# Post-mortems

Blameless after-the-fact analyses of incidents that materially impacted the system.

## When to write one

Threshold: any incident that meets ≥1 of:
- Bot down >2h
- Data loss (signals, predictions, decisions)
- KPI #2 (Brier resolution cadence) blocked or skipped
- Silent failure that ran undetected >24h
- Recovery required manual intervention from backup or schema migration

## Template

Each post-mortem includes:
1. **Timeline** — UTC, what happened when
2. **Impact** — concretely what broke, who/what was affected
3. **Root cause** — the actual mechanism (not "human error")
4. **What worked** — detection, telemetry, runbook that helped
5. **What failed** — gaps in detection or recovery
6. **Action items** — specific tickets to file, owner = self, due dates

Filename convention: `YYYY-MM-DD-short-title.md`
