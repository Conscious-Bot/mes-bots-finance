# crons/ — OS-level cron scripts

This directory contains shell scripts called by the system crontab (OS-level)
for tasks NOT scheduled by the bot's internal APScheduler.

## Current scripts

### `uptime_monitor.sh`
- **Cron**: `*/5 * * * *` (every 5 min)
- **Purpose**: Heartbeat check, logs to `uptime.log`. Detects bot crashes.
- **Why OS-level**: Needs to run when bot is DOWN (APScheduler unavailable).

### `resolve_predictions.sh`
- **Cron**: not currently scheduled (manual or scheduled separately)
- **Purpose**: Triggers prediction resolution batch.

## Removed scripts

### `daily_backup.sh` (removed 2026-05-16)
- **Previous cron**: `15 23 * * *`
- **Removed because**: redundant with `scripts/backup.sh` which is called by
  APScheduler at 04:00 via `daily_backup_job` (bot/main.py).
- **Replacement**: see `scripts/backup.sh` — more robust:
  - Atomic SQLite `.backup` API
  - Integrity check post-backup
  - Backs up to `~/backups/mes-bots-finance/` (off-project, survives repo clean)
  - 14-day rotation
- **Restore test**: `make test-restore-db` validates latest backup is restorable.

## Backup architecture (canonical, post 2026-05-16)
APScheduler (in bot.main, cron 04:00 daily)
└─> daily_backup_job()
└─> subprocess: bash scripts/backup.sh
├─> tar snapshot to ~/backups/mes-bots-finance/snapshot_<TS>.tar.gz
├─> sqlite3 atomic .backup to bot.db.<TS>
├─> integrity_check PRAGMA
└─> rotation: delete files older than 14 days

OS cron only handles uptime monitoring (which must run when bot is down).
All other periodic tasks are inside APScheduler for visibility via `/handler_stats`.
