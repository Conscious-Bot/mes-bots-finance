"""Tests verrouillants SOCLE Phase 2 S2 : position_valuation_datum.

position_valuation_datum() compose value_eur via derive() en wrappant qty,
price_native, fx_rate en leaf Datums. Le Datum produit capture le LIGNAGE
(parents) qui amorce le graphe vivant (post-socle).

Cf SPEC_SOCLE.md S1 + HANDOFF_SOCLE.md S2.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from shared import valuation
from shared.datum import Datum
from shared.valuation import PositionValuation, position_valuation_datum


def _fake_pv(
    *,
    qty: float = 10.0,
    price_native: float = 100.0,
    price_asof: str = "2026-06-08T10:00:00Z",
    price_source: str = "yfinance",
    price_severity: str = "green",
    fx_rate: float = 0.92,
    fx_asof: str = "2026-06-08T09:00:00Z",
    fx_source: str = "yfinance:fx",
    fx_severity: str = "green",
    value_eur: float | None = None,
    overall_severity: str = "green",
) -> PositionValuation:
    if value_eur is None:
        value_eur = qty * price_native * fx_rate
    return PositionValuation(
        position_id=1, ticker="NVDA", qty=qty,
        price_native=price_native, price_asof=price_asof,
        price_source=price_source, price_severity=price_severity,
        fx_rate=fx_rate, fx_from="USD", fx_to="EUR",
        fx_asof=fx_asof, fx_source=fx_source, fx_severity=fx_severity,
        value_eur=value_eur, value_eur_fail_reason=None,
        effective_asof=fx_asof, overall_severity=overall_severity,
    )


# === Test 1 : retourne Datum en cas green ===


def test_returns_datum_when_position_valuation_green(monkeypatch) -> None:
    pv = _fake_pv()
    monkeypatch.setattr(valuation, "position_valuation", lambda pid: pv)
    d = position_valuation_datum(1)
    assert isinstance(d, Datum)
    assert d.value == pytest.approx(10.0 * 100.0 * 0.92)
    assert d.source == "derived"
    assert d.op == "qty_mul_price_mul_fx"
    assert d.degraded is False
    # confidence = min des trois inputs (qty=1.0, price=1.0 green, fx=1.0 green) = 1.0
    assert d.confidence == 1.0


# === Test 2 : lignage capture (parents = ids des trois leafs) ===


def test_datum_captures_lineage_from_qty_price_fx(monkeypatch) -> None:
    pv = _fake_pv()
    monkeypatch.setattr(valuation, "position_valuation", lambda pid: pv)
    d = position_valuation_datum(1)
    # parents tuple de 3 ids sha256
    assert isinstance(d.parents, tuple)
    assert len(d.parents) == 3
    for pid in d.parents:
        assert len(pid) == 64  # sha256 hex


# === Test 3 : asof = min des inputs (M1 honnete) ===


def test_datum_asof_is_min_of_inputs(monkeypatch) -> None:
    """price_asof=10:00, fx_asof=09:00, qty.asof=price_asof=10:00 (baseline).
    min des trois -> fx_asof (09:00).
    """
    pv = _fake_pv(price_asof="2026-06-08T10:00:00Z", fx_asof="2026-06-08T09:00:00Z")
    monkeypatch.setattr(valuation, "position_valuation", lambda pid: pv)
    d = position_valuation_datum(1)
    assert d.asof == "2026-06-08T09:00:00Z"


# === Test 4 : degraded propage depuis price stale ===


def test_degraded_propagates_from_amber_price(monkeypatch) -> None:
    """price_severity=amber -> confidence < 1.0 mais degraded=False.
    Le confidence du Datum produit = min(qty.conf=1, price.conf=0.7, fx.conf=1) = 0.7.
    """
    pv = _fake_pv(price_severity="amber", overall_severity="amber")
    monkeypatch.setattr(valuation, "position_valuation", lambda pid: pv)
    d = position_valuation_datum(1)
    assert d.degraded is False  # amber != rouge
    assert d.confidence == pytest.approx(0.7)


# === Test 5 : None si pv.value_eur=None (L15 fail-closed) ===


def test_returns_none_when_pv_value_eur_none(monkeypatch) -> None:
    """severity=rouge -> pv.value_eur=None -> datum=None (cohesion legacy)."""
    pv = replace(
        _fake_pv(price_severity="rouge", overall_severity="rouge"),
        value_eur=None,
        value_eur_fail_reason="L15 stale",
    )
    monkeypatch.setattr(valuation, "position_valuation", lambda pid: pv)
    d = position_valuation_datum(1)
    assert d is None


# === Test 6 : None si position introuvable ===


def test_returns_none_when_position_not_found(monkeypatch) -> None:
    monkeypatch.setattr(valuation, "position_valuation", lambda pid: None)
    assert position_valuation_datum(999) is None


# === Test 7 : Datum frozen (anti-tampering) ===


def test_datum_produced_is_frozen(monkeypatch) -> None:
    pv = _fake_pv()
    monkeypatch.setattr(valuation, "position_valuation", lambda pid: pv)
    d = position_valuation_datum(1)
    from pydantic import ValidationError
    with pytest.raises((ValueError, AttributeError, TypeError, ValidationError)):
        d.value = 999.0  # type: ignore[misc]


# === Test 8 : content-hash id deterministe ===


def test_datum_id_deterministic_same_inputs(monkeypatch) -> None:
    """Meme PositionValuation -> meme Datum.id (Merkle-DAG reproductibilite)."""
    pv = _fake_pv()
    monkeypatch.setattr(valuation, "position_valuation", lambda pid: pv)
    d1 = position_valuation_datum(1)
    d2 = position_valuation_datum(1)
    assert d1.id == d2.id
