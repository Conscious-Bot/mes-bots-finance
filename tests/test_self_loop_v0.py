"""Boucle-de-soi V0 invariants : ancre figee + append-only + measure honnete.

#38 (01/06/2026) -- fixture `_isolated_db` autouse : chaque test cree sa
propre DB sqlite temp avec le schema decision_counterfactual +
counterfactual_resolution + triggers append-only. Plus de `database is
locked` sous load bot, plus de tickers `TEST_SL_<uniq>` qui polluent la
DB live. Tests strictement isoles.

Tests structurels couverts :
- structure d'API (record_anchor return id valide)
- triggers (INSERT bypass enum bloque)
- branches de bias_context_for_prompt (logique pure, pas DB)
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from intelligence import self_loop
from shared import storage


def _create_self_loop_schema(db_path: Path) -> None:
    """Cree decision_counterfactual + counterfactual_resolution + triggers.

    Reflete scripts/alembic/versions/0018_self_loop_v0.py. A garder en
    sync si la migration evolue. Le test test_schema_drift catch les
    derives, mais on prefere garder ce schema explicite pour decouple."""
    cx = sqlite3.connect(db_path)
    cx.executescript("""
        -- decisions : table referencee par measure_bias via LEFT JOIN sur
        -- d.id = dcf.decision_id (filter VOIDED). Schema minimal -- juste
        -- les colonnes utilisees par les queries de self_loop.
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reasoning TEXT
        );

        CREATE TABLE decision_counterfactual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            decision_type TEXT NOT NULL,
            decided_at TEXT NOT NULL DEFAULT (datetime('now')),
            counterfactual_branch TEXT NOT NULL DEFAULT 'hold',
            anchor_price_native REAL,
            anchor_price_eur REAL,
            anchor_qty_before REAL NOT NULL,
            anchor_currency TEXT,
            anchor_thesis_id INTEGER,
            anchor_conviction INTEGER,
            bias_hypothesis_json TEXT NOT NULL DEFAULT '[]',
            reasoning_at_decision TEXT
        );
        CREATE INDEX idx_dcf_ticker ON decision_counterfactual(ticker, decided_at);
        CREATE INDEX idx_dcf_decision ON decision_counterfactual(decision_id);
        CREATE INDEX idx_dcf_type ON decision_counterfactual(decision_type);

        CREATE TRIGGER dcf_no_update BEFORE UPDATE ON decision_counterfactual
        BEGIN SELECT RAISE(ABORT, 'decision_counterfactual append-only : pas d UPDATE'); END;
        CREATE TRIGGER dcf_no_delete BEFORE DELETE ON decision_counterfactual
        BEGIN SELECT RAISE(ABORT, 'decision_counterfactual append-only : pas de DELETE'); END;
        CREATE TRIGGER dcf_decision_type_valid BEFORE INSERT ON decision_counterfactual
        FOR EACH ROW
        WHEN NEW.decision_type NOT IN ('entry', 'scale_in', 'partial_exit',
                                       'full_exit', 'no_action_flag', 'override')
        BEGIN SELECT RAISE(ABORT, 'decision_type invalide pour decision_counterfactual'); END;
        CREATE TRIGGER dcf_branch_valid BEFORE INSERT ON decision_counterfactual
        FOR EACH ROW
        WHEN NEW.counterfactual_branch NOT IN ('hold', 'would_have_sold', 'rotate_to')
        BEGIN SELECT RAISE(ABORT, 'counterfactual_branch invalide (v0 = hold)'); END;

        CREATE TABLE counterfactual_resolution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_counterfactual_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            horizon_days INTEGER NOT NULL,
            resolved_at TEXT NOT NULL DEFAULT (datetime('now')),
            price_at_horizon_native REAL,
            price_at_horizon_eur REAL,
            actual_value_eur REAL NOT NULL,
            counterfactual_value_eur REAL NOT NULL,
            delta_eur REAL NOT NULL,
            delta_pct REAL NOT NULL,
            verdict TEXT NOT NULL
        );
        CREATE INDEX idx_cfr_dcf ON counterfactual_resolution(decision_counterfactual_id, horizon_days);
        CREATE INDEX idx_cfr_ticker ON counterfactual_resolution(ticker, resolved_at);
        CREATE UNIQUE INDEX uniq_cfr_dcf_horizon
            ON counterfactual_resolution(decision_counterfactual_id, horizon_days);

        CREATE TRIGGER cfr_no_update BEFORE UPDATE ON counterfactual_resolution
        BEGIN SELECT RAISE(ABORT, 'counterfactual_resolution append-only : pas d UPDATE'); END;
        CREATE TRIGGER cfr_no_delete BEFORE DELETE ON counterfactual_resolution
        BEGIN SELECT RAISE(ABORT, 'counterfactual_resolution append-only : pas de DELETE'); END;
        CREATE TRIGGER cfr_verdict_valid BEFORE INSERT ON counterfactual_resolution
        FOR EACH ROW
        WHEN NEW.verdict NOT IN ('decision_beneficial', 'decision_neutral', 'decision_harmful')
        BEGIN SELECT RAISE(ABORT, 'verdict invalide'); END;
    """)
    cx.commit()
    cx.close()


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Autouse : chaque test du module re-bootstrap une DB sqlite temp avec
    le schema self_loop. Plus de `database is locked` sous load bot,
    plus de pollution `TEST_SL_<uniq>` dans la DB live."""
    db = tmp_path / "self_loop_test.db"
    _create_self_loop_schema(db)
    monkeypatch.setattr(storage, "DB_PATH", db)
    # storage._DB_PATH est un alias dynamique via __getattr__, donc auto-suit
    # DB_PATH (cf memory storage-DB_PATH-consolidated). Pas besoin de setattr
    # separe.
    return db


def _uniq_ticker(prefix="TEST_SL"):
    """Ticker unique par test (kept pour clarte semantique meme si DB isolee)."""
    return f"{prefix}_{int(time.time() * 1000000) % 100000000}"


def test_record_anchor_basic():
    """Insert legitime fonctionne, retourne id valide."""
    tk = _uniq_ticker()
    aid = self_loop.record_anchor(
        decision_id=99999,
        ticker=tk,
        decision_type="partial_exit",
        qty_before=10.0,
        price_at_decision=100.0,
        price_at_decision_eur=100.0,
        bias_hypothesis=["vend_winners_trop_tot"],
    )
    assert aid is not None and aid > 0


def test_record_anchor_invalid_decision_type():
    """Trigger DB bloque decision_type hors enum. record_anchor catch -> None."""
    tk = _uniq_ticker()
    aid = self_loop.record_anchor(
        decision_id=99999,
        ticker=tk,
        decision_type="bogus_type",
        qty_before=10.0,
    )
    assert aid is None


def test_anchor_append_only_no_update():
    """Triggers SQL bloquent UPDATE sur decision_counterfactual."""
    tk = _uniq_ticker()
    self_loop.record_anchor(
        decision_id=99999,
        ticker=tk,
        decision_type="partial_exit",
        qty_before=10.0,
    )
    with storage.db() as cx:
        with pytest.raises(Exception, match="append-only"):
            cx.execute(
                "UPDATE decision_counterfactual SET anchor_qty_before=999 WHERE ticker=?",
                (tk,),
            )
            cx.commit()


def test_anchor_append_only_no_delete():
    """Triggers SQL bloquent DELETE sur decision_counterfactual."""
    tk = _uniq_ticker()
    self_loop.record_anchor(
        decision_id=99999,
        ticker=tk,
        decision_type="partial_exit",
        qty_before=10.0,
    )
    with storage.db() as cx:
        with pytest.raises(Exception, match="append-only"):
            cx.execute("DELETE FROM decision_counterfactual WHERE ticker=?", (tk,))
            cx.commit()


def test_resolution_unique_per_horizon():
    """UNIQUE index empeche 2 resolutions pour meme (dcf_id, horizon)."""
    tk = _uniq_ticker()
    aid = self_loop.record_anchor(
        decision_id=99999,
        ticker=tk,
        decision_type="partial_exit",
        qty_before=10.0,
        price_at_decision_eur=100.0,
    )
    with storage.db() as cx:
        cx.execute(
            "INSERT INTO counterfactual_resolution ("
            "  decision_counterfactual_id, ticker, horizon_days,"
            "  actual_value_eur, counterfactual_value_eur, delta_eur, delta_pct,"
            "  verdict) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (aid, tk, 30, 800.0, 1000.0, -200.0, -20.0, "decision_harmful"),
        )
        cx.commit()
        import sqlite3 as _sq
        with pytest.raises(_sq.IntegrityError):
            cx.execute(
                "INSERT INTO counterfactual_resolution ("
                "  decision_counterfactual_id, ticker, horizon_days,"
                "  actual_value_eur, counterfactual_value_eur, delta_eur, delta_pct,"
                "  verdict) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (aid, tk, 30, 900.0, 1000.0, -100.0, -10.0, "decision_harmful"),
            )
            cx.commit()


def test_resolution_invalid_verdict_blocked():
    """Trigger valide l'enum verdict."""
    tk = _uniq_ticker()
    aid = self_loop.record_anchor(
        decision_id=99999, ticker=tk, decision_type="partial_exit",
        qty_before=10.0, price_at_decision_eur=100.0,
    )
    with storage.db() as cx:
        with pytest.raises(Exception, match="verdict invalide"):
            cx.execute(
                "INSERT INTO counterfactual_resolution ("
                "  decision_counterfactual_id, ticker, horizon_days,"
                "  actual_value_eur, counterfactual_value_eur, delta_eur, delta_pct,"
                "  verdict) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (aid, tk, 30, 800.0, 1000.0, -200.0, -20.0, "bogus_verdict"),
            )
            cx.commit()


def test_measure_bias_returns_structured_dict():
    """measure_bias retourne un dict structure avec les cles attendues."""
    m = self_loop.measure_bias("vend_winners_trop_tot", horizon_days=30)
    for k in ("bias_name", "horizon_days", "n_decisions", "n_with_resolution",
              "statistical_significance", "verdict_distribution"):
        assert k in m, f"missing key {k}"


def test_measure_bias_unknown_returns_error():
    """measure_bias sur biais inconnu retourne {error: ...}."""
    m = self_loop.measure_bias("biais_inexistant_xyz", horizon_days=30)
    assert "error" in m


def test_bias_context_no_inject_if_not_winner():
    """bias_context_for_prompt retourne "" si pnl < 10%."""
    ctx = self_loop.bias_context_for_prompt(
        ticker="AAPL", decision_type="partial_exit",
        current_pnl_pct=5.0, held_days=60,
    )
    assert ctx == ""


def test_bias_context_no_inject_if_recent_hold():
    """bias_context_for_prompt retourne "" si held < 14j."""
    ctx = self_loop.bias_context_for_prompt(
        ticker="AAPL", decision_type="partial_exit",
        current_pnl_pct=50.0, held_days=7,
    )
    assert ctx == ""


def test_bias_context_no_inject_for_buy():
    """bias_context_for_prompt retourne "" pour decision_type != sell."""
    ctx = self_loop.bias_context_for_prompt(
        ticker="AAPL", decision_type="scale_in",
        current_pnl_pct=50.0, held_days=60,
    )
    assert ctx == ""


def test_resolve_due_anchors_no_due_returns_empty():
    """Sans ancres dues, resolve retourne un summary 0."""
    out = self_loop.resolve_due_anchors(horizon_days=30)
    for k in ("resolved", "skipped", "errors", "details"):
        assert k in out


def test_bias_context_is_string_no_crash():
    """bias_context_for_prompt sur winner sell : retourne string (peut etre ""
    si n_with_resolution < 3 ou avg >= 0). Pas de crash."""
    ctx = self_loop.bias_context_for_prompt(
        ticker="AAPL", decision_type="partial_exit",
        current_pnl_pct=50.0, held_days=60,
    )
    assert isinstance(ctx, str)
