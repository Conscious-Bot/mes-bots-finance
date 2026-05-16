# HANDOFF — mes-bots-finance

**Last refresh**: 16 May 2026 ~20:15 KST — Day 5 evening v3 final close
**Mode**: High Standard / Solidification — Path 5/6 strategic target
**Current commit**: c1032b8 (49 commits Day 5 total)
**Bot state**: PID 34990 vivant, scheduler healthy, 22 crons active

---

## TL;DR — what changed Day 5 evening v3 (since 60cf504 tag day5-final)

**16 commits post-tag** :
- 108d57d HPQ + Pharma cleanup (6 watch theses superseded)
- 88db101 Intl pipeline fix (config + prompts US bias removed + thesis_health narrative=)
- 192b62c HANDOFF refresh
- a60b062 Mission queue 6 steps
- 65c7265 /analyze today_str fix
- b68120c /asymmetry 3-section bucketize (computed/incomplete/watch/errors)
- **6b97f2d** F1b Phase 1 fx layer + /asymmetry raw distances (verdict stripped)
- c1032b8 DB snapshot pre target/stop fill

**17 target/stop UPDATEs** via framework empirique :
- c5: stop=-25%, target=+70% (with L5 metrology cyclical mod=-20%)
- c4: stop=-20%, target=+60% (L1 litho mod=-22%, HBM cyclical mod=-25%)
- c3: stop=-18%, target=+50% (story stock mod=-25%, defense low vol mod=-15%)
- 4 orphans c1 (AMD, GOOGL, SAF.PA, TSLA) SKIPPED → review J+30 = 2026-06-16

**Empirical insight Day 5 evening v3** : user identified confirmation bias
in /asymmetry verdicts (STRONG_RUN/FAVORABLE auto-derived from user's own
framework = tautology on day-1 logging). Stripped icons + labels. Kept
raw distances only. Path 5/6 valuable insight.

---

## 21 PF positions empirical mapping (16/05 logged, target/stop filled 16/05 evening)

| Ticker | Conv | Entry | Stop | Target | Current | Status |
|---|---|---|---|---|---|---|
| 6920.T Lasertec | 5 | €208 | €167 (-20%) | €354 (+70%) | €210 | computed ✅ |
| 000660.KS SK Hynix | 4 | €1043 | €782 (-25% HBM) | €1669 (+60%) | €1075 | computed ✅ |
| 4063.T | 4 | €38.5 | €30.8 (-20%) | €61.6 (+60%) | €38.8 | computed ✅ |
| 7011.T Mitsubishi HI | 4 | €22.1 | €17.7 (-20%) | €35.4 (+60%) | €22.3 | computed ✅ |
| ASML.AS | 4 | €1309 | €1021 (-22% L1) | €2094 (+60%) | €1307 | computed ✅ |
| BESI.AS | 4 | €261 | €203 (-22% L1) | €417 (+60%) | €262 | computed ✅ |
| COHR | 4 | €348 | €278 (-20%) | €557 (+60%) | €328 | computed ✅ (-5.7%) |
| KLAC | 4 | €1626 | €1301 (-20%) | €2602 (+60%) | €1548 | computed ✅ (-4.8%) |
| SNPS | 4 | €438 | €351 (-20%) | €701 (+60%) | €431 | computed ✅ |
| SU.PA | 4 | €264 | €211 (-20%) | €422 (+60%) | €264 | computed ✅ |
| TSM | 4 | €359 | €287 (-20%) | €574 (+60%) | €347 | computed ✅ (-3.3%) |
| ALAB | 3 | €196 | €147 (-25% story) | €295 (+50%) | €200 | computed ✅ |
| AVGO | 3 | €378 | €310 (-18%) | €567 (+50%) | €365 | computed ✅ (-3.4%) |
| HO.PA Thales | 3 | €222 | €189 (-15% defense) | €333 (+50%) | €219 | computed ✅ |
| MRVL | 3 | €157 | €129 (-18%) | €235 (+50%) | €152 | computed ✅ |
| STMPA.PA | 3 | €52.5 | €43.1 (-18%) | €78.8 (+50%) | €52.8 | computed ✅ |
| TER | 3 | €306 | €245 (-20%) | €459 (+50%) | €290 | computed ✅ (-5.4%) |
| AMD | 1 | €386 | NULL | NULL | — | INCOMPLETE (orphan c1) |
| GOOGL | 1 | €345 | NULL | NULL | — | INCOMPLETE (orphan c1) |
| SAF.PA | 1 | €274 | NULL | NULL | — | INCOMPLETE (orphan c1) |
| TSLA | 1 | €381 | NULL | NULL | — | INCOMPLETE (orphan c1) |

---

## FX layer (Phase 1 R3 hardcoded, calibrated empirically 2026-05-16)

In `shared/prices.py:HARDCODED_FX_TO_EUR`:
- JPY 0.005467 (calibrated 6920.T 38410 JPY = €210)
- KRW 0.000591 (calibrated 000660.KS 1819000 KRW = €1075)
- USD 0.858 (calibrated TSM/TER vs broker)
- EUR/GBP/AUD/CAD/SEK/HKD/CNY hardcoded estimates

**Migration scope** : asymmetry._get_current_price → delegates to
shared.prices.get_current_price_in_eur. **Other modules NOT migrated yet**
(see Carry-forward S1).

---

## Carry-forward critical (next session)

### P1 — F1b S1 full replace scope (8 modules)
Migrate price fetch to `shared.prices.get_current_price_in_eur` :
- intelligence/morning_brief.py:244 (line 302 comment "currency mismatch")
- intelligence/price_monitor.py:185
- intelligence/learning.py:125
- intelligence/thesis.py:149
- intelligence/shadow_decisions.py (target_partial >= compare)
- shared/positions.py:158
- bot/handlers/positions.py:103 (uses get_current_price_eur)
- bot/handlers/portfolio_views.py:78 (uses get_current_price_eur)

**Empirical investigation first** : shared/prices.py:262 has existing
`get_current_price_eur` function (different from new line 104
`get_current_price_in_eur`). **Clarify dup before migration** to avoid
double API call. Likely one of them should be removed/aliased.

### P1 — F1b Phase 2 R1 (SQLite fx_rates table + daily cron)
Currently fx hardcoded in shared/prices.py. Upgrade to:
- Create `fx_rates` table (pair, rate, fetched_at, source)
- Add `refresh_fx_rates_job` cron 1x/day
- `get_fx_rate()` reads table with hardcoded fallback
- Add `/fx_status` handler

### P2 — 4 orphans c1 review J+30 (2026-06-16)
AMD, GOOGL, SAF.PA, TSLA → decide:
- Exit position (no target/stop needed)
- OR promote to c3+ with empirical target/stop

### P2 — Calibration tracking
Track if user's historical targets get hit/missed.
Surface meta-discipline: are framework assumptions empirically valid?
This addresses the philosophical defect identified Day 5 evening v3
(verdicts confirming user's own assumptions vs reality).

### P2 — Challenger layer
Compare user targets to analyst consensus when available
(e.g. ASML.AS target €2094 vs analyst high €1710 → flag stretch).

### P2 — Audit other LLM handlers for today_str
`/analyze_debate`, `/thesis_premortem` likely have same bug as /analyze
had (no today_str injection → Opus uses 2024 knowledge cutoff).

### P3 — Source coverage gap Japan/Korea/EU
Sources don't publish about intl tickers (deferred from Step 4 mission queue).

### P3 — 26 silent tickers per /journal audit
KPI #5 = 1/27 = 3.7%. AMD/AVGO/MRVL/GOOGL/MSFT/META have signals but
no decisions logged. User action: log decisions next session.

---

## Bot state at end of Day 5 evening v3

- PID 34990 alive
- Scheduler healthy (22 crons)
- 33 active theses: 17 computed + 4 incomplete (orphans) + 12 watch
- 189 tests passing
- mypy strict on 30 modules
- ruff 0 errors
- Cost trajectory: $15/mo projected (GREEN)
- KPI #2 timer: J+25 → 2026-06-10 (46 predictions auto-resolve)
- 7 handler UX-fixes Day 5: /brief v3.1, /digest v2, /portfolio v2.1,
  /thesis_health v2, /analyze today_str, /asymmetry verbose, /asymmetry strip

---

## Backups Day 5 evening v3

- data/backups/day5_final_20260516_172609.tar.gz (Day 5 morning close)
- data/backups/data_20260516_183722.tar.gz (post NVDA cleanup)
- data/backups/day5_evening_final_20260516_201028.tar.gz (Day 5 evening v3 final)
- docs/snapshots/theses_2026-05-16_post_cleanup.sql (post HPQ+Pharma)
- docs/snapshots/theses_2026-05-16_pre_target_fill.sql (pre 17 UPDATEs)

---

## Next session opening checklist

1. `cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate`
2. `ps aux | grep bot.main` (confirm PID 34990 still vivant)
3. Read this HANDOFF.md (it is canonical)
4. `git log --oneline -5` (verify HEAD = c1032b8)
5. `/asymmetry` empirique Telegram to see raw distances
6. Decide next priority: P1 (F1b S1 full replace) or P2 (calibration/challenger)

