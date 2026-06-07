"""Carte-decision #1 etape 2 : tests assemble_card_inputs.

Spec :
- Lit toutes les sources sans rien inventer
- Retourne None UNIQUEMENT si these inexistante
- Champs None si source absente (pas raise)
- Frozen dataclass
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from intelligence.card_inputs import CardInputs, assemble_card_inputs


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
            entry_price REAL, target_partial REAL, target_full REAL, stop_price REAL,
            notes TEXT,
            status TEXT DEFAULT 'active',
            last_reviewed TEXT,
            position_type TEXT NOT NULL DEFAULT 'priced',
            position_tags_json TEXT NOT NULL DEFAULT '[]',
            structural_justification TEXT,
            triggers_profit_take TEXT,
            price_7d REAL, price_30d REAL, price_90d REAL,
            clv_7d REAL, clv_30d REAL, clv_90d REAL,
            last_revisit_at TEXT, triggered_partial_at TEXT,
            triggered_full_at TEXT, triggered_stop_at TEXT,
            last_price REAL, last_price_at TEXT,
            pre_mortem TEXT, variant_perception TEXT,
            driver_epic TEXT, benchmark TEXT
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
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL, qty REAL, avg_cost REAL,
            status TEXT DEFAULT 'open',
            last_price_native REAL, last_price_currency TEXT,
            price_asof TEXT, fx_rate_to_eur REAL, fx_asof TEXT
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
            confidence REAL, materiality REAL,
            rationale TEXT, evidence_quote TEXT
        );
        CREATE TABLE kill_criteria_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thesis_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            status TEXT NOT NULL,
            dominant_reason TEXT,
            evidence_quote TEXT,
            confidence REAL,
            notified INTEGER DEFAULT 0,
            transition TEXT,
            bias_event_id INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE over_cap_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL, status TEXT NOT NULL,
            weight_pct REAL NOT NULL, cap_pct REAL NOT NULL,
            conviction INTEGER, notified INTEGER DEFAULT 0,
            transition TEXT, bias_event_id INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE bias_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            ticker TEXT, bias TEXT, action TEXT,
            decision_json TEXT, counterfactual_json TEXT,
            resolution_json TEXT, status TEXT DEFAULT 'open',
            source TEXT, thesis_id INTEGER,
            prediction_id INTEGER, note_tags_json TEXT,
            horizon_days INTEGER, resolve_at TEXT
        );
        CREATE TABLE bot_copilot_interventions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL, decision_type TEXT NOT NULL,
            brief TEXT, pressure_score INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)


def _seed_minimal(cx: sqlite3.Connection, ticker: str = "ASML.AS") -> int:
    cur = cx.execute(
        "INSERT INTO theses (ticker, opened_at, conviction, conviction_at_entry, "
        "entry_price, target_full, stop_price, position_type, last_reviewed, "
        "key_drivers, invalidation_triggers) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ticker, "2026-04-15T00:00:00+00:00", 5, 5,
         1309.0, 1806.0, None, "structural",
         (datetime.now(UTC) - timedelta(days=5)).isoformat(),
         json.dumps(["Duopoly EUV"]),
         json.dumps(["Bookings <35B"])),
    )
    tid = cur.lastrowid
    # Add a position
    cx.execute(
        "INSERT INTO positions (ticker, qty, avg_cost, last_price_native, "
        "last_price_currency, price_asof) VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, 4.0, 1150.0, 1462.20, "EUR",
         (datetime.now(UTC) - timedelta(minutes=10)).isoformat()),
    )
    cx.commit()
    return tid


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    p = tmp_path / "t.db"
    cx = sqlite3.connect(p)
    _schema(cx)
    monkeypatch.setattr("shared.storage.DB_PATH", p)
    return p, cx


# ─── Test 1 : unknown thesis -> None ────────────────────────────────────


def test_unknown_thesis_returns_none(db) -> None:
    p, cx = db
    cx.close()
    assert assemble_card_inputs(999) is None


# ─── Test 2 : these minimal -> CardInputs avec defaults ────────────────


def test_minimal_thesis_returns_card_inputs(db, monkeypatch) -> None:
    p, cx = db
    tid = _seed_minimal(cx)
    cx.close()
    # Stub risk_watch loader (pour ballast_membership)
    monkeypatch.setattr("shared.risk_watch.load_risk_watch", lambda: None)

    inputs = assemble_card_inputs(tid)
    assert isinstance(inputs, CardInputs)
    assert inputs.thesis_id == tid
    assert inputs.ticker == "ASML.AS"
    assert inputs.position_type == "structural"
    assert inputs.conviction_current == 5
    assert inputs.conviction_at_entry == 5
    assert inputs.conviction_drift_delta == 0
    # Pas d'erosion compute -> verdict None
    assert inputs.erosion_verdict is None
    # Pas de kill alert -> None
    assert inputs.kill_status is None
    # Pas de bias_events open -> liste vide
    assert inputs.bias_events_open == []
    # Default ballast = False
    assert inputs.ballast_membership is False
    # Default ruin budget 1.5
    assert inputs.ruin_budget_per_name_pct == 1.5
    # Default add_steer = False (anti-FOMO)
    assert inputs.allow_add_steer is False


# ─── Test 3 : conviction drift propage ─────────────────────────────────


def test_conviction_drift_propagates(db, monkeypatch) -> None:
    p, cx = db
    tid = _seed_minimal(cx)
    # Drift conviction 5 -> 3 via storage helper
    cx.close()
    monkeypatch.setattr("shared.risk_watch.load_risk_watch", lambda: None)
    from shared import storage
    storage.update_thesis_field("ASML.AS", "conviction", 3)
    inputs = assemble_card_inputs(tid)
    assert inputs.conviction_current == 3
    assert inputs.conviction_at_entry == 5
    assert inputs.conviction_drift_delta == -2
    assert inputs.conviction_n_drifts == 1


# ─── Test 4 : erosion verdict surface si compute ───────────────────────


def test_erosion_verdict_surfaces(db, monkeypatch) -> None:
    p, cx = db
    tid = _seed_minimal(cx)
    # Seed un verdict erosion + 1 classification
    driver_status = [{"driver": "Duopoly EUV", "net": 1.5, "status": "intact"}]
    cur = cx.execute(
        "INSERT INTO thesis_erosion_log (thesis_id, ticker, verdict, n_confirm, "
        "driver_status_json) VALUES (?, ?, ?, ?, ?)",
        (tid, "ASML.AS", "INTACT", 2, json.dumps(driver_status)),
    )
    eroid = cur.lastrowid
    cx.execute(
        "INSERT INTO thesis_erosion_classifications (erosion_log_id, signal_id, "
        "signal_source, bears_on, target_index, relation, confidence, materiality, "
        "rationale, evidence_quote) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (eroid, 1, "signals", "driver", 0, "confirms", 0.85, 3.0, "ok", "Q3 €52B"),
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.risk_watch.load_risk_watch", lambda: None)

    inputs = assemble_card_inputs(tid)
    assert inputs.erosion_verdict == "INTACT"
    assert inputs.erosion_n_confirm == 2
    assert len(inputs.erosion_classifications) == 1
    assert inputs.erosion_classifications[0]["relation"] == "confirms"
    assert inputs.erosion_driver_status[0]["status"] == "intact"


# ─── Test 5 : kill_alert + over_cap surfaces ───────────────────────────


def test_discipline_flags_surface(db, monkeypatch) -> None:
    p, cx = db
    tid = _seed_minimal(cx)
    cx.execute(
        "INSERT INTO kill_criteria_alerts (thesis_id, ticker, status, confidence) "
        "VALUES (?, ?, ?, ?)",
        (tid, "ASML.AS", "at_risk", 0.7),
    )
    cx.execute(
        "INSERT INTO over_cap_alerts (ticker, status, weight_pct, cap_pct) "
        "VALUES (?, ?, ?, ?)",
        ("ASML.AS", "over", 8.5, 6.0),
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.risk_watch.load_risk_watch", lambda: None)

    inputs = assemble_card_inputs(tid)
    assert inputs.kill_status == "at_risk"
    assert inputs.over_cap_status == "over"
    assert inputs.over_cap_pct == 8.5


# ─── Test 6 : bias_events open surface ─────────────────────────────────


def test_bias_events_open_surface(db, monkeypatch) -> None:
    p, cx = db
    tid = _seed_minimal(cx)
    cx.execute(
        "INSERT INTO bias_events (created_at, ticker, bias, action, decision_json, "
        "counterfactual_json, horizon_days, resolve_at, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')",
        ("2026-06-05T10:00:00+00:00", "ASML.AS", "lock_in", "resisted",
         "{}", "{}", 30, "2026-07-05T10:00:00+00:00"),
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.risk_watch.load_risk_watch", lambda: None)

    inputs = assemble_card_inputs(tid)
    assert len(inputs.bias_events_open) == 1
    assert inputs.bias_events_open[0]["bias"] == "lock_in"


# ─── Test 7 : counter_argument surface ─────────────────────────────────


def test_counter_argument_surface(db, monkeypatch) -> None:
    p, cx = db
    tid = _seed_minimal(cx)
    cx.execute(
        "INSERT INTO bot_copilot_interventions (ticker, decision_type, brief, "
        "pressure_score) VALUES (?, ?, ?, ?)",
        ("ASML.AS", "trade_intent", "Concurrent EUV emerge plus tot que prevu", 7),
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.risk_watch.load_risk_watch", lambda: None)

    inputs = assemble_card_inputs(tid)
    assert inputs.counter_argument_brief == "Concurrent EUV emerge plus tot que prevu"
    assert inputs.counter_argument_pressure_score == 7


# ─── Test 8 : ballast membership via risk_watch ────────────────────────


def test_ballast_membership_via_risk_watch(db, monkeypatch) -> None:
    p, cx = db
    tid = _seed_minimal(cx, "CCJ")  # CCJ est dans ballast typique
    cx.close()
    # Stub risk_watch avec CCJ in ballast_strict_tickers
    monkeypatch.setattr(
        "shared.risk_watch.load_risk_watch",
        lambda: {
            "risks": [{
                "ballast_strict_tickers": ["MP", "SAF.PA", "HO.PA", "CCJ"],
            }],
        },
    )
    inputs = assemble_card_inputs(tid)
    assert inputs.ballast_membership is True


# ─── Test 9 : non-ballast ticker ───────────────────────────────────────


def test_non_ballast_ticker(db, monkeypatch) -> None:
    p, cx = db
    tid = _seed_minimal(cx, "ASML.AS")
    cx.close()
    monkeypatch.setattr(
        "shared.risk_watch.load_risk_watch",
        lambda: {"risks": [{"ballast_strict_tickers": ["MP"]}]},
    )
    inputs = assemble_card_inputs(tid)
    assert inputs.ballast_membership is False


# ─── Test 10 : CardInputs est frozen ───────────────────────────────────


def test_card_inputs_frozen(db, monkeypatch) -> None:
    p, cx = db
    tid = _seed_minimal(cx)
    cx.close()
    monkeypatch.setattr("shared.risk_watch.load_risk_watch", lambda: None)
    inputs = assemble_card_inputs(tid)
    from dataclasses import FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        inputs.ticker = "HACKED"  # type: ignore[misc]
