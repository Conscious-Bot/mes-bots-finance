# J-day v1 Brier Reading Contract

**Committed 2026-06-03, before resolution.** This document binds how the J-day v1 Brier number gets read on 2026-06-10. Pre-registration is the entire point: writing "did not earn its cost" *before* seeing the result is what prevents rationalization after.

## Scope

This contract covers ONE number: the Brier score on the V1 cohort resolved by `bot/jobs/j_day.py:j_day_batch_close_job` on 2026-06-10. That cohort is the 35-ish V1 predictions with `target_date ≤ 2026-06-10`, scored by `signal_scorer_v2` (LLM Sonnet, base-rate-first 3-step prompt) between mid-May and early June 2026.

It does NOT cover:
- v0 quarantine (excluded by methodology_version filter)
- v2 canonical (doesn't yet exist; opens after this batch closes)
- Forward predictions made after 2026-06-10

## Forced numbers (not a choice)

**No-skill baseline = b · (1 − b)** where `b` = realized hit rate (fraction of resolved predictions where direction was correct, neutral excluded).

At b ≈ 60%, baseline ≈ 0.24. That's the floor the LLM must beat to have added *anything* over a coin-weighted-by-base-rate. If b comes in at 50%, baseline = 0.25. If 70%, baseline = 0.21. The baseline is computed from the same batch the LLM is scored on — same distribution, same horizon.

This is forced because it's math, not preference.

## Sample floor — [YOUR CALL — proposed N=20]

**If `n_resolved < N`, the read is NULL.** No verdict. No priority change. No conclusion about LLM value. The number gets reported as a transparency snapshot ("here's what the small sample showed") but it does not bind future direction.

Proposed N = 20. Current state: 18 already resolved + ~17 expected in this batch ≈ 35. So if the batch resolves cleanly, the read will be live. If a chunk fails to resolve (data gaps, stuck predictions), this floor catches that.

**Revise N to the number you'll actually hold to.** Lower than 20 is louder but noisier; higher is quieter but might null out a real read.

## Verdict bands — [YOUR CALL — proposed M=0.02]

Three outcomes, no fourth:

- **Earned its cost** if `Brier ≤ baseline − M`
- **Did not earn its cost** if `Brier ≥ baseline`
- **Inconclusive** if `baseline − M < Brier < baseline`

Proposed M = 0.02. That's the gap the LLM must clear *below* the no-skill baseline to count as having added value beyond noise.

**Revise M to the gap you'll actually use as the line.** M too small = too easy to declare victory on noise. M too large = even a real edge gets called inconclusive. The honest number is the smallest gap you'd trust if it came in unfavorably.

## Pre-committed consequences (the anti-rationalization core)

The whole point of pre-registering is that the "did not earn" branch is the outcome you'll most want to explain away. So it's pinned hardest, and the action is written *before* the data.

### Earned → proceed

- v2 builds on the v1 methodology spine (LLM Sonnet, base-rate-first prompt structure preserved).
- Champion-challenger #96 ships post-flag-flip to validate forward (LLM vs rule_v1_shadow Brier delta on new resolutions).
- No methodology change in response to the favorable number — that's overfitting to one batch.

### Did not earn → reshape priorities

- **Default headline**: LLM scoring is not beating a base-rate heuristic on this distribution at this horizon. State it plainly. No softening, no "the sample was unusual," no "the prompt needs another iteration."
- **The work shifts**: from "build more on top of LLM scoring" to "establish whether any predictive edge exists at all, by any method." That likely means digging into the RuleScorer baseline (already shipped flag-off in #94) and the per-source Brier desegregation to see if specific sources have edge while others poison the average.
- **What is NOT allowed**: tweaking the prompt to make the number look better, narrowing the bucket/horizon definition retroactively, excluding predictions post-hoc as "atypical." The /asymmetry rule is in force.

### Inconclusive → report as-is, wait for N, change nothing

- Headline says inconclusive with N and the actual number.
- No priority shift in either direction until N is large enough for the band to break (either v2 cohort grows, or v1 resolutions backfill).
- Champion-challenger doesn't ship yet (would build on an unvalidated baseline).

## Binding rules

1. **Report v1 as-is**, labelled transitional (per ADR 014 archive-report rule, already wired in `bot/jobs/j_day.py`).
2. **Do NOT touch buckets/horizons/methodology in response to the value**. The /asymmetry rule — definitions are frozen at the moment the bet was made.
3. **v1 closes here; v2 opens clean**. No retroactive re-tagging, no re-scoring of v1 predictions through the v2 lens.
4. **The verdict is read once**, on or shortly after 2026-06-10, against the bands above. Not re-read at J+7, not re-read at J+30 with "more data now." (Those are separate reads on separate cohorts.)

## What gets published

The J-day Telegram report (already wired) sends:
- N resolved / correct / incorrect / neutral
- Brier raw average
- Brier dedup average (cluster-level)
- Mono-bucket warning if applicable

The verdict (earned / did not / inconclusive) gets added to the public `site_public/track.html` track record page, plainly labelled, with the contract reference and the actual numbers. If "did not," the headline says so. That is the public commitment.

## Pre-flight

This contract must be committed before 2026-06-10 to count as pre-registered. If the three [YOUR CALL] lines aren't revised and committed before resolution, the contract defaults to the proposed values (N=20, M=0.02), which is still a binding pre-registration — just with the default thresholds.
