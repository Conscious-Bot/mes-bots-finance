"""Transition BUILD → OPERATE déclarative (étape 3 Path B, cure 04/07).

Ferme le seuil ORAL (≥65k en memory) qui laissait « phase construction » servir
d'excuse infinie (antipattern gravé memory 26/06). rule=first_of : capital OU
date. Le monitor over_cap s'auto-active à OPERATE au lieu d'une décision orale.
"""

from __future__ import annotations

from datetime import date

from shared.portfolio_rules import load_portfolio_rules, operate_state


def test_yaml_still_validates_with_operate_block():
    """extra:forbid — le nouveau bloc DOIT être au schéma, sinon load renvoie
    None et TOUTES les règles tombent (garde-fou de régression)."""
    cfg = load_portfolio_rules()
    assert cfg is not None, "portfolio_rules.yaml ne valide plus (schéma incomplet ?)"
    assert "operate_transition" in cfg
    ot = cfg["operate_transition"]
    assert ot["rule"] in ("first_of", "all_of")
    assert ot["book_eur"] > 0


def test_build_phase_below_threshold_before_date():
    s = operate_state(book_eur=55000, today=date(2026, 7, 4))
    assert s["available"] is True
    assert s["phase"] == "BUILD"
    assert s["met_by"] is None
    assert s["book_gap_eur"] == 10000  # 65000 - 55000
    assert s["days_to_date"] > 0


def test_operate_by_capital():
    s = operate_state(book_eur=66000, today=date(2026, 7, 4))
    assert s["phase"] == "OPERATE"
    assert s["met_by"] == "capital"


def test_operate_by_date_first_of():
    """first_of : la date butoir déclenche OPERATE même book sous le seuil —
    c'est CE qui tue l'excuse infinie (BUILD ne peut pas durer indéfiniment)."""
    s = operate_state(book_eur=55000, today=date(2026, 10, 1))
    assert s["phase"] == "OPERATE"
    assert s["met_by"] == "date"


def test_capital_boundary_strict_at_threshold():
    """Book == seuil exact → OPERATE (>=)."""
    s = operate_state(book_eur=65000, today=date(2026, 7, 4))
    assert s["phase"] == "OPERATE" and s["met_by"] == "capital"


def test_book_unavailable_fail_safe(monkeypatch):
    """Book vraiment indisponible (calcul planté) + avant date → BUILD, pas de
    faux OPERATE fabriqué (fail-safe : cap non atteignable sans book)."""
    import shared.book as _bk

    def _boom():
        raise RuntimeError("book indisponible (simulé)")

    monkeypatch.setattr(_bk, "get_held_lines", _boom)
    s = operate_state(book_eur=None, today=date(2026, 7, 4))
    assert s["phase"] == "BUILD"
    assert s["book_eur"] is None
    # mais la date butoir déclenche OPERATE même sans book (first_of)
    s2 = operate_state(book_eur=None, today=date(2026, 10, 1))
    assert s2["phase"] == "OPERATE" and s2["met_by"] == "date"


def test_over_cap_notify_gated_on_operate_phase():
    """Le monitor over_cap ne notifie qu'en OPERATE (dark déclaratif, plus oral).
    Source-read : le gate operate_state est bien câblé sur le notify."""
    from pathlib import Path

    src = Path("intelligence/over_cap_monitor.py").read_text()
    assert "from shared.portfolio_rules import operate_state" in src
    assert 'if _operate:' in src
    # le journal d'audit reste inconditionnel (observabilité préservée)
    assert "notify différé" in src
