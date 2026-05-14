# Plan — Week of May 19, 2026 (Sprint 1.1 execution)

**Status**: drafted 2026-05-14 Day 3 close, refine pre-flight Monday morning
**Mode**: STRICT (equivalence test mandatory per chunk, zero consolidation)
**Baseline**: `baselines/sprint-1.1-chunk-0.json` @ commit 2158adf

## Goal

Split `bot/main.py` (3314 LOC) into `bot/handlers/*.py` modules through 10 sequential extraction chunks, validated by equivalence checkpoint after each.

## Constraint

NO behavior change. Each chunk extraction must pass:
- Function body SHA256 unchanged (allowlist documented if needed)
- Structural counts unchanged (65 handler regs, 65 cmd_* defs, 23 crons)
- Smoke tests (import bot.main, ruff, mypy, pytest, bot startup)

## Day-by-day plan

### Monday 2026-05-19 — Chunks 1 + 2 (ramp up)

- **Morning** (2-3h): Pre-flight refresh
  - cat HANDOFF.md
  - python scripts/sprint_1_1_checkpoint.py verify 0 (should pass after Friday fix)
  - Read docs/sprint-1.1-plan.md chunk 1 blueprint
  - Open questions section: clarify any uncertainty before code
- **Midday** (2h): Chunk 1 — anti_erosion (43 LOC pre-analyzed)
  - Per per-chunk procedure
  - Address the KNOWN PIEGE
  - Acceptance: equivalence verify 1 = PASS
- **Afternoon** (2-3h): Chunk 2 — observability (/health, /handler_stats, /llm_costs, /cost_trajectory, /kpi_status)
  - Larger scope, expect 200-400 LOC
  - Verify 2 = PASS before commit

Acceptance Monday: 2 chunks shipped, verify 1 + verify 2 PASS, bot startup OK.

### Tuesday 2026-05-20 — Chunks 3 + 4

- Chunk 3 — admin (/start, /help, /mode_switch, /version, /sources)
- Chunk 4 — positions (/position_buy, /position_sell, /portfolio, /pnl)
  - Note: Phase B5 journal regression P1 item — re-integrate during this chunk (carry-forward from Ship 5)

### Wednesday 2026-05-21 — Chunks 5 + 6

- Chunk 5 — sources (/sources_brier, /promote, /tiers)
- Chunk 6 — signals (/signals_by_type, /materiality_debug, /recent_8k, /insider_buy_cluster_stats)

### Thursday 2026-05-22 — Chunk 7 (biggest)

- Chunk 7 — thesis (/thesis, /thesis_premortem, /analyze, /analyze_debate, /risk_check)
- Expected largest single chunk (~600-800 LOC, multi-round debate logic)
- Full day, less buffer

### Friday 2026-05-23 — Chunks 8 + 9 + 10 (close)

- Chunk 8 — ritual (/brief, /digest) — note: friction items captured for redesign POST-1.1
- Chunk 9 — analytics (/asymmetry, remaining)
- Chunk 10 — cleanup (final smoke + tests + retro)

## Buffer & risk

Plan suggests 45h focused work. Day-by-day above ~9h/day. 17% buffer per plan = each day has slack for one paste catastrophe + one missed PIEGE.

If Monday chunks 1+2 ship by EOD: ON TRACK.
If Monday only ships chunk 1: -1 day, compress Friday or extend to Saturday.
If chunk 1 fails: investigate piège, may need Tuesday before resuming.

## Post-Sprint-1.1 (week of May 26+)

- Sprint 1.2: handler audit + consolidation per friction.md (5 items from Day 3 close)
- /brief + /digest redesign together
- Metrics handlers unified into 1 explained handler
- Phase 1 appropriation pre-conditions (FileVault, no iCloud sync, backup restore, risk_engine wired, paper_only verified)

## References

- `docs/sprint-1.1-plan.md` — detailed chunk 1 blueprint + per-chunk procedure
- `baselines/sprint-1.1-chunk-0.json` — function body baseline
- `scripts/sprint_1_1_checkpoint.py` — equivalence harness
- `friction.md` — post-Sprint-1.1 redesign input
- `docs/post-mortems/2026-05-14-apscheduler-hang-restart-cascade.md` — incident learnings
- `CONVENTIONS.md` §16, §18, §19 — process/paste/code targeting rules
