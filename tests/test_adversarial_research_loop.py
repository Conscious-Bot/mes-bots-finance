"""Smoke tests for intelligence/adversarial_research_loop.py.

Pattern : tracer-bullet style (memory `feedback_walking_skeleton`).
Pas de live network call — backend mocke via _StubBackend qui retourne
"BIGDATA_API_KEY not configured" placeholders. Verifie l'orchestration
(4 stages run + markdown format + anti-anchoring gate + log).
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def isolated_db(monkeypatch):
    """Isolated DB pour insert_research_brief_log."""
    db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db.close()
    monkeypatch.setenv("PRESAGE_DB_PATH", db.name)
    # Create minimal schema
    cx = sqlite3.connect(db.name)
    cx.execute("""
        CREATE TABLE research_brief_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_id TEXT NOT NULL,
            target TEXT NOT NULL,
            target_type TEXT,
            success INTEGER NOT NULL,
            cost_actual_usd REAL,
            error_reason TEXT,
            response_chars INTEGER
        )
    """)
    cx.commit()
    cx.close()
    yield db.name
    Path(db.name).unlink(missing_ok=True)


def test_invalid_target_rejected():
    """Empty/oversized target -> error."""
    from intelligence.adversarial_research_loop import run
    r = run("", "user1")
    assert not r.ok
    assert "invalide" in (r.error or "").lower()
    r = run("X" * 200, "user1")
    assert not r.ok


def test_loop_runs_4_stages_with_stub_backend(monkeypatch, isolated_db):
    """Sans BIGDATA_API_KEY ni ANTHROPIC_API_KEY -> stub backend.
    Stage 4 + 5 LLM skip silently sur stub (claims vides). Markdown reste OK.
    """
    monkeypatch.delenv("BIGDATA_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from intelligence.adversarial_research_loop import run
    r = run("AAPL", "user_test")
    assert r.ok
    assert len(r.raw_bull_chunks) >= 1
    assert len(r.raw_bear_chunks) >= 1
    assert len(r.raw_counter_chunks) >= 1
    # Stage 4 skipped sur stub -> claims empty
    assert r.claims_bull == []
    assert r.claims_bear == []
    # Markdown contains key section markers
    assert "ADVERSARIAL BRIEF" in r.markdown
    assert "BULL CLAIMS" in r.markdown
    assert "BEAR CLAIMS" in r.markdown
    assert "VERDICT GRID" in r.markdown


def test_anti_anchoring_gate_catches_verdict_pattern(monkeypatch, isolated_db):
    """Si _format_markdown introduisait un verdict pattern, gate refuserait."""
    from intelligence.adversarial_research_loop import _check_no_verdict
    # Sanity : current markdown template ne match aucun pattern verdict
    sample = "Bull case : strong growth. Bear case : valuation stretched."
    assert _check_no_verdict(sample) is False
    # Mais une violation deliberee est catchee
    leak = "Recommande achete strong buy."
    assert _check_no_verdict(leak) is True


def test_result_dataclass_shape():
    """LoopResult instanciable avec defaults coherents."""
    from intelligence.adversarial_research_loop import Claim, LoopResult
    r = LoopResult(target="AAPL", asof="2026-06-23 12:00 UTC")
    assert r.target == "AAPL"
    assert r.claims_bull == []
    assert r.n_claims_confirmed == 0
    assert r.ok is False
    c = Claim(stance="bull", text="strong growth")
    assert c.stance == "bull"
    assert c.verdict == "unverified"
