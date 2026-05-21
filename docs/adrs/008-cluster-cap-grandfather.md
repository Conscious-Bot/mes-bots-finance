# ADR 008 — Cluster cap 35% + position cap soft + grandfather strict

**Date**: 21 May 2026
**Status**: Accepted
**Context**: Empirical concentration breach observed in /portfolio:
6 positions over `style.position_max_pct = 5%`. Deeper inspection
revealed the bigger issue is *cluster-level* concentration:
**14 of 21 positions (76.6% of book USD) are in AI_COMPUTE_2026
narrative**. Individual position cap is the wrong invariant — the
real risk is correlated downside via narrative cluster.

## Decision

Four points figés:

### 1. Cluster cap = 35% per narrative_tag
Each `sector_thesis_id` cluster (parsed from `theses.notes`) cannot
exceed 35% of total book USD value. Hard cap.

### 2. Position cap = 5% (kept, demoted to soft)
Individual position cap stays at `style.position_max_pct = 5%` for
visual signaling, but is no longer the binding invariant. Cluster cap
is the hard policy. Position cap remains as additional alerting only.

### 3. Grandfather strict
All positions existing at 2026-05-21 are accepted as historical
exception (e.g. AI_COMPUTE @ 76.6%). Going forward:
- NO new entries on any ticker that would push a cluster over 35%
- NO new entries on tickers in over-cap clusters even if the ticker
  itself is under 5% individually
- Existing positions may continue to drift (price-driven), with no
  forced trim — but NEW size additions blocked

### 4. ADR revisit trigger
Quarterly review starting J+28 = 2026-06-10. If a cluster has drifted
above 50% (regardless of new entries), forced trim discussion.

## Rationale

### Why cluster > individual cap
A 5% AVGO position is not "5% risk" if 13 other positions also have
correlated downside via the same AI_COMPUTE narrative. The cluster
moves as one in a regime shock. Individual cap is a fiction of
diversification when narrative clustering is high.

Reference empirical: 4 of 6 P0 risks identified would be triggered
by an AI_compute thesis invalidation simultaneously hitting 14
positions. Individual cap protects against single-ticker idiosyncratic
risk; cluster cap protects against narrative regime risk.

### Why 35% (not 30% or 40%)
- 30%: too restrictive given current 76.6% concentration. Would force
  immediate trim of ~5 positions. Cost > benefit before J+28 data.
- 40%: too permissive. Doesn't create meaningful behavioral pressure
  to diversify.
- 35%: meaningful gap from current state, signals "you're way over",
  motivates organic rebalance via NEW entries on under-cap clusters
  (ELECTRIFICATION 9.3%, EU_DEFENSE 3.7% have room).

### Why grandfather strict (not force-trim)
- Trim now = realize gains/losses + tax friction + reset cost basis
  + potential mis-timing
- Grandfather lets price-driven drift correct over time
- NEW entries policy is the actionable constraint
- Aligns with PHILOSOPHY: "Plus de discipline dans l'usage" — the
  pressure is on future actions, not retroactive revisions

### Why 5% kept (soft)
- Still informative to see "TSM 8.8% individual" as a flag
- Demoting to "alert only" preserves signal without binding constraint
- If position cap is removed entirely, lose the visual heuristic for
  "this ticker is a meaningful slice of book"

## Empirical state at decision time (21 May 2026)
Cluster                          $Value       %   Status
AI_COMPUTE_2026                  $XX,XXX  76.6%   🔴 +41.6pp over cap
ORPHAN_C1_REVIEW_J30_2026         $X,XXX  10.2%   ✅ (exit candidates)
ELECTRIFICATION_2026              $X,XXX   9.3%   ✅ 25.7pp room
EU_DEFENSE_2026                   $X,XXX   3.7%   ✅ 31.3pp room

Individual caps breached: 4063.T (10.2%), ASML.AS (9.2%), TSM (8.8%),
SNPS (6.8%), 7011.T (5.6%), STMPA.PA (5.3%). All grandfathered.

## Implementation phases

### Phase 1 — Decision documented (this ADR)
DONE. Decision figée. No code yet.

### Phase 2 — /portfolio CLUSTER CONCENTRATION section
Add display section after header showing cluster breakdown with %
and delta vs cap. Daily psychological pressure to rebalance via
new entries on under-cap clusters.

Target file: `bot/handlers/positions.py:cmd_portfolio`
Effort: ~30-40 min.

### Phase 3 — risk.validate() wiring (DEFERRED to post-J+28)
Wire cluster cap check into `risk/risk_engine.py:validate()` before
position_buy execution. Block with reason if would push cluster over
35%. Aligns with existing TODO L325 "Wire risk.validate() into
cmd_position_buy / cmd_position_sell" planned for post-J+28.

## Consequences

### Positive
- Behavioral pressure to diversify via under-cap clusters
- Cluster-level concentration risk surfaced daily
- Foundation for risk.validate() wiring post-J+28
- Aligns with PHILOSOPHY High Standard Mode

### Negative (accepted)
- AI_COMPUTE concentration not immediately reduced
- Soft individual cap may confuse if not clearly documented
- Cluster identification depends on accurate sector_thesis_id in notes
  (parsing dependency — could break if notes format changes)

### Mitigation
- Phase 2 alerting creates visible daily reminder
- ADR document is the canonical reference for "why these numbers"
- If sector_thesis_id parsing fails for a position, default to
  UNCLUSTERED bucket (transparent rather than silent miscategorization)

## Revisit trigger

Mandatory review at 2026-06-10 (KPI #2 batch resolution day):
- Has cluster concentration shifted naturally?
- Does the cap percentage feel right empirically vs aspirational?
- Should orphans cluster be split or reclassified?

Discretionary review if:
- AI_COMPUTE drifts above 90% of book
- Any cluster crosses 50%
- Path 5/6 acquirer/subscriber asks about diversification policy
