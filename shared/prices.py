"""Price data wrapper. Thin abstraction over yfinance so we can swap
in Polygon/Tiingo later without touching downstream code.

Returns None on failures - downstream must handle gracefully.
"""

import logging as _logging
from datetime import UTC, datetime, timedelta

_logging.getLogger("yfinance").setLevel(_logging.CRITICAL)
# Also suppress yfinance's print() to stdout for missing tickers
import contextlib
from typing import Any

import yfinance.utils as _yfu

with contextlib.suppress(Exception):
    _yfu.get_yf_logger().setLevel(_logging.CRITICAL)

import yfinance as yf

# ============================================================================
# Cache info/calendar pour réduire les appels yfinance lourds (SOCLE S1c #111).
# TTL court (1h) — les fundamentals bougent rarement intraday.
# ============================================================================
_INFO_CACHE: dict[str, tuple[dict, float]] = {}
_INFO_TTL_SEC = 3600.0
_CALENDAR_CACHE: dict[str, tuple[Any, float]] = {}
_CALENDAR_TTL_SEC = 21600.0  # 6h (earnings annoncés rarement updated intraday)

# ============================================================================
# Cache prix EUR + native (cure P0-1 audit (3) 12/06).
# Déplacé depuis dashboard/render.py — un cache prix au-dessus de get_current_price*
# n'a aucune raison de vivre dans la couche présentation (anti-pattern reconnu
# dans 3 commentaires inline sans correction depuis plusieurs sessions :
# shared/macro_state.py:92, intelligence/over_cap_monitor.py:166, intelligence/
# portfolio_grade.py:96). Le test test_no_shared_dashboard_import enforce
# désormais qu'aucun module shared/ ne peut importer dashboard.*.
#
# TTL 30 min : throttle yfinance partagé entre dashboard + price_monitor
# (même IP / même lib → un ban toucherait les deux).
# ============================================================================
_PX_CACHE: dict[str, tuple[float, float]] = {}
_PX_CACHE_NATIVE: dict[str, tuple[float, float]] = {}
_PX_TTL = 1800.0


def _cached_price_eur(ticker: str) -> float | None:
    """Source de prix EUR throttlée (TTL 30 min) au-dessus de get_current_price_in_eur.

    Le dashboard monkeypatche `asymmetry._get_current_price` sur cette fonction
    dans `render()` pour que le process dashboard ne matraque pas yfinance.
    Le process du bot (price_monitor) n'est pas affecté — ils partagent l'IP/lib
    mais pas le cache (chacun son process).
    """
    import time as _t

    now = _t.monotonic()
    hit = _PX_CACHE.get(ticker)
    if hit is not None and now - hit[1] < _PX_TTL:
        return hit[0]
    try:
        px = get_current_price_in_eur(ticker)
    except Exception:
        px = None
    if px is not None:
        _PX_CACHE[ticker] = (float(px), now)
        return float(px)
    return hit[0] if hit is not None else None


def _cached_price_native(ticker: str) -> float | None:
    """Prix NATIVE currency throttlé (TTL 30 min). JPY pour .T, KRW pour .KS,
    USD pour US, etc.

    Pour comparer aux `stop_price`/`target_full`/`target_partial` qui sont
    stockés en native currency (cf memory currency_native_invariant).
    Bug fix 31/05 : `_theses()` utilisait `_cached_price_eur` pour comparer à
    stop/tgt native → %.absurdes (4063.T target +23876%, 000660.KS target
    +175408%). Solidified par décision Olivier currency-native-invariant.
    """
    import time as _t

    now = _t.monotonic()
    hit = _PX_CACHE_NATIVE.get(ticker)
    if hit is not None and now - hit[1] < _PX_TTL:
        return hit[0]
    try:
        px = get_current_price(ticker)
    except Exception:
        px = None
    if px is not None:
        _PX_CACHE_NATIVE[ticker] = (float(px), now)
        return float(px)
    return hit[0] if hit is not None else None


def get_info(ticker: str) -> dict:
    """Gateway canonique pour yfinance Ticker.info (fundamentals + métadonnées).

    Cache mémoire avec TTL 1h. Throttle anti-ban yfinance partagé avec
    get_current_price (même module). Consumers : ticker_names (shortName),
    review._fetch_valuation (PE/marketCap), analyze.fetch_stock_data
    (revenueGrowth + fallbacks), bot/jobs/daily.resolve_journal (price now).

    Retourne dict vide si fetch fail (jamais None — consumers utilisent .get()).
    """
    import time as _t
    now = _t.monotonic()
    cached = _INFO_CACHE.get(ticker)
    if cached is not None and now - cached[1] < _INFO_TTL_SEC:
        return cached[0]
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}
    _INFO_CACHE[ticker] = (info, now)
    return info


def get_analyst_consensus(ticker: str) -> dict | None:
    """Gateway canonique consensus analyst targets via yfinance .info.

    Wire 12/06/2026 : substitut gratuit à LSEG/FMP (couverture FMP free
    tier = 19% du book vs yfinance .info = 100% pour PRESAGE).

    Returns dict ou None si pas couvert / fetch fail :
    {
        "ticker": str,
        "target_mean": float,       # consensus moyen
        "target_median": float | None,
        "target_high": float,
        "target_low": float,
        "n_analysts": int,          # nombre d'opinions
        "recommendation_key": str,  # "buy" / "hold" / "sell" / etc.
        "recommendation_mean": float,  # 1=Strong Buy, 5=Strong Sell
        "currency": str,            # devise native du listing
        "asof": str,                # ISO timestamp fetch
        "source": "yfinance",
    }

    Prix en native currency du ticker (USD pour US, JPY pour .T, etc.).
    """
    info = get_info(ticker)
    if not info:
        return None
    tm = info.get("targetMeanPrice")
    n = info.get("numberOfAnalystOpinions")
    if not tm or not n:
        return None
    from datetime import UTC as _UTC, datetime as _dt
    return {
        "ticker": ticker.upper(),
        "target_mean": float(tm),
        "target_median": float(info["targetMedianPrice"]) if info.get("targetMedianPrice") else None,
        "target_high": float(info.get("targetHighPrice") or 0) or None,
        "target_low": float(info.get("targetLowPrice") or 0) or None,
        "n_analysts": int(n),
        "recommendation_key": str(info.get("recommendationKey") or ""),
        "recommendation_mean": float(info.get("recommendationMean") or 0) or None,
        "currency": str(info.get("currency") or ""),
        "asof": _dt.now(_UTC).isoformat(),
        "source": "yfinance",
    }


def get_calendar(ticker: str) -> Any:
    """Gateway canonique pour yfinance Ticker.calendar (earnings dates).

    Cache 6h. Earnings dates publiés à fréquence trimestrielle, refresh
    rare intraday justifié.
    """
    import time as _t
    now = _t.monotonic()
    cached = _CALENDAR_CACHE.get(ticker)
    if cached is not None and now - cached[1] < _CALENDAR_TTL_SEC:
        return cached[0]
    try:
        cal = yf.Ticker(ticker).calendar
    except Exception:
        cal = None
    _CALENDAR_CACHE[ticker] = (cal, now)
    return cal


# Cache fundamentals DataFrames (financials, balance_sheet, cashflow).
# TTL 24h — publiés trimestriellement, refresh intraday inutile.
_FUNDAMENTALS_CACHE: dict[tuple[str, str], tuple[Any, float]] = {}
_FUNDAMENTALS_TTL_SEC = 86400.0


def _get_fundamental_df(ticker: str, attr: str) -> Any:
    import time as _t
    now = _t.monotonic()
    key = (ticker, attr)
    cached = _FUNDAMENTALS_CACHE.get(key)
    if cached is not None and now - cached[1] < _FUNDAMENTALS_TTL_SEC:
        return cached[0]
    try:
        df = getattr(yf.Ticker(ticker), attr)
    except Exception:
        df = None
    _FUNDAMENTALS_CACHE[key] = (df, now)
    return df


def get_financials(ticker: str) -> Any:
    """yfinance Ticker.financials (annual income statement DataFrame). Cache 24h."""
    return _get_fundamental_df(ticker, "financials")


def get_balance_sheet(ticker: str) -> Any:
    """yfinance Ticker.balance_sheet (annual DataFrame). Cache 24h."""
    return _get_fundamental_df(ticker, "balance_sheet")


def get_cashflow(ticker: str) -> Any:
    """yfinance Ticker.cashflow (annual DataFrame). Cache 24h."""
    return _get_fundamental_df(ticker, "cashflow")


# Seuil sanity outlier price (#144 cure source 12/06/2026) : un fetch yfinance
# qui devie de >50% du median des 7 derniers prix CLEAN historiques est suspect
# (KLAC bug 11/06 : 213 USD -> 2411 USD x11 sans split). On audit append-only
# avec source="yfinance:outlier" pour traçabilite, mais on REFUSE de retourner
# l'outlier (le caller voit None -> fail-closed downstream). Splits annonces
# legitimes seront aussi rejetes (rares, manuels a corriger), c'est le prix de
# l'integrite. Cf TODO #144 v2 si false-positives observes en pratique.
_OUTLIER_RATIO = 0.5  # 50% delta vs median (1.5x ou 0.67x = trigger)
_OUTLIER_MIN_HISTORY = 3  # < 3 points clean -> trust (premiere ingestion)
_OUTLIER_LOOKBACK = 7  # comparer au median des N derniers prix clean


def _last_clean_median(ticker: str) -> float | None:
    """Median des closes daily yfinance des _OUTLIER_LOOKBACK derniers jours.

    Pourquoi pas price_history live : si le feed est casse depuis N polls,
    price_history live est sature d'outliers et le median devient lui-meme
    l'outlier. yfinance daily history (par appel separe period="N+5d") porte
    la timeline calendaire ; median sur 7 points resiste a <=3 outliers
    consecutifs ce qui couvre les cas typiques (1-2 jours de bug feed).

    Returns None si <_OUTLIER_MIN_HISTORY closes valides.
    """
    try:
        t = yf.Ticker(ticker)
        # period suffisant : daily window N+5d pour absorber weekends/holidays
        hist = t.history(period=f"{_OUTLIER_LOOKBACK + 5}d", interval="1d")
        closes = [float(c) for c in hist["Close"].dropna()]
        # On exclut le dernier point (= le candidat lui-meme si fetche en meme
        # temps) pour comparer le fresh contre le passe propre, pas contre lui.
        clean = closes[:-1][-_OUTLIER_LOOKBACK:]
    except Exception:
        return None
    if len(clean) < _OUTLIER_MIN_HISTORY:
        return None
    s = sorted(clean)
    n = len(s)
    return s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2


def _is_outlier(candidate: float, median: float | None) -> bool:
    if median is None or median <= 0:
        return False
    ratio = abs(candidate / median - 1)
    return ratio > _OUTLIER_RATIO


def get_current_price(ticker: str) -> float | None:
    """Latest close price. Returns float or None.

    M1 doctrine (07/06 nuit++) : apres fetch live success, persist
    append-only dans price_history (asof + source). Permet freshness
    queryable + serie historique pour attribution causale 2x2.

    Cure source #144 (12/06) : sanity check contre outlier feed yfinance.
    Si le fetch devie de >50% du median des 7 derniers prix clean, on
    persiste l'observation avec source="yfinance:outlier" (audit append-only)
    MAIS on retourne None pour que le caller passe en fail-closed downstream
    (P&L, MV, perf "&mdash;" plutot que faux nombre confiant).
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d", interval="1d")
        closes = hist["Close"].dropna()
        if closes.empty:
            return None
        price = float(closes.iloc[-1])

        # Sanity check pre-persist : compare au median des prix clean recents.
        median = _last_clean_median(ticker)
        outlier = _is_outlier(price, median)

        # M1 persist append-only (silent-miss L7 si DB down -- ne casse pas fetch).
        # Persiste TOUJOURS (audit), avec source distincte si outlier.
        try:
            from shared.storage import insert_price_observation
            currency = get_currency_for_ticker(ticker)
            insert_price_observation(
                ticker=ticker, price_native=price, currency=currency,
                source="yfinance:outlier" if outlier else "yfinance",
            )
        except Exception:
            pass

        if outlier:
            # Log warning pour audit live ; le caller verra None -> fail-closed.
            import logging as _lg
            _lg.getLogger(__name__).warning(
                "price outlier suspect %s : fresh=%.4f median7=%.4f ratio=%.2f -- returned None",
                ticker, price, median or 0.0, abs(price / (median or price) - 1),
            )
            return None
        return price
    except Exception as e:
        print(f"price fetch error for {ticker}: {e}")
        return None


def get_close_on(ticker: str, date_str: str) -> float | None:
    """Close price on `date_str` (YYYY-MM-DD), or next trading day if
    weekend/holiday (yfinance auto-aligne). None si rien dans 7j (delisted /
    suspended / data gap).

    Use case : resolution de predictions doit utiliser le close du target_date
    exact, pas "current price quand le cron tourne" (bug ground-truth pre-31/05
    qui faisait que les resolves matinaux US tombaient sur close T-1)."""
    try:
        start = datetime.strptime(date_str, "%Y-%m-%d")
        end = (start + timedelta(days=7)).strftime("%Y-%m-%d")
        d = yf.Ticker(ticker).history(
            start=date_str, end=end, interval="1d", auto_adjust=False
        )
        closes = d["Close"].dropna()
        if closes.empty:
            return None
        return float(closes.iloc[0])
    except Exception:
        return None


def get_fx_rate_on(from_cur: str, to_cur: str, date_str: str) -> float | None:
    """Historical FX rate `from_cur -> to_cur` ON `date_str` (YYYY-MM-DD).

    Use case : resolution bias_events / track record retrospectif demande
    FX-coherent aux 2 dates (event + horizon). Sans ca, la derive FX entre
    les 2 dates pollue le delta_signed.

    Strategie : tente pair direct `{from}{to}=X` puis inverse `{to}{from}=X`
    (yfinance ne quote que la direction majeure). 7j window pour absorber
    weekend/holiday. None si rien (PAS de fallback hardcoded ici : caller
    decide -- contrairement a get_fx_rate qui sert le live courant)."""
    if from_cur == to_cur:
        return 1.0
    try:
        start = datetime.strptime(date_str, "%Y-%m-%d")
        end = (start + timedelta(days=7)).strftime("%Y-%m-%d")
        for pair, invert in [
            (f"{from_cur}{to_cur}=X", False),
            (f"{to_cur}{from_cur}=X", True),
        ]:
            try:
                d = yf.Ticker(pair).history(
                    start=date_str, end=end, interval="1d", auto_adjust=False
                )
                closes = d["Close"].dropna()
                if not closes.empty:
                    rate = float(closes.iloc[0])
                    return 1.0 / rate if invert else rate
            except Exception:
                continue
    except Exception:
        return None
    return None


def get_close_on_in_eur(ticker: str, date_str: str) -> float | None:
    """Close du ticker ON `date_str` converti en EUR via FX-coherent a la
    MEME date (cf [[currency-native-invariant]] : prix stockes NATIVE, on
    convertit cote consumer).

    Used by bias_events resolution + track record retrospectif. None si
    NATIVE close manque OU FX rate manque (caller leve MissingDataError --
    JAMAIS default silencieux, cf charte invariant)."""
    native_close = get_close_on(ticker, date_str)
    if native_close is None:
        return None
    currency = get_currency_for_ticker(ticker)
    if currency == "EUR":
        return native_close
    fx_rate = get_fx_rate_on(currency, "EUR", date_str)
    if fx_rate is None:
        return None
    return native_close * fx_rate


# ===== FX CONVERSION LAYER (Phase 1: hardcoded constants, Phase 2: SQLite-cached) =====

# Base currency = user portfolio currency (PEA/TR account)
BASE_CURRENCY = "USD"  # Day 11 ADR 004 (was "EUR" pre-migration)

# Ticker suffix -> quote currency mapping
SUFFIX_TO_CURRENCY = {
    ".T": "JPY",  # Tokyo
    ".KS": "KRW",  # Korea (Seoul)
    ".AS": "EUR",  # Amsterdam
    ".PA": "EUR",  # Paris
    ".DE": "EUR",  # Germany
    ".MI": "EUR",  # Milan
    ".L": "GBP",  # London
    ".AX": "AUD",  # Australia
    ".TO": "CAD",  # Toronto
    ".ST": "SEK",  # Stockholm
    ".HK": "HKD",  # Hong Kong
    ".SS": "CNY",  # Shanghai
    ".SZ": "CNY",  # Shenzhen
}

# Hardcoded fx rates to EUR (Phase 1 R3)
# Derived empirically from broker observations 2026-05-16
# JPY/EUR=0.005467 (1 JPY = 0.0055 EUR; 38410 JPY = €210 -> Lasertec catch)
# KRW/EUR=0.000591 (1 KRW = 0.00059 EUR; 1819000 KRW = €1075 -> SK Hynix catch)
# USD/EUR=0.858 (empirically calibrated 2026-05-16 vs broker TSM €347.5, TER €289.7)
# TODO Phase 2 R1: migrate to fx_rates SQLite table + daily refresh cron
HARDCODED_FX_TO_EUR = {
    "EUR": 1.0,
    "JPY": 0.005467,
    "KRW": 0.000591,
    "USD": 0.858,
    "GBP": 1.17,
    "AUD": 0.61,
    "CAD": 0.68,
    "SEK": 0.087,
    "HKD": 0.118,
    "CNY": 0.128,
}


HARDCODED_FX_TO_USD: dict[str, float] = {
    cur: rate / HARDCODED_FX_TO_EUR["USD"] for cur, rate in HARDCODED_FX_TO_EUR.items()
}


# Live FX cache : TTL 4h (FX bouge lentement intraday vs ban-risk yfinance)
_FX_TTL_SEC = 14400
_FX_CACHE: dict[tuple[str, str], tuple[float, datetime]] = {}
# Last successful live fetch per pair (independent from cache : survit a
# l'expiration TTL pour permettre fx_freshness() de signaler la staleness).
_FX_LIVE_LAST_SUCCESS: dict[tuple[str, str], datetime] = {}
_log = _logging.getLogger(__name__)


def reset_caches() -> None:
    """Vide tous les caches in-process (prix natif/EUR, info, FX, last-success).

    Source UNIQUE de reset (L1) : ne pas clear les dicts internes ailleurs.
    Usage : fixture autouse de conftest pour l'isolation inter-tests. Sans ça,
    un cache (FX surtout) porté d'un test a l'autre faisait diverger les
    agregats somme-parties au-dela de la tolerance -> flaky ordre-dependant
    (#147 : _FX_CACHE/_PX_CACHE non resetes entre tests)."""
    _PX_CACHE.clear()
    _PX_CACHE_NATIVE.clear()
    _INFO_CACHE.clear()
    _FX_CACHE.clear()
    _FX_LIVE_LAST_SUCCESS.clear()


def _fetch_fx_live(from_cur: str, to_cur: str) -> float | None:
    """Fetch FX rate live via yfinance. Tries direct pair `{from}{to}=X` then
    inverted `{to}{from}=X` (since yfinance only quotes the major direction
    for many pairs). Returns None on failure."""
    if from_cur == to_cur:
        return 1.0
    for pair, invert in [
        (f"{from_cur}{to_cur}=X", False),
        (f"{to_cur}{from_cur}=X", True),
    ]:
        try:
            d = yf.Ticker(pair).history(period="2d", interval="1d", auto_adjust=False)
            closes = d["Close"].dropna()
            if not closes.empty:
                rate = float(closes.iloc[-1])
                return 1.0 / rate if invert else rate
        except Exception:
            continue
    return None


def fx_freshness(from_cur: str, to_cur: str = "EUR") -> dict[str, Any]:
    """Etat de fraicheur du pair FX `from_cur -> to_cur` pour affichage dashboard.

    Retourne un dict avec :
    - source : 'live_cached' (cache vivant, TTL not expired)
             | 'live_stale_cache' (live deja fetchee mais TTL expire, le prochain
               appel re-fetchera)
             | 'fallback' (live n'a jamais reussi, on tape sur HARDCODED_FX)
             | 'never_queried' (rien n'a encore appele get_fx_rate sur ce pair)
    - last_live_at : datetime ISO du dernier live success, None si jamais
    - age_seconds : int, secondes depuis last_live_at, None si jamais
    - ttl_seconds : int, _FX_TTL_SEC (4h actuel)

    Use case : dashboard affiche "USD/EUR live as of HH:MM" si live_cached, ou
    "USD/EUR HARDCODED depuis 16/05 (fallback)" si fallback, ou un badge stale
    si live_stale_cache.
    """
    if from_cur == to_cur:
        return {"source": "identity", "last_live_at": None, "age_seconds": 0, "ttl_seconds": _FX_TTL_SEC}
    key = (from_cur, to_cur)
    last_live = _FX_LIVE_LAST_SUCCESS.get(key)
    now = datetime.now(UTC)
    if last_live is None:
        return {"source": "never_queried", "last_live_at": None, "age_seconds": None, "ttl_seconds": _FX_TTL_SEC}
    age = int((now - last_live).total_seconds())
    cached = _FX_CACHE.get(key)
    if cached is not None and age < _FX_TTL_SEC:
        return {"source": "live_cached", "last_live_at": last_live.isoformat(), "age_seconds": age, "ttl_seconds": _FX_TTL_SEC}
    return {"source": "live_stale_cache", "last_live_at": last_live.isoformat(), "age_seconds": age, "ttl_seconds": _FX_TTL_SEC}


def fx_is_stale(from_cur: str, to_cur: str = "EUR", max_age_seconds: int = 86400) -> bool:
    """True si le dernier live fetch de ce pair date de plus de `max_age_seconds`
    (default 24h). Si jamais fetche live -> True (fallback en cours).

    Usage : dashboard affiche un warning sur les chiffres EUR derives si
    fx_is_stale("USD") returns True."""
    if from_cur == to_cur:
        return False
    key = (from_cur, to_cur)
    last_live = _FX_LIVE_LAST_SUCCESS.get(key)
    if last_live is None:
        return True
    age = (datetime.now(UTC) - last_live).total_seconds()
    return age > max_age_seconds


def get_currency_for_ticker(ticker: str) -> str:
    """Infer quote currency from ticker suffix. Defaults to USD (US listing, no suffix)."""
    for suffix, cur in SUFFIX_TO_CURRENCY.items():
        if ticker.endswith(suffix):
            return cur
    return "USD"


def get_fx_rate(from_cur: str, to_cur: str = "EUR") -> float | None:
    """Return fx rate from `from_cur` to `to_cur`.

    Phase 2 (R1): tente live yfinance (cache _FX_TTL_SEC), fallback sur
    HARDCODED_FX_TO_EUR si live indispo. Le fallback preserve l'ancien
    comportement Phase 1.
    """
    if from_cur == to_cur:
        return 1.0

    key = (from_cur, to_cur)
    now = datetime.now(UTC)
    cached = _FX_CACHE.get(key)
    if cached is not None:
        rate, fetched_at = cached
        if (now - fetched_at).total_seconds() < _FX_TTL_SEC:
            return rate

    live = _fetch_fx_live(from_cur, to_cur)
    if live is not None:
        _FX_CACHE[key] = (live, now)
        _FX_LIVE_LAST_SUCCESS[key] = now
        # M1 persist append-only (silent-miss L7)
        try:
            from shared.storage import insert_fx_observation
            insert_fx_observation(
                base=from_cur, quote=to_cur, rate=live, source="yfinance",
            )
        except Exception:
            pass
        return live

    _log.warning(f"FX live fetch failed for {from_cur}->{to_cur}, fallback hardcoded")
    if to_cur == "EUR":
        return HARDCODED_FX_TO_EUR.get(from_cur)
    from_eur = HARDCODED_FX_TO_EUR.get(from_cur)
    to_eur = HARDCODED_FX_TO_EUR.get(to_cur)
    if from_eur is None or to_eur is None or to_eur == 0:
        return None
    return from_eur / to_eur


def get_current_price_in(ticker: str, target_cur: str) -> float | None:
    """Return current price converted to ``target_cur``.

    Generic helper supporting any currency in HARDCODED_FX_TO_EUR.
    Day 11 ADR 004: parametric core for USD/EUR dual-currency support.
    """
    raw_price = get_current_price(ticker)
    if raw_price is None:
        return None
    cur = get_currency_for_ticker(ticker)
    if cur == target_cur:
        return raw_price
    fx = get_fx_rate(cur, target_cur)
    if fx is None:
        return None
    return raw_price * fx


def get_current_price_in_usd(ticker: str) -> float | None:
    """Return current price converted to USD (canonical, Day 11 ADR 004)."""
    return get_current_price_in(ticker, "USD")


def get_current_price_in_eur(ticker: str) -> float | None:
    """Return current price converted to EUR (legacy display/secondary, ADR 004).

    Preserved for backward compatibility during USD migration. New code
    should prefer get_current_price_in_usd or get_current_price_in.
    """
    return get_current_price_in(ticker, "EUR")


def get_price_on_date(ticker: str, date: str | datetime) -> tuple[str | None, float | None]:
    """Close price on or after `date` (str YYYY-MM-DD or datetime).
    Falls back to next trading day. Returns (actual_date_str, price) or (None, None).
    """
    if isinstance(date, datetime):
        date_str = date.strftime("%Y-%m-%d")
        target = date
    else:
        date_str = str(date)[:10]
        try:
            target = datetime.fromisoformat(date_str)
        except Exception:
            return (None, None)

    end = (target + timedelta(days=10)).strftime("%Y-%m-%d")
    try:
        t = yf.Ticker(ticker)
        hist = t.history(start=date_str, end=end, interval="1d")
        if hist.empty:
            return (None, None)
        first = hist.iloc[0]
        actual = first.name.strftime("%Y-%m-%d")
        return (actual, float(first["Close"]))
    except Exception as e:
        print(f"price fetch error for {ticker} @ {date_str}: {e}")
        return (None, None)


def get_returns(ticker: str, baseline_date: str, current_date: str | None = None) -> dict[str, Any]:
    """Return between baseline_date and current_date (default now)."""
    b_actual, b_price = get_price_on_date(ticker, baseline_date)
    if b_price is None:
        return {"error": f"no baseline price for {ticker} @ {baseline_date}"}
    c_actual: str | None
    if current_date is None:
        c_price = get_current_price(ticker)
        c_actual = datetime.now(UTC).strftime("%Y-%m-%d")
    else:
        c_actual, c_price = get_price_on_date(ticker, current_date)
    if c_price is None:
        return {"error": f"no current price for {ticker}"}
    return {
        "ticker": ticker,
        "baseline_date": b_actual,
        "baseline_price": b_price,
        "current_date": c_actual,
        "current_price": c_price,
        "return_pct": (c_price - b_price) / b_price,
    }


if __name__ == "__main__":
    print("Test get_current_price(NVDA):")
    p = get_current_price("NVDA")
    print(f"  current = ${p:.2f}" if p else "  FAILED")

    print("Test get_price_on_date(NVDA, 2026-04-11):")
    d, p = get_price_on_date("NVDA", "2026-04-11")
    print(f"  {d} = ${p:.2f}" if p else "  FAILED")

    print("Test get_returns(NVDA, 2026-02-11):")
    r = get_returns("NVDA", "2026-02-11")
    if "error" in r:
        print(f"  ERROR: {r['error']}")
    else:
        print(
            f"  {r['ticker']}: {r['baseline_date']} ${r['baseline_price']:.2f} -> {r['current_date']} ${r['current_price']:.2f} = {r['return_pct']:+.1%}"
        )


def ensure_price_history(
    ticker: str,
    start: str | datetime,
    end: str | datetime,
    min_coverage_pct: float = 0.7,
) -> Any:  # pd.DataFrame
    """Garantit que price_history a des observations pour ticker dans [start, end].

    Doctrine Axe 5 QUALITY_BAR : source unique de verite = price_history.
    Au lieu de yfinance live a chaque query (ban risk + lent), on backfill
    one-shot puis on lit DB ensuite.

    Strategie :
    1. Query existing observations dans la fenetre
    2. Coverage = N_obs / N_business_days_expected
    3. Si coverage < min_coverage_pct -> fetch yfinance batch + persist
    4. Returns DataFrame complet (index=date, colonnes=[price_native, currency])

    Args:
        ticker, start, end : fenetre
        min_coverage_pct : seuil declenchant le backfill (default 0.7 = 70%)

    Returns:
        pd.DataFrame avec index DatetimeIndex, colonnes ['price_native', 'currency'].
        DataFrame vide si fetch fail + DB vide.

    Examples:
        # First call backfills, persistent thereafter
        df = ensure_price_history('NVDA', '2020-01-01', '2026-06-07')
    """
    try:
        import pandas as pd

        from shared import storage
    except ImportError as e:
        _log.warning(f"ensure_price_history deps missing: {e}")
        return None

    # Normalize dates
    if isinstance(start, datetime):
        start_str = start.strftime("%Y-%m-%d")
        start_dt = start
    else:
        start_str = str(start)[:10]
        start_dt = datetime.fromisoformat(start_str)
    if isinstance(end, datetime):
        end_str = end.strftime("%Y-%m-%d")
        end_dt = end
    else:
        end_str = str(end)[:10]
        end_dt = datetime.fromisoformat(end_str)

    # Query existing observations in window
    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT asof, price_native, currency FROM price_history "
                "WHERE ticker = ? AND asof >= ? AND asof <= ? "
                "ORDER BY asof",
                (ticker.upper(), start_str, end_str + "T23:59:59"),
            ).fetchall()
    except Exception as e:
        _log.warning(f"ensure_price_history DB read failed for {ticker}: {e}")
        rows = []

    # Business days expected (rough : 252 / year)
    n_days = (end_dt - start_dt).days
    n_business_days_expected = max(1, int(n_days * 252 / 365))
    n_obs = len(rows)
    coverage = n_obs / n_business_days_expected if n_business_days_expected else 0.0

    # Backfill if coverage low
    if coverage < min_coverage_pct:
        _log.info(
            f"ensure_price_history {ticker}: coverage {coverage:.0%} "
            f"({n_obs}/{n_business_days_expected}j) < {min_coverage_pct:.0%}, "
            "backfill yfinance"
        )
        try:
            t = yf.Ticker(ticker)
            hist = t.history(start=start_str, end=end_str, interval="1d", auto_adjust=False)
            if not hist.empty:
                currency = get_currency_for_ticker(ticker)
                # Build bulk batch + route via storage.insert_price_observations_bulk
                # (L1 single passerelle DB, discipline test_db_write_surface_is_frozen)
                bulk_rows = [
                    (
                        ticker.upper(),
                        date_idx.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                        float(close),
                        currency,
                        "yfinance_backfill",
                    )
                    for date_idx, close in hist["Close"].dropna().items()
                ]
                if bulk_rows:
                    storage.insert_price_observations_bulk(bulk_rows)
        except Exception as e:
            _log.warning(f"ensure_price_history backfill failed for {ticker}: {e}")

        # Re-query post-backfill
        try:
            with storage.db() as cx:
                rows = cx.execute(
                    "SELECT asof, price_native, currency FROM price_history "
                    "WHERE ticker = ? AND asof >= ? AND asof <= ? "
                    "ORDER BY asof",
                    (ticker.upper(), start_str, end_str + "T23:59:59"),
                ).fetchall()
        except Exception:
            pass

    # Build DataFrame
    if not rows:
        return pd.DataFrame(columns=["price_native", "currency"])
    df = pd.DataFrame(
        [{"asof": r[0], "price_native": r[1], "currency": r[2]} for r in rows]
    )
    # ISO8601 format=mixed gere les obs avec microsecondes (reconcile live) ET
    # sans (backfill yfinance) sans warning.
    df["asof"] = pd.to_datetime(df["asof"], format="ISO8601")
    df = df.set_index("asof").sort_index()
    return df


def get_price_window(ticker: str, start_date: str | datetime, end_date: str | datetime) -> Any:  # pd.DataFrame | None
    """Phase A4 — Daily closes between start and end (inclusive).
    Returns list of (date_str_YYYYMMDD, close_float). Empty list on failure.
    """
    if isinstance(start_date, datetime):
        start_str = start_date.strftime("%Y-%m-%d")
    else:
        start_str = str(start_date)[:10]
    if isinstance(end_date, datetime):
        end_str = end_date.strftime("%Y-%m-%d")
    else:
        end_str = str(end_date)[:10]
    try:
        t = yf.Ticker(ticker)
        hist = t.history(start=start_str, end=end_str, interval="1d")
        if hist.empty:
            return []
        return [(d.strftime("%Y-%m-%d"), float(c)) for d, c in hist["Close"].items()]
    except Exception as e:
        print(f"price window error for {ticker}: {e}")
        return []


from shared.datum import Datum

# === SOCLE Phase 1b : Gateway Datum (SPEC_SOCLE.md S3) =====================
# Cf HANDOFF_SOCLE.md S1 : prices.get() et fx() retournent JAMAIS un float nu.
# Tout consumer downstream doit recevoir un Datum (value, asof, source,
# confidence, parents=(), op=None, degraded).
#
# SLA freshness :
#   - price : green < 900s, amber < 3600s, sinon degraded
#   - fx    : green < 3600s, amber < 14400s, sinon degraded
# Ces seuils seront migrés vers config/freshness.yaml (L17) une fois la
# migration progressive des consumers achevée. V0 hardcodés ici pour pas
# proliférer la complexité tant que tracer-bullet validé.

_PRICE_GREEN_SEC = 900
_PRICE_AMBER_SEC = 3600
_FX_GREEN_SEC = 3600
_FX_AMBER_SEC = 14400


def _staleness_to_confidence(age_sec: float, green_sec: int, amber_sec: int) -> tuple[float, bool]:
    """Convertit l'age d'un input en (confidence, degraded).

    age <= green_sec        -> confidence=1.0, degraded=False
    green < age <= amber    -> confidence interpolée [1.0 -> 0.5], degraded=False
    age > amber_sec         -> confidence=0.4, degraded=True (fail-closed structurel)
    """
    if age_sec <= green_sec:
        return (1.0, False)
    if age_sec <= amber_sec:
        # interpolation linéaire entre green (conf=1.0) et amber (conf=0.5)
        ratio = (age_sec - green_sec) / max(1.0, (amber_sec - green_sec))
        return (1.0 - 0.5 * ratio, False)
    return (0.4, True)


def get(ticker: str) -> Datum | None:
    """SOCLE Gateway : retourne Datum[float] pour le prix d'un ticker.

    value     = price_native (float, devise du ticker)
    asof      = ISO timestamp de l'observation
    source    = "yfinance" (ou autre une fois multi-provider)
    confidence = decroit avec age (cf _staleness_to_confidence)
    parents   = () (leaf Datum -- sortie gateway, pas de parents)
    op        = None
    degraded  = True si age > _PRICE_AMBER_SEC

    Retourne None si fetch fail (le caller doit gerer -- pas de fallback).
    Le gateway append append-only dans price_history via get_current_price.
    """
    price = get_current_price(ticker)
    if price is None:
        return None
    # asof = maintenant (get_current_price vient de fetcher)
    # Une amelioration future : lire le timestamp REEL du fetch yfinance plutot
    # que le now -- mais yfinance retourne souvent T-1 close, donc on prend now
    # comme borne haute de la fraicheur (overestimes fresh, conservative).
    asof_dt = datetime.now(UTC)
    asof_iso = asof_dt.isoformat()
    confidence, degraded = _staleness_to_confidence(
        age_sec=0.0,  # juste fetche
        green_sec=_PRICE_GREEN_SEC,
        amber_sec=_PRICE_AMBER_SEC,
    )
    return Datum(
        value=price,
        asof=asof_iso,
        source="yfinance",
        confidence=confidence,
        degraded=degraded,
    )


def fx(base: str, quote: str = "EUR") -> Datum | None:
    """SOCLE Gateway : retourne Datum[float] pour le taux FX base->quote.

    Memes invariants que get(). Identity (base==quote) -> Datum(value=1.0, ...)
    """
    if base == quote:
        return Datum(
            value=1.0,
            asof=datetime.now(UTC).isoformat(),
            source="identity",
            confidence=1.0,
            degraded=False,
        )
    rate = get_fx_rate(base, quote)
    if rate is None:
        return None
    asof_iso = datetime.now(UTC).isoformat()
    confidence, degraded = _staleness_to_confidence(
        age_sec=0.0,
        green_sec=_FX_GREEN_SEC,
        amber_sec=_FX_AMBER_SEC,
    )
    return Datum(
        value=rate,
        asof=asof_iso,
        source="yfinance:fx",
        confidence=confidence,
        degraded=degraded,
    )
