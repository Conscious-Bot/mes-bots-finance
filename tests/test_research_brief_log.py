"""Tests research_brief_log helpers (spec #152 / migration 0061).

2 tests scope minimal :
1. INSERT helper + check_rate_limit fire correctement
2. INSERT helper + append-only trigger DELETE/UPDATE interdit
"""
from __future__ import annotations

import time

import pytest


def test_insert_ok_and_rate_limit_fires(migrated_db):
    """INSERT puis check_rate_limit dans la meme seconde : doit refuser le 2e."""
    from shared import storage as s

    pid = s.insert_research_brief_log(
        user_id="test_user_1", target="MGM", target_type="ticker",
        success=True, cost_actual_usd=0.08, response_chars=1500,
    )
    assert pid is not None and pid > 0

    # Immediatement apres, rate-limit doit refuser (1h window default)
    check = s.check_research_brief_rate_limit("test_user_1")
    assert check["allowed"] is False
    assert check["last_at"] is not None
    assert check["retry_after_seconds"] > 0
    assert check["retry_after_seconds"] <= 3600  # raisonnable

    # User different : pas affecte par le rate-limit
    check_other = s.check_research_brief_rate_limit("test_user_2")
    assert check_other["allowed"] is True

    # Window 0 sec : passe immediatement (utile pour tests rapides)
    check_zero = s.check_research_brief_rate_limit("test_user_1", window_seconds=0)
    assert check_zero["allowed"] is True


def test_append_only_triggers(migrated_db):
    """research_brief_log : DELETE et UPDATE interdits par triggers."""
    import sqlite3

    from shared import storage as s

    pid = s.insert_research_brief_log(
        user_id="test_user_audit", target="MSFT", target_type="ticker",
        success=True, cost_actual_usd=0.10,
    )
    assert pid is not None

    # DELETE interdit
    with s.db() as cx:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            cx.execute("DELETE FROM research_brief_log WHERE id = ?", (pid,))

    # UPDATE interdit
    with s.db() as cx:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            cx.execute(
                "UPDATE research_brief_log SET success = 0 WHERE id = ?", (pid,)
            )

    # Verifier que la row est toujours la (pas de mutation accidentelle)
    with s.db() as cx:
        row = cx.execute(
            "SELECT success FROM research_brief_log WHERE id = ?", (pid,)
        ).fetchone()
        assert row is not None
        assert row[0] == 1  # success = True stocke 1


def test_invalid_target_type_raises(migrated_db):
    """target_type doit etre IN ('ticker', 'theme')."""
    from shared import storage as s

    with pytest.raises(ValueError, match="target_type"):
        s.insert_research_brief_log(
            user_id="test_user_3", target="foo", target_type="invented",
            success=True,
        )


def test_cost_today_sum_per_user(migrated_db):
    """Sum cost_actual_usd today per user pour budget hard-stop."""
    from shared import storage as s

    s.insert_research_brief_log(
        user_id="budget_user", target="A", target_type="ticker",
        success=True, cost_actual_usd=0.05,
    )
    s.insert_research_brief_log(
        user_id="budget_user", target="B", target_type="ticker",
        success=True, cost_actual_usd=0.07,
    )
    # Autre user : pas compte dans le total budget_user
    s.insert_research_brief_log(
        user_id="other_user", target="X", target_type="theme",
        success=True, cost_actual_usd=0.20,
    )

    total = s.get_research_brief_cost_today("budget_user")
    assert abs(total - 0.12) < 0.001  # 0.05 + 0.07

    total_other = s.get_research_brief_cost_today("other_user")
    assert abs(total_other - 0.20) < 0.001
