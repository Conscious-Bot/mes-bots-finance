# Gmail OAuth token expired / refresh fails

## Symptoms

- Cron `ingest_gmail_job` logs `google.auth.exceptions.RefreshError`
- `data_sources/gmail_.py` returns `{"fetched": 0, "persisted": 0}` consistently
- Telegram `/health` shows `gmail_last_signal_at` older than 6h
- `token.json` mtime no longer updates (refresh stopped happening)

## Triage (5 min)

1. Check token.json expiry:
```bash
   python -c "
   import json
   t = json.load(open('token.json'))
   print('expiry:', t.get('expiry'))
   print('has_refresh:', bool(t.get('refresh_token')))
   "
```
2. Test get_service() directly:
```bash
   python -c "
   from data_sources.gmail_ import get_service
   svc = get_service()
   print('OK service:', svc)
   "
```
3. If refresh_token missing or revoked: token was invalidated server-side (Google may revoke after 6 months of inactivity, or after password change, or if user manually revoked at https://myaccount.google.com/permissions).

## Recovery

### Refresh token still valid (most common case)
The google-auth library auto-refreshes on next call. If it failed once, restart bot:
```bash
pkill -f "python.*bot.main"
sleep 2
nohup python -m bot.main > bot.log 2>&1 &
```

### Refresh token revoked (must re-authorize)
1. Delete stale token:
```bash
   cp token.json token.json.bak_$(date +%Y%m%d_%H%M%S)
   rm token.json
```
2. Re-run OAuth flow interactively (will open browser):
```bash
   python -c "
   from data_sources.gmail_ import get_service
   svc = get_service()
   print('OK new token issued')
   "
```
3. Verify new token.json written + test fetch:
```bash
   python -m data_sources.gmail_
```
4. Restart bot.

## Prevention hooks

- Telegram alert if `gmail_last_signal_at` > 6h during business hours
- Sunday weekly health check includes gmail freshness verification
- Backup `token.json` daily alongside `data/bot.db` (currently not in backup.sh — TODO)

## References

- `data_sources/gmail_.py:get_service()` — token refresh logic
- `credentials.json` — OAuth client config (do NOT commit, already in .gitignore)
