'''Shadow decisions: parallel variants for empirical optimization.

For each decision (/exit verdict, signal scoring), compute parallel
variants (main/aggressive/conservative). Outcome resolution (Chunk 5)
measures which performs best.

Asymmetric behavioral correction:
- aggressive: fights premature exits (PLTR/NVDA-style)
- conservative: fights late exits (BTC/ETH-style)
'''
import json as _json
from shared import storage


def compute_exit_variants(thesis, current_price):
    entry = thesis.get("entry_price") or 0
    target_partial = thesis.get("target_partial") or float("inf")
    target_full = thesis.get("target_full") or float("inf")
    gain_pct = (current_price - entry) / entry if entry > 0 else 0

    if current_price >= target_partial:
        main = {"decision": "allow", "rationale": f"target_partial atteint ({current_price} >= {target_partial})"}
    elif gain_pct < 0.10:
        main = {"decision": "reject", "rationale": f"gain {gain_pct:.0%} < 10% min"}
    else:
        main = {"decision": "reject", "rationale": "pas de trigger valide"}

    if current_price >= target_full:
        aggressive = {"decision": "allow", "rationale": "target_full atteint"}
    else:
        aggressive = {"decision": "reject", "rationale": f"tient jusqu a target_full ({target_full})"}

    if gain_pct >= 0.15:
        conservative = {"decision": "allow", "rationale": f"gain {gain_pct:.0%} >= 15%"}
    else:
        conservative = {"decision": "reject", "rationale": f"gain {gain_pct:.0%} < 15%"}

    return {"main": main, "aggressive": aggressive, "conservative": conservative}


def compute_score_variants(signal_score, source_credibility):
    main_amp = signal_score
    aggressive_amp = min(10, int(signal_score * 1.3)) if source_credibility > 0.6 else signal_score
    conservative_amp = signal_score if source_credibility > 0.5 else max(0, signal_score - 2)
    return {
        "main": {"amplified_score": main_amp, "rationale": "as-is"},
        "aggressive": {"amplified_score": aggressive_amp, "rationale": f"cred {source_credibility:.2f} +30% if >0.6"},
        "conservative": {"amplified_score": conservative_amp, "rationale": f"cred {source_credibility:.2f} -2 if <0.5"},
    }


def log_shadow_decision(decision_type, decision_id, input_data, variants):
    return storage.insert_shadow_decision(
        decision_type=decision_type,
        decision_id=str(decision_id),
        input_data=_json.dumps(input_data),
        variants=_json.dumps(variants),
    )


if __name__ == "__main__":
    print("Test exit variants (entry $130):")
    thesis = {"entry_price": 130, "target_partial": 250, "target_full": 400}
    for price in [150, 180, 250, 300, 400]:
        variants = compute_exit_variants(thesis, price)
        print(f"  Price ${price}:")
        for name, v in variants.items():
            d = v["decision"]
            r = v["rationale"]
            print(f"    {name:13} -> {d:6} | {r}")

    print("Test score variants:")
    for score, cred in [(7, 0.8), (5, 0.4), (3, 0.7)]:
        variants = compute_score_variants(score, cred)
        print(f"  Score {score}, cred {cred}:")
        for name, v in variants.items():
            amp = v["amplified_score"]
            print(f"    {name:13} -> amplified {amp}")

    print("Test log:")
    sid = log_shadow_decision("exit_test", "NVDA", thesis, compute_exit_variants(thesis, 200))
    print(f"  logged shadow_decision id={sid}")
