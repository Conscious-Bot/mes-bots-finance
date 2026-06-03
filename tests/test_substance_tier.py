"""ADR 014 § Substance tier (#97 hazard A fix) -- invariants substance filter.

Tests structurels qui garantissent :
- substance_predictions_filter() exclut v0 + rule_v1_shadow + rule_v1_fallback
- substance_predictions_filter() INCLUT v1 archive + v2 canonical (LLM families)
- substance ⊃ canonical (strict superset : substance inclut v1 archive,
  canonical le supplémentaire exclut)
- Future-proof : si une nouvelle famille non-LLM arrive (ex: rule_v2_*,
  ensemble_v1 si on déclare le ensemble non-LLM), l'ajouter dans le tuple
  SUBSTANCE_METHODOLOGY_EXCLUSIONS la masque automatiquement des base_rates /
  outcome_context / portfolio_grade / etc.

Spec user 03/06 : "Make the substance predicate an allow-list (real forward
LLM methodologies), or explicitly exclude the shadow/fallback families.
'non-canonical' means 'not in the public headline,' never 'invisible.'"
On a choisi exclusion explicite (symetric à canonical) plutot qu'allowlist
parce que : symetrie de pattern, ajout famille LLM future = pas de touch.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from shared.storage import (
    CANONICAL_METHODOLOGY_EXCLUSIONS,
    SUBSTANCE_METHODOLOGY_EXCLUSIONS,
    canonical_predictions_filter,
    substance_predictions_filter,
)


@pytest.fixture
def synthetic_db(monkeypatch, tmp_path):
    """DB peuplée avec 4 familles : v0/v1/v2/rule_v1_shadow/rule_v1_fallback."""
    db_path = tmp_path / "test_substance.db"
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
        # (id, ticker, outcome, prob, brier, sig_id, version)
        (1, "AAPL", "correct",   0.70, 0.09, 101, "v2"),
        (2, "MSFT", "correct",   0.65, 0.12, 102, "v2"),
        (3, "NVDA", "correct",   0.55, 0.20, 103, "v1"),
        (4, "GOOG", "incorrect", 0.60, 0.36, 104, "v1"),
        (5, "AMZN", "correct",   0.50, 0.25, 105, "v0"),       # quarantine
        (6, "TSLA", "incorrect", 0.60, 0.36, 106, "rule_v1_shadow"),
        (7, "META", "correct",   0.58, 0.18, 107, "rule_v1_shadow"),
        (8, "AMD",  "incorrect", 0.40, 0.16, 108, "rule_v1_fallback"),
    ]
    for r in rows:
        conn.execute(
            "INSERT INTO predictions (id, ticker, direction, outcome, "
            "probability_at_creation, brier_score, signal_id, methodology_version, "
            "resolved_at) VALUES (?, ?, 'bullish', ?, ?, ?, ?, ?, ?)",
            (r[0], r[1], r[2], r[3], r[4], r[5], r[6], now),
        )
    conn.commit()
    conn.close()
    from shared import storage
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    return db_path


# ─── Invariant 1 : substance exclut les non-LLM + quarantine ─────────────


def test_substance_excludes_v0():
    """v0 quarantine exclu (jamais ne resurface dans aucun tier)."""
    assert "v0" in SUBSTANCE_METHODOLOGY_EXCLUSIONS
    assert "'v0'" in substance_predictions_filter()


def test_substance_excludes_rule_v1_shadow():
    """Hazard A : shadow non-LLM ne doit JAMAIS contaminer le scorer-feed."""
    assert "rule_v1_shadow" in SUBSTANCE_METHODOLOGY_EXCLUSIONS
    assert "'rule_v1_shadow'" in substance_predictions_filter()


def test_substance_excludes_rule_v1_fallback():
    """Hazard A : fallback non-LLM ne doit JAMAIS contaminer portfolio_grade."""
    assert "rule_v1_fallback" in SUBSTANCE_METHODOLOGY_EXCLUSIONS
    assert "'rule_v1_fallback'" in substance_predictions_filter()


# ─── Invariant 2 : substance INCLUT toutes les familles LLM ───────────────


def test_substance_includes_v1():
    """v1 archive est LLM substance reelle (utilisee par base_rates etc)."""
    assert "v1" not in SUBSTANCE_METHODOLOGY_EXCLUSIONS
    assert "'v1'" not in substance_predictions_filter()


def test_substance_includes_v2():
    """v2 canonical inclus dans substance (canonical ⊂ substance)."""
    assert "v2" not in SUBSTANCE_METHODOLOGY_EXCLUSIONS
    assert "'v2'" not in substance_predictions_filter()


# ─── Invariant 3 : query SQL utilisable sur DB synthetique ────────────────


def test_substance_filter_returns_v1_and_v2(synthetic_db):
    """SELECT via substance filter retourne LLM families uniquement (v1 + v2)."""
    conn = sqlite3.connect(str(synthetic_db))
    rows = conn.execute(
        f"SELECT id, methodology_version FROM predictions WHERE {substance_predictions_filter()}"
    ).fetchall()
    conn.close()
    versions = {r[1] for r in rows}
    assert versions == {"v1", "v2"}
    assert len(rows) == 4  # 2 v2 + 2 v1


def test_substance_filter_excludes_non_llm_on_real_query(synthetic_db):
    """Garde-fou : aucune ligne shadow/fallback/v0 dans le resultat."""
    conn = sqlite3.connect(str(synthetic_db))
    rows = conn.execute(
        f"SELECT methodology_version FROM predictions WHERE {substance_predictions_filter()}"
    ).fetchall()
    conn.close()
    versions = {r[0] for r in rows}
    assert "v0" not in versions
    assert "rule_v1_shadow" not in versions
    assert "rule_v1_fallback" not in versions


# ─── Invariant 4 : canonical ⊂ substance (relation de subset) ────────────


def test_canonical_strict_subset_of_substance():
    """Toute exclusion canonique non-v0/non-rule doit etre dans canonical seul.

    Substance EXCLUSIONS = {v0, rule_v1_shadow, rule_v1_fallback}
    Canonical EXCLUSIONS = {v0, v1, rule_v1_shadow, rule_v1_fallback}
    Canonical ⊃ Substance EXCLUSIONS strictement -> Canonical (rows) ⊂
    Substance (rows). Toute ligne canonique est donc substance.
    """
    assert set(SUBSTANCE_METHODOLOGY_EXCLUSIONS).issubset(
        set(CANONICAL_METHODOLOGY_EXCLUSIONS)
    )
    # Et l'inverse : canonical a strictement plus d'exclusions que substance
    assert set(CANONICAL_METHODOLOGY_EXCLUSIONS) - set(SUBSTANCE_METHODOLOGY_EXCLUSIONS) == {"v1"}


def test_canonical_rows_subset_of_substance_rows(synthetic_db):
    """Toute ligne dans canonical doit aussi etre dans substance (verite SQL)."""
    conn = sqlite3.connect(str(synthetic_db))
    canon_ids = {
        r[0] for r in conn.execute(
            f"SELECT id FROM predictions WHERE {canonical_predictions_filter()}"
        ).fetchall()
    }
    subst_ids = {
        r[0] for r in conn.execute(
            f"SELECT id FROM predictions WHERE {substance_predictions_filter()}"
        ).fetchall()
    }
    conn.close()
    assert canon_ids.issubset(subst_ids)
    # Et substance a strictement plus (v1 archive)
    extras = subst_ids - canon_ids
    assert len(extras) > 0  # v1 archive lignes


# ─── Invariant 5 : structure SQL NOT IN (allowlist-equivalent) ────────────


def test_substance_filter_uses_not_in_structure():
    """Le filtre utilise NOT IN(...), ajout d'une famille non-LLM =
    ajouter au tuple, le filtre regenere automatiquement."""
    f = substance_predictions_filter()
    assert "NOT IN" in f
    for v in SUBSTANCE_METHODOLOGY_EXCLUSIONS:
        assert f"'{v}'" in f
