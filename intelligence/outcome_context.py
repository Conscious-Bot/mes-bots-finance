"""outcome_context -- injection des lecons d'outcomes passes dans le prompt scorer.

Strategie user 31/05/2026 point #3c : "Injection outcome -> contexte :
reinjecte dans le prompt les lecons d'outcomes passes + analogues + drift
de calibration. C'est litteralement ta PHILOSOPHY (la boucle qui enrichit
le contexte). Construire ca = le bot apprend de lui-meme."

Architecture :
- Analogues : K predictions historiques resolues sur le meme ticker ou
  meme signal_type, avec leur outcome (correct/incorrect/neutral). Format
  liste markdown court pour injection prompt.
- Calibration drift : si une CalibrationMap est fittee (cf recalib_map.py),
  resume "tes 0.70 historiques ont realise a 0.60 -- attention overconfidence".
- Lessons : top patterns d'erreurs recents (e.g. "les bullish sur tickers
  Korean ont rate 4/5 fois sur 30j").

Activation :
- K_analogues : min 3 analogues pour les inclure (sinon noise > signal)
- Calibration drift : disponible si recalib_map.fit_calibration_map() retourne
  pas None (= MIN_N_FIT reached)
- Lessons : disponible si N total resolved >= 20

Integration : appele depuis signal_scorer_v2.py au build du prompt. Le LLM
recoit en plus :
    ## Contexte historique
    Analogues similaires resolus :
    - NVDA bullish 14j -> incorrect (-6.3% vs +5% cible)
    - AVGO bullish 14j -> correct (+5.1% > seuil)
    Calibration : tes 0.7 historiques ont realise a 0.6 (overconfidence)
    Lessons : bullish post-earnings ont rate 4/5 fois en mai

Pas branche en J0 (scaffolding), s'activera dimension par dimension quand
les seuils sont atteints.

Discipline : reste honnete sur le cold-start. Retourne string vide ("") si
rien d'utilisable -- pas de remplissage decoratif.
"""

from __future__ import annotations

import logging
import sqlite3

from shared import storage

log = logging.getLogger(__name__)

K_ANALOGUES_DEFAULT = 5
K_ANALOGUES_MIN = 3
LESSONS_MIN_N = 20


def fetch_analogues(
    cx: sqlite3.Connection,
    ticker: str,
    signal_type: str | None,
    k: int = K_ANALOGUES_DEFAULT,
) -> list[dict]:
    """K predictions resolues les plus recentes pour ce ticker (priorite) ou
    signal_type (fallback). Exclut neutral + v0."""
    rows = cx.execute(
        f"""
        SELECT ticker, signal_type, direction, horizon_days, outcome,
               return_pct, resolved_at, probability_at_creation
        FROM predictions
        WHERE resolved_at IS NOT NULL
          AND outcome IN ('correct', 'incorrect')
          AND {storage.substance_predictions_filter()}
          AND (ticker = ? OR signal_type = ?)
        ORDER BY resolved_at DESC
        LIMIT ?
        """,
        (ticker, signal_type, k),
    ).fetchall()
    return [
        {
            "ticker": r[0],
            "signal_type": r[1],
            "direction": r[2],
            "horizon_days": r[3],
            "outcome": r[4],
            "return_pct": r[5],
            "resolved_at": r[6],
            "probability_at_creation": r[7],
        }
        for r in rows
    ]


def fetch_recent_lessons(cx: sqlite3.Connection, window_days: int = 30) -> dict | None:
    """Patterns d'erreurs recents : par direction / par ticker suffix / par
    signal_type. Retourne None si insufficient data."""
    rows = cx.execute(
        f"""
        SELECT direction, outcome, COUNT(*) AS n
        FROM predictions
        WHERE resolved_at IS NOT NULL
          AND outcome IN ('correct', 'incorrect')
          AND {storage.substance_predictions_filter()}
          AND resolved_at >= datetime('now', ?)
        GROUP BY direction, outcome
        """,
        (f"-{window_days} days",),
    ).fetchall()
    if not rows:
        return None
    by_direction: dict[str, dict[str, int]] = {}
    total = 0
    for direction, outcome, n in rows:
        by_direction.setdefault(direction, {"correct": 0, "incorrect": 0})
        by_direction[direction][outcome] = n
        total += n
    if total < LESSONS_MIN_N:
        return None
    return {"window_days": window_days, "total": total, "by_direction": by_direction}


def build_outcome_context(
    cx: sqlite3.Connection,
    ticker: str,
    signal_type: str | None,
    k_analogues: int = K_ANALOGUES_DEFAULT,
    include_calibration_drift: bool = True,
) -> str:
    """Build le markdown context fragment pour injection prompt scorer.

    Retourne string vide ("") si rien d'utilisable (cold start) -- le scorer
    fonctionnera sans, comme avant.
    """
    parts = []

    analogues = fetch_analogues(cx, ticker, signal_type, k=k_analogues)
    if len(analogues) >= K_ANALOGUES_MIN:
        parts.append("## Analogues historiques resolus")
        for a in analogues:
            ret_str = f"{a['return_pct']:+.1%}" if a["return_pct"] is not None else "?"
            parts.append(
                f"- {a['ticker']} {a['direction']} {a['horizon_days']}j "
                f"-> {a['outcome']} ({ret_str})"
            )
        parts.append("")

    if include_calibration_drift:
        try:
            from intelligence import recalib_map

            cmap = recalib_map.fit_calibration_map(cx)
            if cmap is not None:
                # Sample 5 raw probs to show the drift
                samples = [0.55, 0.65, 0.75, 0.85, 0.95]
                deltas = [(p, cmap.correct(p)) for p in samples]
                parts.append("## Calibration drift (fitted vs raw)")
                for raw, corrected in deltas:
                    parts.append(f"- raw {raw:.2f} -> calibre {corrected:.2f}")
                parts.append(f"(fitted sur n={cmap.n_fit} predictions, method={cmap.method})")
                parts.append("")
        except Exception as e:
            log.warning(f"outcome_context : calibration drift skip ({e})")

    lessons = fetch_recent_lessons(cx)
    if lessons is not None:
        parts.append("## Pattern d'erreurs recents (30j)")
        for direction, counts in lessons["by_direction"].items():
            total_dir = counts["correct"] + counts["incorrect"]
            if total_dir > 0:
                wr = counts["correct"] / total_dir
                parts.append(
                    f"- {direction} : {counts['correct']}/{total_dir} corrects ({wr:.0%})"
                )
        parts.append("")

    return "\n".join(parts).strip()
