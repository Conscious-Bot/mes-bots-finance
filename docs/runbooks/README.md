# Runbooks

Operational recovery procedures for known failure scenarios.

Each runbook follows the structure:
1. **Symptoms** — how to detect this is happening
2. **Triage** — verify diagnosis (5 min budget)
3. **Recovery** — executable steps to restore service
4. **Prevention hooks** — what to add/monitor to avoid recurrence

Convention: file names are `<failure-scenario>.md` in kebab-case.

## Index

- `anthropic-down.md` — Anthropic API outage / 5xx
- `gmail-oauth-expired.md` — Gmail OAuth token refresh fails
- `yfinance-corrupted.md` — yfinance returns None/garbage on known tickers
- `db-corrupted.md` — SQLite database corruption
- `cron-loop.md` — APScheduler job stuck / runaway CPU

See `docs/failure_modes.md` for the strategic catalog of failure modes that drive what runbooks get written.
