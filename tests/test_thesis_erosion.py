"""Tests thesis_erosion : aiguillage anti-entetement driver-level.

Patterns canoniques :
1. INTACT : signals classifies neutral/confirms -> verdict INTACT
2. EROSION_DETECTED : signals erodent net <= -1.5 sur >=1 driver
3. INVALIDATION_HIT : >=1 trigger declenche confidence >= 0.60
4. STALE_UNUPDATED : aucun signal materiel + opened_at > 45j
5. INTACT (jeune) : aucun signal materiel + opened_at < 45j
6. CRITIQUE L15 REVIEW_DUE_DEGRADED : LLM down sur majorite signals
7. fail-safe : 1 these buggee n'arrete pas batch
8. compute_all_active_theses agrege stats
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from intelligence import thesis_erosion as te


def _schema_minimal(cx: sqlite3.Connection) -> None:
    """Clone DDL theses + signals + chat_extracted_signals + erosion_log."""
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
            entry_price REAL,
            target_price REAL,
            stop_price REAL,
            price_7d REAL, price_30d REAL, price_90d REAL,
            clv_7d REAL, clv_30d REAL, clv_90d REAL,
            status TEXT DEFAULT 'active',
            last_reviewed TEXT,
            notes TEXT,
            triggers_profit_take TEXT,
            target_partial REAL,
            target_full REAL,
            last_revisit_at TEXT,
            triggered_partial_at TEXT,
            triggered_full_at TEXT,
            triggered_stop_at TEXT,
            last_price REAL,
            last_price_at TEXT,
            pre_mortem TEXT,
            variant_perception TEXT,
            driver_epic TEXT,
            benchmark TEXT
        );
        CREATE TABLE signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            timestamp TEXT NOT NULL,
            title TEXT,
            content TEXT,
            summary TEXT,
            entities TEXT,
            impact_magnitude REAL,
            materiality_boost REAL,
            score INTEGER,
            sentiment TEXT,
            narratives TEXT,
            decay_at TEXT,
            raw_url TEXT,
            gmail_id TEXT,
            user_feedback TEXT,
            echo_cluster_id INTEGER,
            signal_type TEXT,
            reversibility TEXT,
            time_to_realization TEXT,
            materiality_breakdown TEXT,
            scoring_status TEXT
        );
        CREATE TABLE chat_extracted_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            chat_message_id INTEGER,
            kind TEXT,
            ticker TEXT,
            sector TEXT,
            theme TEXT,
            valence TEXT,
            confidence REAL,
            evidence_quote TEXT,
            note TEXT,
            model_used TEXT,
            cost_usd REAL
        );
        CREATE TABLE thesis_erosion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            computed_at TEXT NOT NULL DEFAULT (datetime('now')),
            thesis_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            verdict TEXT NOT NULL CHECK(verdict IN (
                'INTACT', 'EROSION_DETECTED', 'INVALIDATION_HIT',
                'STALE_UNUPDATED', 'REVIEW_DUE_DEGRADED'
            )),
            n_confirm INTEGER NOT NULL DEFAULT 0,
            n_erode INTEGER NOT NULL DEFAULT 0,
            n_invalidation_hit INTEGER NOT NULL DEFAULT 0,
            driver_status_json TEXT NOT NULL DEFAULT '[]',
            signals_considered_json TEXT NOT NULL DEFAULT '[]',
            degraded INTEGER NOT NULL DEFAULT 0,
            steer TEXT
        );
    """)


def _seed_thesis(cx, ticker="ASML.AS", drivers=None, invals=None, days_ago=60):
    drivers = drivers or ["Duopole EUV", "AI capex pass-through"]
    invals = invals or ["Bookings <35B 2 Q consec", "Capex hyperscaler pause"]
    opened = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    cur = cx.execute(
        "INSERT INTO theses (ticker, opened_at, conviction, key_drivers, "
        "invalidation_triggers, status) VALUES (?, ?, ?, ?, ?, 'active')",
        (
            ticker, opened, 5,
            json.dumps(drivers, ensure_ascii=False),
            json.dumps(invals, ensure_ascii=False),
        ),
    )
    return cur.lastrowid


def _seed_signal(cx, ticker, title, days_ago=10, impact=2.0, materiality_boost=1.5):
    ts = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    cur = cx.execute(
        "INSERT INTO signals (timestamp, title, summary, entities, "
        "impact_magnitude, materiality_boost) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, title, f"summary about {ticker}", f'["{ticker.upper()}"]',
         impact, materiality_boost),
    )
    return cur.lastrowid


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = tmp_path / "test.db"
    cx = sqlite3.connect(db)
    _schema_minimal(cx)
    cx.commit()
    monkeypatch.setattr("shared.storage.DB_PATH", db)
    return db, cx


# ─── Test 1 : INTACT (signals classifies neutral/confirms) ────────────────


def test_intact_when_signals_confirm_or_neutral(
    isolated_db, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _db, cx = isolated_db
    tid = _seed_thesis(cx, "ASML.AS")
    _seed_signal(cx, "ASML.AS", "Bookings strong 52B annual reported")
    _seed_signal(cx, "ASML.AS", "Market neutral macro update")
    cx.commit()

    fake_llm = MagicMock(side_effect=[
        json.dumps({
            "bears_on": "driver", "target_index": 0,
            "relation": "confirms", "confidence": 0.75,
            "rationale": "x", "evidence_quote": "y",
        }),
        json.dumps({
            "bears_on": "none", "target_index": None,
            "relation": "neutral", "confidence": 0.3,
            "rationale": "x", "evidence_quote": "",
        }),
    ])
    monkeypatch.setattr(te.llm, "call", fake_llm)

    out = te.compute_thesis_erosion(tid)
    assert out["verdict"] == "INTACT"
    assert out["n_confirm"] == 1
    assert out["n_erode"] == 0
    assert out["n_invalidation_hit"] == 0


# ─── Test 2 : EROSION_DETECTED (net <= -1.5 sur driver) ──────────────────


def test_erosion_detected_when_driver_eroded(
    isolated_db, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _db, cx = isolated_db
    tid = _seed_thesis(cx, "ASML.AS")
    # 2 signaux qui erodent driver 0 fortement
    _seed_signal(cx, "ASML.AS", "Erosion 1", impact=2.0, materiality_boost=1.5)
    _seed_signal(cx, "ASML.AS", "Erosion 2", impact=2.0, materiality_boost=1.5)
    cx.commit()

    fake_llm = MagicMock(side_effect=[
        json.dumps({
            "bears_on": "driver", "target_index": 0,
            "relation": "erodes", "confidence": 0.8,
            "rationale": "x", "evidence_quote": "y",
        }),
        json.dumps({
            "bears_on": "driver", "target_index": 0,
            "relation": "erodes", "confidence": 0.7,
            "rationale": "x", "evidence_quote": "y",
        }),
    ])
    monkeypatch.setattr(te.llm, "call", fake_llm)

    out = te.compute_thesis_erosion(tid)
    # materiality 2*1.5=3 x confidence 0.8/0.7 -> net cumulative -2.4 -2.1 = -4.5
    assert out["verdict"] == "EROSION_DETECTED"
    assert out["n_erode"] == 2
    # driver_status[0].status = broken
    assert any(ds["status"] == "broken" for ds in out["driver_status"])


# ─── Test 3 : INVALIDATION_HIT ────────────────────────────────────────────


def test_invalidation_hit_when_trigger_fires(
    isolated_db, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _db, cx = isolated_db
    tid = _seed_thesis(cx, "ASML.AS")
    _seed_signal(cx, "ASML.AS", "Bookings drop 30B Q1 + Q2 confirmed")
    cx.commit()

    fake_llm = MagicMock(return_value=json.dumps({
        "bears_on": "invalidation", "target_index": 0,
        "relation": "triggers", "confidence": 0.85,
        "rationale": "bookings drop 30B factual", "evidence_quote": "Q1 + Q2",
    }))
    monkeypatch.setattr(te.llm, "call", fake_llm)

    out = te.compute_thesis_erosion(tid)
    assert out["verdict"] == "INVALIDATION_HIT"
    assert out["n_invalidation_hit"] == 1


# ─── Test 4 : STALE_UNUPDATED (no signals + opened_at > 45j) ──────────────


def test_stale_unupdated_old_thesis_no_signals(
    isolated_db, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _db, cx = isolated_db
    tid = _seed_thesis(cx, "ASML.AS", days_ago=60)  # > 45j
    cx.commit()

    fake_llm = MagicMock()
    monkeypatch.setattr(te.llm, "call", fake_llm)

    out = te.compute_thesis_erosion(tid)
    assert out["verdict"] == "STALE_UNUPDATED"
    assert fake_llm.call_count == 0  # pas de LLM call


# ─── Test 5 : INTACT jeune (no signals + opened_at < 45j) ─────────────────


def test_intact_young_thesis_no_signals(
    isolated_db, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _db, cx = isolated_db
    tid = _seed_thesis(cx, "ASML.AS", days_ago=10)  # < 45j
    cx.commit()

    fake_llm = MagicMock()
    monkeypatch.setattr(te.llm, "call", fake_llm)

    out = te.compute_thesis_erosion(tid)
    assert out["verdict"] == "INTACT"
    assert fake_llm.call_count == 0


# ─── Test 6 : CRITIQUE L15 — LLM down majoritaire ─────────────────────────


def test_critical_L15_llm_down_majority_review_due_degraded(
    isolated_db, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L15 fail-closed strict : LLM down sur >=50% des signals -> verdict
    REVIEW_DUE_DEGRADED, jamais fabriquer un verdict de contenu sur
    evidence partielle."""
    _db, cx = isolated_db
    tid = _seed_thesis(cx, "ASML.AS")
    _seed_signal(cx, "ASML.AS", "sig1")
    _seed_signal(cx, "ASML.AS", "sig2")
    _seed_signal(cx, "ASML.AS", "sig3")
    cx.commit()

    # 2/3 LLM raise -> >= 50% -> REVIEW_DUE_DEGRADED
    fake_llm = MagicMock(side_effect=[
        te.llm.LLMUnavailableError("rate_limited"),
        te.llm.LLMUnavailableError("rate_limited"),
        json.dumps({
            "bears_on": "driver", "target_index": 0,
            "relation": "confirms", "confidence": 0.8,
            "rationale": "x", "evidence_quote": "",
        }),
    ])
    monkeypatch.setattr(te.llm, "call", fake_llm)

    out = te.compute_thesis_erosion(tid)
    assert out["verdict"] == "REVIEW_DUE_DEGRADED"
    assert out["degraded"] is True


# ─── Test 7 : compute_all_active_theses ─────────────────────────────────


def test_compute_all_active_aggregates_stats(
    isolated_db, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _db, cx = isolated_db
    _seed_thesis(cx, "ASML.AS", days_ago=60)  # STALE
    _seed_thesis(cx, "TSM", days_ago=10)      # INTACT jeune
    cx.commit()

    fake_llm = MagicMock()
    monkeypatch.setattr(te.llm, "call", fake_llm)

    stats = te.compute_all_active_theses()
    assert stats["checked"] == 2
    assert stats["stale_unupdated"] == 1
    assert stats["intact"] == 1


# ─── Test 8 : non-active thesis -> N/A ──────────────────────────────────


def test_non_active_thesis_skipped(isolated_db) -> None:
    _db, cx = isolated_db
    tid = _seed_thesis(cx, "X")
    cx.execute("UPDATE theses SET status='paused' WHERE id=?", (tid,))
    cx.commit()
    out = te.compute_thesis_erosion(tid)
    assert out["verdict"] == "N/A"


# ─── Test 9 : LLM down 1/3 (minoritaire) -> verdict CONTENU calcule ─────


def test_llm_down_minority_keeps_verdict(
    isolated_db, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM down sur <50% des signals : on calcule le verdict sur les
    classified. degraded=True surface mais verdict content valide."""
    _db, cx = isolated_db
    tid = _seed_thesis(cx, "ASML.AS")
    _seed_signal(cx, "ASML.AS", "sig1")
    _seed_signal(cx, "ASML.AS", "sig2")
    _seed_signal(cx, "ASML.AS", "sig3")
    cx.commit()

    # 1/3 raise -> < 50%
    fake_llm = MagicMock(side_effect=[
        te.llm.LLMUnavailableError("rate_limited"),
        json.dumps({
            "bears_on": "driver", "target_index": 0,
            "relation": "confirms", "confidence": 0.8,
            "rationale": "x", "evidence_quote": "",
        }),
        json.dumps({
            "bears_on": "none", "target_index": None,
            "relation": "neutral", "confidence": 0.3,
            "rationale": "x", "evidence_quote": "",
        }),
    ])
    monkeypatch.setattr(te.llm, "call", fake_llm)

    out = te.compute_thesis_erosion(tid)
    assert out["verdict"] == "INTACT"
    assert out["degraded"] is True
