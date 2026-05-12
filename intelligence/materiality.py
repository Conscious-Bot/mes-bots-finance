"""
Phase 11 Materiality scoring engine v2 — calibrated.
Penalties: tickerless, narrativeless, noise patterns.
"""
import json, logging, re
log = logging.getLogger(__name__)


MEGA_CAP = {
    "NVDA", "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "TSLA",
    "AVGO", "TSM", "BRK.B", "JPM", "V", "MA", "XOM", "JNJ", "WMT",
    "LLY", "UNH", "NFLX", "ORCL", "CRM",
}
LARGE_CAP = {
    "PLTR", "AMD", "COIN", "MSTR", "IBIT", "ETHA", "INTC", "IBM",
    "CSCO", "QCOM", "TXN", "PYPL", "SHOP", "ADBE", "ASML", "BABA",
    "PDD", "NEE", "CEG", "VRT", "EAT", "URA", "REMX", "XOP",
    "AMAT", "KLAC", "LRCX", "MU", "MRVL", "ARM", "MPWR",
    "NBIS", "SMCI", "ANET", "JNPR", "DELL", "HPE", "WDC",
    "ON", "STM", "INFN", "VRT", "FLEX", "JBL",
}
TICKER_BLACKLIST = {
    "AI", "USD", "EU", "US", "CEO", "CFO", "IPO", "ETF", "API",
    "GPU", "CPU", "EUR", "GDP", "FED", "ECB", "BOJ", "PBOC", "OPEC",
    "EBITDA", "P", "Q", "FY", "EPS", "M1", "M2", "M3", "Q1", "Q2", "Q3", "Q4",
    "WSJ", "FT", "NYT", "BBG", "CNBC", "VS", "PER", "POUR", "DE",
    "IA", "OK", "OS", "LE", "LA", "JPY", "GBP", "CHF", "CAD",
    "HTML", "CSS", "URL", "PDF", "JSON", "XML", "HTTP", "HTTPS",
    "TBD", "TBA", "ETA", "FAQ", "TPU", "ASIC", "HPC", "MOQ",
}
NOISE_PATTERNS = (
    "authenticationerror", "error:", "exception:", "traceback",
    "welcome to ", "confirm your ", "verify your ", "thanks for subscribing",
    "subscription confirmed", "email de bienvenue", "confirmation d'abonnement",
    "abonnement substack",
)


def _safe_json(v):
    if v is None: return []
    if isinstance(v, (list, dict)): return v
    if isinstance(v, str):
        try: return json.loads(v)
        except Exception: return []
    return []


def extract_tickers(signal):
    ents = _safe_json(signal.get("entities"))
    tickers = []
    if isinstance(ents, list):
        for e in ents:
            if isinstance(e, str) and e.strip():
                t = e.upper().strip()
                if 1 <= len(t) <= 6 and t not in TICKER_BLACKLIST and t.replace(".", "").isalpha():
                    tickers.append(t)
    elif isinstance(ents, dict):
        for t in (ents.get("tickers") or ents.get("symbols") or []):
            if isinstance(t, str):
                tickers.append(t.upper().strip())
    if not tickers:
        text = (signal.get("summary") or signal.get("title") or "")[:500]
        for t in re.findall(r"\b([A-Z]{2,5})\b", text):
            if t not in TICKER_BLACKLIST:
                tickers.append(t)
                if len(tickers) >= 5: break
    return tickers[:5]


def extract_narratives(signal):
    n = _safe_json(signal.get("narratives"))
    if isinstance(n, list):
        return [str(x).lower().strip() for x in n if x]
    return []


def sentiment_polarity(signal):
    s = signal.get("sentiment")
    if s is None: return "neutral"
    if isinstance(s, (int, float)):
        if s > 0.2: return "positive"
        if s < -0.2: return "negative"
        return "neutral"
    s = str(s).lower().strip()
    if s in ("positive", "bullish", "buy", "+", "pos"): return "positive"
    if s in ("negative", "bearish", "sell", "-", "neg"): return "negative"
    return "neutral"


def derive_signal_type(signal):
    """Narratives first (structured), then text keywords (fallback)."""
    narr = set(extract_narratives(signal))
    if any("insider" in n for n in narr):
        return "insider"
    if narr & {"earnings", "guidance"}:
        return "earnings"
    if narr & {"ai_infra", "ai_capex", "semi_cycle", "supply_chain", "datacenter", "ai_compute", "critical_minerals"}:
        return "industry"
    if narr & {"macro", "fed", "rates", "inflation", "cpi", "fomc", "geopolitics"}:
        return "macro"
    if narr & {"analyst", "upgrade", "downgrade"}:
        return "analyst"
    if narr & {"crypto", "btc", "eth"}:
        return "crypto"

    text = ((signal.get("summary") or "") + " " + (signal.get("title") or "")).lower()
    if any(k in text for k in ("insider", "form 4", "10b5-1")): return "insider"
    if any(k in text for k in ("guidance ", "outlook ", "forecast ")): return "guidance"
    if any(k in text for k in ("earnings beat", "earnings miss", "eps beat")): return "earnings"
    if any(k in text for k in ("upgrade", "downgrade", "price target")): return "analyst"
    if any(k in text for k in ("fomc", "powell", "rate cut", "rate hike", "cpi report")): return "macro"
    if any(k in text for k in ("capex", "supply chain", "supplier")): return "industry"
    return "news"


def _is_noise(signal):
    text = ((signal.get("summary") or "") + " " + (signal.get("title") or "")).lower()
    return any(p in text for p in NOISE_PATTERNS)


def _ticker_importance(ticker, watchlist=None):
    if not ticker: return 0.15
    t = str(ticker).upper().strip()
    if t in MEGA_CAP: return 1.0
    if watchlist and t in {w.upper() for w in watchlist}: return 0.75
    if t in LARGE_CAP: return 0.65
    return 0.4


def score_novelty(signal, recent_signals):
    target_tickers = set(extract_tickers(signal))
    target_narratives = set(extract_narratives(signal))
    target_id = signal.get("id")
    if not target_tickers and len(target_narratives) <= 1:
        return 0.3
    similar = 0
    for other in recent_signals or []:
        if other.get("id") == target_id: continue
        ot = set(extract_tickers(other))
        on = set(extract_narratives(other))
        if target_tickers and ot and (target_tickers & ot):
            if not target_narratives or not on or (target_narratives & on):
                similar += 1
        elif target_narratives and on and len(target_narratives & on) >= 2:
            similar += 0.5
    return max(0.15, 1.0 / (1 + 0.5 * similar))


def score_cross_confirmation(signal, recent_signals):
    target_tickers = set(extract_tickers(signal))
    target_narratives = set(extract_narratives(signal))
    target_polarity = sentiment_polarity(signal)
    target_id = signal.get("id")
    target_source = signal.get("source_id")
    if not target_tickers and not target_narratives:
        return 0.2
    confirming = set()
    if target_source is not None:
        confirming.add(target_source)
    for other in recent_signals or []:
        if other.get("id") == target_id: continue
        ot = set(extract_tickers(other))
        on = set(extract_narratives(other))
        tm = bool(target_tickers and ot and (target_tickers & ot))
        nm = bool(target_narratives and on and (target_narratives & on))
        if not (tm or nm): continue
        if sentiment_polarity(other) != target_polarity: continue
        os_ = other.get("source_id")
        if os_ is not None:
            confirming.add(os_)
    n = len(confirming)
    if n <= 1: return 0.4
    return min(1.0, 0.4 + 0.15 * (n - 1) + 0.05 * max(0, n - 3))


TYPE_WEIGHTS = {
    "insider": 0.85, "earnings": 0.85, "guidance": 0.90,
    "analyst": 0.55, "macro": 0.75, "industry": 0.70, "crypto": 0.65,
    "news": 0.40, "social": 0.25,
}


def _primary_ticker(tickers, watchlist=None):
    """Pick most important ticker from list (not just first)."""
    if not tickers:
        return None
    best = tickers[0]
    best_s = _ticker_importance(best, watchlist)
    for t in tickers[1:]:
        s = _ticker_importance(t, watchlist)
        if s > best_s:
            best_s = s
            best = t
    return best


def score_market_impact(signal, watchlist=None):
    tickers = extract_tickers(signal)
    primary = _primary_ticker(tickers, watchlist)
    ticker_score = _ticker_importance(primary, watchlist=watchlist)
    sig_type = derive_signal_type(signal)
    type_w = TYPE_WEIGHTS.get(sig_type, 0.5)
    raw = signal.get("score", 0.5)
    try:
        mag = max(0.1, min(1.0, float(raw)))
    except (TypeError, ValueError):
        mag = 0.5
    return ticker_score * 0.45 + type_w * 0.30 + mag * 0.25


def score_regime_relevance(signal, regime_info):
    sig_type = derive_signal_type(signal)
    polarity = sentiment_polarity(signal)
    credit = (regime_info or {}).get("credit", {}) or {}
    credit_class = str(credit.get("overall", "NORMAL")).upper() if isinstance(credit, dict) else "NORMAL"
    base = 0.55
    if sig_type == "insider":
        if polarity == "positive":
            base = 0.85
            if credit_class in ("STRESSED", "CRISIS"):
                base = min(1.0, base + 0.10)
        elif polarity == "negative":
            if credit_class == "TIGHT": base = 0.80
            elif credit_class in ("STRESSED", "CRISIS"): base = 0.50
            else: base = 0.60
    elif sig_type in ("earnings", "guidance"): base = 0.85
    elif sig_type == "macro": base = 0.75
    elif sig_type == "industry": base = 0.70
    elif sig_type == "analyst": base = 0.50
    elif sig_type == "crypto": base = 0.55
    elif sig_type == "news": base = 0.40
    elif sig_type == "social": base = 0.25
    return base


def score_materiality(signal, recent_signals_24h=None, recent_signals_72h=None,
                       regime_info=None, watchlist=None):
    novelty = score_novelty(signal, recent_signals_24h or [])
    cross_conf = score_cross_confirmation(signal, recent_signals_72h or recent_signals_24h or [])
    market_impact = score_market_impact(signal, watchlist=watchlist)
    regime_rel = score_regime_relevance(signal, regime_info or {})
    composite = novelty * cross_conf * market_impact * regime_rel
    noise = _is_noise(signal)
    if noise:
        composite *= 0.1
    quality = composite ** 0.25 if composite > 0 else 0
    return {
        "composite": composite, "quality": quality,
        "novelty": novelty, "cross_confirmation": cross_conf,
        "market_impact": market_impact, "regime_relevance": regime_rel,
        "noise": noise,
        "_derived": {
            "tickers": extract_tickers(signal),
            "narratives": extract_narratives(signal),
            "polarity": sentiment_polarity(signal),
            "signal_type": derive_signal_type(signal),
        }
    }


def format_materiality(score_dict, width=10):
    s = score_dict
    def bar(v):
        f = int(v * width)
        return "#" * f + "." * (width - f)
    noise_tag = " [NOISE]" if s.get("noise") else ""
    return (
        "composite: " + ("%.3f" % s["composite"]) + "  (quality: " + ("%.2f" % s["quality"]) + ")" + noise_tag + "\n"
        "  novelty:        " + ("%.2f" % s["novelty"]) + "  " + bar(s["novelty"]) + "\n"
        "  cross-conf:     " + ("%.2f" % s["cross_confirmation"]) + "  " + bar(s["cross_confirmation"]) + "\n"
        "  market_impact:  " + ("%.2f" % s["market_impact"]) + "  " + bar(s["market_impact"]) + "\n"
        "  regime_fit:     " + ("%.2f" % s["regime_relevance"]) + "  " + bar(s["regime_relevance"])
    )
