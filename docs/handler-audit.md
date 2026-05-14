# Handler audit — Sprint 1.2 input

**Created**: 2026-05-14 Day 3 close
**Purpose**: structured surface for KEEP / DISABLE / UNIFY decisions on 65 handlers
**Execution**: post Sprint 1.1 (week of May 26+), once handlers/*.py modules exist

## Telemetry context

- Total calls logged: 27
- Window: 2026-05-13 03:56:19 → 2026-05-14 00:47:24
- Sample size: ~21h — THIN. Re-audit recommended once telemetry has accumulated 14+ days.
- A handler with 0 calls in this window is NOT auto-useless — could be event-driven (alert-triggered), seasonal, or simply unused recently. Requires Olivier review.

## Decision codes

- **K** = KEEP (single purpose, clear value, used or planned)
- **D** = DISABLE (comment out registration in handlers/*.py, keep function body for trivial revival)
- **U** = UNIFY (merge into consolidated handler with subcommands or args)
- **?** = NEEDS DECISION (manual review by Olivier with fresh eyes)

Olivier's stated favorites (DO NOT disable, EXPAND scope): `/analyze`, `/orphan_tickers`.
Olivier's friction signal: Observability handlers — 'too many, balanced sans explication, je ne les comprends pas tous'. Likely UNIFY candidates.

## Handlers by chunk

### Chunk 1 — Anti-erosion

| Handler | Calls (21h) | Last used | Reco | Olivier |
|---|---|---|---|---|
| /log_value | 4 | 2026-05-14 00:47 | K | ___ |
| /log_friction | 1 | 2026-05-13 13:56 | K | ___ |

### Chunk 2 — Observability / Metrics

| Handler | Calls (21h) | Last used | Reco | Olivier |
|---|---|---|---|---|
| /health | 3 | 2026-05-13 09:59 | K | ___ |
| /handler_stats | 1 | 2026-05-13 03:56 | K | ___ |
| /llm_costs | 0 | — | ? | ___ |
| /cost_trajectory | 0 | — | ? | ___ |
| /kpi_status | 0 | — | ? | ___ |
| /sources_health | 0 | — | ? | ___ |

### Chunk 3 — Admin / meta

| Handler | Calls (21h) | Last used | Reco | Olivier |
|---|---|---|---|---|
| /ping | 2 | 2026-05-13 04:06 | K | ___ |
| /help | 2 | 2026-05-13 13:21 | K | ___ |
| /exit | 0 | — | ? | ___ |
| /exit_force | 0 | — | ? | ___ |
| /feedback | 0 | — | ? | ___ |
| /credit | 0 | — | ? | ___ |
| /regime | 0 | — | ? | ___ |
| /override | 1 | 2026-05-13 13:22 | K | ___ |

### Chunk 4 — Positions

| Handler | Calls (21h) | Last used | Reco | Olivier |
|---|---|---|---|---|
| /portfolio | 1 | 2026-05-13 13:21 | K | ___ |
| /position_buy | 2 | 2026-05-13 13:40 | K | ___ |
| /position_sell | 0 | — | ? | ___ |
| /position_history | 0 | — | ? | ___ |
| /position_set | 0 | — | ? | ___ |
| /position | 1 | 2026-05-13 13:22 | K | ___ |
| /bias_review | 0 | — | ? | ___ |

### Chunk 5 — Sources

| Handler | Calls (21h) | Last used | Reco | Olivier |
|---|---|---|---|---|
| /sources_brier | 0 | — | ? | ___ |
| /sources_half_life | 0 | — | ? | ___ |
| /tiers | 0 | — | ? | ___ |
| /tiers_watch | 0 | — | ? | ___ |
| /promote | 0 | — | ? | ___ |

### Chunk 6 — Signals

| Handler | Calls (21h) | Last used | Reco | Olivier |
|---|---|---|---|---|
| /signals_by_type | 0 | — | ? | ___ |
| /materiality | 2 | 2026-05-13 13:22 | K | ___ |
| /recent_8k | 0 | — | ? | ___ |
| /eight_k_history | 0 | — | ? | ___ |
| /insider_buy_cluster | 0 | — | ? | ___ |
| /insider_buy_cluster_stats | 0 | — | ? | ___ |
| /insider_cluster | 0 | — | ? | ___ |
| /insiders | 0 | — | ? | ___ |
| /insider_digest | 0 | — | ? | ___ |
| /echo_recent | 0 | — | ? | ___ |
| /orphan_tickers | 0 | — | ? | ___ |

### Chunk 7 — Thesis

| Handler | Calls (21h) | Last used | Reco | Olivier |
|---|---|---|---|---|
| /thesis_add | 0 | — | ? | ___ |
| /thesis_list | 0 | — | ? | ___ |
| /thesis_revisit | 0 | — | ? | ___ |
| /thesis_set | 0 | — | ? | ___ |
| /thesis_note | 0 | — | ? | ___ |
| /thesis_premortem | 0 | — | ? | ___ |
| /analyze | 0 | — | ? | ___ |
| /analyze_debate | 0 | — | ? | ___ |
| /debate_replay | 0 | — | ? | ___ |
| /risk_check | 0 | — | ? | ___ |

### Chunk 8 — Ritual

| Handler | Calls (21h) | Last used | Reco | Olivier |
|---|---|---|---|---|
| /digest | 1 | 2026-05-14 00:43 | K | ___ |
| /brief | 4 | 2026-05-14 00:42 | K | ___ |

### Chunk 9 — Analytics

| Handler | Calls (21h) | Last used | Reco | Olivier |
|---|---|---|---|---|
| /asymmetry | 1 | 2026-05-13 03:56 | K | ___ |
| /calendar | 0 | — | ? | ___ |
| /calendar_refresh | 0 | — | ? | ___ |
| /macro | 0 | — | ? | ___ |
| /predictions | 0 | — | ? | ___ |
| /resolve_now | 0 | — | ? | ___ |
| /history | 0 | — | ? | ___ |
| /journal | 0 | — | ? | ___ |
| /journal_review | 0 | — | ? | ___ |
| /journal_unresolved | 0 | — | ? | ___ |
| /journal_tag | 0 | — | ? | ___ |
| /price_check | 0 | — | ? | ___ |
| /crypto | 0 | — | ? | ___ |
| /credibility | 0 | — | ? | ___ |

## Execution plan

1. **Olivier reviews with fresh eyes** (15-30 min, NOT 22:30 KST after 17h work)
2. Fill 'Olivier' column with K / D / U / ? for each row
3. Commit decisions to git
4. Sprint 1.1 (May 19-23) extracts handlers AS-IS — STRICT mode, no behavior change
5. Sprint 1.2 (May 26+) executes the decisions on bot/handlers/*.py:
   - K: keep registration
   - D: comment `app.add_handler(...)`, function body preserved
   - U: design consolidated handler, migrate, comment originals
6. Re-audit in 2 weeks once telemetry has 14+ days of data

## References

- `friction.md` 2026-05-14 — items 5 (metrics proliferation) and 4 (/brief vs /digest)
- `docs/plan-week-of-may-19.md` — Sprint 1.1 schedule
- `docs/sprint-1.1-plan.md` — chunk taxonomy reference
- `bot/main.py` L3243-L3308 — current handler registration block
