# Pipeline coherence audit — score field deprecation gap

**Created**: 2026-05-15 morning Day 4 reopen
**Triggered by**: /digest empty output investigation (user reported "bizarre")

## Empirical finding

The `signals.score` column (legacy materiality score) is **deprecated but not removed**. Current pipeline writes to materiality_v2 fields (`impact_magnitude`, `reversibility`, `time_to_realization`, `materiality_breakdown`) but does NOT update the legacy `score` field.

### Evidence (2026-05-15 12:35 KST, ~92 signals total)

- 61 signals with `score IS NOT NULL` — all from 2026-05-11 06:10 to 2026-05-13 02:01
- 31 signals with `score IS NULL` — all from 2026-05-13 04:29 to 2026-05-15 01:33

**Cutoff point**: 2026-05-13 morning. Coincides with materiality_v2 chained pipeline activation (Day 2 marathon afternoon).

The 31 NULL-score signals DO have materiality_v2 fields populated correctly. Only the legacy `score` field is orphaned.

### Downstream impact

`/digest` (intelligence/digest.py:316) filters `AND COALESCE(s.score, 0) >= 3`. NULL coalesces to 0, fails >=3 threshold. 16 of 16 signals in last 24h excluded. User-facing message: "Aucun signal pertinent sur les dernieres 24h."

`/digest` ordering also broken: `ORDER BY (COALESCE(s.score, 0) * COALESCE(s.materiality_boost, 1.0)) DESC` — multiplying NULL-coalesced 0 by boost yields 0 for all recent signals.

Potential other consumers (NOT yet audited):
- `cmd_brief` (chunk 8 ritual)
- `cmd_signals_by_type` (chunk 6)
- prediction auto-registration
- Brier recalibration

User-facing impact: morning ritual `/digest` has been silently broken ~48h since 2026-05-13 cutoff.

## Root cause hypothesis

Materiality v1 → v2 migration was **partial**:
- v2 pipeline writes new fields ✓
- No derivation step computes legacy `score` from v2 fields ✗
- Downstream consumers (`/digest`) not migrated to v2 ✗

No ADR documents this transition. Materiality_v2 was added during Day 2 marathon as "chained scoring" without explicit deprecation/migration plan for legacy `score`.

## Validates friction items (2026-05-14 batch)

- **Item 4** (/brief and /digest review together) — confirmed: /digest filter is the broken layer
- **Item 5** (metrics proliferation, balanced sans explication) — confirmed: dual scoring systems without unified surface
- **Item 6** (whole pipeline coherence) — confirmed: interpretation (v2) and summary (/digest) layers misaligned

User's intuition was a real architecture gap, not just UX preference.

## Disposition

**No fix tonight.** Observation discipline applies (KPI #2 timer to 2026-06-10). Fixing /digest filter is behavior change.

**Sprint 1.2 critical input.** When /digest extracts to `bot/handlers/ritual.py` (Sprint 1.1 chunk 8), the redesign MUST:
1. Migrate filter from `score` to materiality_v2-derived score
2. Decision: deprecate `score` column outright, or compute on-demand from v2 fields
3. Audit `/brief`, `/signals_by_type`, prediction auto-registration for same gap

**Workaround for visibility now**: SQL query against v2 fields shows what /digest would return:

    SELECT signal_type, title, src.name as source,
           ROUND(impact_magnitude, 1) as impact,
           ROUND(reversibility, 1) as rev,
           ROUND(materiality_boost, 1) as boost,
           ROUND((COALESCE(impact_magnitude, 0) * COALESCE(reversibility, 0) * COALESCE(materiality_boost, 1)), 1) as v2_score
    FROM signals s LEFT JOIN sources src ON s.source_id = src.id
    WHERE s.timestamp > datetime('now', '-24 hours')
    ORDER BY v2_score DESC
    LIMIT 10;

## Action items

- [P1] Sprint 1.2 chunk 8 redesign — migrate /digest filter + ordering to v2 fields
- [P2] Audit /brief, /signals_by_type, prediction registration for same `score` dependency
- [P3] Decision: deprecate score column or keep as derived
- [P3] Retroactive ADR documenting materiality v1 → v2 transition

## References

- `friction.md` 2026-05-14 — items 4, 5, 6 (now empirically validated)
- `docs/handler-audit.md` — /digest already marked U, this finding reinforces rationale
- `intelligence/digest.py:301-360` — generate_unified_digest with broken filter
- `intelligence/materiality_v2.py:129` — score_pending_signals_v2 (v2 scoring path)
- `bot/main.py:1921` — score_pending_signals_job cron 1h
