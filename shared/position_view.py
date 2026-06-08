"""SOCLE Phase 3 : PositionView -- une compute, deux rendus.

Resout PAR CONSTRUCTION le bug d'incoherence 0,5x (page positions) vs 1,80x
(card) sur le meme ticker. La carte rend la vue complete ; la ligne rend
une PROJECTION de cette meme vue. Aucun recompute cote ligne.

Cf SPEC_POSITIONS_CARD_LINK.md + HANDOFF_SOCLE.md Phase 3.

Composition (le walking-skeleton de tout le socle d'un coup) :
  prices.get(ticker)          -> Datum[price_native]    (Phase 1b)
  prices.fx(currency, EUR)    -> Datum[fx_rate]         (Phase 1b)
  position_valuation_datum    -> Datum[value_eur]       (Phase 2 S2, via derive)
  assemble_card_inputs        -> CardInputs (etape 2 existante)
  derive_card_steer           -> SteerOutput (etape 3 existante)
  =>
  compute_position(ticker)    -> PositionView (composition)
       split en 2 rendus :
       - render_card(view)               -> profondeur (1 position)
       - render_row(project_row(view))   -> triage (N positions)

Invariant central : tout nombre present dans row ET card est byte-identique.
Le test verrouillant `test_byte_identity_ratio_row_and_card` tue le bug.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from shared.datum import Datum

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PositionView:
    """Vue complete d'une position -- la SOURCE UNIQUE consomme par card + row.

    Frozen : anti-tampering downstream. L'etage compose, ne mute pas.
    Les champs Datum portent leur lignage (parents, op, id) pour audit.
    """

    # === Identite (M1 : valeurs litterales user-defined) ===
    thesis_id: int
    ticker: str
    name: str | None = None
    position_type: str | None = None  # 'structural' | 'priced' | 'tactical'
    conviction: int | None = None

    # === Marche (Datums -- valeurs derivees avec lignage) ===
    # value_eur peut etre None si fail-closed L15 (price/fx stale).
    value_eur_datum: Datum | None = None
    price_native: float | None = None      # depuis Datum.value pour affichage
    price_asof: str | None = None
    fx_rate: float | None = None
    fx_asof: str | None = None

    # === Asymetrie (le coeur du bug d'incoherence -- une SEULE source) ===
    # upside / downside derivent du prix actuel vs target/stop natives.
    # ratio = upside / downside (>= 1.0 favorable, < 1.0 defavorable).
    upside_pct: float | None = None
    downside_pct: float | None = None
    asym_ratio: float | None = None
    target_partial_native: float | None = None
    target_full_native: float | None = None
    stop_native: float | None = None
    entry_native: float | None = None

    # === Steer (la chip / l'action -- decide UNE fois, lue partout) ===
    # Ces champs sont consommes IDENTIQUES par card (detail) et row (chip).
    steer_verdict: str | None = None        # de SteerOutput.verdict.value
    steer_chip: str | None = None           # chip pour row (None si calm)
    steer_dominant_reason: str | None = None
    steer_exit_action: str | None = None
    steer_size_action: str | None = None

    # === Thesis state ===
    erosion_verdict: str | None = None      # intact / erosion / invalidation_hit
    discipline_flags: list[str] = field(default_factory=list)  # OVER_CAP, BIAS_OPEN, ...

    # === Fail-closed propage (Datum.degraded chain) ===
    degraded: bool = False
    degraded_reason: str | None = None

    # === Provenance audit ===
    computed_at: str | None = None          # ISO timestamp de compute_position
    inputs_lineage_ids: tuple[str, ...] = ()  # ids des Datums consommes (Merkle-DAG seed)


@dataclass(frozen=True)
class RowView:
    """Projection ligne -- ce que render_row consomme.

    Strictement un SUBSET de PositionView. Aucun champ calcule, aucune
    derivation locale. Construit via project_row(view).
    """

    ticker: str
    name: str | None
    position_type: str | None
    # Marche (faits, M1 propage)
    value_eur: float | None
    price_native: float | None
    # Asymetrie (lue, pas calculee !)
    asym_ratio: float | None
    # Steer (chip si gagnee, sinon None -- silence par defaut)
    steer_chip: str | None
    # Etats visibles a la ligne
    erosion_verdict: str | None
    degraded: bool


def project_row(view: PositionView) -> RowView:
    """Projection ligne : extrait les champs ligne SANS recalculer.

    L'invariant garanti : aucun nombre dans RowView != PositionView.
    Si demain un champ est ajoute en ligne, il doit etre ajoute dans
    PositionView ET projete ici -- pas re-derive cote ligne.
    """
    return RowView(
        ticker=view.ticker,
        name=view.name,
        position_type=view.position_type,
        value_eur=view.value_eur_datum.value if view.value_eur_datum else None,
        price_native=view.price_native,
        asym_ratio=view.asym_ratio,
        steer_chip=view.steer_chip,
        erosion_verdict=view.erosion_verdict,
        degraded=view.degraded,
    )


def _compute_asym_ratio(
    price_native: float | None,
    target_partial: float | None,
    target_full: float | None,
    stop: float | None,
) -> tuple[float | None, float | None, float | None]:
    """Calcule (upside_pct, downside_pct, asym_ratio) depuis prix natifs.

    target_full prioritaire pour upside (la cible long). target_partial fallback.
    Tous en MEME devise native (cf currency_native_invariant memory) :
    interdiction de melanger EUR target et USD price.

    Returns (None, None, None) si donnees manquantes (fail-closed L15).
    """
    if price_native is None or stop is None:
        return (None, None, None)
    target = target_full or target_partial
    if target is None:
        return (None, None, None)
    # %.upside = (target - price) / price ; downside = (price - stop) / price
    upside = (target - price_native) / price_native * 100.0
    downside = (price_native - stop) / price_native * 100.0
    if downside <= 0:
        # Prix sous le stop -> downside negatif, ratio non-defini
        return (upside, downside, None)
    ratio = upside / downside
    return (upside, downside, ratio)


def compute_position(
    thesis_id: int,
    *,
    card_inputs: Any = None,       # CardInputs (intelligence.card_inputs)
    steer_output: Any = None,       # SteerOutput (intelligence.card_steer)
    price_datum: Datum | None = None,
    fx_datum: Datum | None = None,
    value_eur_datum: Datum | None = None,
) -> PositionView:
    """Factory PositionView pour 1 these. Injecte les sources -- ne fait PAS le fetch.

    Pour le walking-skeleton, l'appelant fournit CardInputs + SteerOutput +
    Datums (price/fx/value_eur) -- ca permet de tester deterministement sans
    hit reseau. Le helper assemble_position_for_thesis (a venir) sera le
    callsite production qui orchestre les fetches reels via les gateways.

    Pourquoi inversion de dependances : separer la composition (testable)
    de l'orchestration (live). C'est le pattern PositionValuation actuel
    qui marche -- on l'etend a la vue complete.

    L'argument thesis_id est obligatoire pour la tracabilite ; les autres
    sont optionnels (None = champ absent, REVIEW).
    """
    from datetime import UTC, datetime

    # Identite
    ticker = (card_inputs.ticker if card_inputs else "?") or "?"
    name = None
    if card_inputs and card_inputs.thesis:
        name = card_inputs.thesis.get("name")
    position_type = card_inputs.position_type if card_inputs else None
    conviction = card_inputs.conviction_current if card_inputs else None

    # Marche : extraire les valeurs scalaires depuis les Datums pour affichage
    price_native = price_datum.value if price_datum else None
    price_asof = price_datum.asof if price_datum else None
    fx_rate = fx_datum.value if fx_datum else None
    fx_asof = fx_datum.asof if fx_datum else None

    # Asymetrie : derive UNE fois (le bug 0,5x vs 1,80x venait de 2 derivations)
    thesis_dict = card_inputs.thesis if card_inputs else {}
    target_partial = thesis_dict.get("target_partial_native") or thesis_dict.get("target_partial_price")
    target_full = thesis_dict.get("target_full_native") or thesis_dict.get("target_full_price")
    stop = thesis_dict.get("stop_native") or thesis_dict.get("stop_price")
    entry = thesis_dict.get("entry_native") or thesis_dict.get("entry_price")
    upside_pct, downside_pct, asym_ratio = _compute_asym_ratio(
        price_native, target_partial, target_full, stop
    )

    # Steer (decision unique consomme par card + row)
    steer_verdict = steer_output.verdict.value if (steer_output and steer_output.verdict) else None
    # Chip : on ne l'expose en ligne que si le steer est "act-class" (TRIM/EXIT/RIGHTSIZE/...)
    # Pour la V0 : chip = exit_action si present, sinon size_action si present, sinon None.
    chip = None
    if steer_output:
        if steer_output.exit_action:
            chip = steer_output.exit_action
        elif steer_output.size_action:
            chip = steer_output.size_action

    # Discipline flags (cf SPEC_ALERT_VOCABULARY classe FLAG)
    flags: list[str] = []
    if card_inputs:
        if card_inputs.over_cap_status == "over":
            flags.append("OVER_CAP")
        if card_inputs.bias_events_open:
            flags.append("BIAS_OPEN")
        if not stop:
            flags.append("NO_STOP")
        if not (target_full or target_partial):
            flags.append("NO_TARGET")

    # Fail-closed propage : value_eur_datum.degraded ou aucun value -> degraded
    degraded = False
    degraded_reason = None
    if value_eur_datum is None:
        degraded = True
        degraded_reason = "value_eur unavailable (price/fx stale ou position non-resolved)"
    elif value_eur_datum.degraded:
        degraded = True
        degraded_reason = "value_eur Datum degraded (1+ input stale au-dela SLA)"

    # Lignage : capturer les ids des Datums sources (Merkle-DAG seed)
    lineage: list[str] = []
    if value_eur_datum:
        lineage.append(value_eur_datum.id)
    if price_datum:
        lineage.append(price_datum.id)
    if fx_datum:
        lineage.append(fx_datum.id)

    return PositionView(
        thesis_id=thesis_id,
        ticker=ticker,
        name=name,
        position_type=position_type,
        conviction=conviction,
        value_eur_datum=value_eur_datum,
        price_native=price_native,
        price_asof=price_asof,
        fx_rate=fx_rate,
        fx_asof=fx_asof,
        upside_pct=upside_pct,
        downside_pct=downside_pct,
        asym_ratio=asym_ratio,
        target_partial_native=target_partial,
        target_full_native=target_full,
        stop_native=stop,
        entry_native=entry,
        steer_verdict=steer_verdict,
        steer_chip=chip,
        steer_dominant_reason=steer_output.dominant_reason if steer_output else None,
        steer_exit_action=steer_output.exit_action if steer_output else None,
        steer_size_action=steer_output.size_action if steer_output else None,
        erosion_verdict=card_inputs.erosion_verdict if card_inputs else None,
        discipline_flags=flags,
        degraded=degraded,
        degraded_reason=degraded_reason,
        computed_at=datetime.now(UTC).isoformat(),
        inputs_lineage_ids=tuple(lineage),
    )
