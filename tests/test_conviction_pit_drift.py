"""Carte-decision #1 etape 1 : conviction PIT + drift hook tamper-evident.

Spec user 07/06 : conviction_at_entry = snapshot J0 immuable, conviction
= courante. Drift = changement detecte -> integrity chain append.

Tests :
- backfill : conviction_at_entry = conviction au moment migration
- update_thesis_field conviction sans change -> 0 drift, 0 chain entry
- update conviction avec change -> 1 chain entry event=conviction_drift
- conviction_at_entry JAMAIS modifie par update_thesis_field
- get_conviction_drift returns expected structure
- chain payload contient old/new/delta + asof
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from shared import storage


def _schema(cx: sqlite3.Connection) -> None:
    cx.executescript("""
        CREATE TABLE theses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            opened_at TEXT NOT NULL,
            conviction INTEGER NOT NULL,
            conviction_at_entry INTEGER,
            direction TEXT DEFAULT 'long',
            horizon TEXT,
            key_drivers TEXT,
            invalidation_triggers TEXT,
            entry_price REAL,
            target_partial REAL,
            target_full REAL,
            stop_price REAL,
            triggered_partial_at TEXT,
            triggered_full_at TEXT,
            triggered_stop_at TEXT,
            notes TEXT,
            status TEXT DEFAULT 'active',
            last_reviewed TEXT,
            position_type TEXT NOT NULL DEFAULT 'priced',
            position_tags_json TEXT NOT NULL DEFAULT '[]',
            structural_justification TEXT
        );
        CREATE TABLE thesis_integrity_log (
            seq INTEGER PRIMARY KEY,
            thesis_id INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            chain_hash TEXT NOT NULL UNIQUE,
            anchor_ref TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "t.db"
    cx = sqlite3.connect(p)
    _schema(cx)
    # Seed une these active avec conviction 4 + conviction_at_entry 4 (baseline)
    cx.execute(
        "INSERT INTO theses (ticker, opened_at, conviction, conviction_at_entry) "
        "VALUES (?, ?, ?, ?)",
        ("ASML.AS", "2026-03-15T00:00:00+00:00", 4, 4),
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", p)
    return p


def _count_chain(db: Path) -> int:
    cx = sqlite3.connect(db)
    n = cx.execute("SELECT COUNT(*) FROM thesis_integrity_log").fetchone()[0]
    cx.close()
    return n


# ─── Test 1 : pas de change -> 0 drift ──────────────────────────────────


def test_same_value_no_drift(db: Path) -> None:
    ok, _msg, _old = storage.update_thesis_field("ASML.AS", "conviction", 4)
    assert ok
    assert _count_chain(db) == 0
    drift = storage.get_conviction_drift(1)
    assert drift["drifted"] is False
    assert drift["delta"] == 0
    assert drift["n_drifts"] == 0


# ─── Test 2 : drift conviction -> chain entry ───────────────────────────


def test_conviction_change_appends_chain_entry(db: Path) -> None:
    ok, _msg, old = storage.update_thesis_field("ASML.AS", "conviction", 3)
    assert ok
    assert int(old) == 4
    assert _count_chain(db) == 1
    # Verify payload
    cx = sqlite3.connect(db)
    row = cx.execute("SELECT payload_json FROM thesis_integrity_log").fetchone()
    cx.close()
    payload = json.loads(row[0])
    assert payload["event"] == "conviction_drift"
    assert payload["old_conviction"] == 4
    assert payload["new_conviction"] == 3
    assert payload["delta"] == -1
    assert payload["ticker"] == "ASML.AS"
    assert "asof" in payload


# ─── Test 3 : conviction_at_entry JAMAIS modifie ────────────────────────


def test_conviction_at_entry_immutable(db: Path) -> None:
    """Le snapshot PIT ne doit JAMAIS etre modifie par update_thesis_field."""
    storage.update_thesis_field("ASML.AS", "conviction", 2)
    storage.update_thesis_field("ASML.AS", "conviction", 5)
    cx = sqlite3.connect(db)
    row = cx.execute(
        "SELECT conviction, conviction_at_entry FROM theses WHERE ticker='ASML.AS'"
    ).fetchone()
    cx.close()
    assert row[0] == 5     # courante mise a jour
    assert row[1] == 4     # PIT inchange


# ─── Test 4 : drifts multiples -> chain en croissance ───────────────────


def test_multiple_drifts_accumulate_in_chain(db: Path) -> None:
    storage.update_thesis_field("ASML.AS", "conviction", 3)
    storage.update_thesis_field("ASML.AS", "conviction", 5)
    storage.update_thesis_field("ASML.AS", "conviction", 4)
    assert _count_chain(db) == 3
    drift = storage.get_conviction_drift(1)
    assert drift["n_drifts"] == 3
    assert drift["current"] == 4
    assert drift["at_entry"] == 4
    assert drift["delta"] == 0
    assert drift["drifted"] is False


# ─── Test 5 : get_conviction_drift structure ────────────────────────────


def test_get_conviction_drift_full_structure(db: Path) -> None:
    storage.update_thesis_field("ASML.AS", "conviction", 2)
    drift = storage.get_conviction_drift(1)
    assert drift is not None
    assert drift["current"] == 2
    assert drift["at_entry"] == 4
    assert drift["delta"] == -2
    assert drift["drifted"] is True
    assert drift["n_drifts"] == 1
    assert drift["last_drift_at"] is not None


# ─── Test 6 : unknown thesis_id -> None ─────────────────────────────────


def test_get_conviction_drift_unknown_returns_none(db: Path) -> None:
    out = storage.get_conviction_drift(999)
    assert out is None


# ─── Test 7 : update field non-conviction n'append PAS chain ────────────


def test_non_conviction_field_does_not_append_chain(db: Path) -> None:
    storage.update_thesis_field("ASML.AS", "stop_price", 100.0)
    storage.update_thesis_field("ASML.AS", "horizon", "12m")
    assert _count_chain(db) == 0


# ─── Test 8 : chain payload tamper-evident (hash chain coherent) ────────


def test_chain_hash_chain_coherent(db: Path) -> None:
    """Verifications minimales chainage hash : seq increment, chain_hash unique."""
    storage.update_thesis_field("ASML.AS", "conviction", 3)
    storage.update_thesis_field("ASML.AS", "conviction", 5)
    cx = sqlite3.connect(db)
    rows = cx.execute(
        "SELECT seq, prev_hash, chain_hash FROM thesis_integrity_log ORDER BY seq"
    ).fetchall()
    cx.close()
    assert len(rows) == 2
    assert rows[0][0] == 1
    assert rows[1][0] == 2
    # chain_hash[1].prev_hash == chain_hash[0]
    assert rows[1][1] == rows[0][2]
    # Hashes distincts
    assert rows[0][2] != rows[1][2]


# ─── Test : révision de niveau reset le triggered_*_at (fail-silent audit 30/06) ──


def test_level_revision_clears_trigger_flag(db: Path) -> None:
    """Réviser un niveau (target/stop) doit RESET le triggered_*_at correspondant.

    Sinon le garde `not triggered_*_at` de price_monitor supprime silencieusement
    l'alerte cible/stop contre le nouveau niveau (5 thèses orphelines, audit chrono
    30/06 : triggered_full_at posé contre une ancienne cible, prix à 53-84% de la
    cible relevée). Le flag d'un AUTRE niveau ne doit pas bouger.
    """
    cx = sqlite3.connect(db)
    cx.execute(
        "UPDATE theses SET target_full=700, "
        "triggered_full_at='2026-06-09T00:00:00+00:00', "
        "stop_price=400, triggered_stop_at='2026-06-12T00:00:00+00:00' "
        "WHERE ticker='ASML.AS'"
    )
    cx.commit()
    cx.close()

    ok, _msg, old = storage.update_thesis_field("ASML.AS", "target_full", 900)
    assert ok
    assert float(old) == 700.0

    cx = sqlite3.connect(db)
    row = cx.execute(
        "SELECT target_full, triggered_full_at, triggered_stop_at "
        "FROM theses WHERE ticker='ASML.AS'"
    ).fetchone()
    cx.close()
    assert row[0] == 900
    assert row[1] is None        # flag full reset (niveau révisé)
    assert row[2] is not None    # flag stop intact (niveau non touché)


def test_level_noop_set_keeps_trigger_flag(db: Path) -> None:
    """Set no-op (même valeur) ne doit PAS reset le flag — pas de reset gratuit."""
    cx = sqlite3.connect(db)
    cx.execute(
        "UPDATE theses SET target_full=700, "
        "triggered_full_at='2026-06-09T00:00:00+00:00' WHERE ticker='ASML.AS'"
    )
    cx.commit()
    cx.close()

    storage.update_thesis_field("ASML.AS", "target_full", 700)

    cx = sqlite3.connect(db)
    row = cx.execute(
        "SELECT triggered_full_at FROM theses WHERE ticker='ASML.AS'"
    ).fetchone()
    cx.close()
    assert row[0] is not None    # flag conservé (valeur inchangée)
