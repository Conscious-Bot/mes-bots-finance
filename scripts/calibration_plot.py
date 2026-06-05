"""Reliability diagram (calibration plot) sur le ledger Brier.

C'est LA visualisation centrale du projet PRESAGE. Le Brier mean rep1ond a
"as-tu de la skill globalement ?". Le reliability diagram repond a "quand
tu dis 70%, est-ce que le monde te repond 70% ?".

Si bot dit 70% et hit rate = 0% -> antiskill grave (over-confidence sur fortes
convictions). Si bot dit 60% et hit rate = 60% -> calibre.

Pipeline :
  1. Pull resolved+scored predictions (proba_at_creation + outcome + signal_id)
  2. Bucket probas (par tranche de 10pt : [0.5, 0.6), [0.6, 0.7), ...)
  3. Pour chaque bucket : raw stats + dedup-by-signal stats
  4. ASCII reliability diagram cote-a-cote (predicted vs actual)
  5. ECE (Expected Calibration Error) = moyenne ponderee des |pred - actual|
  6. Verdict honnete -- pas de claim de calibration tant que N_sig faible

Cohort actuelle V1 (cf donnees 05/06) : bucket 0.70 hit 0%, bucket 0.60 hit 60%.
V1 est anti-skille sur les fortes convictions. C'est exactement ce que ce
plot rend visible d'un coup d'oeil.

Usage :
  python -m scripts.calibration_plot
  python -m scripts.calibration_plot --bins 5    # plus fin
  python -m scripts.calibration_plot --methodology v2  # restrict
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
log = logging.getLogger("calibration_plot")

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


def fetch_predictions(conn: sqlite3.Connection, methodology: str | None) -> list[dict]:
    """Resolved+scored predictions avec proba + outcome + signal_id."""
    extra = ""
    params: tuple = ()
    if methodology:
        extra = " AND methodology_version = ?"
        params = (methodology,)
    rows = conn.execute(
        f"""
        SELECT id, signal_id, ticker, direction, probability_at_creation,
               outcome, brier_score, methodology_version
        FROM predictions
        WHERE outcome IN ('correct', 'incorrect')
          AND probability_at_creation IS NOT NULL
          {extra}
        """,
        params,
    ).fetchall()
    return [{
        "id": r[0], "signal_id": r[1], "ticker": r[2], "direction": r[3],
        "prob": float(r[4]), "outcome": r[5], "brier": float(r[6]) if r[6] is not None else None,
        "methodology": r[7],
    } for r in rows]


def bucket_predictions(preds: list[dict], n_bins: int) -> list[dict]:
    """Bucket par proba. Returns liste de buckets [{lo, hi, center, preds: [...]}, ...]."""
    # Probas sont en [0.5, 1.0] pour le bot (jamais < 0.5 par construction
    # signal_scorer_v2 : on prend toujours la direction majoritaire).
    # Buckets : [0.50, 0.60), [0.60, 0.70), ..., [0.90, 1.00]
    bins = []
    if n_bins <= 0:
        n_bins = 5
    bin_width = 0.5 / n_bins
    for i in range(n_bins):
        lo = 0.5 + i * bin_width
        hi = lo + bin_width
        if i == n_bins - 1:
            hi = 1.0001  # inclusive de 1.0
        bins.append({"lo": lo, "hi": hi, "center": (lo + hi) / 2, "preds": []})
    for p in preds:
        for b in bins:
            if b["lo"] <= p["prob"] < b["hi"]:
                b["preds"].append(p)
                break
    return bins


def stats_for_bucket(bucket: dict) -> dict:
    """Raw + dedup stats pour un bucket."""
    preds = bucket["preds"]
    n_raw = len(preds)
    if n_raw == 0:
        return {**bucket, "n_raw": 0, "n_sig": 0,
                "hit_rate_raw": float("nan"), "hit_rate_sig": float("nan"),
                "predicted_avg": float("nan"),
                "brier_raw": float("nan"), "brier_sig": float("nan")}
    n_correct = sum(1 for p in preds if p["outcome"] == "correct")
    hit_raw = n_correct / n_raw

    # Dedup par signal_id : majority vote des outcomes par signal
    by_signal: dict = {}
    for p in preds:
        by_signal.setdefault(p["signal_id"], []).append(p)
    n_sig = len(by_signal)
    n_correct_sig = 0
    sig_briers = []
    for sid_preds in by_signal.values():
        n_c = sum(1 for x in sid_preds if x["outcome"] == "correct")
        if n_c * 2 > len(sid_preds):
            n_correct_sig += 1
        # Mediane des briers du signal
        briers = sorted([x["brier"] for x in sid_preds if x["brier"] is not None])
        if briers:
            mid = len(briers) // 2
            sig_briers.append(briers[mid] if len(briers) % 2 else (briers[mid - 1] + briers[mid]) / 2)
    hit_sig = n_correct_sig / n_sig

    pred_avg = sum(p["prob"] for p in preds) / n_raw
    brier_raw = sum(p["brier"] for p in preds if p["brier"] is not None) / n_raw
    brier_sig = sum(sig_briers) / len(sig_briers) if sig_briers else float("nan")

    return {**bucket, "n_raw": n_raw, "n_sig": n_sig,
            "hit_rate_raw": hit_raw, "hit_rate_sig": hit_sig,
            "predicted_avg": pred_avg,
            "brier_raw": brier_raw, "brier_sig": brier_sig}


def _bar(value: float, scale: int = 20) -> str:
    """ASCII bar 0-100% sur `scale` chars."""
    n = round(value * scale)
    n = max(0, min(scale, n))
    return "█" * n + "░" * (scale - n)


def _delta_marker(predicted: float, actual: float) -> str:
    """Indicateur visuel de la deviation predicted vs actual."""
    delta = predicted - actual
    if abs(delta) < 0.05:
        return "● calibre"
    if delta > 0.20:
        return "▲▲▲ over-confident grave"
    if delta > 0.10:
        return "▲▲ over-confident"
    if delta > 0.05:
        return "▲ leger over"
    if delta < -0.20:
        return "▼▼▼ under-confident grave"
    if delta < -0.10:
        return "▼▼ under-confident"
    return "▼ leger under"


def expected_calibration_error(buckets: list[dict], use_dedup: bool = False) -> tuple[float, int]:
    """ECE = sum_bucket( N_bucket/N_total * |predicted_avg - actual_hit_rate| ).
    Returns (ECE, total N used).
    """
    weighter = "n_sig" if use_dedup else "n_raw"
    hit_key = "hit_rate_sig" if use_dedup else "hit_rate_raw"
    total = sum(b[weighter] for b in buckets if b[weighter] > 0)
    if total == 0:
        return (float("nan"), 0)
    ece = sum(
        (b[weighter] / total) * abs(b["predicted_avg"] - b[hit_key])
        for b in buckets if b[weighter] > 0
    )
    return (ece, total)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--bins", type=int, default=5, help="N buckets sur [0.5, 1.0] (default 5).")
    parser.add_argument("--methodology", type=str, default=None,
                        help="Restrict to methodology_version (v0/v1/v2/rule_v1_*).")
    args = parser.parse_args()

    conn = sqlite3.connect(storage.DB_PATH)
    try:
        preds = fetch_predictions(conn, args.methodology)
    finally:
        conn.close()

    if not preds:
        log.error("Aucune prediction resolved+scored. Rien a plotter.")
        return

    log.info(f"Loaded {len(preds)} predictions resolved+scored "
             f"(methodology={args.methodology or 'all'})")

    # Detection mono-bucket : si toutes les probas tombent dans <= 2 buckets
    # = V1 mono-bucket par construction, calibration plot ne peut pas montrer
    # spread (cf doctrine [[scorer_v2_canonical]]). Surface comme finding.
    unique_probs = sorted({round(p["prob"], 3) for p in preds})
    prob_min = min(p["prob"] for p in preds)
    prob_max = max(p["prob"] for p in preds)
    prob_spread = prob_max - prob_min

    buckets = bucket_predictions(preds, args.bins)
    stats = [stats_for_bucket(b) for b in buckets]
    n_buckets_nonempty = sum(1 for s in stats if s["n_raw"] > 0)

    n_total_raw = sum(s["n_raw"] for s in stats)
    n_total_sig = sum(s["n_sig"] for s in stats)

    print("\n" + "=" * 84)
    print("CALIBRATION PLOT — RELIABILITY DIAGRAM")
    print("=" * 84)
    print(f"Predictions resolved+scored : {n_total_raw} (raw) / {n_total_sig} signaux uniques")
    methodologies = sorted({p["methodology"] for p in preds})
    print(f"Methodology(ies) : {', '.join(methodologies)}")
    print(f"Bins : {args.bins} sur [0.5, 1.0]")
    print()
    print(f"Probability spread : [{prob_min:.3f}, {prob_max:.3f}] = {prob_spread*100:.1f}pt")
    print(f"Unique probability values : {len(unique_probs)} -> {unique_probs[:8]}"
          + (" ..." if len(unique_probs) > 8 else ""))
    print(f"Buckets non-vides : {n_buckets_nonempty} / {args.bins}")
    if n_buckets_nonempty <= 1:
        print()
        print("/!\\ MONO-BUCKET DETECTE : toutes les probas tombent dans 1 seul bucket.")
        print("    Calibration plot ne peut pas montrer spread (cf doctrine V1 mono-bucket).")
        print("    Le reliability diagram montrera un seul point -- a interpreter comme")
        print("    'mean predicted prob = X' vs 'mean realized hit rate = Y', pas comme")
        print("    une vraie courbe de calibration. Le vrai test cal arrive avec V2.")
    print()
    print("Bucket          N_raw  N_sig  Predicted  Actual(raw)  Actual(sig)  Diagnostic")
    print("-" * 84)

    for s in stats:
        if s["n_raw"] == 0:
            continue
        bucket_label = f"[{s['lo']:.2f}, {s['hi']:.2f})"
        pred = s["predicted_avg"]
        hit_raw = s["hit_rate_raw"]
        hit_sig = s["hit_rate_sig"]
        diag_raw = _delta_marker(pred, hit_raw)
        print(f"{bucket_label:<15} {s['n_raw']:>5} {s['n_sig']:>5}    "
              f"{pred:>5.2f}      {hit_raw:>5.0%}        {hit_sig:>5.0%}    {diag_raw}")

    print()
    print("Reliability diagram (predicted = ▲ position, actual = ▼ position) :")
    print("           0%  10  20  30  40  50  60  70  80  90  100%")
    print("           ─" + "─" * 50)
    for s in stats:
        if s["n_raw"] == 0:
            continue
        scale = 50
        pred_pos = round(s["predicted_avg"] * scale)
        actual_pos = round(s["hit_rate_raw"] * scale)
        line_chars = [" "] * (scale + 2)
        # Mark predicted at ▲ position, actual at ▼ position
        if 0 <= pred_pos < scale + 1:
            line_chars[pred_pos] = "▲"
        if 0 <= actual_pos < scale + 1:
            # If overlapping, use ◆ to mark calibrated
            line_chars[actual_pos] = "◆" if pred_pos == actual_pos else "▼"
        bucket_label = f"[{s['lo']:.2f},{s['hi']:.2f})"
        print(f"  {bucket_label:<11}  {''.join(line_chars)}  N_raw={s['n_raw']}")

    # ECE
    print()
    ece_raw, n_raw = expected_calibration_error(stats, use_dedup=False)
    ece_sig, n_sig = expected_calibration_error(stats, use_dedup=True)
    print("Expected Calibration Error (ECE) :")
    print(f"  RAW   (N={n_raw}) : {ece_raw:.3f} ({ece_raw * 100:.1f}pt)")
    print(f"  DEDUP (N={n_sig}) : {ece_sig:.3f} ({ece_sig * 100:.1f}pt)")
    print()
    print("Lecture ECE :")
    print("  < 0.05 (5pt) : calibre")
    print("  0.05-0.15    : leger miscalibration")
    print("  0.15-0.30    : miscalibration substantielle")
    print("  > 0.30       : antiskill grave -- le bot reverse pred vs realite")

    # Verdict global
    print()
    print("=" * 84)
    if n_sig < 5:
        print("VERDICT : N_sig < 5 -> point estimates indicatifs uniquement. NULL.")
    elif n_sig < 15:
        print(f"VERDICT : N_sig={n_sig} -> read transparency snapshot, pas conclusion ferme.")
    else:
        if ece_sig < 0.05:
            print(f"VERDICT : ECE_dedup={ece_sig:.3f} -> calibration acceptable.")
        elif ece_sig < 0.15:
            print(f"VERDICT : ECE_dedup={ece_sig:.3f} -> miscalibration legere.")
        elif ece_sig < 0.30:
            print(f"VERDICT : ECE_dedup={ece_sig:.3f} -> miscalibration substantielle.")
        else:
            print(f"VERDICT : ECE_dedup={ece_sig:.3f} -> ANTISKILL grave.")
    print()
    print("Note : dedup ECE = pondere par signaux uniques (5-10 signaux >> 25 predictions")
    print("       correlees). Le raw ECE surestime l'info reelle par theme correlation.")
    print("=" * 84)


if __name__ == "__main__":
    main()
