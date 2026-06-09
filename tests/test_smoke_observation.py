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
        "cmd_position_buy",
        "cmd_position_sell",
        "cmd_portfolio",
        # Monitoring handlers (Path 5/6 dimension 2)
        "cmd_bot_data",
        "cmd_cost_trajectory",
        "cmd_handler_stats",
        # Asymmetry + risk (anti-bias core)
        "cmd_asymmetry",
        "cmd_risk_check",
        # Ritual matinal
        "cmd_brief",
        "cmd_digest",
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
        "weekly_kpi_status_job",  # Sun 22:30
        "weekly_cost_summary_job",  # Sun 22:00
        "weekly_handler_stats_job",  # Sun 23:00
        "daily_backup_job",  # 04:00 daily
    ]
    for c in crons:
        assert hasattr(main, c), f"Cron job {c} missing"
        assert callable(getattr(main, c)), f"{c} not callable"


def test_phase_b5_journal_helpers_present():
    """Phase B5 journal integration helpers exposed (post-Ship 5 restoration)."""
    from intelligence import bias_tagger
    from shared import storage

    storage_helpers = [
        "log_decision",
        "get_decision",
        "get_position_by_ticker",
        "update_decision_bias_tags",
        "get_active_positions",
        "get_positions_history",
        "get_bias_stats",
        "create_or_update_position_on_buy",
        "record_position_sell",
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


def test_db_schema_critical_tables_exist(tmp_path):
    """DB schema bootstrap creates all tables required by observation period.

    Sprint 1.3: now uses bootstrap_schema() on a fresh tmp DB instead of
    skipping in CI. Validates the migration is self-sufficient.
    """
    import sqlite3

    from shared.storage import bootstrap_schema

    test_db = tmp_path / "test_bootstrap.db"
    bootstrap_schema(db_path=str(test_db))

    conn = sqlite3.connect(test_db)
    tables = {
        r[0]
        for r in conn.execute(
            # Inclut VIEWs depuis migration 0048 (positions = VUE dérivée)
            "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    conn.close()

    required = {
        # Core entities
        "signals",
        "sources",
        "theses",
        "decisions",
        "predictions",
        # Position tracking (Phase B5)
        "positions",
        "position_events",
        # Materiality + embeddings
        "conviction_history",
        "signal_embeddings",
        # Observability
        "llm_calls",
        "handler_calls",
        # Macro
        "events",
        "filings_8k_log",
    }
    missing = required - tables
    assert not missing, f"Missing required tables: {missing}"


def test_db_wal_mode_active(tmp_path):
    """bootstrap_schema sets WAL mode on the DB.

    Sprint 1.3: now uses bootstrap_schema() on a fresh tmp DB instead of
    skipping in CI. Validates WAL is part of the bootstrap protocol.
    """
    import sqlite3

    from shared.storage import bootstrap_schema

    test_db = tmp_path / "test_wal.db"
    bootstrap_schema(db_path=str(test_db))

    conn = sqlite3.connect(test_db)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()

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


def test_uptime_monitor_uses_case_insensitive_pgrep():
    """Regression guard for 2026-05-14 case-sensitivity postmortem (AI #4).

    `crons/uptime_monitor.sh` must use case-insensitive pgrep. macOS Python
    binary is capital-P; case-sensitive `pgrep -f` missed it for 3+ days,
    producing 422 false-negative FAIL entries.

    See docs/post-mortems/2026-05-14-uptime-monitor-case-bug.md
    """
    from pathlib import Path

    script = Path("crons/uptime_monitor.sh")
    assert script.exists(), "crons/uptime_monitor.sh missing"

    content = script.read_text()
    has_case_insensitive = (
        "pgrep -fi" in content or "pgrep -if" in content or "pgrep -i " in content or "pgrep -i\t" in content
    )
    assert has_case_insensitive, (
        "crons/uptime_monitor.sh does not use case-insensitive pgrep. "
        "macOS capital-P Python binary requires -i flag. "
        "See docs/post-mortems/2026-05-14-uptime-monitor-case-bug.md"
    )


def test_no_duplicate_handler_registrations():
    """Regression guard for 2026-05-14 dup handler postmortem (AI #10).

    bot/main.py must not register the same CommandHandler command name
    twice. Ship 5 deleted dup cmd_position_buy/sell defs but left both
    add_handler() calls (commit c6d959a fixed this). Per AI #9 audit, dup
    registrations are dead code in python-telegram-bot v21+ (only first
    matching handler in group fires), but still bad hygiene + defensive
    against library version upgrades that might change group semantics.

    AST inspection — no runtime import needed.

    See docs/post-mortems/2026-05-14-duplicate-position-handler-registration.md
    """
    import ast
    from pathlib import Path

    src = Path("bot/main.py").read_text()
    tree = ast.parse(src)

    seen_commands: dict[str, int] = {}
    duplicates: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "add_handler"):
            continue
        if not node.args:
            continue

        first_arg = node.args[0]
        if not (
            isinstance(first_arg, ast.Call)
            and isinstance(first_arg.func, ast.Name)
            and first_arg.func.id == "CommandHandler"
        ):
            continue

        if not first_arg.args:
            continue
        cmd_arg = first_arg.args[0]
        if not (isinstance(cmd_arg, ast.Constant) and isinstance(cmd_arg.value, str)):
            continue

        cmd_name = cmd_arg.value
        line_no = node.lineno

        if cmd_name in seen_commands:
            duplicates.append(f"/{cmd_name} registered at L{seen_commands[cmd_name]} AND L{line_no}")
        else:
            seen_commands[cmd_name] = line_no

    assert not duplicates, (
        "Duplicate CommandHandler registrations found in bot/main.py:\n  "
        + "\n  ".join(duplicates)
        + "\nSee docs/post-mortems/2026-05-14-duplicate-position-handler-registration.md"
    )


# === Regression guards for scripts/bot_health_check.sh (AI #3, 2026-05-14) ===
from pathlib import Path as _Path_for_health

_HEALTH_REPO_ROOT = _Path_for_health(__file__).resolve().parents[1]
HEALTH_SCRIPT = _HEALTH_REPO_ROOT / "scripts" / "bot_health_check.sh"


def test_bot_health_check_exists_and_executable():
    """Script file is present and has the executable bit set."""
    assert HEALTH_SCRIPT.exists(), f"missing: {HEALTH_SCRIPT}"
    assert HEALTH_SCRIPT.stat().st_mode & 0o111, "bot_health_check.sh is not executable"


def test_bot_health_check_uses_case_insensitive_pgrep():
    """Every pgrep invocation in the script uses -fi (or -i).

    Same lesson as uptime_monitor case-bug 2026-05-14: macOS pgrep is
    case-sensitive on cmdline by default. Python.app binary path contains
    capital P, so `pgrep -f python` misses it. Use -fi.
    """
    text = HEALTH_SCRIPT.read_text()
    pgrep_lines = [line.rstrip() for line in text.splitlines() if "pgrep" in line and not line.lstrip().startswith("#")]
    assert pgrep_lines, "no pgrep calls found — has the script been refactored?"
    for line in pgrep_lines:
        assert ("-fi" in line) or (" -i " in line) or (' -i"' in line), (
            f"pgrep without case-insensitive flag (-fi or -i): {line!r}\n"
            "macOS Python.app cmdline contains capital P. Use -fi."
        )


def test_bot_health_check_trap_preserves_exit_code():
    """EXIT trap must capture $? before cleanup and re-exit with it.

    Bash EXIT trap runs the trap action, and the LAST command's rc becomes the
    shell's exit code unless explicitly preserved. A naive `trap 'rm -f X' EXIT`
    silently overrides `exit 3` with `rm`'s rc=0.
    """
    text = HEALTH_SCRIPT.read_text()
    assert "rc=$?" in text, (
        "EXIT trap must capture $? at entry. Without it, cleanup overrides the script's intended exit code."
    )
    assert 'exit "$rc"' in text or "exit $rc" in text, "EXIT trap must re-exit with the preserved rc."


def test_bot_health_check_handles_missing_files_gracefully():
    """Critical file paths are guarded with [ -f ... ] checks (no unguarded reads).

    The script must not crash if data/bot.db, data/bot_state.json, or bot.log
    are missing — those are the failure modes the health check is meant to
    surface, not blow up on.
    """
    text = HEALTH_SCRIPT.read_text()
    for var in ["DB_PATH", "STATE_JSON", "BOT_LOG"]:
        has_guard = f'[ -f "${var}" ]' in text or f'[ ! -f "${var}" ]' in text
        assert has_guard, (
            f"${var} is used but never guarded with [ -f ... ]. "
            "Missing-file scenarios will crash the script instead of "
            "being reported as a signal."
        )


def test_bot_health_check_exit_codes_documented():
    """The script's header documents all four exit codes (0/1/2/3) and the
    corresponding GREEN/RED/ORANGE/CRITICAL verdict labels are present."""
    text = HEALTH_SCRIPT.read_text()
    for code, label in [("0", "GREEN"), ("1", "RED"), ("2", "ORANGE"), ("3", "CRITICAL")]:
        assert f"{code} =" in text or f"{code}=" in text, f"exit code {code} not documented"
        assert label in text, f"verdict label {label} not present in script"
