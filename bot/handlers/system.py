"""System-level handlers: ping (liveness probe) + help (commands index)."""

from shared import storage


async def cmd_ping(update, ctx):  # noqa: ARG001
    state = storage.load_state()
    await update.message.reply_text(
        f"alive\n"
        f"capital: ${state['current_capital']:.0f}\n"
        f"drawdown: {state['drawdown_pct']:.1%}\n"
        f"theses actives: {state['active_theses_count']}\n"
        f"paper_only: {state['paper_only']}"
    )


async def cmd_help(update, ctx):  # noqa: ARG001
    """Show categorized list of all 65 registered commands."""
    help_text = """mes-bots-finance — 65 commands (consolidation V4 spec'd Sprint 1.2)

DAILY RITUAL (6)
  /brief             Morning briefing (6 sections)
  /health            Bot health snapshot
  /ping              Liveness probe
  /digest            Run digest pipeline now
  /log_value <msg>   Log a moment the bot helped
  /log_friction <msg> Log a friction

THESES (8)
  /thesis_list       List active theses (chunked)
  /thesis_add        Create new thesis
  /thesis_set        Set thesis params
  /thesis_note       Add note
  /thesis_revisit    Monthly revisit
  /thesis_premortem  Pre-mortem analysis
  /exit TICKER       Check exit triggers
  /exit_force        Force-close (regret-tagged)

POSITIONS (8)
  /portfolio         View positions w/ PnL
  /position TICKER   Drill-down
  /position_buy      Record buy + journal
  /position_sell     Record sell + journal
  /position_set      Set position manually
  /position_history  Event log
  /orphan_tickers    Holdings w/o thesis
  /override          Manual override

ANALYSIS (6)
  /analyze TICKER    Deep analysis (Opus, $0.20)
  /analyze_debate    Multi-round debate
  /asymmetry TICKER  Anti-sell-too-early math
  /risk_check        Risk premortem (Opus reads journal+biases)
  /materiality       Materiality (no args=top5, INT=signal_id, TICKER=last 5)

JOURNAL (9)
  /journal           View decision journal
  /journal_review    Review unresolved
  /journal_unresolved List unresolved
  /journal_tag       Tag with bias
  /bias_review       Bias patterns
  /history TICKER    Position/thesis history
  /predictions       Pending predictions
  /resolve_now       Force-resolve due
  /feedback          Submit feedback

SIGNALS & SOURCES (9)
  /echo_recent       Recent echo clusters
  /credibility       Source credibility
  /sources_brier     Brier per source
  /sources_half_life Source decay rates
  /sources_health    Source freshness
  /tiers             Source tier ranking
  /tiers_watch       Watch tier changes
  /promote           Promote tier

MARKET (7)
  /macro             Macro snapshot
  /regime            Current regime
  /credit            Credit / HY OAS
  /crypto            Crypto zone
  /price_check TICK  Live price
  /calendar          Upcoming events
  /calendar_refresh  Force refresh

INSIDERS (7)
  /insiders          Recent activity
  /insider_cluster   Cluster analysis
  /insider_buy_cluster      Buy-cluster only
  /insider_buy_cluster_stats Stats
  /insider_digest    Daily digest
  /recent_8k         Recent 8-K filings
  /eight_k_history   Historical 8-K

OPS & MONITORING (5)
  /cost_trajectory   LLM cost + budget
  /llm_costs         Operational LLM costs
  /handler_stats     Handler usage telemetry
  /help              This message

Spec V4: 65 -> 18 handlers in Sprint 1.2 (post 2026-06-10).
See docs/personal/handlers-consolidation-plan.md
"""
    await update.message.reply_text(help_text)
