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

## Sample floor — N = 20 (committed 2026-06-05)

**If `n_resolved < N`, the read is NULL.** No verdict. No priority change. No conclusion about LLM value. The number gets reported as a transparency snapshot ("here's what the small sample showed") but it does not bind future direction.

N = 20. Current state: 18 already resolved + ~17 expected in this batch ≈ 35. Floor is low enough to survive a few stuck predictions and still produce a binding read, high enough to not be absurd.

**Effective N caveat — read this before reading the number.** N=35 is nominal. The predictions are heavily theme-correlated (semis cluster: NVDA/AMD/AVGO/MU/ARM/AMRC; crypto cluster: MSTR/COIN/IBIT; etc.). Independent information is well below 35. Treat the bootstrap CI as a *minimum* uncertainty bound — true uncertainty is wider because the bootstrap implicitly assumes independence that doesn't hold. The dedup-by-cluster Brier (already wired in `post_resolution_brier_report.py`) is the more honest read.

## Verdict bands — M = 0.03 (committed 2026-06-05) — readability floor only

Three outcomes, no fourth:

- **Earned its cost** if `Brier ≤ baseline − M`
- **Did not earn its cost** if `Brier ≥ baseline`
- **Inconclusive** if `baseline − M < Brier < baseline`

M = 0.03. Stricter than the original proposed 0.02 — doctrine-consistent with anti-flattery.

**But M is a readability floor, not the binding verdict.** A fixed gap M can't distinguish a real edge of 0.03 from a noise swing of 0.03. The signal-vs-noise question isn't a function of a fixed threshold — it's a function of the confidence interval.

## Binding verdict — CI-based (the real test)

**The committed verdict is read from `scripts/post_resolution_brier_report.py` `_ci_verdict()` (already wired), not from the simpler `j_day.py` Telegram auto-message.** The bootstrap percentile CI (n=1000, seed 42) is the authoritative read:

- **Earned its cost** if `CI_high < baseline` (entire interval below 0.25)
- **Did not earn its cost** if `CI_low > baseline` (entire interval above 0.25)
- **Inconclusive** if the CI envelopes the baseline (which is what's expected for N=35 nominal in a noisy first cohort)

The point estimate crossing M is informative as a *headline*, not as the verdict. The verdict is the CI relationship to the baseline.

This applies to both the raw Brier and the cluster-dedup Brier. **The dedup version is the more honest read** because of theme correlation (see N caveat above).

### Pre-resolution forecast (so we read 10/06 honestly)

The 10/06 V1 verdict is essentially pre-determined by sample size + noise structure: at N≈35 nominal (effective N << 35 due to theme correlation) and the dry-run Brier ≈ 0.295 already on record, the CI will envelope the baseline → outcome will be **"did not earn its cost" or "inconclusive"** regardless of M. That's not a failure of the contract — it's the contract telling us truth: V1's first cohort doesn't have the statistical mass to declare itself, and the point estimate is on the wrong side of baseline anyway.

The M=0.03 + CI-excluding-baseline rule **really bites later**, on V2 cohorts when N grows and the question shifts from "can we read anything" to "is the apparent edge real or noise." That's where this contract pays for itself.

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

This contract is pre-registered: committed on 2026-06-05, before resolution of the 2026-06-10 V1 cohort. The two thresholds (N=20, M=0.03) plus the CI-based verdict mechanism are the binding contract going into the read.
