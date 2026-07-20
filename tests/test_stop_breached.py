"""Stop FRANCHI ≠ stop proche (cure 20/07 — cas fondateur SK Hynix / baisse KOSPI).

Un trailing stop franchi à la baisse sur un WINNER (+16% vs entrée thèse,
stop 2.2M ₩, prix 1.76M) n'a levé AUCUNE alerte : le filtre « winner au trailing
proche = sécurisation » de is_near_stop masquait aussi le FRANCHISSEMENT.
is_stop_breached = distance <= 0, JAMAIS filtré par le PnL.
"""

from __future__ import annotations

import dashboard.render as r
from shared.portfolio_analytics import is_near_stop, is_stop_breached

# ---------- le prédicat ----------


def test_sk_hynix_founding_case():
    """downside −24.7%, winner +16.6% : breached=True, near_stop=False (winner
    filter inchangé — les deux prédicats répondent à des questions différentes)."""
    assert is_stop_breached(-24.7) is True
    assert is_near_stop(-24.7, +16.6) is False


def test_breach_ignores_pnl_sign():
    """Franchi = franchi, winner ou perdante (le prédicat ne voit pas le PnL)."""
    assert is_stop_breached(-1.0) is True


def test_approaching_is_not_breached():
    assert is_stop_breached(3.4) is False   # proche (CCJ) mais pas franchi
    assert is_stop_breached(0.001) is False


def test_exactly_on_stop_is_breached():
    assert is_stop_breached(0.0) is True


def test_missing_data_fail_closed():
    assert is_stop_breached(None) is False


# ---------- surfaces ----------


def _mon_empty():
    return {
        "over_cap": {"over_tickers": []},
        "stress_gate": {"worst_scenario": None, "breached_scenarios": []},
        "kill_criteria": {"triggered_tickers": [], "at_risk_tickers": []},
        "stale_target": {"dead_tickers": [], "dying_tickers": []},
    }


def test_needs_today_surfaces_winner_breach(monkeypatch):
    """LE trou fermé : un winner sous son stop apparaît en tête de file
    Needs-you (sev 0), avec son PnL et le geste."""
    import intelligence.digue_monitor as _dm
    import intelligence.monitors_summary as _ms

    monkeypatch.setattr(r, "_cluster_health", lambda *a, **k: [])
    monkeypatch.setattr(_dm, "current_digue_state", lambda: {"frozen": False})
    monkeypatch.setattr(_ms, "get_monitors_summary", _mon_empty)
    computed = [{"ticker": "000660.KS", "downside_pct": -24.7, "upside_pct": 70.0}]
    pnl = {"000660.KS": +16.6}
    html = r._needs_today([], pnl, [], computed, {"000660.KS": "SK Hynix"})
    assert "STOP FRANCHI" in html
    assert "+17% on cost" in html or "+16" in html  # le PnL est DIT (winner assumé)
    assert "card-000660.KS" in html  # geste : nav vers la card


def test_needs_today_no_breach_no_item(monkeypatch):
    import intelligence.digue_monitor as _dm
    import intelligence.monitors_summary as _ms

    monkeypatch.setattr(r, "_cluster_health", lambda *a, **k: [])
    monkeypatch.setattr(_dm, "current_digue_state", lambda: {"frozen": False})
    monkeypatch.setattr(_ms, "get_monitors_summary", _mon_empty)
    computed = [{"ticker": "TSM", "downside_pct": 12.0, "upside_pct": 20.0}]
    html = r._needs_today([], {"TSM": 5.0}, [], computed, {})
    assert "STOP FRANCHI" not in html


def test_band_chip_shows_breach():
    """La bande monitors affiche la chip « stop franchi » depuis le paramètre."""
    band = r._monitors_live_band(stop_breached=[("000660.KS", -24.7)])
    assert "stop franchi" in band
    assert "000660.KS" in band


def test_wiring_no_pnl_filter_on_breach():
    """Anti-résurrection : le chemin breach ne doit JAMAIS re-filtrer par PnL.
    Le PnL est affiché (ternaire de signe OK) mais aucun skip n'en dépend :
    le seul `continue` du bloc est le guard is_stop_breached/ticker."""
    from pathlib import Path

    src = Path("dashboard/render.py").read_text()
    block = src.split("Stop FRANCHI (breach)")[1].split("=== Stop margin critical")[0]
    assert "is_stop_breached" in block
    assert block.count("continue") == 1, "un skip supplémentaire est apparu dans le bloc breach"
    assert any("not _isb" in ln for ln in block.splitlines()), "le guard canonique a changé"
    assert not any("_pnl_b" in ln and "continue" in ln for ln in block.splitlines()), (
        "un continue conditionné au PnL a été introduit — le breach redevient filtrable"
    )
