"""Axe 2 QUALITY_BAR tests : source_diversity helpers.

Garde-fou : 2 sources d'une meme cohorte narrative ne comptent pas pour 2.
Le 1er geste rend visible la monoculture, pas encore corrige (gating L15
calibration N<100).

Tests :
1. Liste vide -> stats vides, pas de division par zero
2. Cas monoculture : 5 signaux tous newsletters -> N_eff=1, is_monoculture=True
3. Cas orthogonal pur : 1 signal EDGAR -> N_eff=1, n_orthogonal=1
4. Cas mixte : 3 newsletters + 1 EDGAR + 1 insider -> N_eff=3, n_orthogonal=2
5. is_monoculture False quand 1 seule newsletter (pas une cohorte)
6. is_monoculture False quand 1 narrative + 1 orthogonal
7. Resolution via source_id DB (round-trip)
8. book_source_composition global (snapshot DB)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from intelligence import source_diversity as sd


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "test.db"
    cx = sqlite3.connect(db)
    cx.executescript("""
        CREATE TABLE sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            credibility REAL NOT NULL DEFAULT 0.5,
            family TEXT NOT NULL DEFAULT 'narrative_newsletter'
        );
        INSERT INTO sources (id, name, type, family) VALUES
            (1, 'SemiAnalysis', 'newsletter', 'narrative_newsletter'),
            (2, 'Doomberg', 'newsletter', 'narrative_newsletter'),
            (3, 'Stoller', 'newsletter', 'narrative_newsletter'),
            (10, 'SEC EDGAR 8-K', 'sec_filing', 'primary_filing'),
            (20, 'Form 4 Insider', 'insider', 'insider'),
            (30, 'Goldman Sachs', 'broker_research', 'broker_research'),
            (40, 'WSB', 'social', 'social');
    """)
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db)
    return db


# ─── Test 1 : liste vide ───────────────────────────────────────────────────


def test_empty_signals_returns_zero() -> None:
    out = sd.effective_n_signals([])
    assert out == {
        "n_raw": 0, "n_effective": 0, "n_orthogonal": 0,
        "by_family": {}, "is_monoculture": False,
    }


# ─── Test 2 : monoculture pure ─────────────────────────────────────────────


def test_monoculture_5_newsletters(isolated_db: Path) -> None:
    """5 signaux tous narrative_newsletter -> N_eff=1, is_monoculture=True."""
    signals = [{"source_id": sid} for sid in [1, 2, 3, 1, 2]]
    out = sd.effective_n_signals(signals)
    assert out["n_raw"] == 5
    assert out["n_effective"] == 1
    assert out["n_orthogonal"] == 0
    assert out["by_family"] == {"narrative_newsletter": 5}
    assert out["is_monoculture"] is True


# ─── Test 3 : orthogonal pur ───────────────────────────────────────────────


def test_orthogonal_single_edgar(isolated_db: Path) -> None:
    signals = [{"source_id": 10}]
    out = sd.effective_n_signals(signals)
    assert out["n_raw"] == 1
    assert out["n_effective"] == 1
    assert out["n_orthogonal"] == 1
    assert out["by_family"] == {"primary_filing": 1}
    assert out["is_monoculture"] is False


# ─── Test 4 : mixte ──────────────────────────────────────────────────────


def test_mixed_3_narrative_plus_orthogonal(isolated_db: Path) -> None:
    """3 newsletters + 1 EDGAR + 1 insider = 3 familles, 2 orthogonales."""
    signals = [
        {"source_id": 1}, {"source_id": 2}, {"source_id": 3},
        {"source_id": 10}, {"source_id": 20},
    ]
    out = sd.effective_n_signals(signals)
    assert out["n_raw"] == 5
    assert out["n_effective"] == 3
    assert out["n_orthogonal"] == 2  # primary_filing + insider
    assert out["by_family"] == {
        "narrative_newsletter": 3,
        "primary_filing": 1,
        "insider": 1,
    }
    assert out["is_monoculture"] is False


# ─── Test 5 : 1 newsletter unique != monoculture ───────────────────────────


def test_single_newsletter_not_monoculture(isolated_db: Path) -> None:
    """1 seule newsletter : pas une cohorte. is_monoculture False."""
    signals = [{"source_id": 1}]
    out = sd.effective_n_signals(signals)
    assert out["n_raw"] == 1
    assert out["n_effective"] == 1
    assert out["is_monoculture"] is False


# ─── Test 6 : narrative + orthogonal -> pas monoculture ────────────────────


def test_narrative_plus_orthogonal_not_monoculture(isolated_db: Path) -> None:
    """Newsletter + EDGAR : melange orthogonal, plus une cohorte."""
    signals = [{"source_id": 1}, {"source_id": 1}, {"source_id": 10}]
    out = sd.effective_n_signals(signals)
    assert out["n_effective"] == 2
    assert out["is_monoculture"] is False


# ─── Test 7 : family explicite dans signal short-circuit DB ────────────────


def test_explicit_source_family_bypass_db() -> None:
    """Si source_family explicite -> pas de lookup DB necessaire."""
    signals = [
        {"source_family": "primary_filing"},
        {"source_family": "narrative_newsletter"},
        {"source_family": "narrative_newsletter"},
    ]
    out = sd.effective_n_signals(signals)
    assert out["n_raw"] == 3
    assert out["n_effective"] == 2
    assert out["n_orthogonal"] == 1


# ─── Test 8 : book_source_composition global ──────────────────────────────


def test_book_source_composition_distribution(isolated_db: Path) -> None:
    out = sd.book_source_composition()
    assert out["total"] == 7
    assert out["by_family"]["narrative_newsletter"] == 3
    assert out["by_family"]["primary_filing"] == 1
    assert out["by_family"]["insider"] == 1
    # 3 orthogonal (primary + insider + broker) sur 7 = 42.9%
    assert out["orthogonal_pct"] == pytest.approx(42.9, abs=0.1)
    # 3 narrative sur 7 = 42.9%
    assert out["narrative_pct"] == pytest.approx(42.9, abs=0.1)


# ─── Test 9 : signal sans source_id ni source_family -> 'other' ────────────


def test_signal_without_source_id_or_family_defaults_other() -> None:
    signals = [{"some_other_field": "value"}]
    out = sd.effective_n_signals(signals)
    assert out["by_family"] == {"other": 1}
    assert out["n_orthogonal"] == 0


# ─── Test 10 : source_id inconnu DB -> 'other' ─────────────────────────────


def test_unknown_source_id_defaults_other(isolated_db: Path) -> None:
    signals = [{"source_id": 9999}]  # not in DB
    out = sd.effective_n_signals(signals)
    assert out["by_family"] == {"other": 1}
