"""Tests digues de concentration ADR 015 (intelligence/digue_monitor.py).

Classifier pur = CI-safe (déterministe). Transitions journalisées = DB temp isolée.
"""

import sqlite3
from unittest import mock

import pytest

from intelligence import digue_monitor as dm

# ---------- classifier pur (source de vérité) ----------

@pytest.mark.parametrize(
    "dd,expected",
    [
        (0.0, "normal"),
        (-9.31, "normal"),
        (-14.99, "normal"),
        (-15.0, "gel_15"),
        (-24.99, "gel_15"),
        (-25.0, "gel_25"),
        (-34.99, "gel_25"),
        (-35.0, "prorata_35"),
        (-60.0, "prorata_35"),
    ],
)
def test_classify_digue_thresholds(dd, expected):
    assert dm.classify_digue(dd) == expected


def test_gel_states_all_freeze_prorata_only_at_35():
    """Un seul gel gradué : tout gel_* gèle ; prorata armé seulement à -35%."""
    assert dm.is_frozen("normal") is False
    assert dm.is_frozen("gel_15") is True
    assert dm.is_frozen("gel_25") is True
    assert dm.is_frozen("prorata_35") is True
    assert dm.is_prorata_armed("gel_15") is False
    assert dm.is_prorata_armed("gel_25") is False
    assert dm.is_prorata_armed("prorata_35") is True


def test_transition_direction():
    assert dm._transition("normal", "gel_15") == "escalation"
    assert dm._transition("gel_15", "prorata_35") == "escalation"
    assert dm._transition("prorata_35", "gel_15") == "recovery"
    assert dm._transition("gel_15", "normal") == "recovery"
    assert dm._transition("gel_25", "gel_25") == "no_change"


# ---------- state + transition avec DB temporaire isolée ----------

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """DB SQLite temp avec portfolio_snapshots + digue_alerts."""
    p = tmp_path / "t.db"
    c = sqlite3.connect(p)
    c.executescript(
        """
        CREATE TABLE portfolio_snapshots (
            snapshot_date TEXT, total_value_eur REAL, hwm_value_eur REAL, drawdown_pct REAL
        );
        CREATE TABLE digue_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            drawdown_pct REAL NOT NULL, hwm_value_eur REAL, current_value_eur REAL,
            snapshot_date TEXT,
            status TEXT NOT NULL CHECK(status IN ('normal','gel_15','gel_25','prorata_35')),
            notified INTEGER NOT NULL DEFAULT 0, transition TEXT
        );
        """
    )
    c.commit()
    c.close()
    from shared import storage

    monkeypatch.setattr(storage, "DB_PATH", str(p))
    return p


def _set_snapshot(db_path, date, value, hwm, dd):
    c = sqlite3.connect(db_path)
    c.execute(
        "INSERT INTO portfolio_snapshots VALUES (?,?,?,?)", (date, value, hwm, dd)
    )
    c.commit()
    c.close()


def test_current_state_normal_when_shallow(temp_db):
    _set_snapshot(temp_db, "2026-07-02", 54646, 60258, -9.31)
    st = dm.current_digue_state()
    assert st["available"] is True
    assert st["status"] == "normal"
    assert st["frozen"] is False


def test_current_state_frozen_at_minus_20(temp_db):
    _set_snapshot(temp_db, "2026-07-10", 48000, 60000, -20.0)
    st = dm.current_digue_state()
    assert st["status"] == "gel_15"
    assert st["frozen"] is True


def test_fail_open_when_no_snapshot(temp_db):
    """Aucun snapshot => available=False, frozen=False (ne fabrique PAS un gel)."""
    st = dm.current_digue_state()
    assert st["available"] is False
    assert st["frozen"] is False
    assert st["drawdown_pct"] is None


def test_check_transition_journals_and_notifies_on_escalation(temp_db):
    _set_snapshot(temp_db, "2026-07-10", 48000, 60000, -20.0)
    with mock.patch("shared.notify.send_text") as sent:
        out = dm.check_digue_transition()
    assert out["status"] == "gel_15"
    assert out["transition"] == "escalation"  # normal (default) -> gel_15
    assert out["notified"] is True
    sent.assert_called_once()
    # une row journalisée
    from shared import storage

    row = storage.get_latest_digue_alert()
    assert row["status"] == "gel_15"
    assert row["transition"] == "escalation"


def test_check_transition_no_change_second_cycle_no_notify(temp_db):
    _set_snapshot(temp_db, "2026-07-10", 48000, 60000, -20.0)
    with mock.patch("shared.notify.send_text"):
        dm.check_digue_transition()  # 1er : escalation
    with mock.patch("shared.notify.send_text") as sent2:
        out = dm.check_digue_transition()  # 2e : même état
    assert out["transition"] == "no_change"
    assert out["notified"] is False
    sent2.assert_not_called()


def test_check_transition_skips_when_signal_unavailable(temp_db):
    """Pas de snapshot => skip propre, 0 row, 0 notify (fail-open, pas de fabrication)."""
    with mock.patch("shared.notify.send_text") as sent:
        out = dm.check_digue_transition()
    assert out["status"] is None
    sent.assert_not_called()
    from shared import storage

    assert storage.get_latest_digue_alert() is None
