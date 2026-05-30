# How my forecaster lied to me, six layers deep

*An audit that wouldn't stop being right too early.*

---

## The setup

My personal investing system logs predictions and scores them with Brier — the calibration metric. The idea: if I say "70% probability NVDA goes up next month" and it goes up 70% of the time across many such calls, the system is calibrated. Bad calibration shows up as a curve that doesn't follow the diagonal. Good calibration is the whole point of pretending probabilistic forecasting is more than vibes.

Eleven days before the first real batch resolution (40 predictions due 10 June), I ran an audit on the predictions waiting to resolve. I expected to find boring things to fix.

I found six bugs, each hiding the next.

---

## Layer 1: the mono-bucket

The 40 predictions in the batch had probability values of exactly **0.608, 0.626, 0.628, or 0.658**. Four unique values. All clustered in a 5-point band. None below 0.50, none above 0.72.

A forecaster whose probabilities all fit inside 5 points is not doing probabilistic forecasting. It is producing a constant in disguise. The Brier score on such a system measures nothing — it tests whether ~0.63 happens ~63% of the time, which any single-bucket histogram will mechanically answer one way or the other.

The cause was a formula: `estimate_probability(score, credibility, signal_type, impact_magnitude)` that capped output at [0.50, 0.72]. Plus 64 of 68 sources stuck at default `credibility = 0.50` because the monthly recalibration required `n_resolutions >= 10` per source and I had 6 total resolutions in the database. Bootstrap deadlocked.

The tempting conclusion: *"the maturity of data will fix this. More resolutions, more diversity. Pivot the publication plan to publish reasoning, not calibration plots."*

This is wrong, and a sharp evaluator would catch it in ten seconds. Time doesn't fix mono-bucket. In four months I'd just have more 0.63s.

---

## Layer 2: the prompt

I replaced the formula with a Sonnet call structured around three explicit steps:

1. **Base rate** — what's the probability a directional move (>5%) happens in 30 days, ignoring the signal entirely? Near 0.50 for liquid equities. Don't default to 0.6 *pour le confort*.
2. **Adjustment** — list the specific evidence in the signal that justifies deviating from base rate, and by how much. Be explicit on strength: none (stay at base rate), weak (0-3 points), moderate (5-15 points), strong (15-30 points).
3. **Anti-anchoring** — one sentence: why is your probability *neither* ~0.50 *nor* ~0.90? If you cannot justify the deviation, your probability *must equal the base rate*.

The forbidden patterns the prompt enforces: no probability in [0.55-0.70] "because it seems probable", no asserting "strong" without naming a verifiable fact, no fake calls — if no falsifiable directional evidence exists, return `direction="watch"` and the prediction never enters the scored ledger.

First test on 8 real signals: range expanded to [0.44-0.54], watch rate 62%. Better. Tempting to integrate immediately.

---

## Layer 3: the side door

The pushback: *"you verified the lower half. You haven't verified the high end. LLMs anchor at both ends. Maybe you broke the floor (now goes below 0.50) without touching the ceiling. You won't know without seeing it produce 0.75+ on real strong evidence."*

So: a synthetic 4-level evidence scale on NVDA. Vague narrative ("AI chip sector momentum"), routine analyst note ("Goldman raises target $1100→$1200"), earnings beat with magnitude ("$35.1B beats $33.5B"), multi-catalyst quantified ("guidance raised +$14B, $25B buyback, supply shortage resolved").

Result: the "very strong" case returned `probability=0.520 watch`. Same as the vague narrative. The prompt I designed to force calibration had collapsed the top end on the most lopsided test I could construct.

I almost concluded "ceiling intact, refactor needed". But I read the LLM's `anti_anchoring_reason`. It said, verbatim:

> *"The signal content would nominally justify a large upward deviation, **but the source is explicitly synthetic_test**, so..."*

I had injected `source_name="synthetic_test"` into the prompt as metadata. The LLM had downgraded its own evidence reading because it didn't recognize the source.

This is the exact bug that motivated my plan to "weight source credibility downstream" — applied as a separate layer instead of leaking into evidence scoring. I had violated my own architecture inside the prompt I wrote two hours earlier. Removed `source_name` from the prompt. Re-ran with the same content. Got `0.770 bullish strong` with the anti-anchoring reasoning *"not ~0.90 because a +12% pre-market gap creates mean-reversion risk over a 30-day window."*

The ceiling worked. I just hadn't fed it clean inputs.

---

## Layer 4: the symmetric sin

Re-tested the 20 real signals post-fix. Watch rate dropped from 62% to 12%. Looked great.

The pushback: *"62% might have been an artifact. 12% isn't verified either. The original sin was under-commitment — quasi-coinflips piling up as 0.5 watches. The symmetric sin is over-commitment — weak narratives forced into the ledger as ~0.5 directional calls. Same disease, different service. A Brier computed on a pile of 0.52 calls proves no edge."*

I looked at the sample. Three signals with `evidence_strength=weak` had been logged as bullish 0.54 or bearish 0.43. My prompt's spec said *"if no evidence supports a falsifiable direction, return watch"*. Weak ≈ vague narrative ≈ not falsifiable. My server-side enforcement only caught a narrow dead-zone [0.55-0.70]. Weak just below 0.55 leaked through.

Fixed: `evidence_strength ∈ (none, weak) → direction="watch"`, no matter the probability. Watch rate climbed back to 75% — which I now had a principled reason to call healthy, not a bug. Most signals in my pipeline are weak narratives by construction; most should rightfully exit before reaching the ledger.

---

## Layer 5: the meaning

Re-tested with the new floor. Directional cohort: range `[0.38-0.42]`, all bearish, all `evidence_strength=moderate`.

This was technically a passing test (no incoherence). It was also suspicious. A bearish call at 0.38 means *"I'm 38% confident this bearish call is correct"* — which means I'm 62% confident bullish would be correct. Why am I logging the bearish?

I had ambiguity in the prompt about what `probability` means. In Brier-style ledgers, `probability = P(your directional call is correct)` regardless of direction. In market-style ledgers, `probability = P(price goes up)` invariantly. The two collapse into "0.7 bullish" but they diverge sharply on "0.38 bearish".

My downstream resolver scored predictions as Brier (P(call correct)). The LLM was producing values in the other frame. The metric on the ledger was about to evaluate calls that were definitionally incoherent — silent garbage, the worst kind of bug because Brier averages don't notice they're averaging nonsense.

Fixed: explicit semantics in the prompt, plus a server enforcement that any `direction != "watch"` with `probability < 0.55` snaps to `watch`. You can't commit to a directional call if you're not more confident than a coin flip.

---

## Layer 6: the inputs

Re-tested on the same 20 real signals. Directional cohort: still `[0.60-0.62]`. The mono-bucket I'd been chasing for four iterations was *still there*, just at a different value.

I almost concluded *"need to diversify sourcing — add SEC EDGAR, earnings calendars, regulatory feeds"*. The pushback was sharper than that: *"the problem isn't the count of sources, it's the type of evidence. Newsletter commentary caps structurally at moderate. Strong evidence comes from primaries — 8-K, insider, earnings transcripts. You already have EDGAR, FRED, yfinance wired in your code. Verify the high-evidence sources actually reach the scorer before buying more."*

Five-minute query:

```
filings_8k_log    :  43 rows  (SEC 8-K filings, classified)
insider_snapshots : 378 rows  (Form 4 insider trades)
─────────────────────────────
sources.type unique values in signals table : 'newsletter' (nothing else)
```

421 lines of primary data, ingested by code that runs daily, sitting in parallel tables that never reach the scoring pipeline. The scorer sees 100% newsletter not because the system lacks primaries, but because the primaries flow into a separate plumbing run.

The temptation: declare bug found, commit "wire 8-K → signals", publish post. The pushback: *"you've confirmed the diagnostic. You haven't confirmed the payoff. Publishing 'wiring resolves the ceiling' before seeing it = committing in the post the exact sin the post is about."*

So: an ad-hoc DoD. Take 3 real 8-K from the database, feed them to V2, observe.

All 3 returned `probability=0.500 watch evidence=none`. The LLM's diagnostic on NVDA Item 2.02 (an *earnings filing*): *"boilerplate Item 2.02 header/cover page only — no actual earnings data, revenue figures, guidance, or qualitative commentary is present in the excerpt."*

The `filing_url` I had stored pointed to the cover page of the SEC filing. The actual material content — earnings tables, press release, CFO commentary — lives in **separate exhibits attached in the same filing folder**. My ingestion captured the wrapper, not the substance.

Sixth layer. Cousin of the fifth: *sources exist but aren't wired* → *URLs exist but point to empty*. One layer deeper.

---

## The fix that worked

`shared/edgar_exhibits.extract_filing_content(url)`: resolve folder via SEC `index.json`, exclude main filing (cover) and XBRL reports, fetch the top 2 attached `.htm` files by size, strip tags.

Re-test:

| 8-K | V2 verdict | Excerpt of evidence summary |
|---|---|---|
| **NVDA Q1 FY27 earnings** | **0.750 bullish strong** | *"revenue $81.6B (+85% YoY), Data Center $75.2B (+92%), $80B repurchase authorization, dividend increase 25x"* |
| **MSTR Bitcoin treasury** | **0.620 bullish moderate** | *"$1.5B convertible repurchase, debt $8.2B→$6.7B, +24,869 BTC"* |
| GOOGL debt notes issuance | 0.500 watch evidence=none | *"routine debt boilerplate, no earnings surprise or material business catalyst"* |

The chain works. NVDA earnings traverse V2 and produce a calibrated directional call at 0.75. Boilerplate gets correctly rejected. The system can now ingest primary data and produce diversity of probability — *if* the next step (wire the extractor into the ingestion job) gets shipped without a similar bug six layers below.

Codified as a regression fixture (`tests/test_edgar_exhibits.py`, network-dependent, marker `slow`) that fails loudly if either the extractor regresses to the cover-page bug or V2 loses its discrimination on real strong evidence. The bug was silent for months. It can't be silent anymore.

---

## The lesson

Six iterations. Six layers. At each *"ah, I found it"*, verifying first revealed the real bug one layer deeper:

```
formula cap → prompt elicitation → source contamination → 
commit threshold → ledger semantics → wiring → extraction
```

The pattern I came out with: **the conclusion is always one step ahead of the proof.** Every time I felt the urge to declare "fixed", that was the signal there was a layer below I hadn't checked.

The adversarial pushbacks that drove each verification weren't optional. Left to my own pace, I would have shipped after layer 2 (looked great, wasn't), or layer 4 (silent semantic bug), or layer 5 (wire-up to broken URLs, would have flooded the ledger with 0.5 watches). Each "almost done" was wrong in a way that only the next verification could surface.

That's the thing worth publishing. Not the scorer. Not the calibration metric. The discipline of refusing to declare convergence until the verification you didn't want to run has run.

---

*Code at [github.com/Conscious-Bot/mes-bots-finance](https://github.com/Conscious-Bot/mes-bots-finance). Decision log at `docs/decision_logs/01_calibration_unanchored.md`. The wire-up step (8-K → signals job) is deliberately left for a fresh session — that decision tree (schema, source attribution, dedup) is exactly the kind I now know not to trust at commit #18.*
