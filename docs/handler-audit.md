# Handler audit — Sprint 1.2 input (FIRST PASS RECOMMENDATIONS)

**Created**: 2026-05-14 Day 3 close
**First-pass reviewer**: Claude (heuristic from handler name + project context + 21h telemetry — NOT code body read)
**Final reviewer**: Olivier, fresh eyes (15-30 min), validates or overrides each row
**Execution**: Sprint 1.2 (May 26+), post Sprint 1.1 chunk split

## Telemetry context

- Total calls logged: 44
- Window: 2026-05-13 03:56:19 → 2026-05-14 13:21:32
- Sample: ~21h — THIN. Re-audit recommended once telemetry has 14+ days.

### Behavioral tension worth noting

Olivier stated in friction.md: */brief feels less interesting than /digest*.
Empirical telemetry: **/brief = 4 calls, /digest = 1 call** in 21h window.

Three hypotheses to test during redesign:
- **(a) Habit override stated preference** — exactly the bidirectional discipline gap this bot is designed to catch on positions, surfacing here on handlers
- **(b) Sampling bias** — /digest fires automatically via cron (7h + 19h), so manual calls aren't needed; /brief is manual-only
- **(c) Cognitive friction on command name** — /brief is shorter/easier to type than /digest

This tension is data for the /brief vs /digest redesign, not a problem to fix tonight.

## Decision codes

- **K** = KEEP (single purpose, clear value, used or planned)
- **K+** = KEEP & EXPAND (Olivier-stated favorite, scope-expand candidate)
- **D** = DISABLE (comment out registration in handlers/*.py, keep function body)
- **U** = UNIFY (merge into consolidated handler with subcommands or args)
- **?** = NEEDS DECISION (body read required, or genuine ambiguity)

### First-pass tally

- **K**: 37 (56%)
- **K+** (Olivier favorites): 2 (3%)
- **U** (unify candidates): 18 (27%)
- **D** (disable candidates): 0 (0%)
- **?** (needs review): 8 (12%)

Effective surface reduction if all U merges execute: ~13 handlers → ~5 handlers = **-8 handlers**.
Final surface estimate after Sprint 1.2: ~55-57 handlers (down from 65).

## Top unification clusters identified

1. **`/insider_*` family** (5 handlers → 1): /insiders, /insider_cluster, /insider_buy_cluster, /insider_buy_cluster_stats, /insider_digest — merge into single `/insiders <subcommand>` (e.g., `/insiders cluster`, `/insiders stats`, `/insiders digest`)
2. **`/sources_*` family** (3 handlers → 1): /sources_brier, /sources_half_life, /sources_health — merge into `/sources_metrics` with --type flag
3. **`/cost*` family** (2 handlers → 1): /llm_costs, /cost_trajectory — single `/costs <view>` with mtd, projection, breakdown
4. **`/tiers*` family** (2 handlers → 1): /tiers, /tiers_watch — `/tiers --watch`
5. **`/materiality*` family** (2 handlers → 1): /materiality, /materiality_debug — `/materiality --debug`
6. **`/8k*` family** (2 handlers → 1): /recent_8k, /eight_k_history — `/8k` with --window flag
7. **`/position*` family** (review): /position, /position_set vs /portfolio, /position_history — consolidate aliases
8. **`/brief` + `/digest`** (review TOGETHER, possibly merge or redesign — friction items 1-4)

## Handlers by chunk

### Chunk 1 — Anti-erosion

| Handler | Calls | Last used | Reco | Rationale | Olivier |
|---|---|---|---|---|---|
| /log_value | 4 | 2026-05-14 | K | Tier 1 anti-erosion, just shipped, core Path 5/6 dim 2 | ___ |
| /log_friction | 1 | 2026-05-13 | K | Companion to log_value, wedge signal capture | ___ |

### Chunk 2 — Observability / Metrics

| Handler | Calls | Last used | Reco | Rationale | Olivier |
|---|---|---|---|---|---|
| /health | 3 | 2026-05-13 | K | Tier 2 shipped Day 3, validated 24h post-deploy | ___ |
| /handler_stats | 2 | 2026-05-14 | K | Telemetry surfacing, sample for this audit itself | ___ |
| /llm_costs | 1 | 2026-05-14 | U | Merge with /cost_trajectory — both LLM cost metrics, friction item 5 direct | ___ |
| /cost_trajectory | 1 | 2026-05-14 | U | Merge with /llm_costs into single /costs handler with args (mtd/projection/breakdown) | ___ |
| /kpi_status | 1 | 2026-05-14 | K | Recently added Day 3, Path 5/6 dim 2 monitoring critical | ___ |
| /sources_health | 0 | — | U | Merge with /sources_brier + /sources_half_life into /sources_metrics | ___ |

### Chunk 3 — Admin / meta

| Handler | Calls | Last used | Reco | Rationale | Olivier |
|---|---|---|---|---|---|
| /ping | 2 | 2026-05-13 | K | Diagnostic, low cost, classic | ___ |
| /help | 3 | 2026-05-14 | K | Essential | ___ |
| /exit | 0 | — | ? | Body unclear from name — closes thesis? closes position? needs review | ___ |
| /exit_force | 0 | — | ? | Companion to /exit, same uncertainty | ___ |
| /feedback | 0 | — | ? | Feedback to bot? to thesis? unclear without body | ___ |
| /credit | 0 | — | ? | Credit what — API credit balance? overlap with cost_trajectory? | ___ |
| /regime | 1 | 2026-05-14 | K | Macro regime detection, useful even if not used recently | ___ |
| /override | 1 | 2026-05-13 | ? | Override what — mode? thesis? paper_only? needs review | ___ |

### Chunk 4 — Positions

| Handler | Calls | Last used | Reco | Rationale | Olivier |
|---|---|---|---|---|---|
| /portfolio | 1 | 2026-05-13 | K | Essential, view positions | ___ |
| /position_buy | 2 | 2026-05-13 | K | Core feature, Phase B5 journal-logging integrated | ___ |
| /position_sell | 0 | — | K | Core feature, anti-sell-too-early discipline hook | ___ |
| /position_history | 0 | — | K | Audit trail of position events | ___ |
| /position_set | 0 | — | U | Probably overlap with /position_buy or admin-set — consolidate | ___ |
| /position | 1 | 2026-05-13 | U | Likely alias for /portfolio or /position_history — unify | ___ |
| /bias_review | 0 | — | K | Path 5/6 dim 2 critical, bias tracking | ___ |

### Chunk 5 — Sources

| Handler | Calls | Last used | Reco | Rationale | Olivier |
|---|---|---|---|---|---|
| /sources_brier | 0 | — | U | Merge with /sources_health + /sources_half_life into /sources_metrics | ___ |
| /sources_half_life | 0 | — | U | Merge with sources_health + sources_brier | ___ |
| /tiers | 0 | — | K | S/A/B tiers shipped Day 2, empirical credibility ranking | ___ |
| /tiers_watch | 0 | — | U | Tiers + watchlist combo — consolidate into /tiers with --watch flag | ___ |
| /promote | 0 | — | K | Admin promote source to higher tier | ___ |

### Chunk 6 — Signals

| Handler | Calls | Last used | Reco | Rationale | Olivier |
|---|---|---|---|---|---|
| /signals_by_type | 0 | — | K | Catalyst/data/narrative/opinion taxonomy, valuable filter | ___ |
| /materiality | 2 | 2026-05-13 | U | Likely old version vs materiality_v2 chained — consolidate into /materiality with --v flag | ___ |
| /recent_8k | 1 | 2026-05-14 | K | 8-K filings cat scan, niche but high-signal | ___ |
| /eight_k_history | 0 | — | U | Overlap with /recent_8k — consolidate with --history flag | ___ |
| /insider_buy_cluster | 0 | — | U | Merge into /insiders with subcommand (5 insider_* handlers is the worst proliferation case) | ___ |
| /insider_buy_cluster_stats | 0 | — | U | Same merge target as insider_buy_cluster | ___ |
| /insider_cluster | 0 | — | U | Variant of insider_buy_cluster — merge | ___ |
| /insiders | 2 | 2026-05-14 | U | Merge target for /insider_* family (5 handlers → 1) | ___ |
| /insider_digest | 0 | — | U | Merge into /insiders --digest | ___ |
| /echo_recent | 0 | — | K | BGE embedding echo detection, unique feature | ___ |
| /orphan_tickers | 1 | 2026-05-14 | K+ | OLIVIER STATED FAVORITE — EXPAND scope, do NOT disable | ___ |

### Chunk 7 — Thesis

| Handler | Calls | Last used | Reco | Rationale | Olivier |
|---|---|---|---|---|---|
| /thesis_add | 0 | — | K | Essential thesis tracker entry point | ___ |
| /thesis_list | 0 | — | K | Essential view | ___ |
| /thesis_revisit | 0 | — | K | Anti-sell-too-early discipline mechanism | ___ |
| /thesis_set | 0 | — | U | Probably overlap with /thesis_add — verify intent | ___ |
| /thesis_note | 0 | — | K | Notes appended to thesis | ___ |
| /thesis_premortem | 0 | — | K | Path 5/6 pre-commit discipline | ___ |
| /analyze | 0 | — | K+ | OLIVIER STATED FAVORITE — EXPAND, north star for handler quality | ___ |
| /analyze_debate | 0 | — | K | Multi-round debate, expensive but high-signal when used | ___ |
| /debate_replay | 0 | — | ? | Replay past debate — diagnostic only? could be D | ___ |
| /risk_check | 0 | — | K | Opus risk_check, anti-FOMO discipline | ___ |

### Chunk 8 — Ritual

| Handler | Calls | Last used | Reco | Rationale | Olivier |
|---|---|---|---|---|---|
| /digest | 2 | 2026-05-14 | U | Friction item 4: review WITH /brief, potentially consolidate | ___ |
| /brief | 4 | 2026-05-14 | U | Friction item 1-3: redesign WITH /digest. 4 calls vs digest 1 call — tension empirique vs stated preference | ___ |

### Chunk 9 — Analytics

| Handler | Calls | Last used | Reco | Rationale | Olivier |
|---|---|---|---|---|---|
| /asymmetry | 1 | 2026-05-13 | K | Core bidirectional discipline math | ___ |
| /calendar | 0 | — | K | Macro calendar view | ___ |
| /calendar_refresh | 1 | 2026-05-14 | ? | Admin trigger for cron — could be D if cron-only path adequate | ___ |
| /macro | 1 | 2026-05-14 | K | Macro events feed | ___ |
| /predictions | 0 | — | K | KPI #2 source, ledger view | ___ |
| /resolve_now | 0 | — | K | Manual override for prediction resolve | ___ |
| /history | 0 | — | ? | History of what — predictions? thesis? events? needs review | ___ |
| /journal | 0 | — | K | Phase B5 decision journal | ___ |
| /journal_review | 0 | — | K | Review past journaled decisions | ___ |
| /journal_unresolved | 0 | — | K | Find unresolved decisions for follow-up | ___ |
| /journal_tag | 0 | — | K | Bias tagging for journaled decisions | ___ |
| /price_check | 2 | 2026-05-14 | K | Quick price query | ___ |
| /crypto | 1 | 2026-05-14 | K | Crypto zones anti-greed discipline | ___ |
| /credibility | 0 | — | K | Source credibility lookup, KPI #3 | ___ |

## Execution plan

1. **Olivier reviews FRESH** (15-30 min, NOT 22:30 KST after 17h+ work)
2. For each row: validate Reco, override if my heuristic missed nuance. Pay extra attention to the `?` rows — those need body-read or decision context I lack.
3. Fill 'Olivier' column. Commit decisions to git.
4. Sprint 1.1 (May 19-23): extract handlers AS-IS, STRICT mode, no behavior change.
5. Sprint 1.2 (May 26+): execute decisions on bot/handlers/*.py:
   - K, K+: keep, expand K+ scope per Olivier priority
   - D: comment `app.add_handler(...)`, function body preserved
   - U: design consolidated handler, migrate functionality, comment originals
6. Re-audit in 2 weeks once telemetry has 14+ days of data.

## Notes on confidence

- High confidence: K and K+ on handlers with clear single purpose and known project value (anti_erosion, asymmetry, thesis_*, journal_*, risk_check, analyze, orphan_tickers)
- High confidence: U clusters where naming convention reveals overlap (insider_*, sources_*, cost*, tiers*)
- Medium confidence: U on /brief, /digest — friction signal clear, exact consolidation design TBD
- Low confidence: ? rows (/exit, /exit_force, /feedback, /credit, /override, /calendar_refresh, /history, /debate_replay) — body read required to commit

## References

- `friction.md` 2026-05-14 — items 1-7
- `docs/plan-week-of-may-19.md` — Sprint 1.1 schedule
- `docs/sprint-1.1-plan.md` — chunk taxonomy reference
- `bot/main.py` L3243-L3308 — current handler registration block
