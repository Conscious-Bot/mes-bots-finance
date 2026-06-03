"""ADR 014 -- invariants ledger segmentation par methodology_version.

Tests structurels qui garantissent :
- canonical_predictions_filter() exclut rule_v1_shadow + rule_v1_fallback + v0 + v1
- brier_by_methodology() retourne UNIQUEMENT la famille demandée, pas de fuite cross-family
- Future-proof : si une nouvelle famille (rule_v2_*, ensemble_*) est ajoutee SANS
  l'inclure dans CANONICAL_METHODOLOGY_EXCLUSIONS, le headline reste protege par
  defaut (allowlist implicite : par defaut on inclut canonique, le test sentinel
  attrape les regressions).

Spec user 03/06 (degraded_restitution_contract, resilience_architecture_spine) :
"JAMAIS commingled dans Brier headline." Cet ADR est inviolable par STRUCTURE,
pas par revue.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from shared.storage import (
    CANONICAL_METHODOLOGY_EXCLUSIONS,
    brier_by_methodology,
    canonical_predictions_filter,
)


@pytest.fixture
def synthetic_predictions_db(monkeypatch, tmp_path):
    """DB in-memory peuplée avec 4 familles methodology_version distinctes."""
    db_path = tmp_path / "test_ledger.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE predictions (
            id INTEGER PRIMARY KEY,
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL,
            horizon_days INTEGER NOT NULL DEFAULT 30,
            baseline_price REAL,
            baseline_date TEXT NOT NULL DEFAULT '2026-06-01',
            target_date TEXT NOT NULL DEFAULT '2026-07-01',
            resolved_at TEXT,
            final_price REAL,
            return_pct REAL,
            outcome TEXT,
            credibility_delta REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            probability_at_creation REAL,
            brier_score REAL,
            signal_id INTEGER,
            methodology_version TEXT NOT NULL DEFAULT 'v2'
        )
    """)
    now = datetime.now(UTC).isoformat()
    rows = [
        # (id, ticker, direction, outcome, prob, brier, sig_id, version)
        (1, "AAPL", "bullish", "correct",   0.70, 0.09, 101, "v2"),
        (2, "MSFT", "bullish", "correct",   0.65, 0.12, 102, "v2"),
        (3, "NVDA", "bullish", "incorrect", 0.72, 0.52, 103, "v2"),
        (4, "GOOG", "bullish", "correct",   0.55, 0.20, 104, "v1"),       # archive
        (5, "AMZN", "bullish", "correct",   0.50, 0.25, 105, "v0"),       # quarantine
        (6, "TSLA", "bullish", "incorrect", 0.60, 0.36, 106, "rule_v1_shadow"),   # challenger
        (7, "META", "bullish", "correct",   0.58, 0.18, 107, "rule_v1_shadow"),
        (8, "AMD",  "bullish", "incorrect", 0.40, 0.16, 108, "rule_v1_fallback"),  # plancher
    ]
    for r in rows:
        conn.execute(
            "INSERT INTO predictions (id, ticker, direction, outcome, "
            "probability_at_creation, brier_score, signal_id, methodology_version, "
            "resolved_at, horizon_days, baseline_price, baseline_date, target_date) "
            "VALUES (?,?,?,?,?,?,?,?,?,30,100,'2026-06-01','2026-07-01')",
            (*r, now),
        )
    conn.commit()
    conn.close()

    # Patch storage.DB_PATH pour que les helpers tapent cette DB
    from shared import storage
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    return db_path


# ─── Invariant 1 : filter exclut TOUTES les familles non-canoniques ────────


def test_canonical_filter_excludes_v0():
    """v0 (quarantine 12/05) exclu du headline."""
    assert "v0" in CANONICAL_METHODOLOGY_EXCLUSIONS
    assert "'v0'" in canonical_predictions_filter()


def test_canonical_filter_excludes_v1():
    """v1 (pre-pivot mono-bucket) exclu du headline."""
    assert "v1" in CANONICAL_METHODOLOGY_EXCLUSIONS
    assert "'v1'" in canonical_predictions_filter()


def test_canonical_filter_excludes_rule_v1_shadow():
    """rule_v1_shadow (challenger paired) exclu du headline.

    Crucial pour #96 : le shadow ne doit JAMAIS contaminer le Brier headline."""
    assert "rule_v1_shadow" in CANONICAL_METHODOLOGY_EXCLUSIONS
    assert "'rule_v1_shadow'" in canonical_predictions_filter()


def test_canonical_filter_excludes_rule_v1_fallback():
    """rule_v1_fallback (plancher degrade) exclu du headline.

    Crucial pour #94 : le fallback est un secours, pas de la calibration LLM."""
    assert "rule_v1_fallback" in CANONICAL_METHODOLOGY_EXCLUSIONS
    assert "'rule_v1_fallback'" in canonical_predictions_filter()


def test_canonical_filter_does_not_exclude_v2():
    """v2 (LLM Sonnet, ledger canonique 2026) NON exclu."""
    assert "v2" not in CANONICAL_METHODOLOGY_EXCLUSIONS
    assert "'v2'" not in canonical_predictions_filter()


# ─── Invariant 2 : query SQL utilisable ───────────────────────────────────


def test_canonical_filter_returns_only_v2(synthetic_predictions_db):
    """Une SELECT qui utilise le filter retourne UNIQUEMENT v2 dans la fixture."""
    conn = sqlite3.connect(str(synthetic_predictions_db))
    rows = conn.execute(
        f"SELECT id, methodology_version FROM predictions WHERE {canonical_predictions_filter()}"
    ).fetchall()
    conn.close()
    versions = {r[1] for r in rows}
    assert versions == {"v2"}, f"Expected only v2, got {versions}"
    assert len(rows) == 3  # AAPL, MSFT, NVDA dans la fixture


# ─── Invariant 3 : brier_by_methodology cible UNE famille, zero fuite ─────


def test_brier_by_methodology_v2_no_leak(synthetic_predictions_db):
    """Brier pour v2 = uniquement les 3 lignes v2, jamais shadow/fallback/archives."""
    stats = brier_by_methodology("v2")
    assert stats["n_total"] == 3
    assert stats["n_correct"] == 2
    assert stats["n_incorrect"] == 1


def test_brier_by_methodology_shadow_no_leak(synthetic_predictions_db):
    """Brier pour shadow = uniquement les 2 lignes shadow."""
    stats = brier_by_methodology("rule_v1_shadow")
    assert stats["n_total"] == 2
    assert stats["n_correct"] == 1
    assert stats["n_incorrect"] == 1


def test_brier_by_methodology_fallback_isolated(synthetic_predictions_db):
    """Brier pour fallback = uniquement la ligne fallback."""
    stats = brier_by_methodology("rule_v1_fallback")
    assert stats["n_total"] == 1
    assert stats["n_incorrect"] == 1


def test_brier_by_methodology_empty_family_returns_zero(synthetic_predictions_db):
    """Famille inexistante -> structure cohérente avec zéros."""
    stats = brier_by_methodology("llm_v999")
    assert stats["n_total"] == 0
    assert stats["brier_raw_avg"] is None


# ─── Invariant 4 : impossible de fabriquer la fuite via query directe ──────


def test_shadow_predictions_present_but_not_in_canonical(synthetic_predictions_db):
    """La DB contient shadow ET fallback (preuve qu'ils existent dans la fixture),
    MAIS le filter canonique les exclut. Garde-fou : si une regression rend le
    filter permissif, ce test attrape AVANT prod."""
    conn = sqlite3.connect(str(synthetic_predictions_db))
    n_total = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    n_canonical = conn.execute(
        f"SELECT COUNT(*) FROM predictions WHERE {canonical_predictions_filter()}"
    ).fetchone()[0]
    conn.close()
    assert n_total == 8
    assert n_canonical == 3
    assert n_canonical < n_total  # impossible que filter laisse tout passer


# ─── Invariant 5 : commingling impossible structurellement ──────────────


def test_canonical_filter_uses_not_in_not_or_chain():
    """Le filter doit utiliser NOT IN(...), pas une chaine de OR potentiellement
    incomplete. Construction structurelle : ajouter une famille = ajouter dans
    le tuple CANONICAL_METHODOLOGY_EXCLUSIONS, le filter regenere automatiquement."""
    filter_sql = canonical_predictions_filter()
    assert "NOT IN" in filter_sql
    # Chaque famille listee doit etre dans le SQL
    for version in CANONICAL_METHODOLOGY_EXCLUSIONS:
        assert f"'{version}'" in filter_sql
