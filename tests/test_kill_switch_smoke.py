"""Smoke tests for risk/kill_switch.py (kill-condition disjoncteur grappe AI-compute).

Cf doctrine vault "Kill-condition — disjoncteur de la grappe AI-compute" V3 (26/06).
Cf spec handoff §8.
"""

from __future__ import annotations

import pytest

from risk import kill_switch as ks


def test_module_imports():
    """Ensure all public exports are present."""
    assert hasattr(ks, "check_and_fire")
    assert hasattr(ks, "validate_override")
    assert hasattr(ks, "snapshot_cluster_value")
    assert hasattr(ks, "escalate_unresolved")
    assert hasattr(ks, "cmd_kill_exec")
    assert hasattr(ks, "cmd_kill_override")
    assert hasattr(ks, "cmd_kill_resolve")


def test_stage_thresholds(monkeypatch):
    """Stage detection : 0 normal / 1 vigilance / 2 derisque / 3 hard (si activé)."""
    monkeypatch.setattr(
        ks,
        "_cfg",
        lambda: {
            "drawdown_reduce_pct": 0.25,
            "drawdown_stop_pct": 0.35,
            "drawdown_hard_pct": None,
        },
    )
    assert ks.stage_for_drawdown(-0.10) == 0  # < reduce → normal
    assert ks.stage_for_drawdown(-0.25) == 1  # >= reduce → vigilance
    assert ks.stage_for_drawdown(-0.34) == 1  # < stop, > reduce → vigilance
    assert ks.stage_for_drawdown(-0.35) == 2  # >= stop → derisque
    assert ks.stage_for_drawdown(-0.60) == 2  # hard désactivé → caps à 2


def test_stage_thresholds_hard_enabled(monkeypatch):
    """Si drawdown_hard_pct activé : Stage 3 atteignable."""
    monkeypatch.setattr(
        ks,
        "_cfg",
        lambda: {
            "drawdown_reduce_pct": 0.25,
            "drawdown_stop_pct": 0.35,
            "drawdown_hard_pct": 0.50,
        },
    )
    assert ks.stage_for_drawdown(-0.50) == 3
    assert ks.stage_for_drawdown(-0.49) == 2


def test_override_rejects_no_date(monkeypatch):
    monkeypatch.setattr(ks, "_cfg", lambda: {"override_min_chars": 10})
    ok, d, _ = ks.validate_override("la thèse va se redresser bientôt promis")
    assert ok is False
    assert d is None


def test_override_rejects_past_date(monkeypatch):
    monkeypatch.setattr(ks, "_cfg", lambda: {"override_min_chars": 10})
    ok, _d, _ = ks.validate_override(
        "je tiens car capex intact, tort si <1.0 le 2020-01-01"
    )
    assert ok is False


def test_override_accepts_future_dated(monkeypatch):
    monkeypatch.setattr(ks, "_cfg", lambda: {"override_min_chars": 10})
    ok, d, _ = ks.validate_override(
        "je tiens: capex hyperscaler intact; tort si book-to-bill ASML <1.0 d'ici 2026-11-30"
    )
    assert ok is True
    assert d == "2026-11-30"


def test_override_rejects_too_short(monkeypatch):
    monkeypatch.setattr(ks, "_cfg", lambda: {"override_min_chars": 40})
    ok, _d, _ = ks.validate_override("tort si X 2026-12-01")
    assert ok is False


def test_override_invalid_date_format(monkeypatch):
    """Date type-extractable mais invalide (mois 13)."""
    monkeypatch.setattr(ks, "_cfg", lambda: {"override_min_chars": 10})
    ok, _d, _reason = ks.validate_override(
        "je tiens longuement; ma date est 2026-13-99 absurde"
    )
    assert ok is False


def test_cluster_membership_explicit(monkeypatch):
    """cluster_tickers explicite a priorité sur cluster_narrative."""
    monkeypatch.setattr(
        ks,
        "_cfg",
        lambda: {"cluster_tickers": ["asml.as", "TSM", "000660.KS"]},
    )
    members = ks._cluster_membership()
    assert "ASML.AS" in members  # uppercased
    assert "TSM" in members
    assert "000660.KS" in members
    assert len(members) == 3


def test_cluster_membership_neither_defined_raises(monkeypatch):
    """Ni cluster_tickers ni cluster_narrative → ConfigurationError."""
    monkeypatch.setattr(ks, "_cfg", dict)
    from shared import config

    with pytest.raises(config.ConfigurationError):
        ks._cluster_membership()
