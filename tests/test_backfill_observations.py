"""v2.c.6 tests : backfill_resolved_observations -- architecture B3.

User 01/06 Q3 valide :
- resolution_json.delta_signed_eur = scoring CANONIQUE immutable (a +30j)
- resolution_json.observations[] = log d'enrichissement APPEND-ONLY
- Compatible PIT bitemporal (ADR 001) -- pas de mutation du scoring

4 tests canoniques :
1. bias_event resolved depuis 60j -> backfille observation +60j
2. bias_event resolved depuis 90j -> backfille observations +60j ET +90j
3. observation deja presente -> skip (idempotent)
4. anchor_price_eur manquant -> error compte, scoring inchange
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


def _schema_minimal(cx: sqlite3.Connection) -> None:
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
            resolve_at TEXT NOT NULL,
            position_event_id INTEGER
        );
    """)


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "test.db"
    cx = sqlite3.connect(db)
    _schema_minimal(cx)
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db)
    return db


def _seed_resolved(
    db: Path, *, eid: int = 1, ticker: str = "NVDA",
    anchor_eur: float = 100.0, initial_qty: float = 50.0,
    delta_30: float = 200.0, days_ago: int = 60,
    observations: list | None = None,
) -> None:
    """INSERT bias_event resolved avec resolution_json + observations[]."""
    created = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    resolved = (datetime.now(UTC) - timedelta(days=days_ago - 30)).isoformat()
    cf = json.dumps({
        "anchor_price_eur": anchor_eur, "initial_qty": initial_qty,
        "discipline_expected_delta": 0.0,
        "counterfactual_method": "cash_idle", "horizon_days": 30,
    }, sort_keys=True)
    res = {
        "delta_signed_eur": delta_30,
        "horizon_days": 30,
        "anchor_price_eur": anchor_eur,
        "resolved_at": resolved,
        "counterfactual_method": "cash_idle",
    }
    if observations is not None:
        res["observations"] = observations

    cx = sqlite3.connect(db)
    cx.execute(
        "INSERT INTO bias_events "
        "(id, created_at, ticker, bias, action, decision_json, "
        " counterfactual_json, resolution_json, status, source, "
        " horizon_days, resolve_at) "
        "VALUES (?, ?, ?, 'lock_in', 'acted_on_bias', '{}', ?, ?, "
        " 'resolved', 'auto_detected', 30, ?)",
        (eid, created, ticker, cf, json.dumps(res, sort_keys=True), resolved),
    )
    cx.commit()
    cx.close()


def _mock_prices(monkeypatch: pytest.MonkeyPatch, eur: float = 130.0,
                 native: float = 130.0) -> None:
    import shared.prices
    monkeypatch.setattr(shared.prices, "get_close_on_in_eur",
                        lambda tk, d: eur)
    monkeypatch.setattr(shared.prices, "get_close_on",
                        lambda tk, d: native)


def _read_observations(db: Path, eid: int) -> list:
    cx = sqlite3.connect(db)
    row = cx.execute(
        "SELECT resolution_json FROM bias_events WHERE id=?", (eid,)
    ).fetchone()
    cx.close()
    res = json.loads(row[0])
    return res.get("observations", [])


# ─── Test 1 : event resolved depuis 60j -> backfille +60j ────────────────


def test_resolved_60d_ago_backfills_60d_observation(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bias_event resolved canoniquement (+30j) il y a 30j supplementaires
    (donc anchor il y a 60j) -> backfill +60j (mais pas +90j car pas encore
    atteint)."""
    _seed_resolved(isolated_db, eid=1, ticker="NVDA",
                   anchor_eur=100.0, initial_qty=50.0,
                   delta_30=200.0, days_ago=60)
    _mock_prices(monkeypatch, eur=130.0)

    from intelligence.bias_events import backfill_resolved_observations

    # Query default fetch tous les bias_events ou anchor + max(60,90) <= now
    # Or notre seed est il y a 60j, donc < 90j -> ne sera PAS scanned avec
    # horizons par default (60, 90). Lancons avec (60,) seul.
    stats = backfill_resolved_observations(horizons=(60,))
    assert stats["scanned"] == 1
    assert stats["enriched"] == 1

    obs = _read_observations(isolated_db, 1)
    assert len(obs) == 1
    assert obs[0]["horizon_days"] == 60
    assert obs[0]["price_eur"] == 130.0
    assert obs[0]["delta_eur"] == pytest.approx((130 - 100) * 50, abs=0.01)


# ─── Test 2 : event resolved depuis 90j -> backfille +60j ET +90j ────────


def test_resolved_90d_ago_backfills_both_horizons(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """anchor il y a 90j -> backfill +60j ET +90j en un seul run."""
    _seed_resolved(isolated_db, eid=1, ticker="NVDA",
                   anchor_eur=100.0, initial_qty=50.0,
                   delta_30=200.0, days_ago=90)
    _mock_prices(monkeypatch, eur=140.0)

    from intelligence.bias_events import backfill_resolved_observations
    stats = backfill_resolved_observations(horizons=(60, 90))
    assert stats["scanned"] == 1
    assert stats["enriched"] == 1

    obs = _read_observations(isolated_db, 1)
    assert len(obs) == 2
    horizons_present = sorted(o["horizon_days"] for o in obs)
    assert horizons_present == [60, 90]


# ─── Test 3 : observation deja presente -> skip (idempotent) ──────────────


def test_observation_already_present_skip_idempotent(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Observation +60j deja presente. Run le backfill -> ne re-fetch pas,
    skip propre. Mais peut backfille +90j si pas present."""
    pre_existing_obs = [{
        "horizon_days": 60,
        "price_eur": 125.0,
        "delta_eur": 1250.0,
        "fetched_at": "2026-05-31T00:00:00+00:00",
    }]
    _seed_resolved(isolated_db, eid=1, ticker="NVDA",
                   anchor_eur=100.0, initial_qty=50.0,
                   delta_30=200.0, days_ago=90,
                   observations=pre_existing_obs)
    _mock_prices(monkeypatch, eur=140.0)

    from intelligence.bias_events import backfill_resolved_observations
    _ = backfill_resolved_observations(horizons=(60, 90))
    # +60j skip (deja present), +90j enriched
    obs = _read_observations(isolated_db, 1)
    assert len(obs) == 2
    horizons = sorted(o["horizon_days"] for o in obs)
    assert horizons == [60, 90]
    # +60j garde la valeur ancienne (pas overwritten)
    obs_60 = next(o for o in obs if o["horizon_days"] == 60)
    assert obs_60["price_eur"] == 125.0  # ancienne valeur preservee


# ─── Test 4 : anchor_price_eur manquant -> error, scoring inchange ────────


def test_missing_anchor_eur_error_no_scoring_mutation(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cf.anchor_price_eur absent -> compte en errors, ne modifie PAS le
    resolution_json existant (scoring canonical immutable)."""
    # seed manual avec cf sans anchor_price_eur
    created = (datetime.now(UTC) - timedelta(days=70)).isoformat()
    resolved = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    cx = sqlite3.connect(isolated_db)
    cx.execute(
        "INSERT INTO bias_events "
        "(created_at, ticker, bias, action, decision_json, counterfactual_json, "
        " resolution_json, status, source, horizon_days, resolve_at) "
        "VALUES (?, 'BAD', 'lock_in', 'acted_on_bias', '{}', '{}', "
        " ?, 'resolved', 'auto_detected', 30, ?)",
        (created, json.dumps({"delta_signed_eur": 100.0}, sort_keys=True), resolved),
    )
    cx.commit()
    cx.close()
    _mock_prices(monkeypatch, eur=130.0)

    from intelligence.bias_events import backfill_resolved_observations
    stats = backfill_resolved_observations(horizons=(60,))
    assert stats["errors"] >= 1

    # Scoring canonical NON mute
    cx = sqlite3.connect(isolated_db)
    row = cx.execute(
        "SELECT resolution_json FROM bias_events WHERE ticker='BAD'"
    ).fetchone()
    cx.close()
    res = json.loads(row[0])
    assert res["delta_signed_eur"] == 100.0  # immutable
    assert "observations" not in res or res["observations"] == []
