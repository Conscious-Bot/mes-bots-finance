"""Pile 2.1 v2 tests : verrouille la formule contrefactuel + lifecycle status.

MIGRES v2.c.3 (01/06) -- user guide single-path : "tue la branche legacy".
Le shape counterfactual_json est passe de {shares_taken, shares_avoided}
(v2.b interne) a {initial_qty, discipline_expected_delta} (v2.c canonique).
position_events est INJECTE en argument (pas lu du JSON).

VALUE-EQUIVALENCE PRESERVEE : les expected delta_signed_eur sont identiques
a v2.b -- la formule canonique n'a pas bouge, seule la source des shares
a change (table position_events au lieu du JSON).

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
- acted_on_bias + prix UP   = delta NEGATIF (mauvais biais)
- acted_on_bias + prix DOWN = delta POSITIF (bon biais)

PIEGE FENETRE VIDE (user 01/06 guide #1) : 0 trade != erreur. Discipline=hold
+ 0 trade -> resisted (a tenu). Discipline=exit + 0 trade -> acted_on_bias
(echec a sortir). PAS de MissingDataError -- celle-la concerne UNIQUEMENT
le prix manquant.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from intelligence.bias_events import (
    MissingDataError,
    resolve_due_bias_events,
    resolve_one_bias_event,
)


def _schema_minimal(cx: sqlite3.Connection) -> None:
    """DDL minimal bias_events + position_events (v2.c.3 utilise les 2)."""
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
            thesis_id INTEGER, prediction_id INTEGER, note_tags_json TEXT,
            horizon_days INTEGER NOT NULL,
            resolve_at TEXT NOT NULL
        );
        CREATE TABLE position_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER,
            ticker TEXT NOT NULL,
            event_type TEXT NOT NULL,
            qty REAL,
            price REAL,
            pnl REAL,
            notes TEXT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX idx_position_events_ticker
            ON position_events(ticker, timestamp);
    """)


def _make_event(
    *,
    eid: int = 1,
    ticker: str = "NVDA",
    bias: str = "lock_in",
    initial_qty: float = 100.0,
    discipline_expected_delta: float = -40.0,  # discipline rightsize trim 40
    anchor_eur: float = 154.00,
    horizon_days: int = 30,
    resolve_at: str = "2026-06-30T07:00:00+00:00",
    created_at: str = "2026-05-31T07:00:00+00:00",
) -> dict:
    """Helper : event canonique shape v2.c (initial_qty + expected_delta)."""
    cf = {
        "anchor_price_eur": anchor_eur,
        "counterfactual_method": "cash_idle",
        "discipline_expected_delta": discipline_expected_delta,
        "horizon_days": horizon_days,
        "initial_qty": initial_qty,
        "path_avoided": "discipline",
        "path_taken": "user",
    }
    return {
        "id": eid, "ticker": ticker, "bias": bias,
        "decision_json": json.dumps(
            {"captured_at_event": True,
             "discipline_said": {"action": "rightsize", "ref": "r"}},
            sort_keys=True,
        ),
        "counterfactual_json": json.dumps(cf, sort_keys=True),
        "resolve_at": resolve_at, "created_at": created_at,
        "horizon_days": horizon_days,
    }


# ─── resolve_one_bias_event : formule canonique 4 directions ──────────────


def test_resisted_prix_up_donne_delta_positif(monkeypatch: pytest.MonkeyPatch) -> None:
    """lock_in : discipline rightsize (-40), user did NOTHING (0 trades, fenetre
    vide). actual=0, expected=-40, delta_vs_discipline=+40 -> resisted.
    shares_taken=100, shares_avoided=60. Prix 154->180 = delta +1040 EUR.
    Value-equivalence avec v2.b test du meme nom."""
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: 180.00)
    event = _make_event(initial_qty=100, discipline_expected_delta=-40, anchor_eur=154.00)
    resolution, action = resolve_one_bias_event(event, position_events_in_window=[])
    assert action == "resisted"
    assert resolution["delta_signed_eur"] == pytest.approx(40 * (180 - 154), abs=0.5)
    assert resolution["delta_signed_eur"] > 0


def test_resisted_prix_down_donne_delta_negatif(monkeypatch: pytest.MonkeyPatch) -> None:
    """Idem mais prix down 154->120 -> delta -1360 EUR (mauvaise resistance)."""
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: 120.00)
    event = _make_event(initial_qty=100, discipline_expected_delta=-40, anchor_eur=154.00)
    resolution, action = resolve_one_bias_event(event, position_events_in_window=[])
    assert action == "resisted"
    assert resolution["delta_signed_eur"] == pytest.approx(40 * (120 - 154), abs=0.5)
    assert resolution["delta_signed_eur"] < 0


def test_acted_on_bias_prix_up_donne_delta_negatif(monkeypatch: pytest.MonkeyPatch) -> None:
    """lock_in acted : discipline hold (0), user sell 40 (trim winner) ->
    actual=-40, delta_vs_discipline=-40 -> acted_on_bias.
    shares_taken=60, avoided=100. Prix up -> delta NEGATIF."""
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: 180.00)
    event = _make_event(initial_qty=100, discipline_expected_delta=0, anchor_eur=154.00)
    pos = [{"event_type": "sell", "qty": 40.0, "timestamp": "2026-06-15T12:00:00Z"}]
    resolution, action = resolve_one_bias_event(event, position_events_in_window=pos)
    assert action == "acted_on_bias"
    assert resolution["delta_signed_eur"] == pytest.approx(-40 * (180 - 154), abs=0.5)
    assert resolution["delta_signed_eur"] < 0


def test_acted_on_bias_prix_down_donne_delta_positif(monkeypatch: pytest.MonkeyPatch) -> None:
    """acted_on_bias trim, prix down = lucky bias (delta POSITIF)."""
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: 120.00)
    event = _make_event(initial_qty=100, discipline_expected_delta=0, anchor_eur=154.00)
    pos = [{"event_type": "sell", "qty": 40.0, "timestamp": "2026-06-15T12:00:00Z"}]
    resolution, action = resolve_one_bias_event(event, position_events_in_window=pos)
    assert action == "acted_on_bias"
    assert resolution["delta_signed_eur"] == pytest.approx(-40 * (120 - 154), abs=0.5)
    assert resolution["delta_signed_eur"] > 0


# ─── MissingDataError + ValueError ─────────────────────────────────────────


def test_raises_missing_data_si_price_indisponible(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_close_on_in_eur None -> MissingDataError. PAS confondre avec
    fenetre vide (signal valide)."""
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: None)
    event = _make_event()
    with pytest.raises(MissingDataError, match="price_at_horizon_eur"):
        resolve_one_bias_event(event, position_events_in_window=[])


def test_raises_value_error_si_counterfactual_incomplet() -> None:
    """counterfactual_json sans anchor_price_eur -> ValueError (shape v2.c)."""
    event = _make_event()
    cf = json.loads(event["counterfactual_json"])
    del cf["anchor_price_eur"]
    event["counterfactual_json"] = json.dumps(cf)
    with pytest.raises(ValueError, match="counterfactual_json incomplet"):
        resolve_one_bias_event(event, position_events_in_window=[])


def test_raises_value_error_si_initial_qty_manque() -> None:
    """v2.c shape requiert initial_qty (lit pas reconstruit -- user guide #3)."""
    event = _make_event()
    cf = json.loads(event["counterfactual_json"])
    del cf["initial_qty"]
    event["counterfactual_json"] = json.dumps(cf)
    with pytest.raises(ValueError, match="counterfactual_json incomplet"):
        resolve_one_bias_event(event, position_events_in_window=[])


def test_raises_missing_data_si_ticker_null() -> None:
    """ticker NULL (event portefeuille) non-supporte."""
    event = _make_event()
    event["ticker"] = None
    with pytest.raises(MissingDataError, match="ticker NULL"):
        resolve_one_bias_event(event, position_events_in_window=[])


# ─── User guide #1 PIEGE FENETRE VIDE : 0 trade != erreur ──────────────────


def test_fenetre_vide_hold_donne_resisted(monkeypatch: pytest.MonkeyPatch) -> None:
    """USER GUIDE #1 LINCHPIN : discipline=hold (expected=0), 0 trade dans
    window -> classify_net_delta retourne actual=0, delta_vs_discipline=0,
    |0|<=threshold -> resisted (a tenu). PAS MissingDataError."""
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: 180.00)
    event = _make_event(initial_qty=100, discipline_expected_delta=0, anchor_eur=154.00)
    resolution, action = resolve_one_bias_event(event, position_events_in_window=[])
    assert action == "resisted", "0 trade + hold doit etre resisted, pas erreur"
    # value : shares_taken=avoided=100 -> delta_signed = 0
    assert resolution["delta_signed_eur"] == 0.0
    assert resolution["n_trades_in_window"] == 0


def test_fenetre_vide_exit_donne_acted_on_bias(monkeypatch: pytest.MonkeyPatch) -> None:
    """USER GUIDE #1 SUITE : discipline=exit (expected=-100, sortir tout),
    0 trade -> echec a sortir = acted_on_bias (fomo_greed a tenu malgre exit)."""
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: 180.00)
    event = _make_event(
        bias="fomo_greed", initial_qty=100, discipline_expected_delta=-100,
        anchor_eur=154.00,
    )
    resolution, action = resolve_one_bias_event(event, position_events_in_window=[])
    assert action == "acted_on_bias", "0 trade + exit doit etre acted (echec a sortir)"
    # shares_taken=100 (held), avoided=0 (would have exited).
    # delta_signed = (100-0) * (180-154) = 2600 EUR (acted_on_bias paid off, lucky bias)
    assert resolution["delta_signed_eur"] == pytest.approx(100 * 26, abs=0.5)
    assert resolution["n_trades_in_window"] == 0


# ─── User guide #2 : filtre strict, non-trade ignore ──────────────────────


def test_ligne_non_trade_ignoree_du_delta_net(monkeypatch: pytest.MonkeyPatch) -> None:
    """USER GUIDE #2 : event_type hors {buy, sell} (dividend, split,
    adjustment, metadata) -> ignore du delta net. _qty_delta_from_event
    retourne 0.0 pour ces types."""
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: 180.00)
    event = _make_event(initial_qty=100, discipline_expected_delta=0, anchor_eur=154.00)
    pos = [
        {"event_type": "dividend", "qty": 5.0, "timestamp": "2026-06-10T12:00:00Z"},
        {"event_type": "split", "qty": 100.0, "timestamp": "2026-06-12T12:00:00Z"},
        {"event_type": "adjustment", "qty": 999.0, "timestamp": "2026-06-14T12:00:00Z"},
    ]
    resolution, action = resolve_one_bias_event(event, position_events_in_window=pos)
    # Pas de buy/sell -> delta net = 0, comme une fenetre vide
    assert action == "resisted"
    assert resolution["actual_delta_net"] == 0.0
    # n_trades_in_window compte tous les events injecte (3), mais delta=0
    assert resolution["n_trades_in_window"] == 3


# ─── User guide #4 : idempotency + lifecycle ───────────────────────────────


def test_idempotent_meme_resolution_si_appele_deux_fois(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """resolve_one_bias_event est pur (pas de side effect DB) : 2 appels
    identiques donnent meme resolution."""
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: 180.00)
    event = _make_event()
    r1, a1 = resolve_one_bias_event(event, position_events_in_window=[])
    r2, a2 = resolve_one_bias_event(event, position_events_in_window=[])
    assert a1 == a2
    assert r1["delta_signed_eur"] == r2["delta_signed_eur"]
    assert r1["classified_action"] == r2["classified_action"]


# ─── resolve_due_bias_events : transitions DB ──────────────────────────────


def test_resolve_due_passe_open_a_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1 event open du + 1 trade dans position_events -> resolved + action
    classifiee depuis le delta net (UPDATE action si necessaire)."""
    db_path = tmp_path / "test.db"
    cx = sqlite3.connect(db_path)
    _schema_minimal(cx)
    cf = json.dumps({
        "anchor_price_eur": 100.0,
        "counterfactual_method": "cash_idle",
        "discipline_expected_delta": 0.0,  # hold
        "horizon_days": 30,
        "initial_qty": 100.0,
    }, sort_keys=True)
    cx.execute(
        "INSERT INTO bias_events (created_at, ticker, bias, action, decision_json, "
        "counterfactual_json, source, horizon_days, resolve_at) "
        "VALUES ('2026-04-01T12:00:00Z', 'NVDA', 'lock_in', 'acted_on_bias', "
        "'{}', ?, 'auto_detected', 30, '2026-05-01T12:00:00Z')",
        (cf,),
    )
    # User trim 50 in window
    cx.execute(
        "INSERT INTO position_events (ticker, event_type, qty, timestamp) "
        "VALUES ('NVDA', 'sell', 50.0, '2026-04-15T12:00:00Z')",
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
    row = cx2.execute(
        "SELECT status, action, resolution_json FROM bias_events WHERE id=1"
    ).fetchone()
    cx2.close()
    assert row[0] == "resolved"
    assert row[1] == "acted_on_bias"  # classification confirme provisoire
    res = json.loads(row[2])
    # shares_taken=50, avoided=100, delta=-50 * (150-100) = -2500
    assert res["delta_signed_eur"] == pytest.approx(-50 * 50, abs=0.5)


def test_resolve_due_update_action_a_resisted_si_classify_dit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Event ouvert avec action='acted_on_bias' provisoire (open_candidate
    default). Au resolve, 0 trade + hold -> classify dit resisted ->
    UPDATE action='resisted'."""
    db_path = tmp_path / "test.db"
    cx = sqlite3.connect(db_path)
    _schema_minimal(cx)
    cf = json.dumps({
        "anchor_price_eur": 100.0,
        "counterfactual_method": "cash_idle",
        "discipline_expected_delta": 0.0,
        "horizon_days": 30,
        "initial_qty": 100.0,
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

    resolve_due_bias_events()
    cx2 = sqlite3.connect(db_path)
    action = cx2.execute("SELECT action FROM bias_events WHERE id=1").fetchone()[0]
    cx2.close()
    assert action == "resisted", "0 trade + hold -> classify -> UPDATE action"


def test_resolve_due_passe_open_a_missing_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """price indisponible -> status='missing_data'. Confondu PAS avec
    fenetre vide (user guide #1)."""
    db_path = tmp_path / "test.db"
    cx = sqlite3.connect(db_path)
    _schema_minimal(cx)
    cf = json.dumps({
        "anchor_price_eur": 100.0,
        "counterfactual_method": "cash_idle",
        "discipline_expected_delta": 0.0,
        "horizon_days": 30,
        "initial_qty": 100.0,
    }, sort_keys=True)
    cx.execute(
        "INSERT INTO bias_events (created_at, ticker, bias, action, decision_json, "
        "counterfactual_json, source, horizon_days, resolve_at) "
        "VALUES ('2026-04-01T12:00:00Z', 'DELISTED', 'lock_in', 'acted_on_bias', "
        "'{}', ?, 'auto_detected', 30, '2026-05-01T12:00:00Z')",
        (cf,),
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


def test_resolve_due_idempotent_pas_de_double_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User guide #4 : 2eme appel ne re-resout pas (status='open' filtre).
    Resoudre 2x = meme resultat naturellement (idempotent)."""
    db_path = tmp_path / "test.db"
    cx = sqlite3.connect(db_path)
    _schema_minimal(cx)
    cf = json.dumps({
        "anchor_price_eur": 100.0,
        "counterfactual_method": "cash_idle",
        "discipline_expected_delta": 0.0,
        "horizon_days": 30,
        "initial_qty": 100.0,
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

    r1 = resolve_due_bias_events()
    r2 = resolve_due_bias_events()
    assert r1["resolved"] == 1
    assert r2["resolved"] == 0


# ─── User guide #2 borne exacte : timestamp = created_at / resolve_at ─────


def test_borne_exacte_event_au_created_at_exclu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Event a timestamp == created_at EXCLU (window strict ouvert a gauche).
    L'event est deja dans initial_qty au moment de l'open."""
    db_path = tmp_path / "test.db"
    cx = sqlite3.connect(db_path)
    _schema_minimal(cx)
    cf = json.dumps({
        "anchor_price_eur": 100.0,
        "counterfactual_method": "cash_idle",
        "discipline_expected_delta": 0.0,
        "horizon_days": 30,
        "initial_qty": 100.0,
    }, sort_keys=True)
    cx.execute(
        "INSERT INTO bias_events (created_at, ticker, bias, action, decision_json, "
        "counterfactual_json, source, horizon_days, resolve_at) "
        "VALUES ('2026-04-01T12:00:00Z', 'NVDA', 'lock_in', 'acted_on_bias', "
        "'{}', ?, 'auto_detected', 30, '2026-05-01T12:00:00Z')",
        (cf,),
    )
    # Event AU created_at EXACT -> doit etre exclu
    cx.execute(
        "INSERT INTO position_events (ticker, event_type, qty, timestamp) "
        "VALUES ('NVDA', 'sell', 50.0, '2026-04-01T12:00:00Z')",
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db_path)
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: 100.0)

    result = resolve_due_bias_events()
    assert result["resolved"] == 1
    cx2 = sqlite3.connect(db_path)
    action = cx2.execute("SELECT action FROM bias_events WHERE id=1").fetchone()[0]
    cx2.close()
    # 0 trade IN WINDOW + hold -> resisted (event au created_at exclu)
    assert action == "resisted"


def test_borne_exacte_event_au_resolve_at_inclus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Event a timestamp == resolve_at INCLUS (window strict ferme a droite)."""
    db_path = tmp_path / "test.db"
    cx = sqlite3.connect(db_path)
    _schema_minimal(cx)
    cf = json.dumps({
        "anchor_price_eur": 100.0,
        "counterfactual_method": "cash_idle",
        "discipline_expected_delta": 0.0,
        "horizon_days": 30,
        "initial_qty": 100.0,
    }, sort_keys=True)
    cx.execute(
        "INSERT INTO bias_events (created_at, ticker, bias, action, decision_json, "
        "counterfactual_json, source, horizon_days, resolve_at) "
        "VALUES ('2026-04-01T12:00:00Z', 'NVDA', 'lock_in', 'acted_on_bias', "
        "'{}', ?, 'auto_detected', 30, '2026-05-01T12:00:00Z')",
        (cf,),
    )
    # Event au resolve_at EXACT -> doit etre inclus
    cx.execute(
        "INSERT INTO position_events (ticker, event_type, qty, timestamp) "
        "VALUES ('NVDA', 'sell', 50.0, '2026-05-01T12:00:00Z')",
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db_path)
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: 100.0)

    result = resolve_due_bias_events()
    assert result["resolved"] == 1
    cx2 = sqlite3.connect(db_path)
    action = cx2.execute("SELECT action FROM bias_events WHERE id=1").fetchone()[0]
    cx2.close()
    # 1 trade (sell 50) IN WINDOW + hold -> acted_on_bias
    assert action == "acted_on_bias"


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


def test_get_fx_rate_on_identity() -> None:
    """get_fx_rate_on(X, X, date) == 1.0 sans fetch."""
    from shared.prices import get_fx_rate_on

    assert get_fx_rate_on("EUR", "EUR", "2026-05-15") == 1.0


def test_counterfactual_method_preserve_dans_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR §5 : method (cash_idle v1 vs redeployment v2) preserve dans summary."""
    monkeypatch.setattr("shared.prices.get_close_on_in_eur", lambda tk, date: 180.0)
    event = _make_event()
    resolution, _ = resolve_one_bias_event(event, position_events_in_window=[])
    assert "cash_idle" in resolution["summary"]
