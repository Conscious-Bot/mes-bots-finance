"""Tests M1 doctrine premier-principe : inputs dates, outputs derives live.

Spec red-team 07/06 nuit++ : "Stocke les inputs dates, derive les outputs live.
Ne stocke jamais une valeur qui est fonction d'un prix."

Verrouille :
- price_history + fx_history append-only avec triple (value, asof, source)
- shared/freshness.py SLA classification green/amber/rouge
- shared/valuation.py position_valuation = fonction, jamais persiste
- L15 fail-closed sur severity rouge (value_eur = None + raison)
- Hidden bug catch : si on stocke eur_value en table -> ce test detecte
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from shared.freshness import (
    classify_age,
    classify_asof,
    is_actionable,
    load_freshness_config,
)

# === Test 1 : freshness.yaml charge + SLA primary ===========================


def test_freshness_config_loads():
    cfg = load_freshness_config()
    assert "slas" in cfg
    assert "price" in cfg["slas"]
    assert "fx" in cfg["slas"]


def test_classify_age_thresholds():
    """green sous green_sec, amber entre green et amber, rouge au-dela."""
    cfg = load_freshness_config()["slas"]["price"]
    assert classify_age("price", 0) == "green"
    assert classify_age("price", cfg["green_sec"] - 1) == "green"
    assert classify_age("price", cfg["green_sec"] + 1) == "amber"
    assert classify_age("price", cfg["amber_sec"] + 1) == "rouge"


def test_classify_age_unknown_category_returns_rouge():
    """L15 fail-closed sur category inconnue."""
    assert classify_age("nonexistent", 0) == "rouge"


def test_classify_asof_iso_parsing():
    fresh_iso = datetime.now(UTC).isoformat()
    sev, age = classify_asof("price", fresh_iso)
    assert sev == "green"
    assert age >= 0 and age < 60


def test_classify_asof_invalid_returns_rouge():
    sev, age = classify_asof("price", "not_a_timestamp")
    assert sev == "rouge"
    assert age == -1.0


def test_is_actionable_green_amber_true_rouge_false():
    now = datetime.now(UTC).isoformat()
    assert is_actionable("price", now) is True
    rouge = (datetime.now(UTC) - timedelta(seconds=20000)).isoformat()
    assert is_actionable("price", rouge) is False


# === Test 2 : price_history + fx_history append-only ===


def test_insert_price_observation_appends(migrated_db):
    from shared.storage import get_latest_price, insert_price_observation
    rid = insert_price_observation(
        ticker="NVDA", price_native=850.0, currency="USD", source="test",
    )
    assert rid is not None
    latest = get_latest_price("NVDA")
    assert latest is not None
    assert latest["price_native"] == 850.0
    assert latest["currency"] == "USD"
    assert latest["source"] == "test"
    assert latest["ticker"] == "NVDA"


def test_insert_price_observation_latest_returns_most_recent(migrated_db):
    """Deux observations -> latest = la plus recente."""
    from shared.storage import get_latest_price, insert_price_observation
    insert_price_observation(
        "TSM", 100.0, "USD", source="test",
        asof="2026-06-01T10:00:00+00:00",
    )
    insert_price_observation(
        "TSM", 110.0, "USD", source="test",
        asof="2026-06-07T10:00:00+00:00",
    )
    latest = get_latest_price("TSM")
    assert latest["price_native"] == 110.0


def test_insert_fx_observation(migrated_db):
    from shared.storage import get_latest_fx_rate, insert_fx_observation
    rid = insert_fx_observation(base="USD", quote="EUR", rate=0.92, source="test")
    assert rid is not None
    latest = get_latest_fx_rate("USD", "EUR")
    assert latest is not None
    assert latest["rate"] == 0.92


# === Test 3 : position_valuation = function, jamais table ===


def test_position_valuation_returns_none_without_observation(migrated_db):
    """Sans price_history observation -> None ou unknown severity."""
    from shared import storage
    from shared.valuation import position_valuation

    # Create test position
    with storage.db() as cx:
        cx.execute(
            "INSERT INTO positions (ticker, qty, avg_cost, status, opened_at, last_updated) "
            "VALUES (?, ?, ?, 'open', ?, ?)",
            ("TESTV", 10.0, 100.0, "2026-06-07", "2026-06-07"),
        )
        pid = cx.execute("SELECT id FROM positions WHERE ticker='TESTV'").fetchone()[0]

    val = position_valuation(pid)
    assert val is not None
    assert val.ticker == "TESTV"
    assert val.qty == 10.0
    # Pas d'observation -> unknown severity, value_eur = None
    assert val.value_eur is None
    assert val.price_severity == "unknown"
    assert "no price_history observation" in val.value_eur_fail_reason


def test_position_valuation_computes_eur_when_fresh(migrated_db):
    """Avec price + fx fresh -> value_eur = qty * price * fx."""
    from shared import storage
    from shared.valuation import position_valuation

    # Setup position + fresh observations
    with storage.db() as cx:
        cx.execute(
            "INSERT INTO positions (ticker, qty, avg_cost, status, opened_at, last_updated) "
            "VALUES (?, ?, ?, 'open', ?, ?)",
            ("FRESH", 5.0, 100.0, "2026-06-07", "2026-06-07"),
        )
        pid = cx.execute("SELECT id FROM positions WHERE ticker='FRESH'").fetchone()[0]
    storage.insert_price_observation("FRESH", 200.0, "USD", source="test")
    storage.insert_fx_observation("USD", "EUR", 0.92, source="test")

    val = position_valuation(pid)
    assert val is not None
    # value_eur = 5 * 200 * 0.92 = 920
    assert val.value_eur == pytest.approx(920.0, abs=0.01)
    assert val.price_severity == "green"
    assert val.fx_severity == "green"
    assert val.overall_severity == "green"


def test_position_valuation_fail_closed_on_stale_inputs(migrated_db):
    """Severity rouge -> value_eur = None + raison explicite L15."""
    from shared import storage
    from shared.valuation import position_valuation

    with storage.db() as cx:
        cx.execute(
            "INSERT INTO positions (ticker, qty, avg_cost, status, opened_at, last_updated) "
            "VALUES (?, ?, ?, 'open', ?, ?)",
            ("STALE", 5.0, 100.0, "2026-06-07", "2026-06-07"),
        )
        pid = cx.execute("SELECT id FROM positions WHERE ticker='STALE'").fetchone()[0]

    # Inserer observation TRES vieille (>= rouge SLA price)
    old_asof = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    storage.insert_price_observation(
        "STALE", 200.0, "USD", source="test", asof=old_asof,
    )
    storage.insert_fx_observation("USD", "EUR", 0.92, source="test")

    val = position_valuation(pid)
    assert val is not None
    assert val.price_severity == "rouge"
    assert val.overall_severity == "rouge"
    # L15 fail-closed : value_eur = None malgre que le math fonctionne
    assert val.value_eur is None
    assert "fail-closed" in val.value_eur_fail_reason


def test_position_valuation_returns_none_if_position_closed(migrated_db):
    from shared.valuation import position_valuation
    val = position_valuation(99999)  # id inexistant
    assert val is None


# === Test 4 : M1 invariant : pas de eur_value persiste en table positions ===


def test_positions_schema_has_no_eur_value_column():
    """Catch the founding bug : si quelqu'un ajoute eur_value en table
    positions, ce test fail. La verite est calculee, jamais stockee.
    """
    from shared import storage
    with storage.db() as cx:
        cols = [
            r[1] for r in cx.execute("PRAGMA table_info(positions)").fetchall()
        ]
    forbidden = {"eur_value", "value_eur", "market_value_eur", "market_value"}
    found = forbidden & set(cols)
    assert not found, (
        f"M1 violation : colonne(s) derivee(s) {found} en table positions. "
        "Calcul live via shared.valuation.position_valuation, ne pas persister."
    )
