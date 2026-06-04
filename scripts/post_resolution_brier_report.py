#!/usr/bin/env python3
"""Post-resolution Brier report. A lancer manuellement APRES le job
daily_resolve_job qui tourne a 9h00 chaque jour.

Le format_resolve_report dans intelligence/learning.py envoie via Telegram
un summary correct/incorrect/neutral counts mais SANS le Brier moyen --
qui est la vraie metrique calibration. Ce script complete le report.

Bootstrap CI ajoute 04/06/2026 (advisor : "garde-fou d'humilite, pas mesure
de performance"). A N=45, un CI plus large que le score n'est PAS non-
instructif : c'est l'etat le plus instructif, il crie "tu n'as pas encore
de signal, ne lis pas ce chiffre". Special urgence J-day 10/06 ou la
tentation de surlire un Brier sera maximale.

Usage (depuis le ROOT du projet pour que les imports `from shared` marchent) :
  python -m scripts.post_resolution_brier_report [YYYY-MM-DD]

  Sans argument : analyse toutes les predictions resolues aujourd'hui.
  Avec date : analyse celles resolues a cette date precise.

Exemple 10/06 a 9h05 (apres le cron daily_resolve_job 9h) :
  python -m scripts.post_resolution_brier_report 2026-06-10
"""

import random
import sys
from datetime import date

_BOOTSTRAP_N = 1000  # resamples ; 1000 = standard percentile bootstrap
_BASELINE_NO_SKILL = 0.25  # Brier du prior trivial constant 0.5
_CI_LO = 2.5
_CI_HI = 97.5


def _bootstrap_brier_ci(scores: list[float], n_resample: int = _BOOTSTRAP_N) -> tuple[float, float, float]:
    """Bootstrap percentile CI 95% sur la moyenne Brier.

    Retourne (mean, ci_low, ci_high). Resampling avec remplacement, n_resample
    fois, calcule moyenne sur chaque sample, prend percentiles 2.5 / 97.5.

    Deterministe via random.seed(42) pour reproducibilite des rapports.
    """
    if not scores:
        return (0.0, 0.0, 0.0)
    mean = sum(scores) / len(scores)
    rng = random.Random(42)
    means = []
    n = len(scores)
    for _ in range(n_resample):
        sample = [scores[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int(_CI_LO / 100 * n_resample)
    hi_idx = int(_CI_HI / 100 * n_resample) - 1
    return (mean, means[lo_idx], means[hi_idx])


def _format_ci(mean: float, lo: float, hi: float) -> str:
    """Formate "0.295 [0.18, 0.41] (95% CI bootstrap)" """
    return f"{mean:.3f} [{lo:.3f}, {hi:.3f}] (95% CI bootstrap n={_BOOTSTRAP_N})"


def _ci_verdict(mean: float, lo: float, hi: float, n: int) -> str:
    """Verdict honnete : CI englobe-t-il la baseline no-skill (0.25) ?"""
    if lo <= _BASELINE_NO_SKILL <= hi:
        return (
            f"⚠️  CI [{lo:.3f}, {hi:.3f}] ENGLOBE la baseline no-skill 0.250.\n"
            f"   Sur N={n}, on ne peut PAS distinguer skill de chance.\n"
            f"   Ne PAS lire le point estimate comme un verdict de calibration."
        )
    elif hi < _BASELINE_NO_SKILL:
        return (
            f"✓ CI [{lo:.3f}, {hi:.3f}] EST EN DESSOUS de baseline 0.250.\n"
            f"   Sur N={n}, signal positif (mieux que chance) avec 95% confiance."
        )
    else:  # lo > baseline
        return (
            f"✗ CI [{lo:.3f}, {hi:.3f}] EST AU-DESSUS de baseline 0.250.\n"
            f"   Sur N={n}, signal NEGATIF (pire que chance) avec 95% confiance."
        )


def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()

    from shared import storage

    with storage.db() as cx:
        rows = cx.execute(
            """SELECT id, ticker, direction, baseline_price, final_price,
                      return_pct, outcome, probability_at_creation, brier_score,
                      signal_id
               FROM predictions
               WHERE date(resolved_at) = ? AND resolved_at IS NOT NULL
               ORDER BY ticker, id""",
            (target_date,),
        ).fetchall()

    if not rows:
        print(f"Aucune prediction resolue le {target_date}.")
        return 0

    print(f"=== Brier report : {len(rows)} predictions resolues le {target_date} ===\n")

    n_correct = n_incorrect = n_neutral = 0
    briers = []
    clusters = {}

    print(f"{'#':<4} {'Ticker':<8} {'Dir':<6} {'Ret%':>7} {'Outcome':<10} {'Prob':>6} {'Brier':>7}")
    print("-" * 70)
    for r in rows:
        d = dict(r)
        if d["outcome"] == "correct":
            n_correct += 1
        elif d["outcome"] == "incorrect":
            n_incorrect += 1
        else:
            n_neutral += 1

        if d["brier_score"] is not None:
            briers.append(d["brier_score"])
            key = (d["signal_id"], d["ticker"], d["direction"])
            clusters.setdefault(key, []).append(d["brier_score"])

        brier_str = f"{d['brier_score']:.3f}" if d["brier_score"] is not None else "  --"
        print(
            f"{d['id']:<4} {d['ticker']:<8} {d['direction']:<6} "
            f"{d['return_pct'] * 100:>+6.1f}% {d['outcome']:<10} "
            f"{d['probability_at_creation']:>6.3f} {brier_str:>7}"
        )

    print("\n=== Outcomes ===")
    total = len(rows)
    print(f"  correct    : {n_correct} ({n_correct / total * 100:.0f}%)")
    print(f"  incorrect  : {n_incorrect} ({n_incorrect / total * 100:.0f}%)")
    print(f"  neutral    : {n_neutral} ({n_neutral / total * 100:.0f}%) -- exclu Brier")

    if briers:
        mean, lo, hi = _bootstrap_brier_ci(briers)
        print("\n=== Brier (raw, sans dedup) ===")
        print(f"  n scored : {len(briers)}")
        print(f"  brier    : {_format_ci(mean, lo, hi)}")
        print("  baseline trivial (prior 0.5 constant) : 0.250")
        print()
        for line in _ci_verdict(mean, lo, hi, len(briers)).split("\n"):
            print(f"  {line}")

    if clusters:
        cluster_briers = [sum(v) / len(v) for v in clusters.values()]
        mean_d, lo_d, hi_d = _bootstrap_brier_ci(cluster_briers)
        print("\n=== Brier dedup par cluster (signal_id x ticker x direction) ===")
        print(f"  n clusters uniques : {len(clusters)} (vs {len(briers)} predictions brier-scored)")
        print(f"  dedup ratio        : {len(briers) / len(clusters):.2f}")
        print(f"  brier (dedup)      : {_format_ci(mean_d, lo_d, hi_d)}")
        print(f"  range cluster_briers : [{min(cluster_briers):.3f}, {max(cluster_briers):.3f}]")
        print()
        for line in _ci_verdict(mean_d, lo_d, hi_d, len(cluster_briers)).split("\n"):
            print(f"  {line}")

    unique_probs = {round(r["probability_at_creation"], 2) for r in rows}
    if briers and len(unique_probs) <= 2:
        print("\n=== ⚠️  WARNING ===")
        print("  Toutes probabilites dans <= 2 buckets uniques.")
        print("  Reliability diagram = 1 point ou ligne degeneree.")
        print("  Calibration non-publiable scientifiquement sur ce batch.")
        print("  Cause : V1 mono-bucket (cf decision_log/01_calibration_unanchored.md).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
