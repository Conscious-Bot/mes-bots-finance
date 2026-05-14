# Anthropic API down / degraded

## Symptoms

- `/brief`, `/digest` Telegram commands return "LLM call failed" or hang
- Crons `score_pending_signals_v2`, `materiality_boost`, `journal_resolve`, `scheduled_digest_job` log `anthropic.APIError` or `httpx.ConnectError`
- `shared/llm.py` raises `anthropic.RateLimitError` (different cause but same downstream effect)
- `/cost_trajectory` MTD shows no new entries since outage start

## Triage (5 min)

1. Check Anthropic status page: https://status.anthropic.com
2. Tail logs for actual error class:
```bash
   tail -500 bot.log | grep -i "anthropic\|llm\|claude" | tail -30
```
3. Test direct API call from venv:
```bash
   source venv/bin/activate
   python -c "
   from shared import llm
   r = llm.complete_haiku('reply with exactly: OK', max_tokens=10)
   print(repr(r))
   "
```
4. Determine if it's full outage (5xx) vs auth issue (401) vs rate limit (429) vs cost limit hit on Anthropic side.

## Recovery

### If outage is Anthropic-side (5xx, status page red)
- **Do NOT** restart the bot. Crons that need LLM will fail gracefully and retry next cycle.
- Ingestion crons (gmail, edgar, prices) keep running — signals stack up in DB unscored, this is fine.
- When Anthropic recovers: `score_pending_signals_v2` cron next hour will drain the backlog naturally.

### If auth issue (401)
1. Check ANTHROPIC_API_KEY in .env not expired:
```bash
   grep ANTHROPIC_API_KEY .env | head -1
```
2. If rotated key, update .env + restart bot:
```bash
   pkill -f "python.*bot.main"
   sleep 2
   nohup python -m bot.main > bot.log 2>&1 &
```

### If rate limit / cost cap
1. Check `/cost_trajectory` for MTD spend
2. If we hit Anthropic-side cost cap: increase cap in Anthropic console, **not** in our config
3. If hitting RPM rate limit: lower concurrency in `score_pending_signals_v2` (currently sequential, so this is unlikely)

## Prevention hooks

- Telegram alert when bot.log accumulates >5 `anthropic.APIError` in 1h window
- `/cost_trajectory` weekly cron Sun 22:00 catches budget drift early (already shipped)
- Consider: fallback path that defers scoring instead of erroring (signals re-eligible next cycle automatically via `score_pending` design)

## References

- `shared/llm.py` — cascade Haiku/Sonnet/Opus
- ADR-002 (when written) — cascade routing rationale
