import pytest

"""Smoke tests for 28-day observation period.

Lightweight fail-fast tests verifying:
- Critical modules import cleanly (catches refactor regressions)
- Key handlers + cron jobs are callable symbols
- Phase B5 journal helpers still exposed
- DB schema has required tables

Doesn't mock LLM/Gmail/yfinance — just verifies the wiring.
Real path coverage happens when user invokes commands on Telegram.
"""


def test_shared_modules_import_cleanly():
    """All shared/* modules importable. Catches import-cascade regressions."""
    from shared import (
        config,
        crypto,
        echo,
        edgar,
        embeddings,
        llm,
        macro,
        math_helpers,
        notify,
        positions,
        prices,
        prompts,
        storage,
    )


def test_intelligence_modules_import_cleanly():
    """Core intelligence/* modules importable."""
    from intelligence import (
        analyze,
        asymmetry,
        bias_tagger,
        credibility,
        debate,
        digest,
        half_life,
        journal,
        learning,
        materiality,
        materiality_v2,
        regime,
        signal_classify,
    )


def test_bot_main_imports_cleanly():
    """bot.main imports without crash. Catches NameError/ImportError from refactors."""
    import bot.main


def test_critical_handlers_callable():
    """Handlers used during daily ops + auto-cron must exist + be callable."""
    from bot import main

    critical = [
        # Position handlers (Phase B5 integration verified)
        "cmd_position_buy", "cmd_position_sell", "cmd_portfolio",
        # Monitoring handlers (Path 5/6 dimension 2)
        "cmd_kpi_status", "cmd_cost_trajectory", "cmd_handler_stats",
        # Asymmetry + risk (anti-bias core)
        "cmd_asymmetry", "cmd_risk_check",
        # Ritual matinal
        "cmd_brief", "cmd_digest",
        # Telemetry middleware
        "log_handler_call_middleware",
    ]
    for h in critical:
        assert hasattr(main, h), f"Handler {h} missing from bot.main"
        assert callable(getattr(main, h)), f"{h} not callable"


def test_cron_jobs_for_observation_callable():
    """Cron jobs that fire during 28-day observation must be intact."""
    from bot import main

    crons = [
        "weekly_kpi_status_job",       # Sun 22:30
        "weekly_cost_summary_job",     # Sun 22:00
        "weekly_handler_stats_job",    # Sun 23:00
        "daily_backup_job",            # 04:00 daily
    ]
    for c in crons:
        assert hasattr(main, c), f"Cron job {c} missing"
        assert callable(getattr(main, c)), f"{c} not callable"


def test_phase_b5_journal_helpers_present():
    """Phase B5 journal integration helpers exposed (post-Ship 5 restoration)."""
    from intelligence import bias_tagger
    from shared import storage

    storage_helpers = [
        "log_decision", "get_decision", "get_position_by_ticker",
        "update_decision_bias_tags", "get_active_positions",
        "get_positions_history", "get_bias_stats",
        "create_or_update_position_on_buy", "record_position_sell",
    ]
    for name in storage_helpers:
        assert hasattr(storage, name), f"storage.{name} missing"
        assert callable(getattr(storage, name)), f"storage.{name} not callable"

    assert hasattr(bias_tagger, "auto_tag_biases"), "bias_tagger.auto_tag_biases missing"
    assert callable(bias_tagger.auto_tag_biases)


def test_portfolio_journal_ctx_in_bot_main():
    """_portfolio_journal_ctx helper used by Phase B5 integration in cmd_position_buy/sell."""
    from bot import main

    assert hasattr(main, "_portfolio_journal_ctx"), "_portfolio_journal_ctx missing"
    assert callable(main._portfolio_journal_ctx)


def test_db_schema_critical_tables_exist():
    """DB has all tables that observation period depends on.
    Skipped if DB not bootstrapped (CI fresh env). Schema bootstrap is manual
    (one-time sqlite3 CLI setup, no init code in repo - pre-existing debt).
    """
    from shared import storage

    with storage.db() as conn:
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()}

    if not tables:
        pytest.skip("DB schema not bootstrapped (CI/fresh env) - smoke test is local-dev only")

    required = {
        # Core entities
        "signals", "sources", "theses", "decisions", "predictions",
        # Position tracking (Phase B5)
        "positions", "position_events",
        # Materiality + embeddings
        "conviction_history", "signal_embeddings",
        # Observability
        "llm_calls", "handler_calls",
        # Macro
        "events", "filings_8k_log",
    }
    missing = required - tables
    assert not missing, f"Missing required tables: {missing}"


def test_db_wal_mode_active():
    """SQLite WAL mode required for concurrent reads during cron jobs.
    Skipped if DB not bootstrapped (WAL set on first bot startup).
    """
    from shared import storage

    with storage.db() as conn:
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()}
        if not tables:
            pytest.skip("DB not bootstrapped (CI/fresh env) - WAL set on bot startup")
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal", f"DB not in WAL mode (got: {mode})"


def test_llm_cascade_models_configured():
    """LLM cascade requires 3 tiers configured. Crash early if missing."""
    from shared import config

    cfg = config.load()
    tiers = cfg.get("tiers", {})

    required_tiers = ["extract", "enrich", "synthesize"]
    for t in required_tiers:
        assert t in tiers, f"Tier '{t}' not in config.yaml"
        assert tiers[t], f"Tier '{t}' is empty"


def test_horizon_diversification_active():
    """Ship A diversification — different signal_types -> different horizons."""
    from intelligence.learning import horizon_for_signal_type

    # Should differ by signal_type
    h_catalyst = horizon_for_signal_type("catalyst")
    h_narrative = horizon_for_signal_type("narrative")
    assert h_catalyst != h_narrative, "horizon_for_signal_type not differentiating types"
    assert 7 <= h_catalyst <= 30
    assert 30 <= h_narrative <= 90


def test_backup_script_exists_and_executable():
    """Daily backup must be functional during observation."""
    import os
    from pathlib import Path
    p = Path("scripts/backup.sh")
    assert p.exists(), "scripts/backup.sh missing"
    assert os.access(p, os.X_OK), "scripts/backup.sh not executable"
