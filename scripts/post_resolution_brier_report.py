#!/usr/bin/env python3
"""Post-resolution Brier report. A lancer manuellement APRES le job
daily_resolve_job qui tourne a 9h00 chaque jour.

Le format_resolve_report dans intelligence/learning.py envoie via Telegram
un summary correct/incorrect/neutral counts mais SANS le Brier moyen --
qui est la vraie metrique calibration. Ce script complete le report.

Usage (depuis le ROOT du projet pour que les imports `from shared` marchent) :
  python -m scripts.post_resolution_brier_report [YYYY-MM-DD]

  Sans argument : analyse toutes les predictions resolues aujourd'hui.
  Avec date : analyse celles resolues a cette date precise.

Exemple 10/06 a 9h05 (apres le cron daily_resolve_job 9h) :
  python -m scripts.post_resolution_brier_report 2026-06-10
"""

import sys
from datetime import date


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
        avg_brier = sum(briers) / len(briers)
        print("\n=== Brier (raw, sans dedup) ===")
        print(f"  n scored : {len(briers)}")
        print(f"  avg      : {avg_brier:.3f}")
        print("  baseline trivial (prior 0.5 constant) : 0.250")
        verdict = "BEATS" if avg_brier < 0.25 else "WORSE THAN"
        print(f"  -> {verdict} baseline 0.5 prior")

    if clusters:
        cluster_briers = [sum(v) / len(v) for v in clusters.values()]
        avg_dedup = sum(cluster_briers) / len(cluster_briers)
        print("\n=== Brier dedup par cluster (signal_id x ticker x direction) ===")
        print(f"  n clusters uniques : {len(clusters)} (vs {len(briers)} predictions brier-scored)")
        print(f"  dedup ratio        : {len(briers) / len(clusters):.2f}")
        print(f"  avg brier (dedup)  : {avg_dedup:.3f}")
        print(f"  range cluster_briers : [{min(cluster_briers):.3f}, {max(cluster_briers):.3f}]")

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
