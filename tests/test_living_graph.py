"""W0 LIVING GRAPH tests serrures — fork-detection + anti-cry-wolf + idempotence.

Cf SPEC_LIVING_GRAPH.md §6 tests verrouillants.
Le test critique : reproduire le cas exact L29 09/06 (PMP roulant divergent
entre deux producteurs) via fixture → fork détecté. Et inversement : deux
producteurs convergents en-deçà de ε → 0 fork (anti-cry-wolf).
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import date

import pytest


@pytest.fixture
def lg_db(monkeypatch):
    """DB temporaire isolée avec table concept_index. Reset à chaque test."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setattr("shared.storage.DB_PATH", tmp.name)
    # Réinit le cache module-level _REGISTRY_CACHE entre tests (registre yaml)
    from shared import living_graph
    living_graph._REGISTRY_CACHE = None

    cx = sqlite3.connect(tmp.name)
    cx.execute("""
        CREATE TABLE concept_index (
            concept_key TEXT NOT NULL,
            ticker TEXT NOT NULL DEFAULT '',
            asof_bucket TEXT NOT NULL,
            source TEXT NOT NULL,
            value REAL NOT NULL,
            op TEXT,
            degraded INTEGER NOT NULL DEFAULT 0,
            confidence REAL NOT NULL DEFAULT 1.0,
            logged_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (concept_key, ticker, asof_bucket, source)
        )
    """)
    cx.commit()
    cx.close()
    yield tmp.name
    os.unlink(tmp.name)


def test_fork_detected_above_epsilon(lg_db):
    """Le cas L29 09/06 : 2 sources publient pmp_eur divergent > ε=0.001 → fork."""
    from shared.living_graph import detect_forks, register_concept
    today = date.today().isoformat()

    # SK Hynix : BookLine dit 45.21, VUE SQL legacy dit 44.83 — divergence ~0.85%
    register_concept("pmp_eur", 45.21, source="ledger_pmp", ticker="000660.KS")
    register_concept("pmp_eur", 44.83, source="sql_view", ticker="000660.KS")

    forks = detect_forks(today)
    assert len(forks) == 1, f"expected 1 fork, got {len(forks)}: {forks}"
    f = forks[0]
    assert f["concept_key"] == "pmp_eur"
    assert f["ticker"] == "000660.KS"
    assert f["max_div_rel"] > 0.001  # au-delà ε pmp_eur
    assert len(f["candidates"]) == 2
    sources = {c["source"] for c in f["candidates"]}
    assert sources == {"ledger_pmp", "sql_view"}


def test_no_fork_below_epsilon(lg_db):
    """Anti-cry-wolf : 2 sources divergent < ε → 0 fork (jitter, pas fork)."""
    from shared.living_graph import detect_forks, register_concept
    today = date.today().isoformat()

    # Diff 0.05% < ε=0.001 → pas un vrai fork, juste du jitter intra-regen
    register_concept("pmp_eur", 100.000, source="ledger_pmp", ticker="TSLA")
    register_concept("pmp_eur", 100.050, source="sql_view", ticker="TSLA")

    forks = detect_forks(today)
    assert forks == [], f"expected no fork (jitter < ε), got: {forks}"


def test_idempotent_upsert_no_duplicate(lg_db):
    """Même source publié 2× même bucket = UPSERT idempotent, pas de 2e row."""
    from shared.living_graph import detect_forks, register_concept
    today = date.today().isoformat()

    register_concept("pmp_eur", 100.0, source="ledger_pmp", ticker="NVDA")
    register_concept("pmp_eur", 100.0, source="ledger_pmp", ticker="NVDA")  # 2e publish
    register_concept("pmp_eur", 100.0, source="ledger_pmp", ticker="NVDA")  # 3e publish

    forks = detect_forks(today)
    assert forks == [], "single source republished = no fork"

    # Vérifie 1 seule row dans la table
    import shared.storage as _st
    with _st.db() as cx:
        n = cx.execute(
            "SELECT COUNT(*) AS n FROM concept_index WHERE ticker = 'NVDA'"
        ).fetchone()["n"]
    assert n == 1, f"expected 1 row (UPSERT), got {n}"


def test_unknown_concept_uses_default_epsilon(lg_db):
    """Concept hors registre yaml : default ε=0.001 (strict)."""
    from shared.living_graph import detect_forks, register_concept
    today = date.today().isoformat()

    # 'unknown_concept' pas dans concept_keys.yaml → ε default 0.001
    register_concept("unknown_concept", 100.0, source="A", ticker="XX")
    register_concept("unknown_concept", 100.5, source="B", ticker="XX")  # 0.5% diff

    forks = detect_forks(today)
    assert len(forks) == 1, "0.5% > default ε=0.001 → fork attendu"


def test_register_silent_miss_if_db_down(lg_db, monkeypatch):
    """Si living_graph DB indispo, register_concept silent-miss L7 (pas exception)."""
    from shared import living_graph

    def _fail_db():
        raise sqlite3.OperationalError("simulated DB down")

    monkeypatch.setattr("shared.storage.db", _fail_db)

    # Ne doit PAS raise — producteur appelant ne doit pas casser
    living_graph.register_concept("pmp_eur", 100.0, source="X", ticker="TEST")
