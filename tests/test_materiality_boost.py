"""Tests pour intelligence.materiality_boost (chemins critiques #36).

Couverture cible : >85% sur materiality_boost.py (vs ~17% pre-test).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from intelligence.materiality_boost import (
    compute_corroboration_multiplier,
    recompute_boosts_for_clustered_signals,
)


# ─── compute_corroboration_multiplier : 4 branches ────────────────────────


def test_multiplier_lone_signal_returns_1():
    """1 source = 1.0 (no boost)."""
    assert compute_corroboration_multiplier(1) == 1.0


def test_multiplier_zero_sources_returns_1():
    """0 sources = 1.0 (degenerate, no boost). Branch implicite."""
    assert compute_corroboration_multiplier(0) == 1.0


def test_multiplier_negative_returns_1():
    """Defensive : n < 0 ne doit pas casser, retombe sur 1.0."""
    assert compute_corroboration_multiplier(-5) == 1.0


def test_multiplier_two_sources_returns_1_3():
    assert compute_corroboration_multiplier(2) == 1.3


def test_multiplier_three_sources_returns_1_5():
    assert compute_corroboration_multiplier(3) == 1.5


def test_multiplier_four_sources_returns_1_7():
    assert compute_corroboration_multiplier(4) == 1.7


def test_multiplier_many_sources_caps_at_1_7():
    """N >= 4 sature a 1.7 (le boost ne grandit pas indefiniment)."""
    assert compute_corroboration_multiplier(10) == 1.7
    assert compute_corroboration_multiplier(100) == 1.7


def test_multiplier_monotonic():
    """Invariant metier : plus de sources -> boost >= (jamais decroissant)."""
    prev = 0.0
    for n in range(0, 10):
        b = compute_corroboration_multiplier(n)
        assert b >= prev, f"n={n} regresse: {b} < {prev}"
        prev = b


# ─── recompute_boosts_for_clustered_signals : DB integration ──────────────


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Mini schema : signals (id, echo_cluster_id, materiality_boost) + 2 helpers
    storage. Monkeypatch storage._DB_PATH + 2 fonctions storage utilisees."""
    db = tmp_path / "test.db"
    cx = sqlite3.connect(db)
    cx.executescript("""
        CREATE TABLE signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            echo_cluster_id TEXT,
            materiality_boost REAL DEFAULT 1.0
        );
    """)
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage._DB_PATH", db)
    monkeypatch.setattr("shared.storage.DB_PATH", db)
    return db


def _seed_signals(db: Path, items: list[tuple[int, str | None, float]]) -> None:
    """items: list of (id, cluster_id, current_boost)."""
    cx = sqlite3.connect(db)
    for (sid, cid, boost) in items:
        cx.execute(
            "INSERT INTO signals (id, echo_cluster_id, materiality_boost) VALUES (?, ?, ?)",
            (sid, cid, boost),
        )
    cx.commit()
    cx.close()


def _read_boost(db: Path, sid: int) -> float | None:
    cx = sqlite3.connect(db)
    row = cx.execute(
        "SELECT materiality_boost FROM signals WHERE id=?", (sid,)
    ).fetchone()
    cx.close()
    return row[0] if row else None


def test_recompute_skips_unclustered_signals(isolated_db, monkeypatch):
    """Signal sans echo_cluster_id n'est pas updated."""
    _seed_signals(isolated_db, [(1, None, 1.0)])
    monkeypatch.setattr(
        "shared.storage.get_signals_in_cluster_with_sources", lambda cid: 999,
    )
    monkeypatch.setattr(
        "shared.storage.update_materiality_boost",
        lambda sid, b: pytest.fail("should not call update on unclustered"),
    )
    n = recompute_boosts_for_clustered_signals()
    assert n == 0


def test_recompute_updates_when_boost_changes(isolated_db, monkeypatch):
    """Signal clustered + n_sources change -> update + count."""
    _seed_signals(isolated_db, [(1, "cluster_A", 1.0)])
    monkeypatch.setattr(
        "shared.storage.get_signals_in_cluster_with_sources", lambda cid: 3,
    )
    updates: list[tuple] = []
    monkeypatch.setattr(
        "shared.storage.update_materiality_boost",
        lambda sid, b: updates.append((sid, b)),
    )
    n = recompute_boosts_for_clustered_signals()
    assert n == 1
    assert updates == [(1, 1.5)]  # n=3 -> 1.5


def test_recompute_skips_when_boost_unchanged(isolated_db, monkeypatch):
    """Signal deja a la valeur correcte -> pas d'update (idempotent)."""
    _seed_signals(isolated_db, [(1, "cluster_A", 1.5)])
    monkeypatch.setattr(
        "shared.storage.get_signals_in_cluster_with_sources", lambda cid: 3,
    )
    monkeypatch.setattr(
        "shared.storage.update_materiality_boost",
        lambda sid, b: pytest.fail("should not call update when unchanged"),
    )
    n = recompute_boosts_for_clustered_signals()
    assert n == 0


def test_recompute_handles_null_current_boost(isolated_db, monkeypatch):
    """COALESCE(materiality_boost, 1.0) fallback : signal avec boost NULL
    doit etre traite comme 1.0 baseline."""
    cx = sqlite3.connect(isolated_db)
    cx.execute(
        "INSERT INTO signals (id, echo_cluster_id, materiality_boost) "
        "VALUES (1, 'cluster_A', NULL)",
    )
    cx.commit()
    cx.close()
    monkeypatch.setattr(
        "shared.storage.get_signals_in_cluster_with_sources", lambda cid: 2,
    )
    updates: list[tuple] = []
    monkeypatch.setattr(
        "shared.storage.update_materiality_boost",
        lambda sid, b: updates.append((sid, b)),
    )
    n = recompute_boosts_for_clustered_signals()
    assert n == 1
    assert updates == [(1, 1.3)]


def test_recompute_multiple_signals_different_clusters(isolated_db, monkeypatch):
    """3 signals, 3 clusters de tailles 2/3/4 -> 3 updates."""
    _seed_signals(isolated_db, [
        (1, "cluster_2src", 1.0),
        (2, "cluster_3src", 1.0),
        (3, "cluster_4src", 1.0),
    ])
    cluster_sizes = {"cluster_2src": 2, "cluster_3src": 3, "cluster_4src": 4}
    monkeypatch.setattr(
        "shared.storage.get_signals_in_cluster_with_sources",
        lambda cid: cluster_sizes[cid],
    )
    updates: list[tuple] = []
    monkeypatch.setattr(
        "shared.storage.update_materiality_boost",
        lambda sid, b: updates.append((sid, b)),
    )
    n = recompute_boosts_for_clustered_signals()
    assert n == 3
    assert sorted(updates) == [(1, 1.3), (2, 1.5), (3, 1.7)]
