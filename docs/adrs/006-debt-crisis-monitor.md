# ADR 006 — Debt Crisis Monitor (15-indicator phase-based tail-risk overlay)

**Status**: Accepted (Phase 1 shipped)
**Date**: 2026-05-20 (Day 14 evening)
**Discipline override**: Conscious violation of PHILOSOPHY observation discipline (J-20 to KPI #2 batch resolution 2026-06-10). Justified as tail-risk hedge on existing thesis cluster (AI_compute 46.5% concentration), not new ticker/source/thesis.

---

## Context

Olivier's portfolio: 21 positions, 46.5% concentrated in AI_compute thesis cluster (4063.T, TSM, ASML.AS, SNPS, 7011.T, STMPA.PA all >5% style cap). Concentration is conditional on absence of major US debt crisis trigger (30Y >6%, JPY 200+, regional bank failures). Bot tracks per-thesis signals but no formalized macro overlay for systemic debt crisis early warning.

## Decision

Implement 15-indicator phase-based monitor (`intelligence/debt_monitor.py`) with deterministic threshold classification + composite scoring. Single module, no LLM, reuse `shared/macro.py` FRED+yfinance helpers (DRY per Lesson 15).

**Tier 1 (daily, weight 1.0):** TYX, Gold, USDJPY, VIX, HY_OAS, DXY, BTC
**Tier 2 (weekly, weight 0.75):** MOVE, KRE, T10Y2Y, RepoSRF, CopperGold ratio
**Tier 3 (monthly, weight 0.5):** CoreCPI, FedBalance, ISMMfg

**Phase mapping (per-indicator):** 1=normal, 2=stress, 3=severe, 4=crisis. Boundaries per Olivier spec calibrated to 2026-05 market regime.

**Composite scoring:** indicator_weight × phase_weight (1/8/16/32 pts per phase). Thresholds composite 0-22 / 22-60 / 60-115 / 115+ → Phase 1/2/3/4 (scaled for 15 indicators from Olivier's 30-indicator formula).

## Consequences

**Positive:**
- Tail-risk monitoring decoupled from per-thesis signals
- Deterministic, no LLM cost
- Reuses existing FRED/yfinance infrastructure (no new dependencies)
- Empirically actionable: first scan Day 14 returned Composite 37.5 = Phase 2 STRESS, driven by Gold $4,485 (P3) + RepoSRF $12.9B drainage (P3) — alignment with thesis concentration concern surfaces same evening

**Negative / tradeoffs:**
- 30 indicators trimmed to 15 (manual auction tail, lagging FINRA margin, hard-to-source CDS dropped)
- ISMMfg may need alternative FRED series (NAPM possibly deprecated)
- Thresholds calibrated 2026-05; require recalibration if regime shifts
- Cron scheduler integration deferred to Phase 2 (tomorrow)

## Empirical first-scan results (2026-05-20 evening)

| Indicator | Value | Phase | Contribution |
|---|---|---|---|
| TYX (30Y) | 5.18% | 1 | 1.0 pts |
| Gold | $4,485.70 | **3** | **16.0 pts** |
| USDJPY | 159.01 | 1 | 1.0 pts |
| VIX | 18.08 | 1 | 1.0 pts |
| HY_OAS | 283 bp | 1 | 1.0 pts |
| DXY | 99.44 | 1 | 1.0 pts |
| BTC | $77,440 | 1 | 1.0 pts |
| MOVE | 85.32 | 1 | 0.8 pts |
| KRE | $67.56 | 1 | 0.8 pts |
| T10Y2Y | +0.54% | 1 | 0.8 pts |
| RepoSRF | $12.9B | **3** | **12.0 pts** |
| CopperGold | 0.00139 | 1 | 0.8 pts |
| FedBalance | $6.73T | 1 | 0.5 pts |
| CoreCPI | (fetch failed) | — | — |
| ISMMfg | (fetch failed) | — | — |

**Composite: 37.5 pts → Phase 2 STRESS.**

Drivers: Gold $4,485 (mainstream fear narrative active, +40% from $3,200 estimate when spec was written) + Repo SRF drainage (excess liquidity at Fed drained from peak ~$2T to $12.9B). Both indicators credibly Phase 3 — not false positives.

Strategic alignment with concentration breach finding: Phase 2 = "Cash +5%, halt aggressive deploy" per spec. Coherent with prudent trim direction on 6 over-sized positions.

## Implementation status

**Phase 1 (today):**
- ✅ Module `intelligence/debt_monitor.py` (INDICATOR_CONFIG + fetch + classify + persist + composite)
- ✅ Handler `bot/handlers/debt_crisis.py` `/debt_status [refresh]`
- ✅ DB schema `debt_signals` + `debt_composite`
- ✅ E2E proof: TYX, Gold, VIX, USDJPY fetched + classified + persisted
- ✅ Full 15-indicator scan run + composite computed
- ✅ Wired in bot/main.py

**Phase 2 (tomorrow):**
- Fix CoreCPI silent fail (_fetch_fred_cpi_yoy debug)
- Fix ISMMfg (NAPM deprecated check, alternative FRED series)
- Fix CopperGold display formatting
- APScheduler cron registration: Tier 1 daily 06:00 Paris, Tier 2 Mon 06:30, Tier 3 1st 07:00
- Alert dispatch on composite phase escalation (phase 1→2, 2→3, 3→4)
- `/debt_history INDICATOR` handler (30d trend)
- `/debt_alerts on|off` toggle
- Hypothesis property tests on classify_phase invariants
- Smoke tests no-regression

## Alternatives rejected

**A. Full 30-indicator spec implementation now**
- Manual auction tail / Sovereign CDS / FINRA margin require scraping or manual entry
- Adds maintenance overhead with marginal signal-to-noise
- Trimmed to 15 deterministic API-fetchable

**B. LLM-based interpretation layer**
- Adds cost ($0.01-0.05 per scan)
- Reduces determinism
- Phase classification is binary by design, no LLM needed
- Rejected: keep monitor deterministic, leave interpretation to /risk_check downstream

**C. Defer entirely to post-J+30**
- Acknowledged as PHILOSOPHY-aligned option
- Rejected because empirical evidence Day 14 (Gold $4,485 P3, RepoSRF $12.9B P3) shows current macro warrants monitoring NOW
- Override discipline document in HANDOFF for traceability

## References

- ADR 005 (Day 13-14) — EUR canonical positions (immediate predecessor)
- Lesson 15 — empirical verification beyond SQL (applies to indicator value classification)
- `intelligence/regime.py` — existing macro regime detector (complementary, not duplicate)
- `shared/macro.py` — FRED+yfinance wrappers reused

---

## Phase 2A + 2B SHIPPED (Day 14 evening, 20 May 2026)

### Phase 2A — Data quality + invariant locks (commit e49c326)

**Indicator fixes:**
- CoreCPI YoY: `limit=14 + obs[11]` for true 12-month YoY (was `obs[12]` = 13 months back)
- ISMMfg deprecated (FRED dropped ISM series 2024+, paywalled) → replaced by **MfgIP_yoy** (FRED IPMAN YoY %), semantically closest available manufacturing signal. Phase ranges: >2% expansion / 0-2 sluggish / -2-0 contraction / <-2 recession.
- `__main__` display: smart format handles small ratios (0.0014 instead of 0.00)

**Test lock:**
- 18 Hypothesis property tests on `classify_phase`, `composite_phase_from_score`, `_score_contribution`, `INDICATOR_CONFIG` structure (15 indicators, tier distribution 7/5/3, weight canonicals 1.0/0.75/0.5, range well-formedness)
- 281 → 299 tests passing

**Re-scan empirical:** Composite **42.0 pts → Phase 2 STRESS** (up from 37.5, +4.5 from MfgIP_yoy now classified P2 sluggish). Drivers:
- Gold $4,488 → P3 (+16 pts, mainstream fear)
- RepoSRF $12.9B → P3 (+12 pts, drainage from $2T peak)
- MfgIP_yoy +1.47% → P2 (+4 pts, manufacturing sluggish)
- 12 other indicators Phase 1

### Phase 2B — Scheduler crons + transition alerts (commit 1e4c745)

**Alert dispatch (`_dispatch_alerts`):**
- Composite phase escalation alert (P1→P2, P2→P3, P3→P4) with full driver breakdown
- Tier 1 individual indicator transition to Phase 3+ (single-indicator alert, only on fresh transition — not re-alerted while persisting at P3+)
- Telegram push via `shared.notify.send_text`
- Markdown formatting with phase emoji map {1:🟢, 2:🟡, 3:🟠, 4:🔴}

**`run_scan(dispatch_alerts=False)` signature change:**
- Captures `prev_composite_phase` + `prev_indicator_phases` BEFORE persist
- If `dispatch_alerts=True`: post-persist diff → `_dispatch_alerts(...)`
- Default `False` preserves CLI/test isolation (no spurious Telegram fires)

**Cron wrappers (3 APScheduler entry points):**
- `cron_tier1_daily()` — Tier 1 scan, daily 06:00 Paris
- `cron_tier2_weekly()` — Tier 2 scan, Monday 06:30 Paris
- `cron_tier3_monthly()` — Tier 3 scan, 1st of month 07:00 Paris

**bot/main.py wiring:**
- 3 `sched.add_job` registered
- Announce log extended to include `debt_tier1 6:00, debt_tier2 Mon 6:30, debt_tier3 1st 7:00`
- Total cron count: 22 → 25

**Smoke verified:** Re-scan with `dispatch_alerts=True` on already-Phase-2 state → no Telegram alert (transition detection works correctly).

### Status: protective layer LIVE

- Bot will autonomously monitor debt regime starting tomorrow 06:00 Paris
- If Gold/RepoSRF transitions OR composite escalates → immediate Telegram push with stress drivers breakdown
- Olivier receives signal without needing to invoke `/debt_status`
- Coherent with PHILOSOPHY: extends discipline enforcement to regime detection layer

### Phase 2C deferred (carry-forward, ~1h)

- `/debt_history INDICATOR` handler — 30d sparkline + phase transitions per indicator
- `/debt_alerts on|off` handler — global mute toggle (default ON for transitions)

**Rationale for deferral:** Phase 2B = full functional protective layer. Phase 2C is UX nice-to-have, not core. 12h+ Day 14 cumulative — diminishing returns. Phase 2C value < closing propre + observation discipline restart.

---

## Phase 2C SHIPPED + audit findings (Day 14 evening post-audit)

### Phase 2C ships (commits 2eebde3, d6463fa)

**`/debt_history INDICATOR`** handler (`bot/handlers/debt_crisis.py`):
- 30d sparkline via Unicode block characters (▁▂▃▄▅▆▇█) normalized over min/max value range
- Phase transitions count + last 5 observations table with timestamps
- No-arg call lists all 15 indicators grouped by tier
- Case-insensitive indicator name matching
- Helper `_format_val_compact()` is abs-aware for negatives (fixes latent legacy bug in `_fmt_indicator_line` where `val >= 1000` missed negative magnitudes)

**`/debt_alerts on|off`** toggle (`bot/handlers/debt_crisis.py`):
- Persists state in `bot_state.json` key `debt_alerts_enabled` (default True)
- When OFF: cron scans persist data normally, but no Telegram push fires on transitions
- Manual `/debt_status` queries still work
- Round-trip verified empirically via `storage.update_state` + `storage.load_state`
- Fail-open contract: any read error returns True (never accidentally muted by bot_state corruption)

### Audit findings + fixes (commit 2eebde3)

Post-Day-14-evening rigorous audit produced 1 false positive (S1, retracted) and 4 real findings (L1, H1, H2, H3) plus 2 codification needs (Lessons 17-20).

**S1 — FALSE ALARM (retracted)**: Claimed `cron_tier1_daily` would corrupt composite by recomputing on only Tier 1 indicators. Reality: `run_scan` lines 391-400 already merged stale cached Tier 2+3 values from `get_latest_indicator()` with fresh-scanned tier values, computing composite on full 15 with `stale: True` markers. My audit was wrong — read function signature + opening loop, pattern-matched without reading the full conditional branch. Codified as Lesson 17 (CONVENTIONS.md) to prevent recurrence.

**L1 — Cron exception envelope** (FIXED): All 3 cron wrappers (`cron_tier1_daily`, `cron_tier2_weekly`, `cron_tier3_monthly`) previously called `run_scan(...)` directly with no try/except. A FRED API outage or scheduler crash would log a traceback and silently die — bot continues but the 06:00 Paris protective layer is blind for 24h. Fix: shared `_cron_run(tier, label)` helper wraps work in try/except with `log.exception` + `notify.send_text` crash alert. Pattern aligned with existing bot/main.py crons. Empirically verified via `mock.patch.object(run_scan, side_effect=RuntimeError)` — cron does NOT raise, crash-alert dispatched with class+message preview. Codified as Lesson 18.

**H1 — Alert content actionability** (FIXED): Composite escalation alert previously contained drivers breakdown + "Run /debt_status for full breakdown" — pure data, no recommendation. A 06:00 wake-up push that requires context-switch to recall the playbook = friction = abandonment. Fix: `_PHASE_ACTIONS` constant with phase-specific cash% + defensive actions, injected as `*Action:* {playbook[new_phase]}` line in composite alert before /debt_status reference. Codified as Lesson 19.

**H2 — Integration tests for dispatch path** (FIXED): The previous 18 Hypothesis tests covered pure math (classify_phase, composite, score_contribution, INDICATOR_CONFIG structure). Zero tests on `_dispatch_alerts` — the alert formatting and dispatch behavior was production-only validated. Fix: `tests/test_debt_dispatch.py` with 9 integration scenarios mocking `shared.notify.send_text` + `_alerts_enabled`. Coverage: P1→P2/P2→P3/P3→P4 escalations (each with action playbook assertion), no-transition no-alert, first-scan baseline rule (prev=None), Tier 1 indicator P1→P3 transition, Tier 1 dedup at P3+, Tier 1 first-observation baseline label, alerts-disabled short-circuit. 299 → 308 tests passing.

**H3 — None-prev composite documented** (FIXED): `_dispatch_alerts` previously had a one-line docstring. Now includes full behavior contract: alerts-enabled gate, prev=None = baseline establishment (no alert), Tier 1 dedup rule, fail-open on bot_state read errors.

### Lessons codified (CONVENTIONS.md Section 16)

- **Lesson 16**: heredoc-in-heredoc double-escape diligence + triple-quote nesting trap (caught in Bash 66-67 and Bash 70-71 during this work)
- **Lesson 17**: audits MUST read complete control flow before declaring SEVERE (anti-false-positive discipline, retroactive from S1)
- **Lesson 18**: cron entry points MUST have try/except + notify envelope
- **Lesson 19**: user-facing alerts MUST include actionable recommendation
- **Lesson 20**: UTC explicit on all persisted datetime fields (20+ legacy violations tracked in TODO P2 sweep)

### Final state Day 14 ultra-final

- 308/308 tests passing (281 pre-audit + 18 debt_monitor pure math + 9 debt_dispatch integration)
- 25 crons live (22 baseline + 3 debt_monitor with try/except envelope)
- Composite persisted: 42.0 → Phase 2 STRESS (Gold P3, RepoSRF P3, MfgIP_yoy P2)
- 5 commits since `day14-debt` tag: L1+H1+H3+Phase2C ship, H2 tests, Lessons 16-20 + UTC sweep
- Bot PID 71677 vivant
- `_alerts_enabled()` toggle live (default True), `/debt_alerts off` available if needed during testing
- ADR 006 status: **CLOSED** (all phases shipped, audit findings resolved, lessons codified)

### Reopen entry point

1. `cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate`
2. `pgrep -fil "python.*bot.main"` confirm
3. Overnight check: did `debt_tier1_daily` fire at 06:00 Paris? Any Telegram alert?
4. KPI #2 timer J-19 to 2026-06-10 (44 predictions batch resolution)
5. Concentration policy decision (a/b/c) STILL unresolved — block before next `/position_buy`

