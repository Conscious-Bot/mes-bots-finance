# HANDOFF — mes-bots-finance

**Last refresh**: 17 May 2026 ~14:15 KST — Day 9 P3 closure complete (~10-11h cumulative session)
**Mode**: High Standard / Solidification + Observation phase (J-23 vers 10 juin 2026 KPI #2 batch resolution)
**Current commit**: 85440e4 (HEAD = origin/main, day9-close tag stable @ 52bd3a0)
**Bot state**: PID 41435 vivant, scheduler 23 crons active
**Tests**: 226 passing (218 prior + 8 new Hypothesis portfolio_metrics)
**Mypy**: 16 modules strict-typed (+ shared.portfolio_metrics Day 9)
**KPI #6**: wired Day 9 P3 (auto-flip GREEN/YELLOW/RED post-J+365 = 10 mai 2027)

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


---

## Day 8 close (17/05/2026 ~04h45 KST, ~3h session)

**HEAD**: 7c6d9a0 | **Tag**: day8-close

### Ships this session (5 commits + B.4 NO-OP)

1. **ddced97** feat(display) Phase A — shared/display.py centralized canonical API
   - Currency StrEnum + CANONICAL_FINANCE=EUR, CANONICAL_BILLING=USD constants
   - Primitives: format_money, format_finance, format_billing, format_pct,
     format_pnl_pct, format_position_line, format_brief_position_line,
     format_aggregate_line
   - 29 Hypothesis property-based tests, currency-agnostic invariants
     (assert against CANONICAL_FINANCE.value, not hard-coded "€")
   - UX fix: format_pct normalizes -0.0 and round-to-zero -> "+0.0%" (caught
     by Hypothesis edge case, prevented "-0.0%" production artifact)
   - mypy strict override added for shared.display

2. **43940db** feat(display) Phase B.1 — intelligence/morning_brief.py
   - 3 sites: POSITIONS loop (3 branches -> 1 call), LLM cost line
   - REMOVED legacy `(check fx)` defensive guard `elif abs(pnl) > 200`
     (was masking legitimate +200% winners: PLTR 4x 2022, NVDA 3x 2023)
   - Empirical cross-check: Python smoke IDENTICAL Day 6 /brief @ 17:31

3. **38302bf** feat(display) Phase B.2 — bot/handlers/positions.py + 6 BUG FIXES
   - Workstream A (4 sites display migration): portfolio totals, worst3, best3
   - Workstream B (6 REAL BUGS $ -> EUR): trade-confirm messages rendered $
     symbol pour prices EUR-stored. Bought/Sold price, avg_cost, Realized PnL
     event + total. Latent bug shipped en production avant Day 8.
   - API EXTENSION: added `signed: bool = False` to format_money/finance/billing
   - +5 signed-behavior tests, baseline 213 -> 218

4. **237367a** feat(display) Phase B.3 — bot/handlers/portfolio_views.py
   - 11 sites, 3 fonctions (cmd_portfolio_sectors / _narratives / _drift)
   - L148 sector aggregate -> format_aggregate_line (direct drop-in, valide
     que API design Phase A etait empiriquement ground)
   - Net drift, Executed/Locked/Planned lines all canonical EUR
   - Empirical Telegram: /portfolio_sectors, /_narratives, /_drift OK

5. **B.4 digest.py** — NO-OP (zero display sites empirical scout)
   - L305 docstring "Cost: ~$0.025/call" = comment, pas display
   - Skipped directly to B.5

6. **7c6d9a0** feat(display) Phase B.5 — bot/handlers/observability.py
   - 14 patches (1 import + 13 sites LLM billing $)
   - 3 fonctions: cmd_health, _cost_format_trajectory, cmd_llm_costs
   - Migration vers format_billing() preserve $ via Currency.USD canonical
   - Future-proof pour flip canonical (storage migration + constant flip)
   - Phase B COMPLETE: tous handlers display-active migres

### Architecture insight: canonical centralisation definitive

Avant Phase B: chaque handler hardcoded `"€"`, `f"${value:.2f}"`, ad-hoc
formatters. Future USD migration aurait force distributed search-replace
sur ~50 sites avec risque de drift visuel.

Apres Phase B: un seul point de verite (`shared/display.py`). Future flip
EUR -> USD = (1) `CANONICAL_FINANCE = Currency.USD`, (2) storage migration
broker. Display layer auto-suit. ZERO modification dans handlers.

Invariant API: `format_finance(value)` assumes value already in
CANONICAL_FINANCE. Caller responsable storage-currency match.

### Empirical state end-of-session

- 21 positions EUR ~42.7K (unchanged Day 7)
- 6 commits cumules (Phase A + B.1 + B.2 + B.3 + B.5)
- 218 tests passing (vs 189 Day 7, +29 Phase A property-based)
- mypy 0 errors sur 17 modules strict-typed (vs 16 Day 7, +shared.display)
- ruff 0 errors
- Bot PID 39396 healthy, 22 crons schedules, 239 tickers
- 6 REAL BUGS fixed inline (Phase B.2 trade-confirm $ -> EUR)

### Carry-forward Day 8 (clean state)

**Phase B finition (next session first-ship, ~30min)**:
- B.2.5 position line `bot/handlers/positions.py` L221-226 migration vers
  format_position_line. Design decision: `pos["conv_str"]` pre-formatted vs
  format_position_line attend raw conviction. Choix: expose raw conviction
  dans pos dict OU adjust signature. Frais first-ship next session.

**Data hygiene (empirical Day 8 obs, non-bloquant)**:
- Sector flatten bug `_build_ticker_to_sector()` rend "coresemiscore",
  "extsemissupporting" au lieu de "core/semis_core", "ext/semis_supporting".
  Cosmetique /portfolio_sectors output.
- Narrative tagging gap: 100% positions "untagged" dans /portfolio_narratives.
  positions.notes pas peuplee avec narrative tags. Data hygiene, pas display.

**Dettes accumulees (carry Day 7 -> Day 8, non-bloquant)**:
- pyproject.toml ~21 unused module overrides
- KPI #5 semantique gap, bot_start_ts stale, /kpi_status undercount
- NVDA zombie "Unresolved decisions: 3"
- shared/ticker_names.py:36,70 mypy no-any-return
- {value:>6,.0f} truncate >€99,999 (non-issue, current PF max ~€5K)

**Strategic (post J+30 KPI#2 resolution)**:
- USD canonical migration. Olivier confirmation Day 7: pas urgent, EUR mieux
  usage perso francais + broker EUR reconciliation. Reconsiderer post-track
  record measurable.

### Lessons learned cumulees Day 8

1. **Defensive guard `abs(pnl) > 200` REMOVED** (Phase B.1). Etait suppose
   detecter fx mismatch but masquait des legitimate winners 2x+. Removed
   pour eviter UX worse-than-the-bug-it-tries-to-prevent.

2. **format_pct UX `-0.0` normalization** (Phase A). Hypothesis property-based
   test caught edge case. Production-quality polish via fuzz testing > eye
   review.

3. **format_aggregate_line direct drop-in L148** (Phase B.3). API designed
   Phase A empirically mirroring sector pattern. Confirms design Phase A
   wasn't speculative.

4. **Bash inline `#` interpreted as path** (today's gates). `git log A..HEAD
   # comment` -> "fatal: ambiguous argument '#'". Recurring zsh lesson:
   `interactive_comments` not active inline. Use `;` separator or `||true`.

5. **6 latent bugs fixed Phase B.2 trade-confirm $ -> EUR**. Avant Phase B
   ces bugs etaient invisibles (`$` rendered but on EUR-stored values).
   Migration force-cast displayed correctly. Canonical centralization expose
   l'inconsistance qu'ad-hoc cache.

### NEXT SESSION reopen sequence

1. cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate
2. ps aux | grep -i bot.main (filter -i obligatoire pour macOS Python.app)
3. Read this Day 8 close section
4. **First-ship recommended**: B.2.5 position line migration (~30min frais).
   Phase B truly 100% complete apres ca.
5. Sinon: observation phase active jusqu'au 10 juin 2026 (KPI #2 batch
   resolution = 45+ predictions due)
6. Si KPI #2 GREEN post-resolution -> ADR 001 PIT bitemporal Phase 1
   implementation trigger


---

## Day 9 close (17/05/2026 ~14h KST, ~7h session split Sprint 1+2+3)

**HEAD**: 9412bd4baf6e072459e128b3743756afc1629840 | **Tag**: day9-close

### Sprint 1 (~1h30): alpha + beta + recovery + alpha2 + beta2
3 protocol failures Sprint 1 (ruff RED shipped, WARN ignored, carry-forward
dette mentioned but not fixed inline). Lessons captured CONVENTIONS Section 16.

- ca89ff3 fix(uptime) alpha v1: bot_start_ts update on restart
- c220a0b fix(kpi) beta v1: emoji classifier KPI #2 ON TRACK + PROJECTED BREACH
- f75f2f9 fix(main) hotfix: missing datetime import (ruff F821 caught but shipped)
- 9eced50 style(main) cleanup: isort I001 merge datetime imports
- f27335a fix(observability) alpha2 + beta2: UTC end-to-end + KPI N/A bucket

Net: 2 ships reels (alpha + beta) + 3 self-correction commits.

### Sprint 2 (~45min): delta + epsilon (discipline clean, no recovery)
- 629e443 fix(portfolio_sectors) delta: Telegram Markdown italic bug in sector labels
- 9d5136a fix(kpi5) epsilon: title scope refinement + inline criteria docstring
- DB hygiene: DELETE FROM decisions WHERE id=7 (test data row, backup
  pre_kpi5_delete_20260517_133157.db)

### Sprint 3 (~30min): zeta (discipline clean)
- dbe695b fix(portfolio_narratives) zeta: escape _ in narrative display
- DB hygiene: 21 theses backfilled with sector_thesis_id via path alpha
  4-bucket mapping editorial:
  - AI_COMPUTE_2026          : 14 positions (semis + AI infra)
  - ELECTRIFICATION_2026     :  2 positions (7011.T, SU.PA)
  - EU_DEFENSE_2026          :  1 position (HO.PA)
  - ORPHAN_C1_REVIEW_J30_2026:  4 positions (AMD, GOOGL, SAF.PA, TSLA)
  Backup: pre_zeta_backfill_20260517_134038.db

### Empirical state end-of-Day-9
- 21 positions all narrative-tagged + sector-tagged
- KPI #5 N/A bucket (post-delete row 7) -> enforcement removed
- KPI #2 ON TRACK correctly classified green
- KPI #3-6 all correctly bucketed
- /health uptime returns positive minutes (UTC end-to-end)
- /portfolio_sectors + /portfolio_narratives Markdown safe (escape _)
- /kpi_status Overall sum to 5 (no silent undercount)
- 218 tests preserved across all 8 commits
- mypy 0 errors on 18+ modules strict-typed
- Bot PID 41102 healthy

### Carry-forward Day 10

**DEFER strict (no action this session)**:
- bot/main.py 2428 LOC split (session architectural dediee frais)
- USD canonical migration (post J+30 = 10 juin 2026)

**Telemetry verified end-of-Day-9** (post-P2 investigation) :
- handler_calls table 155 rows, /handler_stats Pareto curve works
- Top-10 handlers (brief/digest/portfolio/health/help/asymmetry/find/
  kpi_status/analyze/handler_stats) = 60% calls
- 47 unique used / 73 registered -> ~26 zero-use 30d (telemetry fenetre
  effective 4-5j, triage premature)
- bot.log silent = by design (telemetry DB-side, no log spam)
- Lesson 8 channel verification added CONVENTIONS Section 16

**Eligible quick wins Day 10 (low risk, scope-bounded)**:
- (KPI #6 wiring CLOSED Day 9 P3 - see closure section below)
- zeta extension: finer narrative granularity if desired (SQL UPDATE on
  demand, no code change required)
- Day 9 carry: /handler_stats Pareto curve validation post-telemetry-fix

**Observation phase active**: KPI #2 timer J-23 vers 10 juin 2026 (45+
predictions batch resolution).

### NEXT SESSION reopen sequence
1. cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate
2. ps aux | grep -i bot.main (-i obligatoire macOS Python.app)
3. Read this Day 9 close section
4. Apply CONVENTIONS Section 16 discipline strictly (no protocol failures)
5. Observation phase: passive monitoring + low-risk carry-forward only


---

## Day 9 P3 closure - KPI #6 wired (17/05/2026 ~15h KST, ~1h30 session)

**Status**: Day 9 P3 closed, 2 commits post-day9-close tag.

### Phase A - new shared/portfolio_metrics.py + 8 tests
- parse_eur_invested(): regex extraction of legacy_import_2026_05_15 tag
- compute_portfolio_return_eur(): aggregate EUR P&L via canonical
  Day 7 get_current_price_in_eur() + list_positions() accessors
- fetch_benchmark_return_eur(): SPY/QQQ USD + EURUSD=X -> EUR-equivalent
  return (FX-adjusted, correct for cross-currency)
- compute_kpi6(): orchestrator returning canonical schema dict
- 8 Hypothesis property-based tests (parse_eur_invested invariants)
- mypy strict override added (16 modules now enforced in CI - portfolio_metrics included)

### Phase B - bot/handlers/observability.py wire
- Drop hardcoded "NOT IMPLEMENTED" stub at lines 320-326
- Replace with try/except compute_kpi6() + graceful fallback dict
- Schema-aligned: {title, target, current, status, enforcement}

### Empirical state post-Phase-B (Telegram verified PID 41435)
KPI #6 transitions: "NOT IMPLEMENTED" -> "INSUFFICIENT" (semantic upgrade)
- Pf -1.30% | SPY-eur +2.05% (delta -3.3pp) | QQQ-eur +3.04% (delta -4.3pp)
- 1d window, 21/21 positions priced (100% live EUR coverage)
- Overall: 2 GREEN | 0 YELLOW | 0 RED | 3 N/A (sum to 5)
- Auto-flips GREEN/YELLOW/RED post-J+365 (10 mai 2027)

### Math FX validation
EUR investor in USD asset: (USD_t/EURUSD_t) / (USD_0/EURUSD_0) - 1.
Currency invariance argument applies only WITHIN single currency, NOT
across cross-currency benchmark. Day 7 canonical get_current_price_in_eur()
handles portfolio side. yfinance EURUSD=X = USD per 1 EUR.

### Gates Phase A + B
- ruff 0 errors all files
- mypy 0 errors on portfolio_metrics + observability
- pytest 226/226 passing (218 prior + 8 new Hypothesis)
- import bot.main OK
- bot restart clean PID 41435, scheduler 23 crons
- Telegram /kpi_status empirical visual GREEN

### Carry-forward Day 10 (post-P3)
- DEFER strict: bot/main.py 2428 LOC split (architectural session)
- DEFER strict: USD canonical migration (post J+30 = 10 juin 2026)
- Q3 (post-J+90): dormant-handler triage (telemetry mature)
- KPI #6 auto-transitions post-J+365 (10 mai 2027)

### NEXT SESSION reopen
1. cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate
2. ps aux | grep -i bot.main
3. Read this Day 9 P3 closure section
4. Observation phase active jusqu au 10 juin 2026 (KPI #2 batch resolution)


---

## Day 9 audit H1 verdict (17 May 2026, closure by-design)

**Audit question** : 22 position_events buys vs 2 decisions rows → KPI #5 regression ?

**Empirical analysis** :
- 21 Day 5 fills (2026-05-15) ALL tagged `legacy_import_2026_05_15` → bulk
  SQL import bypassed cmd_position_buy Telegram handler → log_decision
  NOT called (expected, architectural)
- 1 Day 2 buy (2026-05-13 NVDA "test b2 flag off") = Phase B5 Ship 5
  test artifact (Day 2 marathon)
- 2 existing decisions rows : decision_type = `no_action_flag`
  (test_manual_override + retest credit fix Day 2 marathon)
  -> meta-decisions, NOT entry/scale/exit, excluded from KPI #5 trade scope

**Phase B5 chain verified wired** in bot/handlers/positions.py:
- L280 storage.log_decision (Phase B5 Ship 5 hybrid integration)
- L303 storage.log_decision + L319 bias_tagger.auto_tag_biases
- L362 storage.log_decision + L378 bias_tagger.auto_tag_biases
- _portfolio_journal_ctx helper providing price + regime + credit + thesis_id

**Verdict** : KPI #5 `🔍 NO MATERIAL DECISIONS 30d` = informative N/A
correct. Chain will engage at first real /position_buy Telegram invocation.
Zero such invocations in 30d window = explained by user workflow (all fills
via bulk import Day 5).

**No code change**. Audit closed.

### Deferred non-debts (rationale documented for future audits)
- L1 TZ ambiguity in opened_at parsing: precision impact <0.1% on 365d
  KPI #6 windows, defer to PIT migration ADR 001 implementation
- M4 telemetry typo pollution in handler_calls: cosmetic noise (porfolio,
  portfolio_drive, healthy registered as distinct handler_name), defer
  to Q3 dormant-handler triage when telemetry mature
- M2 SMH/sectoral benchmark for KPI #6: new feature scope, not debt
- L4 KPI #1 uptime wire to /kpi_status: new feature scope, not debt


---

## Day 10 close (17 May 2026 ~12h KST, ~9h session)

**E REFACTOR COMPLETE** — bot/main.py architectural split shipped + empirically validated via /help Telegram.

### Empirical state Day 10 close

| Métrique | Day 9 close | Day 10 close | Δ |
|---|---|---|---|
| bot/main.py LOC | 2428 | **793** | -1635 (-67%) |
| cmd_ defs in main.py | 73 | **0** | -73 |
| handler modules bot/handlers/ | 6 | **22** | +16 |
| Tests passing | 239 | 239 | (0 régression) |
| failure_modes FMs | 5 | **7** | +FM-6 +FM-7 |
| CONVENTIONS Section 16 | 11 | **13** | +R11 +R12 +R13 |
| Commits Day 10 | — | **8** (656198b → 8537a10) | — |
| Tags pushed | day9-close | + day10-close | — |

### Ships closed Day 10

- **E batch 1** `7f32335` : cmd_ping + cmd_help → system.py NEW, cmd_insiders → signals_filings.py
- **E polling robustness** `cbc3519` : `app.run_polling(drop_pending_updates=True)` baked
- **E batch 2+3** `b134bf9` : cmd_digest → digest.py NEW, cmd_regime + cmd_calendar* → regime_calendar.py NEW, cmd_credibility + cmd_predictions + cmd_resolve_now + cmd_feedback → predictions.py NEW
- **E fixups** `767f141` + `5988705` + `6844012` : CAPS const auto-detection bug + config import + assignment-vs-reference regex
- **E batch 4 FINAL** `1d57d9a` : cmd_thesis_* + cmd_exit* + _parse_thesis_template (sync helper) + THESIS_TEMPLATE → thesis_crud.py NEW
- **Day 10 close docs** `8537a10` : FM-7 + R13

### Empirical validation
- `/help` Telegram → 65 commands listés depuis extracted modules = chain entière batches 1+2+3+4 fonctionnelle
- `/regime` mid-session served from bot/handlers/regime_calendar.py (bot 44229)
- Bot 44580 single instance post-cleanup, Conflict: 0, scheduler 22 crons up

### Discoveries Day 10

**FM-7 macOS pkill case-sensitivity** (~2h diagnostic detour) :
- macOS Python framework binary = `/Library/Frameworks/Python.framework/.../Python` (capital P)
- `pkill -f "python.*"` lowercase pattern ne match jamais → ghost processes accumulés
- 10 zombies bot.main vivants en simultané toute la session, tous polling Telegram = **vraie cause** des Conflict cascades (PAS retry behavior comme j'avais hypothèsé initialement)
- Fix : `pkill -9 -if "python.*bot.main"` ou pattern `[Pp]ython`
- Token regen #1 mid-session = **inutile** sur ce symptôme (10 zombies tapaient le même token quoi qu'il arrive)
- Detection canon : `lsof bot.log` montre N writers même si pgrep `(clean)`
- Documenté FM-7 + CONVENTIONS R13

**Observation freeze lifted Day 10** avec user signoff explicite pour exécuter sprint E. Sprint 1.2 (Consolidation V4 65→18 handlers, plan `docs/personal/handlers-consolidation-plan.md`) reste post-J+28 = post 10 juin 2026.

**AST extraction script évolué 4 itérations** : auto-import detection → R11 annotation stripping → CAPS const auto-detection (regex assignment vs name reference, R12) → sync FunctionDef support (batch 4 helper). Script réutilisable pour futurs splits architecturaux.


### Latent debt post-Day-10 (Day 11 17/05/2026)

- `bot/handlers/*.py` (22 modules) utilisent signatures untyped `def cmd_x(update, ctx):` per R11 stripping → mypy ne flag pas les `update.message.reply_text` sans guard → runtime risk None-deref si message manquant. Cleanup possible : ajouter les modules au mypy strict-typed override + annotate. Effort ~6h. Bénéfice : type safety end-to-end sur la chaîne handler. Trigger candidat : post J+30 ou après 1st runtime None-deref encountered.
- `intelligence.materiality:291` FIXED Day 11 (similar: float = 0.0).

### Carry-forward post-Day-10

E refactor **RÉSORBÉ** (no longer deferred). Sprint queue restante :

- **J+24 → 10 juin 2026** : KPI #2 batch resolution (45+ predictions cluster, target ≥5 résolues, timer non-négociable)
- **Post-June-10** : Sprint 1.2 Consolidation V4 (65→18 handlers, élagage informé par /handler_stats 30j+ empirique)
- **F** USD canonical migration (strategic, post-J+30)
- **B** L4 KPI #1 uptime wire to /kpi_status
- **B'** handler_calls.is_typo column + migration rows existants
- **A** M2 SMH/sectoral benchmark wire KPI #6
- **C** dormant-handler triage post-telemetry mature
- **Pre-existing cleanup** : main.py 3× union-attr `update.message`, intelligence/materiality.py:291 float→int (P3, not blocking)
- **ADR 001 PIT bitemporal** : trigger = KPI #2 GREEN OR 1er recal mensuel post-juin


### Day 11 lessons (R14 self-violation + R18 added)

**R14 self-violation** : codifié Day 10 ("name exists check = assignment regex JAMAIS substring"), violé Day 11 dans le patcher python pour SMH benchmark insertion (`if '_BENCHMARKS' not in new_src` → False car nouveau corps de fonction contenait référence → insertion skip silencieuse → commit broken). Fix forward 1 commit après.

**R18 added** : tout bash qui git commit du code DOIT gate-abort sur RED. Le pattern Day 11 (4 ruff + 1 mypy + 7 pytest fails → commit quand même) prouve que les gates seules ne suffisent pas sans abort mechanism. Pattern : `set -e` ou `cmd || { echo X; exit 1; }`.

**Méta-leçon** : codifier une règle ≠ la suivre. Re-lire R14-R17 au début de chaque patcher Python est obligatoire. Ne pas trust la mémoire en-context.

### Lessons learned Day 10 (time-wasters codifiés)

Anti-patterns identifiés et documentés pour ne PAS reperdre du temps dessus :

| Time-waster | Cost | Codifié dans |
|---|---|---|
| pkill case-sensitivity macOS | ~2h | FM-7 + R13 |
| pgrep/ps grep menteurs post-kill | (corollaire) | FM-8 |
| Token regen comme "fix" Conflict | ~30min + BotFather social cost | R17 |
| AST extraction substring vs assignment | 3 fixup commits, ~30min | R14 |
| Heredoc + zsh `#` | cosmetic noise | R15 |
| Restart cascade escalation sans forensics | ~1h amplifié | R16 |
| Claude solution-first sur symptômes weird | ~2h amplifié (cumulé R16+R17) | R17 |

**Anti-pattern méta canonique** : *quand le 1er restart après "fix" produit même symptôme, le fix N'A PAS marché. Pas la peine de répéter en plus aggressive. Pivot forensics.*

Lecture obligatoire pour Claude reopen futur : CONVENTIONS Section 16 R13→R17 + failure_modes.md FM-7+FM-8. Ces 5 rules + 2 FMs couvrent l'intégralité des erreurs opérationnelles Day 10.

### NEXT SESSION reopen

1. `cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate`
2. `pgrep -if "python.*bot.main"` (**case-insensitive obligatoire** post FM-7)
3. `tail -120 HANDOFF.md` (lire cette section Day 10 close)
4. Observation phase active jusqu'au 10 juin 2026 (KPI #2 trigger)
5. Optional : alias `kbot='pkill -9 -if "python.*bot.main"'` dans `~/.zshrc` pour discipline future


## Day 11 R18 violations post-mortem (18 May 2026 KST)

**Two broken commits landed in the Day 11 sprint**:

1. **7f7bb7d** (SMH benchmark wire) — R14 violation: `_BENCHMARKS not in src`
   substring check returned False because new function body contained
   `for tk in _BENCHMARKS:` as reference → constant declaration skipped
   silently → 4 ruff + 1 mypy + 7 pytest failures. Fixed in 6233e95
   (R14 strengthened with `re.search(r'^NAME\s*[:=]', src, re.MULTILINE)`).

2. **f2b23fe** (Batch 2 USD canonical) — `ruff --fix` auto-removed unused
   imports `get_current_price_in_eur`/`_usd` from `shared/portfolio_metrics.py`
   after parametric refactor. Tests in `TestComputePortfolioReturnEur`
   monkeypatched the now-absent module attributes → 6 AttributeError test
   failures. Fixed in 12973a1 (mocks redirected to
   `shared.portfolio_metrics.get_current_price_in` with 2-arg signature).

**Common root cause**: shipping bash gate pattern
`(set -eo pipefail; ... pytest -q 2>&1 | tail; git commit; git push) || echo`
did NOT abort on test failure under zsh. R18 was process *intent* but its
*implementation* was unreliable. See FM-9 + R19 in failure_modes.md /
CONVENTIONS.md for mitigation.

**Process discipline going forward (Batches 3-5)**:
- Every shipping bash uses R19 explicit gate pattern
- Defect rate tracking: pre-R19 = 2/7 commits broken (28%). Target post-R19 = 0%
- Belt-and-suspenders: `pytest -q | tail -3` immediately after every push

**Day 11 final stats (post-fix)**:
- 9 commits since Day 10 close (e8c81cf base):
  - e8c81cf (materiality), 7ecb10c (KPI #1), 7f7bb7d (broken SMH),
    6233e95 (fix SMH), f3dc54c (mypy floor), 08df457 (ADR 004),
    e6fed9d (Batch 1 prices), f2b23fe (broken Batch 2), 12973a1 (fix tests),
    + this commit (R19 codify)
- 270 tests passing, 0 mypy errors codebase-wide
- USD migration: ADR 004 documented, Batches 1-2 of 5 shipped
- Bot still on PID 44580 cached f3dc54c (will pick up new code on next restart)

**Remaining Day 11 work (or carry-forward)**:
- Batch 3 — `shared/positions.py _enrich_with_live` + `intelligence/price_monitor.py` USD canonical (~1h)
- Batch 4 — display layer: bot/handlers/positions.py + portfolio_views.py + find.py ($ primary, € secondary) (~1h)
- Batch 5 — `intelligence/morning_brief.py` + /digest /brief USD primary (~45min)
- Restart bot post-Batch-5 (or earlier for staging if needed)


## Day 11 close (18 May 2026 KST)

**Final stats**: 14 commits since Day 10 close (e8c81cf), 270 tests, 0 mypy errors, R19 holding 8 commits since 12973a1.

**USD migration ADR 004 status**:
- Batch 1: shared/prices.py foundation (e6fed9d)
- Batch 2: portfolio_metrics + KPI #6 USD primary (f2b23fe + fix 12973a1)
- Batch 3A: positions._enrich_with_live parametric (5d04a25)
- Batch 3B: DEFERRED post-J+30 (price_monitor thesis triggers, KPI #4 protection)
- Batch 4A: cmd_portfolio (911dcfd) — repo state: USD values, AWAITING Path γ display retrofit
- Batch 4B: _compute_book_market_value (f262c71) — same, AWAITING Path γ
- Batch 4C: find.py format helpers (5153982) — CORRECT, uses explicit f-strings
- Batch 4D candidate: cmd_portfolio_drift (FM-11, deferred post-J+30)
- Batch 5: morning_brief NOT shipped (would have same coupling)

**Critical audit (this close commit)**: shared/display.py has CANONICAL_FINANCE
= Currency.EUR + explicit doctrine. Batches 4A/4B values are USD but pass
through format_finance internally -> display lies `€{USD_value}` if restarted.
Path γ fix planned Day 12.

**Bot status**: PID 44580 still on cached f3dc54c. **DO NOT RESTART** until
Day 12 Path γ lands. Restart now = broken display.

**Day 12 plan (Path γ — currency kwarg extension)**:

1. display.py extension (~30min): add `currency: Currency | None = None` kwarg
   to format_finance + format_position_line + format_aggregate_line +
   format_brief_position_line. Default CANONICAL_FINANCE. Backward-compat.

2. 4A retrofit (~15min): cmd_portfolio passes `currency=Currency.USD` to
   format_position_line.

3. 4B retrofit (~15min): cmd_portfolio_sectors + cmd_portfolio_narratives
   pass `currency=Currency.USD` to format_finance + format_aggregate_line.

4. Batch 5 (~45min): morning_brief _positions_top5_section USD canonical
   via get_current_price_in_usd. format_brief_position_line gets
   `currency=Currency.USD`. Audit _stats_section for any pre-existing issue
   (Day 6 memory mentioned hardcoded \$).

5. Restart + smoke (~15min): kbot alias + nohup + Telegram smoke
   /portfolio /portfolio_sectors /portfolio_narratives /brief /find ASML.AS.
   Confirm USD primary + EUR secondary where applicable + FM-10 coherent pnl_pct.

6. Tag day12-close (~5min).

Estimated Day 12: 2-2.5h single sprint.

**Process discipline lessons codified Day 11**:
- FM-9: zsh subshell pipefail unreliability (post commit 12973a1, R19 mitigation)
- R20: display-layer forensic before centralized formatter refactor (this close)

**Carry-forward post-Day-11**:
- Batch 3B price_monitor (post-J+30)
- FM-10 unrealized_pnl currency mix (partial fix in 4A/4B scope only)
- FM-11 cmd_portfolio_drift SQL aggregation currency mix (Batch 4D, post-J+30)
- Day 12 Path γ implementation (above)

**KPI timers**:
- KPI #2: J-23 to 10 juin 2026 batch resolution (45+ predictions due)
- KPI #6 USD primary: live since Batch 2 (commit f2b23fe), 0 panic sells, INSUFFICIENT (need 365d)


---

## Day 12 close — 2026-05-18 ~16:19 KST (Path γ COMPLETE + smoke verified)

**HEAD**: aa6976e  •  **Tag**: day12-close  •  **Bot PID**: 55387 (cached aa6976e)
**Day 12 commits**: 7 (since day11-close 7090820)

### Day 12 commit chain
- 4ceb084 — feat(display): Step 1 — currency kwarg on 4 formatters
- 094f33d — fix(display+lint): Step 1.5 corrective + R19 v3 + R14 v2
- a9c3adf — feat(handlers): Step 2A retrofit (PARTIAL, 3 patches missed silently)
- 2ef6c73 — fix(handlers): Step 2A.5 R19 v4 codify (FM-12 swallowed abort)
- c4eb24e — fix(handlers): Step 2A.6 REAL patches + FM-12 + R19 v5
- a25ed81 — feat(brief): Step 2B morning_brief Batch 5 USD + FM-10 fix
- aa6976e — fix(positions): Step 2D cmd_portfolio summary USD coverage gap

### Ships (architectural)

**display.py Path γ infrastructure** (Step 1+1.5):
- format_finance, format_position_line, format_aggregate_line, format_brief_position_line all extended with `currency: Currency | None = None` kwarg
- CANONICAL_FINANCE=EUR default preserved (backward compat)

**Handler retrofit USD primary** (Steps 2A.6, 2B, 2D):
- /portfolio: 4 markers (Book + Cost + PnL summary + format_position_line)
- /portfolio_sectors: 2 markers (header + format_aggregate_line)
- /portfolio_narratives: 2 markers (header + per-narrative)
- /brief: 1 marker + FM-10 fix in _positions_top5_section (avg_cost native→USD, last_price EUR→USD, coherent pnl_pct)
- Total: 9 USD activation markers across 3 files

### Process discipline R19 stack consolidated

- **v2 (Day 11)**: pytest + mypy explicit rc check (FM-9 mitigation)
- **v3 (Day 12 Step 1.5)**: ruff added to gate set
- **v4 (Day 12 Step 2A.5)**: AST function-scoped marker count gate (semantic completeness)
- **v5 (Day 12 Step 2A.6)**: explicit rc check applied to ALL commands incl python3 heredocs (FM-12 mitigation)

R14 v2 reinforced after Step 1 substring contamination. R20 (display-layer forensic) preserved.

### Failure modes added

- **FM-12 (Day 12)**: zsh `set -e` bypass on python3 heredoc commands in subshells. Same family as FM-9 (pipefail) but broader. Mitigation = R19 v5 explicit rc check for ALL commands.

### ADR 004 USD canonical migration

✅ COMPLETE for daily-usage handlers (smoke verified Olivier 09:13+ KST):
- /portfolio: $ summary line + per-position line — GREEN
- /portfolio_sectors: $ header + sector lines — GREEN
- /portfolio_narratives: $ header + narrative lines — GREEN
- /brief: $ top5 + coherent pnl_pct FM-10 fix — GREEN
- /find ASML.AS: $ primary + € secondary — GREEN
- /portfolio_drift: € symbol (negative test, FM-11 deferral) — GREEN

🚧 DEFERRED post-J+30 (J-22):
- **Batch 3B**: price_monitor.py thesis triggers (KPI #4 protection, DB threshold audit needed)
- **Batch 4D**: cmd_portfolio_drift FM-11 (target_eur DB column + SQL aggregation currency-mixed, 8 format_finance calls stay EUR — empirically validated unchanged)
- **FM-10 systematic**: cmd_position_buy / cmd_position_sell display NATIVE-currency values with €. Pre-existing JPY/KRW=€ inconsistency. Out of D11+12 scope. Native-display batch post-J+30.

### Empirical state Day 12 close

- Tests: 270 passing (Hypothesis property-based + integration + smoke)
- mypy: 0 errors on 16 strict-typed modules
- ruff: 0 errors codebase-wide
- Bot uptime: PID 55387 alive on aa6976e (rotated from 44580 at 09:13 KST)
- 0 Traceback/ERROR/CRITICAL post-init
- Telegram smoke 5/5 USD GREEN + 1/1 EUR deferral GREEN

### Carry-forward post-Day-12

- Batch 3B price_monitor (post-J+30, KPI #4 protection)
- Batch 4D cmd_portfolio_drift FM-11 (post-J+30)
- FM-10 systematic native-display batch (post-J+30, pre-existing JPY/KRW=€)
- Latent: bot/handlers/* untyped tree strict-typed override (~6h post-J+30)
- KPI #2 trigger: 10 juin 2026 (J-22, 45+ predictions cluster batch resolution)

### Next session reopen

1. `cd ~/mes-bots-finance && source venv/bin/activate`
2. `pgrep -if "python.*bot.main"` (expect PID 55387 or rotated)
3. `git log --oneline day12-close..HEAD` for any commits since
4. `tail -120 HANDOFF.md` for this Day 12 close + commits chain
5. Per CONVENTIONS.md Section 16: R19 v5 explicit rc check pattern for all discipline-critical bashes
6. Per ADR 004: Batch 3B/4D + FM-10 systematic deferred to post-J+30

KPI #2 timer: J-22 (10 juin 2026 = 45+ predictions cluster batch resolution).


---

## Day 12 extended (post day12-close) - 18 May 2026 evening KST

day12-close tag at 0183c88 remains canonical operational snapshot. This section
documents 7 post-tag commits within same calendar day (Bucket A + ADR narrative).

### Post-tag commits
- 1361efb chore(gitignore): bot.log rotation + patterns
- 57b9056 docs(readme): stale numbers refresh post Day 11+12
- f520bd7 docs(adr): ADR 005 process-discipline (with collision)
- db7213f fix(adr): rename 005 to 006 (collision corrective + lesson)
- 3ab76be fix(types/positions): Step C strict-typed + 20-error corrective
- 74bacd7 docs(adr): ADR 007 Bidirectional Thesis Tracker (RETROACTIVE)
- e207a1c docs(handoff): Day 12 extended section
- 7e18e14 docs(adr): ADR 008 LLM Cascade Architecture (RETROACTIVE)

### Bucket A status (Olivier directive: tout le bucket A doit etre fait)
- A.1 Cleanup debt: shipped (gitignore + .keep patterns)
- A.2 format_billing audit: stale memory note, no work needed (diagnostic confirmed)
- A.3 README polish: shipped (Conscious-Bot org + 270 tests + 12 FMs)
- A.4 Type hints bot/handlers/positions.py: 17th strict-typed module
- A.5 Handler integration tests: deferred multi-session
- A.6 Observation tooling: deferred multi-session

### Strategic ADRs added
- ADR 006 Process Discipline R19 v2-v5 stack: formalizes Day 11+12 lessons
- ADR 007 Bidirectional Thesis Tracker: RETROACTIVE, core mechanism since Day 2

### Path 5/6 narrative arc COMPLETE
ADR registry answers the three audit questions:
- What does this bot do uniquely? ADR 007 (bidirectional thesis tracker)
- How does it ship reliably? ADR 006 (process discipline R19 stack)
- How does it stay coherent? ADR 004 (USD canonical migration)
- How is it economically sustainable? ADR 008 (LLM cascade, 70% budget headroom)
Plus supporting infra ADRs (001 credibility, 002 universe, 003 targets, 005 schema).

### Discipline tally Day 11+12 final: 8 violations = 8 codifications
1. R14 violation Day 10 SMH = R14 v2
2. R14 v2 self-violation Day 12 Step 1 = reinforced (function-scoped AST)
3. R18 violations Day 11 x2 = R19 v2
4. R17 violation Day 11 (display.py audit miss) = R20
5. R19 v2 hole Day 12 (ruff missing) = R19 v3
6. R19 v3 hole Day 12 (semantic gate missing) = R19 v4
7. FM-12 Day 12 (zsh set-e bypass python3 heredoc) = R19 v5
8. ADR numbering collision Day 12 = mental checklist update

Each violation = durable system improvement. Path 5/6 defensibility tangible.

### Final empirical state at HEAD
- Tests: 270 passing
- mypy: 0 errors on 17 strict-typed modules (Day 12 close was 16, +1 via Step C)
- ruff: 0 errors codebase-wide
- ADRs: 8 total (001-008, no gaps)
- Failure modes: 12 documented (FM-1 to FM-12)
- Bot: PID 55387 alive on aa6976e (Step C type-only, no restart needed)

### Carry-forward post-J+30 (unchanged from day12-close)
- Batch 3B: price_monitor.py thesis triggers (KPI #4 protection)
- Batch 4D: cmd_portfolio_drift FM-11 (DB column + SQL aggregation)
- FM-10 systematic: cmd_position_buy/sell native-currency display batch
- bot/handlers/* tree strict-typed expansion (15+ modules remaining)
- Bucket A.5 handler integration tests + A.6 observation tooling
- KPI #2 trigger: 10 juin 2026 (J-22, 45+ predictions cluster batch resolution)

### Next session reopen
1. cd ~/mes-bots-finance && source venv/bin/activate
2. pgrep -if "python.*bot.main" (expect PID 55387 or rotated)
3. git log --oneline day12-close..HEAD for 8 extension commits
4. tail -200 HANDOFF.md for Day 12 close + extension sections
5. CONVENTIONS.md Section 16: R19 v5 + R14 v2 + R17 + R20 patterns
6. ADR 007 = canonical reference for product mechanism questions
7. KPI #2 timer: J-22 to 10 juin 2026

---

## Day 13 close — 19 May 2026 ~22h KST (10h+ session)

**HEAD**: 9cc907b (tag day13-close on this commit). 6 commits since e29a887.

### Ships (chronological)
1. `dfff980` feat(universe): +19 Bucket B align (asia_semis sub-group NEW)
2. `2622e39` feat(universe): +39 exclus tickers user-directed (watchlist override "less surface" philosophy break, J+30 review tagged in friction.md)
3. `f4fbfc1` feat(universe): +16 tier1 mega-caps B-16 strict
4. `abe7c23` docs: /risk_check + /analyze v2 roadmap (docs/risk_check_v2_roadmap.md, 10 improvements)
5. `d4925b3` feat(risk_check): P0 newsletter signal injection v1 [BROKEN: F821 get_conn + materiality_v2 column]
6. `c7e5ed0` fix(storage): get_conn -> db canonical context manager
7. `e29a887` fix(risk_check): P0 schema correction (materiality_v2/tier columns don't exist - decomposed v2 schema)
8. `7f9b759` docs: CONVENTIONS Lessons 12-14 + PROCEDURE_URGENCE case-insensitive flags
9. `9cc907b` feat(analyze): P0 extension /analyze + refactor build_signals_context_block to shared/storage

### Universe end state
313 tickers (23 core / 123 watch / 167 extended). Asia_semis sub-group added (Samsung 005930.KS, BYD 002594.SZ, CATL 300750.SZ, SoftBank 9984.T, Sony 6758.T). J+30 prune audit mid-juin per friction.md.

### P0 newsletter signal injection — VALIDATED end-to-end
- shared/storage.py: build_signals_context_block(ticker) public formatter
- intelligence/risk_manager.py: imports + calls shared helper (dropped 25 LOC local copy)
- intelligence/analyze.py: enriches data[newsletter_signals_block] in analyze_stock, renders RECENT NEWSLETTER SIGNALS section in build_prompt, adds NEWSLETTER SIGNAL CONTEXT axis in output template

Empirical validation /risk_check NVDA + GEV: LLM cited 4 of 5 injected signals (Stratechery Inference Shift, Chamath SpaceX-Anthropic 300MW, WSR weekly, Substack Photonics SuperCycle) and synthesized SUPPORTING vs CONTRADICTING in verdict reasoning. Closes the philosophical loop (PHILOSOPHY.md core principle): signals harvested -> decisional handler enriched -> bidirectional discipline output.

### Disasters + recoveries (3 violations, 3 codifications)

**Violation 1 (Lesson 12)**: R19 v5 plain `ruff check .` without `|| exit 1` allowed F821 to ship in d4925b3. Fixed c7e5ed0.

**Violation 2 (Lesson 13)**: Schema presumed (materiality_v2, tier columns). Empirical sqlite3 .schema reality: decomposed v2 = score INTEGER + materiality_boost REAL; sources has credibility only (tier derived dynamically S>=0.7/A>=0.5/B>=0.3). Fixed e29a887.

**Violation 3 (Lesson 14)**: macOS Python.app uses capital `Python` executable. `pgrep -f "python.*..."` silently misses since Day 5. PID 55387 zombie since 2026-05-04 (15j) caused persistent Telegram Conflict. 4 instances accumulated. PROCEDURE_URGENCE.md patched.

### Discipline audit
- WAL integrity intact despite 4-instance disaster: 125 signals = 125 distinct gmail_ids (zero duplicates 15j)
- Daily signal flow normal (3-26/day, 47 spike May 11 backfill)
- 270 tests passing
- Gates ALL GREEN at close (ruff/pytest/mypy)
- Bot PID 64509 single-instance, scheduler 22 crons

### Day 13 substantive wins (rank-ordered)
1. P0 newsletter injection validated end-to-end /risk_check + /analyze (closes philosophical loop)
2. WAL audit clean despite zombies (data integrity confirmed)
3. Lessons 12-14 codified (R19 v5 + schema verify + macOS case-i)
4. /risk_check + /analyze v2 roadmap docs (10 improvements pour post-J+30)
5. Universe +90 tickers (313 stable, J+30 prune scheduled)

### Carry-forward (NOT urgent)
- **Smoke test /analyze on fresh ticker** to verify NEWSLETTER SIGNAL CONTEXT axis renders (cache 24h)
- **score column scale**: empirically 0-10 not 0-100. Mat normalization in build_signals_context_block divides by 100, producing weights too low. Recalibrate when convenient (no behavior impact, just absolute magnitudes)
- **v2 roadmap improvements 1-9** (28h cumulative): #1 reverse stress test bidirectional, #2 inverted framing, #3 historical analogues (needs ADR 001 PIT), #4 multi-scenario probabilities, #5 cluster sizing math, #6 calibrated probability output, #7 at-a-glance header, #8 track record context line, #9 ASCII decision tree
- **Universe J+30 audit** (mid-juin per friction.md)
- **KPI #2 timer J-21** to 10 juin 2026 batch resolution
- **Plan A Big Bang preparation** mi-juin (ENR.DE, NDA.DE, RHM.DE, HAG.DE, 4062.T fresh /analyze + /risk_check)

### Strategic note
Day 13 fait passer un cap : le bot ne consomme plus juste son own decisions, il consomme aussi les newsletters payantes (SemiAnalysis $65/mo + Stratechery + Apollo + 6 autres) DIRECTEMENT dans ses decisional handlers. C'est l'argument central de Path 5/6 narrative : un système qui digère un curated stream + applique discipline bidirectionnelle calibrée. Plus juste un wrapper LLM.


---

## Day 14 close — 2026-05-20 ~08:15 KST (~6h session)

### Ships (4 commits since day13-close)

1. `1cefee6` fix(morning_brief): FX bug avg_cost EUR canonical (morning)
2. `b601bfd` fix(positions,kpi6): ADR 005 EUR canonical via cost_in helper
3. `8e345c2` fix(display): Group C currency labels follow-up
4. (this commit) docs+fix: ADR 005 doc + Lesson 15 + format_position_detail residuals + HANDOFF close + .gitignore dead tokens

### State

- HEAD pending commit, tag `day14-close`
- 281 tests passing, 0 ruff, 0 mypy (14 strict modules)
- Bot PID 69278, 22 crons clean
- Universe: 313 tickers (23/123/167)
- DB: 21 positions, 45 open predictions, 66 signals 30d, 27 active sources

### KPI snapshot

| KPI | Value | Status |
|---|---|---|
| #1 uptime 30d | 99.9% | ✅ GREEN |
| #2 NON-NEG | 1 res, 45 due J-20 (10 juin), forecast 46 | ⏳ ON TRACK |
| #3 Brier 90d | N=0 | 🔍 insufficient |
| #4 panic sells | 0 | ✅ GREEN |
| #5 decisions journalisées | 0 material 30d | 🔍 N/A |
| #6 Pf vs benchmarks | Pf -4.07%, Δ-4.4pp SPY / -5.0pp QQQ / -4.8pp SMH, 4d (21/21 priced) | 🔍 INSUFFICIENT (need 365d) |

### Concentration breach finding

`style.position_max_pct = 5%` violated by 6 positions (46.5% cluster, AI_compute thesis):
- 4063.T 10.5%, TSM 9.0%, ASML.AS 9.0%, SNPS 7.0%, 7011.T 6.0%, STMPA.PA 5.3%

**Decision pendante**: (a) trim, (b) bump policy à 8-10% documented, (c) ignore legacy inheritance + watch new. Required before next `/position_buy`.

### Carry-forward (priority order)

**P1 — Strategic/empirical:**
- KPI #2 timer J-20 to 2026-06-10 batch (45 predictions)
- Concentration policy decision (a/b/c) before next /position_buy
- VALUE_LOG.md entry Day 14: first /digest with action-grade synthesis (Path 6 evidence)
- NVDA: 2 high 8-K 5.02 in 12 days, 2 unresolved decisions, /risk_check NVDA candidate

**P2 — ADR 005 incomplete coverage (audit follow-up):**
- `theses.entry_price/target_*/stop_price` currency audit
- `decisions.price_at_decision` currency audit
- `position_events.price/pnl` currency audit
- `positions.realized_pnl` currency audit
- Each requires Lesson 15 cross-source ratio audit pattern

**P2 — Infra:**
- OAuth Cloud Console "Push to Production" (15 min, prevent weekly re-revocation)
- score column scale 0-10 vs 0-100 recal in build_signals_context_block
- Price snapshot drift /brief vs /portfolio caching audit (UX consistency)

**P2 — Universe:**
- Universe pruning audit J+30 mid-juin (313 tickers vs PHILOSOPHY "less surface")

**P3 — Code health:**
- bot/main.py 2428 LOC split bot/handlers/* (incremental as touched)
- Type hints remaining modules (gradual)

### Reopen entry point

1. `cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate`
2. `pgrep -fil "python.*bot.main"` confirm (PID 69278 or rotated)
3. Read this HANDOFF Day 14 close + `docs/adrs/005-eur-canonical-positions.md`
4. Pick P1 item: concentration policy OR KPI #2 wait OR ADR 005 P2 audit


---

## Day 14 evening — Debt Crisis Monitor Phase 1 (CONSCIOUS observation discipline override)

**Override rationale**: ADR 006 system addresses tail-risk on EXISTING thesis cluster (AI_compute 46.5%), not a new thesis/ticker/source. Empirical justification stronger than discipline cost: first scan returned **Composite 37.5 = Phase 2 STRESS**, driven by Gold $4,485 (P3) and RepoSRF $12.9B drainage (P3). The macro signal that the framework was designed to catch is already firing.

**Strategic alignment surface**: Phase 2 = "Cash +5%, halt aggressive deploy" per spec. Coherent with the Day 14 morning concentration breach finding (6 positions >5% cap). Combined reading: trim direction (option a) > bump policy (option b) for concentration decision.

**Ships Phase 1**: intelligence/debt_monitor.py + bot/handlers/debt_crisis.py + docs/adrs/006 + HANDOFF entry. 281 tests still passing.

**Phase 2 tomorrow (~4-5h)**: Fix CoreCPI+ISMMfg silent fails, APScheduler cron registration (3 schedules), alerts dispatch on phase escalation, /debt_history + /debt_alerts handlers, Hypothesis property tests, final ADR 006 update + day14-debt tag.
