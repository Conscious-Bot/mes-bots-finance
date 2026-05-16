# HANDOFF — mes-bots-finance

**Last close**: 16 May 2026, 18:00 KST (Seoul) — Day 5 final + 3 bonus commits
**Latest commit**: 88db101 (Fix intl ticker pipeline + /thesis_health narrative parsing)
**Tag**: day5-final (on 60cf504, marks official close before 3 bonus commits)
**Bot**: PID 33688 alive, single instance, scheduler started (22 crons)

---

## TL;DR for new session

Day 5 = **4 pivots empirique** (matin marathon -> midi audit -> soir UX-fix -> nuit thesis logging + cleanup) :
1. **Pivot 1 (matin)**: ship marathon -> handler UX audit (73 handlers -> 24 planned)
2. **Pivot 2 (soir)**: handler UX-fix -> portfolio thesis logging (real 21-position alignment)

**Critical state**:
- 21 positions réelles (dummy NVDA cleaned up)
- 33 theses actives total: 21 PF (1:1 with /portfolio) + 12 watch carry-forward
- 9 theses superseded (3 old 15/05 + 6 HPQ/Pharma evening cleanup, 6890.T rollback-kept)
- 4 orphans c1 flagged J+30 review (AMD, GOOGL, TSLA, SAF.PA)
- 46 predictions due 2026-06-10 (J+24 from this close)
- KPI #2 timer ON TRACK for first Brier baseline
- Intl ticker pipeline FIXED (config + prompts + handler) - empirical effect within 1h cron

---

## What got shipped Day 5 (38 commits)

### Morning marathon (33 commits)
- Sprint 1.1: 9/10 PLAIN chunks extracted (bot/main.py 3324 -> 1115 LOC, -66%)
- 8 new features: /find, /portfolio_sectors/narratives/drift, /journal_audit, /signal_drilldown, /thesis_health, /bias_pattern
- mypy strict: 11 -> 30 modules
- Tests: 49 -> 189 (Hypothesis property-based)
- Chunk 3 TYPED reserved Sprint 1.2 (17 handlers, ~345 LOC)

### Afternoon pivot — handler UX audit (1 commit)
User feedback: "73 handlers, beaucoup affichent des textes incomprehensibles"
- 12 blocs decisions K/U/D logged docs/handler-review-2026-05-16/decisions.md
- Plan: 73 -> 24 commands (-67% surface)
- Sprint 1.2 plan docs/sprint-1.2-plan.md (Phases A-N, 23-28h + 8-15h UX)

### Evening — 3 UX-fixes empirique validated (3 commits)
1. **/brief v3.1** (43831d9): 16 lines, KPI #2 timer, top 5 conviction, devise heuristic
2. **/digest v2** (0b01fd4): header metadata + VERDICT line + 1-line bruit + drill-down
3. **/portfolio v2.1** (0d1735d): ALERTS top + conviction + PnL% + common names cache + drill-down
   + NEW shared/ticker_names.py + DB table ticker_names (yfinance shortName cache)

### Post-close bonus (3 commits, after tag day5-final)
- **108d57d**: supersede 6 HPQ + Pharma watch theses (clean carry-forward)
  - Empirical catch: 7 rows updated initially (6890.T double-classified HPQ+PHYSICAL_AI)
  - Rollback 6890.T to active per Thèse #3 (Ferrotec ferrofluids/thermal)
  - Final: 33 active / 9 superseded
- **88db101**: Fix intl ticker pipeline + /thesis_health narrative parsing
  - Fix 1: config.yaml +3 tickers (4063.T, 000660.KS, ALAB)
  - Fix 2: shared/prompts.py removed "US tickers" bias, intl explicit (.T .PA .AS .KS .SW .L)
  - Fix 3: bot/handlers/thesis_health.py recognizes both narrative= and sector_thesis_id formats
  - Empirical: /thesis_health now shows AI_compute/Electrification/EU_defense narratives
    instead of "untagged" for the 21 PF theses
  - Limitation documented: source coverage gap (no dedicated Japan/Korea newsletter)
- 4th handler UX-fixed empirical validated: /thesis_health v2 (3 fixes)

### Late evening — thesis logging (1 commit, DB ops not git-tracked except snapshot)
- 5aeea1c: docs/snapshots/ DB dump (21 theses + bot_state) for audit trail
- DB ops (NOT in git, only in DB):
  - DELETE positions.NVDA zombi (id=6 qty=0.1 closed)
  - UPDATE bot_state.json (10k dummy -> 42726 real PF value)
  - INSERT 21 theses (one per real position, from user 5-thesis doc)
  - UPDATE 3 watch theses (4063.T, 7011.T, 000660.KS) -> status='superseded'

---

## Critical handlers state

| Handler | State | Notes |
|---|---|---|
| /brief | v3.1 ✅ | Empirical Telegram validated |
| /digest | v2 ✅ | VERDICT line, header metadata, drill-down |
| /portfolio | v2.1 ✅ | ALERTS + conviction + common names |
| /find | as-is | Favori user, UX-review queued |
| /journal audit | as-is | Created Day 5 morning, UX-review queued |
| /signal_drilldown | as-is | UX-review queued (will become /signal Sprint 1.2) |
| /thesis_health | v2 ✅ | 3 fixes shipped 88db101 (narrative parsing + intl pipeline) |
| 70+ others | as-is | Sprint 1.2 audit (24 final commands planned) |

---

## 21 positions + theses (state DB après thesis logging 16/05)

### AI_compute narrative (14 positions, dominant)
- **Tier S c5**: 6920.T LASERTEC (L5_metrology, EUV mask monopole)
- **Tier A c4**: ASML.AS, BESI.AS (L1), 4063.T (L3_wafer), COHR (L3 mat),
  KLAC (L5), TSM (L6_foundry), 000660.KS (L7_HBM), SNPS (L8_EDA)
- **Tier B c3**: STMPA.PA (L9), MRVL/AVGO/ALAB (L10_networking), TER (L5 test)

### Electrification narrative (2 positions)
- **Tier A c4**: 7011.T (gas turbines), SU.PA (transmission)

### EU_defense narrative (1 position)
- **Tier A c3**: HO.PA Thales (underweight to upsize post-J+28)

### Orphan c1 (4 positions, review_by=2026-06-16)
- AMD: doc explicitly says "trop priced, exposition cycle"
- GOOGL: Thèse #5 names AMZN not GOOGL
- TSLA: not in any of 5 theses
- SAF.PA: EU defense but #4 names HO.PA only

---

## 18 watch theses from 15/05 (carry-forward decision)

Created Day 4-5 sector_thesis_id framework, NOT in portfolio:
- **POWER_GEN** (CEG, BWXT, GEV, 5411.T) — 3/4 align with Thèse #2 Electrification
- **PHYSICAL_AI** (6324.T, 6890.T, 6268.T, 6861.T, CGNX) — 2/5 align with Thèse #3
- **STORAGE** (STX, PSTG, 285A.T) — abandoned, candidate superseded
- **HPQ_WAFER** (3436.T, MTUS) — redundant Shin-Etsu, candidate superseded
- **PHARMA_GLP1** (WST, STVN, DIM.PA, YPSN.SW) — out of focus, candidate superseded

**Decision deferred next session**: superseded HPQ+Pharma (6 tickers) was queued but not executed.
User reco received: drop HPQ + Pharma, keep POWER_GEN + PHYSICAL_AI + STORAGE.

**SQL ready to execute** (in /tmp/ but lost on reboot, recompute next session):
```sql
UPDATE theses SET status='superseded',
  last_reviewed=<now>,
  notes = notes || ' | superseded 2026-05-16: framework dropped'
WHERE status='active'
  AND (notes LIKE '%HPQ_WAFER_CHOKEPOINT_2026%'
       OR notes LIKE '%PHARMA_FILL_FINISH_GLP1_2026%');
```

---

## Bot state (truth source data/bot_state.json)

```json
{
  "peak_capital": 42726.0,
  "current_capital": 42726.0,
  "drawdown_pct": 0.0,
  "session_id": "session_20260516",
  "paper_only": true,
  "notes": "Reset 2026-05-16: removed dummy 10k test state. PF real = 21 positions. NVDA monitored (theses/predictions) but not held."
}
```

---

## DB key metrics (16/05 close)
positions:        21 (qty > 0, NVDA dummy purged)
theses active:    39 (21 portfolio + 18 watch sector_thesis_id)
theses with PF:   21/21 (100% coverage, no more c- in /portfolio)
theses orphan:    4 c1 (AMD, GOOGL, TSLA, SAF.PA) — review J+30
predictions open: 46 (cluster J+28 due 2026-06-10)
predictions resolved 28d: 1
signals 30d:      66+
cost MTD:         ~$15/mo projected (5% budget GREEN)
tests:            189/189 passing (Hypothesis property-based)
mypy strict:      30 modules
ruff:             0 errors

---

## Next session — canonical entry steps

```bash
cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate

# 1. Verify bot vivant
pgrep -fl "python.*bot.main"
# Si DOWN: nohup python -m bot.main > bot.log 2>&1 & ; sleep 10 ; pgrep -fl ...

# 2. Read this HANDOFF.md + TODO.md
cat HANDOFF.md
cat TODO.md | head -50

# 3. Pull latest
git pull
git log --oneline -10
```

---

## Recommended next session 3 paths

### Path A — Finish thesis cleanup (~10 min) [DONE 108d57d post-close]
~~Supersede HPQ + Pharma 6 tickers~~ DONE. 33 active / 9 superseded final state.

### Path B — Continue handler UX-fix sweep (~30-45 min per handler)
Candidates per Sprint 1.2 plan:
- /find (user favorite, queue P0)
- /journal audit (post-thesis logging, KPI #5 enforcement)
- /thesis health (overview after 21 logged)
- /signal_drilldown (rename to /signal Sprint 1.2)

### Path C — Document method + skills carry-over
- Create docs/handler-ux-2026-05-16/log.md (currently untracked)
- Document UX-fix replicable pattern for future handlers
- Update docs/sprint-1.2-plan.md with empirical learnings

**Mission queue next session (validated user 16/05 evening, ordered execution)**:

### Step 1 — /thesis_health empirical retest (5 min, FREE gate)
- Wait 24h+ from 88db101 commit (Day 5 close) to let cron signal_classify
  ingest new signals with intl-aware prompt.
- Run `/thesis_health` in Telegram.
- VERIFY: ASML/TSM/Lasertec/4063.T/000660.KS have 'sig' count > 0.
- If YES: prompt fix is sufficient, proceed to Step 2.
- If NO: P0 source coverage is THE only remaining lever, jump directly to Step 4.

### Step 2 — UX-fix /find handler (30-45 min)
- Empirical paste -> diagnose -> redesign -> smoke -> gates -> commit.
- /find = user favori for cross-domain drill-down (signals + thesis + recent
  decisions + price action for a single ticker).
- 5th handler UX-fixed (after /brief, /digest, /portfolio, /thesis_health).

### Step 3 — UX-fix /journal audit (30-45 min)
- Same method.
- /journal audit = KPI #5 enforcement: surface tickers with signals but no
  logged decision. Now critical because 21 theses logged Day 5 = baseline.

### Step 4 — P0 Source coverage gap (1-3h, depends on Step 1 result)
- Identify 2-3 newsletters Japan equities:
  candidates Asianometry deep, Smartkarma free tier, JapanInvest, Hayek Japan
- Identify 1-2 Korea equities:
  candidates Korea Investing, KospiKosdaq Weekly
- Identify 1-2 EU deep coverage:
  candidates Vinland Capital EU, Petrostevia EU equities, Morningstar EU
- Subscribe + Gmail filter "Newsletters" routing.
- Empirical verification: 7 days cron, /sources_brier shows new sources active.

### Step 5 — P2 Timezone audit (1h)
- Fix "-1d old" bug in /thesis_health and across /digest /portfolio.
- Root cause: datetime.now() machine = KST, opened_at stored UTC-naive ->
  mismatch. Need datetime.now(timezone.utc) consistent everywhere.
- Audit all `datetime.now()` calls in handlers, normalize.

### Step 6 — P2 Tier inflation review (30 min methodology)
- Empirical c4 = 30% of theses (10/33) post-Day 5 tier-based mapping.
- PHILOSOPHY watch >20% c5 only, but c4 saturation is silent inflation.
- Revisit 10 c4 theses: identify which are TRULY Tier A monopole vs
  "quality company in sector" (which should be c3).
- Candidates for downgrade: SNPS (duopoly not monopole), KLAC (duopoly),
  BESI.AS (duopoly hybrid bonding), COHR (multi-product).
- Updates: status='active', conviction downgrade as decided, note appended.

---

**Estimated total**: 4-7h spread across 3-5 sessions.
**Deadline empirical**: J+24 = 10 juin 2026 (KPI #2 batch resolution).

After 10 juin: decision Path 5 (acquihire 18-24mo) vs Path 6 (Substack 24-36mo)
based on first Brier baseline + track record empirical.

---

## Critical files reference

| File | Purpose |
|---|---|
| HANDOFF.md | This file, canonical session entry |
| TODO.md | Backlog + Path 5/6 + day 5 closed items |
| PHILOSOPHY.md | High Standard Mode principles |
| CONVENTIONS.md | Naming + code structure |
| FICHE_TECHNIQUE.md | Mission + stack + KPIs |
| docs/handler-review-2026-05-16/decisions.md | 12 blocs K/U/D for 73->24 commands |
| docs/sprint-1.2-plan.md | Phases A-N execution plan |
| docs/snapshots/theses_2026-05-16_post_logging.sql | SQL dump 21 theses + 18 watch |
| docs/snapshots/bot_state_2026-05-16_post_cleanup.json | bot_state snapshot |

---

## Source coverage gap (NEW dette discovered Day 5 evening)

**Empirical finding**: 9 newsletters subscribed = US-centric (Stratechery,
SemiAnalysis, Apollo, Unusual Whales, Wall Street Rollup, Adam Tooze,
Noahpinion, Stoller, Defiant) + 1 FR aggregator (Meilleurtaux, Bourseko).

**NO dedicated source for**:
- Japan equities (4063.T, 6920.T, 7011.T held c4-c5 = 67% of Thèse #1 critical mass)
- Korea equities (000660.KS held c4)
- European deep-coverage (ASML.AS, BESI.AS, SU.PA, HO.PA detailed)

**Consequence**: even with intl ticker prompt fix shipped 88db101, signal volume
for intl positions will stay LOW because sources don't cover them deeply.

**Action items Sprint 1.2 or earlier**:
- Identify Japan equities newsletter source (search candidates: Asianometry deep,
  Smartkarma, Tobias Carlisle Japan, Hayek Japan Equities)
- Identify Korea equities newsletter (search: Korea Investing, Korea Stocks Weekly)
- Identify European deep-coverage (Société Européenne, Investing.com EU deep,
  Morningstar EU)
- Decision: add free tier subscription + Gmail Newsletters filter routing

## Empirical lessons Day 5

1. **Method validated 3x consecutive**: empirical Telegram paste -> diagnose ->
   redesign -> smoke -> gates -> commit. Replicable for handlers UX-fix.
2. **Bot restart pitfalls**: kill -9 + sleep 5 minimum (sleep 3 insufficient,
   double instance Conflict error from polling). Always verify ps + tail bot.log.
3. **Schema mismatches**: signals.source_name doesn't exist (-> JOIN sources),
   theses.narrative doesn't exist (-> use notes field with key=value format).
4. **Sonnet hallucinations**: hardcoded dates, location ("Paris" when Seoul).
   Fix via explicit today_str in prompt + remove location hardcodes.
5. **Nested f-strings**: pre-compute strings to avoid SyntaxError on \" escapes.
6. **Idempotent patches**: use `if "marker" not in text` guards to allow retry.
7. **Pivot pendant ship**: rare but precious. Tu as pivoté 2x Day 5 (audit + thesis logging).
