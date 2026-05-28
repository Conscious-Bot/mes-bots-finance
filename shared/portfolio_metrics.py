"""Portfolio-level metrics for KPI #6 monitoring.

KPI #6: TWR vs SPY/QQQ 12M, target >-5pp underperformance.

Currency: portfolio is EUR-denominated. Entry value extracted from
`eur_invested=N` tag in position notes (canonical, injected by cmd_position_buy
upstream Day 9 H2 fix). Fallback for positions without tag: qty * avg_cost
* fx(native_currency, EUR) via shared.prices canonical helpers
(get_currency_for_ticker + get_fx_rate). Benchmark fetched USD via yfinance,
converted to EUR-equivalent via EURUSD=X spot at window endpoints. FX
adjustment is non-negligible on windows >30d (EUR/USD typically moves
5-10% per year).

Time/timezone convention (per CONVENTIONS Section 1):
- positions.opened_at stored as UTC ISO 8601 (CURRENT_TIMESTAMP default)
- Legacy bulk imports may store naive datetime; treated as UTC with warning
- Defer formal TZ migration to PIT bitemporal ADR 001 implementation

Math (EUR investor in USD asset):
    eur_start = usd_start / EURUSD_start
    eur_end   = usd_end   / EURUSD_end
    return    = eur_end / eur_start - 1

Status logic:
- INSUFFICIENT if portfolio_age < 365d (KPI #6 spec demands 12M window)
- INSUFFICIENT_BENCHMARK if yfinance fetch fails for SPY/QQQ/EURUSD
- GREEN if delta vs SPY AND delta vs QQQ > -5pp
- YELLOW if delta vs ONE benchmark < -5pp
- RED if delta vs BOTH benchmarks < -5pp

Entry value extraction:
- Canonical: parse `eur_invested=N` from position notes (legacy import format)
- Fallback: qty * avg_cost (may be incorrect currency for non-EUR-stored
  positions; caveat logged)
"""

import logging
import re
from datetime import UTC, datetime
from typing import Any

import yfinance as yf

from shared.positions import list_positions
from shared.prices import get_current_price_in, get_fx_rate

log = logging.getLogger(__name__)

_EUR_INVESTED_RE = re.compile(r"eur_invested=(\d+(?:\.\d+)?)")


_BENCHMARKS: tuple[str, ...] = ("SPY", "QQQ", "SMH")


def parse_eur_invested(notes: str | None) -> float | None:
    """Extract `eur_invested=N` value from position notes string.

    Returns float if tag present and parseable, None otherwise.
    Caller handles fallback to qty * avg_cost.
    """
    if not notes:
        return None
    m = _EUR_INVESTED_RE.search(notes)
    if m is None:
        return None
    try:
        return float(m.group(1))
    except ValueError, TypeError:
        return None


def compute_portfolio_return(target_cur: str = "USD") -> dict[str, Any] | None:
    """Aggregate cumulative return on open portfolio, in ``target_cur``.

    Day 11 ADR 004: parametric core supporting USD (canonical/primary) and
    EUR (legacy/secondary).

    Math note: EUR-stored entry values from notes are converted to target_cur
    via CURRENT fx rate (historical fx at acquisition unknown for legacy
    positions). Acceptable for KPI #6 vs USD benchmarks at current fx
    (apples-to-apples). For strict EUR-investor experience, use _eur wrapper.

    Returns None if no priceable positions or total_entry <= 0.
    """
    positions = list_positions(status="open")
    if not positions:
        return None

    total_entry = 0.0
    total_current = 0.0
    positions_priced = 0
    earliest_opened: str | None = None

    fx_eur_to_target = 1.0 if target_cur == "EUR" else get_fx_rate("EUR", target_cur)
    if fx_eur_to_target is None:
        log.warning(f"compute_portfolio_return: no fx EUR->{target_cur}")
        return None

    for p in positions:
        ticker = p["ticker"]
        cur_price = get_current_price_in(ticker, target_cur)
        if cur_price is None:
            log.debug(f"kpi6: skipping {ticker} (no live {target_cur} price)")
            continue

        eur_inv = parse_eur_invested(p.get("notes"))
        if eur_inv is None:
            qty = float(p.get("qty", 0) or 0)
            avg_cost_eur = float(p.get("avg_cost", 0) or 0)
            # Day 13 ADR 005: avg_cost EUR canonical, no native conversion needed.
            eur_inv = qty * avg_cost_eur
            log.warning(
                f"kpi6: {ticker} missing eur_invested tag, fallback qty*avg_cost (EUR canonical) = {eur_inv:.2f}"
            )

        total_entry += eur_inv * fx_eur_to_target
        total_current += float(p["qty"]) * cur_price
        positions_priced += 1

        opened = p.get("opened_at")
        if opened and (earliest_opened is None or opened < earliest_opened):
            earliest_opened = opened

    if total_entry <= 0 or positions_priced == 0:
        return None

    days = 0.0
    if earliest_opened:
        try:
            opened_dt = datetime.fromisoformat(earliest_opened)
            if opened_dt.tzinfo is None:
                log.warning(
                    f"kpi6: naive opened_at {earliest_opened!r}, treating as UTC "
                    f"(CONVENTIONS Section 1); legacy imports may be off by TZ"
                )
                opened_dt = opened_dt.replace(tzinfo=UTC)
            days = (datetime.now(UTC) - opened_dt).total_seconds() / 86400
        except (ValueError, TypeError) as e:
            log.warning(f"kpi6: cannot parse opened_at {earliest_opened!r}: {e}")

    return_pct = (total_current / total_entry - 1) * 100

    return {
        "total_entry": total_entry,
        "total_current": total_current,
        "currency": target_cur,
        "return_pct": return_pct,
        "earliest_opened": earliest_opened,
        "days": days,
        "positions_total": len(positions),
        "positions_priced": positions_priced,
    }


def compute_portfolio_return_usd() -> dict[str, Any] | None:
    """Primary: USD canonical (Day 11 ADR 004)."""
    return compute_portfolio_return("USD")


def compute_portfolio_return_eur() -> dict[str, Any] | None:
    """Legacy/secondary: EUR. Backward compat wrapper with EUR-suffixed key aliases."""
    result = compute_portfolio_return("EUR")
    if result is None:
        return None
    result["total_entry_eur"] = result["total_entry"]
    result["total_current_eur"] = result["total_current"]
    return result


def fetch_benchmark_return(ticker: str, days: int, target_cur: str = "USD") -> float | None:
    """Fetch ticker return over window in ``target_cur``.

    Day 11 ADR 004: parametric core. USD returns native (no fx noise).
    EUR returns fx-adjusted via EURUSD=X spot at window endpoints
    (preserves Day 7 EUR-investor algorithm).
    """
    try:
        period_days = max(days + 5, 7)
        h = yf.Ticker(ticker).history(period=f"{period_days}d")
        if h.empty or len(h) < 2:
            log.warning(f"kpi6: {ticker} yfinance empty/short ({len(h)} rows)")
            return None
        usd_start = float(h["Close"].iloc[0])
        usd_end = float(h["Close"].iloc[-1])
        if usd_start <= 0:
            return None

        if target_cur == "USD":
            return (usd_end / usd_start - 1) * 100

        if target_cur == "EUR":
            fx_h = yf.Ticker("EURUSD=X").history(period=f"{period_days}d")
            if fx_h.empty or len(fx_h) < 2:
                log.warning(f"kpi6: EURUSD=X yfinance empty/short ({len(fx_h)} rows)")
                return None
            fx_start = float(fx_h["Close"].iloc[0])
            fx_end = float(fx_h["Close"].iloc[-1])
            if fx_start <= 0:
                return None
            eur_start = usd_start / fx_start
            eur_end = usd_end / fx_end
            return (eur_end / eur_start - 1) * 100

        fx = get_fx_rate("USD", target_cur)
        if fx is None:
            return None
        return (usd_end / usd_start - 1) * 100
    except Exception as e:
        log.warning(f"kpi6: benchmark {ticker} fetch failed: {e}")
        return None


def fetch_benchmark_return_usd(ticker: str, days: int) -> float | None:
    """Primary: native USD return (Day 11 ADR 004, no fx conversion)."""
    return fetch_benchmark_return(ticker, days, "USD")


def fetch_benchmark_return_eur(ticker: str, days: int) -> float | None:
    """Legacy: EUR-adjusted via EURUSD=X spot (Day 7 algorithm preserved)."""
    return fetch_benchmark_return(ticker, days, "EUR")


def compute_kpi6() -> dict[str, Any]:
    """KPI #6 orchestrator for /kpi_status producer.

    Compares portfolio return (EUR) to 3 benchmarks: SPY (broad US),
    QQQ (Nasdaq-100 tech), SMH (VanEck Semiconductor — most relevant to
    AI/semis-tilted portfolio).

    Status:
    - GREEN: 0 benchmarks underperformed >-5pp
    - YELLOW: 1 of 3 benchmarks underperformed >-5pp
    - RED: >=2 of 3 benchmarks underperformed >-5pp

    Output schema matches existing KPI dicts in observability.py:
    {title, target, current, status, enforcement}.
    """
    title = f"KPI #6: Portfolio return vs {'/'.join(_BENCHMARKS)} (USD)"
    target = "12M delta vs majority benchmarks > -5pp"
    enforcement = "Revue strat trimestrielle si majority <-5pp"

    pf = compute_portfolio_return_usd()
    if pf is None:
        return {
            "title": title,
            "target": target,
            "current": "no open positions or no live prices",
            "status": "🔍 INSUFFICIENT — no portfolio data",
            "enforcement": enforcement,
        }

    days = int(pf["days"])
    pf_ret = pf["return_pct"]
    window_days = max(days, 1)

    bench_data: dict[str, float] = {}
    for tk in _BENCHMARKS:
        ret = fetch_benchmark_return_usd(tk, window_days)
        if ret is None:
            return {
                "title": title,
                "target": target,
                "current": (
                    f"Pf {pf_ret:+.2f}% over {days}d ({pf['positions_priced']}/{pf['positions_total']} priced)"
                ),
                "status": f"🔍 INSUFFICIENT_BENCHMARK — yfinance fetch failed for {tk}",
                "enforcement": enforcement,
            }
        bench_data[tk] = ret

    deltas: dict[str, float] = {tk: pf_ret - r for tk, r in bench_data.items()}
    breaches = [tk for tk, d in deltas.items() if d < -5]
    n_breach = len(breaches)
    n_total = len(_BENCHMARKS)

    bench_str = " | ".join(f"{tk}-usd {bench_data[tk]:+.2f}% (Δ {deltas[tk]:+.1f}pp)" for tk in _BENCHMARKS)
    value_str = f"Pf {pf_ret:+.2f}% | {bench_str} | {days}d ({pf['positions_priced']}/{pf['positions_total']} priced)"

    if days < 365:
        status = f"🔍 INSUFFICIENT — need 365d, have {days}d (provisional)"
    elif n_breach >= 2:
        status = f"🚨 RED — underperforming {n_breach}/{n_total} benchmarks <-5pp ({', '.join(breaches)})"
    elif n_breach == 1:
        status = f"⚠️ YELLOW — underperforming {breaches[0]} <-5pp"
    else:
        status = f"✅ GREEN — delta all {n_total} benchmarks > -5pp"

    return {
        "title": title,
        "target": target,
        "current": value_str,
        "status": status,
        "enforcement": enforcement,
    }
