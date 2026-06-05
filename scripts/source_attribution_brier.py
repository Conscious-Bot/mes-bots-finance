"""Decompose Brier par SOURCE qui a genere le signal -> ou est ton edge ?

Question repondue : parmi tes newsletters / 8-K / insider clusters / chat,
laquelle a un Brier sous baseline (= edge predictif) ?

Pipeline :
  1. JOIN predictions -> signals -> sources
  2. Pour chaque source : agrege predictions resolves
  3. Reporting DUAL :
     - RAW : compte chaque prediction (gonfle N artificiellement quand un signal
       emet plusieurs tickers correles)
     - DEDUP : 1 prediction par signal_id (mediane des briers du cluster) -- la
       vraie N independante. C'est cette vue qui compte pour conclure.

Cf [[J-day reading contract]] section "Effective N caveat" : les predictions
sont theme-correlated, donc la N raw surestime l'info reelle. La dedup est
explicitement aligned sur la doctrine du contract.

Usage :
  python -m scripts.source_attribution_brier
  python -m scripts.source_attribution_brier --min-n 3   # filtre sources < N
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
log = logging.getLogger("source_attribution")

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


def _clean_source_name(name: str | None) -> str:
    """'Wall Street Rollup <foo@bar.com>' -> 'Wall Street Rollup'."""
    if not name:
        return "(no source)"
    i = name.find("<")
    return (name[:i] if i > 0 else name).strip().strip('"')


def _verdict(values: list[float]) -> str:
    """Bootstrap CI vs baseline 0.250. Pour N < 5 : NULL."""
    if len(values) < 5:
        return "NULL (N<5)"
    lo, hi = bootstrap_ci(values)
    if hi < 0.250:
        return f"EARNED (CI[{lo:.3f},{hi:.3f}] < 0.250)"
    if lo > 0.250:
        return f"DID NOT EARN (CI[{lo:.3f},{hi:.3f}] > 0.250)"
    return f"INCONCLUSIVE (CI[{lo:.3f},{hi:.3f}] englobe 0.250)"


def fetch_predictions_with_source(conn: sqlite3.Connection) -> list[dict]:
    """JOIN predictions -> signals -> sources. Retourne resolved+scored only."""
    rows = conn.execute("""
        SELECT
          p.id AS prediction_id,
          p.signal_id,
          p.ticker,
          p.brier_score,
          p.methodology_version,
          src.id AS source_id,
          src.name AS source_name,
          src.type AS source_type,
          src.credibility AS source_credibility
        FROM predictions p
        LEFT JOIN signals s ON s.id = p.signal_id
        LEFT JOIN sources src ON src.id = s.source_id
        WHERE p.outcome IN ('correct', 'incorrect')
          AND p.brier_score IS NOT NULL
    """).fetchall()
    return [{
        "prediction_id": r[0], "signal_id": r[1], "ticker": r[2], "brier": float(r[3]),
        "methodology": r[4], "source_id": r[5], "source_name": _clean_source_name(r[6]),
        "source_type": r[7] or "?", "source_credibility": r[8],
    } for r in rows]


def aggregate_by_source(predictions: list[dict]) -> dict[str, dict]:
    """Group par source_name. Compute RAW + DEDUP (par signal_id) Brier."""
    by_source: dict[str, dict] = {}
    for p in predictions:
        src = p["source_name"]
        if src not in by_source:
            by_source[src] = {
                "type": p["source_type"],
                "credibility": p["source_credibility"],
                "raw_briers": [],
                "by_signal": {},  # signal_id -> [briers]
                "signal_ids": set(),
            }
        by_source[src]["raw_briers"].append(p["brier"])
        sid = p["signal_id"]
        by_source[src]["signal_ids"].add(sid)
        by_source[src]["by_signal"].setdefault(sid, []).append(p["brier"])

    # Compute dedup briers : 1 valeur par signal_id (mediane des briers du cluster)
    for data in by_source.values():
        dedup = []
        for briers in data["by_signal"].values():
            # Mediane (plus robuste que mean pour cluster correle)
            sorted_b = sorted(briers)
            mid = len(sorted_b) // 2
            if len(sorted_b) % 2:
                dedup.append(sorted_b[mid])
            else:
                dedup.append((sorted_b[mid - 1] + sorted_b[mid]) / 2)
        data["dedup_briers"] = dedup
    return by_source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--min-n", type=int, default=1,
                        help="Filtre sources avec n_signals (dedup) < min-n (default 1).")
    args = parser.parse_args()

    conn = sqlite3.connect(storage.DB_PATH)
    try:
        predictions = fetch_predictions_with_source(conn)
    finally:
        conn.close()

    if not predictions:
        log.error("Aucune prediction resolved+scored avec brier_score. Rien a decomposer.")
        return

    by_source = aggregate_by_source(predictions)

    # Sort par N dedup descendant (sources les plus signal-riches d'abord)
    sorted_sources = sorted(
        by_source.items(),
        key=lambda kv: -len(kv[1]["dedup_briers"]),
    )

    total_raw = sum(len(d["raw_briers"]) for _, d in sorted_sources)
    total_dedup = sum(len(d["dedup_briers"]) for _, d in sorted_sources)

    print("\n" + "=" * 84)
    print("SOURCE ATTRIBUTION — BRIER DECOMPOSITION")
    print("=" * 84)
    print(f"Predictions resolved+scored : {total_raw} (raw) / {total_dedup} signaux uniques (dedup)")
    print(f"Sources distinctes : {len(by_source)}")
    print("Baseline no-skill Brier : 0.250")
    print("Methode dedup : mediane des briers par signal_id (1 valeur / signal independant)")
    print()

    # Header line
    print(f"{'Source':<32} {'Type':<11} {'Cred':>4} {'N_raw':>5} {'N_sig':>5} "
          f"{'Brier_raw':>9} {'Brier_dd':>9}  Verdict (dedup)")
    print("-" * 84)

    for src, data in sorted_sources:
        n_raw = len(data["raw_briers"])
        n_sig = len(data["dedup_briers"])
        if n_sig < args.min_n:
            continue
        mean_raw = sum(data["raw_briers"]) / n_raw if n_raw else float("nan")
        mean_dd = sum(data["dedup_briers"]) / n_sig if n_sig else float("nan")
        cred = data["credibility"]
        cred_s = f"{cred:.2f}" if cred is not None else " -- "
        verdict = _verdict(data["dedup_briers"])
        src_short = (src[:30] + "..") if len(src) > 32 else src
        print(f"{src_short:<32} {data['type']:<11} {cred_s:>4} {n_raw:>5} {n_sig:>5} "
              f"{mean_raw:>9.3f} {mean_dd:>9.3f}  {verdict}")

    print()
    print("=" * 84)
    print("Lecture honnete :")
    print("- N_sig est la VRAIE taille effective de l'echantillon (signaux independants).")
    print("- Quand N_sig << N_raw, les predictions du signal ont fortement co-bouge -> 1")
    print("  signal = 1 information, pas N_raw.")
    print("- Verdict CI-based (cf reading contract). EARNED/DID NOT requiert N_sig>=5.")
    print("- A faible N_sig la valeur point estimate est indicative, pas un verdict.")
    print("=" * 84)


if __name__ == "__main__":
    main()
