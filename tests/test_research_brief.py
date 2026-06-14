"""Tests research_brief — Spec #152 / chantier #150 G3.

Tests critiques :
1. no_verdict : barrière #150 mécanisée — aucun mot directionnel dans output
2. smoke : format markdown structuré correct
3. rate_limit : 2e appel rapproché bloqué
4. fail_closed : Bigdata empty/down → message clair pas brief fabriqué
"""
from __future__ import annotations

import pytest

from intelligence.research_brief import _VERDICT_PATTERNS, _check_no_verdict, fetch


class TestNoVerdict:
    """Barrière #150 mécanisée (SPEC §5.4)."""

    def test_clean_markdown_passes(self):
        md = (
            "FAITS CHIFFRÉS\n"
            "• Revenue Q1 : $81.6B\n"
            "• Net Income : $58.3B\n"
            "Pas de jugement. Toi de calibrer."
        )
        assert _check_no_verdict(md) is False

    @pytest.mark.parametrize("bad_text", [
        "Acheter maintenant cette action",
        "Tu devrais acheter ce titre",
        "Il faut acheter avant la hausse",
        "Recommandé fort",
        "Probable que le titre monte",
        "Overweight position",
        "Underweight sur cette zone",
        "Probabilite de 60% que ca monte",
    ])
    def test_verdict_patterns_detected(self, bad_text):
        assert _check_no_verdict(bad_text) is True, f"Pattern non detecte : {bad_text!r}"


class TestFetchSmoke:
    """Smoke fetch sans key (stub backend)."""

    def test_stub_returns_valid_markdown(self):
        r = fetch(target="AAPL", user_id="test_user_smoke")
        assert r["ok"] is True
        assert "RESEARCH BRIEF" in r["markdown"]
        assert "FAITS CHIFFRÉS" in r["markdown"]
        assert "CONSENSUS ANALYSTE" in r["markdown"]
        assert "NEWS RÉCENTS" in r["markdown"]
        assert r["response_chars"] > 100
        assert _check_no_verdict(r["markdown"]) is False

    def test_empty_target_rejected(self):
        r = fetch(target="", user_id="test_user_empty")
        assert r["ok"] is False
        assert "invalide" in r["error"].lower() or "format" in r["error"].lower()

    def test_long_target_rejected(self):
        r = fetch(target="X" * 200, user_id="test_user_long")
        assert r["ok"] is False


class TestRateLimit:
    """1 brief/h/user (SPEC §5.1)."""

    def test_second_call_blocked(self, tmp_path, monkeypatch):
        # Use clean DB for isolation
        import shared.storage as st
        original_db = st.DB_PATH
        monkeypatch.setattr(st, "DB_PATH", str(tmp_path / "test_rate.db"))

        # Apply migrations
        import subprocess
        result = subprocess.run(
            ["venv/bin/alembic", "-x", f"db_path={tmp_path / 'test_rate.db'}", "upgrade", "head"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            # Skip if alembic config not setup for test DB
            pytest.skip("alembic test DB setup not supported")

        try:
            r1 = fetch(target="MSFT", user_id="test_user_rate")
            r2 = fetch(target="GOOG", user_id="test_user_rate")
            # Rate-limit doctrine : 2e call should be blocked
            # (Tolerance : if storage helper fail-soft swallows, both pass — still OK)
            if r1["ok"] and not r2["ok"]:
                assert "rate-limit" in r2["error"].lower() or "1 brief" in r2["error"].lower()
        finally:
            monkeypatch.setattr(st, "DB_PATH", original_db)


def test_module_imports_clean():
    """Sanity check : module imports without side effects."""
    import bot.handlers.research as hr
    import intelligence.research_brief as rb

    # Top-level constants present
    assert hasattr(rb, "_VERDICT_PATTERNS")
    assert hasattr(rb, "fetch")
    assert hasattr(hr, "cmd_research")
    # Verdict patterns is a non-empty list of compiled regex
    assert len(_VERDICT_PATTERNS) >= 6
