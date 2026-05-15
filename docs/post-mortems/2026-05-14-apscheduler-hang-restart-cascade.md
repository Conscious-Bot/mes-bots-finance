# Postmortem: APScheduler hang + restart cascade

**Date**: 14 May 2026 evening (KST 21:11 - 21:33)
**Severity**: P1 (bot scheduler frozen ~7h, no auto-recovery)
**Author**: Olivier Legendre

## TLDR

APScheduler thread hung silently at 11:15 CEST (process alive, no jobs firing). Detection at next reopen via `bot_health_check.sh heartbeat_fresh` signal — Tier 2 ship from previous day validated within 24h of deploy. Restart cascade due to case-sensitive pkill (§16 violation) + Python.app launcher PID confusion → dual-launch competing for Telegram polling. Fix: kill by interpreter PID via `pgrep -if | xargs kill -9`.

## Timeline (CEST, system TZ)

- **06:43** Bot start, scheduler running with 23 crons registered
- **07:44 + 08:44** "Missed by 20-23s" batches in log (gmail_ingest 20s API call blocking concurrents)
- **09:13** Last clean log entry (signal_classify ran normally)
- **09:13 - 11:15** Silent gap ~2h — no log entries despite hourly crons
- **11:15:11** APScheduler wakes partially, logs 7 jobs missed by 31min (incl. heartbeat + gmail_ingest themselves). Crypto_zone hourly missed by 1h15m
- **11:15+** Complete log silence ~7h (until restart)
- **21:11 KST** Health check on reopen → RED, heartbeat 327min stale
- **21:13-21:33 KST** 4 restart attempts cascade before clean state PID 13697

## Root cause

### Primary (hypothesis, P2 to confirm)

APScheduler default `ThreadPoolExecutor(max_workers=10)`. Gmail_ingest blocking ~20s per call (Google API), combined with other concurrent jobs at hourly tick, accumulated stuck workers. Around 09:13 the pool went fully saturated. Scheduler dispatcher recovered briefly at 11:15 (logged misses) then dispatcher thread itself died. Process and asyncio loop remained alive (Telegram polling continued), only scheduler subsystem stopped.

Not 100% confirmed without APScheduler DEBUG-level internal logging. Requires post-J+28 investigation.

### Secondary cascade (4 failures during restart)

1. **pkill -f case-sensitive** — `python.*bot.main` lowercase pattern, but macOS bin path is `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python` (capital P). Zero match. §16 violation in my own block 24h after codifying §16
2. **First nohup restart** spawned PID 13201 (launcher) while old PID 10657 still polling Telegram → Conflict
3. **kill 13201** killed launcher but interpreter PID 13403 (forked child) survived, reparented to shell
4. **Second nohup restart** spawned PID 13546 (launcher) competing with surviving 13403 → Conflict cascade

Underlying mechanism: macOS Python.app launcher pattern. The launcher binary forks the actual interpreter into a different PID, then may exit. bash tracks launcher PID as job [N]. `kill %N` kills the launcher (often already dead), leaves interpreter orphaned.

## Impact

- ~7h pipeline frozen (gmail_ingest, scoring, journal_resolve, backup 04:00)
- Predictions resolution unaffected (cluster J+28 = 10 juin = batch, not daily)
- KPI #2 timer unaffected (signal accumulation reduced, fully resumable)
- 22min restart cascade with dual processes Telegram-competing — no observed rate-limit

## Detection

Tier 2 `bot_health_check.sh` (commit 26678e9, Day 3 evening) caught via `heartbeat_fresh FAIL` (327min > 60min threshold). Without it: incident invisible until next manual `tail bot.log` check. Detector value validated empirically within 24h of deployment.

## Fix (canonical sequence)
pgrep -if "python.*bot.main" | xargs kill -9
sleep 30
pgrep -ifl "python.*bot.main"
nohup python -m bot.main > bot.log 2>&1 &
head -10 bot.log
./scripts/bot_health_check.sh

Heartbeat_fresh will remain FAIL ~1h post-restart until first cron fires. Expected, not a re-occurrence.

## Lessons learned

1. **§16 case-insensitive matching applies to pkill/ps/grep, not just pgrep/detectors** → codified CONVENTIONS §19 Rule 1
2. **Python.app launcher PID ≠ interpreter PID on macOS** → codified CONVENTIONS §19 Rule 2
3. **APScheduler default config is fragile under sustained load** → P2 investigation
4. **Cascading restart attempts during fatigue degrade situation** — each "quick fix" produced worse state. Future: complete diagnostic before any kill/restart action

## Action items

- [P0] CONVENTIONS §19 + §16 extension (shipped this commit)
- [P0] failure_modes.md #6 (shipped this commit)
- [P2] APScheduler config investigation: max_workers, coalesce, executor type (post-J+28)
- [P2] APScheduler INFO-level internal logging for stuck worker detection (post-J+28)
- [P3] Consider multiprocessing executor for long-running gmail/LLM jobs (Sprint 1.5+ scope)

## Validation

Bot restarted clean PID 13697 at 14:32:49 CEST (21:32 KST). Log shows canonical startup: `Bot starting. Tickers: 22 core + 81 watch + 112 extended = 215 total`, `Polling Telegram...`, `Scheduler started: heartbeat 1h, gmail 1h, ...` with all 23 jobs. Zero Telegram Conflict in new bot.log.

## Correction (added 2026-05-14 22:00, post pre-flight code analysis)

The initial root cause hypothesis above ("ThreadPoolExecutor saturation, max_workers=10") is **wrong**. Pre-flight `grep` of `bot/main.py` during Sprint 1.1 readiness check revealed:

- Line 8: `from apscheduler.schedulers.asyncio import AsyncIOScheduler`
- Line 2614: `sched = AsyncIOScheduler(timezone=os.environ.get("TZ", "Europe/Paris"))`

The bot uses **AsyncIOScheduler**, not BackgroundScheduler. AsyncIOScheduler shares the asyncio event loop with the main app (Telegram polling via python-telegram-bot). It does NOT have its own thread pool.

### Revised root cause hypothesis

A synchronous (blocking) call inside an async scheduled job blocks the entire event loop, including:
- Telegram polling (incoming /commands queue silently)
- Scheduler dispatcher (cannot fire next due jobs)
- All concurrent async tasks

The "missed by 20-23s" batches in logs match exactly when gmail_ingest is running. google-api-python-client is **synchronous**; each gmail call blocks the loop for ~20s. During that 20s, other jobs scheduled at the same hour offset queue up.

The "11:15 missed by 31min" is the smoking gun: ONE blocking call hung for 31+ minutes without a timeout. Most likely candidates:
1. Google API call without explicit timeout, hit network hang
2. yfinance call (synchronous library) waiting for slow Yahoo response
3. anthropic SDK sync client without `timeout=N` param
4. Any `requests.get(...)` without timeout

After this 31+ min hang, the event loop never recovered.

### Revised action items (override original P2 items above)

- [P2] Audit all I/O in async scheduled jobs for synchronous blocking calls
- [P2] Wrap blocking I/O in `await asyncio.to_thread(sync_func, *args)` (Python 3.9+)
- [P2] Add explicit timeouts to all external API SDKs (anthropic, google-api-python-client, yfinance, requests)
- [P2] Consider `asyncio.wait_for(coro, timeout=N)` wrapper on each scheduled job
- [P2] Investigate gmail_ingest 20s baseline — async alternative or to_thread wrapping

### Why the original hypothesis was wrong

Claude (me) pattern-matched "APScheduler hang" to "ThreadPoolExecutor saturation" without grep-ing the code first. The actual `AsyncIOScheduler` import was discoverable in one command. Principle: **read the actual code before hypothesizing root cause**, even when a pattern feels familiar. Caught within 12h of postmortem writing during Sprint 1.1 pre-flight.

---

## Phase B audit empirical confirmation (Day 4 — 2026-05-15)

Day 3 evening postmortem hypothesized "AsyncIOScheduler shares asyncio event loop with Telegram polling; sync blocking call inside async job stalls the loop." Phase B audit empirically confirms this is **systemic**, not isolated to one job.

### Quantified state

    sched.add_job sites: 23/23
    async def jobs:      23/23  (every job runs in event loop)
    sync def jobs:        0/23  (no threadpool isolation by APScheduler)
    asyncio.to_thread:    0     (no manual sync-I/O isolation either)
    run_in_executor:      0
    asyncio.wait_for:     0     (no timeout protection on any job)

**Interpretation**: every APScheduler job in bot/main.py runs in the event loop with zero sync-I/O isolation and zero timeout protection. The Day 3 catastrophic "missed by 31min" hang was not a fluke — it is a structural fragility that will recur whenever any of these 23 jobs makes a sync I/O call exceeding ~30s (network hang, API throttle, sentence-transformers warmup, large sqlite query).

### Risk-ranked suspects (frequency × likelihood of sync I/O)

| Frequency | Job | Sync I/O risk | Priority |
|---|---|---|---|
| 1h | ingest_gmail_job | google-api-python-client sync, no built-in timeout | **P0** |
| 1h | score_pending_signals_job | anthropic SDK sync; chronic "missed by 20-33s" observed | **P0** |
| 1h | scheduled_materiality_v2_job | anthropic SDK sync | **P0** |
| 30min | scheduled_classify_signal_types_job | anthropic Haiku sync | **P0** |
| 1h | update_echo_clusters_job | sentence-transformers BGE inference CPU-bound | P1 |
| 15min mkt | price_monitor_job | yfinance (sync requests internally) | P1 |
| 1h | scheduled_recompute_materiality_boost_job | sqlite + math | P2 |
| 1h | heartbeat | sqlite + JSON write | P2 |
| daily | daily_digest_job | anthropic + sqlite | P1 |
| daily | daily_resolve_job | yfinance + sqlite | P1 |
| daily | scheduled_insider_refresh_job | EDGAR HTTP sync | P1 |
| daily | scheduled_8k_scan_job | EDGAR HTTP sync | P1 |
| daily | scheduled_buy_cluster_scan_job | EDGAR + yfinance | P1 |
| weekly | weekly_*_job (3 jobs) | sqlite | P3 |
| daily | daily_backup_job | filesystem + sqlite atomic | P3 |
| cron | refresh_source_half_lives_job, recalibrate_credibility_brier_job | sqlite | P3 |
| cron | daily_calendar_refresh_job, daily_crypto_zone_job, scheduled_resolve_buy_cluster_returns_job, resolve_journal_decisions_job | mixed sqlite/API | P2 |

Chronic "missed by 20-33s" entries in bot.log are sub-threshold manifestations of the same fragility. P0 jobs all run hourly with slow remote API dependencies — when any hangs beyond 60s without timeout, the next hourly batch is dropped and the event loop accumulates delay.

### Recommended Sprint 1.2 fix architecture

Each async job performing sync I/O should be wrapped:

    async def ingest_gmail_job():
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_sync_ingest_gmail_impl),
                timeout=120.0
            )
        except asyncio.TimeoutError:
            log.warning("ingest_gmail_job timeout after 120s")
        except Exception:
            log.exception("ingest_gmail_job crashed")

Releases event loop during sync I/O + hard timeout. Same shape for all 23 jobs (~30 min/job, ~6h full sweep, ~2h P0 critical path on 4 jobs).

### Defensive interim mitigation (observation window 2026-05-15 → 2026-06-10)

No code change. Operational compensation:
- Tier 2 detector `scripts/bot_health_check.sh` catches scheduler hang within ~7h (validated Day 3 empirically — heartbeat freshness gate triggered)
- Manual restart procedure: `PROCEDURE_URGENCE.md` Scenario 1
- AsyncIOScheduler `misfire_grace_time` could be tuned longer but doesn't fix root cause

Risk acceptance: another hang during 28-day window is **likely** (chronic "missed by 20-33s" is ongoing). Cost = ~24h ingestion loss + 5min manual restart. Acceptable vs piecemeal fix violating observation discipline.

### Status

- Phase B audit: complete, empirical confirmation captured
- Hypothesis "structural fragility" upgraded to confirmed diagnosis
- Sprint 1.2 P0 batch defined (4 jobs, ~2h critical path)
- Full sprint scope: 23 jobs, ~6h batched with shared helper
