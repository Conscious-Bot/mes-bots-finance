"""
Company analysis fiche generator.
Stocks: prices gateway (info+fundamentals) + EDGAR insiders + regime → LLM synthesis (Claude)
Crypto (BTC-USD etc): partial — price + macro, LLM adapts
"""

import contextlib
import logging
from datetime import UTC, date, datetime

from shared import edgar
from shared.storage import build_signals_context_block, db

log = logging.getLogger(__name__)


def _fmt_money(v):
    if v is None:
        return "n/a"
    av = abs(v)
    if av >= 1e12:
        return f"${v / 1e12:.2f}T"
    if av >= 1e9:
        return f"${v / 1e9:.2f}B"
    if av >= 1e6:
        return f"${v / 1e6:.1f}M"
    if av >= 1e3:
        return f"${v / 1e3:.1f}K"
    return f"${v:.2f}"


def _fmt_pct(v, sign=False):
    if v is None:
        return "n/a"
    s = "+" if sign and v > 0 else ""
    return f"{s}{v * 100:.1f}%"


def _safe(v, fmt="", default="n/a"):
    if v is None:
        return default
    try:
        return f"{v:{fmt}}"
    except (TypeError, ValueError):
        return str(v)


def _is_crypto(ticker: str) -> bool:
    t = ticker.upper()
    return t.endswith(("-USD", "-EUR")) or t in ("BTC", "ETH", "SOL", "BNB")


def _phase25_enrich(info, fin):
    """Phase 25 — Return dict of comprehensive yfinance fundamentals.
    Non-fatal: missing fields absent from returned dict.
    """
    if not info:
        return {}
    out = {}
    out["ebitda_abs"] = info.get("ebitda")
    out["ebitda_margin"] = info.get("ebitdaMargins")
    out["operating_cashflow_abs"] = info.get("operatingCashflow")
    out["free_cashflow_abs"] = info.get("freeCashflow")
    out["roe"] = info.get("returnOnEquity")
    out["roa"] = info.get("returnOnAssets")
    dte_pct = info.get("debtToEquity")
    out["debt_to_equity_ratio"] = (dte_pct / 100.0) if dte_pct is not None else None
    out["current_ratio"] = info.get("currentRatio")
    out["quick_ratio"] = info.get("quickRatio")
    out["insider_ownership_pct"] = info.get("heldPercentInsiders")
    out["institutional_ownership_pct"] = info.get("heldPercentInstitutions")
    out["short_pct_float"] = info.get("shortPercentOfFloat")
    out["short_ratio_days"] = info.get("shortRatio")
    out["peg_ratio"] = info.get("pegRatio")
    out["earnings_growth_qoq"] = info.get("earningsGrowth")
    try:
        if fin is not None and "Total Revenue" in fin.index:
            revs = fin.loc["Total Revenue"].dropna()
            if len(revs) >= 3:
                recent = float(revs.iloc[0])
                oldest = float(revs.iloc[-1])
                years = len(revs) - 1
                if oldest > 0 and recent > 0:
                    cagr = (recent / oldest) ** (1.0 / years) - 1.0
                    out["revenue_cagr_multiyear"] = cagr
                    out["revenue_cagr_years"] = years
    except Exception:
        pass
    return out


def fetch_stock_data(ticker: str) -> dict:
    """Pull all structured data via prices gateway + EDGAR + regime."""
    # SOCLE S1c (#111) : migré yf.Ticker → prices gateway (cache info 1h, fundamentals 24h).
    from shared.prices import get_balance_sheet, get_cashflow, get_financials, get_info
    info = get_info(ticker)

    def _safe_df(df, row, col=0):
        try:
            if df is not None and not df.empty and row in df.index:
                return df.loc[row].iloc[col]
        except Exception:
            pass
        return None

    fin = get_financials(ticker)
    bs = get_balance_sheet(ticker)
    cf = get_cashflow(ticker)

    revenue = _safe_df(fin, "Total Revenue")
    revenue_prev = _safe_df(fin, "Total Revenue", col=1)
    rev_growth = (revenue / revenue_prev - 1) if (revenue and revenue_prev) else info.get("revenueGrowth")

    net_income = _safe_df(fin, "Net Income")
    op_income = _safe_df(fin, "Operating Income")
    gross_profit = _safe_df(fin, "Gross Profit")

    fcf = _safe_df(cf, "Free Cash Flow")

    cash = _safe_df(bs, "Cash And Cash Equivalents")
    debt = _safe_df(bs, "Total Debt")

    # Insider
    insider = None
    cluster = None
    try:
        insider = edgar.get_insider_brief(ticker)
    except Exception as e:
        log.warning(f"insider {ticker}: {e}")
    try:
        cluster = edgar.get_insider_cluster(ticker, days=90)
    except Exception as e:
        log.warning(f"cluster {ticker}: {e}")

    # Regime
    regime_overall = None
    try:
        from intelligence import regime as regime_mod

        r = regime_mod.detect_regime()
        regime_overall = r.get("overall") if isinstance(r, dict) else None
    except Exception:
        pass

    # Credit
    credit = None
    try:
        from shared import macro

        credit = macro.get_credit_regime()
    except Exception as e:
        log.warning(f"credit fetch: {e}")

    # Earnings
    next_earnings, days_to_earnings = None, None
    try:
        with db() as cx:
            row = cx.execute(
                "SELECT date FROM events WHERE event_type='earnings' AND ticker=? "
                "AND date >= date('now') ORDER BY date LIMIT 1",
                (ticker,),
            ).fetchone()
            if row:
                next_earnings = row["date"]
                days_to_earnings = (datetime.strptime(row["date"], "%Y-%m-%d").date() - date.today()).days
    except Exception:
        pass

    # CEO from officers
    ceo = None
    try:
        for o in info.get("companyOfficers") or []:
            title = (o.get("title") or "").upper()
            if "CEO" in title or "CHIEF EXECUTIVE" in title:
                ceo = o.get("name")
                break
    except Exception:
        pass

    return {
        "ticker": ticker.upper(),
        "is_crypto": _is_crypto(ticker),
        "name": info.get("longName") or info.get("shortName") or ticker,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "employees": info.get("fullTimeEmployees"),
        "ceo": ceo,
        "market_cap": info.get("marketCap"),
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "business_summary": (info.get("longBusinessSummary") or "")[:1500],
        # Analyst
        "target_mean": info.get("targetMeanPrice"),
        "target_high": info.get("targetHighPrice"),
        "target_low": info.get("targetLowPrice"),
        "rec_key": info.get("recommendationKey"),
        "analyst_count": info.get("numberOfAnalystOpinions"),
        # Valuation
        "forward_pe": info.get("forwardPE"),
        "trailing_pe": info.get("trailingPE"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "ev_sales": info.get("enterpriseToRevenue"),
        "price_to_book": info.get("priceToBook"),
        # Growth & profit
        "revenue": revenue,
        "revenue_growth": rev_growth,
        "net_income": net_income,
        "net_margin": (net_income / revenue) if (net_income and revenue) else info.get("profitMargins"),
        "op_margin": (op_income / revenue) if (op_income and revenue) else info.get("operatingMargins"),
        "gross_margin": (gross_profit / revenue) if (gross_profit and revenue) else info.get("grossMargins"),
        "fcf_margin": (fcf / revenue) if (fcf and revenue) else None,
        "eps_growth_5y": info.get("earningsGrowth"),
        # Balance
        "cash": cash,
        "debt": debt,
        "net_cash": (cash - debt) if (cash and debt) else cash,
        # Forward
        "forward_eps": info.get("forwardEps"),
        "next_earnings": next_earnings,
        "days_to_earnings": days_to_earnings,
        # Insider
        "insider_net_m": insider.get("net_m") if insider else None,
        "insider_n_buys": insider.get("n_buys") if insider else None,
        "insider_n_sells": insider.get("n_sells") if insider else None,
        "cluster": cluster,
        "credit": credit,
        # Macro
        "regime": regime_overall,
        "beta": info.get("beta"),
        "dividend_yield": info.get("dividendYield"),
        **_phase25_enrich(info, fin),
    }


def _cluster_section(d):
    """Format per-insider breakdown for LLM prompt."""
    c = d.get("cluster")
    if not c or "error" in c:
        return ""
    lines = ["", "Per-insider breakdown (last 90d):"]
    lines.append(
        "- Distinct sellers: "
        + str(c["distinct_sellers"])
        + " (concentration "
        + ("%.0f" % (c["sell_concentration"] * 100))
        + "%"
        + ", ex-top "
        + ("%.0f" % (c["sell_concentration_ex_top"] * 100))
        + "%)"
    )
    lines.append("- Distinct buyers: " + str(c["distinct_buyers"]))
    lines.append("- Buy cluster: " + str(c["is_buy_cluster"]) + " (strength: " + c["cluster_strength"] + ")")
    if c.get("top_sellers"):
        lines.append("Top sellers (by $value, last 90d):")
        for owner, role, val in c["top_sellers"]:
            lines.append("  - " + owner.title() + " (" + (role or "?") + "): $" + (f"{val:.2f}") + "M")
    if c.get("top_buyers"):
        lines.append("Top buyers (by $value, last 90d):")
        for owner, role, val in c["top_buyers"]:
            lines.append("  - " + owner.title() + " (" + (role or "?") + "): $" + (f"{val:.2f}") + "M")
    return "\n".join(lines)


def _credit_line(d):
    c = d.get("credit")
    if not c or "error" in c:
        return "- Credit regime: data unavailable"
    hy = c.get("hy", {})
    ig = c.get("ig", {})
    parts = []
    if hy.get("bp") is not None:
        sign = "+" if hy.get("change_1m_bp", 0) >= 0 else ""
        parts.append(
            "HY OAS "
            + ("{:.0f}".format(hy["bp"]))
            + "bp ("
            + c.get("overall", "?")
            + ", 1m "
            + sign
            + ("{:.0f}".format(hy.get("change_1m_bp", 0)))
            + "bp)"
        )
    if ig.get("bp") is not None:
        parts.append("IG OAS " + ("{:.0f}".format(ig["bp"])) + "bp")
    return "- Credit regime: " + ", ".join(parts) if parts else "- Credit regime: unknown"


def build_prompt(d: dict) -> str:
    from datetime import datetime as _dt

    today_str = _dt.now().strftime("%d %B %Y")
    today_iso = _dt.now().strftime("%Y-%m-%d")
    current_quarter = f"Q{((_dt.now().month - 1) // 3) + 1} {_dt.now().year}"
    next_quarter_year = _dt.now().year + (1 if _dt.now().month >= 10 else 0)
    next_quarter = f"Q{((_dt.now().month - 1) // 3 + 1) % 4 + 1} {next_quarter_year}"

    crypto_note = ""
    if d["is_crypto"]:
        crypto_note = "\nNOTE: This is a cryptocurrency. Fundamental ratios may be n/a — focus on cycle position, macro liquidity sensitivity, and on-chain dynamics inferred from price action + market cap. Acknowledge data gaps honestly.\n"

    return f"""You are a senior buy-side analyst. Produce a concise, decision-useful analysis fiche for {d["name"]} ({d["ticker"]}).

=== ANCHOR DATE (CRITICAL) ===
TODAY IS {today_str} ({today_iso}). Current quarter is {current_quarter}.
- ALL catalysts in "CATALYSTS NEXT 6 MONTHS" MUST be events AFTER {today_iso}.
  NEXT earnings event for most companies = {next_quarter} or {current_quarter} (end-of-quarter releases).
- DO NOT cite past events (Q3 2024, FY2024, October 2024 announcements) as if they were future catalysts.
- DO NOT cite "post-election" without specifying which election.
- If your training data is older than today, acknowledge it and reason from the structured data provided.
- The "next_earnings" field below tells you the actual upcoming earnings date — use it.
{crypto_note}
=== STRUCTURED DATA ===

Identity:
- Sector: {d.get("sector") or "n/a"} / {d.get("industry") or "n/a"}
- Country: {d.get("country") or "n/a"}  •  Employees: {_safe(d.get("employees"), ",")}
- CEO: {d.get("ceo") or "n/a"}
- Market cap: {_fmt_money(d.get("market_cap"))}

Business summary:
{d.get("business_summary") or "n/a"}

Price & valuation:
- Price: {_safe(d.get("price"), ".2f")} (52w {_safe(d.get("52w_low"), ".2f")}-{_safe(d.get("52w_high"), ".2f")})
- Trailing P/E: {_safe(d.get("trailing_pe"), ".1f")} | Forward P/E: {_safe(d.get("forward_pe"), ".1f")}
- EV/EBITDA: {_safe(d.get("ev_ebitda"), ".1f")} | EV/Sales: {_safe(d.get("ev_sales"), ".1f")} | P/Book: {_safe(d.get("price_to_book"), ".1f")}

Profitability & growth:
- Revenue (latest yr): {_fmt_money(d.get("revenue"))}, growth YoY: {_fmt_pct(d.get("revenue_growth"), sign=True)}
- Gross margin: {_fmt_pct(d.get("gross_margin"))}
- Operating margin: {_fmt_pct(d.get("op_margin"))}
- Net margin: {_fmt_pct(d.get("net_margin"))}
- FCF margin: {_fmt_pct(d.get("fcf_margin"))}
- 5y EPS growth: {_fmt_pct(d.get("eps_growth_5y"), sign=True)}
- EBITDA (TTM): {_fmt_money(d.get("ebitda_abs"))}, margin {_fmt_pct(d.get("ebitda_margin"))}
- OCF (TTM): {_fmt_money(d.get("operating_cashflow_abs"))} | FCF (TTM): {_fmt_money(d.get("free_cashflow_abs"))}
- ROE: {_fmt_pct(d.get("roe"))} | ROA: {_fmt_pct(d.get("roa"))}
- Revenue CAGR ({d.get("revenue_cagr_years") or "?"}Y): {_fmt_pct(d.get("revenue_cagr_multiyear"), sign=True)}
- Earnings growth (latest Q YoY): {_fmt_pct(d.get("earnings_growth_qoq"), sign=True)}

Balance sheet:
- Cash: {_fmt_money(d.get("cash"))}
- Debt: {_fmt_money(d.get("debt"))}
- Net cash: {_fmt_money(d.get("net_cash"))}
- D/E ratio: {_safe(d.get("debt_to_equity_ratio"), ".2f")}x | Current ratio: {_safe(d.get("current_ratio"), ".2f")} | Quick ratio: {_safe(d.get("quick_ratio"), ".2f")}

Analyst consensus:
- Mean target: {_safe(d.get("target_mean"), ".2f")} (high {_safe(d.get("target_high"), ".0f")} / low {_safe(d.get("target_low"), ".0f")})
- Recommendation: {d.get("rec_key") or "n/a"} ({d.get("analyst_count") or 0} analysts)
- PEG ratio: {_safe(d.get("peg_ratio"), ".2f")}

Insider activity (90d via SEC EDGAR):
- Net flow: {_fmt_money((d.get("insider_net_m") or 0) * 1e6)}
- # buys / # sells: {d.get("insider_n_buys") or 0} / {d.get("insider_n_sells") or 0}
{_cluster_section(d)}

Market positioning:
- Short interest: {_fmt_pct(d.get("short_pct_float"))} of float | Days to cover: {_safe(d.get("short_ratio_days"), ".1f")}
- Insider ownership: {_fmt_pct(d.get("insider_ownership_pct"))} | Institutional ownership: {_fmt_pct(d.get("institutional_ownership_pct"))}

Forward catalysts:
- Next earnings: {d.get("next_earnings") or "n/a"} ({d.get("days_to_earnings") or "n/a"}d away)
- Forward EPS: {_safe(d.get("forward_eps"), ".2f")}

Macro context:
- Current regime: {d.get("regime") or "unknown"}
{_credit_line(d)}
- Beta: {_safe(d.get("beta"), ".2f")}

=== RECENT NEWSLETTER SIGNALS (last 30d) ===

{d.get("newsletter_signals_block") or "(no signals available)"}

=== OUTPUT REQUIRED ===

Plain text (no markdown headers, no bold). Structure:

BUSINESS QUALITY
[3-4 bullets on moats, competitive positioning, why this company wins. SPECIFIC to THIS company.]

FINANCIAL HEALTH
[3-4 bullets interpreting numbers. Strong/weak signals. Red flags. Trends.]

INSIDER & MACRO CONTEXT
[2-3 bullets. Use the per-insider breakdown to distinguish dominant-seller patterns (one co-founder/exec dominating) from broad exec distribution. Names and roles matter — interpret WHO is selling and what it implies, not just net amounts.]

CATALYSTS NEXT 6 MONTHS
Bullish:
- [specific catalyst, with date/timeframe; cite supporting signals if any]
- [...]
Bearish:
- [specific catalyst; cite supporting signals if any]
- [...]

NEWSLETTER SIGNAL CONTEXT
[2-3 bullets synthesizing what the recent newsletter signals (above section) say about this name. Are they SUPPORTING or CONTRADICTING the quality/catalyst picture? Cite source names. If no signals, state that and move on.]

FLIP CRITERIA — BIDIRECTIONAL DISCIPLINE
[3 specific, measurable, time-bounded developments that would INVALIDATE this analysis. Each must be (a) concrete data point / price level / event, (b) bounded within 30d / 90d / 6m / 12m, (c) plausibly observable. NOT generic. YES specific (e.g., "if FCF margin compresses below 20% over 2 consecutive quarters" or "if forward P/E re-rates to >35x without commensurate growth acceleration"). This is the most important section: reading it should make a thoughtful reader say "yes, those are the right things to watch for an exit."]

PROBABILISTIC OUTLOOK (6M)
Probability weighting MUST explicitly cite: (a) current credit regime (HY OAS bp level + classification + 1m trend), (b) insider concentration_ex_top from past 90d (distinguishing broad executive distribution from single-seller idiosyncratic noise). Tether each scenario weight to these two anchors plus catalyst proximity. No abstract probabilities.
- Bull case (N%): price target $X, drivers: ...
- Base case (N%): price target $X, drivers: ...
- Bear case (N%): downside $X, drivers: ...

ACTIONABLE TAKEAWAY
[2-3 sentences max. What would a thoughtful PM do here? What's the asymmetric bet? If "wait", say why.]

Rules: No generic statements. Cite specific numbers. If data missing, acknowledge. Total under 1500 words. Match language of business summary (English default).
"""


def _get_cached_analysis(ticker, max_age_hours=24):
    """Return (content, data_dict, timestamp) if recent cache exists, else None."""
    import json
    import sqlite3
    from datetime import datetime, timedelta

    conn = sqlite3.connect("data/bot.db")
    try:
        cutoff = (datetime.now(UTC) - timedelta(hours=max_age_hours)).replace(tzinfo=None).isoformat()
        row = conn.execute(
            "SELECT content, metadata, timestamp FROM analyses "
            "WHERE ticker=? AND type='analyze' AND timestamp > ? "
            "ORDER BY id DESC LIMIT 1",
            (ticker.upper(), cutoff),
        ).fetchone()
        if not row:
            return None
        content, meta_json, ts = row
        try:
            data_cached = json.loads(meta_json) if meta_json else {}
        except Exception:
            data_cached = {}
        return content, data_cached, ts
    finally:
        conn.close()


def _store_analysis(ticker, synthesis, data):
    """Persist LLM synthesis + full data snapshot (JSON-safe subset)."""
    import json
    import sqlite3

    from shared.storage import _naive_utc_iso

    def _safe(v):
        try:
            json.dumps(v)
            return True
        except (TypeError, ValueError):
            return False

    meta_dict = {k: v for k, v in data.items() if _safe(v)}
    conn = sqlite3.connect("data/bot.db")
    try:
        conn.execute(
            "INSERT INTO analyses(ticker, type, timestamp, content, metadata) VALUES (?, ?, ?, ?, ?)",
            (
                ticker.upper(),
                "analyze",
                _naive_utc_iso(),
                synthesis,
                json.dumps(meta_dict),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def analyze_stock(ticker: str, use_cache: bool = True) -> dict:
    from shared import llm

    # Cache check FIRST -- skip 15-20s of fetch_stock_data on hit
    if use_cache:
        try:
            cached = _get_cached_analysis(ticker, max_age_hours=24)
            if cached:
                content_cached, data_cached, ts_cached = cached
                data_cached.setdefault("ticker", ticker.upper())
                data_cached.setdefault("name", ticker.upper())
                data_cached["_cache_hit"] = True
                data_cached["_cache_ts"] = ts_cached
                return {
                    "ticker": data_cached.get("ticker"),
                    "data": data_cached,
                    "synthesis": content_cached,
                    "cached": True,
                }
        except Exception:
            pass

    data = fetch_stock_data(ticker)
    try:
        data["newsletter_signals_block"] = build_signals_context_block(ticker)
    except Exception as e:
        log.warning(f"analyze: signals fetch {ticker} failed: {e}")
        data["newsletter_signals_block"] = "(signal query unavailable)"
    if (not data.get("name") or data.get("name") == ticker) and not data.get("price"):
        return {"error": f"No data found for {ticker}", "data": data}

    prompt = build_prompt(data)

    # Defensive LLM call - try multiple common signatures
    synthesis = None
    last_err = None
    llm_unavailable = None
    for fn_name in ["complete", "ask", "call", "generate", "chat"]:
        fn = getattr(llm, fn_name, None)
        if not fn:
            continue
        try:
            try:
                synthesis = fn(prompt, max_tokens=2500)
            except TypeError:
                synthesis = fn(prompt)
            if synthesis:
                break
        except llm.LLMUnavailableError as _e:
            # #93 Composant A : LLM upstream indisponible -- pas la peine
            # d'essayer les autres fonctions, elles tapent le meme client.
            llm_unavailable = _e
            break
        except Exception as e:
            last_err = e
    if llm_unavailable is not None:
        # MARQUEUR SEC (degraded_restitution_contract) via source unique
        # dashboard.restitution. data brutes (COMPUTED) restent disponibles
        # pour le caller -- on n'efface QUE le slot SYNTHESIZED.
        from shared.llm_restitution import (
            format_llm_unavailable_marker,  # cure P2 audit (3) — couche shared/, plus de dashboard/
        )

        return {
            "ticker": data.get("ticker"),
            "data": data,
            "synthesis": None,
            "cached": False,
            "llm_unavailable": True,
            "llm_unavailable_reason": llm_unavailable.reason,
            "marker": format_llm_unavailable_marker(
                llm_unavailable.reason, surface="synthèse"
            ),
        }
    if not synthesis:
        return {"error": f"LLM call failed: {last_err}", "data": data}

    # Cache write (failure must not break user-visible result)
    with contextlib.suppress(Exception):
        _store_analysis(ticker, synthesis, data)

    return {"ticker": data["ticker"], "data": data, "synthesis": synthesis, "cached": False}


def format_for_telegram(result: dict) -> list:
    if "error" in result:
        return [f"❌ Analysis failed: {result['error']}"]

    d = result["data"]
    syn = result["synthesis"]

    header = (
        f"📊 {d['name']} ({d['ticker']})\n"
        f"{d.get('sector') or 'n/a'} / {d.get('industry') or 'n/a'}\n"
        f"Cap: {_fmt_money(d.get('market_cap'))}  •  "
        f"Price: {_safe(d.get('price'), '.2f')}  •  "
        f"Regime: {d.get('regime') or '?'}\n"
        f"───────────────────\n"
    )

    chunks = []
    current = header
    for line in syn.split("\n"):
        if len(current) + len(line) + 1 > 3800:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)
    return chunks
