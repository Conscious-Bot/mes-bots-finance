"""Position-card #1 couche 1 : tests position_type + hook integrity.

Spec user red-team 07/06 :
- 3 types mutuellement exclusifs (axe EXIT POLICY uniquement)
- structural REQUIERT structural_justification (Catch 1 garde)
- Assignation structural append au thesis_integrity_log (tamper-evident)
- Tu ne peux pas re-tagger un loser en structural sans trace
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from shared import storage


def _schema_minimal(cx: sqlite3.Connection) -> None:
    """Clone DDL theses (avec position_type, tags, justif) + thesis_integrity_log."""
    cx.executescript("""
        CREATE TABLE theses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            opened_at TEXT NOT NULL,
            conviction INTEGER,
            direction TEXT DEFAULT 'long',
            horizon TEXT,
            key_drivers TEXT,
            invalidation_triggers TEXT,
            status TEXT DEFAULT 'active',
            position_type TEXT NOT NULL DEFAULT 'priced'
                CHECK(position_type IN ('structural', 'priced', 'tactical')),
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
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "test.db"
    cx = sqlite3.connect(db)
    _schema_minimal(cx)
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db)
    return db


def _seed_thesis(db: Path, ticker: str = "ASML.AS") -> int:
    cx = sqlite3.connect(db)
    cur = cx.execute(
        "INSERT INTO theses (ticker, opened_at, conviction) VALUES (?, ?, ?)",
        (ticker, "2026-03-15T00:00:00+00:00", 5),
    )
    tid = cur.lastrowid
    cx.commit()
    cx.close()
    return tid


# ─── Test 1 : default position_type = priced ──────────────────────────────


def test_default_position_type_is_priced(isolated_db: Path) -> None:
    tid = _seed_thesis(isolated_db)
    out = storage.get_position_type(tid)
    assert out["position_type"] == "priced"
    assert out["position_tags"] == []
    assert out["structural_justification"] is None


# ─── Test 2 : set priced -> no integrity append ───────────────────────────


def test_set_priced_does_not_touch_integrity_chain(isolated_db: Path) -> None:
    tid = _seed_thesis(isolated_db)
    storage.set_position_type(tid, "priced")
    # No integrity row appended
    cx = sqlite3.connect(isolated_db)
    n = cx.execute("SELECT COUNT(*) FROM thesis_integrity_log").fetchone()[0]
    cx.close()
    assert n == 0


# ─── Test 3 : set tactical -> no integrity append ─────────────────────────


def test_set_tactical_does_not_touch_integrity_chain(isolated_db: Path) -> None:
    tid = _seed_thesis(isolated_db)
    storage.set_position_type(tid, "tactical")
    cx = sqlite3.connect(isolated_db)
    n = cx.execute("SELECT COUNT(*) FROM thesis_integrity_log").fetchone()[0]
    cx.close()
    assert n == 0


# ─── Test 4 : CRITIQUE Catch 1 — structural sans justif -> raise ──────────


def test_structural_without_justification_raises(isolated_db: Path) -> None:
    """Catch 1 garde : tu ne peux pas re-tagger un loser en structural
    sans justification. Le code REFUSE l'assignation."""
    tid = _seed_thesis(isolated_db)
    with pytest.raises(storage.StructuralJustificationRequired):
        storage.set_position_type(tid, "structural")
    with pytest.raises(storage.StructuralJustificationRequired):
        storage.set_position_type(tid, "structural", structural_justification="")
    # DB inchangee
    out = storage.get_position_type(tid)
    assert out["position_type"] == "priced"


# ─── Test 5 : CRITIQUE Catch 1 — structural avec justif -> integrity append


def test_structural_with_justification_appends_to_integrity_chain(isolated_db: Path) -> None:
    """Tamper-evident : assignation structural laisse trace dans la chain."""
    tid = _seed_thesis(isolated_db, "ASML.AS")
    justif = "Monopole EUV litho verifie : seul fournisseur lithographie EUV niveau 7nm-3nm pour TSM/Samsung/Intel"
    result = storage.set_position_type(
        tid, "structural", structural_justification=justif,
        position_tags=["mega_cap"],
    )
    assert result["position_type"] == "structural"
    assert "integrity_seq" in result
    assert "integrity_hash" in result
    # Chain row inserted
    cx = sqlite3.connect(isolated_db)
    rows = cx.execute(
        "SELECT seq, thesis_id, payload_json, chain_hash FROM thesis_integrity_log"
    ).fetchall()
    cx.close()
    assert len(rows) == 1
    assert rows[0][1] == tid
    import json as _json
    payload = _json.loads(rows[0][2])
    assert payload["event"] == "position_type_assigned"
    assert payload["position_type"] == "structural"
    assert payload["structural_justification"] == justif
    assert payload["ticker"] == "ASML.AS"
    assert payload["previous_type"] == "priced"
    assert payload["tags"] == ["mega_cap"]


# ─── Test 6 : tags orthogonaux conserves ──────────────────────────────────


def test_position_tags_persisted(isolated_db: Path) -> None:
    tid = _seed_thesis(isolated_db)
    storage.set_position_type(tid, "priced", position_tags=["mega_cap", "satellite"])
    out = storage.get_position_type(tid)
    assert out["position_tags"] == ["mega_cap", "satellite"]


# ─── Test 7 : invalid type -> ValueError ──────────────────────────────────


def test_invalid_type_raises(isolated_db: Path) -> None:
    tid = _seed_thesis(isolated_db)
    with pytest.raises(ValueError):
        storage.set_position_type(tid, "chokepoint")  # 6 types old spec
    with pytest.raises(ValueError):
        storage.set_position_type(tid, "")


# ─── Test 8 : chain integrite hash differents par seq ─────────────────────


def test_multiple_structural_assignments_chain(isolated_db: Path) -> None:
    """Re-assignation structural sur theses differentes etend la chain."""
    tid1 = _seed_thesis(isolated_db, "ASML.AS")
    tid2 = _seed_thesis(isolated_db, "TSM")
    r1 = storage.set_position_type(
        tid1, "structural",
        structural_justification="Monopole EUV verified",
    )
    r2 = storage.set_position_type(
        tid2, "structural",
        structural_justification="Quasi-monopole foundry leading-edge",
    )
    assert r1["integrity_seq"] == 1
    assert r2["integrity_seq"] == 2
    # Chain hashes differents (chainage hash-of-prev)
    assert r1["integrity_hash"] != r2["integrity_hash"]
