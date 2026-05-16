# Sprint 1.2 — Handler consolidation + rename + UX fix

**Status**: planned 2026-05-16, trigger post-J+28 OR earlier if UX blocks daily ritual
**Input**: `docs/handler-review-2026-05-16/decisions.md` (12 blocs, 73 -> 24 commands)
**Mode**: STRICT during sub-command routing (behavior preserved). RELAXED for output format fixes (UX redesign per command).

## Goal

Reduce surface 73 -> 24 top-level commands via family unification with sub-commands. Fix illisible outputs flagged by user 2026-05-16.

## Surface reduction summary

- Before: 73 registered handlers
- After: 24 top-level commands (with sub-commands routing internally)
- Reduction: -49 handlers / 73 = -67%

## Execution phases

### Phase A — Renames only (low risk, 2-3h)

Pure rename, no behavior change. Old handler names registered as aliases for 1 release cycle, then removed.

1. `/signal_drilldown` -> `/signal`
2. `/echo_recent` -> `/echo`
3. `/bias_pattern` -> `/biases`
4. `/recent_8k` -> `/8k`

Acceptance: 5/5 gates pass, smoke each renamed handler in Telegram.

### Phase B — Family /portfolio (medium risk, 3-4h)

Unify 8 handlers into 1 family with sub-commands.

Family target:
- `/portfolio` -> TL;DR positions + cash + PnL
- `/portfolio TICKER` -> single position detail (was /position)
- `/portfolio TICKER history` -> events log (was /position_history)
- `/portfolio sectors` -> sectoral breakdown (was /portfolio_sectors)
- `/portfolio narratives` -> narrative breakdown (was /portfolio_narratives)
- `/portfolio drift` -> vs targets (was /portfolio_drift)

Handlers absorbed: /position, /position_history, /portfolio_sectors, /portfolio_narratives, /portfolio_drift.
Handlers deleted: /position_set (admin, replaceable by SQL).

Acceptance: each sub-command callable, 5/5 gates, smoke Telegram.

### Phase C — Family /trade (low risk, 1h)

Unify 2 action handlers.

Family target:
- `/trade buy TICKER QTY [price]` (was /position_buy)
- `/trade sell TICKER QTY [price]` (was /position_sell)

Preserved: Phase B5 journal_mod chain + bias_tagger auto.

### Phase D — Family /thesis (highest risk, 5-6h)

Unify 12 handlers (9 thesis + 3 absorbed from other categories) into 1 family.

Family target:
- `/thesis add [template]`
- `/thesis list`
- `/thesis set TICKER field value`
- `/thesis note ID texte`
- `/thesis revisit`
- `/thesis health`
- `/thesis premortem ID`
- `/thesis exit TICKER [price]`
- `/thesis exit TICKER --force raison`
- `/thesis asymmetry TICKER` (absorbed from /asymmetry, Bloc 8)
- `/thesis check_triggers` (absorbed from /price_check, Bloc 10)
- `/thesis override TICKER level reason` (absorbed from /override, Bloc 11)

### Phase E — Family /insiders (medium risk, 2h)

Unify 5 handlers.

- `/insiders TICKER` -> form 4 raw (was /insiders)
- `/insiders cluster TICKER` (was /insider_cluster)
- `/insiders buy_cluster [TICKER]` (was /insider_buy_cluster)
- `/insiders digest` (was /insider_digest)

Deleted: /insider_buy_cluster_stats (alpha calc requêtable SQL).

### Phase F — Family /8k (low risk, 1h)

- `/8k` -> recent 8K (was /recent_8k)
- `/8k history TICKER` (was /eight_k_history)

### Phase G — Family /macro (medium risk, 2h)

Unify 4 handlers.

- `/macro` -> TL;DR (events upcoming)
- `/macro regime` (was /regime)
- `/macro credit` (was /credit)
- `/macro calendar` (was /calendar)

Deleted: /calendar_refresh (cron 5h suffit).

### Phase H — Family /journal (medium risk, 2-3h)

Unify 5 handlers under 1 family.

- `/journal TICKER type conviction reasoning` -> log decision (action)
- `/journal review`
- `/journal unresolved`
- `/journal tag DECISION_ID newtag`
- `/journal audit` (was /journal_audit)

Deleted: /bias_review (absorbed by /biases stricter superset).

### Phase I — Family /sources (medium risk, 2h)

Unify 4 handlers.

- `/sources` -> TL;DR (health + tier breakdown)
- `/sources health` (was /sources_health)
- `/sources brier` (was /sources_brier)
- `/sources credibility` (was /credibility, absorbed Bloc 8)
- `/sources feedback ID up|down` (was /feedback, absorbed Bloc 8)

Deleted: /sources_half_life, /tiers, /tiers_watch, /promote (backend tier S/A/B reste actif).

### Phase J — Family /bot_data (medium risk, 2h)

Unify 4 handlers.

- `/bot_data` -> TL;DR all sections
- `/bot_data health` (was /health)
- `/bot_data costs` (was /llm_costs + /cost_trajectory merged)

Deleted: /kpi_status handler (KEEP cron Sunday 22:30 auto-post Telegram).

### Phase K — Family /predictions (low risk, 1h)

Unify 2 handlers.

- `/predictions` -> recent list with outcomes
- `/predictions resolve` (was /resolve_now)

### Phase L — Family /remarks (low risk, 30min)

Unify 2 handlers.

- `/remarks value <text>` (was /log_value)
- `/remarks friction <text>` (was /log_friction)

### Phase M — Standalone keep + minor (1h)

Standalone unchanged: /ping, /handler_stats, /analyze, /analyze_debate, /digest, /history, /crypto, /help, /find, /orphan_tickers.

Deleted: /debate_replay (Bloc 4).
Renamed: /materiality U dans /digest --materiality (Bloc 6).
Renamed: /signals_by_type D (Bloc 6).

### Phase N — UX fix output redesign (open scope)

Per user feedback "textes incomprehensibles" 2026-05-16, each handler output reviewed:
- TL;DR top
- Hierarchical info presentation
- Parlant labels (vs Phase XX technical refs)
- No Markdown parse_mode crashes (lesson 69e70c1)

Priority handlers (daily ritual):
1. /digest
2. /portfolio
3. /thesis list, /thesis health
4. /journal audit (silent tickers)
5. /biases
6. /orphan_tickers (favori, golden standard reference)

Lower priority: niche commands (/8k, /insiders, /sources, /macro).

## Estimated total effort

Phase A-M: 23-28h focused work.
Phase N (UX fix): 8-15h depending on handlers prioritized.

Realistic: 4-5 work sessions of 4-6h each.

## Execution constraint

NO Sprint 1.2 ship before 2026-06-10 (J+28) per observation mode discipline.
Exception: Phase A (renames only, behavior preserved) acceptable pre-J+28 if UX blocks daily ritual.

## Gates per phase

1. Test rename: old name still works (alias) AND new name works
2. Behavior preserved: existing tests pass (189 currently)
3. Sub-command routing tested
4. Output empirical Telegram test (paste output to friction.md if illisible)
5. Commit message per phase: "Sprint 1.2 Phase X — [family] consolidation"

## References

- `docs/handler-review-2026-05-16/decisions.md` — full 12 blocs decisions
- `docs/handler-audit.md` — original audit 14 mai (now superseded)
- `friction.md` — UX issues capture
- `PHILOSOPHY.md` — High Standard Mode discipline
