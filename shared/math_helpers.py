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
