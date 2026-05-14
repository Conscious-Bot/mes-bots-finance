# APScheduler job stuck / runaway CPU

## Symptoms

- `ps aux` shows the bot at >50% CPU sustained (vs normal <5%)
- `bot.log` shows the same cron job logging start but never end
- APScheduler logs `Execution of job "<name>" skipped: maximum number of running instances reached (1)`
- New jobs missing their schedule (next-run-time keeps slipping)

## Triage (3 min)

1. Identify the stuck job:
```bash
   tail -200 bot.log | grep -E "Running job|Job .* (executed|finished|raised)" | tail -20
```
   Look for a job with a "Running job" entry but no matching "executed"/"finished" within its expected window.
2. Snapshot what python is doing (macOS-friendly):
```bash
   PID=$(pgrep -f "python.*bot.main" | head -1)
   sample $PID 5 -file /tmp/bot_sample.txt
   head -100 /tmp/bot_sample.txt
```
3. Common culprits:
   - LLM call without timeout hanging
   - SQLite WAL-checkpoint deadlock (two long-held transactions)
   - yfinance scraping page that returns slow / never-EOF
   - Infinite loop in newly-deployed code

## Recovery

### Hot restart
```bash
pkill -f "python.*bot.main"
sleep 3
pgrep -fl "python.*bot.main"  # should be empty
nohup python -m bot.main > bot.log 2>&1 &
sleep 5
tail -30 bot.log
```

### If the same job re-stucks within an hour after restart
Code-level fix required. Disable that single cron temporarily:
1. Open `bot/main.py`, find the `scheduler.add_job(<stuck_func>, ...)` line
2. Comment it out + add `# DISABLED YYYY-MM-DD: investigating loop, ticket #<n>`
3. Restart bot
4. File post-mortem in `docs/post-mortems/`

## Prevention hooks

- All `add_job` calls should have `misfire_grace_time=300` + `max_instances=1` (verify via grep when touching bot/main.py)
- All `requests.get` and `anthropic.complete` calls need an explicit `timeout=` argument (verified for edgar via Sprint 1.2 item 3a; gmail uses google-api-python-client defaults)
- Consider: add a per-job timeout wrapper that raises after N seconds and logs

## References

- `bot/main.py` — APScheduler setup (search `scheduler.add_job`)
- `shared/data_source_base.py:retry_with_backoff` — already bounded retries
- ADR-002 (when written) — LLM cascade should document timeouts
