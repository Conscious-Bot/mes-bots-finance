# 2026-05-14 — uptime-monitor case-sensitivity bug

## Timeline (UTC)

- **2026-05-11 09:34**: `uptime_monitor.sh` logs first `FAIL bot down`. Bot was actually running. First false negative.
- **2026-05-11 09:34 → 2026-05-13 11:15**: ~400 continuous `FAIL` entries in `uptime.log`. Bot was running for most of this period. Hourly rate-limited Telegram alerts fired, likely muted by operator.
- **2026-05-13 ~11:30**: Day 2 marathon begins. Bot restarted multiple times, each followed by false FAILs.
- **2026-05-14 01:30**: Bot started as PID 8112 (current alive instance).
- **2026-05-14 ~03:55**: New diagnostic session starts. Takes `uptime.log` at face value, concludes "bot down 56h+" — wrong.
- **2026-05-14 ~04:18**: Manual restart attempt (PID 9549) returns `telegram.error.Conflict: terminated by other getUpdates request`. First empirical evidence the prior "bot down" diagnosis was incorrect.
- **2026-05-14 ~04:26**: Side-by-side `pgrep -f` vs `pgrep -fi` test reveals case-sensitivity bug.
- **2026-05-14 ~04:30**: Patch shipped: `crons/uptime_monitor.sh` and `PROCEDURE_URGENCE.md` (1-char change `-f` → `-fi`).
- **2026-05-14 ~04:35**: First true `OK alive` entry in `uptime.log`.

## Impact

- **422 false FAIL entries** in `uptime.log` accumulated over 3+ days.
- **KPI #1 (uptime > 95%)** measurement was bound to a broken detector since metric creation — effectively unmeasurable until today.
- **Hourly Telegram alerts** caused alert-fatigue. Operator (correctly) ignored them. Real safety net disabled.
- **~2h of diagnostic work** in current session based on false premise.
- **One failed restart attempt** (PID 9549) injected a crash trace into `bot.log` and risked disrupting the legitimate Telegram polling session of PID 8112.
- **SESSION_STATE claims** like "Bot PID 8112 vivant" used the same broken `pgrep -fl`, making the claim structurally unverifiable at authoring time.

## Root cause

`pgrep -f` is case-sensitive on macOS/BSD. The macOS Python binary path is `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python` — capital P. The detection pattern `python.*bot\.main` (lowercase) never matched. This was true from the day `uptime_monitor.sh` was authored (2026-05-11). `PROCEDURE_URGENCE.md` inherited the same bug.

**Compounding diagnostic error**: the same broken pattern was reused in 4+ consecutive interactive diagnostic commands without ever cross-checking against `ps aux` raw output, which would have immediately revealed the capital-P `Python` invocation.

## What worked

- **Telegram Conflict exception** — Server-side enforcement of single-instance polling raised the error when the failed restart collided with the legitimate session. First concrete signal contradicting the false diagnosis.
- **lsof on PID 8112** — Showed fd 1w + 2w pointing to bot.log inode, confirming PID 8112 was the legitimate writer.
- **DB liveness query** — `SELECT count(*) FROM signals WHERE timestamp > datetime('now','-30 minutes')` returned 6, definitive proof of real-time ingestion.
- **Sprint 1.2 item 4 structure** — `docs/post-mortems/` was created ~6h before this incident and was ready to receive its first entry. Best possible validation of the structure choice within hours of authoring.

## What failed

- **No empirical validation at script authoring time** — Manual run + alive-case assertion was never done. `uptime_monitor.sh` shipped untested in happy path.
- **No fallback signal in detector** — Single detection method (pgrep -f). A secondary check (DB activity, bot_state.json heartbeat freshness, lsof of expected files) would have caught the bug.
- **KPI #1 inherited the broken detector silently** — Metric definition in `KPI_DASHBOARD.md` was "count OK alive / total lines uptime.log" without independently validating the detector. **Metrics that depend on detectors must validate the detector independently.**
- **Multiple diagnostic iterations confidently restated the wrong conclusion** — "Bot down 56h", "bot hung", etc., each new diagnosis built on the previous false premise. The system meant to mechanize discipline against this exact bias (confident conclusion without testing) was the victim of the bias.
- **Alert fatigue removed the safety net** — 422 false alerts trained operator to mute the Telegram channel.

## Action items

1. **DONE 2026-05-14** — Patch `crons/uptime_monitor.sh` (case-insensitive `-fi`).
2. **DONE 2026-05-14** — Patch `PROCEDURE_URGENCE.md` scenario 1 (case-insensitive `-fli`).
3. **TODO due 2026-05-21** — Add `scripts/bot_health_check.sh` combining: pgrep -fi + DB signals last 2h + bot_state.json heartbeat < 90min. Replaces single-signal uptime check.
4. **TODO due 2026-05-21** — Add test in `tests/test_smoke_observation.py` asserting `pgrep -fi "python.*bot\.main"` matches when bot is running. Regression guard.
5. **TODO due 2026-05-15** — Purge `uptime.log` of pre-2026-05-14 12:26 KST FAIL entries OR prepend header documenting them as false negatives.
6. **TODO due 2026-05-28** — TZ standardization. Currently bot.log/state.json use CEST, backup.log UTC, shell scripts KST. Pick one (UTC recommended per CONVENTIONS.md §1), document, migrate.
7. **DEFERRED P2** — `bot_state.json` stale fields: `predictions_pending_resolution`, `active_theses_count`, `bot_start_ts` set at init, never updated. Heartbeat field works. File ticket separately.
8. **PROCESS LESSON** — Add to `CONVENTIONS.md`: "Any detector backing a KPI must have an independent validation test (positive + negative case) at authoring time. KPI inheritance from a detector without separate verification is forbidden."

## References

- `crons/uptime_monitor.sh` (patched this cycle)
- `PROCEDURE_URGENCE.md` (patched this cycle)
- `crons/uptime_monitor.sh.bak_20260514_122633` (pre-patch forensic snapshot)
- `bot.log.before_restart_20260514_122000` (forensic archive of pre-incident bot.log)
- Adjacent runbook: `docs/runbooks/cron-loop.md`
