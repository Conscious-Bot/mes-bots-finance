"""Boucle-de-soi V0 invariants : ancre figee + append-only + measure honnete.

NOTE : les tables sont APPEND-ONLY by design (triggers SQL bloquent UPDATE/DELETE).
Les tests inserent dans la live DB et NE CLEANUP PAS (impossible). On utilise
des tickers TEST_SL_<uniq> pour ne pas confondre les rows test avec les
vraies decisions user.

Tests structurels qui n'ont pas besoin d'isolement DB :
- structure d'API (record_anchor return id valide)
- triggers (INSERT bypass enum bloque)
- branches de bias_context_for_prompt (logique pure, pas DB)
"""

from __future__ import annotations

import time

import pytest

from intelligence import self_loop
from shared import storage


def _uniq_ticker(prefix="TEST_SL"):
    """Ticker unique par test pour eviter collisions append-only."""
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
