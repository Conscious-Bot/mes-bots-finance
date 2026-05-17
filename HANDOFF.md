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


---

## Update 16 May 2026 ~20:45 KST — C1+C2 today_str fixes

**Commit cec0f41**: Fix /analyze_debate + /thesis_premortem today_str
anchor. Same systemic bug pattern as /digest + /analyze (Day 5 morning +
evening). 4 LLM handlers now anchored empirique.

**Day 5 final**: 51 commits total (HEAD=cec0f41), 9 handler UX-fixes,
fx layer calibrated, 17 target/stop filled, philosophical insight on
verdict confirmation bias.

**Bot state**: PID 35358 alive, scheduler healthy.

**Next session P1 priority**: F1b S1 full replace 8 modules OR
/risk_check today_str audit (5 min check).



---

## Day 6 close — 16 May 2026 17:35 KST (~5h session, +4 commits)

**HEAD**: dfb74e4 | **Tag**: day6-close

### Commits this session

1. **21b8fd5** fix(observability) scope C — 4 latent bugs Sprint 1.1 extraction
   - actual_date -> resolved_at (KPI #2 query)
   - ts -> timestamp (handler_calls drift)
   - target_date -> target date (kpi defensive)
   - full_exit -> full-exit (unpaired _ broke /kpi_status Markdown V1)
   - mypy narrowing if material == 0 or pct is None

2. **0963369** feat(prices) A1 canonical migration
   - 4 swaps get_current_price_eur -> get_current_price_in_eur (positions, portfolio_views)
   - Delete 74 lines legacy chain (shared/prices.py 289->215)
   - Root cause Day 5 "broker mismatch": silent FX fallback 1.0
   - Empirical: TSM EUR346.93 (-0.16%), 6920.T EUR209.99 (-0.005%)

3. **ed98573** feat(brief) A2-1 morning_brief fallback canonical
   - intelligence/morning_brief.py:244 yfinance native -> canonical EUR
   - Findings: theses.last_price NULL all samples (cache jamais peuple)

4. **dfb74e4** feat(brief) readable POSITIONS layout
   - Names from get_short_name + value total + EUR Unicode
   - Validated /brief @ 17:31
   - CANONICAL FORMAT: currency symbol > ASCII codes, total value > qty*price, names > tickers

### Empirical state end-of-session
- 21 positions EUR ~42.7K, 8 intl (.T/.KS/.AS/.PA)
- KPI #2: 1 resolu lifetime, 45 due 10-11 juin -> J+28 forecast 46 ON TRACK
- KPI #4: 0 panic sells GREEN (mais voir A2-2: faussement vert intl)
- 22 crons, 189 tests pytest, 30 modules mypy strict
- /portfolio /brief /health /kpi_status /handler_stats all clean

### Carry-forward PRIORITY NEXT SESSION

**γ2 A2-2 CRITIQUE (~45-60 min, priority 1)** — intelligence/price_monitor.py:173
p = prices.get_current_price(ticker)         (NATIVE price JPY/KRW raw)
if t["stop_price"] and p <= t["stop_price"]: (vs EUR-stored stop)

8 intl positions (28% book) triggers ne firent JAMAIS depuis Day 5 target fill.
KPI #4 dependance + alertes runtime cassees.
Fix surface = 1 ligne, MAIS audit store-at-rest serre pre-patch OBLIGATOIRE:
sqlite3 data/bot.db "SELECT ticker, stop_price, target_price, avg_cost FROM theses WHERE ticker LIKE '%.%'"

Verifier theses.stop_price EUR pour tous intl + test fake target avant deploy.

### Carry-forward A2-3/4/5/6 (chained, NOT batched per protocol §6)
- intelligence/learning.py:125 (KPI #3 Brier critical, return_pct dependency)
- intelligence/thesis.py:149 (comparison vs entry_price)
- intelligence/shadow_decisions.py (shadow variants)
- shared/positions.py:158 (DB layer audit complet)

### Architectural dette (P2, ~5-10h)
**shared/display.py canonical refactor** — single source of truth absent.
Currency symbol / ticker widths / price decimals / pct copy-pasted across 5+
handlers. Solution: format_price, format_position_line, format_currency_symbol,
format_pct. Migration: morning_brief, positions, portfolio_views, digest.

### Dettes mineures (accumulation, non-bloquant)
- KPI #5 semantique gap: decision events (position_buy/sell + reasoning + bias_tags) != thesis events. HANDOFF Day 5 "all theses logged = baseline" imprecis.
- bot_state.bot_start_ts stale (uptime 123h vs restart frais)
- /kpi_status Overall undercount ("TIMER" string match misses "ON TRACK")
- pyproject.toml 25 unused module overrides
- shared/ticker_names.py:36,70 mypy no-any-return
- shared/positions.py:77,107 mypy dict|None return
- NVDA zombie "Unresolved decisions: 3"
- _stats_section "LLM today: $X" hardcoded $ (hors canonical format)
- format value:>6,.0f truncate si >EUR99,999 (non-issue current PF max EUR5K)

### Meta-lesson session (3 erreurs diagnostic Claude corrigees)
Empirique > pattern-matching:
1. "Tests 152 vs 189" — grep def test_ rate Hypothesis @given cases
2. "KPI #2 query cassee" — confusion theses.outcome_evaluated_at vs predictions.resolved_at
3. "Bot DOWN" — pgrep case-sensitive echoue sur Python.app macOS framework
Lecture profonde + validation second canal avant action.

### NEXT SESSION reopen sequence
1. cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate
2. ps aux | grep -i bot.main (filter -i OBLIGATOIRE, pas -f seul)
3. Read this Day 6 close section
4. PRIORITY γ2: A2-2 price_monitor.py canonical (CRITIQUE)
5. Pre-patch audit: SELECT theses.stop_price/target_price intl (verif store-at-rest EUR)
6. Patch 1 ligne get_current_price -> get_current_price_in_eur
7. Smoke test fake target intl avant deploy


---

## Day 7 close - 17 May 2026 ~04h KST (~3h session, +3 commits)

**HEAD**: e1e2e50 | **Tag**: day7-close

### Ships this session

1. **7aeac4a** fix(price_monitor) A2-2 canonical EUR thesis triggers
   - intelligence/price_monitor.py:185 swap NATIVE -> EUR
   - 8 intl positions (28% book) triggers ne firent JAMAIS depuis Day 5
   - KPI #4 maintenant fonctionnel pour intl (was faussement vert)
   - Empirical post-patch: theses_checked=33, alerts=0, fails=0

2. **f5a6300** fix(positions) A2-6 canonical EUR _enrich_with_live
   - shared/positions.py:158 - Day 6 commit 0963369 missed this helper
   - Bug latent: market_value=NATIVE x qty, pnl=NATIVE-EUR_avg, garbage intl
   - Path consumers: price_monitor alerts, bot/handlers/misc, scripts
   - Cross-path EUR consistency proof: smoke IDENTICAL Day 6 /brief @ 17:31

3. **e1e2e50** chore(types) eta3 mypy cleanup
   - price_monitor.py:239 + positions.py:77 + positions.py:107
   - cur.lastrowid + get_position(ticker) return types narrowed via assertion
   - Per CONVENTIONS.md "Erreurs explicites"
   - mypy: 3 errors -> 0 sur les 2 fichiers

### Audit classification eps1 (carry-forward cleanup)

False alarms identifies + REMOVED Day 6 carry-forward:
- A2-3 learning.py:125 - pattern (curr-baseline)/baseline ratio NATIVE/NATIVE
  mathematically INVARIANT (currency cancels). PAS de bug.
- A2-4 thesis.py:149 - check_exit_request(current_price) recoit prix en param,
  zero prices.* calls dans thesis.py. Caller-dependent, pas bug local.
- A2-5 shadow_decisions.py - zero prices.* calls dans le file. Pas de bug.

Real bug confirme + patche: A2-6 positions.py:158 (threshold-based mix).

**Lesson learned pour futurs audits "canonical EUR migration"**:
- Ratio-based (p_t - p_0) / p_0 -> currency-INVARIANT -> no patch needed
- Threshold-based (p compared to EUR-stored value) -> currency-SENSITIVE -> patch

### Meta-rule session

Olivier directive Day 7: **default = option la plus complete**, pas de question
gamma/delta/eps/eta decision matrices au stop point. Garde-fou protocol Sec.6
maintenu: "plus complet" = clore session proprement, PAS scope creep refactor
non-borne.

### Empirical state end-of-session
- 21 positions EUR ~42.7K, 8 intl maintenant firing-eligible (vs jamais Day 5/6)
- KPI #2: 1 resolu lifetime, 45 due 10-11 juin -> forecast J+24 ON TRACK
- KPI #4: GREEN avec confidence accrue (mecanisme intl fonctionnel)
- 22 crons, 189 tests, mypy: 0 errors sur 16 modules strict-typed (vs 14 Day 6)
- Bot PID 38520 vivant

### Carry-forward Day 7 (clean state)

**Strategic (post J+30 KPI#2 resolution)**:
- USD canonical migration ~10-15h. Olivier decision Day 7: confirmed
  carry-forward, pas urgent. Lecture honnete: EUR canonical mieux pour usage
  perso francais + broker EUR reconciliation. USD justifie seulement si Path
  5/6 acquihire/Substack global devient driver principal. Reconsiderer
  post-track record measurable.

**Architectural (P2, ~5-10h)**:
- shared/display.py canonical refactor (format_price, format_position_line,
  format_currency_symbol, format_pct). Migration: morning_brief, positions,
  portfolio_views, digest, observability.

**Dettes mineures (accumulation, non-bloquant)**:
- pyproject.toml ~21 unused module overrides (single-file mypy noise)
- KPI #5 semantique gap (decision events vs thesis events imprecis)
- bot_state.bot_start_ts stale (uptime mismatch)
- /kpi_status Overall undercount ("TIMER" vs "ON TRACK" string match)
- NVDA zombie "Unresolved decisions: 3"
- _stats_section "LLM today: $X" hardcoded $ (hors canonical EUR display)

### NEXT SESSION reopen sequence
1. cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate
2. ps aux | grep -i bot.main (filter -i obligatoire)
3. Read this Day 7 close section
4. NO new priority urgent (3 critical bugs patched Day 7)
5. Si energie + temps: tackle shared/display.py architectural refactor (P2)
6. Sinon: observation phase active jusqu'au 10 juin 2026 (KPI #2 batch resolution)
