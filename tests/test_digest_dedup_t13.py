"""Tests dedup catalysts + garde T13 (fixes digest 29/07 soir).

Bug 1 : doublons catalysts (META 29+30/07, AMD 04+05/08...) — le refresh
quotidien insere une nouvelle row quand l'API deplace une date d'earnings,
l'ancienne survit (UNIQUE ... ON CONFLICT IGNORE). Dedup par (ticker,
event_type), derniere estimation gagne.

Bug 2 : le digest emettait des ORDRES de trade ("reduire 20-25% aujourd'hui")
— violation T13/L9. Garde = prompt durci + filet mecanique post-rendu.
"""
from __future__ import annotations

from intelligence.digest import _dedup_ticker_events, _t13_guard

# ─── _dedup_ticker_events ────────────────────────────────────────────────────


def _ev(date: str, ticker: str | None, created: str, etype: str = "earnings") -> dict:
    return {
        "date": date, "ticker": ticker, "event_type": etype,
        "description": f"{ticker or 'MACRO'} {etype}", "created_at": created,
    }


def test_dedup_keeps_latest_estimate_per_ticker():
    """META estime 30/07 (vieux refresh) puis 29/07 (refresh recent) ->
    seule l'estimation la plus recente survit."""
    raw = [
        _ev("2026-07-30", "META", "2026-07-25 06:00:00"),
        _ev("2026-07-29", "META", "2026-07-28 06:00:00"),
    ]
    out = _dedup_ticker_events(raw)
    assert len(out) == 1
    assert out[0]["date"] == "2026-07-29"


def test_dedup_tie_on_created_at_keeps_earliest_date():
    raw = [
        _ev("2026-08-05", "AMD", "2026-07-28 06:00:00"),
        _ev("2026-08-04", "AMD", "2026-07-28 06:00:00"),
    ]
    out = _dedup_ticker_events(raw)
    assert len(out) == 1
    assert out[0]["date"] == "2026-08-04"


def test_dedup_macro_events_never_deduped():
    """FOMC + NFP + CPI = dates distinctes, events distincts — pas de dedup."""
    raw = [
        _ev("2026-07-29", "MACRO", "2026-07-28", etype="fomc"),
        _ev("2026-08-07", None, "2026-07-28", etype="nfp"),
        _ev("2026-08-12", "MACRO", "2026-07-28", etype="cpi"),
    ]
    assert len(_dedup_ticker_events(raw)) == 3


def test_dedup_distinct_tickers_untouched_and_sorted():
    raw = [
        _ev("2026-08-06", "CEG", "2026-07-28"),
        _ev("2026-07-30", "AMZN", "2026-07-28"),
    ]
    out = _dedup_ticker_events(raw)
    assert [r["ticker"] for r in out] == ["AMZN", "CEG"]  # trie par date


# ─── _t13_guard ──────────────────────────────────────────────────────────────


def test_t13_flags_trade_imperatives():
    """Les formulations du digest fautif du 29/07 doivent etre flaggees."""
    for bad in (
        "GOOGL — Poser un stop ou reduire 20-25% aujourd'hui",
        "signal composite : sortir une partie sur le rebond",
        "MU : vendre avant la guidance",
        "TSM : renforcer sur faiblesse",
    ):
        out = _t13_guard(bad)
        assert "GARDE T13" in out, f"non flagge: {bad!r}"
        assert bad in out  # jamais de censure silencieuse — texte preserve


def test_t13_clean_factual_text_not_flagged():
    """Du factuel avec vocabulaire proche (insiders ont vendu, la vente,
    sortie du capital) ne doit PAS false-positive."""
    clean = (
        "AVGO : les insiders ont vendu massivement (-195M$) [#1425]. "
        "La vente nette institutionnelle touche le kill-criterion. "
        "KOSPI -11%, pattern de sortie de capitaux etrangers. "
        "-> a passer dans le framework (Q1 these / Q2 poids)."
    )
    out = _t13_guard(clean)
    assert "GARDE T13" not in out
    assert out == clean
