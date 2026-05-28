"""SEC EDGAR Form 4 insider trading wrapper.

No auth required. SEC requires User-Agent header (rejects calls without).
Rate limit ~10 req/s, we use ~1 req/s to be conservative.

Future v2: persist to insider_trades table, daily refresh, big-sell alerts.
"""

import os
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from shared.data_source_base import RateLimiter, retry_with_backoff

EDGAR_UA = os.environ.get("EDGAR_USER_AGENT", "Olivier Legendre olegendre@gmail.com")
EDGAR_HEADERS = {
    "User-Agent": EDGAR_UA,
    "Accept-Encoding": "gzip, deflate",
}


# SEC EDGAR public rate limit is 10 req/sec; be conservative at 5 req/sec = 300 rpm
_EDGAR_RATE_LIMITER = RateLimiter(requests_per_minute=300)


def _edgar_get(url: str, timeout: int = 10) -> requests.Response:
    """Rate-limited + retried GET to SEC EDGAR. Sprint 1.2 item 3a."""
    _EDGAR_RATE_LIMITER.acquire()
    return retry_with_backoff(  # type: ignore[no-any-return]  # Sprint 1.2 baseline: retry_with_backoff is untyped
        lambda: requests.get(url, headers=EDGAR_HEADERS, timeout=timeout),
        max_attempts=3,
        base_delay=2.0,
        exceptions=(requests.RequestException,),
    )


_CIK_CACHE: dict[str, str] | None = None
_CIK_CACHE_TS: Any = None  # datetime
CIK_CACHE_TTL_HOURS = 24


def get_cik_for_ticker(ticker):
    """Lookup CIK for ticker. Cached 24h."""
    global _CIK_CACHE, _CIK_CACHE_TS
    now = datetime.now(UTC)
    stale = _CIK_CACHE_TS is None or (now - _CIK_CACHE_TS).total_seconds() > CIK_CACHE_TTL_HOURS * 3600
    if _CIK_CACHE is None or stale:
        try:
            r = _edgar_get("https://www.sec.gov/files/company_tickers.json", timeout=10)
            data = r.json()
            _CIK_CACHE = {}
            for entry in data.values():
                _CIK_CACHE[entry["ticker"].upper()] = str(entry["cik_str"]).zfill(10)
            _CIK_CACHE_TS = now
        except Exception as e:
            print(f"CIK fetch failed: {e}")
            return None
    return _CIK_CACHE.get(ticker.upper())


def get_recent_form4_filings(ticker, days=90, limit=30):
    """Returns list of recent Form 4 filing metadata."""
    cik = get_cik_for_ticker(ticker)
    if not cik:
        return []
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        r = _edgar_get(url, timeout=10)
        data = r.json()
    except Exception as e:
        print(f"Submissions fetch failed for {ticker}: {e}")
        return []
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    cik_int = str(int(cik))
    results: list[dict[str, Any]] = []
    for i, form in enumerate(forms):
        if form != "4":
            continue
        if i >= len(filing_dates) or filing_dates[i] < cutoff:
            continue
        if len(results) >= limit:
            break
        accession = accessions[i]
        primary = primary_docs[i] if i < len(primary_docs) else None
        if not primary:
            continue
        accession_nd = accession.replace("-", "")
        # Strip xsl rendering prefix: "xslF345X06/wk-form4_X.xml" -> "wk-form4_X.xml" (raw XML)
        raw_doc = primary.split("/", 1)[1] if "/" in primary else primary
        url_xml = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nd}/{raw_doc}"
        results.append(
            {
                "ticker": ticker,
                "cik": cik,
                "filing_date": filing_dates[i],
                "accession": accession,
                "url": url_xml,
            }
        )
    return results


def parse_form4(url):
    """Fetch + parse Form 4 XML. Returns dict or None."""
    try:
        r = _edgar_get(url, timeout=10)
        if r.status_code != 200:
            return None
        content = r.content
        if not content or b"<" not in content[:200]:
            return None
        root = ET.fromstring(content)
    except Exception:
        return None
    owner = root.findtext(".//reportingOwnerId/rptOwnerName") or "?"
    is_dir = root.findtext(".//reportingOwnerRelationship/isDirector") == "1"
    is_off = root.findtext(".//reportingOwnerRelationship/isOfficer") == "1"
    is_10 = root.findtext(".//reportingOwnerRelationship/isTenPercentOwner") == "1"
    title = root.findtext(".//reportingOwnerRelationship/officerTitle") or ""
    relations = []
    if is_off:
        relations.append(title or "Officer")
    if is_dir:
        relations.append("Director")
    if is_10:
        relations.append("10%")
    role = " / ".join(relations) if relations else "Other"
    transactions = []
    for trans in root.findall(".//nonDerivativeTransaction"):
        code = trans.findtext(".//transactionCoding/transactionCode") or ""
        date = trans.findtext(".//transactionDate/value") or ""
        try:
            shares = float(trans.findtext(".//transactionAmounts/transactionShares/value") or "0")
            price = float(trans.findtext(".//transactionAmounts/transactionPricePerShare/value") or "0")
        except ValueError:
            continue
        ad = trans.findtext(".//transactionAmounts/transactionAcquiredDisposedCode/value") or ""
        transactions.append(
            {
                "code": code,
                "date": date,
                "shares": shares,
                "price": price,
                "value": shares * price,
                "ad_code": ad,
            }
        )
    return {"owner": owner, "role": role, "transactions": transactions}


def get_insider_activity(ticker, days=90, sleep_between=0.7):
    """High-level: fetch + parse all Form 4 transactions for ticker."""
    filings = get_recent_form4_filings(ticker, days=days)
    if not filings:
        return []
    activity = []
    for f in filings:
        time.sleep(sleep_between)
        parsed = parse_form4(f["url"])
        if not parsed:
            continue
        for trans in parsed["transactions"]:
            activity.append(
                {
                    "ticker": ticker,
                    "filing_date": f["filing_date"],
                    "transaction_date": trans["date"],
                    "owner": parsed["owner"],
                    "role": parsed["role"],
                    "code": trans["code"],
                    "shares": trans["shares"],
                    "price": trans["price"],
                    "value": trans["value"],
                    "ad_code": trans["ad_code"],
                }
            )
    return activity


def format_insider_summary(activity, top_n=15):
    if not activity:
        return "Aucune transaction insider Form 4 dans la fenetre."
    purchases = [a for a in activity if a["code"] == "P"]
    sales = [a for a in activity if a["code"] == "S"]
    awards = [a for a in activity if a["code"] == "A"]
    total_p = sum(a["value"] for a in purchases)
    total_s = sum(a["value"] for a in sales)
    ticker = activity[0]["ticker"]
    lines = [f"INSIDERS {ticker} ({len(activity)} txns, 90j)"]
    lines.append(f"  Buys (P): {len(purchases)} = ${total_p / 1e6:.2f}M")
    lines.append(f"  Sells (S): {len(sales)} = ${total_s / 1e6:.2f}M")
    if purchases or sales:
        lines.append(f"  Net (P-S): ${(total_p - total_s) / 1e6:+.2f}M")
    lines.append(f"  Awards/grants (A): {len(awards)} (skipped from net)")
    lines.append("")
    lines.append("Top recent (15):")
    sorted_act = sorted(activity, key=lambda a: a["filing_date"], reverse=True)
    code_map = {"P": "BUY", "S": "SELL", "A": "GRANT", "F": "TAX", "M": "EXERC", "G": "GIFT"}
    for a in sorted_act[:top_n]:
        cl = code_map.get(a["code"], a["code"])
        owner = (a["owner"] or "?")[:22]
        role = (a["role"] or "?")[:20]
        lines.append(
            f"  {a['filing_date']} {cl:5} {owner:22} [{role:20}] "
            f"{a['shares']:>10,.0f}@${a['price']:>7.2f}=${a['value'] / 1e6:>6.2f}M"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "NVDA"
    print(f"Fetching insiders for {ticker} (last 90 days, expect 20-40s)...")
    activity = get_insider_activity(ticker, days=90)
    print(format_insider_summary(activity))


# === Lazy cache for digest prompt integration ===
import contextlib
import json as _json

CACHE_DIR = "data/cache"
INSIDER_CACHE_TTL_HOURS = 24


def get_insider_brief(ticker, days=90, ttl_hours=INSIDER_CACHE_TTL_HOURS):
    """Lightweight insider summary with file cache (24h TTL by default)."""
    from pathlib import Path as _Path

    _cache_dir = _Path(CACHE_DIR)
    _cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = str(_cache_dir / f"insiders_{ticker.upper()}.json")
    if _Path(cache_file).exists():
        try:
            with open(cache_file) as _cf:
                data = _json.load(_cf)
            ts = data.get("cached_at", 0)
            age_h = (datetime.now(UTC).timestamp() - ts) / 3600
            if age_h < ttl_hours:
                return data["brief"]
        except Exception:
            pass
    activity = get_insider_activity(ticker, days=days)
    if not activity:
        brief = {
            "ticker": ticker,
            "net_m": 0.0,
            "buys_m": 0.0,
            "sells_m": 0.0,
            "n_buys": 0,
            "n_sells": 0,
            "n_big_sales": 0,
        }
    else:
        purchases = [a for a in activity if a["code"] == "P"]
        sales = [a for a in activity if a["code"] == "S"]
        total_p = sum(a["value"] for a in purchases)
        total_s = sum(a["value"] for a in sales)
        big_sales = [a for a in sales if a["value"] > 5e6]
        brief = {
            "ticker": ticker,
            "net_m": (total_p - total_s) / 1e6,
            "buys_m": total_p / 1e6,
            "sells_m": total_s / 1e6,
            "n_buys": len(purchases),
            "n_sells": len(sales),
            "n_big_sales": len(big_sales),
        }
    with contextlib.suppress(Exception):
        with open(cache_file, "w") as _cf:
            _json.dump({"brief": brief, "cached_at": datetime.now(UTC).timestamp()}, _cf)
    return brief


def get_insider_briefs(tickers):
    """Get cached briefs for multiple tickers."""
    return [get_insider_brief(t) for t in tickers if t]


def format_insider_context_for_prompt(briefs):
    """Format briefs as preamble for LLM signal-scoring prompt."""
    if not briefs:
        return ""
    active = [b for b in briefs if (b.get("n_buys", 0) + b.get("n_sells", 0)) > 0]
    if not active:
        return ""
    lines = ["=== INSIDER FLOW (90d, top watchlist) ==="]
    for b in active[:15]:
        tk = b["ticker"]
        net = b["net_m"]
        sign = "+" if net > 0 else ""
        lines.append(
            f"  {tk}: net {sign}{net:.1f}M (P:${b['buys_m']:.1f}M / S:${b['sells_m']:.1f}M, {b['n_buys']}P/{b['n_sells']}S)"
        )
    lines.append("")
    lines.append("Scoring adjustment: net sells > $50M = bearish lean. Insider buys > $5M = bullish lean.")
    lines.append("Heavy director dumping vs bullish narrative = caution flag, downgrade score by 1-2.")
    lines.append("===")
    lines.append("")
    return "\n".join(lines)


# === Phase 12.1: Cluster detection ===


def _role_weight(role):
    r = (role or "").lower()
    if any(x in r for x in ("ceo", "chief executive")):
        return 5
    if any(x in r for x in ("cfo", "chief financial")):
        return 4
    if any(x in r for x in ("coo", "cto", "cio", "chief")):
        return 3
    if "director" in r:
        return 2
    if "10%" in r or "owner" in r:
        return 1
    return 1


def _classify_buy_cluster(buyers):
    n = len(buyers)
    if n == 0:
        return "none"
    total_m = sum(b["value_m"] for b in buyers.values())
    max_role = max((_role_weight(b["role"]) for b in buyers.values()), default=0)
    if n >= 5 and total_m >= 5.0:
        return "strong"
    if n >= 3 and max_role >= 4 and total_m >= 5.0:
        return "strong"
    if n >= 3 and total_m >= 1.0:
        return "moderate"
    if n >= 3:
        return "weak"
    return "none"


def get_insider_cluster(ticker, days=14):
    try:
        activity = get_insider_activity(ticker, days=days)
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e), "days": days}

    cutoff = datetime.now(UTC) - timedelta(days=days)
    buyers, sellers = {}, {}

    for t in activity or []:
        td_str = t.get("transaction_date")
        if not td_str:
            continue
        try:
            td = datetime.strptime(td_str[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError, TypeError:
            continue
        if td < cutoff:
            continue

        code = (t.get("code") or "").upper()
        owner = (t.get("owner") or "").strip()
        role = (t.get("role") or "").strip()
        value_m = abs(t.get("value", 0) or 0) / 1e6

        if not owner or value_m == 0:
            continue

        if code == "P":
            if owner not in buyers:
                buyers[owner] = {"value_m": 0, "role": role}
            buyers[owner]["value_m"] += value_m
        elif code == "S":
            if owner not in sellers:
                sellers[owner] = {"value_m": 0, "role": role}
            sellers[owner]["value_m"] += value_m

    def _top(d):
        return sorted([(o, b["role"], b["value_m"]) for o, b in d.items()], key=lambda x: -x[2])[:5]

    total_sell_m = sum(float(s["value_m"]) for s in sellers.values())
    concentration = 0.0
    concentration_ex_top = 0.0
    if sellers and total_sell_m > 0:
        sorted_vals = sorted([float(s["value_m"]) for s in sellers.values()], reverse=True)
        concentration = sorted_vals[0] / total_sell_m
        if len(sorted_vals) >= 2:
            rest = sum(sorted_vals[1:])
            concentration_ex_top = sorted_vals[1] / rest if rest > 0 else 0

    return {
        "ticker": ticker.upper(),
        "days": days,
        "distinct_buyers": len(buyers),
        "distinct_sellers": len(sellers),
        "total_buy_m": sum(b["value_m"] for b in buyers.values()),
        "total_sell_m": total_sell_m,
        "top_buyers": _top(buyers),
        "top_sellers": _top(sellers),
        "is_buy_cluster": _classify_buy_cluster(buyers) in ("moderate", "strong"),
        "is_distributed_selling": len(sellers) >= 5 and concentration < 0.5,
        "sell_concentration": concentration,
        "sell_concentration_ex_top": concentration_ex_top,
        "cluster_strength": _classify_buy_cluster(buyers),
    }


def format_insider_cluster(cluster):
    if "error" in cluster:
        return "ERROR " + cluster["ticker"] + ": " + cluster["error"]
    c = cluster
    out = []
    out.append("INSIDER CLUSTER " + c["ticker"] + " (" + str(c["days"]) + "d window)")
    out.append("")

    if c["is_buy_cluster"]:
        marks = {"strong": "!!!", "moderate": "!!", "weak": "!", "none": ""}.get(c["cluster_strength"], "")
        out.append(
            "BUY CLUSTER "
            + marks
            + ": "
            + str(c["distinct_buyers"])
            + " insiders, $"
            + ("{:.2f}".format(c["total_buy_m"]))
            + "M"
        )
        out.append("Strength: " + c["cluster_strength"].upper())
        out.append("Top buyers:")
        for owner, role, val in c["top_buyers"]:
            out.append("  - " + owner.title() + " (" + (role or "?") + "): $" + (f"{val:.2f}") + "M")
    elif c["distinct_buyers"] == 0:
        out.append("No buying (0 P-code transactions)")
    else:
        out.append("BUYS: " + str(c["distinct_buyers"]) + " insider(s), $" + ("{:.2f}".format(c["total_buy_m"])) + "M")
        for owner, role, val in c["top_buyers"]:
            out.append("  - " + owner.title() + " (" + (role or "?") + "): $" + (f"{val:.2f}") + "M")

    out.append("")

    if c["distinct_sellers"] > 0:
        sig = " DISTRIBUTED" if c["is_distributed_selling"] else ""
        out.append(
            "SELLS: "
            + str(c["distinct_sellers"])
            + " insider(s), $"
            + ("{:.2f}".format(c["total_sell_m"]))
            + "M  (conc "
            + ("%.0f" % (c["sell_concentration"] * 100))
            + "%, ex-top "
            + ("%.0f" % (c["sell_concentration_ex_top"] * 100))
            + "%)"
            + sig
        )
        for owner, role, val in c["top_sellers"]:
            out.append("  - " + owner.title() + " (" + (role or "?") + "): $" + (f"{val:.2f}") + "M")
    else:
        out.append("No selling")

    return "\n".join(out)


# ============ Phase C9 — 8-K filings via submissions API ============


def get_recent_8k_filings(ticker, days=30):
    """Phase C9 — Fetch recent 8-K filings via SEC submissions JSON.

    Returns list of dicts: {accession, cik, filed_at, items_raw, item_codes, url, form}.
    Uses recent.items[] parallel-indexed array, zero HTML parsing.
    """
    cik = get_cik_for_ticker(ticker)
    if not cik:
        return []
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        r = _edgar_get(url, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    items_list = recent.get("items", [])
    primary_docs = recent.get("primaryDocument", [])
    cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    result = []
    for i, form in enumerate(forms):
        if form not in ("8-K", "8-K/A"):
            continue
        filed_at = dates[i] if i < len(dates) else None
        if not filed_at or filed_at < cutoff:
            continue
        accession = accessions[i] if i < len(accessions) else None
        items_raw = items_list[i] if i < len(items_list) else ""
        primary = primary_docs[i] if i < len(primary_docs) else ""
        item_codes = []
        for c in (items_raw or "").split(","):
            c = c.strip().replace("Item ", "").replace("Item\u00a0", "")
            if c:
                item_codes.append(c)
        acc_clean = (accession or "").replace("-", "")
        filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{primary}"
        result.append(
            {
                "accession": accession,
                "cik": cik,
                "filed_at": filed_at,
                "items_raw": items_raw,
                "item_codes": item_codes,
                "url": filing_url,
                "form": form,
            }
        )
    return result
