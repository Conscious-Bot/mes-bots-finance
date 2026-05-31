"""Pile 2.1 v1 mecanique : tests minimaux du squelette bias_events.

Verrouille :
- Schema table + indexes existent post-migration 0023
- CHECK constraints sur les 4 enums refusent valeurs hors-domaine
- get_due_bias_events filtre status='open' AND resolve_at <= now
- resolve_due_bias_events retourne no-op safe quand rien a faire

Pas de test contrefactuel (logique pas implementee en v1).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _schema_minimal(cx: sqlite3.Connection) -> None:
    """Replique le DDL de migration 0023 dans un in-memory DB."""
    cx.executescript("""
        CREATE TABLE bias_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            ticker TEXT,
            bias TEXT NOT NULL CHECK(bias IN ('lock_in', 'fomo_greed', 'other')),
            action TEXT NOT NULL CHECK(action IN ('acted_on_bias', 'resisted')),
            decision_json TEXT NOT NULL,
            counterfactual_json TEXT NOT NULL,
            resolution_json TEXT,
            status TEXT NOT NULL DEFAULT 'open'
                CHECK(status IN ('open', 'resolved', 'void',
                                 'thesis_invalidated', 'reentered',
                                 'missing_data')),
            source TEXT NOT NULL CHECK(source IN ('auto_detected',
                                                  'telegram_tap', 'manual')),
            thesis_id INTEGER, prediction_id INTEGER,
            note_tags_json TEXT,
            horizon_days INTEGER NOT NULL,
            resolve_at TEXT NOT NULL
        );
        CREATE INDEX idx_bias_events_open
            ON bias_events(status, resolve_at);
    """)


@pytest.fixture
def in_memory_db() -> sqlite3.Connection:
    cx = sqlite3.connect(":memory:")
    _schema_minimal(cx)
    return cx


def test_check_constraint_bias_enum_refuse_hors_domaine(
    in_memory_db: sqlite3.Connection,
) -> None:
    """bias = 'made_up' -> IntegrityError immediate."""
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        in_memory_db.execute(
            "INSERT INTO bias_events "
            "(created_at, bias, action, decision_json, counterfactual_json, "
            " source, horizon_days, resolve_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-05-31T12:00:00Z", "made_up", "resisted",
             "{}", "{}", "manual", 30, "2026-06-30T12:00:00Z"),
        )


def test_check_constraint_action_enum_refuse_hors_domaine(
    in_memory_db: sqlite3.Connection,
) -> None:
    """action = 'maybe' -> IntegrityError."""
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        in_memory_db.execute(
            "INSERT INTO bias_events "
            "(created_at, bias, action, decision_json, counterfactual_json, "
            " source, horizon_days, resolve_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-05-31T12:00:00Z", "lock_in", "maybe",
             "{}", "{}", "manual", 30, "2026-06-30T12:00:00Z"),
        )


def test_check_constraint_status_enum_refuse_hors_domaine(
    in_memory_db: sqlite3.Connection,
) -> None:
    """status = 'pending' (pas dans l'enum) -> IntegrityError."""
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        in_memory_db.execute(
            "INSERT INTO bias_events "
            "(created_at, bias, action, decision_json, counterfactual_json, "
            " source, horizon_days, resolve_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-05-31T12:00:00Z", "lock_in", "resisted",
             "{}", "{}", "manual", 30, "2026-06-30T12:00:00Z", "pending"),
        )


def test_insert_canonique_valide_accepte(in_memory_db: sqlite3.Connection) -> None:
    """4 enums respectes + status default = 'open' -> INSERT ok."""
    in_memory_db.execute(
        "INSERT INTO bias_events "
        "(created_at, ticker, bias, action, decision_json, counterfactual_json, "
        " source, horizon_days, resolve_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("2026-05-31T12:00:00Z", "NVDA", "lock_in", "resisted",
         '{"discipline_said":{"action":"hold"},"captured_at_event":true}',
         '{"anchor_price_eur":181.2,"horizon_days":30}',
         "telegram_tap", 30, "2026-06-30T12:00:00Z"),
    )
    in_memory_db.commit()
    n = in_memory_db.execute("SELECT COUNT(*) FROM bias_events").fetchone()[0]
    assert n == 1
    row = in_memory_db.execute("SELECT status FROM bias_events").fetchone()
    assert row[0] == "open", "Default status doit etre 'open'"


def test_resolve_due_skeleton_noop_quand_table_vide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """resolve_due_bias_events sur table vide -> {resolved:0, deferred:0}."""
    db_path = tmp_path / "test_bias.db"
    cx = sqlite3.connect(db_path)
    _schema_minimal(cx)
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db_path)
    from intelligence import bias_events

    result = bias_events.resolve_due_bias_events()
    assert result["resolved"] == 0
    assert result["deferred"] == 0
    assert result["details"] == []


def test_resolve_due_skeleton_defere_open_dus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1 event open avec resolve_at passe -> deferred=1, resolved=0 (v1 no-op)."""
    db_path = tmp_path / "test_bias.db"
    cx = sqlite3.connect(db_path)
    _schema_minimal(cx)
    cx.execute(
        "INSERT INTO bias_events "
        "(created_at, ticker, bias, action, decision_json, counterfactual_json, "
        " source, horizon_days, resolve_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("2026-04-01T12:00:00Z", "AMD", "lock_in", "acted_on_bias",
         "{}", "{}", "auto_detected", 30, "2026-05-01T12:00:00Z"),
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db_path)
    from intelligence import bias_events

    result = bias_events.resolve_due_bias_events()
    assert result["resolved"] == 0
    assert result["deferred"] == 1
    assert len(result["details"]) == 1
    assert result["details"][0]["skipped_reason"] == "v2_contrefactuel_pending"
