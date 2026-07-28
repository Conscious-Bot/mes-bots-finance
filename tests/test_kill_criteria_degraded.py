"""Cure 28/07/2026 — kill_criteria degraded ne s'affiche plus « success ».

Post-mortem : LLM-down 04→20/07 (credit_exhausted) = 16 jours ou
check_one_thesis avalait LLMUnavailableError → return None → compte
« skipped » → daily_kill_criteria_check_job loggait INFO et _safe_run
journalisait success dans scheduler_runs, alors que 0 evaluation n'etait
produite. Meme classe que la cure over_cap 04/07 (L25 : la classe, pas
l'instance).

Contrat verrouille ici :
1. check_one_thesis RE-RAISE LLMUnavailableError (≠ skip legitime).
2. check_all_active_theses : break au 1er LLMUnavailableError (#93, pas de
   martelage de l'API morte), compte les non-evaluees dans out["llm_down"].
3. daily_kill_criteria_check_job : raise RuntimeError si llm_down > 0 OU
   (theses eligibles > 0 ET 0 evaluation produite) → _safe_run journalise
   failed dans scheduler_runs (L21 : pas plus confiant que son evidence).
4. Sortie saine / book vide : pas de raise.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from shared.llm import LLMUnavailableError


def _thesis_dict() -> dict:
    return {
        "id": 1,
        "ticker": "NVDA",
        "conviction": 3,
        "direction": "long",
        "opened_at": "2026-04-01T00:00:00Z",
        "last_reviewed": "2026-07-01T00:00:00Z",
        "entry_price": 100.0,
        "target_partial": 130.0,
        "target_full": 150.0,
        "stop_price": 80.0,
        "invalidation_triggers": json.dumps([{"trigger": "FCF negatif 2 trimestres"}]),
    }


_FAKE_STATE = {
    "age_days": 30,
    "days_since_review": 5,
    "current_price": 110.0,
    "pnl_pct": 10.0,
    "margin_to_stop_pct": 27.0,
    "margin_to_target_pct": 36.0,
}


def _patch_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from intelligence import kill_criteria_monitor as kcm

    monkeypatch.setattr(kcm, "_compute_current_state", lambda th: dict(_FAKE_STATE))
    monkeypatch.setattr(kcm, "_fetch_recent_signals", lambda tk: "(aucun signal)")


# ---------------------------------------------------------------- couche 1


def test_check_one_thesis_reraises_llm_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM indisponible = panne infra, PAS un skip de these. Doit remonter."""
    from intelligence import kill_criteria_monitor as kcm

    _patch_state(monkeypatch)

    def _boom(*a, **k):
        raise LLMUnavailableError("credit_exhausted")

    monkeypatch.setattr(kcm.llm, "call_json", _boom)
    with pytest.raises(LLMUnavailableError):
        kcm.check_one_thesis(_thesis_dict())


def test_check_one_thesis_generic_llm_error_still_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Erreur LLM generique (JSON pourri etc.) : skip resilient inchange."""
    from intelligence import kill_criteria_monitor as kcm

    _patch_state(monkeypatch)

    def _bad(*a, **k):
        raise ValueError("json decode mess")

    monkeypatch.setattr(kcm.llm, "call_json", _bad)
    res, alert = kcm.check_one_thesis(_thesis_dict())
    assert res is None and alert is None


# ---------------------------------------------------------------- couche 2


def _isolated_db_with_theses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, n: int = 3) -> Path:
    db = tmp_path / "test.db"
    cx = sqlite3.connect(db)
    cx.executescript(
        """
        CREATE TABLE theses (
            id INTEGER PRIMARY KEY, ticker TEXT, conviction INTEGER,
            direction TEXT, opened_at TEXT, last_reviewed TEXT,
            entry_price REAL, target_partial REAL, target_full REAL,
            stop_price REAL, invalidation_triggers TEXT, status TEXT
        );
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY, ticker TEXT, qty REAL, status TEXT
        );
        """
    )
    for i in range(n):
        tk = f"TK{i}"
        cx.execute(
            "INSERT INTO theses (ticker, conviction, direction, opened_at, "
            "entry_price, invalidation_triggers, status) "
            "VALUES (?, 3, 'long', '2026-04-01', 100.0, '[{\"trigger\":\"x\"}]', 'active')",
            (tk,),
        )
        cx.execute(
            "INSERT INTO positions (ticker, qty, status) VALUES (?, 10.0, 'open')",
            (tk,),
        )
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db)
    return db


def test_check_all_llm_down_breaks_and_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API morte des la 1re these : break immediat (#93), llm_down = total."""
    from intelligence import kill_criteria_monitor as kcm

    _isolated_db_with_theses(tmp_path, monkeypatch, n=3)
    calls = {"n": 0}

    def _down(th):
        calls["n"] += 1
        raise LLMUnavailableError("credit_exhausted")

    monkeypatch.setattr(kcm, "check_one_thesis", _down)
    out = kcm.check_all_active_theses()
    assert out["llm_down"] == 3
    assert calls["n"] == 1, "l'API morte ne doit PAS etre martelee sur les theses restantes"
    assert out["triggered"] + out["at_risk"] + out["dormant"] == 0


def test_check_all_llm_down_mid_loop_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Panne en cours de boucle : les evaluations deja produites restent comptees."""
    from intelligence import kill_criteria_monitor as kcm

    _isolated_db_with_theses(tmp_path, monkeypatch, n=3)
    seq = iter(["ok", "down"])

    def _mixed(th):
        if next(seq) == "ok":
            return {"global_status": "dormant"}, None
        raise LLMUnavailableError("rate_limited")

    monkeypatch.setattr(kcm, "check_one_thesis", _mixed)
    out = kcm.check_all_active_theses()
    assert out["dormant"] == 1
    assert out["llm_down"] == 2  # la these en cours + la restante


# ---------------------------------------------------------------- couche 3 (job)


def _out(**over) -> dict:
    base = {"triggered": 0, "at_risk": 0, "dormant": 0, "skipped": 0, "failed": 0, "llm_down": 0}
    base.update(over)
    return base


def _run_job_with(monkeypatch: pytest.MonkeyPatch, fake_out: dict) -> None:
    from bot.jobs.daily import daily_kill_criteria_check_job
    from intelligence import kill_criteria_monitor as kcm

    monkeypatch.setattr(kcm, "check_all_active_theses", lambda: fake_out)
    asyncio.run(daily_kill_criteria_check_job())


def test_job_raises_on_llm_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le cas des 16 jours : llm_down doit finir en failed, pas en success."""
    with pytest.raises(RuntimeError, match="degraded"):
        _run_job_with(monkeypatch, _out(llm_down=25))


def test_job_raises_on_zero_produced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Toutes skipped (prix down partout, triggers vides...) : degraded aussi."""
    with pytest.raises(RuntimeError, match="degraded"):
        _run_job_with(monkeypatch, _out(skipped=25))


def test_job_ok_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sortie saine avec skips legitimes partiels : pas de raise."""
    _run_job_with(monkeypatch, _out(dormant=20, at_risk=2, skipped=3))


def test_job_ok_empty_book(monkeypatch: pytest.MonkeyPatch) -> None:
    """0 these active = rien a evaluer, success legitime."""
    _run_job_with(monkeypatch, _out())
