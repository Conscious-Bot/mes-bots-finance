"""File décisionnelle unifiée « Needs you today » (#19, cure 04/07).

L'audit : le système CONNAÎT ~9 actions dues (digue, kill_criteria, stress gate,
over_cap, thèses mourantes, cibles atteintes) mais Needs-you n'en montrait que 2.
Ce test verrouille l'agrégation multi-sources + tri par sévérité + dédup.
Source-read pour le HTML + appel direct avec mocks (pas de DB).
"""

from __future__ import annotations

import dashboard.render as r


def _run(monkeypatch, *, digue=None, monitors=None, computed=None):
    monkeypatch.setattr(
        r, "_cluster_health", lambda *a, **k: []
    )  # pas de cluster breach pour isoler
    if digue is not None:
        import intelligence.digue_monitor as _dm
        monkeypatch.setattr(_dm, "current_digue_state", lambda: digue)
    if monitors is not None:
        import intelligence.monitors_summary as _ms
        monkeypatch.setattr(_ms, "get_monitors_summary", lambda: monitors)
    names = {"TSM": "TSMC", "CCJ": "Cameco", "MP": "MP Materials"}
    return r._needs_today([], {}, [], computed or [], names)


_EMPTY_MON = {
    "over_cap": {"over_tickers": []},
    "stress_gate": {"worst_scenario": None, "breached_scenarios": []},
    "kill_criteria": {"triggered_tickers": [], "at_risk_tickers": []},
    "stale_target": {"dead_tickers": [], "dying_tickers": []},
}


def test_all_clear_when_no_signal(monkeypatch):
    html = _run(monkeypatch, digue={"frozen": False}, monitors=_EMPTY_MON)
    assert "All clear" in html
    assert "0 items" in html


def test_digue_gel_is_top_of_queue(monkeypatch):
    digue = {"frozen": True, "status": "gel_15", "drawdown_pct": -16.2}
    html = _run(monkeypatch, digue=digue, monitors=_EMPTY_MON)
    assert "GELÉ" in html
    assert "-16.2%" in html


def test_aggregates_all_sources(monkeypatch):
    mon = {
        "over_cap": {"over_tickers": [{"ticker": "MP"}]},
        "stress_gate": {"worst_scenario": {"name": "capex_pause"}, "breached_scenarios": ["capex_pause"]},
        "kill_criteria": {"triggered_tickers": ["TSM"], "at_risk_tickers": ["CCJ"]},
        "stale_target": {"dead_tickers": ["MP"], "dying_tickers": []},
    }
    html = _run(monkeypatch, digue={"frozen": False}, monitors=mon)
    # les sources distinctes apparaissent
    assert "kill-criteria FIRING" in html
    assert "Stress gate franchi" in html
    assert "over cap" in html
    assert "thèse morte" in html
    # le compteur reflète l'agrégation (>2 = l'ancienne limite dépassée)
    import re
    m = re.search(r"(\d+) item", html)
    assert m and int(m.group(1)) >= 4


def test_sorted_by_severity(monkeypatch):
    """Critique (kill FIRING, sev 0) doit précéder moyen (at_risk, sev 2) dans le HTML."""
    mon = {
        "over_cap": {"over_tickers": []},
        "stress_gate": {"worst_scenario": None, "breached_scenarios": []},
        "kill_criteria": {"triggered_tickers": ["TSM"], "at_risk_tickers": ["CCJ"]},
        "stale_target": {"dead_tickers": [], "dying_tickers": []},
    }
    html = _run(monkeypatch, digue={"frozen": False}, monitors=mon)
    assert html.index("FIRING") < html.index("at risk"), "sévérité pas triée : critique doit précéder moyen"


def test_target_hit_review_due(monkeypatch):
    computed = [{"ticker": "CCJ", "upside_pct": -1.8}]  # prix au-dessus de la cible
    html = _run(monkeypatch, digue={"frozen": False}, monitors=_EMPTY_MON, computed=computed)
    assert "cible atteinte" in html
    assert "revue due" in html


def test_dedup_same_ticker_keeps_most_severe(monkeypatch):
    """Un ticker sur 2 canaux (kill FIRING sev0 + at_risk sev2) → 1 seule carte, la + sévère."""
    mon = {
        "over_cap": {"over_tickers": []},
        "stress_gate": {"worst_scenario": None, "breached_scenarios": []},
        "kill_criteria": {"triggered_tickers": ["TSM"], "at_risk_tickers": ["TSM"]},
        "stale_target": {"dead_tickers": [], "dying_tickers": []},
    }
    html = _run(monkeypatch, digue={"frozen": False}, monitors=mon)
    assert html.count("card-TSM") == 1  # dédupliqué
    assert "FIRING" in html and "at risk" not in html  # la sévère gardée
