"""#87 -- Cost cap LLM (mitigation vendor lock Anthropic).

Verifie que `shared.llm._check_cost_cap()` :
  - Pass quand usage < cap
  - Raise CostCapExceeded quand usage >= cap
  - Respecte env var override LLM_COST_CAP_USD_24H
  - Bypass via LLM_COST_CAP_DISABLE=1
  - Fail-open si DB indispo (ne bloque pas le bot en panne)
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from shared import llm
from shared.llm import CostCapExceeded


@pytest.fixture
def isolated_llm_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """DB temp avec table llm_calls + monkeypatch llm._DB_PATH."""
    db = tmp_path / "llm.db"
    cx = sqlite3.connect(db)
    cx.executescript("""
        CREATE TABLE llm_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tier TEXT, model TEXT, task TEXT,
            input_tokens INTEGER, output_tokens INTEGER, cached_tokens INTEGER,
            cost_usd REAL, elapsed_ms INTEGER, error TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cx.commit()
    cx.close()
    monkeypatch.setattr(llm, "_DB_PATH", str(db))
    # Reset warn counter pour ne pas heriter entre tests
    monkeypatch.setattr(llm, "_COST_CAP_LAST_WARNED", 0.0)
    return db


def _insert_calls(db: Path, cost_usd: float, n: int = 1) -> None:
    cx = sqlite3.connect(db)
    for _ in range(n):
        cx.execute(
            "INSERT INTO llm_calls (tier, model, task, input_tokens, output_tokens, "
            "cached_tokens, cost_usd, elapsed_ms) VALUES "
            "('extract', 'haiku-3.5', 'test', 100, 50, 0, ?, 200)",
            (cost_usd,),
        )
    cx.commit()
    cx.close()


# ─── Path nominal : pass + raise ──────────────────────────────────────────


def test_cap_pass_under_threshold(isolated_llm_db, monkeypatch):
    """Usage 1 USD, cap 10 USD -> pass."""
    monkeypatch.setenv("LLM_COST_CAP_USD_24H", "10.0")
    monkeypatch.delenv("LLM_COST_CAP_DISABLE", raising=False)
    _insert_calls(isolated_llm_db, cost_usd=1.0)
    # Doit pas raise
    llm._check_cost_cap()


def test_cap_raise_at_threshold(isolated_llm_db, monkeypatch):
    """Usage 10 USD, cap 10 USD -> raise."""
    monkeypatch.setenv("LLM_COST_CAP_USD_24H", "10.0")
    monkeypatch.delenv("LLM_COST_CAP_DISABLE", raising=False)
    _insert_calls(isolated_llm_db, cost_usd=10.0)
    with pytest.raises(CostCapExceeded, match="LLM cost cap atteint"):
        llm._check_cost_cap()


def test_cap_raise_above_threshold(isolated_llm_db, monkeypatch):
    """Usage 15 USD, cap 10 USD -> raise avec montant."""
    monkeypatch.setenv("LLM_COST_CAP_USD_24H", "10.0")
    monkeypatch.delenv("LLM_COST_CAP_DISABLE", raising=False)
    _insert_calls(isolated_llm_db, cost_usd=15.0)
    with pytest.raises(CostCapExceeded) as exc:
        llm._check_cost_cap()
    assert "15.00" in str(exc.value)


# ─── Overrides : disable + custom cap ─────────────────────────────────────


def test_disable_bypass(isolated_llm_db, monkeypatch):
    """LLM_COST_CAP_DISABLE=1 -> pass meme au-dessus du cap."""
    monkeypatch.setenv("LLM_COST_CAP_USD_24H", "10.0")
    monkeypatch.setenv("LLM_COST_CAP_DISABLE", "1")
    _insert_calls(isolated_llm_db, cost_usd=50.0)
    llm._check_cost_cap()  # pas de raise


def test_custom_cap_via_env(isolated_llm_db, monkeypatch):
    """LLM_COST_CAP_USD_24H=2.0 -> raise a 2 USD."""
    monkeypatch.setenv("LLM_COST_CAP_USD_24H", "2.0")
    monkeypatch.delenv("LLM_COST_CAP_DISABLE", raising=False)
    _insert_calls(isolated_llm_db, cost_usd=2.5)
    with pytest.raises(CostCapExceeded):
        llm._check_cost_cap()


def test_cap_zero_disables(isolated_llm_db, monkeypatch):
    """LLM_COST_CAP_USD_24H=0 -> disable (pas de raise jamais)."""
    monkeypatch.setenv("LLM_COST_CAP_USD_24H", "0")
    monkeypatch.delenv("LLM_COST_CAP_DISABLE", raising=False)
    _insert_calls(isolated_llm_db, cost_usd=100.0)
    llm._check_cost_cap()  # pas de raise


def test_invalid_cap_env_falls_back_to_default(isolated_llm_db, monkeypatch):
    """LLM_COST_CAP_USD_24H='garbage' -> fallback 10.0 USD default."""
    monkeypatch.setenv("LLM_COST_CAP_USD_24H", "not_a_number")
    monkeypatch.delenv("LLM_COST_CAP_DISABLE", raising=False)
    _insert_calls(isolated_llm_db, cost_usd=11.0)
    with pytest.raises(CostCapExceeded):
        llm._check_cost_cap()


# ─── Fail-safe : DB indispo ───────────────────────────────────────────────


def test_fail_open_on_db_error(monkeypatch):
    """Si la DB est inaccessible, _get_cost_usage_24h retourne 0 -> pass.
    Choix conscient : fail-open pour ne pas bloquer le bot si DB en panne.
    Le risque cost-runaway dans ce cas est secondaire vs downtime user."""
    monkeypatch.setattr(llm, "_DB_PATH", "/nonexistent/path/to/db")
    monkeypatch.setenv("LLM_COST_CAP_USD_24H", "10.0")
    monkeypatch.delenv("LLM_COST_CAP_DISABLE", raising=False)
    assert llm._get_cost_usage_24h() == 0.0
    llm._check_cost_cap()  # pas de raise (fail-open)


# ─── Soft warn 80% ────────────────────────────────────────────────────────


def test_soft_warn_at_80pct(isolated_llm_db, monkeypatch, caplog):
    """A 80% du cap, log warning (mais pas raise)."""
    import logging
    monkeypatch.setenv("LLM_COST_CAP_USD_24H", "10.0")
    monkeypatch.delenv("LLM_COST_CAP_DISABLE", raising=False)
    _insert_calls(isolated_llm_db, cost_usd=8.5)  # 85%
    with caplog.at_level(logging.WARNING, logger="shared.llm"):
        llm._check_cost_cap()
    assert any("approche cap" in rec.message for rec in caplog.records), (
        f"Expected 'approche cap' warning, got: {[r.message for r in caplog.records]}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
