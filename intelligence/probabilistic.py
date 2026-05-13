"""Probabilistic output helpers.
Express uncertainty: format probs, combine weighted predictions,
apply credibility weights, confidence intervals, calibration.
"""

import math


def format_probability(p, conviction=None):
    if p >= 0.5:
        pct = round(p * 100)
        label = "bullish"
    else:
        pct = round((1 - p) * 100)
        label = "bearish"
    if conviction is not None:
        return f"{pct}% {label}, conviction {conviction}/5"
    return f"{pct}% {label}"


def combine_probabilities(weighted_probs):
    if not weighted_probs:
        return 0.5
    tw = sum(w for _, w in weighted_probs)
    if tw == 0:
        return 0.5
    return sum(p * w for p, w in weighted_probs) / tw


def apply_credibility_weight(prob, credibility):
    return 0.5 + (prob - 0.5) * credibility


def wilson_confidence_interval(p, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    spread = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n * n)) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def brier_score(predictions):
    if not predictions:
        return 0.25
    return sum((p - (1.0 if o else 0.0)) ** 2 for p, o in predictions) / len(predictions)


if __name__ == "__main__":
    print("format(0.7) =", format_probability(0.7))
    print("format(0.3, conv=4) =", format_probability(0.3, conviction=4))
    print(
        f"combine [(0.8,0.8),(0.7,0.5),(0.9,0.7)] = {combine_probabilities([(0.8, 0.8), (0.7, 0.5), (0.9, 0.7)]):.3f}"
    )
    print(f"cred-adj 0.8 @ cred 0.6 = {apply_credibility_weight(0.8, 0.6):.3f}")
    lo, hi = wilson_confidence_interval(0.7, 10)
    print(f"Wilson 95% CI (7/10) = ({lo:.3f}, {hi:.3f})")
    print(f"Brier [(0.8,T),(0.6,F),(0.9,T)] = {brier_score([(0.8, True), (0.6, False), (0.9, True)]):.3f}")
