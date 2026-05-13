# Handlers Index

**Generated**: 13 May 2026
**Total handlers**: 67 registered Telegram commands

Catalog of all `/command` handlers in `bot/main.py`, categorized by use case.


## Ritual matinal / restitution

| Command | Function | Description |
|---|---|---|
| `/brief` | `cmd_brief` | Phase Brief — Morning ritual aggregator. |
| `/digest` | `cmd_digest` | — |
| `/kpi_status` | `cmd_kpi_status` | Phase Solidification P2 — Show KPI status with breach detection. |
| `/cost_trajectory` | `cmd_cost_trajectory` | Phase Solidification P2 — Strategic cost dashboard avec MTD + projection + budge |
| `/handler_stats` | `cmd_handler_stats` | Phase Solidification P0 #3 — Show handler usage stats with Pareto curve. |
| `/sources_brier` | `cmd_sources_brier` | Phase A1 — Display per-source Brier calibration stats. |
| `/tiers` | `cmd_tiers` | Phase Tickers Tiered — display ticker tier breakdown. |

## Thesis tracker (bidirectionnel)

| Command | Function | Description |
|---|---|---|
| `/thesis_add` | `cmd_thesis_add` | — |
| `/thesis_list` | `cmd_thesis_list` | — |
| `/thesis_revisit` | `cmd_thesis_revisit` | — |
| `/thesis_premortem` | `cmd_thesis_premortem` | Phase B7 — Display pre-mortem for a thesis. Usage: /thesis_premortem <id> |
| `/asymmetry` | `cmd_asymmetry` | Phase C13 — Show asymmetry ratio for thesis. Usage: /asymmetry [TICKER] |
| `/risk_check` | `cmd_risk_check` | Phase C12 — Pre-commit discipline check on proposed trade. |

## Signaux + scoring

| Command | Function | Description |
|---|---|---|
| `/signals_by_type` | `cmd_signals_by_type` | Phase Digestion 3a — Usage: /signals_by_type catalyst|data|narrative|opinion [ho |
| `/materiality_debug` | `cmd_materiality_debug` | Phase Digestion 3c — /materiality_debug TICKER → show last 5 signals with breakd |

## Positions + journal

| Command | Function | Description |
|---|---|---|
| `/position_buy` | `cmd_position_buy` | Add buy: /position_buy TICKER QTY PRICE [notes] |
| `/position_buy` | `cmd_position_buy` | Add buy: /position_buy TICKER QTY PRICE [notes] |
| `/position_sell` | `cmd_position_sell` | Sell: /position_sell TICKER QTY PRICE [notes] |
| `/position_sell` | `cmd_position_sell` | Sell: /position_sell TICKER QTY PRICE [notes] |
| `/positions` | `cmd_positions` | List all open positions with live valuation. |
| `/journal` | `cmd_journal` | Log a decision. Usage: /journal <TICKER> <type> <confidence_1_5> <reasoning> |
| `/bias_review` | `cmd_bias_review` | Phase B6 — Show aggregated bias frequencies. Usage: /bias_review [TICKER] |

## Catalyst + insider

| Command | Function | Description |
|---|---|---|
| `/recent_8k` | `cmd_recent_8k` | Phase C9 — List recent 8-Ks. Usage: /recent_8k [TICKER] [severity] |
| `/insider_buy_cluster_stats` | `cmd_insider_buy_cluster_stats` | Phase C7 — Empirical alpha summary across all logged BUY clusters. |

## Multi-round debate + analyze

| Command | Function | Description |
|---|---|---|
| `/analyze` | `cmd_analyze` | Full company analysis fiche: /analyze TICKER |
| `/analyze_debate` | `cmd_analyze_debate` | Phase C11 — Multi-round Bull/Bear debate. Usage: /analyze_debate TICKER |

## Ops + monitoring

| Command | Function | Description |
|---|---|---|
| `/llm_costs` | `cmd_llm_costs` | Phase A2 — Display LLM call costs + token usage by tier. |
| `/ping` | `cmd_ping` | — |
| `/promote` | `cmd_promote` | Phase Tickers Tiered — promote ticker between tiers. |

## Macro + regime

| Command | Function | Description |
|---|---|---|
| `/regime` | `cmd_regime` | — |
| `/macro` | `cmd_macro` | Show FOMC / NFP / CPI macro events for next 90 days. |
| `/calendar` | `cmd_calendar` | — |

## Other / Uncategorized

| Command | Function | Description |
|---|---|---|
| `/calendar_refresh` | `cmd_calendar_refresh` | — |
| `/credibility` | `cmd_credibility` | — |
| `/credit` | `cmd_credit` | — |
| `/crypto` | `cmd_crypto` | Show crypto cycle indicators (funding, OI, Mayer Multiple). |
| `/debate_replay` | `cmd_debate_replay` | Phase C11 — Replay stored debate by id. Usage: /debate_replay <id> |
| `/echo_recent` | `cmd_echo_recent` | Phase A3 — Show recent multi-source echo clusters. Usage: /echo_recent [hours] |
| `/eight_k_history` | `cmd_eight_k_history` | Phase C9 — Full 8-K history for ticker. Usage: /eight_k_history TICKER |
| `/exit` | `cmd_exit` | — |
| `/exit_force` | `cmd_exit_force` | — |
| `/feedback` | `cmd_feedback` | — |
| `/help` | `cmd_help` | Show all available commands grouped by category. |
| `/history` | `cmd_history` | Historical context for a ticker. |
| `/insider_buy_cluster` | `cmd_insider_buy_cluster` | Phase C7 — List BUY clusters. Usage: /insider_buy_cluster [TICKER] |
| `/insider_cluster` | `cmd_insider_cluster` | Detect cluster buying/selling: /insider_cluster TICKER [days] |
| `/insider_digest` | `cmd_insider_digest` | Manual: refresh insider snapshots and post digest. |
| `/insiders` | `cmd_insiders` | — |
| `/journal_review` | `cmd_journal_review` | Review journal stats + recent decisions. Usage: /journal_review [TICKER] |
| `/journal_tag` | `cmd_journal_tag` | Manually override mistake tag. Usage: /journal_tag <id> <tag> |
| `/journal_unresolved` | `cmd_journal_unresolved` | List decisions awaiting J+30 or J+90 resolution. |
| `/materiality` | `cmd_materiality` | View materiality scoring: /materiality (top 5 last 24h) or /materiality SIGNAL_I |
| `/orphan_tickers` | `cmd_orphan_tickers` | Tickers in signals (30d) NOT in watchlist. |
| `/override` | `cmd_override` | Capture override of a trigger: /override TICKER level reason |
| `/overrides` | `cmd_overrides` | List recent overrides. |
| `/portfolio` | `cmd_portfolio` | Phase B5 — Show active positions + concentration + unrealized PnL. |
| `/position` | `cmd_position` | Detail: /position TICKER |
| `/position_history` | `cmd_position_history` | Phase B5 — Show position history. Usage: /position_history [TICKER] |
| `/position_set` | `cmd_position_set` | Bootstrap position: /position_set TICKER QTY AVG_COST [notes] |
| `/predictions` | `cmd_predictions` | — |
| `/price_check` | `cmd_price_check` | Manual trigger : check all active theses for crossings right now. |
| `/resolve_now` | `cmd_resolve_now` | — |
| `/sources_half_life` | `cmd_sources_half_life` | Phase A4 — Display per-source information half-life. |
| `/sources_health` | `cmd_sources_health` | Health check newsletter sources. |
| `/thesis_note` | `cmd_thesis_note` | — |
| `/thesis_set` | `cmd_thesis_set` | Edit a field on active thesis: /thesis_set TICKER field value |
| `/tiers_watch` | `cmd_tiers_watch` | Full list of T2 watch tickers. |

## Stats

- **Categorized**: 30 / 67
- **Uncategorized**: 35
- **Cron-triggered handlers**: not listed (see `scripts.py` or bot/main.py scheduler init)
