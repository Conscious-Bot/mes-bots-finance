"""Phase Solidification — pure math helpers extracted for testability.

Mirrors the inline math in:
- shared/storage.py L52-58 (update_credibility SQL clamping)
- intelligence/learning.py L107-111 (Brier score inline)

These are NOT yet used by production code. Production refactor is next step
once tests validate the helpers vs current behavior.
"""


def clamp_credibility(current, delta):
    """Mirror SQL `MAX(0, MIN(1, credibility + ?))`.

    Invariants:
    - Output in [0, 1] for any current, delta in R
    - clamp(c, 0) == c (when c in [0,1])
    - clamp(0, negative) == 0
    - clamp(1, positive) == 1
    """
    if current is None:
        return None
    return max(0.0, min(1.0, float(current) + float(delta)))


_BRIER_OUTCOME_MAP = {"correct": 1.0, "incorrect": 0.0, "neutral": 0.5}


def compute_brier_score(prob, outcome):
    """Mirror intelligence/learning.py L107-111.

    Args:
        prob: probability_at_creation in [0, 1], or None
        outcome: 'correct' | 'incorrect' | 'neutral' | other (defaults 0.5)

    Returns:
        (prob - outcome_binary) ** 2 in [0, 1], or None if prob is None.

    Invariants:
    - Output in [0, 1] for prob in [0,1]
    - == 0 when prob == outcome_binary
    - Symmetric: brier(p, 'incorrect') == brier(1-p, 'correct')
    - Returns None when prob is None
    """
    if prob is None:
        return None
    outcome_binary = _BRIER_OUTCOME_MAP.get(outcome, 0.5)
    return (float(prob) - outcome_binary) ** 2


def estimate_probability(score, credibility, signal_type=None, impact_magnitude=None):
    """Differentiated P(directional call correct) at prediction creation.

    LEARNABLE PRIOR, not calibrated. Makes the Brier informative and iterable
    (vs the old constant = source credibility). Real calibration comes from the
    resolve -> reliability -> adjust loop.

    Invariants:
    - Output in [0.50, 0.72]
    - Non-decreasing in score
    - catalyst >= narrative for identical other inputs
    - 0.50 floor when all inputs weak/None
    """
    p = 0.50
    p += min(max((score if score is not None else 3) - 3, 0), 5) * 0.032
    if credibility is not None:
        p += (credibility - 0.5) * 0.4
    if signal_type == "catalyst":
        p += 0.03
    elif signal_type == "narrative":
        p -= 0.02
    if impact_magnitude is not None and impact_magnitude >= 4:
        p += 0.03
    return round(min(0.72, max(0.50, p)), 4)


def brier_for(prob: float | None, outcome: str) -> float | None:
    """Brier d'une resolution binaire. None si non-scoreable : prob absente,
    ou outcome 'neutral' (non-resolution — credibility l'exclut deja, delta==0).
    Audit 2026-05-23."""
    if prob is None or outcome == "neutral":
        return None
    return (prob - (1.0 if outcome == "correct" else 0.0)) ** 2


def aggregate_brier_dedup(predictions: list[dict]) -> dict:
    """Agregat Brier dedupplique par cluster.

    Probleme decouvert 29/05 dry-run resolution 10/06 : 49 predictions due,
    dont NVDA x 7, AMD x 7, AVGO x 7, MU x 6 -- meme cluster signal genere
    7 predictions identiques baseline+target -> 1 vrai outcome compte 7x
    dans le Brier moyen. Un sceptique audit Path 6 verrait juste ca.

    Le fix : on regroupe par cluster (signal_id, ticker, direction) et on
    publie 1 outcome par cluster, brier moyen par cluster.

    Args:
        predictions: list de dicts avec au moins keys: signal_id, ticker,
                     direction, brier_score (None = neutral, exclu).

    Returns:
        {
            "n_unique_clusters": int (= nb d'outcomes uniques effectifs),
            "n_raw_predictions": int (= nb predictions brutes),
            "dedup_ratio": float (1.0 = pas de doublons, >1 = doublons),
            "avg_brier": float | None,
            "n_neutral_excluded": int,
        }
    """
    if not predictions:
        return {"n_unique_clusters": 0, "n_raw_predictions": 0,
                "dedup_ratio": 1.0, "avg_brier": None, "n_neutral_excluded": 0}
    n_neutral = sum(1 for p in predictions if p.get("brier_score") is None)
    by_cluster: dict[tuple, list[float]] = {}
    for p in predictions:
        b = p.get("brier_score")
        if b is None:
            continue
        key = (p.get("signal_id"), p.get("ticker"), p.get("direction"))
        by_cluster.setdefault(key, []).append(b)
    n_unique = len(by_cluster)
    n_raw = sum(len(v) for v in by_cluster.values())
    cluster_briers = [sum(v) / len(v) for v in by_cluster.values()]
    avg = sum(cluster_briers) / len(cluster_briers) if cluster_briers else None
    return {
        "n_unique_clusters": n_unique,
        "n_raw_predictions": n_raw,
        "dedup_ratio": n_raw / max(n_unique, 1),
        "avg_brier": avg,
        "n_neutral_excluded": n_neutral,
    }


def credibility_from_hitrate(n_correct: int, n_incorrect: int, alpha: float = 2.0) -> float:
    """Source credibility = hit-rate directionnel, shrinkage Beta(alpha,alpha) vers 0.5.

    (n_correct + alpha) / (n_correct + n_incorrect + 2*alpha), clampe [0,1].
    Coin-flip (correct==incorrect) -> 0.5 ; le shrinkage borne le perfect sous 1.0.
    """
    total = n_correct + n_incorrect + 2.0 * alpha
    return max(0.0, min(1.0, (n_correct + alpha) / total))
