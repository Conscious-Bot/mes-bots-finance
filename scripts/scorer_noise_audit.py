#!/usr/bin/env python3
"""scorer_noise_audit.py — Mesurer la NOISE du scorer V2.

Origine : Kahneman/Sibony/Sunstein "Noise" (2021) + audit harvest tennis-bot 31/05.

3 types de noise (Noise book) :
- level noise   : juges différents → résultats différents (= comparer Haiku vs Sonnet)
- pattern noise : un juge → résultats différents pour cas similaires (= variance inter-cas)
- occasion noise: même juge → résultats différents selon moment (= variance intra-cas, re-runs)

Ce script mesure SURTOUT l'occasion noise du scorer V2 single-Haiku :
re-run scorer V2 sur N signaux historiques × M fois, mesurer std deviation des probas.

Verdict :
- std_per_signal < 0.02 → noise faible, single-run OK
- std_per_signal 0.02-0.05 → noise modéré, multi-run (median de 3) recommandé
- std_per_signal > 0.05 → noise élevé, multi-run obligatoire OU revoir prompt

⚠️ COÛT LLM : chaque run = 1 appel Haiku. N=10 signaux × M=5 re-runs = 50 appels.
À tarif Haiku ~$0.001/call = ~$0.05 total. Pas critique mais à acter.

USAGE :
    python3 scripts/scorer_noise_audit.py --n-signals 10 --n-runs 5 --dry-run
    python3 scripts/scorer_noise_audit.py --n-signals 10 --n-runs 5  # vrai run

DRY-RUN par défaut : montre quels signaux seraient testés, n'appelle PAS le LLM.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from pathlib import Path

# Ensure parent dir in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.storage import DB_PATH


def sample_signals(cx, n: int) -> list[dict]:
    """Échantillonne N signaux historiques avec predictions résolues (= cas connus).

    Préférer signaux RÉSOLUS pour pouvoir comparer noise vs accuracy aussi.
    """
    rows = cx.execute(
        """SELECT sig.id, sig.title, sig.summary, sig.timestamp,
                  p.ticker, p.direction, p.horizon_days, p.probability_at_creation,
                  p.outcome, p.brier_score
           FROM signals sig
           JOIN predictions p ON p.signal_id = sig.id
           WHERE p.resolved_at IS NOT NULL
             AND p.brier_score IS NOT NULL
           ORDER BY RANDOM()
           LIMIT ?""",
        (n,),
    ).fetchall()
    return [dict(r) for r in rows]


def rerun_scorer_v2(signal: dict) -> float | None:
    """Re-run le scorer V2 sur un signal et retourne la probability calculée."""
    from intelligence import signal_scorer_v2
    try:
        result = signal_scorer_v2.score_directional_probability(
            title=signal.get("title") or "",
            summary=signal.get("summary"),
            ticker=signal["ticker"],
            horizon_days=signal["horizon_days"],
        )
        return result.get("probability") if isinstance(result, dict) else None
    except Exception as e:
        print(f"  [ERR] re-run failed for signal {signal['id']}: {e}")
        return None


def analyze(probas_per_signal: dict[int, list[float]]) -> dict:
    """Analyse la noise par signal."""
    per_signal_stats = []
    all_stds = []
    for sig_id, probas in probas_per_signal.items():
        valid = [p for p in probas if p is not None]
        if len(valid) < 2:
            continue
        std = statistics.stdev(valid)
        mean = statistics.mean(valid)
        range_obs = max(valid) - min(valid)
        per_signal_stats.append({
            "signal_id": sig_id,
            "n_runs": len(valid),
            "mean": round(mean, 4),
            "std": round(std, 4),
            "range": round(range_obs, 4),
            "all_probas": [round(p, 4) for p in valid],
        })
        all_stds.append(std)
    if not all_stds:
        return {"verdict": "NO_DATA", "per_signal": [], "global_mean_std": None}
    global_mean_std = statistics.mean(all_stds)
    if global_mean_std < 0.02:
        verdict = "LOW_NOISE_single_run_OK"
    elif global_mean_std < 0.05:
        verdict = "MODERATE_NOISE_recommend_3run_median"
    else:
        verdict = "HIGH_NOISE_multi_run_obligatoire_OR_revoir_prompt"
    return {
        "verdict": verdict, "global_mean_std": round(global_mean_std, 4),
        "n_signals_tested": len(per_signal_stats),
        "per_signal": per_signal_stats,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-signals", type=int, default=10)
    parser.add_argument("--n-runs", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Montre quels signaux seraient testés, n'appelle PAS le LLM.")
    parser.add_argument("--output", default="scorer_noise_audit_results.json")
    args = parser.parse_args()

    cx = sqlite3.connect(DB_PATH)
    cx.row_factory = sqlite3.Row

    print(f"=== scorer_noise_audit ===")
    print(f"  N signaux : {args.n_signals}")
    print(f"  N re-runs : {args.n_runs}")
    print(f"  Mode : {'DRY-RUN (pas d\\'appel LLM)' if args.dry_run else 'VRAI RUN'}")
    print()

    signals = sample_signals(cx, args.n_signals)
    if not signals:
        print(f"[ERR] aucun signal résolu non-neutral disponible (table predictions vide ou tous neutrals).")
        print(f"      Cibler 10/06/2026 (batch KPI #2) puis re-lancer.")
        sys.exit(0)

    print(f"Signaux échantillonnés ({len(signals)}) :")
    for s in signals:
        print(f"  - sig#{s['id']} {s['ticker']} {s['direction']} {s['horizon_days']}d "
              f"prob_orig={s['probability_at_creation']:.3f} outcome={s['outcome']}")
    print()

    if args.dry_run:
        print(f"[DRY-RUN] script terminé sans appel LLM.")
        print(f"          Coût estimé vrai run : ~${args.n_signals * args.n_runs * 0.001:.3f}")
        print(f"          Lancer sans --dry-run pour exécuter.")
        return

    probas_per_signal: dict[int, list[float]] = {s["id"]: [] for s in signals}
    total_calls = args.n_signals * args.n_runs
    call_num = 0
    for run in range(args.n_runs):
        print(f"--- Run {run+1}/{args.n_runs} ---")
        for s in signals:
            call_num += 1
            print(f"  [{call_num}/{total_calls}] re-scoring sig#{s['id']} {s['ticker']}...", end=" ")
            prob = rerun_scorer_v2(s)
            if prob is not None:
                print(f"prob={prob:.4f}")
            else:
                print(f"FAILED")
            probas_per_signal[s["id"]].append(prob)
        print()

    result = analyze(probas_per_signal)
    print(f"=== VERDICT : {result['verdict']} ===")
    print(f"  global mean std = {result['global_mean_std']}")
    print(f"  n signaux exploités : {result['n_signals_tested']}")
    print()
    print(f"{'sig_id':<8}{'n_runs':>7}{'mean':>8}{'std':>8}{'range':>8}")
    print("-" * 50)
    for s in result["per_signal"]:
        print(f"{s['signal_id']:<8}{s['n_runs']:>7}{s['mean']:>8.4f}{s['std']:>8.4f}{s['range']:>8.4f}")

    Path(args.output).write_text(json.dumps(result, indent=2))
    print(f"\n[OK] résultats sauvés -> {args.output}")
    cx.close()


if __name__ == "__main__":
    main()
