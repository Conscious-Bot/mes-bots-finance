"""Valeur de la discipline (#20) — compteur bidirectionnel canonique (GLOSSARY).

Verrouille : somme signée + filtres pollution (TEST_%/VOIDED, mêmes règles que
measure_bias), valorisation des refus digue (signe inversé : baisse évitée =
positif), pending <30j, total None si rien de résolu (L15), lens biais séparée.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from intelligence import discipline_value as dv
from shared import storage


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    cx = sqlite3.connect(p)
    cx.executescript(
        """
        CREATE TABLE decisions (id INTEGER PRIMARY KEY, reasoning TEXT);
        CREATE TABLE decision_counterfactual (
            id INTEGER PRIMARY KEY, decision_id INTEGER, ticker TEXT,
            decision_type TEXT);
        CREATE TABLE counterfactual_resolution (
            id INTEGER PRIMARY KEY, decision_counterfactual_id INTEGER,
            ticker TEXT, delta_eur REAL, verdict TEXT);
        CREATE TABLE bot_events (
            id INTEGER PRIMARY KEY, timestamp TEXT, event_type TEXT, details TEXT);
        CREATE TABLE price_history (
            id INTEGER PRIMARY KEY, ticker TEXT, asof TEXT,
            price_native REAL, currency TEXT, source TEXT);
        CREATE TABLE kill_triggers (id INTEGER PRIMARY KEY, status TEXT);
        """
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr(storage, "DB_PATH", str(p))
    return p


def _seed_decision(db, dcf_id, dtype, delta, ticker="TSM", reasoning=None):
    cx = sqlite3.connect(db)
    cx.execute("INSERT INTO decisions(id, reasoning) VALUES (?, ?)", (dcf_id, reasoning))
    cx.execute(
        "INSERT INTO decision_counterfactual(id, decision_id, ticker, decision_type) VALUES (?,?,?,?)",
        (dcf_id, dcf_id, ticker, dtype),
    )
    cx.execute(
        "INSERT INTO counterfactual_resolution(decision_counterfactual_id, ticker, delta_eur, verdict) "
        "VALUES (?,?,?,?)",
        (dcf_id, ticker, delta, "decision_beneficial" if delta >= 0 else "decision_harmful"),
    )
    cx.commit()
    cx.close()


def test_decisions_signed_sum(temp_db):
    _seed_decision(temp_db, 1, "scale_in", +1000.0)
    _seed_decision(temp_db, 2, "partial_exit", -400.0)
    s = dv.discipline_value_summary()
    assert s["total_eur"] == 600.0
    assert s["n_total"] == 2
    assert s["components"]["decisions"]["by_type"]["scale_in"]["eur"] == 1000.0


def test_pollution_filtered_like_measure_bias(temp_db):
    """TEST_% tickers et decisions VOIDED exclus (mêmes règles que self_loop)."""
    _seed_decision(temp_db, 1, "scale_in", +1000.0)
    _seed_decision(temp_db, 2, "scale_in", +9999.0, ticker="TEST_FIXTURE")
    _seed_decision(temp_db, 3, "scale_in", +5555.0, reasoning="[VOIDED trade fantôme]")
    s = dv.discipline_value_summary()
    assert s["total_eur"] == 1000.0  # pollution ignorée
    assert s["n_total"] == 1


def test_empty_returns_none_not_zero(temp_db):
    """Rien de résolu → total None (pas de zéro fabriqué présenté comme mesure)."""
    s = dv.discipline_value_summary()
    assert s["total_eur"] is None
    assert s["n_total"] == 0


def _seed_refusal(db, ticker, qty, price, days_ago, px_at_h30=None):
    cx = sqlite3.connect(db)
    t0 = datetime.now(UTC) - timedelta(days=days_ago)
    cx.execute(
        "INSERT INTO bot_events(timestamp, event_type, details) VALUES (?,?,?)",
        (t0.isoformat(), "digue_buy_refused",
         json.dumps({"ticker": ticker, "qty": qty, "price": price})),
    )
    if px_at_h30 is not None:
        cx.execute(
            "INSERT INTO price_history(ticker, asof, price_native, currency, source) "
            "VALUES (?,?,?,?,?)",
            (ticker, (t0 + timedelta(days=31)).isoformat(), px_at_h30, "USD", "test"),
        )
    cx.commit()
    cx.close()


def test_refusal_valued_inverse_sign(temp_db):
    """Achat refusé à 100, prix à +30j = 80 (−20%) → la discipline a évité la
    perte → +20% × 10×100 = +200 € POSITIF."""
    _seed_refusal(temp_db, "CCJ", qty=10, price=100.0, days_ago=40, px_at_h30=80.0)
    s = dv.discipline_value_summary()
    ref = s["components"]["digue_refusals"]
    assert ref["n_events"] == 1 and ref["n_valued"] == 1
    assert ref["cumul_eur"] == pytest.approx(200.0)
    assert s["total_eur"] == pytest.approx(200.0)


def test_refusal_of_rising_stock_costs(temp_db):
    """Achat refusé, le titre monte de +10% → la discipline a coûté −10% : le
    compteur est BIDIRECTIONNEL, pas un auto-satisfecit."""
    _seed_refusal(temp_db, "TSM", qty=5, price=200.0, days_ago=40, px_at_h30=220.0)
    s = dv.discipline_value_summary()
    assert s["components"]["digue_refusals"]["cumul_eur"] == pytest.approx(-100.0)


def test_refusal_pending_before_horizon(temp_db):
    """Refus < 30j → pending, pas valorisé (pas de mesure avant l'horizon)."""
    _seed_refusal(temp_db, "CCJ", qty=10, price=100.0, days_ago=5)
    s = dv.discipline_value_summary()
    ref = s["components"]["digue_refusals"]
    assert ref["n_events"] == 1 and ref["n_valued"] == 0 and ref["pending"] == 1
    assert s["total_eur"] is None  # rien de résolu


def test_sensor_wired_in_buy_gate():
    """Source-read : le refus de gate logge bien l'intention (capteur #20)."""
    from pathlib import Path

    src = Path("bot/handlers/positions.py").read_text()
    assert "digue_buy_refused" in src
    gate_block = src.split("gate_allows_buy()")[1][:900]
    assert "log_event" in gate_block, "le capteur n'est pas dans le chemin de refus"
