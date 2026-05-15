# ADR 003 — Portfolio Targets PIT Bitemporal Multi-Account

**Status**: Accepted
**Date**: 2026-05-15
**Decision-makers**: Olivier Legendre
**Context**: Day 4 evening, post-allocation document received, capital deployment 67% (€43K/€64K)

---

## 1. Context

User has two brokerage accounts with structurally different rebalancing constraints:

- **PEA (Plan Epargne Actions)** — €11,384, LOCKED. French tax-advantaged. Selling = loses PEA fiscal status. Effectively immutable for current generation of positions.
- **Trade Republic (TR)** — €32K executed + €21K cash to deploy = €53K target. Active rebalancing in progress over 8-12 week phasing.

Plus a target allocation document defining 37 portfolio targets (executed/planned/locked/watchlist_conditional/dropped) with EUR amounts, narratives, priorities, DCA phasing weeks.

The bot's positions table did not distinguish accounts. There was no concept of target vs actual. KPI 4, 5, 6 were inert.

## 2. Decision

Add `account` column to positions table. Create `portfolio_targets` table with PIT bitemporal pattern (active_from / active_to). Status enum covers full lifecycle: executed, planned, locked, watchlist_conditional, dropped.

```sql
CREATE TABLE portfolio_targets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT NOT NULL,
  account TEXT NOT NULL,
  bucket TEXT,
  target_eur REAL NOT NULL,
  target_weight_pct REAL,
  narrative TEXT,
  priority TEXT,
  status TEXT NOT NULL DEFAULT 'planned',
  phase_week INTEGER,
  active_from TEXT NOT NULL DEFAULT (datetime('now')),
  active_to TEXT,
  source_doc TEXT,
  thesis_id INTEGER REFERENCES theses(id),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  notes TEXT
);
```

## 3. Consequences

### Positive
- KPI 4 panic_sell tracking now possible (positions tagged by account, by thesis_id linkage)
- KPI 5 decisions journalized references real positions, not abstract holdings
- KPI 6 TWR baseline starts from current market value (forward-tracking honest about no entry data)
- Drift report visible target vs actual per account
- PIT bitemporal preserves target evolution history (allocations change quarterly, audit-grade)
- Multi-account separation prevents drift confusion between LOCKED (PEA) and active (TR)

### Negative
- positions.account default 'TR' may mis-categorize legacy entries (NVDA test soft-deleted to avoid this)
- SQLite drop_column not supported, downgrade path imperfect (acceptable for forward-only schema evolution)
- Watchlist conditional priority status creates ambiguity vs target_eur (eur values are estimates 1500-2000 ranges)

## 4. Implementation

- Alembic migration 0002 (this commit)
- scripts/import_portfolio_targets.py seeds 37 target rows from allocation document
- scripts/import_positions_legacy.py imports 21 actual positions (6 PEA + 15 TR executed)
- storage.compute_drift_report() helper
- scripts/drift_report.py outputs Markdown
- Handlers /target_set /target_compare /portfolio_drift NOT implemented (Sprint 1.2 post-J+28 per V4 consolidation spec)

## 5. Open questions

- Currency handling: legacy import stores cost_basis in EUR uniformly. Native currency tracking deferred to future schema (Sprint 1.3 candidate).
- Phase_week tracking does not auto-trigger reminders. /portfolio_drift will surface DCA week status. Reminders deferred.
- 7011.T MHI has two target rows (executed €2500 + planned topup €1000). Final state €3500 single row OR two-row history? Decision: single row €3500 with notes capturing the topup intent.

## 6. References

- ADR-001 PIT bitemporal credibility ledger (same pattern, different domain)
- docs/personal/handlers-consolidation-plan.md V4 (Sprint 1.2 handler consolidation)
- Source document: user-provided allocation plan dated 2026-05-15
