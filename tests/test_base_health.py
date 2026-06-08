"""Tests verrouillants SOCLE Phase 2 S3 : base_health scoreboard.

Verifie le contrat des 3 dimensions + l'agregation. Tests deterministes
(pas de hit reseau) : on patche les sous-fonctions pour reproduire les
3 etats canoniques (GREEN/AMBER/RED).

Cf SPEC_SOCLE.md S4 + HANDOFF_SOCLE.md S3.
"""

from __future__ import annotations

import pytest

from scripts import base_health

# === Test 1 : aggregate_status (worst dim wins) ===


def test_aggregate_all_green() -> None:
    checks = {
        "A": {"severity": "green", "reason": "ok", "details": {}},
        "B": {"severity": "green", "reason": "ok", "details": {}},
    }
    result = base_health.aggregate_status(checks)
    assert result["overall_severity"] == "green"
    assert result["exit_code"] == 0


def test_aggregate_one_amber_overall_amber() -> None:
    checks = {
        "A": {"severity": "green", "reason": "ok", "details": {}},
        "B": {"severity": "amber", "reason": "warn", "details": {}},
    }
    result = base_health.aggregate_status(checks)
    assert result["overall_severity"] == "amber"
    assert result["exit_code"] == 0  # amber n'echoue pas


def test_aggregate_one_red_overall_red_exit_nonzero() -> None:
    """L'invariant central : un RED -> overall RED + exit non-zero.

    C'est le GATE DUR : un check rouge bloque le ship book-facing.
    """
    checks = {
        "A": {"severity": "green", "reason": "ok", "details": {}},
        "B": {"severity": "red", "reason": "FAIL", "details": {}},
        "C": {"severity": "amber", "reason": "warn", "details": {}},
    }
    result = base_health.aggregate_status(checks)
    assert result["overall_severity"] == "red"
    assert result["exit_code"] == 1


def test_aggregate_unknown_treated_as_failure() -> None:
    """unknown = exit non-zero (on ne sait pas, donc on bloque)."""
    checks = {
        "A": {"severity": "unknown", "reason": "db error", "details": {}},
    }
    result = base_health.aggregate_status(checks)
    assert result["overall_severity"] == "unknown"
    assert result["exit_code"] == 1


# === Test 2 : check_positions_verite ===


def test_positions_check_smoke_returns_dict(monkeypatch) -> None:
    """Smoke test : la fonction retourne un dict avec les cles attendues."""
    r = base_health.check_positions_verite()
    assert "severity" in r
    assert "reason" in r
    assert "details" in r
    assert r["severity"] in ("green", "amber", "red", "unknown")


# === Test 3 : check_integrity_chain ===


def test_integrity_check_smoke_returns_dict() -> None:
    """Smoke test sur la fonction reelle (chains DB courantes)."""
    r = base_health.check_integrity_chain()
    assert r["severity"] in ("green", "amber", "red", "unknown")
    # Si chain non-corrompue, severity doit etre green ou amber (red = corruption)
    if r["severity"] == "red":
        # Si red, la raison doit pointer vers integrity_anchors/ OU verify_chain
        assert (
            "OTS" in r["reason"] or "verify" in r["reason"] or "integrity_anchors" in r["reason"]
        )


# === Test 4 : check_freshness ===


def test_freshness_check_smoke_returns_dict() -> None:
    r = base_health.check_freshness()
    assert r["severity"] in ("green", "amber", "red", "unknown")
    assert "yfinance_violations" in r["details"] or r["severity"] in ("red", "unknown")


# === Test 5 : forbidden columns => RED ===


def test_positions_red_if_forbidden_column_present(monkeypatch) -> None:
    """Si la table positions a une colonne forbidden (eur_value, value_eur, etc.) -> RED."""
    from shared import storage

    class FakeCx:
        def execute(self, sql, *args):
            class _Result:
                def fetchall(self_inner):
                    # PRAGMA table_info(positions) -> cid, name, type, ...
                    return [(0, "id", "INTEGER", 0, None, 1),
                            (1, "ticker", "TEXT", 0, None, 0),
                            (2, "eur_value", "REAL", 0, None, 0)]  # forbidden !
                def fetchone(self_inner):
                    return (0,)
            return _Result()

    class FakeDb:
        def __enter__(self_inner):
            return FakeCx()
        def __exit__(self_inner, *args):
            return False

    monkeypatch.setattr(storage, "db", lambda: FakeDb())
    r = base_health.check_positions_verite()
    assert r["severity"] == "red"
    assert "eur_value" in str(r["details"].get("forbidden_cols", []))


# === Test 6 : exit code = property test ===


@pytest.mark.parametrize("worst,expected_exit", [
    ("green", 0),
    ("amber", 0),
    ("red", 1),
    ("unknown", 1),
])
def test_exit_code_matches_overall_severity(worst, expected_exit) -> None:
    checks = {"A": {"severity": worst, "reason": "", "details": {}}}
    result = base_health.aggregate_status(checks)
    assert result["exit_code"] == expected_exit
