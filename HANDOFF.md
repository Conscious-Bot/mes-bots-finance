# Session 2026-05-23 closed — Brier root-cause fix + audit dashboard clean

**Manuel agent**: `docs/AGENT_HANDOFF.md` (contrat + structure + schemas reels). Ce fichier = log chrono, lire le tail.
**HEAD**: b65ebf3 = origin/main  
**Tags**: day15-brier-dashboard, dashboard-audit-clean-23052026  
**State**: bot 1 instance, 345 tests, ruff/mypy 0  
**Brier**: repare a la racine (estimate_probability dans insert_prediction); effet id >= 158 uniquement; post_fix=0 (pas encore tire). NE PAS publier le Brier legacy (148@0.5 + 8@0.53 = vacant). Cohorte calibration = id >= 158, lue maturite-source en tete (recence != qualite).  
**Dashboard**: audit code clean (5 findings; F3/F4/F5 fixes; F1/F2 false alarms debunkes); 0 defaut restant.  
**KPI #2 timer**: J-18 vers 10/06/2026 (batch resolution legacy).  
**Carry-forward**: vue calibration fin juin (scoper id>=158), concentration AI Compute ~80% (decision operateur), COHR review 30/05, orphans AMD/GOOGL/SAF.PA/TSLA J+30=16/06.

---

# Session 2026-05-21 closed — 30 commits, Phases A+B refactor + 7 lessons

**Full retrospective**: `docs/sessions/2026-05-21.md`

**HEAD**: 236daea  
**State**: bot running 1 instance, 335 tests passing, ruff/mypy 0  
**KPI #2 timer**: J-19 to 10/06/2026  
**Carry-forward**: Sprint 1.2 Phase D-M, Personal Dashboard project, AMD/orphans review J+30

---

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

---

## Day 14 evening (CLOSE) — ADR 006 Phase 2A + 2B SHIPPED

**Status**: Debt Crisis Monitor protective layer LIVE end-to-end.

### Phase 2A (commit e49c326)
- CoreCPI YoY fixed (limit=14 + obs[11])
- ISMMfg → MfgIP_yoy (FRED dropped ISM 2024+)
- 18 Hypothesis property tests on classify_phase + composite + INDICATOR_CONFIG
- 281 → 299 tests passing
- Re-scan: Composite **42.0 pts → Phase 2 STRESS** (drivers Gold P3, RepoSRF P3, MfgIP_yoy P2)

### Phase 2B (commit 1e4c745)
- `_dispatch_alerts()`: composite escalation OR Tier 1 → P3+ transition → Telegram push
- `run_scan(dispatch_alerts=False)`: capture prev state pre-persist, diff post-persist
- 3 cron wrappers: cron_tier1_daily / cron_tier2_weekly / cron_tier3_monthly
- bot/main.py: 3 sched.add_job (Tier 1 daily 06:00 Paris, Tier 2 Mon 06:30, Tier 3 1st 07:00)
- Smoke verified: no spurious alert on no-transition state
- Total crons 22 → 25

### Tools matin protective layer (next session reopen)
- `/debt_status` — manual composite snapshot
- `/debt_status refresh` — force re-scan + persist
- Autonomous alerts: bot Telegram push on regime transition (no command needed)

### Lesson 16 — Heredoc-Python writing Python: double-escape diligence
Inside a Python heredoc string delimited by triple-single-quote, two pitfalls bit Day 14 evening:
1. Backslash escapes are interpreted by the heredoc Python BEFORE writing the file. To produce literal backslash-n in the output, use four backslashes plus n in the heredoc source.
2. Embedding the triple-single-quote sequence anywhere inside the heredoc content (even in prose backticks) terminates the string prematurely. Avoid the sequence in content or switch outer delimiter to triple-double-quote.

Caught both in Bash 66/67 and Bash 70/71. Codification deferred to CONVENTIONS.md only if recurrence — currently a tooling lesson, not a project rule.

### Day 14 final commit chain (post day13-close baseline)
1e4c745  feat(debt_monitor) ADR 006 Phase 2B — scheduler crons + transition alerts
e49c326  feat(debt_monitor) ADR 006 Phase 2A — fixes + Hypothesis property tests
13c9741  feat(debt_monitor) ADR 006 Phase 1 — 15-indicator debt crisis overlay
14cc1f2  docs(substack) Path 6 opening post draft — SK hynix bug case study
6978cdd  feat(risk_manager) ADR 005 P2 theses USD coherence + audit findings
815ed8b  docs(todo) Day 14 archive + carry-forward P1/P2
0bedcff  docs(adr005) ADR 005 doc + Lesson 15 + HANDOFF Day 14 close [TAG day14-close]
8e345c2  fix(display) Group C currency labels
b601bfd  fix(positions,kpi6) ADR 005 EUR canonical via cost_in helper + 6 Hypothesis
1cefee6  fix(morning_brief) FX bug avg_cost EUR canonical

### Carry-forward additions Day 14 evening

**P2 — ADR 006 Phase 2C (~1h):**
- `/debt_history INDICATOR` handler (30d sparkline + phase transitions)
- `/debt_alerts on|off` handler (global mute, default ON)

**Reopen entry point updated:**
1. `cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate`
2. `pgrep -fil "python.*bot.main"` confirm
3. Check overnight: did debt_tier1 cron fire at 06:00? Any Telegram alert?
4. Read this Day 14 evening section + `docs/adrs/006-debt-crisis-monitor.md` Phase 2A+2B
5. P1 still: concentration policy (a/b/c) before next /position_buy; KPI #2 wait J-19 → 10 juin

### Tag
`day14-debt` on commit `1e4c745` (alongside `day14-close` on `0bedcff` for morning close).

---

## Day 14 ULTRA-FINAL CLOSE (post-audit, ~12:15 KST 20 May 2026)

**Trigger**: audit complet demandé by Olivier after Day 14 evening close. Surfaced 1 false alarm + 4 real findings + 5 codification needs. All resolved.

### 5 new commits since day14-debt (`30a7e3c`)
82e1fb5  docs(conventions,todo) codify Lessons 16-20 + UTC sweep tracking
d6463fa  test(debt_monitor) H2 integration tests for _dispatch_alerts (9 scenarios)
2eebde3  fix(debt_monitor,handlers) post-audit L1+H1+H3 fixes + Phase 2C ship complete
30a7e3c  docs(adr006,handoff,todo) Day 14 evening CLOSE — ADR 006 Phase 2A+2B shipped  [TAG day14-debt]

### Bug fixes shipped post-audit

- **L1 cron exception envelope** — `_cron_run(tier, label)` shared helper, all 3 debt crons wrapped. Empirically verified via mock RuntimeError → cron does not raise, Telegram crash-alert dispatched.
- **H1 action playbook in alerts** — `_PHASE_ACTIONS` dict + inline injection in composite escalation message. Wake-up push now contains decision recommendation.
- **H3 None-prev documented** — `_dispatch_alerts` behavior contract in docstring (baseline rule, dedup, fail-open).

### Phase 2C SHIPPED COMPLETE (M3 dette closed)

- `/debt_history INDICATOR` — 30d sparkline (Unicode blocks ▁▂▃▄▅▆▇█) + transitions count + last 5 obs
- `/debt_alerts on|off` — bot_state.json toggle, fail-open default True

### H2 integration tests added (~30 min work, +9 tests)

`tests/test_debt_dispatch.py` mocks notify.send_text + _alerts_enabled. 9 scenarios cover all behavior contract documented in _dispatch_alerts docstring. 299 → 308 tests.

### Lessons 16-20 codified (CONVENTIONS.md Section 16)

| # | Title | Trigger |
|---|---|---|
| 16 | Heredoc double-escape + triple-quote nesting | Any patch script writing Python via heredoc |
| 17 | Audit complete control flow before SEVERE | Any audit declaration |
| 18 | Cron try/except + notify envelope mandatory | Any APScheduler add_job target |
| 19 | Alerts MUST include actionable recommendation | Any push notification on state transition |
| 20 | UTC explicit on all persisted datetimes | Any new datetime.now() |

### UTC sweep tracking (P2 carry-forward)

20+ legacy violations of CONVENTIONS §1 / Lesson 20 inventoried in TODO.md across shared/, intelligence/, bot/handlers/. Strategy: R14 "touch = type" rule extended (fix in same commit when touching file for other reasons), avoid top-down sweep. Custom ruff plugin candidate for Day 15+ infra task.

### S1 false alarm closure (audit accuracy log)

Claimed cron_tier1_daily partial-tier composite bug. Re-read run_scan lines 391-400 → code already merges stale cached + fresh tier values into full 15-indicator composite. False positive. Codified as Lesson 17. Audit accuracy matters: false-positives erode signal-to-noise and waste fix cycles.

### Lesson META for myself (Claude) at this close

12h+ Day 14 session ending pattern: "tout faire et de facon professionnel". Olivier's instruction translates to:
- No surface patches. Fix + lock + codify so problems can't recur.
- No discipline tradeoff for speed at stop point.
- Audit accuracy is a feature of audits, not a nice-to-have.

This ultra-final close embodies that principle. Five commits, zero shortcuts, zero scope deferred without explicit tracking. Net delta: bugs resolved, observability hardened, contracts documented, rules locked.

### Carry-forward Day 15+

**P0 strategic (still unresolved)**:
- ~~Concentration policy decision (a/b/c)~~ — RETRACTED Day 14 ultra-final. Was misframed: bot is intelligence not management, PHILOSOPHY clarifies the bot informs and Olivier acts. Position trims/holds are operator decisions, not config rules. Ship A (commit pending) wires narrative_max_pct + sector_max_pct as advisory OVERWEIGHT markers in /portfolio_narratives + /portfolio_sectors. Phantom rules eliminated.
- **KPI #2 timer J-19** to 2026-06-10 (44 predictions batch resolution). Observation discipline required.

**P2 infra**:
- UTC datetime sweep (per Lesson 20 + tracking inventory)
- ADR 005 P2 residual audit (position_events.price, positions.realized_pnl, decisions.price_at_decision deeper investigation)
- OAuth Cloud Console "Push to Production" (Gmail sensitive scope, prevents weekly token revocation)

**P3 code health**:
- bot/main.py 2428 LOC split bot/handlers/* (incremental as touched)
- Type hints remaining ~25 modules (gradual adoption)

### Tag

`day14-pro` on commit `82e1fb5` (final docs commit). Represents the audit-hardened state: bugs fixed, tests locked, lessons codified, ADR 006 closed.

Existing tags: `day14-close` (morning ship), `day14-debt` (ADR 006 Phase 2A+2B), `day14-pro` (post-audit ultra-final).

### Reopen entry point Day 15

1. `cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate`
2. `pgrep -fil "python.*bot.main"` confirm (last PID 71677, may rotate)
3. Overnight check: `/debt_status` to see if cron fired + alert state
4. Read this Day 14 ULTRA-FINAL section + `docs/adrs/006-debt-crisis-monitor.md` Phase 2C+audit + CONVENTIONS Lessons 16-20
5. Decision call: concentration policy (a/b/c) — NO position_buy until resolved
6. Observation discipline: J-19 to KPI #2 batch resolution. Resist build mode.

---

# Day 15 close — 21/05/2026 evening (Phase D /thesis ship + data fix)

## Shipped this session (15 milestones cumulative)

Continuing from morning + afternoon Sprint 1.2 work (Phase A-M closed earlier today, see prior session retrospective `docs/sessions/2026-05-21.md`):

**Phase B /portfolio family** (commit 556a2d2, tag phase-b-portfolio-21052026)
- Dispatcher injected in cmd_portfolio
- 2 helpers extracted: _position_view_impl, _position_history_impl
- Deleted /position_set
- 74 handlers registered

**Phase D /thesis family** (commit c3d31c8, tag phase-d-thesis-21052026)
- Largest ship of Sprint 1.2: 9 sub-actions absorbed
- 5 helpers extracted across 4 files: _asymmetry_impl, _thesis_set_impl, _thesis_premortem_impl, _thesis_health_impl, _price_check_impl
- ctx.args mutation pattern for 4 in-file delegations (list, add, note, revisit)
- Lazy imports for 5 cross-file helpers
- 75 handlers registered (+1 dispatcher)

**Data fix** (no commit — DB local only):
- 21 theses (IDs 23-43) stored key_drivers + invalidation_triggers as raw strings instead of JSON lists. Caused /thesis list to display character-by-character bullets.
- Bug source: 16/05 batch bootstrap script. Pre-existing, unrelated to Phase D.
- Normalized via sentence-split heuristic: 21/21 fixed, all now JSON arrays of 2-3 driver bullets + 1-3 trigger bullets.

## Incidents instructive (3 codified lessons)

- **L37** templates Python generating Python: no f-strings (Phase D extraction script)
- **L38** exit 1 in zsh interactive paste kills shell session
- **L39** pkill -f "python.*X" unreliable on macOS (capital P in framework binary)

~30min recovery wasted on Phase D Telegram conflict cascade caused by L39. Two prior aborted ships (zsh quote fragmentation) before file-based heredoc approach succeeded. Lessons high-value for future sessions.

## State at close

- Bot alive PID 85463 on c3d31c8 (Phase D)
- All gates green: ruff 0, mypy 0 on strict modules, pytest 335 passing
- 75 handlers registered (was 74)
- 33 active theses, all normalized to JSON storage
- HEAD = c3d31c8 (tag phase-d-thesis-21052026 + day15-close pushed)
- KPI #2 timer J-19 to 10/06 (44 predictions to auto-resolve)

## Carry-forward

**P2** (next session):
- Display defensive code (`try json.loads, except → wrap as single item`) — prevents future regression of the 21-theses bug pattern. ~30min in thesis_crud + display modules.
- Phase E /journal completion verify (done earlier today, smoke test deferred)
- Phase N UX redesign (~8-15h variable scope) per user feedback 2026-05-16

**P3**:
- Audit existing scripts for L39 pkill pattern (uptime_monitor + restart cron specifically)
- Continue type hints rollout (~25 modules remaining, gradual)

## Reopen entry point Day 16

1. `cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate`
2. `ps auxww | grep -E "bot\.main" | grep -v grep` to confirm alive (NOT `pgrep -f "python.*bot.main"` — see L39)
3. Read this Day 15 section + CONVENTIONS L37+L38+L39
4. Decision call: defensive display code P2 vs Phase N UX vs observation discipline
5. KPI #2 batch resolution due 10-11 juin (J-19 remaining)



---

## Day 15 FINAL CLOSE — 2026-05-21 21:17

**9 ships + 9 tags pushed**. Most productive session to date.

### Ships chronological
1. Phase B /portfolio family (commit 556a2d2)
2. Phase D /thesis dispatcher 5-helper extraction (commit c3d31c8)
3. 21-theses data normalization (DB only, no commit)
4. Substack opening post 2 editorial passes (25bb3bc, c90e352)
5. TG canonical output spec doc (2ed7a32) — `docs/conventions/telegram_output_canonical.md`
6. /brief canonical (834bdc4)
7. KPI #2 timer display disambiguation (816ac17)
8. /recent_8k canonical (554f9fb)
9. /asymmetry portfolio canonical + currency fix (4cc4083) — fixes stop EUR/USD bug

### TG canonical rollout state
3/N P0 handlers shipped: /brief, /recent_8k, /asymmetry portfolio.
Spec doc `docs/conventions/telegram_output_canonical.md` codifies the pattern
for future handlers. Principle refined late-session: "color = external signal
only, no color on user-derived constructs" (Day 5 tautology lesson re-applied).
Pending formal addition to canonical spec doc.

### Empirical signals surfaced by canonical (Day 16 Tier S)
1. **COHR 🔴 STOP NEAR** (only flag in 17 COMPUTED): current -11.6% from entry,
   stop at -10% from current. Concrete `/risk_check COHR LONG` or `/thesis premortem`.
2. **ALAB ratio 0.40 + 25.6% P&L** (bottom of ratio sort): anomaly visible — trim 30-50%
   or raise stop. Format made this obvious.
3. **NVDA 4 officer departures in 105 days** (Jan 23, Mar 6, Apr 27, May 8 2026):
   surfaced via /recent_8k canonical grouping. Pattern invisible in old flat dump.
   Plus 2 unresolved NVDA decisions in journal.
4. **4 orphans c1** (AMD, GOOGL, SAF.PA, TSLA) visible INCOMPLETE: target/stop missing.
   J+30 deadline 2026-06-16.
5. **Cluster drift négatif top-ratio**: COHR/AVGO/TSM/KLAC/4063.T/SNPS all -2% to -12%
   from entry. Recent buying near peaks or semis general weakness — pattern noted, not
   actionable from this view alone.

### Lessons codified (CONVENTIONS.md committed 4cc59f2)
- **L37**: Templates Python generating Python → no f-strings (curly brace collision)
- **L38**: `exit 1` in zsh interactive paste kills shell session → use `echo "[FAIL]"` or subshell
- **L39**: `pkill -f "python.*X"` UNRELIABLE on macOS (framework Python = `Python` capital)
  → use substring `pkill -f "bot.main"` or explicit `kill -9 PID`

### Universe expansion noted
Memory snapshot: 178 tickers. Current: 313 (23 core + 123 watch + 167 extended).
Universe pruning audit on June backlog. Not blocking, not addressed Day 15.

### Substack draft state
`docs/drafts/substack_opening_post.md` 1101 words. 2 editorial passes complete.
**Outstanding before publish**: SK hynix $1,216/share fact-check (actual market ~$200,
discrepancy unverified — split? per-lot? ADR equivalent?). Recommended publish 10/06/2026
with Brier batch resolution.

### Bot state
PID 2608, polling, scheduler 27 crons up, no errors.
Tests: 335 passed (up from 281 at Day 14 close).
ruff + mypy clean on touched files.

### Day 16 entry point
1. cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate
2. ps auxww | grep "bot.main" | grep -v grep (NOT pgrep -f python.*, per L39)
3. Read HANDOFF.md Day 15 final close + Day 16 Tier S
4. **Action priority order**:
   - COHR 🔴 STOP NEAR resolution (/risk_check or /thesis premortem)
   - ALAB ratio anomaly resolution (trim or raise stop)
   - NVDA 4-officer departure investigation + 2 unresolved decisions
   - 4 orphans J+30 (AMD/GOOGL/SAF.PA/TSLA — set target/stop or close)
5. Observe /brief 24-48h for friction notes in friction.md
6. Concentration policy AI_compute 67% — trim policy decision pending

### Not addressed Day 15 (carry-forward)
- Universe pruning audit (313 vs 178 baseline)
- ADR 005 P2 audit complete (positions_events.price, realized_pnl, decisions.price_at_decision)
- shared/display.py canonical refactor (~5-10h)
- target_partial NULL across 33 active theses (schema debt)
- Substack SK hynix fact-check
- TG canonical remaining handlers (P1: /portfolio, /positions, /digest)
- Canonical spec doc amendment: formalize "color = external signal only" principle

---

## Day 16 partial — 2026-05-22 (incident revisit + décisions)

### Incident MAJEUR clos: /thesis revisit mass-corruption
- Bug 3-parts (args ignorés + mark-on-display + NULL-due-no-age-gate) → un seul
  /thesis revisit 34 a marqué les 33 theses actives reviewed (corruption silencieuse
  discipline mensuelle).
- Diagnostic empirique (Lesson 13/15), recovery column-level ATTACH depuis backup
  pré-corruption 04:00 (NVDA deleted 11/05 préservée, 32 actives → NULL).
- Fix commit e246211 + tag revisit-bugfix-22052026. 335 tests, smoke 2/2.
- L40 (read-path no side-effect) + L41 (column-restore method) codifiées.
- Audit bug-class: CLEAN, isolé à revisit. debt_crisis update_state = toggle légitime.

### Décisions portfolio journalisées (notes appended)
- COHR (#31): risk_check #5 reco trim 25% OVERRIDE par 2-week observation policy
  (livre ouvert 16/05). Hold to stop $324.37. Review 30/05.
- ALAB (#34): stop raised 147.32 → 196.42 EUR (= entry breakeven). Dollar risk
  restauré $58/share (était $117, doublé). Asymmetry 0.40 → 0.96. Thèse intacte.

### Policy nouvelle (à encoder)
- 2-week observation post-opening: pas d'action portfolio avant 30/05. Tension non
  résolue: s'applique à toute modif ou seulement offensive (trim/add/exit)? ALAB
  stop raise = defensive, jugé OK. À écrire dans PHILOSOPHY.md.
- Le bot ne connait PAS cette policy → /risk_check re-recommandera trim. Guardrail
  Day 16-18: if thesis_age < 14d prepend "WITHIN_OBSERVATION_WINDOW".

### Friction map (9 items, sprint Day 16-18 décision-time UX)
1. /risk_check semantic (add vs eval position existante)
2. /thesis premortem no ticker→ID resolution
3. premortem non-retroactif ~21/33 theses
4. /thesis revisit spam (FIXED today)
5. /thesis set currency ambiguity (EUR storage vs USD display)
6. schema 3 target columns (target_price legacy + partial + full)
7. single-thesis /asymmetry verdict tautology (Day 5 lesson non-appliquée single view)
8. /thesis set no auto-journal decisions (KPI #5 gap)
9. bot n'encode pas 2-week observation policy

### Schema debts notés
- 3 colonnes target (target_price legacy probable dead)
- last_reviewed vs last_revisit_at (doublon, un mort)
- opened_at format (space, no offset) vs last_revisit_at (T+microsec+offset) incohérent
- target_partial NULL sur 33/33 (déjà backlog)

### Bot state
PID 7879 alive (restart post-fix), 27 crons, 335 tests, ruff+mypy clean.

## MAJ 27/05/2026 — dashboard cockpit canonique + hygiene
Bot : bot.main PID 37896 + dashboard.serve PID 47182 (un seul de chaque). Backup OK. Git HEAD 4c604bb.
Dashboard : palette par etat + metal (--c sur chiffres, chrome titres 46px silver-dark/graphite-frost) + concentration rouge "alleger sans sortir". Reference figee : CONVENTIONS.md. Servi HTTP (jamais file://), restart serve apres tout patch render.py.
Residuel P3 : Theses "en profit" rouge -> vert. Style globalement FIGE -- prochain levier = usage, pas CSS.

## Day 17 (28/05/2026) — surface command-line alignee telemetrie

Chantier termine + push origin (f783756, 39 commits). Surface 76->72.
- Cull -10 flats morts, +2 alias (/positions /value_log), restore /kpi_status /signals_by_type /insider_buy_cluster_stats, build /tiers (conviction-sizing price-free), dedup signals_by_type, /help genere du registre (zero drift).
- Signal: /tiers sort inflation c5 = 21% > gate 20% — laisser Brier 10/06 trancher, NE PAS de-tierer a la main.
- Detail complet: SESSION_STATE.md "Day 17 close".

Reouverture: lire SESSION_STATE.md tail + TODO Path5/6 + PHILOSOPHY High Standard. Freeze observation jusqu'au 10/06 (display/UX/additif hors-gel).
Loose ends non-urgents: friction.md (logge ce jour), retirer credentials.json/token.json des project files Claude UI, cat `trade`, Hetzner prep ~31/05 (compte+SSH+ADR 002, 4 questions ouvertes).


## Day 17 (28/05/2026) — Dashboard A/B/C-amorce + command surface

**Command surface** (7 commits, pushes faits) : aligné sur télémétrie (handler_calls), 71 cmds, /help auto-généré du registre (fini la string V4 menteuse), 10 docstrings nues remplies, decision_type enum documenté (CONVENTIONS §2), /bot_data culled.

**Dashboard — fil rouge : single-source + couleur = fait, jamais jugement.** 4 commits atomiques :
- A `_pct` : autorité unique de format des poids → plus-grosse-ligne 9% → 8.6% (réconcilie Concentration/Positions).
- B1 : KPI "asymétrie favorable (ratio≥2)" → "proches de la cible". La tautologie Day-5 qui avait fui dans le dashboard est retirée, + le seuil local ≥2 (≠ module 1.5) tué.
- B2+C-amorce : marqueur asymétrie coloré par PROXIMITÉ factuelle (rouge stop / vert cible / neutre sinon — fini le vert-P&L flatteur) + piste teintée rouge→vert FIXE (légende d'axe identique par carte, pas un verdict). Pose l'axe sémantique unique sur tout le dashboard.

**Méta-leçon de session** : j'avais d'abord re-proposé une carte "favorable/défavorable" colorée = exactement la tautologie Day-5. Rattrapé en lisant le code (format_*_asymmetry de-tautologisé 27/05). Le dashboard avait lui-même dérivé de la leçon ; on l'a réaligné sur la couche TG.

**EN ATTENTE — prochaine session "carte Thèses" (D + sizing) :**
- *Sizing bar overshoot* : hiérarchie inversée aujourd'hui (barre = poids total, cap = tick non-labellisé à 76.9% magique, dépassement = sliver invisible). Refonte : dans-cap muet / **hors-cap rouge saturé proportionnel** / sous-cap marge verte / tick cap labellisé. Code = `th-sz`/`th-szf`/`th-szc` (L1126-1128 CSS) + bloc `_fill`/`sizebar` (~L1300). Isolable, 1 commit.
- *Déclutter* : "cible taille X%" = constante par palier répétée sur chaque carte → hisser dans l'en-tête du tier.
- *Faux précis* : "−1 944 €" → arrondi (−1 950 / −1.9k).
- *D* : page Thèses rangée par ACTIONNABILITÉ d'abord (lignes demandant décision en haut), pas par conviction. Badges conviction déjà colorés (c5 bleu/c4 vert) = moitié de D déjà faite.
- Restent E (parité light/dark des oklch fixes des barres) + F (CTA honnête decision-log, échelle macro labellisée, responsive/mobile).

**Day 17 EXTENSION (cloture reelle)** : sizing overshoot FAIT (la file ci-dessus etait obsolete sur ce point) - barre `th-sz` segmentee gris/ambre/rouge, cible = frontiere de couleur, cap = tick ; queue rouge seulement si depassement de cap. `proches-du-stop` (cockpit) seuille : rouge<10 / ambre<20 / calme>=20, echelle 0-40 -> fini la fausse alarme quand le book est sain. RESTE prochaine session : declutter sizing ("cible taille X%" hisse en en-tete de tier + arrondi EUR), D (ranking actionnabilite), E (parite light/dark des fills fixes #2A4439 / oklch), F (CTA / echelle macro / responsive).
