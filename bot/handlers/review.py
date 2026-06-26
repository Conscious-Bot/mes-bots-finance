"""Handler `/review TICKER` : fact-sheet contextuel par ticker.

Output : 1 message Telegram structure agregating
  - Position courante (PnL + qty depuis avg_cost)
  - These (entry / partial / full / stop + asymmetry)
  - Sector + cycle phase (presage_taxonomy.yaml via shared/sectors façade)
  - Perf 1y / 2y du ticker + perf relative au sector index
  - Valorisation (P/E, P/S vs sector)
  - Modele agrege : top signaux 30j + impact moyen + sentiment dominant

Pattern : zero LLM call, pure data aggregation. Le LLM context ailleurs
benefice de ces datas (prompt injection downstream possible).

Cf [[niveau-2-adversary-and-proof]] move #2 : per-ticker tailor-made
contextualisation pour decisions trades.

Usage :
  /review NVDA
  /review CCJ
"""

from __future__ import annotations

import logging
import sqlite3

from shared import storage

log = logging.getLogger(__name__)

# 06/06 : refactor sur shared.sectors (source unique sectors.yaml).
from shared.sectors import sector_for_ticker as _find_sector_for_ticker


def _compute_returns(ticker: str, sector_index: str | None) -> dict:
    """Returns dict with t_1y, t_2y, idx_1y, idx_2y (in %). NaN si yfinance fail.

    Strategy : period="3y" interval="1d" pour avoir ~750 trading days, puis
    lookup ~252 (1y) et 504 (2y) trading days en arriere depuis current.
    Plus precis que interval='1mo' qui agrege par mois et peut donner des
    deltas mensuels au lieu de point-in-time.
    """
    # SOCLE S1c (#111) : migré yf.Ticker → prices.ensure_price_history gateway.
    import math
    from datetime import UTC, datetime, timedelta

    from shared.prices import ensure_price_history
    out = {}
    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=3 * 365)
    for symbol, prefix in [(ticker, "t"), (sector_index, "idx")]:
        if not symbol:
            continue
        try:
            hist = ensure_price_history(symbol, start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"))
            if hist is None or hist.empty:
                continue
            price_col = "price_native" if "price_native" in hist.columns else "Close"
            close = hist[price_col].dropna()
            n = len(close)
            if n < 30:
                continue
            current = float(close.iloc[-1])
            # 252 trading days ~ 1y, 504 ~ 2y
            if n >= 252:
                year_ago = float(close.iloc[-252])
                if year_ago > 0 and not math.isnan(year_ago):
                    out[f"{prefix}_1y"] = (current - year_ago) / year_ago * 100
            if n >= 504:
                two_year_ago = float(close.iloc[-504])
                if two_year_ago > 0 and not math.isnan(two_year_ago):
                    out[f"{prefix}_2y"] = (current - two_year_ago) / two_year_ago * 100
            elif n >= 252:
                # Fallback : 2y = older avail
                old = float(close.iloc[0])
                if old > 0 and not math.isnan(old):
                    out[f"{prefix}_2y"] = (current - old) / old * 100
        except Exception as e:
            log.debug(f"returns fetch {symbol}: {e}")
    return out


def _fetch_valuation(ticker: str) -> dict:
    """Returns dict with trailingPE, forwardPE, priceToSales, marketCap (or None)."""
    try:
        # SOCLE S1c (#111) : migré yf.Ticker.info → prices.get_info gateway (cache 1h).
        from shared.prices import get_info
        info = get_info(ticker)
        return {
            "trailingPE": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "priceToSales": info.get("priceToSalesTrailing12Months"),
            "marketCap": info.get("marketCap"),
        }
    except Exception as e:
        log.debug(f"valo fetch {ticker}: {e}")
        return {}


def _compute_model_sentiment(signals: list[dict]) -> dict:
    """Agregate impact + sentiment sur signaux recents. Returns dict."""
    if not signals:
        return {"n": 0, "impact_avg": None, "directional_lean": None}
    impacts = [s["impact_magnitude"] for s in signals if s.get("impact_magnitude") is not None]
    impact_avg = sum(impacts) / len(impacts) if impacts else None
    # Directional sentiment : extract from signal_type ou bullish/bearish indicators
    bullish_count = sum(1 for s in signals if "bull" in (s.get("sentiment") or "").lower())
    bearish_count = sum(1 for s in signals if "bear" in (s.get("sentiment") or "").lower())
    if bullish_count > bearish_count:
        lean = f"bullish ({bullish_count}/{len(signals)})"
    elif bearish_count > bullish_count:
        lean = f"bearish ({bearish_count}/{len(signals)})"
    else:
        lean = "neutral / mixed"
    return {
        "n": len(signals),
        "impact_avg": impact_avg,
        "directional_lean": lean,
    }


def _fmt_pct(v: float | None, sign: bool = True) -> str:
    if v is None:
        return "n/a"
    s = f"{v:+.1f}%" if sign else f"{v:.1f}%"
    return s


def _fmt_num(v: float | None, decimals: int = 2) -> str:
    if v is None:
        return "n/a"
    return f"{v:.{decimals}f}"


def _fmt_mcap(v: float | None) -> str:
    if not v:
        return "n/a"
    if v >= 1e12:
        return f"${v/1e12:.2f}T"
    if v >= 1e9:
        return f"${v/1e9:.1f}B"
    if v >= 1e6:
        return f"${v/1e6:.0f}M"
    return f"${v:.0f}"


def _render(
    ticker: str,
    sector: dict | None,
    position: dict | None,
    current_price: float | None,
    current_price_eur: float | None,
    thesis: dict | None,
    perf: dict,
    valo: dict,
    signals: list[dict],
    model: dict,
) -> str:
    """Render le message Telegram compact."""
    lines = []

    # Header
    sect_label = sector["label"] if sector else "uncategorized"
    cycle = sector["cycle_phase"] if sector else "?"
    lines.append(f"🔎 *{ticker}* · {sect_label} · cycle: *{cycle}*")
    lines.append("")

    # PnL : positions.avg_cost en EUR, on calcule PnL en EUR.
    if position and current_price_eur:
        avg = position.get("avg_cost") or 0
        qty = position.get("qty") or 0
        pnl_pct = ((current_price_eur - avg) / avg * 100) if avg > 0 else None
        lines.append(f"PnL : {_fmt_pct(pnl_pct)} (avg {_fmt_num(avg)}€ · current {_fmt_num(current_price_eur)}€ · qty {_fmt_num(qty)})")
    elif position:
        lines.append(f"Position : qty {_fmt_num(position.get('qty'))} avg {_fmt_num(position.get('avg_cost'))} (no current price)")
    else:
        lines.append("Position : aucune ouverte")

    # Perf vs sector
    t1y = perf.get("t_1y")
    idx1y = perf.get("idx_1y")
    t2y = perf.get("t_2y")
    idx2y = perf.get("idx_2y")
    idx_name = sector["index"] if sector else "(no index)"
    if t1y is not None:
        rel1 = (t1y - idx1y) if idx1y is not None else None
        lines.append(f"Perf 1y : {_fmt_pct(t1y)}" + (f"  ·  vs {idx_name} {_fmt_pct(idx1y)}  →  {_fmt_pct(rel1)}" if rel1 is not None else ""))
    if t2y is not None:
        rel2 = (t2y - idx2y) if idx2y is not None else None
        lines.append(f"Perf 2y : {_fmt_pct(t2y)}" + (f"  ·  vs {idx_name} {_fmt_pct(idx2y)}  →  {_fmt_pct(rel2)}" if rel2 is not None else ""))

    # Valo
    valo_parts = []
    if valo.get("trailingPE"):
        valo_parts.append(f"P/E {_fmt_num(valo['trailingPE'], 1)}")
    if valo.get("forwardPE"):
        valo_parts.append(f"fwd {_fmt_num(valo['forwardPE'], 1)}")
    if valo.get("priceToSales"):
        valo_parts.append(f"P/S {_fmt_num(valo['priceToSales'], 1)}")
    if valo.get("marketCap"):
        valo_parts.append(_fmt_mcap(valo["marketCap"]))
    if valo_parts:
        lines.append(f"Valo : {' · '.join(valo_parts)}")

    lines.append("")

    # Thèse cibles
    if thesis:
        entry = thesis.get("entry_price")
        stop = thesis.get("stop_price")
        partial = thesis.get("target_partial")
        full = thesis.get("target_full") or thesis.get("target_price")
        targets = []
        if entry:
            targets.append(f"entry {_fmt_num(entry)}")
        if stop and entry:
            stop_pct = (stop - entry) / entry * 100
            targets.append(f"stop {_fmt_num(stop)} ({stop_pct:+.0f}%)")
        if partial and entry:
            p_pct = (partial - entry) / entry * 100
            targets.append(f"partial {_fmt_num(partial)} ({p_pct:+.0f}%)")
        if full and entry:
            f_pct = (full - entry) / entry * 100
            targets.append(f"full {_fmt_num(full)} ({f_pct:+.0f}%)")
        if targets:
            lines.append("Cibles : " + " · ".join(targets))

        # Asymmetry actuelle si tous les params
        if current_price and entry and stop and full:
            upside = (full - current_price) / current_price
            downside = (current_price - stop) / current_price
            if downside > 0:
                asym = upside / downside
                lines.append(f"Asymmetry actuelle : {_fmt_num(asym, 2)}")
        lines.append("")

    # Modèle
    if model["n"] > 0:
        lines.append(f"Modèle : {model['n']} signaux 30j · impact moy {_fmt_num(model['impact_avg'], 1)} · {model['directional_lean']}")
        # Top 3 signaux
        for s in signals[:3]:
            ts_short = (s.get("timestamp") or "")[5:10]  # MM-DD
            src = (s.get("source_name") or "?")[:25]
            title = (s.get("title") or "")[:65]
            impact = s.get("impact_magnitude")
            impact_s = f"i{int(impact)}" if impact else "—"
            lines.append(f"  · {ts_short} [{src}] {impact_s} {title}")
    else:
        lines.append("Modèle : 0 signal 30j sur ce ticker")
    lines.append("")

    # Cycle context (justify le cycle phase)
    if sector and sector.get("cycle_note"):
        lines.append(f"_{sector['cycle_note']}_")

    return "\n".join(lines)


async def cmd_review(update, ctx):  # noqa: ARG001
    """Surface fact-sheet contextuel par ticker."""
    parts = update.message.text.split()[1:]
    if not parts:
        await update.message.reply_text(
            "Usage: `/review TICKER`\n\n"
            "Exemple: `/review NVDA`",
            parse_mode="Markdown",
        )
        return
    ticker = parts[0].upper()
    await update.message.reply_text(f"🔍 Loading {ticker} review...")

    # Lookup contexte
    sector = _find_sector_for_ticker(ticker)

    # Data fetches en parallel concept (synchrones ici mais isoles errors)
    conn = sqlite3.connect(storage.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        position = storage.get_position_by_ticker(ticker)
        thesis = storage.get_thesis_by_ticker(ticker)
        signals = storage.get_signals_for_ticker(ticker, days=30, limit=8)
    finally:
        conn.close()

    from shared.prices import get_current_price, get_current_price_in_eur
    current_price = get_current_price(ticker)
    # positions.avg_cost stocke en EUR (convention historique), pas en
    # native currency. Pour le PnL calc, on convertit current price en EUR.
    # Theses entry/target/stop restent en native (doctrine currency-native-invariant).
    current_price_eur = get_current_price_in_eur(ticker)

    perf = _compute_returns(ticker, sector["index"] if sector else None)
    valo = _fetch_valuation(ticker)
    model = _compute_model_sentiment(signals)

    msg = _render(ticker, sector, position, current_price, current_price_eur, thesis, perf, valo, signals, model)

    # Telegram limit
    if len(msg) > 3900:
        msg = msg[:3850] + "\n…[truncated]"

    await update.message.reply_text(msg, parse_mode="Markdown")
