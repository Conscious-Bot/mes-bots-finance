"""Gates de creation thèse — Mentor heuristiques mecanisées (M-B pillar).

Encodage des principes mentors battle-tested en gates deterministes (cf
docs/LESSONS.md L14 anti-pattern #1 : on NE clone PAS de personas LLM qui
debattent ; on encode la regle directement).

Gates implementes (Phase post-J-day, doctrine "mesure-passe pas predit-futur") :

- **M1 Buffett/Munger quality** : conviction >= 4 EXIGE solidité ∈
  {Incontournable, Solide}. Catch : "tu te survends sur du Fragile".
  Source solidité : canonical_perimeter.json (user-tagged).
  Si ticker hors canonical -> warning only (pas hard block, on n'a pas de signal).

- **M2 Taleb/Pabrai asymmetry** : conviction >= 4 EXIGE
  asymmetry_ratio = (target_full - entry) / (entry - stop_price) >= 2.0
  pour long, et la symetrique pour short. Catch : "convaincu mais
  upside ridicule vs downside accepte".
  Necessite stop_price + target_full. Si manquant -> warning only
  (pas de stop = autre invariant pris ailleurs, cf shared/thesis_invariants).

Style :
- Validators retournent (passed: bool, message: str). Pas d'exception (le
  caller `intelligence.thesis.add_thesis` decide bloquant ou warning).
- Strict mode = parametre `strict_creation=True` qui transforme en
  exception ; defaut = warning seulement (preserve compat retro).
- Pas de LLM call, pas de DB write -- pure logique deterministe.

Tests :
- M1 : conviction 4 + solidité Solide -> pass
- M1 : conviction 5 + solidité Fragile -> fail
- M1 : conviction 3 + solidité Fragile -> pass (gate ne fire que conviction>=4)
- M2 : conviction 4 long upside=15 downside=5 -> pass (ratio=3)
- M2 : conviction 4 long upside=8 downside=5 -> fail (ratio=1.6)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


# === Constantes encodees ===================================================

SOLIDITE_ACCEPTABLE_HIGH_CONVICTION = {"Incontournable", "Solide"}
CONVICTION_HIGH_THRESHOLD = 4
ASYMMETRY_MIN_RATIO = 2.0


@dataclass(frozen=True, slots=True)
class GateResult:
    """Resultat d'un check de gate. passed=True quand satisfait."""
    gate_name: str
    passed: bool
    message: str


# === M1 Buffett/Munger quality =============================================


def check_m1_buffett_quality(
    ticker: str,
    conviction: int,
    solidite: str | None,
) -> GateResult:
    """Conviction >= 4 exige solidité ∈ {Incontournable, Solide}.

    Args:
        ticker : pour le message uniquement.
        conviction : 1-5.
        solidite : "Incontournable" / "Solide" / "Incertain" / "Fragile" / None.

    Returns:
        GateResult. passed=False si conviction >=4 ET solidité tagged comme
        Incertain ou Fragile. Si solidité None (hors canonical_perimeter),
        passed=True avec message warning (on ne bloque pas sur absence).
    """
    if conviction < CONVICTION_HIGH_THRESHOLD:
        return GateResult(
            gate_name="M1_buffett_quality",
            passed=True,
            message=f"conviction {conviction} < {CONVICTION_HIGH_THRESHOLD} -- gate ne fire pas",
        )
    if solidite is None:
        return GateResult(
            gate_name="M1_buffett_quality",
            passed=True,
            message=(
                f"warning : {ticker} pas dans canonical_perimeter.json -- "
                "solidité inconnue, ne peut pas verifier M1 Buffett quality"
            ),
        )
    if solidite in SOLIDITE_ACCEPTABLE_HIGH_CONVICTION:
        return GateResult(
            gate_name="M1_buffett_quality",
            passed=True,
            message=f"solidité {solidite!r} compatible conviction {conviction}",
        )
    return GateResult(
        gate_name="M1_buffett_quality",
        passed=False,
        message=(
            f"M1 Buffett FAIL : {ticker} conviction {conviction} demande solidité "
            f"∈ {sorted(SOLIDITE_ACCEPTABLE_HIGH_CONVICTION)} mais ticker tagué "
            f"{solidite!r}. Soit baisse conviction ≤ 3, soit re-tag canonical "
            "(rare, justifie). Catch Buffett : 'on ne paye pas pour low-quality '"
            "'with high conviction'."
        ),
    )


# === M2 Taleb/Pabrai asymmetry =============================================


def _compute_asymmetry_ratio(
    direction: str,
    entry: float | None,
    target_full: float | None,
    stop_price: float | None,
) -> float | None:
    """Calcule (upside/downside) ratio. Devises ASSUMEES natives consistantes
    (gate cf shared/thesis_invariants verifie ca separement). None si
    impossible (manque entry / target / stop).
    """
    if entry is None or target_full is None or stop_price is None:
        return None
    if entry <= 0:
        return None
    if direction == "long":
        upside = target_full - entry
        downside = entry - stop_price
    elif direction == "short":
        upside = entry - target_full
        downside = stop_price - entry
    else:
        return None
    if downside <= 0:
        return None  # symmetric : downside doit etre positif (stop sous entry pour long)
    if upside <= 0:
        return None  # target dans le mauvais sens
    return upside / downside


def check_m2_taleb_asymmetry(
    ticker: str,
    conviction: int,
    direction: str,
    entry: float | None,
    target_full: float | None,
    stop_price: float | None,
) -> GateResult:
    """Conviction >= 4 exige asymmetry_ratio >= 2.0 (upside vs downside).

    Args:
        ticker : pour message.
        conviction : 1-5.
        direction : 'long' / 'short' / 'watch'. 'watch' -> gate ne fire pas.
        entry / target_full / stop_price : meme devise native, deja valides
          par shared/thesis_invariants upstream.

    Returns:
        GateResult. passed=False si conviction >=4 ET asymmetry_ratio < 2.0
        et calculable. Si manque entry/target/stop -> passed=True avec warning
        (un autre invariant signalera l'absence de stop).
    """
    if conviction < CONVICTION_HIGH_THRESHOLD:
        return GateResult(
            gate_name="M2_taleb_asymmetry",
            passed=True,
            message=f"conviction {conviction} < {CONVICTION_HIGH_THRESHOLD} -- gate ne fire pas",
        )
    if direction == "watch":
        return GateResult(
            gate_name="M2_taleb_asymmetry",
            passed=True,
            message="direction=watch -- asymmetry non applicable",
        )
    ratio = _compute_asymmetry_ratio(direction, entry, target_full, stop_price)
    if ratio is None:
        return GateResult(
            gate_name="M2_taleb_asymmetry",
            passed=True,
            message=(
                "warning : asymmetry_ratio non calculable (entry/target/stop "
                "manquants ou incoherents)"
            ),
        )
    if ratio >= ASYMMETRY_MIN_RATIO:
        return GateResult(
            gate_name="M2_taleb_asymmetry",
            passed=True,
            message=f"asymmetry_ratio={ratio:.2f} >= {ASYMMETRY_MIN_RATIO} (Taleb compat)",
        )
    return GateResult(
        gate_name="M2_taleb_asymmetry",
        passed=False,
        message=(
            f"M2 Taleb FAIL : {ticker} conviction {conviction} demande "
            f"asymmetry_ratio >= {ASYMMETRY_MIN_RATIO} mais calcul donne "
            f"{ratio:.2f}. (upside {direction}={target_full}-{entry} vs "
            f"downside {entry}-{stop_price}). Catch Taleb : 'high conviction "
            "+ low asymmetry = sous-paye par le risque'."
        ),
    )


# === Aggregator ============================================================


def run_creation_gates(
    ticker: str,
    direction: str,
    conviction: int,
    solidite: str | None = None,
    entry: float | None = None,
    target_full: float | None = None,
    stop_price: float | None = None,
) -> list[GateResult]:
    """Lance tous les gates de creation thèse.

    Returns liste de GateResult. Caller decide bloquant ou warning.
    """
    return [
        check_m1_buffett_quality(ticker, conviction, solidite),
        check_m2_taleb_asymmetry(
            ticker, conviction, direction, entry, target_full, stop_price
        ),
    ]


def fetch_solidite_for_ticker(ticker: str) -> str | None:
    """Helper : lookup solidité dans canonical_perimeter.json via shared.book.
    Returns None si ticker hors perimeter (signal pour M1 warning-only)."""
    try:
        from shared.book import _load_canonical
        canonical = _load_canonical()
        for pos in canonical.get("positions") or []:
            if pos.get("ticker") == ticker:
                return pos.get("solidite")
    except Exception as e:
        log.warning(f"fetch_solidite_for_ticker {ticker} failed: {e}")
    return None
