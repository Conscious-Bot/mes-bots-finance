"""Phase C13 — Asymmetry-First Scoring.

Counter to "vend trop tôt winners" behavioral biais. For each active thesis +
position, compute asymmetry ratio = upside_to_target / |downside_to_stop| at
current price. Surface verdicts ranging STRONG RUN to FLIPPED.

Integrates with existing theses + positions tables. No new schema.
"""

import logging
from typing import Any

log = logging.getLogger(__name__)


def _get_current_price(ticker: str) -> float | None:
    """Latest close in EUR (user base currency, ADR 005 canonical storage).

    Delegates to shared.prices.get_current_price_in_eur which handles
    currency conversion for tickers quoted in JPY (.T), KRW (.KS), USD,
    etc. This ensures asymmetry MATH compares like-for-like with
    entry_price stored in EUR (broker avg_cost). DISPLAY layer
    converts EUR → USD via _fx_eur_to_usd() before showing values
    (post 21/05/2026 alignment with /portfolio and /brief which display USD).
    """
    try:
        from shared.prices import get_current_price_in_eur
        return get_current_price_in_eur(ticker)
    except Exception as e:
        log.warning(f"price fetch {ticker}: {e}")
        return None


def _fx_eur_to_usd() -> float:
    """Display-layer FX conversion EUR→USD. Used by format functions only,
    NOT by compute_thesis_asymmetry (which is pure-math in canonical EUR).

    Aligns /asymmetry display with /portfolio and /brief which both
    show values in USD. Fallback 1.1655 if get_fx_rate fails.
    """
    try:
        from shared.prices import get_fx_rate
        return get_fx_rate("EUR", "USD") or 1.1655
    except Exception:
        return 1.1655


def compute_thesis_asymmetry(thesis: dict[str, Any]) -> dict[str, Any] | None:
    """Compute asymmetry for a thesis dict. Returns dict with ratio + verdict + breakdown."""
    if not thesis:
        return None
    ticker = thesis.get("ticker")
    if not ticker:
        return None
    entry = thesis.get("entry_price")
    target_full = thesis.get("target_full") or thesis.get("target_price")
    target_partial = thesis.get("target_partial")
    stop = thesis.get("stop_price")
    direction = thesis.get("direction", "long")

    current = _get_current_price(ticker)
    if current is None:
        return {"ticker": ticker, "error": "price fetch failed"}

    # Long-direction asymmetry
    if direction != "long":
        return {"ticker": ticker, "note": f"asymmetry not computed for direction={direction}", "current_price": current}
    if not (entry and target_full and stop):
        # Compute actually-missing fields (was hardcoded template before 21/05)
        _missing = [n for n, v in (("entry", entry), ("target_full", target_full), ("stop", stop)) if not v]
        return {
            "ticker": ticker,
            "note": f"incomplete thesis (need {'+'.join(_missing)})",
            "current_price": current,
            "entry": entry,
            "target_full": target_full,
            "stop": stop,
        }

    # Edge cases
    if current <= stop:
        return {
            "ticker": ticker,
            "current_price": current,
            "entry": entry,
            "target_full": target_full,
            "target_partial": target_partial,
            "stop": stop,
            "asymmetry_ratio": 0.0,
            "verdict": "STOP_BREACHED",
            "note": f"current ${current:.2f} ≤ stop ${stop:.2f}",
            "upside_pct": (target_full - current) / current * 100,
            "downside_pct": 0.0,
        }
    if current >= target_full:
        return {
            "ticker": ticker,
            "current_price": current,
            "entry": entry,
            "target_full": target_full,
            "target_partial": target_partial,
            "stop": stop,
            "asymmetry_ratio": 999.0,
            "verdict": "TARGET_HIT",
            "note": f"current ${current:.2f} ≥ target ${target_full:.2f}",
            "upside_pct": 0.0,
            "downside_pct": (current - stop) / current * 100,
        }

    upside_pct = (target_full - current) / current * 100
    downside_pct = (current - stop) / current * 100
    if downside_pct <= 0.001:
        return {"ticker": ticker, "error": "degenerate (downside ~0)", "current_price": current}

    ratio = upside_pct / downside_pct

    if ratio > 3.0:
        verdict = "STRONG_RUN"
    elif ratio > 1.5:
        verdict = "FAVORABLE"
    elif ratio > 0.7:
        verdict = "BALANCED"
    elif ratio > 0.3:
        verdict = "UNFAVORABLE"
    else:
        verdict = "FLIPPED"

    return {
        "ticker": ticker,
        "current_price": current,
        "entry": entry,
        "target_full": target_full,
        "target_partial": target_partial,
        "stop": stop,
        "asymmetry_ratio": ratio,
        "verdict": verdict,
        "upside_pct": upside_pct,
        "downside_pct": downside_pct,
    }


def compute_portfolio_asymmetry() -> list[dict[str, Any]]:
    """Aggregate asymmetry across all active theses. Returns list of dicts sorted by ratio."""
    from shared import storage

    results = []
    try:
        # Get all active theses
        import sqlite3

        conn = sqlite3.connect(storage._DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM theses WHERE status='active'").fetchall()
        theses = [dict(r) for r in rows]
        conn.close()
    except Exception as e:
        log.warning(f"compute_portfolio_asymmetry fetch failed: {e}")
        return []

    for t in theses:
        r = compute_thesis_asymmetry(t)
        if r:
            r["thesis_id"] = t.get("id")
            results.append(r)
    return sorted(results, key=lambda x: -(x.get("asymmetry_ratio") or 0))


def format_asymmetry_single(r: dict[str, Any]) -> str:
    """Single-thesis asymmetry display. Converts EUR-canonical → USD at display.

    De-tautologized 2026-05-27 (mirrors format_portfolio_asymmetry, Day-5 lesson):
    auto-derived sentiment verdicts (STRONG_RUN/FAVORABLE/BALANCED/UNFAVORABLE/
    FLIPPED) removed — circular, computed from the user's own target/stop choices.
    Kept: raw distances, ratio (info-only), FACTUAL threshold events
    (STOP_BREACHED / TARGET_HIT) + external proximity flags (STOP NEAR / TARGET NEAR).
    """
    if not r:
        return "No data"
    if "error" in r:
        return f"{r.get('ticker', '?')}: ERROR {r['error']}"
    # Convert EUR-canonical compute output → USD for display (shallow copy, safe)
    fx = _fx_eur_to_usd()
    r = {**r}
    for k in ("current_price", "entry", "stop", "target_full", "target_partial"):
        if r.get(k) is not None:
            r[k] = r[k] * fx
    if "note" in r and "asymmetry_ratio" not in r:
        return f"{r.get('ticker', '?')} @ ${r.get('current_price', 0):.2f} — {r['note']}"

    verdict = r.get("verdict") or ""
    up_pct = r.get("upside_pct", 0)
    down_pct = r.get("downside_pct", 0)

    # Factual threshold events (real price crossings — NOT tautological). Kept.
    event = ""
    if verdict == "STOP_BREACHED":
        event = "  ⛔ STOP BREACHED"
    elif verdict == "TARGET_HIT":
        event = "  🎯 TARGET HIT"

    lines = [f"{r['ticker']} — Asymmetry{event}"]
    lines.append(
        f"Current: ${r['current_price']:.2f}  |  Entry: ${r['entry']:.2f}  |  Stop: ${r['stop']:.2f}  |  Target: ${r['target_full']:.2f}"
    )
    lines.append(f"Upside to target:  +{up_pct:.1f}%")
    lines.append(f"Downside to stop: -{down_pct:.1f}%")

    # External-signal proximity flags (mirror portfolio view); skip when already an event
    if not event:
        flags = []
        if down_pct < 10:
            flags.append("🔴 STOP NEAR")
        if up_pct < 10:
            flags.append("🎯 TARGET NEAR")
        if flags:
            lines.append("  ".join(flags))

    # Ratio = info-only, NO derived sentiment verdict (Day-5 anti-tautology)
    ratio = r.get("asymmetry_ratio")
    if ratio is not None and not event:
        lines.append(f"Ratio (up/down): {ratio:.2f}")
    return "\n".join(lines)


def format_portfolio_asymmetry(results: list[dict[str, Any]]) -> str:
    """Portfolio-wide display canonical (TG output spec 21/05/2026).

    Design rationale preserved from 2026-05-16 review:
    STRONG_RUN/FAVORABLE/BALANCED verdicts removed (tautological - derived
    from user's own target/stop choices at thesis logging time). Display
    keeps RAW distances + external-signal flags only (STOP NEAR, TARGET NEAR).

    Canonical applied 2026-05-21:
    - Header with emoji + em-dash + count summary
    - Section dividers ━ with count per group
    - Currency normalized USD (fixes pre-21/05 bug: stop raw EUR labeled €
      while current/entry/target USD-converted but also labeled €)
    - Sort COMPUTED by ratio desc (info-only, no color verdict on ratio)
    - Flags: 🔴 STOP NEAR (down_pct<10), 🎯 TARGET NEAR (up_pct<10)
      — external signal (price proximity to invalidation/capture)
    - WATCH compact horizontal list
    - Footer suggestion only if INCOMPLETE present
    """
    if not results:
        return "📊 PORTFOLIO ASYMMETRY — 0 active theses\nNo active theses."

    computed = []
    incomplete = []
    watch = []
    errored = []

    for r in results:
        if "error" in r:
            errored.append(r)
        elif "asymmetry_ratio" in r:
            computed.append(r)
        elif r.get("note", "").startswith("incomplete thesis"):
            incomplete.append(r)
        elif r.get("note", "").startswith("asymmetry not computed for direction"):
            watch.append(r)
        else:
            incomplete.append(r)

    total = len(results)
    lines = [f"📊 PORTFOLIO ASYMMETRY — {total} active theses"]
    parts = []
    if computed:
        parts.append(f"Computed: {len(computed)}")
    if incomplete:
        parts.append(f"Incomplete: {len(incomplete)}")
    if watch:
        parts.append(f"Watch: {len(watch)}")
    if errored:
        parts.append(f"Errors: {len(errored)}")
    if parts:
        lines.append(" | ".join(parts))
    lines.append("")

    # Section 1: COMPUTED — raw distances sorted by ratio desc
    if computed:
        lines.append(f"━ COMPUTED ({len(computed)}) — raw distances (sorted by ratio desc) ━")
        computed_sorted = sorted(computed, key=lambda x: -(x.get("asymmetry_ratio") or 0))
        _fx = _fx_eur_to_usd()
        for r in computed_sorted:
            ticker = r["ticker"]
            current = (r.get("current_price") or 0) * _fx
            entry = (r.get("entry") or 0) * _fx
            target = (r.get("target_full") or 0) * _fx
            stop = (r.get("stop") or 0) * _fx
            up_pct = r.get("upside_pct", 0)
            down_pct = r.get("downside_pct", 0)
            pnl_pct = ((current - entry) / entry * 100) if entry else 0

            flags = []
            if down_pct < 10:
                flags.append("🔴 STOP NEAR")
            if up_pct < 10:
                flags.append("🎯 TARGET NEAR")
            flags_str = ("  " + "  ".join(flags)) if flags else ""

            lines.append(
                f"{ticker:10s} cur=${current:>8.2f}  entry=${entry:>8.2f} ({pnl_pct:+.1f}%)  "
                f"target=${target:>8.2f} (+{up_pct:.0f}%)  stop=${stop:>8.2f} (-{down_pct:.0f}%){flags_str}"
            )
        lines.append("")

    if incomplete:
        lines.append(f"━ INCOMPLETE ({len(incomplete)}) — missing target/stop ━")
        for r in sorted(incomplete, key=lambda x: x.get("ticker", "")):
            missing = []
            if not r.get("entry"):
                missing.append("entry")
            if not r.get("target_full"):
                missing.append("target")
            if not r.get("stop"):
                missing.append("stop")
            missing_str = ", ".join(missing) if missing else "?"
            lines.append(f"{r['ticker']:10s} (missing: {missing_str})")
        lines.append("")

    if watch:
        lines.append(f"━ WATCH ({len(watch)}) — direction not long ━")
        tickers_str = "  ".join(sorted([r["ticker"] for r in watch]))
        lines.append(tickers_str)
        lines.append("")

    if errored:
        lines.append(f"━ ERRORS ({len(errored)}) ━")
        for r in sorted(errored, key=lambda x: x.get("ticker", "")):
            lines.append(f"{r['ticker']:10s}: {r.get('error', '?')}")
        lines.append("")

    if incomplete:
        lines.append("Fix INCOMPLETE via `/thesis set TICKER target X stop Y`")

    return "\n".join(lines).rstrip()


