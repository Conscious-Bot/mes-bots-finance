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
