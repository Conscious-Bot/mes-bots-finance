# Procedures — Operational Runbook

**Last updated**: 13 May 2026
**Purpose**: Runbook for daily ops + emergency procedures + observation mode (June 10 KPI #2 batch resolution).

---

## Daily — Ritual matinal (~10 min)

1. **Open Telegram**, send `/brief` — 6 sections aggregator (regime, signals, theses, asymmetry, calendar, journal)
2. Read sections, no need to act unless STOP_BREACHED or TARGET_HIT verdict appears
3. If material decision considered: ALWAYS run `/risk_check TICKER SIDE USD` BEFORE executing
4. If executed: `/position_buy TICKER QTY PRICE notes...` or `/position_sell ...` (NOTE: Phase B5 journal logging regression — manually run `/journal add ...` after for KPI #5)

---

## Weekly — Sunday review (~20 min, automated posts)

The bot auto-posts 4 weekly summaries on Sunday:

| Time (Paris) | Cron | Output |
|---|---|---|
| 22:00 | `weekly_cost_summary_job` | `/cost_trajectory` — MTD spend + projection vs $50 budget |
| 22:30 | `weekly_kpi_status_job` | `/kpi_status` — 5 KPIs with breach flags |
| 23:00 | `weekly_handler_stats_job` | `/handler_stats` — Pareto curve of command usage |
| 1st 6:00 | `monthly_brier_recal` | Source credibility recalibration from resolved predictions |

**Review checklist on Sundays**:
- KPI #2: Is N_resolved on track? Forecast J+28 GREEN/AMBER/RED?
- KPI #3: Brier rolling 90d <0.20? (only meaningful after June 10)
- KPI #4: 0 panic sells? (panic = full_exit before partial/stop trigger times)
- KPI #5: 100% material decisions journaled (reasoning >=30 chars + bias_tags)?
- Cost: <90% of $50 budget projection?

---

## Monthly — Strategic review (1st of month, ~30 min)

1. Read `/kpi_status` weekly summary archives
2. Read `/sources_brier` — which sources are calibrated, which to demote/drop
3. Manually invoke `/promote TICKER tier` if conviction warrants
4. Review docs/SOURCES.md tier S/A/B distribution — is empirical alignment with intuition?
5. If KPI #2 GREEN AND Brier mesurable → consider activating ADR 001 PIT bitemporal implementation (Phase 1)

---

## Bot lifecycle

### Start bot
```bash
cd /Users/olivierlegendre/mes-bots-finance
source venv/bin/activate
nohup python -m bot.main > bot.log 2>&1 &
```

### Verify bot vivant
```bash
ps aux | grep bot.main | grep -v grep | awk '{print "PID="$2}'
tail -20 bot.log
```

### Restart bot (after code changes)
```bash
pkill -f bot.main; sleep 3
for pid in $(ps aux | grep bot.main | grep -v grep | awk '{print $2}'); do kill -9 $pid 2>/dev/null; done
sleep 2
nohup python -m bot.main > bot.log 2>&1 &
```

### Stop bot definitively
```bash
pkill -f bot.main
```

---

## Emergency procedures

### Bot crashed (no PID running)
1. Check `bot.log` last 50 lines for traceback
2. If syntax error in code: `git log --oneline -5` to find latest commit, `git diff HEAD~1` to see what changed
3. If DB locked: check WAL mode active (`PRAGMA journal_mode;` should say `wal`)
4. If LLM API down: bot can run without LLM (handlers degrade gracefully), restart later

### DB corruption
1. Stop bot
2. `make test-restore-db` to verify backup integrity
3. `cp data/bot.db data/bot.db.corrupted_$(date +%Y%m%d_%H%M%S)` (preserve evidence)
4. Restore latest snapshot: `cp ~/backups/mes-bots-finance/bot.db.LATEST_TIMESTAMP data/bot.db`
5. Restart bot
6. Verify with `/kpi_status` that data state matches expectations

### Cost overrun (>$50/month projection RED)
1. Identify expensive task: `/cost_trajectory` shows tier + task breakdown
2. If `enrich` (Sonnet) dominates: reduce `daily_digest` cron frequency or signal volume
3. If `reasoning` (Opus) dominates: audit `/risk_check` and multi-round debate triggers
4. Disable specific cron temporarily by commenting `sched.add_job(...)` in bot/main.py
5. Restart bot, re-evaluate next Sunday

### Spam from a source (high noise volume)
1. Identify via `/handler_stats` or `/sources_brier`
2. Mark source as Tier B in `docs/SOURCES.md`
3. Optionally: modify `data_sources/gmail_.py` filter to exclude
4. Source weight automatically reduced in materiality scoring

### KPI #2 breach (less than 5 resolved predictions over 28 days)
1. STOP new feature building for 5 days (enforce discipline)
2. Force-use existing tools: `/brief`, `/asymmetry`, `/risk_check` daily
3. Resume only when 5+ resolutions accumulated AND root cause identified
4. Most likely cause: signals not converted to predictions (check `signals.score >= 6` threshold)

---

## Observation mode (current — until June 10, 2026)

**Goal**: Accumulate empirical track record before adding features.

**Rules**:
- NO new features. NO new tickers. NO new sources.
- DAILY: run `/brief`, observe asymmetries, log decisions if any material action
- WEEKLY: read auto-posted summaries Sunday
- MONTHLY (June 1): trigger first brier_recal cron, validate output

**Exit criteria**: KPI #2 satisfied (5+ predictions resolved by June 10) AND no critical bugs surfaced.

**On exit (June 10)**:
- If GREEN: proceed to ADR 001 Phase 1 (PIT bitemporal implementation, ~10h)
- If RED: 5-day enforcement, then root-cause analysis before resuming build

---

## Carry-forward dettes (from session 13 May 2026)

| Dette | Priority | Effort | Path 5/6 impact |
|---|---|---|---|
| Phase B5 journal logging regression (cmd_position_buy/sell) | P1 | ~1h | KPI #5 ablation |
| Refactor bot/main.py (2428 LOC → handlers/*.py split) | P3 | ~4h | Code organization signal |
| Type hints on remaining 30+ files (data_sources, shared/edgar, intelligence/older) | P3 | ~6h | Gradual via touch-pattern |

These are NOT bugs blocking observation. They are carry-forward improvements for future sessions.

---

## Quick reference — most useful commands

| Command | When | Output |
|---|---|---|
| `/brief` | Morning ritual | 6-section status |
| `/asymmetry [TICKER]` | Before sell decision | Math-driven verdict |
| `/risk_check TICKER SIDE USD` | Before any material decision | Opus deep risk assessment |
| `/kpi_status` | Anytime | 5 KPIs with breach flags |
| `/cost_trajectory` | Anytime | LLM spend MTD + projection |
| `/signals_by_type catalyst\|data\|narrative\|opinion [hours]` | Targeted signal review | Filtered list |
| `/recent_8k` | After SEC filing window | Top 5 recent 8-K with severity |
| `/insider_buy_cluster_stats` | Monthly | Insider cluster signal density |
| `/thesis_premortem ID` | After thesis_add | Imagined failure scenarios |
