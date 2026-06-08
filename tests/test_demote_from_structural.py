"""Q3 master : tests auto-demote_from_structural sur INVALIDATION_HIT.

Decision verrouillee master §3 + Q3 §4 :
- Le privilege structural est merite par la premise.
- Si invalidation fire -> premise cassee -> privilege revoque automatique.
- Tamper-evident : append integrity log event=auto_demote_from_structural.
- Anti-lock-in : impossible de re-tagger structural rapidement (chain hash).

Tests :
- demote_from_structural sur thesis structural -> position_type=priced + chain log
- demote_from_structural sur thesis priced -> no-op
- reason vide -> raises ValueError
- demoted_to invalid -> raises ValueError
- Hook dans compute_thesis_erosion : INVALIDATION_HIT + structural -> auto demote
- Hook : INVALIDATION_HIT + priced -> pas de demote (deja priced)
- Hook : EROSION_DETECTED + structural -> pas de demote (verdict != INVALIDATION_HIT)
- Notify Telegram envoye sur demote
- Idempotence : 2e appel demote_from_structural sur deja-priced -> noop sans erreur
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _schema(cx: sqlite3.Connection) -> None:
    cx.executescript("""
        CREATE TABLE theses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL, opened_at TEXT NOT NULL,
            conviction INTEGER, direction TEXT DEFAULT 'long',
            key_drivers TEXT, invalidation_triggers TEXT,
            status TEXT DEFAULT 'active',
            position_type TEXT NOT NULL DEFAULT 'priced'
                CHECK(position_type IN ('structural', 'priced', 'tactical')),
            position_tags_json TEXT NOT NULL DEFAULT '[]',
            structural_justification TEXT,
            last_reviewed TEXT
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
        CREATE TABLE signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER,
            timestamp TEXT NOT NULL, title TEXT, content TEXT, summary TEXT,
            entities TEXT, impact_magnitude REAL, materiality_boost REAL,
            score INTEGER, sentiment TEXT, narratives TEXT, decay_at TEXT,
            raw_url TEXT, gmail_id TEXT, user_feedback TEXT,
            echo_cluster_id INTEGER, signal_type TEXT, reversibility TEXT,
            time_to_realization TEXT, materiality_breakdown TEXT,
            scoring_status TEXT
        );
        CREATE TABLE chat_extracted_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
            chat_message_id INTEGER, kind TEXT, ticker TEXT, sector TEXT,
            theme TEXT, valence TEXT, confidence REAL,
            evidence_quote TEXT, note TEXT, model_used TEXT, cost_usd REAL
        );
        CREATE TABLE thesis_erosion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            computed_at TEXT NOT NULL DEFAULT (datetime('now')),
            thesis_id INTEGER NOT NULL, ticker TEXT NOT NULL,
            verdict TEXT NOT NULL,
            n_confirm INTEGER DEFAULT 0, n_erode INTEGER DEFAULT 0,
            n_invalidation_hit INTEGER DEFAULT 0,
            driver_status_json TEXT NOT NULL DEFAULT '[]',
            signals_considered_json TEXT NOT NULL DEFAULT '[]',
            degraded INTEGER DEFAULT 0, steer TEXT
        );
        CREATE TABLE thesis_erosion_classifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            erosion_log_id INTEGER NOT NULL, signal_id INTEGER NOT NULL,
            signal_source TEXT NOT NULL,
            bears_on TEXT, target_index INTEGER, relation TEXT,
            confidence REAL, materiality REAL, rationale TEXT, evidence_quote TEXT
        );
    """)


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    p = tmp_path / "t.db"
    cx = sqlite3.connect(p)
    _schema(cx)
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", p)
    return p


def _seed(p: Path, ticker: str = "ASML.AS",
          position_type: str = "structural",
          justif: str = "Monopole EUV verified") -> int:
    cx = sqlite3.connect(p)
    cur = cx.execute(
        "INSERT INTO theses (ticker, opened_at, conviction, key_drivers, "
        "invalidation_triggers, position_type, structural_justification) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ticker, "2026-03-15T00:00:00+00:00", 5,
         json.dumps(["Duopole EUV"]),
         json.dumps(["Bookings <35B"]),
         position_type, justif if position_type == "structural" else None),
    )
    tid = cur.lastrowid
    cx.commit()
    cx.close()
    return tid


# ─── Test 1 : demote_from_structural sur structural -> priced + chain log


def test_demote_from_structural_basic(isolated_db) -> None:
    from shared import storage
    tid = _seed(isolated_db)
    result = storage.demote_from_structural(
        tid, reason="invalidation fire test",
    )
    assert result is not None
    assert result["old_type"] == "structural"
    assert result["new_type"] == "priced"
    assert "integrity_seq" in result
    # Verify DB
    cx = sqlite3.connect(isolated_db)
    row = cx.execute("SELECT position_type FROM theses WHERE id=?", (tid,)).fetchone()
    assert row[0] == "priced"
    # Verify chain
    n = cx.execute("SELECT COUNT(*) FROM thesis_integrity_log").fetchone()[0]
    assert n == 1
    payload = cx.execute("SELECT payload_json FROM thesis_integrity_log").fetchone()[0]
    p = json.loads(payload)
    assert p["event"] == "auto_demote_from_structural"
    assert p["old_type"] == "structural"
    assert p["new_type"] == "priced"
    assert "invalidation fire" in p["reason"]
    cx.close()


# ─── Test 2 : demote sur priced -> no-op ──────────────────────────────


def test_demote_on_priced_returns_none(isolated_db) -> None:
    from shared import storage
    tid = _seed(isolated_db, position_type="priced")
    result = storage.demote_from_structural(
        tid, reason="test",
    )
    assert result is None
    # Chain unchanged
    cx = sqlite3.connect(isolated_db)
    n = cx.execute("SELECT COUNT(*) FROM thesis_integrity_log").fetchone()[0]
    cx.close()
    assert n == 0


# ─── Test 3 : reason empty -> raises (anti-rationalisation) ────────────


def test_demote_empty_reason_raises(isolated_db) -> None:
    from shared import storage
    tid = _seed(isolated_db)
    with pytest.raises(ValueError, match="reason"):
        storage.demote_from_structural(tid, reason="")
    with pytest.raises(ValueError, match="reason"):
        storage.demote_from_structural(tid, reason="   ")


# ─── Test 4 : invalid demoted_to -> raises ────────────────────────────


def test_demote_invalid_target_raises(isolated_db) -> None:
    from shared import storage
    tid = _seed(isolated_db)
    with pytest.raises(ValueError, match="demoted_to"):
        storage.demote_from_structural(tid, reason="x", demoted_to="bogus")
    with pytest.raises(ValueError, match="demoted_to"):
        storage.demote_from_structural(tid, reason="x", demoted_to="structural")


# ─── Test 5 : idempotence -- 2e appel sur deja-priced -> noop ──────────


def test_demote_idempotent_after_first(isolated_db) -> None:
    from shared import storage
    tid = _seed(isolated_db)
    r1 = storage.demote_from_structural(tid, reason="first")
    assert r1 is not None
    r2 = storage.demote_from_structural(tid, reason="second")
    assert r2 is None  # already priced
    cx = sqlite3.connect(isolated_db)
    n = cx.execute("SELECT COUNT(*) FROM thesis_integrity_log").fetchone()[0]
    cx.close()
    assert n == 1  # only 1 chain entry, not 2


# ─── Test 6 : HOOK compute_thesis_erosion -- INVALIDATION_HIT + structural


def test_hook_invalidation_hit_on_structural_demotes(
    isolated_db, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LE TEST Q3 master : INVALIDATION_HIT detecte + position_type structural
    -> auto-demote priced + integrity log + notify Telegram."""
    from intelligence import thesis_erosion as te
    tid = _seed(isolated_db, position_type="structural")
    # Seed 1 signal materiel primary
    cx = sqlite3.connect(isolated_db)
    from datetime import UTC, datetime, timedelta
    ts = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    cx.execute(
        "INSERT INTO signals (timestamp, title, summary, entities, "
        "impact_magnitude, materiality_boost) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, "fire trigger", "Q3 2026 bookings 30B reported, Q2 was 32B",
         json.dumps(["ASML.AS"]), 4.0, 2.0),
    )
    cx.commit()
    cx.close()

    notify_mock = MagicMock()
    monkeypatch.setattr("shared.notify.send_text", notify_mock)
    monkeypatch.setattr(te.llm, "call", MagicMock(return_value=json.dumps({
        "bears_on": "invalidation", "target_index": 0,
        "relation": "triggers", "confidence": 0.95,
        "rationale": "factual : bookings 30B Q3 + 32B Q2 both <35B = trigger condition met",
        "evidence_quote": "Q3 2026 bookings 30B reported, Q2 was 32B",
    })))

    out = te.compute_thesis_erosion(tid)
    assert out["verdict"] == "INVALIDATION_HIT"
    # Auto-demote performed
    assert out["demoted"] is not None
    assert out["demoted"]["old_type"] == "structural"
    assert out["demoted"]["new_type"] == "priced"
    # DB state
    cx = sqlite3.connect(isolated_db)
    row = cx.execute("SELECT position_type FROM theses WHERE id=?", (tid,)).fetchone()
    assert row[0] == "priced"
    # Chain entry
    payload = cx.execute(
        "SELECT payload_json FROM thesis_integrity_log "
        "WHERE thesis_id=? AND payload_json LIKE '%auto_demote_from_structural%'",
        (tid,),
    ).fetchone()
    assert payload is not None
    cx.close()
    # Notify Telegram appele
    assert notify_mock.call_count >= 1
    msg = notify_mock.call_args_list[-1][0][0]
    assert "AUTO-DEMOTE" in msg
    assert "ASML.AS" in msg
    assert "POSE-EN UN" in msg  # steer "pose un stop"


# ─── Test 7 : HOOK INVALIDATION_HIT + priced -> pas de demote ─────────


def test_hook_invalidation_hit_on_priced_no_demote(
    isolated_db, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from intelligence import thesis_erosion as te
    tid = _seed(isolated_db, position_type="priced", justif=None)
    cx = sqlite3.connect(isolated_db)
    from datetime import UTC, datetime, timedelta
    ts = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    cx.execute(
        "INSERT INTO signals (timestamp, title, summary, entities, "
        "impact_magnitude, materiality_boost) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, "fire", "factual evidence", json.dumps(["ASML.AS"]), 4.0, 2.0),
    )
    cx.commit()
    cx.close()
    notify_mock = MagicMock()
    monkeypatch.setattr("shared.notify.send_text", notify_mock)
    monkeypatch.setattr(te.llm, "call", MagicMock(return_value=json.dumps({
        "bears_on": "invalidation", "target_index": 0,
        "relation": "triggers", "confidence": 0.95,
        "rationale": "x", "evidence_quote": "y",
    })))

    out = te.compute_thesis_erosion(tid)
    assert out["verdict"] == "INVALIDATION_HIT"
    assert out["demoted"] is None  # deja priced, pas de demote
    # Pas de chain entry pour auto-demote
    cx = sqlite3.connect(isolated_db)
    n = cx.execute(
        "SELECT COUNT(*) FROM thesis_integrity_log "
        "WHERE payload_json LIKE '%auto_demote_from_structural%'",
    ).fetchone()[0]
    cx.close()
    assert n == 0


# ─── Test 8 : HOOK EROSION_DETECTED + structural -> pas de demote ──────


def test_hook_erosion_detected_on_structural_no_demote(
    isolated_db, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EROSION_DETECTED != INVALIDATION_HIT -- pas d'auto-demote, juste flag."""
    from intelligence import thesis_erosion as te
    tid = _seed(isolated_db, position_type="structural")
    cx = sqlite3.connect(isolated_db)
    from datetime import UTC, datetime, timedelta
    ts = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    for _ in range(3):
        cx.execute(
            "INSERT INTO signals (timestamp, title, summary, entities, "
            "impact_magnitude, materiality_boost) VALUES (?, ?, ?, ?, ?, ?)",
            (ts, "erode", "x", json.dumps(["ASML.AS"]), 3.0, 1.5),
        )
    cx.commit()
    cx.close()
    notify_mock = MagicMock()
    monkeypatch.setattr("shared.notify.send_text", notify_mock)
    # All erodes (no trigger)
    monkeypatch.setattr(te.llm, "call", MagicMock(return_value=json.dumps({
        "bears_on": "driver", "target_index": 0,
        "relation": "erodes", "confidence": 0.8,
        "rationale": "x", "evidence_quote": "y",
    })))

    out = te.compute_thesis_erosion(tid)
    assert out["verdict"] == "EROSION_DETECTED"
    assert out["demoted"] is None  # EROSION pas INVALIDATION_HIT
    # Position type unchanged
    cx = sqlite3.connect(isolated_db)
    row = cx.execute("SELECT position_type FROM theses WHERE id=?", (tid,)).fetchone()
    cx.close()
    assert row[0] == "structural"
