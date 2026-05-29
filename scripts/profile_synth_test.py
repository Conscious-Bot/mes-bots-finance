"""Sprint 2 quality test — dry-run user_profile synthesis prompt.

Reads all historical data (decisions, theses, predictions resolved, bias_tags,
copilot interventions, portfolio snapshot, signals window count), formats the
prompt that would be sent to Opus, prints it for inspection.

If --live is passed AND ANTHROPIC_API_KEY is set, actually runs the LLM call
and inserts into user_profile table.

Usage :
  python3 scripts/profile_synth_test.py             # dry-run (no LLM)
  python3 scripts/profile_synth_test.py --live      # actual synthesis + insert
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> int:
    from intelligence import user_profile as up

    ctx, counts = up.assemble_synthesis_context(months_window=6)

    print("\n========== CONTEXT COUNTS ==========")
    for k, v in counts.items():
        print(f"  {k}: {v}")

    if "--live" in sys.argv:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("\nERROR : --live requires ANTHROPIC_API_KEY env var")
            return 2
        print("\n========== INVOKING OPUS ==========\n")
        result, profile_id = up.run_synthesis(months_window=6)
        if result is None:
            print("Synthesis failed (see logs)")
            return 3
        print(f"Inserted into user_profile, id={profile_id}")
        print(f"\nConfidence : {result.get('confidence_score')}/100")
        print(f"\nSummary : {result.get('summary_oneliner')}\n")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        # Quality checks
        print("\n========== QUALITY EVAL ==========")
        traits_with_evidence = 0
        traits_without = 0
        for section_name in ["style", "sizing_patterns"]:
            section = result.get(section_name, {})
            if section.get("evidence_ids"):
                traits_with_evidence += 1
            else:
                traits_without += 1
        # Biases must cite n_occurrences
        biases = result.get("bias_signature", {}).get("recurring_biases") or []
        biases_cited = sum(1 for b in biases if b.get("n_occurrences"))
        print(f"  Top-level traits with evidence_ids : {traits_with_evidence}")
        print(f"  Top-level traits WITHOUT evidence_ids : {traits_without}  (should be 0)")
        print(f"  Recurring biases with n_occurrences cited : {biases_cited}/{len(biases)}")
        if traits_without > 0:
            print("  ⚠ Some top-level traits lack evidence_ids")
        return 0

    # Dry-run : show the prompt
    print("\n========== DRY-RUN : assembled prompt (no LLM) ==========\n")
    prompt = up.PROMPT.format(**ctx)
    print(prompt)
    print("\n========== END PROMPT ==========")
    print("To run live : export ANTHROPIC_API_KEY=... then re-run with --live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
