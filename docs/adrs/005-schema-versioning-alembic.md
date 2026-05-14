# ADR-005: Schema Versioning Strategy with Alembic

## Status
**Accepted** — Sprint 1.3, 14 May 2026

## Context

Until Sprint 1.3, the DB schema lived only as raw SQL inside `shared/storage.py`:
- Schema initialization was implicit (tables auto-created on first call)
- No version tracking, no migration history
- No rollback mechanism if a schema change went wrong
- CI tests couldn't bootstrap a fresh DB (used `pytest.skip` workaround on 2 tests)
- **Sprint 1.6 PIT bitemporal will require disciplined schema evolution** (6+ new columns across 5 tables, new `credibility_history` ledger)

The project has 28 tables and 42 indexes. Without versioning, every future change becomes a risky manual operation with no audit trail.

## Decision

Adopt **Alembic** for schema migration management:

1. **Schema-as-migration** — each schema change becomes a versioned Alembic revision file in `scripts/alembic/versions/`
2. **Production baseline at 0001** — existing 28 tables + 42 indexes captured verbatim in migration `0001_initial_schema_baseline.py`
3. **Programmatic entry point** — `shared.storage.bootstrap_schema(db_path)` wraps `alembic upgrade head` + sets WAL mode, usable from tests/CI/scripts
4. **Convenience targets** — Makefile `db-bootstrap`, `db-current`, `db-history`, `db-migrate`, `db-revision`

## Alternatives considered and rejected

### SQLAlchemy ORM + autogenerate
Would require defining ~28 model classes (~2-3 days work), then using Alembic autogenerate.
**Rejected because**:
- Project uses raw SQL throughout (`storage.py` is dict-based, not ORM)
- Converting to ORM is its own massive refactor (out of scope Phase 1)
- Autogenerate is fragile with complex SQL features (CHECK constraints, partial indexes, JSON columns we use)

### Manual SQL migration scripts (numbered files run sequentially)
**Rejected because**:
- Reinventing the wheel — every migration framework solves this
- No automatic upgrade/downgrade symmetry
- No version tracking table
- No transactional safety on multi-statement migrations

### Custom migration framework
**Rejected because**:
- NIH antipattern
- Alembic is mature (15+ years), well-documented, industry-standard
- Acquihire/Path 5: buyers expect Alembic or similar, not bespoke tooling

## Consequences

### Positive
- Schema is versioned + traceable in git history
- CI tests no longer skip (2 smoke tests now actively pass via `bootstrap_schema()`)
- Sprint 1.6 PIT bitemporal can be implemented as discrete Alembic migrations safely
- Fresh installs work in one command: `make db-bootstrap`
- Each schema change has a paper trail (every migration is reviewable like code)
- `alembic downgrade` provides rollback (for non-destructive changes)

### Negative / Cost
- Adds `alembic>=1.13` + transitive `SQLAlchemy>=2.0` + `Mako` (~3 MB total)
- Future schema changes require Alembic ceremony (`make db-revision MSG="..."`) instead of raw SQL edits in `storage.py`
- Onboarding step: contributors must understand the migration workflow

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Schema drift if someone edits `storage.py` table-creation directly | ADR-005 documented as canonical workflow; reviewers enforce |
| `alembic_version` table corruption requires manual recovery | Included in daily backups via `scripts/backup.sh` |
| Migration file conflicts during parallel development | Single-developer project for now; non-issue |
| `alembic upgrade head` fails mid-migration on production | All changes tested on copy of DB before production apply |

## Implementation

### Phase A — Setup (this Sprint 1.3)
- ✅ `pip install alembic>=1.13` → captured in `requirements.txt`
- ✅ `alembic init scripts/alembic` → directory structure created
- ✅ `alembic.ini` configured with `sqlalchemy.url = sqlite:///data/bot.db`
- ✅ Migration `0001_initial_schema_baseline.py` generated from production schema
- ✅ `alembic stamp head` on production → DB at version `0001` without re-execution
- ✅ `shared.storage.bootstrap_schema()` with WAL mode wrap
- ✅ Makefile targets `db-*`
- ✅ 2 smoke tests refactored to use `bootstrap_schema()` instead of `pytest.skip`

### Phase B — Workflow for future schema changes
1. Plan the change in raw SQL: `ALTER TABLE foo ADD COLUMN bar TEXT`
2. Generate empty revision: `make db-revision MSG="add bar column to foo"`
3. Edit generated file in `scripts/alembic/versions/0002_*.py`:
```python
   def upgrade():
       op.execute("ALTER TABLE foo ADD COLUMN bar TEXT")
   def downgrade():
       op.execute("ALTER TABLE foo DROP COLUMN bar")
```
4. Test on snapshot: `cp data/bot.db /tmp/test.db && python -c "from shared.storage import bootstrap_schema; bootstrap_schema(db_path='/tmp/test.db')"`
5. Verify backup exists (daily 04:00 cron should suffice)
6. Apply to production: `make db-migrate`
7. Verify: `make db-current` shows new version

### Phase C — Sprint 1.6 PIT bitemporal (depends on this ADR)
4-6 migrations across signals/predictions/decisions/prices + new `credibility_history` table. Each migration discrete, reviewable, reversible (where SQLite supports it).

## References

- Alembic documentation: https://alembic.sqlalchemy.org
- Sprint 1.3 commits: pending (this ADR + 0001 baseline + bootstrap_schema + tests)
- Depends on: nothing (foundational)
- Enables: ADR-001 PIT Bitemporal Credibility implementation (Sprint 1.6)

## Date
2026-05-14 (Sprint 1.3, J+1 of observation period)
