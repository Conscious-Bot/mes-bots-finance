# ADR 007 — Bidirectional Thesis Tracker: Core Behavioral Discipline Mechanism

**Status**: Accepted (operational since Day 2, ~13 May 2026; formalized Day 12, 18 May 2026)
**Author**: Olivier Legendre (with Claude as code partner)
**Cross-references**: ADR 001 PIT bitemporal credibility; ADR 004 USD canonical migration; intelligence/bias_tagger.py; shared/positions.py; shared/storage.py decisions/theses tables; KPI #2 + #5.

---

## Context

The user identified two specific, asymmetric behavioral biases in their personal investing history. Generic finance tools (newsletters, signal aggregators, market screeners) do not address them — they produce MORE information, not behavioral correction.

### The two biases (empirical, user-specific)

**Bias 1 — Sells winners too early (locking-in + mean reversion)**

Historical examples in user's track record: PLTR, NVDA. Pattern: winning position reaches +20-30% unrealized gain; user closes the position citing "good enough" or "can't lose what's not realized"; underlying thesis remains intact; position would have run further (often 2-5x more) if held. The bias compounds because the realized P&L is small, the unrealized opportunity cost is invisible.

Root cause cognitive mechanics:
- **Locking-in bias**: the certainty of small gain dominates the probability of larger gain
- **Mean reversion bias**: "it's gone up a lot, must come back" (defies trending markets)
- **Loss aversion at gain stages**: fear of losing existing paper gain > anticipation of further gain

**Bias 2 — Fails to sell crypto at indicator tops (FOMO/greed)**

Historical examples: BTC, ETH cycle tops 2021-2022. Pattern: indicators (on-chain, sentiment, RSI, etc.) signal late-cycle conditions; user holds expecting "one more leg up"; cycle ends; round trip back to entry or below.

Root cause cognitive mechanics:
- **FOMO at top**: extreme prior performance creates expectation of continuation
- **Anchoring to recent peak**: cannot accept exit below recent high
- **Greed > Discipline**: the asymmetry of "if I exit now and it doubles" felt regret > "if I hold and it halves" experienced regret

### Why generic tools don't help

The user already has access to plenty of analysis:
- 9 subscribed newsletters (Stratechery, SemiAnalysis, Glassnode, Apollo, Noahpinion, Doomberg, etc.)
- 178 tickers tracked across thematic groups
- Real-time price data, sentiment, on-chain metrics

The missing piece is NOT more information. The missing piece is **mechanical discipline at decision moments**. Generic tools provide signals; they don't enforce reflection.

A bot that produces more signals = adds to the cognitive noise.
A bot that enforces reflection = mechanizes discipline.

mes-bots-finance is built for the latter.

---

## Decision

Adopt **bidirectional thesis tracking** as the core behavioral mechanism. The system tracks BOTH biases symmetrically through a thesis ledger with mechanical asymmetry ratios + automated bias detection.

### Key design principles

1. **Bidirectional symmetry**: equal weight on both biases. The system enforces anti-sell-too-early AND anti-hold-too-long. Over-correcting one bias would create the other.

2. **Mechanical not discretionary**: explicit framework with empirical asymmetry ratios per conviction tier. No "I'll decide when I get there" — the targets are set at thesis opening and the bot enforces them.

3. **Pre-commit reflection, not automated execution**: the bot does NOT trade. It forces structured reflection before the user commits. Execution remains with user. This is intentional separation of analysis (bot) from execution (user).

4. **Auto-bias tagging on every material decision**: bias_tagger LLM runs on entry and exit decisions, surfacing the cognitive pattern the user is exhibiting at decision time. KPI #5 enforces 100% material decision journaling.

5. **Empirical asymmetry, not theoretical**: target/stop ratios are derived from user's historical exit timing analysis (Day 5 evening baseline), not Kelly criterion or theoretical optimum. Empirical user-derived ratios encode the user's actual behavioral profile.

---

## Asymmetry framework

Conviction tier system c1 through c5. Each tier maps to explicit target/stop ratios committed at thesis opening.

### Empirical baseline (Day 5 evening framework)

| Tier | Target | Stop | Ratio | Notes |
|------|--------|------|-------|-------|
| c5 (highest conviction) | +70% | -25% | 2.8 | High asymmetric reward; reserved for thesis-validated mega-cap or category-defining positions |
| c4 | +60% | -20% | 3.0 | Strong conviction; standard quality position |
| c4 mod (L1 / HBM) | +60% | -22 to -25% | 2.4-2.7 | Modified for specific bias profiles where stop is wider |
| c3 | +50% | -18% | 2.8 | Moderate conviction; entry-level position |
| c3 mod (story / defense) | +50% | -18 to -25% | 2.0-2.8 | Modified for story / defense positions with wider drawdown tolerance |

c1-c2: not actionable. No formal thesis required. Tracker does not open positions at these tiers.

### Why these specific ratios?

The ratios are EMPIRICAL — derived from analysis of user's historical PLTR/NVDA exit timing patterns. They are NOT theoretical Kelly criterion outputs. The user's actual bias-1 behavior was to exit winners around +15-25%; the c5 target of +70% is calibrated to force discipline 3x past that comfort zone. The stop levels (-18% to -25%) reflect user-observed acceptable maximum drawdown before invalidation.

Theoretical Kelly criterion requires accurate edge estimates. A biased trader systematically lacks accurate edge estimates (that's the bias). Empirical user-derived ratios are more honest: they encode the discipline gap, not pretend it doesn't exist.

### Important non-feature: tier promotion is manual

Currently, a c3 position does NOT automatically promote to c4 as thesis validates. The user explicitly upgrades conviction tier via Telegram if thesis hardens. This intentional manual gate prevents conviction inflation (CONVENTIONS.md Section 14: "Conviction inflation watch").

Future consideration: auto-tier-promotion based on empirical validation signals + price action. Deferred until KPI #2 baseline established.

---

## Mechanism flow

### 1. Thesis opening (manual, via Telegram)
/position_buy <TICKER> <QTY> <PRICE> [reasoning]

Flow:
1. User commits ticker + direction (long/short) + qty + price + optional reasoning
2. Bot detects entry vs scale_in via positions_mod.get_position
3. positions_mod.add_buy updates positions table + position_events log
4. _portfolio_journal_ctx auto-context: price, regime, credit, thesis_id, materiality_top, direction
5. storage.log_decision creates entry in decisions table (KPI #5)
6. bias_tagger.auto_tag_biases LLM runs on the decision: FOMO, anchoring, recency, herding, etc.
7. storage.update_decision_bias_tags links detected biases to the decision

Bot response: confirmation of position + asymmetry computed from c-tier (handled separately via /asymmetry handler).

### 2. Thesis tracking (passive, via price_monitor cron)

Every 15 minutes during market hours:
- For each active thesis: fetch current price
- Compute distance from target / stop (as percentage)
- If approaching target (>90% of target): Telegram notify "TICKER approaching target $X"
- If approaching stop (>90% of stop): Telegram notify "TICKER approaching stop $X"
- If crossed: trigger thesis review notification

User sees the bot doing the watching, freeing cognitive bandwidth from price obsession.

### 3. Thesis closing (manual, via Telegram)
/position_sell <TICKER> <QTY> <PRICE> [reasoning]

Same flow as opening but:
- positions_mod.add_sell updates positions + computes realized PnL
- log_decision creates exit decision entry
- bias_tagger runs on exit decision (different bias set: locking-in, mean-reversion, etc.)
- If position fully closed: KPI #2 update (prediction resolved correct/incorrect vs target_hit)

### 4. Bias detection layer (intelligence/bias_tagger.py)

`auto_tag_biases(decision, position, regime_str, top_signals) -> list[str]`

LLM prompt enumerates known bias patterns:
- **FOMO** (Fear of Missing Out): entry after extended rally without conviction reason
- **Locking-in**: exit on small positive PnL without thesis invalidation
- **Mean reversion bias**: exit assumption that "it's gone too far"
- **Recency bias**: over-weighting last 5 days news
- **Anchoring**: stuck on entry price or recent high as reference
- **Herding**: following recent narrative without independent analysis
- **Confirmation**: only reading bullish (or only bearish) sources after position open
- **Disposition effect**: holding losers, selling winners

Output: list of bias tag strings, attached to decision in decisions table.

Over time, the cumulative bias pattern becomes user-specific empirical evidence:
- "User exhibits locking-in bias 60% of exit decisions on positions <30 days held"
- "User shows anchoring bias to entry price on positions held >180 days"

This data feeds the calibration engine (PHILOSOPHY.md loop 5: User Bias Detector).

---

## Consequences

### Positive

1. **Discipline mechanized vs willpower**. Pre-commit reflection survives emotional moments. The bot doesn't depend on the user's discipline at the moment of decision.

2. **Compound learning**. Each thesis resolution → Brier calibration (KPI #2 + #3) → updated bias detection priors → better future decisions. The system becomes more user-calibrated over time.

3. **Behavioral pattern detection over time**. bias_tagger output cumulated across decisions reveals user-specific bias frequencies. The user sees their own patterns externally vs introspectively (which is bias-prone).

4. **Bidirectional symmetry**. The system does not over-correct one bias to create another. Both bias 1 (sell too early) and bias 2 (hold too long) are tracked with equal mechanism weight.

5. **Defensible Path 5/6 narrative**. This is NOT a generic finance LLM agent. This is a behavioral discipline enforcement system with empirical asymmetry framework and automated bias detection. The mechanism is articulable, the rationale is empirical, the math is mechanical.

### Negative

1. **High friction at decision moments**. Every material decision requires Telegram interaction + journaling. Mitigated by streamlined `/position_buy` syntax with auto-context. Still: deliberate friction. Not a bug.

2. **Bias detection is LLM-based, not deterministic**. False positives possible (e.g. LLM flags FOMO when actually thesis-driven). Mitigated by user override capability + cumulative pattern analysis over single instances.

3. **Asymmetry ratios are user-specific empirical**. They do not generalize to other users without re-calibration. This is a Path 6 prosumer challenge: how to onboard new users to derive their own ratios. Deferred until single-user validation completes (post-J+30).

4. **Single-user assumption**. Currently the system tracks ONE user's behavioral profile. Multi-user would require per-user bias profile + asymmetry ratios. Out of current scope.

### Neutral

1. **The bot does NOT trade**. Decisions and execution remain with the user. This is intentional separation of analysis (bot) from execution (user). Eliminates execution risk and regulatory issues. The mechanism is reflective discipline, not automation.

2. **Manual conviction tier**. User must explicitly assign c1-c5 at thesis opening; no auto-classification from price action or thesis content. Deliberate gate against conviction inflation.

---

## Alternatives considered

### 1. Single-direction discipline (anti-sell-too-early only)

**Rejected**. Crypto FOMO bias (bias 2) is empirically the LARGER of the user's two biases in dollar terms (BTC/ETH 2021-2022 cycle held through tops). An asymmetric system targeting only bias 1 would let bias 2 compound. Bidirectional symmetry is the explicit fix.

### 2. Auto-trading / execution integration

**Rejected**. Multiple reasons:
- Execution risk (slippage, partial fills, broker-specific edge cases)
- Regulatory issues (broker integration + user identification compliance)
- Violates "bot doesn't trade" architectural principle (separation of analysis from execution)
- The discipline goal is REFLECTIVE decision-making. Automation removes the reflection moment that the system is designed to force.

If user wants execution, they trade manually after the bot's reflection step.

### 3. Discretionary tier system (manual asymmetry per thesis)

**Rejected**. Discretion is precisely where biases enter. If the user can set custom target/stop per thesis, the biases find expression in those custom levels (e.g. setting tighter targets on positions the user is uncertain about, replicating bias 1). The mechanical c1-c5 ratios are the ENFORCEMENT mechanism.

The user CAN override conviction tier (assign c5 vs c4) but cannot override the target/stop ratios within a tier. The discretion is at tier assignment (where it can be tracked + audited via bias_tagger) not at level setting (where it would hide).

### 4. Theoretical (Kelly criterion) asymmetry ratios

**Rejected**. Kelly assumes accurate edge probability estimates. A biased trader systematically lacks accurate edge estimates — that's the BIAS. Using theoretical Kelly ratios would optimize for a fiction (the unbiased edge estimate the user doesn't actually have).

Empirical user-derived ratios are more honest: they encode the discipline gap explicitly. The ratios are calibrated to push the user's actual exit behavior past their actual bias comfort zones, not to theoretical optimum.

This is engineering judgement: empirical > theoretical for behavioral applications where the human is systematically biased.

---

## Migration / status

The bidirectional thesis tracker has been OPERATIONAL since Day 2 (~13 May 2026). This ADR is RETROACTIVE — it formalizes a mechanism that has been running, not introducing a new decision.

Empirical state at ADR acceptance (Day 12, 18 May 2026):
- 21 EUR positions ~€42.7K total book
- 17 c3+ positions filled with framework-derived target/stop
- 4 orphan c1 positions SKIPPED (AMD, GOOGL, SAF.PA, TSLA) — pending review J+30 (2026-06-16)
- Thesis #1 AI_compute: 14 positions, 67% of book
  - S c5: 6920.T (Tokyo Electron)
  - A c4: ASML, BESI, 4063.T, TSM, 000660.KS (SK Hynix), SNPS, KLAC, COHR
  - B c3: STMPA, MRVL, AVGO, ALAB, TER
- Thesis #2 Electrification c4: 7011.T, SU.PA (2 positions)
- Thesis #4 EU_defense c3: HO.PA (1 position)

Phase B5 journal logging chain operational since Day 5 Ship 5 (recovered from earlier regression). KPI #5 (100% material decisions journaled) enforced runtime.

bias_tagger has accumulated decision-level bias tags since Day 5. Pattern analysis (cumulative bias frequency by decision_type) deferred until N_decisions >= 30 (KPI #2 baseline gate).

---

## Open questions / future work

1. **Auto-tier-promotion logic**: when c3 → c4 based on thesis validation signals? Deferred until empirical KPI #2 baseline (post-J+30).

2. **Cross-thesis correlation**: if AI_compute thesis hits target, should related positions (semis_core) trigger review? Currently NO — each position tracked independently. Future enhancement.

3. **Asymmetry tightening as Brier improves**: better-calibrated bot → tighter ratios → more discipline value. Calibration plot dynamic adjustment, deferred to Path 6 (subscription) era.

4. **Bias pattern feedback into thesis opening**: if user's recent decisions show locking-in bias 80% rate, prompt warning at /position_sell. Currently bias_tagger only logs; doesn't intervene. Future Path 6 feature.

5. **Multi-thesis-tier abstractions**: thematic theses (AI_compute, electrification, defense) currently grouped manually in /portfolio_narratives. Auto-grouping from position metadata would scale better.

---

## References

- intelligence/bias_tagger.py: `BIASES` dict + `auto_tag_biases()` LLM call
- shared/positions.py: position tracking, `_enrich_with_live` (Day 11+12 Batch 3A USD canonical)
- bot/handlers/positions.py: `cmd_position_buy` + `cmd_position_sell` Phase B5 chain (Day 12 Step C strict-typed)
- shared/storage.py: `decisions` table, `theses` table, `position_events` table, `log_decision`, `update_decision_bias_tags`
- intelligence/morning_brief.py: `/brief` top5 positions display (Day 12 Step 2B FM-10 fix)
- intelligence/price_monitor.py: thesis trigger watch (Batch 3B deferred post-J+30)
- ADR 001 PIT bitemporal credibility: feeds bias_tagger context over time
- ADR 004 USD canonical migration: pipeline currency-coherent for /brief PnL display
- ADR 006 Process discipline R19 v2-v5: enforcement gates on each Day 11+12 patch ship
- KPI #2 (NON-NEG ≥5 predictions resolved 28d): track record on thesis resolutions
- KPI #5 (100% material decisions journaled): bias_tagger chain enforcement
- PHILOSOPHY.md "High Standard Mode" + the 6 loops including User Bias Detector (loop 5)
