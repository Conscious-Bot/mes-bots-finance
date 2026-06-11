"""Resolver cron pour thesis_predictions (SPEC_THESIS_ALPHA_RESOLVER pièce 4).

Pour chaque prédiction arrivée à maturité (resolve_due_date ≤ today, non
résolue), tente de calculer l'alpha en devise native et écrit le résultat
atomique via update_thesis_resolve_fields. Si la grâce expire sans prix
valide → mark_thesis_prediction_abandoned terminal.

DESIGN — UN appel get_price_on_date + garde grâce (red-team Olivier 11/06) :

get_price_on_date scanne déjà jusqu'à +10j en interne (history(start=date,
end=date+10) → iloc[0] = premier jour coté ≥ date). Donc le resolver NE
fait PAS de boucle jour-par-jour. UN appel + garde `actual ≤ due+grace`.

Sans ce garde, le fallback yfinance interne (+10j) violerait SPEC §4.3 en
silence : on accepterait un prix à due+7 alors que grace_days=5. Le garde
restaure le contrat de fenêtre bornée.

Décisions §0 + §4 SPEC appliquées :
- D : alpha en NATIF fx-strippé. Pas de get_fx_rate_on (fx_at_asof figé à
  la pose, pt_native_asof déjà converti). asof_price_native est le dénom
  partagé → alpha en pourcentage natif pur.
- §4.3 : fenêtre TOUJOURS [due..due+grace_days], indépendante de today.
  Si resolver down 10j et reprend à due+10, prix à due+7 = REJETÉ (hors
  grâce), abandon terminal.
- §4.2 : prix non-fini (NaN, ≤0) traité comme manquant. Si grâce épuisée
  → abandon. Si in-grace → defer (re-pickup demain).
- §4.2 : classify=None malgré prix valide = bug logique. Fail-loud
  (log error + log_event), JAMAIS abandon silencieux (un bug ne tue pas
  un pari, un manquement de donnée si).
- §3.2 : magnitude Brier-type, outcome=sign(alpha) (PAS direction_correct
  — sinon bear-correct scoré 0.81 au lieu de 0.01).

Tests mockent shared.prices.get_price_on_date (pas de réseau).
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

from shared.storage import log_event
from shared.thesis_alpha import (
    classify_direction,
    compute_alpha_realized_pct,
)
from shared.thesis_predictions_writer import (
    get_due_thesis_predictions,
    mark_thesis_prediction_abandoned,
    update_thesis_resolve_fields,
)

log = logging.getLogger(__name__)


def _compute_magnitude_score(
    *,
    your_delta_native_pct: float,
    alpha_realized_pct: float,
    confidence: float | None,
    epsilon_neutral_pct: float,
) -> float | None:
    """Magnitude Brier-type pondéré confiance (SPEC §3.2).

    Formule :
        prob_you = 0.5 + confidence × 0.5 × sign(your_delta)
        outcome  = 1 si alpha > +ε_neutre, 0 si alpha < -ε_neutre, NULL sinon
        magnitude = (prob_you - outcome)² si outcome non-NULL

    Important (catch red-team 11/06) : outcome = sign(alpha), PAS
    direction_correct. Vérifs des 4 quadrants :
    - Bull correct (δ>0, α>0, conf 0.8) : prob=0.9, outcome=1 → 0.01 ✓
    - Bear correct (δ<0, α<0, conf 0.8) : prob=0.1, outcome=0 → 0.01 ✓
    - Bull incorrect (δ>0, α<0, conf 0.8) : prob=0.9, outcome=0 → 0.81 ✓
    - Bear incorrect (δ<0, α>0, conf 0.8) : prob=0.1, outcome=1 → 0.81 ✓

    Si on codait outcome=direction_correct=1 sur bear-correct, le score
    serait (0.1-1)² = 0.81 = catastrophe sur un pari JUSTE.

    Returns None si confidence absente OU zone neutre |alpha|<ε.
    """
    if confidence is None:
        return None
    if not math.isfinite(alpha_realized_pct):
        return None
    if abs(alpha_realized_pct) < epsilon_neutral_pct:
        return None  # zone neutre, pas de Brier score

    # sign(your_delta) ∈ {-1, +1} (your_delta=0 = no_bet, gate à la pose)
    sign_delta = 1 if your_delta_native_pct > 0 else -1
    prob_you = 0.5 + confidence * 0.5 * sign_delta
    outcome = 1 if alpha_realized_pct > 0 else 0
    return (prob_you - outcome) ** 2


def resolve_due_thesis_predictions(
    today: date | None = None,
    grace_days: int = 5,
    epsilon_neutral_pct: float = 1.0,
    epsilon_delta_pct: float = 1.0,
) -> dict[str, int]:
    """Résout les paris arrivés à maturité (cron daily).

    Pour chaque prediction dans get_due_thesis_predictions :
    1. UN appel shared.prices.get_price_on_date(ticker, due_date).
       (yfinance fallback interne +10j → garde explicite ci-dessous.)
    2. Validation prix : (non-None, math.isfinite, > 0). Non-fini = manquant.
    3. Garde §4.3 : actual_date ≤ due+grace_days. Si actual au-delà →
       traité comme manquant (le fallback yfinance ne peut pas violer la
       grâce).
    4. Trois branches :
       a) Prix valide ET in-grace → compute_alpha + classify + write atomique
       b) Pas de prix valide ET today > due+grace → mark_abandoned terminal
       c) Pas de prix valide ET today ≤ due+grace → defer (NULL, re-pickup)
    5. Garde classify=None défensif : log error, defer (jamais abandon
       silencieux). Un bug ne tue pas un pari, un manquement si.

    Args:
        today : date de référence (default UTC today)
        grace_days : fenêtre de grâce dure (SPEC §4.3, default 5)
        epsilon_neutral_pct : seuil neutral |alpha|<ε → exclu scoring
        epsilon_delta_pct : seuil no_bet (déjà gaté à la pose, défensif ici)

    Returns:
        Compteurs counter avec invariant garanti par construction (L27) :
            attempted == resolved + neutral + abandoned + deferred + classify_none_bugs + write_failed

        write_failed capture les cas où un writer (mark_abandoned ou
        update_thesis_resolve_fields) retourne False (race condition,
        trigger 2 qui mord si pred concurremment résolu, etc.). Sans ce
        compteur, l'invariant casserait silencieusement dans ces cas
        pathologiques — exactement la classe L27 (cohérence mécanique >
        vigilance) qu'on ferme par construction, pas par chance.
    """
    if today is None:
        today = datetime.now(UTC).date()

    # Import différé : ce module est mockable par les tests via monkeypatch
    # sur shared.prices.get_price_on_date sans qu'on déclenche d'import live.
    from shared import prices as _prices

    counters = {
        "attempted": 0,
        "resolved": 0,
        "neutral": 0,
        "abandoned": 0,
        "deferred": 0,
        "classify_none_bugs": 0,
        "write_failed": 0,
    }

    due = get_due_thesis_predictions(today=today)
    for pred in due:
        counters["attempted"] += 1
        pid = pred["id"]
        ticker = pred["ticker"]
        due_date = date.fromisoformat(pred["resolve_due_date"])
        grace_deadline = due_date + timedelta(days=grace_days)

        # Étape 1+2+3 : un appel + validation + garde grâce
        valid_price, resolve_price = _fetch_price_in_grace(
            ticker=ticker, due_date=due_date, grace_deadline=grace_deadline,
            fetcher=_prices.get_price_on_date,
        )

        if not valid_price:
            # Étape 4b/4c : pas de prix utilisable
            if today > grace_deadline:
                # Grâce épuisée → abandon terminal (§4.2)
                ok = mark_thesis_prediction_abandoned(
                    prediction_id=pid, reason="price_unavailable",
                )
                if ok:
                    counters["abandoned"] += 1
                else:
                    # Cure L27 : invariant attempted == Σ par construction.
                    # Sans ce compteur, write_failed orphelin invisible.
                    counters["write_failed"] += 1
                    log.warning(
                        f"thesis_resolver: mark_abandoned failed for pred_id={pid}"
                    )
            else:
                # In-grace, defer (re-pickup demain via get_due)
                counters["deferred"] += 1
                log.info(
                    f"thesis_resolver: defer pred_id={pid} ticker={ticker} "
                    f"in-grace (today={today}, deadline={grace_deadline})"
                )
            continue

        # Étape 4a : prix valide in-grace → compute + classify + write
        alpha = compute_alpha_realized_pct(
            resolve_price_native=resolve_price,
            pt_native_asof=pred["pt_native_asof"],
            asof_price_native=pred["asof_price_native"],
        )
        classify = classify_direction(
            your_delta_native_pct=pred["your_delta_native_pct"],
            alpha_realized_pct=alpha,
            epsilon_neutral_pct=epsilon_neutral_pct,
            epsilon_delta_pct=epsilon_delta_pct,
        )

        # Garde classify=None défensif (SPEC §4.2) : fail-loud, defer
        if classify is None:
            log.error(
                f"thesis_resolver: classify=None malgré prix valide pour "
                f"pred_id={pid} ticker={ticker} alpha={alpha} — bug logique. "
                f"Defer (NULL), surface monitor, JAMAIS abandon silencieux."
            )
            log_event(
                "thesis_resolve_classify_none_bug",
                {
                    "prediction_id": pid,
                    "ticker": ticker,
                    "alpha_realized_pct": alpha,
                    "resolve_price": resolve_price,
                },
            )
            counters["classify_none_bugs"] += 1
            continue

        # Compute magnitude (Brier-type, outcome=sign(alpha))
        magnitude = _compute_magnitude_score(
            your_delta_native_pct=pred["your_delta_native_pct"],
            alpha_realized_pct=alpha,
            confidence=pred.get("confidence"),
            epsilon_neutral_pct=epsilon_neutral_pct,
        )

        # Write atomique
        ok = update_thesis_resolve_fields(
            prediction_id=pid,
            resolve_price_native=resolve_price,
            alpha_realized_pct=alpha,
            classify_result=classify,
            magnitude_score=magnitude,
        )
        if not ok:
            # Cure L27 : invariant attempted == Σ par construction (race condition,
            # trigger 2 mord si pred concurremment résolu, etc.).
            counters["write_failed"] += 1
            log.warning(f"thesis_resolver: update_resolve_fields failed pred_id={pid}")
            continue

        if classify in ("correct", "incorrect"):
            counters["resolved"] += 1
        elif classify == "neutral":
            counters["neutral"] += 1
        elif classify == "no_bet":
            # Gate à la pose devrait empêcher, mais défensif
            counters["resolved"] += 1  # consommé comme résolu
            log.warning(
                f"thesis_resolver: classify=no_bet à la résolution pour pred_id={pid} "
                f"(gate à la pose devrait empêcher — vérifier)"
            )

    log.info(
        f"thesis_resolver done : attempted={counters['attempted']} "
        f"resolved={counters['resolved']} neutral={counters['neutral']} "
        f"abandoned={counters['abandoned']} deferred={counters['deferred']} "
        f"classify_none_bugs={counters['classify_none_bugs']} "
        f"write_failed={counters['write_failed']}"
    )

    return counters


def _fetch_price_in_grace(
    *,
    ticker: str,
    due_date: date,
    grace_deadline: date,
    fetcher: Any,
) -> tuple[bool, float]:
    """UN appel + validation + garde grâce §4.3.

    Returns:
        (valid: bool, resolve_price: float)
        valid = False si prix manquant / non-fini / hors fenêtre grâce.
    """
    try:
        # Passer isoformat() explicite (str) au lieu d'un objet date — le fetcher
        # accepte str|datetime mais la conversion interne via str(date)[:10]
        # serait implicite ; explicite > implicite.
        actual_str, price = fetcher(ticker, due_date.isoformat())
    except Exception as e:
        log.warning(f"thesis_resolver: fetch error for {ticker} @ {due_date}: {e}")
        return (False, 0.0)

    if actual_str is None or price is None:
        return (False, 0.0)
    if not math.isfinite(price) or price <= 0:
        return (False, 0.0)

    # Garde §4.3 : actual_date ≤ due+grace_days (le fallback +10j yfinance
    # ne peut pas violer la grâce, c'est ce garde qui restaure la borne)
    try:
        actual_date = date.fromisoformat(actual_str)
    except (ValueError, TypeError):
        log.warning(f"thesis_resolver: actual_str non parsable '{actual_str}' for {ticker}")
        return (False, 0.0)
    if actual_date > grace_deadline:
        log.info(
            f"thesis_resolver: prix dispo à {actual_date} pour {ticker} mais "
            f"hors grâce (deadline={grace_deadline}) — traité comme manquant §4.3"
        )
        return (False, 0.0)

    return (True, float(price))
