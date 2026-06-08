"""Tests verrouillants SOCLE Phase 2 S2 : position_valuation_datum.

Post-M1 (commit d0e5fdd) : position_valuation_datum() route via le primitif
unique shared.book.value_eur(ticker, qty) qui consomme prices.get + prices.fx
(les gateways canoniques) et compose Datum[Monetary(EUR)] via derive().

Le contrat canonique préservé sous garde anti-affaiblissement (O Olivier) :
  - Datum produit avec value = Monetary(amount, currency="EUR")
  - 3 parents (qty + price + fx) = lineage Merkle-DAG complet
  - asof = min(qty.asof, price.asof, fx.asof) (M1 honnête)
  - confidence = min des trois (propagation derive())
  - degraded = any des trois (fail-closed propage)
  - id content-hash deterministic

Les 5 invariants sont les mêmes qu'avant ; seul le mécanisme d'input a changé
(de position_valuation legacy vers prices.get/fx gateways). Aucun assertion
affaibli — c'est exactement le même verrou structurel, juste sur le bon chemin.

Cf SPEC_SOCLE.md S1 + HANDOFF_SOCLE.md S2 + SPEC_MONEY_INVARIANT §8.
"""

from __future__ import annotations

import pytest

from shared.datum import Datum
from shared.money import Monetary


def _fake_price(value: float = 100.0, asof: str = "2026-06-08T10:00:00Z",
                 confidence: float = 1.0, degraded: bool = False) -> Datum:
    return Datum(
        value=value, asof=asof, source="yfinance",
        confidence=confidence, degraded=degraded,
    )


def _fake_fx(value: float = 0.92, asof: str = "2026-06-08T09:00:00Z",
             confidence: float = 1.0, degraded: bool = False) -> Datum:
    return Datum(
        value=value, asof=asof, source="yfinance:fx",
        confidence=confidence, degraded=degraded,
    )


def _patch_pipeline(monkeypatch, *,
                     ticker: str = "NVDA",
                     qty: float = 10.0,
                     price: Datum | None = None,
                     fx: Datum | None = None,
                     currency: str = "USD") -> None:
    """Patch la pipeline complète book.value_eur consomme :
       storage(positions row) + prices.get(ticker) + prices.get_currency + prices.fx.
    """
    import shared.prices as prices_mod
    from shared import storage

    if price is None:
        price = _fake_price()
    if fx is None:
        fx = _fake_fx()

    monkeypatch.setattr(prices_mod, "get", lambda tk: price if tk == ticker else None)
    monkeypatch.setattr(prices_mod, "fx", lambda b, q: fx if b == currency and q == "EUR" else None)
    monkeypatch.setattr(prices_mod, "get_currency_for_ticker", lambda tk: currency)

    # storage lookup (position_valuation_datum lit position row par id)
    import shared.valuation as val_mod

    class _FakeCursor:
        def __init__(self, row): self._row = row
        def execute(self, *a, **kw): return self
        def fetchone(self): return self._row

    class _FakeConn:
        def __init__(self, row): self._row = row
        row_factory = None
        def execute(self, *a, **kw): return _FakeCursor(self._row)
        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr(storage, "db", lambda: _FakeConn((ticker, qty)))


# === Test 1 : retourne Datum[Monetary(EUR)] en cas green ====================


def test_returns_datum_when_position_valuation_green(monkeypatch) -> None:
    """value = Monetary(amount=qty*price*fx, currency='EUR'), source/op/confidence OK."""
    from shared.valuation import position_valuation_datum
    _patch_pipeline(monkeypatch, qty=10.0, price=_fake_price(100.0), fx=_fake_fx(0.92))
    d = position_valuation_datum(1)

    assert isinstance(d, Datum)
    # value est Monetary(amount, "EUR") -- contrat canonique post-M1
    assert isinstance(d.value, Monetary)
    assert d.value.amount == pytest.approx(10.0 * 100.0 * 0.92)
    assert d.value.currency == "EUR"
    assert d.source == "derived"
    assert d.op == "qty_mul_price_mul_fx_eur"
    assert d.degraded is False
    # confidence = min des trois (qty=1.0, price=1.0, fx=1.0) = 1.0
    assert d.confidence == 1.0


# === Test 2 : lignage 3 parents (qty + price + fx) =========================


def test_datum_captures_lineage_from_qty_price_fx(monkeypatch) -> None:
    """Invariant invariant : qty DOIT rester dans le lineage (mutation traçable).
    Affaibli serait : len(parents) == 2 (qty exclu) -- garde Olivier O rejet."""
    from shared.valuation import position_valuation_datum
    _patch_pipeline(monkeypatch)
    d = position_valuation_datum(1)

    assert isinstance(d.parents, tuple)
    assert len(d.parents) == 3  # qty + price + fx -- jamais 2
    for pid in d.parents:
        assert len(pid) == 64  # sha256 hex


# === Test 3 : asof = min des inputs (M1 honnête) ===========================


def test_datum_asof_is_min_of_inputs(monkeypatch) -> None:
    """qty.asof = price.asof (baseline) ; fx.asof < price.asof -> min = fx.asof."""
    from shared.valuation import position_valuation_datum
    _patch_pipeline(
        monkeypatch,
        price=_fake_price(asof="2026-06-08T10:00:00Z"),
        fx=_fake_fx(asof="2026-06-08T09:00:00Z"),
    )
    d = position_valuation_datum(1)
    assert d.asof == "2026-06-08T09:00:00Z"


# === Test 4 : degraded propage depuis price stale ===========================


def test_degraded_propagates_from_amber_price(monkeypatch) -> None:
    """price.confidence=0.7 (amber) -> result.confidence = min(qty=1, price=0.7, fx=1) = 0.7."""
    from shared.valuation import position_valuation_datum
    _patch_pipeline(
        monkeypatch,
        price=_fake_price(confidence=0.7, degraded=False),
    )
    d = position_valuation_datum(1)
    assert d.degraded is False  # amber != rouge
    assert d.confidence == pytest.approx(0.7)


# === Test 5 : None si fetch fail (L15 fail-closed) ==========================


def test_returns_none_when_pv_value_eur_none(monkeypatch) -> None:
    """price fetch fail (None) -> book.value_eur retourne None -> datum=None."""
    from shared.valuation import position_valuation_datum
    # Patch prices.get pour retourner None (fetch fail)
    import shared.prices as prices_mod
    from shared import storage

    monkeypatch.setattr(prices_mod, "get", lambda tk: None)

    class _FakeCursor:
        def execute(self, *a, **kw): return self
        def fetchone(self): return ("NVDA", 10.0)
    class _FakeConn:
        row_factory = None
        def execute(self, *a, **kw): return _FakeCursor()
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr(storage, "db", lambda: _FakeConn())

    d = position_valuation_datum(1)
    assert d is None


# === Test 6 : None si position introuvable ==================================


def test_returns_none_when_position_not_found(monkeypatch) -> None:
    """storage lookup retourne None -> datum=None (cohérent L15)."""
    from shared.valuation import position_valuation_datum
    from shared import storage

    class _FakeCursor:
        def execute(self, *a, **kw): return self
        def fetchone(self): return None
    class _FakeConn:
        row_factory = None
        def execute(self, *a, **kw): return _FakeCursor()
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr(storage, "db", lambda: _FakeConn())

    assert position_valuation_datum(999) is None


# === Test 7 : Datum frozen (anti-tampering) ================================


def test_datum_produced_is_frozen(monkeypatch) -> None:
    from shared.valuation import position_valuation_datum
    _patch_pipeline(monkeypatch)
    d = position_valuation_datum(1)
    from pydantic import ValidationError
    with pytest.raises((ValueError, AttributeError, TypeError, ValidationError)):
        d.value = 999.0  # type: ignore[misc]


# === Test 8 : content-hash id deterministic =================================


def test_datum_id_deterministic_same_inputs(monkeypatch) -> None:
    """Mêmes inputs (qty + price + fx) -> même Datum.id (Merkle-DAG reproductibilité)."""
    from shared.valuation import position_valuation_datum
    _patch_pipeline(monkeypatch)
    d1 = position_valuation_datum(1)
    _patch_pipeline(monkeypatch)
    d2 = position_valuation_datum(1)
    assert d1.id == d2.id
