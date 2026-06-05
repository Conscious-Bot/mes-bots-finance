"""Validation du scorer materiality_v2 : son output predict-il vraiment Brier ?

Question repondue : quand materiality_v2 dit "impact_magnitude=4" (haute), est-ce
que ces predictions sortent un Brier MEILLEUR que les "impact_magnitude=2" (basse) ?

Si OUI : le scorer fait son job, on garde + on push V2 forward.
Si NON : le scorer pose une etiquette qui ne discrimine pas -> overhead Sonnet
  call sans valeur -> meta-bug, le pipeline scorer-prediction est miscalibré.

Pipeline :
  1. JOIN signals.impact_magnitude -> predictions.brier_score (resolved)
  2. Bucket par impact (1-2-3-4-5)
  3. Pour chaque bucket : N_sig dedup, Brier mean + bootstrap CI
  4. Spearman rank correlation entre impact_magnitude et 1/brier (proxy quality)
  5. Verdict honnete sur la calibration du scorer lui-meme

Observations cohort actuelle (05/06) :
- impact=4 (high) : Brier 0.416 (pire que baseline 0.250)
- impact=3 (medium) : Brier 0.192 (meilleur)
- impact=2 (low) : Brier 0.335
-> Directionnel : scorer ANTI-correle avec qualite predictive.
   Possible explication : high impact = catalyseurs deja prices, low subtle
   medium = sweet spot non price. OU scorer biaise vers over-confidence sur
   les "gros" signaux. A confirmer avec plus de N.

Cf [[scorer_v2_canonical]] : V2 est canonical mais aucune V2 resolved encore
sur ce ledger. Donc ce script audit V1 essentiellement pour le moment.

Usage :
  python -m scripts.materiality_validation
  python -m scripts.materiality_validation --methodology v2
"""

from __future__ import annotations

import argparse
import logging
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("materiality_validation")

BOOTSTRAP_N = 1000
BOOTSTRAP_SEED = 42


def bootstrap_ci(values: list[float], n_iter: int = BOOTSTRAP_N, ci: float = 0.95) -> tuple[float, float]:
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(BOOTSTRAP_SEED)
    means = []
    for _ in range(n_iter):
        sample = [values[rng.randint(0, len(values) - 1)] for _ in range(len(values))]
        means.append(sum(sample) / len(sample))
    means.sort()
    lo_idx = int((1 - ci) / 2 * n_iter)
    hi_idx = int((1 + ci) / 2 * n_iter) - 1
    return (means[lo_idx], means[hi_idx])


def spearman_rank_correlation(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation. Pas de scipy import requis, calcul direct."""
    if len(xs) < 3 or len(xs) != len(ys):
        return float("nan")
    n = len(xs)
    rank_x = _rank(xs)
    rank_y = _rank(ys)
    d_sq = sum((rank_x[i] - rank_y[i]) ** 2 for i in range(n))
    return 1 - (6 * d_sq) / (n * (n ** 2 - 1))


def _rank(values: list[float]) -> list[float]:
    """Average rank (handle ties)."""
    indexed = sorted(enumerate(values), key=lambda kv: kv[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) - 1 and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        # Same-value indices i..j get average rank
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg
        i = j + 1
    return ranks


def fetch_signals_with_brier(conn: sqlite3.Connection, methodology: str | None) -> list[dict]:
    """JOIN signals -> predictions resolved + scored. Filter NULL impact_magnitude."""
    extra = ""
    params: tuple = ()
    if methodology:
        extra = " AND p.methodology_version = ?"
        params = (methodology,)
    rows = conn.execute(
        f"""
        SELECT s.id AS signal_id,
               s.impact_magnitude,
               s.reversibility,
               p.id AS prediction_id,
               p.brier_score,
               p.ticker
        FROM signals s
        JOIN predictions p ON p.signal_id = s.id
        WHERE p.outcome IN ('correct', 'incorrect')
          AND p.brier_score IS NOT NULL
          AND s.impact_magnitude IS NOT NULL
          {extra}
        """,
        params,
    ).fetchall()
    return [{
        "signal_id": r[0], "impact": float(r[1]),
        "reversibility": float(r[2]) if r[2] is not None else None,
        "prediction_id": r[3], "brier": float(r[4]), "ticker": r[5],
    } for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--methodology", type=str, default=None,
                        help="Restrict to one methodology_version (v0/v1/v2).")
    args = parser.parse_args()

    conn = sqlite3.connect(storage.DB_PATH)
    try:
        rows = fetch_signals_with_brier(conn, args.methodology)
    finally:
        conn.close()

    if not rows:
        log.error("Aucune prediction resolved liee a un signal scored impact_magnitude.")
        return

    n_raw = len(rows)
    distinct_signals = {r["signal_id"] for r in rows}
    n_sig = len(distinct_signals)
    methodologies = sorted({args.methodology or "all"})

    print("\n" + "=" * 80)
    print("MATERIALITY_V2 SCORER VALIDATION")
    print("=" * 80)
    print(f"Predictions resolved+scored avec impact_magnitude : {n_raw} raw / "
          f"{n_sig} signaux uniques")
    print(f"Methodology : {methodologies}")
    print("Baseline no-skill Brier : 0.250")
    print()

    # Bucket par impact_magnitude
    buckets: dict[float, dict] = {}
    for r in rows:
        b = r["impact"]
        if b not in buckets:
            buckets[b] = {"signals": {}, "all_briers": []}
        buckets[b]["signals"].setdefault(r["signal_id"], []).append(r["brier"])
        buckets[b]["all_briers"].append(r["brier"])

    # Per-bucket stats with dedup median per signal
    print(f"{'Impact':<8} {'N_sig':>5} {'N_raw':>5} {'Brier_dedup':>12} "
          f"{'CI95_dedup':>20} {'Brier_raw':>10}")
    print("-" * 80)

    sorted_buckets = sorted(buckets.items(), reverse=True)  # high to low
    for impact, data in sorted_buckets:
        n_sig_b = len(data["signals"])
        n_raw_b = len(data["all_briers"])
        # Dedup : median brier par signal
        dedup_briers = []
        for sig_briers in data["signals"].values():
            sorted_b = sorted(sig_briers)
            mid = len(sorted_b) // 2
            dedup_briers.append(
                sorted_b[mid] if len(sorted_b) % 2 else (sorted_b[mid - 1] + sorted_b[mid]) / 2
            )
        mean_dd = sum(dedup_briers) / len(dedup_briers) if dedup_briers else float("nan")
        mean_raw = sum(data["all_briers"]) / len(data["all_briers"])
        if len(dedup_briers) >= 5:
            lo, hi = bootstrap_ci(dedup_briers)
            ci_s = f"[{lo:.3f}, {hi:.3f}]"
        else:
            ci_s = "(N<5 NULL)"
        print(f"{impact:>4.1f}    {n_sig_b:>5} {n_raw_b:>5} "
              f"{mean_dd:>12.3f} {ci_s:>20} {mean_raw:>10.3f}")

    print()

    # Spearman rank correlation : impact vs (1 - brier) [quality proxy]
    # Per signal (dedup) pour eviter inflation par theme correlation
    sig_impact_brier: dict[int, tuple[float, float]] = {}
    for r in rows:
        sid = r["signal_id"]
        if sid not in sig_impact_brier:
            sig_impact_brier[sid] = (r["impact"], r["brier"])
        else:
            # Median brier across the signal's predictions
            prev = sig_impact_brier[sid]
            sig_impact_brier[sid] = (prev[0], (prev[1] + r["brier"]) / 2)

    impacts_per_sig = [v[0] for v in sig_impact_brier.values()]
    briers_per_sig = [v[1] for v in sig_impact_brier.values()]
    # Quality = 1 - brier (higher = better prediction)
    quality_per_sig = [1 - b for b in briers_per_sig]

    rho = spearman_rank_correlation(impacts_per_sig, quality_per_sig)
    print("Spearman rank correlation (impact_magnitude, quality=1-brier) :")
    print(f"  rho = {rho:+.3f}  (N_sig={len(impacts_per_sig)})")
    print()

    # Verdict
    if len(impacts_per_sig) < 5:
        verdict = "NULL (N<5 dedup, pas de conclusion possible)"
    elif rho > 0.3:
        verdict = "POSITIF : scorer materiality_v2 discrimine -- haute impact -> meilleur Brier"
    elif rho < -0.3:
        verdict = ("NEGATIF : scorer ANTI-correle -- haute impact -> PIRE Brier. "
                   "Le scorer pose une etiquette inverse a la realite. Bug ou pattern caché.")
    else:
        verdict = "FLAT : scorer ne discrimine pas significativement (rho dans [-0.3, +0.3])"

    print("=" * 80)
    print(f"VERDICT : {verdict}")
    print()
    print("Lecture :")
    print("- rho > +0.3 : scorer fait son job (haute impact = meilleur Brier)")
    print("- rho in [-0.3, +0.3] : scorer NEUTRAL (etiquette sans info predictive)")
    print("- rho < -0.3 : scorer ANTI-correle (etiquette inverse la realite)")
    print("- N_sig < 5 : aucun verdict possible (cohort actuelle = exploration)")
    print("=" * 80)


if __name__ == "__main__":
    main()
