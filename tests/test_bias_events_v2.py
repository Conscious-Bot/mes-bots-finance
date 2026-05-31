"""Pile 2.1 v2 tests : verrouille la formule contrefactuel + lifecycle status.

Couvre :
- shared.prices.get_fx_rate_on : FX historique a date donnee
- shared.prices.get_close_on_in_eur : conversion EUR a la MEME date
- intelligence.bias_events.resolve_one_bias_event : formule canonique
  delta_signed_eur = (shares_taken - shares_avoided) * (price_horizon_eur - anchor_eur)
- MissingDataError raised si price_at_horizon_eur None
- ValueError raised si counterfactual_json incomplet
- resolve_due_bias_events : transitions open -> resolved | missing_data | void

Formule canonique testee dans LES 4 DIRECTIONS :
- resisted + prix UP   = delta POSITIF (bonne resistance)
- resisted + prix DOWN = delta NEGATIF (mauvaise resistance)
- acted_on_bias + prix UP   = delta NEGATIF (mauvais biais : trim avant hausse)
- acted_on_bias + prix DOWN = delta POSITIF (bon biais : sauve par trim)

Aligne sur [[GLOSSARY]] v1.0 : "Coût du biais / valeur de la discipline =
compteur bidirectionnel, somme signée des deltas contrefactuels".
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from intelligence.bias_events import (
    MissingDataError,
    resolve_due_bias_events,
    resolve_one_bias_event,
)


def _schema_minimal(cx: sqlite3.Connection) -> None:
    """DDL minimal de bias_events (clone migration 0023)."""
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
    """)


def _make_event(
    *, ticker: str = "NVDA",
    bias: str = "lock_in",
    action: str = "acted_on_bias",
    shares_taken: float = 60.0,
    shares_avoided: float = 100.0,
    anchor_eur: float = 154.45,
    horizon_days: int = 30,
    resolve_at: str = "2026-06-30T07:00:00+00:00",
) -> dict:
    """Helper : construit un event canonique pour tests resolve_one_bias_event."""
    cf = {
        "anchor_price_eur": anchor_eur,
        "horizon_days": horizon_days,
        "path_avoided": "discipline",
        "path_taken": "user",
        "shares_taken": shares_taken,
        "shares_avoided": shares_avoided,
        "cash_redeployment": {"assumption": "cash_oisif"},
    }
    return {
        "id": 1, "ticker": ticker, "bias": bias, "action": action,
        "decision_json": "{}",
        "counterfactual_json": json.dumps(cf, sort_keys=True),
        "resolve_at": resolve_at,
        "horizon_days": horizon_days,
    }


# ─── resolve_one_bias_event : formule canonique 4 directions ──────────────


def test_resisted_prix_up_donne_delta_positif(monkeypatch: pytest.MonkeyPatch) -> None:
    """resisted (user a garde 100 vs discipline 60), prix monte 154 -> 180 EUR.
    delta_signed = (100-60) * (180-154) = +1040 EUR (bonne resistance)."""
    monkeypatch.setattr(
        "shared.prices.get_close_on_in_eur",
        lambda tk, date: 180.00,
    )
    event = _make_event(action="resisted", shares_taken=100, shares_avoided=60, anchor_eur=154.00)
    result = resolve_one_bias_event(event)
    assert result["delta_signed_eur"] == pytest.approx(40 * (180 - 154), abs=0.5)
    assert result["delta_signed_eur"] > 0  # bonne decision = positif


def test_resisted_prix_down_donne_delta_negatif(monkeypatch: pytest.MonkeyPatch) -> None:
    """resisted prix descend 154 -> 120. delta_signed < 0 = resistance couta."""
    monkeypatch.setattr(
        "shared.prices.get_close_on_in_eur",
        lambda tk, date: 120.00,
    )
    event = _make_event(action="resisted", shares_taken=100, shares_avoided=60, anchor_eur=154.00)
    result = resolve_one_bias_event(event)
    assert result["delta_signed_eur"] == pytest.approx(40 * (120 - 154), abs=0.5)
    assert result["delta_signed_eur"] < 0  # mauvaise resistance


def test_acted_on_bias_prix_up_donne_delta_negatif(monkeypatch: pytest.MonkeyPatch) -> None:
    """acted_on_bias = lock_in trim. shares_taken < shares_avoided.
    Prix monte = biais a coute (aurait du tenir)."""
    monkeypatch.setattr(
        "shared.prices.get_close_on_in_eur",
        lambda tk, date: 180.00,
    )
    event = _make_event(action="acted_on_bias", shares_taken=60, shares_avoided=100, anchor_eur=154.00)
    result = resolve_one_bias_event(event)
    # shares_delta = 60-100 = -40. (-40) * (180-154) = -1040. Bias couta.
    assert result["delta_signed_eur"] == pytest.approx(-40 * (180 - 154), abs=0.5)
    assert result["delta_signed_eur"] < 0


def test_acted_on_bias_prix_down_donne_delta_positif(monkeypatch: pytest.MonkeyPatch) -> None:
    """acted_on_bias trim prix descend = trim a sauve (lucky bias)."""
    monkeypatch.setattr(
        "shared.prices.get_close_on_in_eur",
        lambda tk, date: 120.00,
    )
    event = _make_event(action="acted_on_bias", shares_taken=60, shares_avoided=100, anchor_eur=154.00)
    result = resolve_one_bias_event(event)
    assert result["delta_signed_eur"] == pytest.approx(-40 * (120 - 154), abs=0.5)
    assert result["delta_signed_eur"] > 0


# ─── MissingDataError + ValueError ─────────────────────────────────────────


def test_raises_missing_data_si_price_indisponible(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_close_on_in_eur None -> MissingDataError (jamais default silencieux)."""
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: None)
    event = _make_event()
    with pytest.raises(MissingDataError, match="price_at_horizon_eur"):
        resolve_one_bias_event(event)


def test_raises_value_error_si_counterfactual_incomplet() -> None:
    """counterfactual_json sans anchor_price_eur -> ValueError."""
    event = _make_event()
    cf = json.loads(event["counterfactual_json"])
    del cf["anchor_price_eur"]
    event["counterfactual_json"] = json.dumps(cf)
    with pytest.raises(ValueError, match="counterfactual_json incomplet"):
        resolve_one_bias_event(event)


def test_raises_missing_data_si_ticker_null() -> None:
    """ticker NULL (event portefeuille) non-supporte en v2.b."""
    event = _make_event()
    event["ticker"] = None
    with pytest.raises(MissingDataError, match="ticker NULL"):
        resolve_one_bias_event(event)


# ─── resolve_due_bias_events : transitions lifecycle ───────────────────────


def test_resolve_due_passe_open_a_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1 event open du, price dispo -> status='resolved' + resolution_json."""
    db_path = tmp_path / "test.db"
    cx = sqlite3.connect(db_path)
    _schema_minimal(cx)
    cf = json.dumps({
        "anchor_price_eur": 100.0,
        "horizon_days": 30,
        "shares_taken": 50,
        "shares_avoided": 100,
    }, sort_keys=True)
    cx.execute(
        "INSERT INTO bias_events (created_at, ticker, bias, action, decision_json, "
        "counterfactual_json, source, horizon_days, resolve_at) "
        "VALUES ('2026-04-01T12:00:00Z', 'NVDA', 'lock_in', 'acted_on_bias', "
        "'{}', ?, 'auto_detected', 30, '2026-05-01T12:00:00Z')",
        (cf,),
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db_path)
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: 150.0)

    result = resolve_due_bias_events()
    assert result["resolved"] == 1
    assert result["missing"] == 0
    assert result["void"] == 0

    cx2 = sqlite3.connect(db_path)
    row = cx2.execute("SELECT status, resolution_json FROM bias_events WHERE id=1").fetchone()
    cx2.close()
    assert row[0] == "resolved"
    res = json.loads(row[1])
    assert res["delta_signed_eur"] == pytest.approx((50 - 100) * (150 - 100), abs=0.5)


def test_resolve_due_passe_open_a_missing_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """price indisponible -> status='missing_data'."""
    db_path = tmp_path / "test.db"
    cx = sqlite3.connect(db_path)
    _schema_minimal(cx)
    cx.execute(
        "INSERT INTO bias_events (created_at, ticker, bias, action, decision_json, "
        "counterfactual_json, source, horizon_days, resolve_at) "
        "VALUES ('2026-04-01T12:00:00Z', 'DELISTED', 'lock_in', 'acted_on_bias', "
        "'{}', '{\"anchor_price_eur\":100,\"shares_taken\":50,\"shares_avoided\":100,\"horizon_days\":30}', "
        "'auto_detected', 30, '2026-05-01T12:00:00Z')",
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db_path)
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: None)

    result = resolve_due_bias_events()
    assert result["missing"] == 1
    assert result["resolved"] == 0

    cx2 = sqlite3.connect(db_path)
    status = cx2.execute("SELECT status FROM bias_events WHERE id=1").fetchone()[0]
    cx2.close()
    assert status == "missing_data"


def test_resolve_due_passe_open_a_void_si_malforme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """counterfactual_json sans champs requis -> status='void'."""
    db_path = tmp_path / "test.db"
    cx = sqlite3.connect(db_path)
    _schema_minimal(cx)
    cx.execute(
        "INSERT INTO bias_events (created_at, ticker, bias, action, decision_json, "
        "counterfactual_json, source, horizon_days, resolve_at) "
        "VALUES ('2026-04-01T12:00:00Z', 'NVDA', 'lock_in', 'acted_on_bias', "
        "'{}', '{\"horizon_days\":30}', 'manual', 30, '2026-05-01T12:00:00Z')",
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db_path)

    result = resolve_due_bias_events()
    assert result["void"] == 1

    cx2 = sqlite3.connect(db_path)
    status = cx2.execute("SELECT status FROM bias_events WHERE id=1").fetchone()[0]
    cx2.close()
    assert status == "void"


# ─── get_close_on_in_eur unit test (v2.a) ──────────────────────────────────


def test_get_close_on_in_eur_eur_ticker_passe_direct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ticker EUR (e.g., .PA) -> NATIVE close direct sans FX."""
    monkeypatch.setattr("shared.prices.get_close_on", lambda tk, date: 285.50)
    from shared.prices import get_close_on_in_eur

    result = get_close_on_in_eur("HO.PA", "2026-05-15")
    assert result == 285.50


def test_get_close_on_in_eur_usd_ticker_converti_via_fx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ticker USD -> NATIVE * fx_rate_at_date."""
    monkeypatch.setattr("shared.prices.get_close_on", lambda tk, date: 200.00)
    monkeypatch.setattr("shared.prices.get_fx_rate_on", lambda f, t, date: 0.85)
    from shared.prices import get_close_on_in_eur

    result = get_close_on_in_eur("NVDA", "2026-05-15")
    assert result == pytest.approx(200 * 0.85, abs=0.01)


def test_get_close_on_in_eur_none_si_fx_indispo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si FX rate None -> None (caller leve MissingDataError, pas default)."""
    monkeypatch.setattr("shared.prices.get_close_on", lambda tk, date: 200.00)
    monkeypatch.setattr("shared.prices.get_fx_rate_on", lambda f, t, date: None)
    from shared.prices import get_close_on_in_eur

    result = get_close_on_in_eur("NVDA", "2026-05-15")
    assert result is None


def test_get_fx_rate_on_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_fx_rate_on(X, X, date) == 1.0 sans fetch."""
    from shared.prices import get_fx_rate_on

    assert get_fx_rate_on("EUR", "EUR", "2026-05-15") == 1.0
