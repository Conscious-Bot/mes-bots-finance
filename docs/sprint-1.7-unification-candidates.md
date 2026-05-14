# Sprint 1.7 — Unification Candidates

**Purpose**: capture handler/code areas that look like consolidation candidates while reading `bot/main.py` during Sprint 1.1 chunks 1-10. Populated progressively, **not acted on during Sprint 1.1** (STRICT mode).

**Activation**: post-J+28 (after 2026-06-10 KPI #2 batch resolution). Prioritization combines this list + `/handler_stats` invocation data (Pareto curve: low-traffic handlers = deletion candidates, semantically similar handlers = unification candidates).

**Workflow**: during chunk N extraction, if a candidate appears, add an entry below. Do NOT modify behavior during Sprint 1.1. The entry is the action.

**Discipline**: this file is *append-only* during Sprint 1.1. Editing entries comes during Sprint 1.7 triage.

---

## Entry template
[target name(s)]

Domain: <chunk N domain>
Type: deletion | unification | helper-extraction | rename
Observation: what looks redundant or fragmentable
Evidence: line numbers, command names, telemetry counts if known
Proposed action: concrete one-liner
Risk: low/medium/high — what users/data could break
Detected during: chunk N reading on YYYY-MM-DD


---

## Candidates

_(none yet — populate during Sprint 1.1 chunk reads)_
