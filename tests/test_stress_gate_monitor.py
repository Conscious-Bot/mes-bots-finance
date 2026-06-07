"""Axe 4 QUALITY_BAR tests : stress_gate_monitor.

Pattern monitor canonique : docs/templates/monitor_pattern.md.
Stress-gate = etat structurel (concentration excessive), pas comportemental
-> pas de wire bias_events. Le canal fomo_greed (kill_criteria + over_cap)
gere deja le biais cognitif.

Tests :
1. Transition * -> breach : 1 notify, 1 audit transition=enter_breach notified=1
2. Etat stable breach -> breach : 0 notify, 1 audit no_change
3. Etat warn -> ok : 1 audit transition=recover_ok, 0 notify
4. TEST CRITIQUE L4 : 2 cycles consecutifs en breach -> 1 seul notify
   (le journal porte prev_status, pas un journal externe)
5. Config absente -> skip propre (fail-closed L15)
6. Fail-safe : 1 scenario raise -> comptee en errors, autres continuent
7. classify pur : drawdown manquant -> MissingStressDataError ; error -> None
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from intelligence import stress_gate_monitor as sgm
from intelligence.stress_gate_monitor import MissingStressDataError


def _schema_minimal(cx: sqlite3.Connection) -> None:
    """Clone DDL migration 0037 (stress_gate_alerts)."""
    cx.executescript("""
        CREATE TABLE stress_gate_alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            scenario_name   TEXT NOT NULL,
            status          TEXT NOT NULL CHECK(status IN ('ok', 'warn', 'breach')),
            drawdown_pct    REAL NOT NULL,
            warn_pct        REAL NOT NULL,
            breach_pct      REAL NOT NULL,
            notified        INTEGER NOT NULL DEFAULT 0,
            transition      TEXT CHECK(transition IN (
                'enter_breach', 'enter_warn', 'recover_ok',
                'recover_warn', 'no_change', NULL
            ))
        );
    """)


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "test.db"
    cx = sqlite3.connect(db)
    _schema_minimal(cx)
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db)
    return db


def _mock_config(
    monkeypatch: pytest.MonkeyPatch,
    warn_pct: float = -25.0,
    breach_pct: float = -30.0,
    overrides: dict | None = None,
    notify_on_breach: bool = True,
) -> None:
    """Stub shared.risk_watch.load_risk_watch avec stress_gate config."""
    cfg = {
        "stress_gate": {
            "default_thresholds": {
                "warn_pct": warn_pct,
                "breach_pct": breach_pct,
            },
            "per_scenario_overrides": overrides or {},
            "notify_on_breach": notify_on_breach,
        },
    }
    import shared.risk_watch
    monkeypatch.setattr(shared.risk_watch, "load_risk_watch", lambda: cfg)


def _mock_scenarios(
    monkeypatch: pytest.MonkeyPatch,
    scenarios: dict[str, dict],
) -> None:
    """Stub factor_exposures.{_STRESS_SCENARIOS, run_stress_test}.

    scenarios = {scenario_name: run_stress_test_return_value}
    """
    import intelligence.factor_exposures as fe
    monkeypatch.setattr(fe, "_STRESS_SCENARIOS", scenarios)
    def _fake_run(name: str) -> dict:
        return scenarios[name]
    monkeypatch.setattr(fe, "run_stress_test", _fake_run)


def _mock_notify(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    import shared.notify
    fake = MagicMock()
    monkeypatch.setattr(shared.notify, "send_text", fake)
    return fake


def _query(db: Path, sql: str, params: tuple = ()) -> list[tuple]:
    cx = sqlite3.connect(db)
    rows = cx.execute(sql, params).fetchall()
    cx.close()
    return rows


# ─── Test 1 : transition * -> breach ───────────────────────────────────────


def test_transition_enter_breach_emits_notify_and_audit(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI capex -30% retourne -35% drawdown ; seuil breach -30%. Pas de prev row.
    Attendu : 1 notify, 1 audit transition=enter_breach notified=1 status=breach."""
    _mock_config(monkeypatch)
    _mock_scenarios(monkeypatch, {
        "AI capex -30%": {
            "scenario": "AI capex -30%",
            "total_drawdown_pct": -35.0,
            "total_drawdown_eur": -17500.0,
            "by_position": [],
            "n_positions_affected": 5,
        },
    })
    notify_mock = _mock_notify(monkeypatch)

    stats = sgm.check_all_stress_transitions()
    assert stats["checked"] == 1
    assert stats["breach"] == 1
    assert stats["transitions"] == 1
    assert stats["notified"] == 1
    assert notify_mock.call_count == 1
    msg = notify_mock.call_args[0][0]
    assert "AI capex -30%" in msg
    assert "-35.0" in msg

    rows = _query(isolated_db, "SELECT status, transition, notified FROM stress_gate_alerts")
    assert rows == [("breach", "enter_breach", 1)]


# ─── Test 2 : etat stable breach -> breach (no re-fire) ────────────────────


def test_stable_breach_no_renotify(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario reste en breach 2 cycles consecutifs : 1 seul notify."""
    _mock_config(monkeypatch)
    _mock_scenarios(monkeypatch, {
        "AI capex -30%": {
            "scenario": "AI capex -30%",
            "total_drawdown_pct": -35.0,
            "total_drawdown_eur": -17500.0,
            "by_position": [],
            "n_positions_affected": 5,
        },
    })
    notify_mock = _mock_notify(monkeypatch)

    # Cycle 1 : ok -> breach (notify)
    sgm.check_all_stress_transitions()
    assert notify_mock.call_count == 1

    # Cycle 2 : breach -> breach (pas de notify)
    sgm.check_all_stress_transitions()
    assert notify_mock.call_count == 1  # toujours 1

    rows = _query(
        isolated_db,
        "SELECT status, transition, notified FROM stress_gate_alerts ORDER BY id",
    )
    assert rows == [
        ("breach", "enter_breach", 1),
        ("breach", "no_change", 0),
    ]


# ─── Test 3 : recovery warn -> ok ──────────────────────────────────────────


def test_recovery_warn_to_ok_audit_only(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warn -> ok : 1 audit transition=recover_ok, 0 notify (recovery silencieuse)."""
    _mock_config(monkeypatch)

    # Cycle 1 : -27 → warn
    _mock_scenarios(monkeypatch, {
        "AI capex -30%": {
            "scenario": "AI capex -30%",
            "total_drawdown_pct": -27.0,
            "total_drawdown_eur": -13500.0,
            "by_position": [],
            "n_positions_affected": 5,
        },
    })
    notify_mock = _mock_notify(monkeypatch)
    sgm.check_all_stress_transitions()
    assert notify_mock.call_count == 0  # warn pas de notify

    # Cycle 2 : -10 → ok (recovery)
    _mock_scenarios(monkeypatch, {
        "AI capex -30%": {
            "scenario": "AI capex -30%",
            "total_drawdown_pct": -10.0,
            "total_drawdown_eur": -5000.0,
            "by_position": [],
            "n_positions_affected": 5,
        },
    })
    sgm.check_all_stress_transitions()
    assert notify_mock.call_count == 0  # recover pas de notify

    rows = _query(
        isolated_db,
        "SELECT status, transition FROM stress_gate_alerts ORDER BY id",
    )
    assert rows == [
        ("warn", "enter_warn"),
        ("ok", "recover_ok"),
    ]


# ─── Test 4 : TEST CRITIQUE L4 — pas de re-fire spurieux ───────────────────


def test_critical_L4_breach_persists_no_refire(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LE TEST L4 : breach persiste sur 3 cycles consecutifs, prev_status lu
    depuis stress_gate_alerts dedie. 3 audit rows, mais 1 seul notify (entree).

    Demontre que le journal dedie porte la verite, pas un cycle externe (bias_events)."""
    _mock_config(monkeypatch)
    _mock_scenarios(monkeypatch, {
        "AI capex -30%": {
            "scenario": "AI capex -30%",
            "total_drawdown_pct": -40.0,
            "total_drawdown_eur": -20000.0,
            "by_position": [],
            "n_positions_affected": 5,
        },
    })
    notify_mock = _mock_notify(monkeypatch)

    for _ in range(3):
        sgm.check_all_stress_transitions()

    assert notify_mock.call_count == 1  # entree breach 1 seule fois

    rows = _query(
        isolated_db,
        "SELECT status, transition, notified FROM stress_gate_alerts ORDER BY id",
    )
    assert len(rows) == 3
    assert rows[0] == ("breach", "enter_breach", 1)
    assert rows[1] == ("breach", "no_change", 0)
    assert rows[2] == ("breach", "no_change", 0)


# ─── Test 5 : cas degenere — config absente ────────────────────────────────


def test_config_absent_skip_propre(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L15 fail-closed : si stress_gate config absente, monitor skip sans
    fabriquer ni notify. stats vides."""
    import shared.risk_watch
    monkeypatch.setattr(shared.risk_watch, "load_risk_watch", lambda: None)
    notify_mock = _mock_notify(monkeypatch)

    stats = sgm.check_all_stress_transitions()
    assert stats["checked"] == 0
    assert stats["transitions"] == 0
    assert stats["notified"] == 0
    assert notify_mock.call_count == 0
    assert _query(isolated_db, "SELECT COUNT(*) FROM stress_gate_alerts") == [(0,)]


# ─── Test 6 : fail-safe — 1 scenario raise n'arrete pas la boucle ──────────


def test_failsafe_one_scenario_raise_others_continue(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si run_stress_test raise sur 1 scenario, les autres continuent.
    errors=1, checked=1 (autre scenario ok)."""
    _mock_config(monkeypatch)

    import intelligence.factor_exposures as fe
    scenarios = {
        "BROKEN": {},  # will trigger MissingStressDataError via classify
        "AI capex -30%": {
            "scenario": "AI capex -30%",
            "total_drawdown_pct": -35.0,
            "total_drawdown_eur": -17500.0,
            "by_position": [],
            "n_positions_affected": 5,
        },
    }
    monkeypatch.setattr(fe, "_STRESS_SCENARIOS", scenarios)

    def _fake_run(name: str) -> dict:
        if name == "BROKEN":
            # missing total_drawdown_pct -> MissingStressDataError via classify
            return {"scenario": "BROKEN"}
        return scenarios[name]
    monkeypatch.setattr(fe, "run_stress_test", _fake_run)
    _mock_notify(monkeypatch)

    stats = sgm.check_all_stress_transitions()
    assert stats["errors"] == 1
    assert stats["checked"] == 1
    assert stats["breach"] == 1
    rows = _query(isolated_db, "SELECT scenario_name FROM stress_gate_alerts")
    assert rows == [("AI capex -30%",)]


# ─── Test 7 : classify pur — distinguer error/missing/legitime ─────────────


def test_classify_distinguishes_error_vs_missing_vs_ok() -> None:
    """classify_stress_scenario doit :
    - result error -> None (non-classifiable legitime)
    - result manquant total_drawdown_pct -> raise MissingStressDataError
    - result valide -> dict {status, drawdown_pct, ...}
    - empty/None -> None
    """
    # Cas 1 : error dict -> None
    assert sgm.classify_stress_scenario(
        {"scenario": "X", "error": "unknown"}, -25, -30, {},
    ) is None

    # Cas 2 : drawdown manquant -> raise
    with pytest.raises(MissingStressDataError):
        sgm.classify_stress_scenario(
            {"scenario": "X"}, -25, -30, {},
        )

    # Cas 3 : ok normal
    out = sgm.classify_stress_scenario(
        {"scenario": "X", "total_drawdown_pct": -10.0}, -25, -30, {},
    )
    assert out is not None
    assert out["status"] == "ok"
    assert out["drawdown_pct"] == -10.0

    # Cas 4 : exact boundary warn (-25.0 inclus)
    out = sgm.classify_stress_scenario(
        {"scenario": "X", "total_drawdown_pct": -25.0}, -25, -30, {},
    )
    assert out["status"] == "warn"

    # Cas 5 : breach
    out = sgm.classify_stress_scenario(
        {"scenario": "X", "total_drawdown_pct": -32.0}, -25, -30, {},
    )
    assert out["status"] == "breach"

    # Cas 6 : empty/None
    assert sgm.classify_stress_scenario(None, -25, -30, {}) is None
    assert sgm.classify_stress_scenario({}, -25, -30, {}) is None

    # Cas 7 : override per-scenario
    out = sgm.classify_stress_scenario(
        {"scenario": "MILD", "total_drawdown_pct": -32.0},
        -25, -30,
        {"MILD": {"warn_pct": -40.0, "breach_pct": -50.0}},
    )
    assert out["status"] == "ok"  # override permissif


# ─── Test 8 : notify_on_breach=False -> pas de notify mais audit ───────────


def test_notify_on_breach_false_audits_but_silent(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag notify_on_breach=False : audit + transition tracking conserves,
    mais notify_mock pas appele."""
    _mock_config(monkeypatch, notify_on_breach=False)
    _mock_scenarios(monkeypatch, {
        "X": {
            "scenario": "X",
            "total_drawdown_pct": -40.0,
            "total_drawdown_eur": -20000.0,
            "by_position": [],
            "n_positions_affected": 1,
        },
    })
    notify_mock = _mock_notify(monkeypatch)

    stats = sgm.check_all_stress_transitions()
    assert stats["breach"] == 1
    assert stats["transitions"] == 1
    assert stats["notified"] == 0
    assert notify_mock.call_count == 0
    # mais audit row present avec transition correcte
    rows = _query(
        isolated_db,
        "SELECT status, transition, notified FROM stress_gate_alerts",
    )
    assert rows == [("breach", "enter_breach", 0)]
