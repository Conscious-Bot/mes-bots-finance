"""Command handler registry — extracted from bot/main.py Phase B (21/05/2026).

Centralizes the 80 CommandHandler registrations previously inline in main().
Old aliases preserved (Sprint 1.2 Phase A): /biases, /signal, /echo, /8k.
"""

from telegram.ext import Application, CommandHandler

from bot.handlers.adversarial import cmd_adversarial
from bot.handlers.anti_erosion import (
    cmd_log_friction,
    cmd_log_value,
    cmd_remarks,
)
from bot.handlers.audit import cmd_audit
from bot.handlers.bias_pattern import cmd_bias_pattern
from bot.handlers.bias_status import cmd_bias_status
from bot.handlers.debt_crisis import (
    cmd_debt_alerts,
    cmd_debt_history,
    cmd_debt_status,
)
from bot.handlers.digest import cmd_digest
from bot.handlers.echo_crypto_macro import (
    cmd_credit,
    cmd_crypto,
    cmd_echo_recent,
    cmd_macro,
    cmd_materiality,
    cmd_orphan_tickers,
    cmd_override,
    cmd_price_check,
)
from bot.handlers.find import cmd_find
from bot.handlers.journal_audit import cmd_journal_audit
from bot.handlers.journal_bias import (
    cmd_bias_review,
    cmd_history,
    cmd_journal,
)
from bot.handlers.misc import (
    cmd_asymmetry,
    cmd_brief,
    cmd_chat,
    cmd_grade,
    cmd_position,
    cmd_thesis_set,
)
from bot.handlers.observability import (
    cmd_cost_trajectory,
    cmd_handler_stats,
    cmd_health,
    cmd_kpi_status,
    cmd_llm_costs,
)
from bot.handlers.portfolio_views import (
    cmd_portfolio_drift,
    cmd_portfolio_narratives,
    cmd_portfolio_sectors,
    cmd_tiers,
)
from bot.handlers.positions import (
    cmd_journal_decision,
    cmd_portfolio,
    cmd_position_buy,
    cmd_position_buy_quick,
    cmd_position_sell,
    cmd_position_sell_quick,
    cmd_trade,
)
from bot.handlers.prediction_why import cmd_why
from bot.handlers.predictions import (
    cmd_credibility,
    cmd_feedback,
    cmd_predictions,
    cmd_resolve_now,
)
from bot.handlers.regime_calendar import (
    cmd_calendar,
    cmd_regime,
)
from bot.handlers.research import cmd_research
from bot.handlers.review import cmd_review
from bot.handlers.signal_drilldown import cmd_signal_drilldown
from bot.handlers.signals_filings import (
    cmd_eight_k_history,
    cmd_insider_buy_cluster,
    cmd_insider_buy_cluster_stats,
    cmd_insider_cluster,
    cmd_insider_digest,
    cmd_insiders,
    cmd_recent_8k,
    cmd_signals_by_type,
)
from bot.handlers.sources_admin import (
    cmd_sources,
    cmd_sources_brier,
    cmd_sources_health,
)
from bot.handlers.system import (
    cmd_help,
    cmd_ping,
)
from bot.handlers.thesis_analyze import (
    cmd_analyze,
    cmd_analyze_debate,
    cmd_risk_check,
)
from bot.handlers.thesis_crud import (
    cmd_exit,
    cmd_exit_force,
    cmd_thesis,
    cmd_thesis_list,
)
from bot.handlers.thesis_health import cmd_thesis_health
from bot.handlers.track_record import cmd_track_record


def register_command_handlers(app: Application) -> None:
    """Register all 80 Telegram CommandHandlers.

    Includes Sprint 1.2 Phase A short aliases:
    /biases → cmd_bias_pattern
    /signal → cmd_signal_drilldown
    /echo → cmd_echo_recent
    /8k → cmd_recent_8k
    """
    app.add_handler(CommandHandler("log_value", cmd_log_value))
    app.add_handler(CommandHandler("value_log", cmd_log_value))  # alias ordre-inverse (telem: 2 tentatives)
    app.add_handler(CommandHandler("log_friction", cmd_log_friction))
    app.add_handler(CommandHandler("remarks", cmd_remarks))  # Sprint 1.2 Phase L family
    app.add_handler(CommandHandler("audit", cmd_audit))  # per-decision audit (cf scripts/decision_audit.py)
    app.add_handler(CommandHandler("review", cmd_review))  # per-ticker fact-sheet (cf bot/handlers/review.py)
    app.add_handler(CommandHandler("research", cmd_research))  # Chantier #150 G3 spec #152 — Bigdata brief
    app.add_handler(CommandHandler("adversarial", cmd_adversarial))  # 4-stage bull/bear/counter/verdicts loop (23/06/2026)
    app.add_handler(CommandHandler("find", cmd_find))
    app.add_handler(CommandHandler("portfolio_sectors", cmd_portfolio_sectors))
    app.add_handler(CommandHandler("portfolio_narratives", cmd_portfolio_narratives))
    app.add_handler(CommandHandler("portfolio_drift", cmd_portfolio_drift))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("handler_stats", cmd_handler_stats))
    app.add_handler(CommandHandler("kpi_status", cmd_kpi_status))
    app.add_handler(CommandHandler("tiers", cmd_tiers))
    app.add_handler(CommandHandler("signals_by_type", cmd_signals_by_type))
    app.add_handler(CommandHandler("cost_trajectory", cmd_cost_trajectory))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("thesis", cmd_thesis))
    app.add_handler(CommandHandler("thesis_list", cmd_thesis_list))
    app.add_handler(CommandHandler("thesis_set", cmd_thesis_set))
    app.add_handler(CommandHandler("exit", cmd_exit))
    app.add_handler(CommandHandler("exit_force", cmd_exit_force))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("feedback", cmd_feedback))
    app.add_handler(CommandHandler("credibility", cmd_credibility))
    app.add_handler(CommandHandler("predictions", cmd_predictions))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("resolve_now", cmd_resolve_now))
    app.add_handler(CommandHandler("regime", cmd_regime))
    app.add_handler(CommandHandler("credit", cmd_credit))
    app.add_handler(CommandHandler("materiality", cmd_materiality))
    app.add_handler(CommandHandler("sources_health", cmd_sources_health))
    app.add_handler(CommandHandler("sources", cmd_sources))  # Sprint 1.2 Phase I family
    app.add_handler(CommandHandler("orphan_tickers", cmd_orphan_tickers))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("journal", cmd_journal))
    app.add_handler(CommandHandler("journal_audit", cmd_journal_audit))
    app.add_handler(CommandHandler("journal_decision", cmd_journal_decision))
    app.add_handler(CommandHandler("thesis_health", cmd_thesis_health))
    app.add_handler(CommandHandler("biases", cmd_bias_pattern))  # Sprint 1.2 Phase A alias
    app.add_handler(CommandHandler("signal_drilldown", cmd_signal_drilldown))
    app.add_handler(CommandHandler("signal", cmd_signal_drilldown))  # Sprint 1.2 Phase A alias
    app.add_handler(CommandHandler("sources_brier", cmd_sources_brier))
    app.add_handler(CommandHandler("llm_costs", cmd_llm_costs))
    app.add_handler(CommandHandler("echo", cmd_echo_recent))  # Sprint 1.2 Phase A alias
    app.add_handler(CommandHandler("position_buy", cmd_position_buy))
    app.add_handler(CommandHandler("position_buy_quick", cmd_position_buy_quick))
    app.add_handler(CommandHandler("position_sell", cmd_position_sell))
    app.add_handler(CommandHandler("position_sell_quick", cmd_position_sell_quick))
    app.add_handler(CommandHandler("trade", cmd_trade))  # Sprint 1.2 Phase C family
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("positions", cmd_portfolio))  # alias intuitif (telem: 5 tentatives)
    app.add_handler(CommandHandler("bias_review", cmd_bias_review))
    app.add_handler(CommandHandler("bias_status", cmd_bias_status))
    app.add_handler(CommandHandler("track_record", cmd_track_record))
    app.add_handler(CommandHandler("why", cmd_why))
    app.add_handler(CommandHandler("calendar", cmd_calendar))
    app.add_handler(CommandHandler("insiders", cmd_insiders))
    app.add_handler(CommandHandler("macro", cmd_macro))
    app.add_handler(CommandHandler("insider_digest", cmd_insider_digest))
    app.add_handler(CommandHandler("insider_cluster", cmd_insider_cluster))
    app.add_handler(CommandHandler("insider_buy_cluster", cmd_insider_buy_cluster))
    app.add_handler(CommandHandler("insider_buy_cluster_stats", cmd_insider_buy_cluster_stats))
    app.add_handler(CommandHandler("recent_8k", cmd_recent_8k))
    app.add_handler(CommandHandler("8k", cmd_recent_8k))  # Sprint 1.2 Phase A alias
    app.add_handler(CommandHandler("eight_k_history", cmd_eight_k_history))
    app.add_handler(CommandHandler("analyze_debate", cmd_analyze_debate))
    app.add_handler(CommandHandler("risk_check", cmd_risk_check))
    app.add_handler(CommandHandler("asymmetry", cmd_asymmetry))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CommandHandler("grade", cmd_grade))
    app.add_handler(CommandHandler("chat", cmd_chat))
    app.add_handler(CommandHandler("price_check", cmd_price_check))
    app.add_handler(CommandHandler("override", cmd_override))
    app.add_handler(CommandHandler("crypto", cmd_crypto))
    app.add_handler(CommandHandler("position", cmd_position))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("debt_status", cmd_debt_status))
    app.add_handler(CommandHandler("debt_history", cmd_debt_history))
    app.add_handler(CommandHandler("debt_alerts", cmd_debt_alerts))
