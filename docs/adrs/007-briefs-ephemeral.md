# ADR 007 — Briefs ephemeral by design

**Date**: 21 May 2026
**Status**: Accepted
**Context**: Chantier #1 backlog item, deferred since Day 14 (20/05). Question
posed: should the markdown content of `/brief` (and by extension `/digest`)
outputs be persisted in a `briefs` table, or remain ephemeral after Telegram
delivery?

## Decision

**Ephemeral. No `briefs` table.**

`/brief` and `/digest` outputs are dynamically generated markdown derived
from already-persisted underlying state. They are sent to Telegram and not
stored elsewhere. If a brief "as of date T" is ever needed retrospectively,
it is reconstructable from the persisted source data.

## Rationale

### 1. Redundancy
Every input to a brief is already in DB:
- signals (with materiality, score, source, timestamp)
- predictions (with claim, target_date, brier_score post-resolution)
- positions + theses
- KPI snapshots (kpi_status, cost trajectory, handler stats)
- LLM cost log (llm_calls table)

Storing the generated markdown duplicates information that can be
reconstructed deterministically from these sources.

### 2. Drift hazard
A stored markdown is immutable. But the *interpretation* of underlying
state evolves: credibility scores update, materiality_v2 rubric refines,
Brier scores accumulate. A brief regenerated "as of date T" using
current methodology is more honest than a frozen historical snapshot.

The latter creates false confidence in stale judgment ("at the time we
thought signal X was high impact"); the former preserves the audit trail
of *evolving* methodology.

### 3. Path 5/6 narrative cost-benefit
The marketing argument for persistence: "show me 30 days of briefs to
prove the system works." Counter-argument: a serious due-diligence party
wants pipeline + methodology + KPI track record + commit history, not
30 markdown blobs of which 28 are similar in shape.

The artifacts that matter for Path 5/6:
- `/kpi_status` snapshot (already wired)
- Brier scores post-10/06 batch (already gated by `predictions` table)
- Audit trail of methodology evolution (CONVENTIONS.md Lessons L1-L31)
- Commit log (engineering rigor evidence)
- Friction.md + VALUE_LOG.md (lived-experience signal)

A 30-day brief archive adds noise to this signal, not strength.

### 4. PHILOSOPHY.md coherence
> "Plus de précision dans la mesure > plus de surface monitorée."

Persisting briefs adds surface (one more table, one more write path, one
more migration to maintain) without adding precision. The boucle
d'apprentissage is enriched by signals/predictions/outcomes, not by
storing rendered output.

> "Est-ce que ça enrichit la boucle d'apprentissage, ou est-ce une
> feature isolée ?"

Brief persistence is isolated. It does not feed back into prompts,
calibration, or pattern extraction. It is product hygiene at best,
bloat at worst.

### 5. Implementation cost vs ROI
Estimated 1-1.5h to ship a minimal version (schema migration + write
hook in morning_brief.py + retrieval handler). 0 marginal ROI on
decision-making during observation window (no human consumer wants
30-day archive yet). Same 1.5h is better invested in:
- letting current architecture soak until 10/06
- documenting failure modes empirically observed
- writing/reading instead of building

## Alternatives considered

### Persist full markdown in `briefs` table
**Rejected**. Reasons 1-5 above.

### Persist only the kpi_snapshot JSON at brief time
**Rejected**. KPI snapshots are already reconstructable from
`predictions`, `decisions`, `positions`, `llm_calls`. Adding a
denormalized snapshot table = same redundancy problem with smaller
surface but identical drift hazard.

### Persist briefs only on user explicit request (e.g. `/brief_save`)
**Rejected as premature**. No user has requested this. No empirical
friction observed. Build when there's a real ask, not a hypothetical
"might want this someday" rationalization.

## Consequences

### Positive
- Zero new tables, zero new write paths
- No migration to maintain
- Underlying state remains canonical source of truth
- Conforms to PHILOSOPHY.md "feature must enrich the loop" gate

### Negative (accepted)
- Cannot retrieve verbatim historical brief markdown
- If user wants "show me what bot said on date T" → must regenerate
  using current methodology (which may differ from what was actually
  sent that day)

### Mitigation
- If verbatim retrieval becomes genuinely required (external audit,
  legal discovery, user-driven demand), Telegram chat history is
  effectively a persistent log. Telegram backup ≈ brief archive.
- Backup strategy already captures `/data/bot.db` daily; the underlying
  data is preserved.

## Revisit trigger

This ADR is revisited only if:
- A real Path 5/6 acquirer or paying subscriber explicitly demands
  brief archive
- Empirical friction shows user wants to scroll their own historical
  briefs more than 3× per month (logged in friction.md)
- Telegram chat history limitations become a binding constraint

Until then: ephemeral, no code, ticket closed.

## Closing thought

This ADR is itself an artifact of decision discipline. The temptation
during observation window was to ship a "small" persistence layer
because the doc TODO said `[ ] briefs persistence decision`. The
correct close is recognizing the decision item was a *real* question
with a defensible *negative* answer, not a TODO to mechanically
discharge by writing code.
