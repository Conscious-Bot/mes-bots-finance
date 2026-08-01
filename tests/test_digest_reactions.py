"""Tests section REACTIONS CATALYSTS PASSES (fix 30/07 — le digest ne rate
plus un print : les newsletters ont un cycle editorial en retard d'un jour
sur la tape, la reaction prix est desormais deterministe)."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from intelligence import digest as _d


def _seed_events(tmp_path, rows):
    db = tmp_path / "events.db"
    cx = sqlite3.connect(str(db))
    cx.execute(
        "CREATE TABLE events (id INTEGER PRIMARY KEY, event_type TEXT, ticker TEXT, "
        "date TEXT, description TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    for r in rows:
        cx.execute(
            "INSERT INTO events (event_type, ticker, date, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            r,
        )
    cx.commit()
    cx.close()
    return db


def _yesterday() -> str:
    return (datetime.now(UTC).date() - timedelta(days=1)).isoformat()


def test_reaction_computed_from_event_close_to_current(tmp_path, monkeypatch):
    """Print hier (META) : baseline 100 -> courant 91 => reaction -9.0%.
    Les events MACRO sont exclus (pas de 'reaction' d'un FOMC)."""
    db = _seed_events(tmp_path, [
        ("earnings", "META", _yesterday(), "META earnings", "2026-07-28"),
        ("fomc", "MACRO", _yesterday(), "FOMC decision", "2026-07-28"),
    ])
    from shared import storage
    monkeypatch.setattr(storage, "_DB_PATH", str(db))
    with patch("shared.prices.get_price_on_date", return_value=(_yesterday(), 100.0)), \
         patch("shared.prices.get_current_price", return_value=91.0):
        out = _d._past_catalysts_reactions()
    assert "META — META earnings -> reaction -9.0%" in out
    assert "FOMC" not in out  # macro exclu
    assert "REACTIONS CATALYSTS PASSES" in out


def test_reaction_fail_closed_on_missing_price(tmp_path, monkeypatch):
    """Prix indisponible -> 'reaction — (prix indisponible)', jamais un
    chiffre fabrique (L15)."""
    db = _seed_events(tmp_path, [
        ("earnings", "SMSN", _yesterday(), "Samsung earnings", "2026-07-28"),
    ])
    from shared import storage
    monkeypatch.setattr(storage, "_DB_PATH", str(db))
    with patch("shared.prices.get_price_on_date", return_value=(None, None)), \
         patch("shared.prices.get_current_price", return_value=None):
        out = _d._past_catalysts_reactions()
    assert "reaction — (prix indisponible)" in out


def test_empty_window_renders_nothing(tmp_path, monkeypatch):
    """Aucun event ticker dans la fenetre -> section absente (rien de rate,
    pas de section fantome)."""
    db = _seed_events(tmp_path, [])
    from shared import storage
    monkeypatch.setattr(storage, "_DB_PATH", str(db))
    assert _d._past_catalysts_reactions() == ""


def test_db_failure_renders_incident_not_silence(tmp_path, monkeypatch):
    """DB inaccessible -> section INCIDENT visible, jamais un silence propre
    (never-fail-silent, doctrine Heimdall)."""
    from shared import storage
    monkeypatch.setattr(storage, "_DB_PATH", str(tmp_path / "inexistante" / "x.db"))
    out = _d._past_catalysts_reactions()
    assert "module en echec" in out
