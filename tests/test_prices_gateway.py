"""Tests verrouillants SOCLE Phase 1b : prices.get() / fx() retournent Datum.

Walking-skeleton : on patche `get_current_price` / `get_fx_rate` au lieu de
hitter yfinance (tests deterministes + offline). Le path complet (fetch -> wrap
Datum) est valide ; les vrais appels reseau sont valides par S0 manuel
(commit 420f95f) et par integration.

Cf SPEC_SOCLE.md S3 + HANDOFF_SOCLE.md S1.
"""

from __future__ import annotations

import pytest

from shared import prices
from shared.datum import Datum, derive

# === Test 1 : get() retourne Datum, pas float nu (M1 invariant) ===


def test_get_returns_datum_when_fetch_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(prices, "get_current_price", lambda t: 123.45)
    d = prices.get("NVDA")
    assert isinstance(d, Datum)
    assert d.value == 123.45
    assert d.source == "yfinance"
    assert d.asof  # non-empty ISO string
    assert d.confidence == 1.0  # just fetched
    assert d.degraded is False
    assert d.parents == ()  # leaf gateway output


def test_get_returns_none_when_fetch_fails(monkeypatch) -> None:
    monkeypatch.setattr(prices, "get_current_price", lambda t: None)
    assert prices.get("INVALID") is None


# === Test 2 : fx() retourne Datum, pas float nu ===


def test_fx_returns_datum_when_fetch_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(prices, "get_fx_rate", lambda b, q: 0.92)
    # Cure 16/06 : prices.fx() asof-honnete inspecte _FX_LIVE_LAST_SUCCESS pour
    # distinguer live vs hardcoded fallback. Pour ce test "fetch succeeds", simule
    # l'etat post-live-success via API _mark_fx_live_success (sinon CI sans
    # reseau classe comme fallback).
    prices._mark_fx_live_success("USD", "EUR")
    d = prices.fx("USD", "EUR")
    assert isinstance(d, Datum)
    assert d.value == 0.92
    assert d.source == "yfinance:fx"
    assert d.confidence == 1.0
    assert d.degraded is False


def test_fx_identity_returns_datum_one(monkeypatch) -> None:
    """fx(USD, USD) -> Datum(value=1.0, source=identity)."""
    d = prices.fx("USD", "USD")
    assert isinstance(d, Datum)
    assert d.value == 1.0
    assert d.source == "identity"


def test_fx_returns_none_when_fetch_fails(monkeypatch) -> None:
    monkeypatch.setattr(prices, "get_fx_rate", lambda b, q: None)
    assert prices.fx("XXX", "EUR") is None


# === Test 3 : _staleness_to_confidence palier (green/amber/degraded) ===


def test_staleness_green_full_confidence() -> None:
    conf, deg = prices._staleness_to_confidence(0.0, green_sec=900, amber_sec=3600)
    assert conf == 1.0
    assert deg is False


def test_staleness_amber_interpolated() -> None:
    """Au milieu de la zone amber, confidence interpolee."""
    conf, deg = prices._staleness_to_confidence(2250.0, green_sec=900, amber_sec=3600)
    # ratio = (2250-900) / (3600-900) = 0.5 -> conf = 1.0 - 0.5*0.5 = 0.75
    assert conf == pytest.approx(0.75, abs=0.01)
    assert deg is False


def test_staleness_above_amber_degraded() -> None:
    """age > amber_sec -> degraded=True, confidence floor 0.4."""
    conf, deg = prices._staleness_to_confidence(7200.0, green_sec=900, amber_sec=3600)
    assert conf == 0.4
    assert deg is True


# === Test 4 : derive() compose avec Datums issus du gateway ===


def test_value_eur_pattern_propagates_lineage(monkeypatch) -> None:
    """Walking-skeleton conceptuel : qty * price_native * fx_rate -> Datum derive
    qui herite asof=min, confidence=min, degraded=any.

    C'est exactement le pattern value_eur() de S2.
    """
    monkeypatch.setattr(prices, "get_current_price", lambda t: 100.0)
    monkeypatch.setattr(prices, "get_fx_rate", lambda b, q: 0.92)
    # Cure 16/06 : simule live success via API _mark_fx_live_success (cf
    # test_fx_returns_datum_when_fetch_succeeds). Sinon CI classe comme hardcoded
    # fallback -> confidence=0.4 au lieu de 1.0.
    prices._mark_fx_live_success("USD", "EUR")
    price = prices.get("NVDA")
    fx_rate = prices.fx("USD", "EUR")
    # Wrapper qty en Datum (ce que fera positions table en S2)
    qty = Datum(value=10.0, asof="2026-06-08T10:00:00Z", source="positions:NVDA", confidence=1.0)
    # Compose : value_eur = qty * price * fx
    value_eur = derive(
        lambda q, p, fx_: q * p * fx_,
        qty, price, fx_rate,
        op="qty_mul_price_mul_fx",
    )
    assert value_eur.value == pytest.approx(10.0 * 100.0 * 0.92)
    assert value_eur.source == "derived"
    assert value_eur.parents == (qty.id, price.id, fx_rate.id)
    assert value_eur.op == "qty_mul_price_mul_fx"
    # asof = le plus vieux des trois inputs (selon timing UTC actuel : peut etre
    # qty si tests run apres 10h UTC, peut etre price/fx si tests run avant).
    # Invariant verrouille : asof_out == min(inputs.asof).
    expected_min = min(qty.asof, price.asof, fx_rate.asof)
    assert value_eur.asof == expected_min
    # confidence = min des trois -> 1.0 ici (tous frais)
    assert value_eur.confidence == 1.0
    # degraded = False (aucun input degraded)
    assert value_eur.degraded is False


def test_value_eur_propagates_degraded_from_stale_price(monkeypatch) -> None:
    """Si price gateway marque degraded (post-amber), value_eur en herite."""
    # Mock degraded price
    def fake_get(ticker: str):
        from datetime import UTC, datetime
        return Datum(
            value=100.0,
            asof=datetime.now(UTC).isoformat(),
            source="yfinance",
            confidence=0.4,
            degraded=True,  # stale
        )
    monkeypatch.setattr(prices, "get", fake_get)
    monkeypatch.setattr(prices, "get_fx_rate", lambda b, q: 0.92)
    price = prices.get("NVDA")
    fx_rate = prices.fx("USD", "EUR")
    qty = Datum(value=10.0, asof="2026-06-08T10:00:00Z", source="positions:NVDA", confidence=1.0)
    value_eur = derive(lambda q, p, fx_: q * p * fx_, qty, price, fx_rate, op="value_eur")
    assert value_eur.degraded is True  # fail-closed propage
    assert value_eur.confidence == 0.4  # min des inputs


# === Tail-freshness ensure_price_history (cure 28/07/2026, cas BTC-USD) ===
# Série DENSE mais TRONQUÉE en fin de fenêtre : le gate volume seul (70 %)
# la laissait passer (crypto 7/7 = surplus de rows qui masque 50 j manquants)
# → BTC_drawdown180 calculé sur substance figée au 08/06 avec timestamp du
# jour. Contrat : le gate répond à DEUX questions — volume ET fin de fenêtre.


def _seed_price_history(tmp_path, monkeypatch, rows):
    import sqlite3
    db = tmp_path / "px.db"
    cx = sqlite3.connect(db)
    cx.executescript(
        """
        CREATE TABLE price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL, asof TEXT NOT NULL,
            price_native REAL NOT NULL, currency TEXT NOT NULL,
            source TEXT NOT NULL
        );
        """
    )
    cx.executemany(
        "INSERT INTO price_history (ticker, asof, price_native, currency, source) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db)
    return db


def _dense_truncated_rows(end_lag_days: int, n: int = 80):
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    return [
        (
            "BTC-USD",
            (now - timedelta(days=end_lag_days + i)).strftime("%Y-%m-%dT00:00:00+00:00"),
            60000.0 + i,
            "USD",
            "yfinance_backfill",
        )
        for i in range(n)
    ]


def test_ensure_tail_stale_triggers_backfill(tmp_path, monkeypatch) -> None:
    """80 rows 7/7 finissant il y a 50 j sur fenêtre 100 j : coverage >100 %
    mais queue morte -> le backfill DOIT se déclencher (avant la cure : non)."""
    from datetime import UTC, datetime, timedelta

    import pandas as pd

    _seed_price_history(tmp_path, monkeypatch, _dense_truncated_rows(end_lag_days=50))
    called = {"n": 0}

    class _FakeTicker:
        def history(self, **kw):
            called["n"] += 1
            idx = pd.date_range(end=datetime.now(UTC).date(), periods=10, freq="D")
            return pd.DataFrame({"Close": [65000.0] * 10}, index=idx)

    monkeypatch.setattr(prices, "_yf_ticker", lambda tk: _FakeTicker())
    start = datetime.now(UTC) - timedelta(days=100)
    df = prices.ensure_price_history("BTC-USD", start, datetime.now(UTC))
    assert called["n"] == 1, "queue morte (50 j) doit déclencher le backfill malgré coverage >70 %"
    assert df is not None and not df.empty
    assert df.index.max().date() >= (datetime.now(UTC) - timedelta(days=6)).date()


def test_ensure_fresh_tail_no_backfill(tmp_path, monkeypatch) -> None:
    """Série dense et fraîche (queue < 5 j) : aucun appel yfinance."""
    from datetime import UTC, datetime, timedelta

    _seed_price_history(tmp_path, monkeypatch, _dense_truncated_rows(end_lag_days=1))

    def _boom(tk):
        raise AssertionError("yfinance ne doit PAS être appelé sur série fraîche")

    monkeypatch.setattr(prices, "_yf_ticker", _boom)
    start = datetime.now(UTC) - timedelta(days=100)
    df = prices.ensure_price_history("BTC-USD", start, datetime.now(UTC))
    assert df is not None and not df.empty
