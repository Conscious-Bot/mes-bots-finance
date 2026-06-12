"""Tests append-only de la table `predictions` (audit 2026-06-12 P1.1).

`predictions` porte le track-record Brier/outcome. Régime propre (write-once-
per-column, comme thesis_predictions) — HORS APPEND_ONLY_TABLES, donc le
méta-test test_append_only_enforced ne la couvre PAS. Ce test verrouille
explicitement son comportement, via migration 0058 :

- predictions_no_delete : DELETE -> RAISE (le track-record ne se supprime pas).
- predictions_resolve_writeonce : 1re résolution (resolved_at NULL->valeur) OK,
  toute réécriture post-résolution des colonnes resolve -> RAISE (anti-falsification
  du Brier).

Les 6 journaux immutable (over_cap_alerts, kill_criteria_alerts, stress_gate_alerts,
macro_regime_alerts, stale_target_alerts, risk_signal_evaluations) sont, eux,
couverts automatiquement par test_append_only_enforced (ils sont au registre).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _insert_unresolved_prediction(cx: sqlite3.Connection) -> int:
    """INSERT minimal valide (colonnes NOT NULL sans défaut), resolved_at NULL.

    `methodology_version` NOT NULL sans default depuis migration 0030+ : stub
    "test" suffit (la valeur exacte n'influe pas sur l'append-only test).
    """
    cur = cx.execute(
        "INSERT INTO predictions (ticker, direction, horizon_days, baseline_date, "
        "                          target_date, methodology_version) "
        "VALUES ('TEST', 'up', 30, '2026-06-12', '2026-07-12', 'test')"
    )
    return int(cur.lastrowid)


def test_predictions_no_delete(migrated_db: Path):
    """DELETE sur predictions -> RAISE (append-only, track-record immuable)."""
    cx = sqlite3.connect(str(migrated_db))
    pid = _insert_unresolved_prediction(cx)
    with pytest.raises(sqlite3.IntegrityError):
        cx.execute("DELETE FROM predictions WHERE id=?", (pid,))


def test_predictions_first_resolution_allowed(migrated_db: Path):
    """1re résolution (resolved_at NULL -> valeur) : autorisée."""
    cx = sqlite3.connect(str(migrated_db))
    pid = _insert_unresolved_prediction(cx)
    # Ne doit PAS lever : OLD.resolved_at IS NULL au moment du 1er UPDATE.
    cx.execute(
        "UPDATE predictions SET resolved_at=CURRENT_TIMESTAMP, final_price=?, "
        "return_pct=?, outcome=?, credibility_delta=?, brier_score=? WHERE id=?",
        (110.0, 5.0, "hit", 0.1, 0.09, pid),
    )
    row = cx.execute("SELECT outcome, brier_score FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row[0] == "hit"
    assert row[1] == pytest.approx(0.09)


def test_predictions_reresolution_blocked(migrated_db: Path):
    """Réécriture du Brier/outcome après résolution -> RAISE (anti-falsification)."""
    cx = sqlite3.connect(str(migrated_db))
    pid = _insert_unresolved_prediction(cx)
    # 1re résolution OK
    cx.execute(
        "UPDATE predictions SET resolved_at=CURRENT_TIMESTAMP, outcome=?, brier_score=? WHERE id=?",
        ("hit", 0.09, pid),
    )
    # 2e écriture sur une colonne resolve (réécrire le Brier) -> mordue par le trigger
    with pytest.raises(sqlite3.IntegrityError):
        cx.execute("UPDATE predictions SET brier_score=0.99 WHERE id=?", (pid,))
    # Le Brier d'origine est préservé
    row = cx.execute("SELECT brier_score FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row[0] == pytest.approx(0.09)


def test_predictions_nonresolve_update_on_unresolved_passes(migrated_db: Path):
    """Garde-fou inverse : un UPDATE de colonne non-resolve sur une ligne NON résolue
    ne doit PAS être bloqué (le trigger ne fire que WHEN OLD.resolved_at IS NOT NULL
    et seulement sur les colonnes resolve). Évite un faux positif qui casserait la
    mutabilité légitime pré-résolution."""
    cx = sqlite3.connect(str(migrated_db))
    pid = _insert_unresolved_prediction(cx)
    # baseline_price n'est pas une colonne resolve, ligne non résolue -> doit passer
    cx.execute("UPDATE predictions SET baseline_price=? WHERE id=?", (100.0, pid))
    row = cx.execute("SELECT baseline_price FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row[0] == pytest.approx(100.0)
