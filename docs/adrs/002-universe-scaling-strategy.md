# ADR-002: Universe scaling strategy (vertical vs horizontal)

**Status**: Proposed (stub, to be developed post-J+28 with empirical data)
**Created**: 2026-05-15
**Trigger**: 2026-05-15 conversation suggesting "render bot universal / milliers de tickers"

## Context

mes-bots-finance currently tracks 178 tickers (22 core / 81 watch / 75 extended). User raised possibility of universal scaling (1000+ tickers). The decision has structural implications for stack contracts (Python 3.14 + SQLite + APScheduler), cost trajectory (currently $15/mo projected), AsyncIOScheduler robustness (already structurally fragile per Phase B audit Day 4), and KPI integrity (KPI #2 J+28 batch not yet resolved as of decision moment).

## Decision constraint

PHILOSOPHY.md High Standard Mode (2026-05-13): "Plus de précision dans la mesure > plus de surface monitorée. Les tickers, handlers, sous-groupes qui ne produisent pas de matière décisionnelle sur 90j sont candidats à suppression."

Universal scaling appears to violate this constraint UNLESS justified by post-J+28 empirical evidence that current pipeline produces calibrated decisions on existing universe.

## Options under consideration

### Option A — Maintain current scale (status quo)
~178 tickers, focus depth + materiality + thesis quality. Add 0-3 tickers post-J+28 if Gates 1-4 (from TODO.md) pass.

### Option B — Moderate horizontal (3-5x)
~500-1000 tickers, requires:
- AsyncIOScheduler hardening (Sprint 1.2 P0 prerequisite)
- Cost trajectory model justifying $60-100/mo
- Empirical KPI #2 data validating current calibration on smaller universe first
- Universe gating policy (criteria for inclusion/exclusion)

### Option C — Full horizontal (10x+)
~2000+ tickers. Requires significant architectural changes:
- Possibly outgrows SQLite (concurrent writes), trigger Postgres ADR
- LLM cost trajectory exceeds budget unless aggressive caching/tier downgrade
- Signal volume requires re-design of /digest, /brief, ritual handlers
- Predictions cluster risk amplified

### Option D — Vertical depth (anti-expansion)
Reduce to ~50 core + ~50 watch, increase decisional quality per ticker. Focus on track record per name. Path 5/6 acquihire narrative argument: "30 named theses with calibrated Brier" defends better than "1000 watched tickers with no Brier."

## Decision

DEFERRED to post-J+28 (2026-06-10) when empirical data on KPI #2 + KPI #3 (Brier rolling 90d) available.

Until then:
- DEFAULT: Option A (status quo + max 3 candidate adds from thesis-candidates-queue)
- NO commitment to B/C/D before empirical KPI evidence
- Sprint 1.2 P0 (AsyncIOScheduler hardening, /digest v2 migration) is a PREREQUISITE for any consideration of B or C

## Decision trigger conditions (when to re-open this ADR)

1. KPI #2 batch resolved (45 predictions, ~10 juin 2026)
2. KPI #3 Brier rolling 90d has N≥10 resolutions (probably ~juillet-août 2026)
3. Cost projection update with empirical N=2 months data
4. AsyncIOScheduler hardening completed (Sprint 1.2 P0)

If at trigger time KPI #2 + KPI #3 show calibrated discrimination → Option B becomes evaluable. If they don't → Option D becomes the default.

## References

- PHILOSOPHY.md High Standard Mode
- TODO.md "Thesis candidates queue" + Gates 0-4
- docs/thesis-candidates-queue.md
- docs/post-mortems/2026-05-14-apscheduler-hang-restart-cascade.md (Phase B audit)
- friction.md 2026-05-15 afternoon entry
