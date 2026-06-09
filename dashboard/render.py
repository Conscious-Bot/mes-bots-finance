"""PRESAGE dashboard. Static-gen, READ-ONLY, REAL data.
Weights from positions.eur_invested (EUR cost basis). Sectors from theses.sector_thesis_id.
Perf as ratio % (currency-invariant). DB read-only; per-panel try/except. Leaflet geo."""

# Sprint 3 logos tickers : import + force-reload pour bypass cache sys.modules
# tant que serve.py n'est pas restart pour activer le nouveau watch.
import contextlib
import importlib
import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

import shared.ticker_logos as _ticker_logos_mod
from dashboard._scripts import (
    _APP_JS,
    _CSORT_JS,
    _CTA_JS,
    _DONUT_JS,
    _EU_SUFFIX,
    _FOOT_METHOD,
    _LOGO,
    _LOUPE_HTML,
    _MODE_BTN,
    _NAV,
    _SORT_JS,
    _THEME_INIT,
)
from dashboard._styles import _CSS, _DBA_CSS, _TH_CSS, _TOKENS_CSS
from intelligence import asymmetry as asym_mod

importlib.reload(_ticker_logos_mod)
_ticker_logo = _ticker_logos_mod.logo_html

# Reconciliation flags - known book/broker drifts not yet journaled.
# Clear an entry when reconciled via /position_sell + /position_buy.
RECONCILE_FLAGS: list[dict] = []


def _cfg() -> dict:
    try:
        loaded = yaml.safe_load(Path("config.yaml").read_text())
        return dict(loaded) if loaded else {}
    except Exception:
        return {}


_CFG = _cfg()
# Plafond ABSOLU pour markers display "above cap" (uniforme).
# Source unique : shared.sizing_caps.absolute_max_cap = cap c5 (sommet bride).
# Cap fin par conviction utilise dans panels qui ont la donnee theses.
from shared.sizing_caps import absolute_max_cap as _absolute_max_cap

POS_CAP = _absolute_max_cap() * 100
NARRATIVE_CAP = float(_CFG.get("style", {}).get("narrative_max_pct", 0.30)) * 100
DD_REDUCE = float(_CFG.get("risk", {}).get("drawdown_reduce_pct", 0.08)) * 100
DD_STOP = float(_CFG.get("risk", {}).get("drawdown_stop_pct", 0.20)) * 100
FX_USD = 0.858
REVIEWS = [
    ("2026-05-30", "Brier resolution (KPI#2)"),
    ("2026-05-30", "COHR review"),
    ("2026-06-16", "c1 orphans review (J+30)"),
]

OUTPUT = Path("dashboard/dashboard.html")
DB = "file:data/bot.db?mode=ro"

COUNTRY = {
    "TSM": "Taiwan",
    "TSEM": "Israel",
    "ASML": "Netherlands",
    "NVO": "Denmark",
    "ARM": "United Kingdom",
    "IFNNY": "Germany",
    "BABA": "China",
    "TCEHY": "China",
    "PDD": "China",
    "STM": "France",
}
SUFFIX = {
    ".KS": "Korea",
    ".T": "Japan",
    ".TW": "Taiwan",
    ".PA": "France",
    ".AS": "Netherlands",
    ".L": "United Kingdom",
    ".HK": "China",
    ".DE": "Germany",
    ".MI": "Italy",
    ".ST": "Sweden",
    ".AX": "Australia",
    ".TO": "Canada",
    ".SS": "China",
    ".SZ": "China",
    ".SW": "Switzerland",
}


_PX_CACHE: dict[str, tuple[float, float]] = {}
_PX_TTL = 1800.0  # 30 min: throttle yfinance (partage IP/lib avec price_monitor, evite le ban)

# Phase post-audit 07/06 : cache historique portfolio pour Performance panel.
# yfinance batch download ~2-4 sec, donc TTL 1h suffit (regen toutes 60s sinon
# crippling). Format : (pd.Series equity_curve, monotonic_timestamp).
_PORTFOLIO_HISTORY_CACHE: tuple | None = None
_PORTFOLIO_HISTORY_TTL = 3600.0  # 1h

# V3 07/06 : cache benchmark SPY pour comparaison Heimdall.
# Meme TTL que portfolio.
_BENCHMARK_HISTORY_CACHE: tuple | None = None
_BENCHMARK_TICKER = "SPY"


def _pct(x: float) -> str:
    """Autorite unique de format des poids de ligne (1 decimale)."""
    return f"{x:.1f}"


def _cached_price_eur(ticker: str) -> float | None:
    """Source de prix EUR du dashboard: throttle les fetchs live a un burst par TTL.

    Monkeypatche sur asymmetry._get_current_price dans render() pour que le process
    dashboard ne matraque pas yfinance (un ban toucherait aussi le price_monitor du
    bot, meme IP / meme lib). Le process du bot n'est pas affecte.
    """
    import time as _t

    now = _t.monotonic()
    hit = _PX_CACHE.get(ticker)
    if hit is not None and now - hit[1] < _PX_TTL:
        return hit[0]
    try:
        from shared.prices import get_current_price_in_eur

        px = get_current_price_in_eur(ticker)
    except Exception:
        px = None
    if px is not None:
        _PX_CACHE[ticker] = (float(px), now)
        return float(px)
    return hit[0] if hit is not None else None


_PX_CACHE_NATIVE: dict[str, tuple[float, float]] = {}


def _cached_price_native(ticker: str) -> float | None:
    """Prix NATIVE currency (JPY pour .T, KRW pour .KS, USD pour US, etc.).
    Pour comparer aux stop_price/target_full qui sont en NATIVE (cf memory
    currency_native_invariant). Bug fix 31/05 : _theses() utilisait
    _cached_price_eur pour comparer a stop/tgt native -> %.absurdes (4063.T
    target +23876%, 000660.KS target +175408%)."""
    import time as _t

    now = _t.monotonic()
    hit = _PX_CACHE_NATIVE.get(ticker)
    if hit is not None and now - hit[1] < _PX_TTL:
        return hit[0]
    try:
        from shared.prices import get_current_price

        px = get_current_price(ticker)
    except Exception:
        px = None
    if px is not None:
        _PX_CACHE_NATIVE[ticker] = (float(px), now)
        return float(px)
    return hit[0] if hit is not None else None


def _stop_distance_pct_native(ticker: str, stop_price: float | None) -> float | None:
    """Canonique : distance courant -> stop en %, calcul NATIVE vs NATIVE.

    Respecte [[currency-native-invariant]] : stop_price (et target_full,
    target_partial) sont stockes en native currency du ticker. Comparer a
    un current_price_eur produit des % absurdes (4063.T -11089%, 000660.KS
    target +175408% etc.). Helper canonique pour TOUS les sites qui calculent
    une distance pct vs un prix-these (stop/target/entry).

    Returns None si stop manquant, current introuvable, ou stop <= 0.
    """
    if not stop_price or stop_price <= 0:
        return None
    current = _cached_price_native(ticker)
    if current is None or current <= 0:
        return None
    return (current - stop_price) / current * 100


_DP_CACHE: dict[str, tuple[float | None, float]] = {}
_DP_TTL = 840.0


def _dp_pct(ticker: str) -> float | None:
    """Variation % 24h : close-to-close officiel via gateway prices canonique.

    Convention décidée 08/06 nuit (red-team Olivier) :
      - Source price_history (L1, alimentée par cron). NON yfinance local
        (bypass éliminé du callsite render.py).
      - Convention close-to-close : matche broker / Yahoo. Le ratio rolling-live
        (dernier tick intraday vs close veille) diverge selon timezone du marché :
          * Asia (KRX/TSE) à 14:21 FR : marchés fermés, dernier tick = close, diff ~0
          * EU (Paris/Amsterdam) à 14:21 CET : marchés ouverts, tick intraday, diff ≤0.3pp
          * US (NASDAQ) à 8:21 ET : pas ouvert, tick = pre-market, diff ≤0.4pp
        On REFUSE cette divergence convention-broker pour un panel "% 24h".
      - Fallback : si close du jour pas dispo (marché ouvert), prend dernier tick
        intraday (pour Asie c'est = close, pour EU/US c'est intraday accepté
        comme "best available" jusqu'au close réel à 22h+ FR).

    Returns None si moins de 2 jours de données (fail-closed L15).
    """
    import time as _t
    from datetime import UTC, datetime, timedelta

    now = _t.monotonic()
    hit = _DP_CACHE.get(ticker)
    if hit is not None and now - hit[1] < _DP_TTL:
        return hit[0]

    v: float | None = hit[0] if hit is not None else None
    try:
        from shared import storage
        with storage.db() as cx:
            cx.row_factory = None
            # 2 derniers jours de close (dernier tick par jour). Si marché Asia
            # déjà clos → tick = close réel. Si marché US/EU encore ouvert →
            # tick intraday, accepté comme best-available pour panel temps réel.
            rows = cx.execute("""
                WITH day_lasts AS (
                    SELECT price_native,
                           substr(asof, 1, 10) AS day,
                           ROW_NUMBER() OVER (
                               PARTITION BY substr(asof, 1, 10)
                               ORDER BY asof DESC
                           ) AS rn
                    FROM price_history WHERE ticker = ?
                )
                SELECT price_native, day FROM day_lasts WHERE rn = 1
                ORDER BY day DESC LIMIT 2
            """, (ticker,)).fetchall()
        if len(rows) >= 2 and rows[0][0] and rows[1][0]:
            v = round((rows[0][0] / rows[1][0] - 1.0) * 100.0, 1)
    except Exception:
        pass

    _DP_CACHE[ticker] = (v, now)
    return v


def _country(tk: str) -> str:
    if tk in COUNTRY:
        return COUNTRY[tk]
    for suf, c in SUFFIX.items():
        if tk.endswith(suf):
            return c
    return "United States"


def _q(sql: str) -> list:
    con = sqlite3.connect(DB, uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _err(e: Exception) -> str:
    return f'<div class="empty"><b>Query to adjust</b><span class="mono" style="font-size:14px">{type(e).__name__}: {str(e)[:130]}</span></div>'


def _tbar(
    value_pct: float | None,
    ticks: list[tuple[float, str | None]] | None = None,
    dot_color: str = "",
    dash_at: float | None = None,
    title: str = "",
    extra_class: str = "",
    stop_target_ends: bool = False,
    hover_pct: bool = True,
    data_attrs: dict[str, str] | None = None,
) -> str:
    """Canonical track bar (#91 signature unifie 03/06/2026).

    Une seule primitive visuelle pour TOUS les axes. Track + dot pour la
    valeur courante + 0/1/2+ ticks de reference. Remplace l'ancien gauge
    (axis + axis-mark losange + axis-target-tick).

    Args:
        value_pct : position du dot (0-100). None = pas de dot rendu.
        ticks : liste de (pct, optional_title). 0/1/2+ ticks acceptes.
        dot_color : '' (neutre ink) | 'acc' | 'warn' | 'bear'.
        dash_at : pct optionnel pour un tick en pointilles (ex: prix d'entree).
        title : tooltip texte sur le track.
        extra_class : classe supplementaire sur .tbar (ex: 'row-bar').

    Returns:
        str HTML <div class="tbar">...</div>
    """
    cls = f"tbar {extra_class}".strip()
    da = "".join(f' data-{k}="{v}"' for k, v in (data_attrs or {}).items())
    parts = [
        f'<div class="{cls}"'
        + da
        + (f' title="{title}"' if title else "")
        + ">"
    ]
    # Stop/target ends pour axes signature (red gauche, green droite)
    if stop_target_ends:
        parts.append('<div class="tbar-tick stop" style="left:0%" title="stop"></div>')
        parts.append('<div class="tbar-tick target" style="left:100%" title="target"></div>')
    for tick in (ticks or []):
        # Backward-compat : (pos, label) ou (pos, label, style)
        if len(tick) == 3:
            tp, tlbl, tstyle = tick
        else:
            tp, tlbl = tick
            tstyle = ""
        tp = max(0.0, min(100.0, tp))
        tt = f' title="{tlbl}"' if tlbl else ""
        tcls = "tbar-tick" + (f" {tstyle}" if tstyle else "")
        parts.append(f'<div class="{tcls}" style="left:{tp:.1f}%"{tt}></div>')
    if dash_at is not None:
        da = max(0.0, min(100.0, dash_at))
        parts.append(f'<div class="tbar-tick dash" style="left:{da:.1f}%"></div>')
    if value_pct is not None:
        v = max(0.0, min(100.0, value_pct))
        dot_cls = f" {dot_color}" if dot_color else ""
        parts.append(f'<div class="tbar-dot{dot_cls}" style="left:{v:.1f}%"></div>')
    if hover_pct:
        parts.append('<div class="tbar-hover-tip"></div>')
    parts.append("</div>")
    return "".join(parts)


def _position_axis(
    entry: float | None,
    stop: float | None,
    target: float | None,
    current: float | None,
    extra_class: str = "",
    pnl_position_pct: float | None = None,
) -> str:
    """Canonical position gauge (#91 unifie 03/06/2026, anchor-agnostique).

    Quatre repères, lecture immediate, zero second-guess :
    - LIMIT (stop) -> tick rouge a sa vraie distance neg vs `entry`
    - 0 (entry)    -> centre de l'axe, reference zero PnL
    - TARGET       -> tick vert a sa vraie distance pos vs `entry`
    - DOT          -> current price = signed PnL % vs `entry`

    SÉMANTIQUE DE `entry` (cf L29 09/06) : ce paramètre est l'ANCRE du zéro,
    pas le prix d'appel de thèse en tant que tel. La fonction est anchor-
    agnostique : passe ce que tu veux comme "zéro de la lecture". Pour la
    gauge canonique post-fix L29, les callers passent avg_cost_eur (le vrai
    coût utilisateur) et stop/target/current TOUS en EUR depuis BookLine →
    dot et tooltip racontent alors la même chose (pnl_position).

    Money-invariant (L28) : tous les 4 chiffres doivent vivre dans la MÊME
    devise. Caller responsable -- la fonction ne convertit pas.

    Returns "" si donnees insuffisantes (caller affiche son fallback).
    """
    if not (entry and stop and target and current and target != stop):
        return ""
    cur_pct = (current - entry) / entry * 100
    stop_pct = (stop - entry) / entry * 100
    tgt_pct = (target - entry) / entry * 100
    # Axis symetrique = max distance from entry. Floor 10% pour eviter
    # un axis micro si tout est tres pres d'entry.
    ax = max(abs(stop_pct), abs(tgt_pct), abs(cur_pct), 10.0)
    # Distance proportionnelle depuis le 0 central (50% visuel = entry).
    dot_v = max(0.0, min(100.0, 50.0 + (cur_pct / ax) * 50.0))
    stop_v = max(0.0, min(100.0, 50.0 + (stop_pct / ax) * 50.0))
    tgt_v = max(0.0, min(100.0, 50.0 + (tgt_pct / ax) * 50.0))
    # Repères : stop rouge gauche, entry gris centre, target vert droite.
    # Dot noir par defaut ; rouge si current < stop (limite cassee), vert si
    # current > target (signal complete). La couleur ne s'allume qu'aux
    # boundary crossings, sinon la position seule porte l'info.
    if current <= stop:
        dot_cls = "bear"
    elif current >= target:
        dot_cls = "acc"
    else:
        dot_cls = ""
    cls_full = ("sig-ent0 " + extra_class).strip()
    # Tooltip : pnl_position_pct (P&L EUR depuis avg_cost broker).
    # Post-fix L29 09/06 : quand le caller ancre la gauge sur avg_cost_eur en
    # passant aussi stop_eur/target_eur/current_eur (tout EUR depuis BookLine),
    # le dot calculé ci-dessus représente exactement pnl_position. Dot et
    # tooltip racontent alors LA MÊME chose (byte-identité de l'info).
    if pnl_position_pct is not None:
        title_str = f"P&L {pnl_position_pct:+.1f}%"
    else:
        title_str = "(P&L position non disponible)"
    return _tbar(
        dot_v,
        ticks=[
            (stop_v, "stop", "stop"),
            (50.0, "entry", "entry"),
            (tgt_v, "target", "target"),
        ],
        dot_color=dot_cls,
        title=title_str,
        extra_class=cls_full,
        data_attrs={"axmin": f"{-ax:.1f}", "axmax": f"{ax:.1f}"},
    )


def _position_axis_pct(
    stop_pct: float | None,
    target_pct: float | None,
    dot_pct: float | None,
    *,
    extra_class: str = "",
    pnl_position_pct: float | None = None,
) -> str:
    """Canonical position gauge — UN SEUL MÈTRE depuis le coût (% depuis 0=cost).

    Cf principe Olivier 09/06 23h+ : 0 = avg_cost (point de départ). stop/target
    posés à leurs % depuis cost (peuvent être négatifs). dot à la perf actuelle
    depuis cost (≡ P&L EUR si cost_native via fx_now).

    Tous les paramètres sont DÉJÀ des % (pas des prix) — pas de division par
    une entry, pas de mélange de mètres. Axe symétrique ax = max(|...|, 10),
    50% visuel = 0 (le coût). Returns "" si dot_pct None.
    """
    if dot_pct is None:
        return ""
    sp = stop_pct if stop_pct is not None else 0.0
    tp = target_pct if target_pct is not None else 0.0
    ax = max(abs(sp), abs(tp), abs(dot_pct), 10.0)
    dot_v = max(0.0, min(100.0, 50.0 + (dot_pct / ax) * 50.0))
    stop_v = max(0.0, min(100.0, 50.0 + (sp / ax) * 50.0)) if stop_pct is not None else None
    tgt_v = max(0.0, min(100.0, 50.0 + (tp / ax) * 50.0)) if target_pct is not None else None
    # Dot color : bear sous stop, acc au-dessus target, neutre entre
    dot_color = ""
    if stop_pct is not None and dot_pct <= stop_pct:
        dot_color = "bear"
    elif target_pct is not None and dot_pct >= target_pct:
        dot_color = "acc"
    # Tooltip simple : P&L EUR (dot_pct ≡ P&L EUR quand fx_now cohérent)
    if pnl_position_pct is not None:
        title_str = f"P&L {pnl_position_pct:+.1f}%"
    else:
        title_str = f"P&L {dot_pct:+.1f}%"
    ticks = []
    if stop_v is not None:
        ticks.append((stop_v, "stop", "stop"))
    ticks.append((50.0, "cost", "entry"))  # 0 central = cost (style "entry" gris)
    if tgt_v is not None:
        ticks.append((tgt_v, "target", "target"))
    cls_full = ("sig-pct " + extra_class).strip()
    return _tbar(
        dot_v,
        ticks=ticks,
        dot_color=dot_color,
        title=title_str,
        extra_class=cls_full,
        data_attrs={"axmin": f"{-ax:.1f}", "axmax": f"{ax:.1f}"},
    )


def _gauge_pcts_from_cost(bl: object | None) -> dict[str, float | None]:
    """Calcule les % de la gauge — principe Olivier 09/06 23h+ :

    - 0 (gris central) = ton coût actuel (cost_native)
    - dot_pct = perf actuelle DEPUIS COÛT (≡ P&L EUR via cost_native = avg_cost_eur / fx_now)
    - stop_pct, target_pct = % DÉCIDÉS EN AMONT (depuis entry de thèse, le point
      de décision original). Stables vs renforcements (le PMP qui bouge ne fait
      pas bouger les ticks décidés).

    Le mélange "dot depuis cost / ticks depuis entry" est ASSUMÉ et justifié :
    dot raconte "où tu en es maintenant", ticks racontent "où tu visais quand
    tu as posé la thèse". Deux questions, une seule gauge.

    Le split Closest/Beyond utilise cur_native >= target_native (FX-invariant)
    pour ranger les positions selon la VÉRITÉ du dépassement, pas l'apparence
    visuelle. SK Hynix : dot visuellement sous target tic (ticks depuis entry),
    mais cur_native > target_native → rangé en Beyond.

    Returns dict avec stop_pct, target_pct, target_partial_pct (depuis entry),
    dot_pct (depuis cost), + cur_native + target_native bruts.
    """
    if not bl:
        return {}
    avg_cost_eur = getattr(bl, "avg_cost_eur", None)
    fx = getattr(bl, "fx_rate_to_eur", None)
    cur_n = getattr(bl, "last_price_native", None)
    entry_n = getattr(bl, "entry_price", None)
    if not avg_cost_eur or not fx or not cur_n or fx <= 0 or avg_cost_eur <= 0:
        return {}
    cost_n = avg_cost_eur / fx  # cost_native via fx_now live
    if cost_n <= 0:
        return {}

    # dot_pct : perf depuis cost (≡ P&L EUR)
    dot_pct = (cur_n - cost_n) / cost_n * 100.0

    # ticks (stop/target) : % décidés depuis entry de thèse (le point posé en amont)
    def pct_from_entry(level: float | None) -> float | None:
        if level is None or level <= 0 or not entry_n or entry_n <= 0:
            return None
        return (level - entry_n) / entry_n * 100.0

    stop_n = getattr(bl, "stop_price", None)
    tgt_n = getattr(bl, "target_full", None)
    tpart_n = getattr(bl, "target_partial", None)
    return {
        "cost_native": cost_n,
        "cur_native": cur_n,
        "target_native": tgt_n,
        "entry_native": entry_n,
        "stop_pct": pct_from_entry(stop_n),
        "target_pct": pct_from_entry(tgt_n),
        "target_partial_pct": pct_from_entry(tpart_n),
        "dot_pct": dot_pct,
    }


def _position_axis_price(
    stop_eur: float | None,
    cost_eur: float | None,
    entry_eur: float | None,
    target_eur: float | None,
    cur_eur: float | None,
    *,
    extra_class: str = "",
    pnl_pct_cost: float | None = None,
    perf_pct_entry: float | None = None,
) -> str:
    """Canonical position gauge V2 (axe-PRIX EUR, cf SPEC_GAUGE_PRICE_AXIS #122).

    5 repères à leur vraie position de prix EUR sur un axe ouvert
    proportionnel. Pas d'anchor à choisir, pas de "0" centré -- les
    repères SONT les références, le dot raconte par sa position entre eux.

    Money-invariant L28 STRICT : tous params en EUR (jamais mix natif/EUR).
    cost_eur = PMP gelé (BookLine.avg_cost_eur, frozen-at-buy).
    stop/entry/target/cur_eur = niveaux × fx_now (live).
    Asymétrie nommée honnête : cost gelé, autres flottants.

    Tooltip enrichi 2 frames : "P&L X% depuis coût · Thèse Y% depuis entry
    · beyond Z%". Le dot ne raconte plus un %, juste sa position visuelle.

    Returns "" si < 2 repères présents + cur (insuffisant pour rendu utile).
    """
    if cur_eur is None or cur_eur <= 0:
        return ""
    # Refs disponibles (cur exclu, c'est le dot)
    refs_raw = [
        (stop_eur, "stop", "stop"),
        (cost_eur, "cost", "cost"),
        (entry_eur, "entry", "dash"),
        (target_eur, "target", "target"),
    ]
    refs = [(p, lbl, style) for p, lbl, style in refs_raw if p is not None and p > 0]
    if len(refs) < 2:
        return ""

    all_prices = [cur_eur] + [r[0] for r in refs]
    p_min, p_max = min(all_prices), max(all_prices)
    if p_max == p_min:
        return ""
    pad = (p_max - p_min) * 0.05
    p_min -= pad
    p_max += pad

    def to_v(p: float) -> float:
        return (p - p_min) / (p_max - p_min) * 100.0

    # Dot color : bear sous stop, acc au-dessus target, neutre entre
    dot_color = ""
    if stop_eur is not None and cur_eur <= stop_eur:
        dot_color = "bear"
    elif target_eur is not None and cur_eur >= target_eur:
        dot_color = "acc"

    # Tooltip : annotations 2 frames + beyond chip
    tip_parts: list[str] = []
    if pnl_pct_cost is not None:
        tip_parts.append(f"P&L {pnl_pct_cost:+.1f}% depuis coût")
    if perf_pct_entry is not None:
        tip_parts.append(f"thèse {perf_pct_entry:+.1f}% depuis entry")
    if target_eur is not None and cur_eur > target_eur > 0:
        beyond = (cur_eur / target_eur - 1) * 100.0
        tip_parts.append(f"beyond +{beyond:.1f}%")
    title_str = " · ".join(tip_parts)

    ticks = [(to_v(p), lbl, style) for p, lbl, style in refs]
    cls_full = ("sig-price " + extra_class).strip()
    # data-axis-mode="price" : enseigne au JS hover que axmin/axmax sont des
    # PRIX EUR (pas des % signed). Le JS formatte le hover en "€XXXX.XX" au
    # lieu de "+XXXX%" (bug 09/06 23h+ : axe-perf legacy assumait axmin/axmax=%
    # systématiquement → KLAC montrait +1821.1% au hover car axmax=1820 EUR
    # interprété comme %). Cure réelle : le JS distingue les 2 modes, chacun
    # honnête à son cadre. Tooltip riche `title` reste pour 2-frames info.
    return _tbar(
        to_v(cur_eur),
        ticks=ticks,
        dot_color=dot_color,
        title=title_str,
        extra_class=cls_full,
        data_attrs={
            "axmin": f"{p_min:.2f}",
            "axmax": f"{p_max:.2f}",
            "axis-mode": "price",
        },
    )


def _llm_status_badge() -> str:
    """Phase B (#93) : surface llm_status comme chip flottant bottom-right.

    Etats (couleur, label) :
    - healthy + model 'sonnet'/'opus' : --acc dot, "LLM sonnet"
    - healthy + model 'haiku' : --steel dot, "LLM haiku" (extract-tier normal)
    - degraded + reason 'cost_cap_soft' : --warn dot, "LLM haiku (cap 80%)"
    - degraded + reason 'cost_cap_hard' : --bear dot, "LLM stopped (cap 100%)"
    - degraded + reason 'credit_exhausted' : --bear dot, "LLM credit exhausted"
    - degraded + reason 'rate_limited' : --warn dot, "LLM rate limited"
    - down : --bear dot, "LLM down"
    - Defensive : si erreur lecture state, on rend rien (pas de marker faux).

    Position fixe bottom-right (z-index 50, hauteur alignee sur .cta-bar a 22px
    du bord). Style chip parchment/midnight aware via var(--panel) + var(--line2).
    """
    try:
        from shared import llm as _llm
        st = _llm.get_llm_status()
    except Exception:
        return ""
    status = st.get("status", "healthy")
    reason = st.get("reason")
    model = st.get("active_model")
    since = st.get("since") or ""

    if status == "healthy":
        dot = "--acc" if model in ("sonnet", "opus") else "--steel"
        label = f"LLM {model}" if model else "LLM"
    elif status == "degraded":
        if reason == "cost_cap_soft":
            dot, label = "--warn", "LLM haiku (cap 80%)"
        elif reason == "cost_cap_hard":
            dot, label = "--bear", "LLM stopped (cap 100%)"
        elif reason == "credit_exhausted":
            dot, label = "--bear", "LLM credit exhausted"
        elif reason == "rate_limited":
            dot, label = "--warn", "LLM rate limited"
        else:
            dot, label = "--warn", f"LLM degraded ({reason or '?'})"
    elif status == "down":
        dot, label = "--bear", "LLM down"
    else:
        return ""

    tip = f"{label} -- status={status} reason={reason or '-'} since={since[:16] if since else '-'}"
    # Fixed bottom-right : dot seul (user spec : no text). Label dans title
    # (tooltip hover) + aria-label (accessibilite). Discretion signal-subtil :
    # la presence indique "instrument", la couleur l'etat.
    # NB : box-sizing:border-box est global (* {...}), donc width/height includent
    # padding+border. Outer 22px sans padding + inner 10px centre via flex = ring
    # visible avec dot couleur a l'interieur.
    return (
        f'<div class="llm-badge" role="status" aria-label="LLM {label}" '
        f'title="{tip}" '
        f'style="position:fixed;bottom:22px;right:22px;z-index:50;'
        f'background:var(--panel);border:1px solid var(--line2);'
        f'border-radius:50%;width:22px;height:22px;'
        f'display:flex;align-items:center;justify-content:center;'
        f'box-shadow:0 14px 40px -12px rgba(0,0,0,.20),0 2px 6px -2px rgba(0,0,0,.08);'
        f'cursor:default;user-select:none">'
        f'<span class="llm-dot" aria-hidden="true" '
        f'style="display:block;width:10px;height:10px;border-radius:50%;'
        f'background:var({dot});flex-shrink:0"></span>'
        f'</div>'
    )


def _needle_color(frac: float, *, invert: bool = False) -> str:
    """Couleur continue du needle calee sur le gradient de l'axe.
    frac 0->100 = bear -> steel -> acc (defaut)
    invert=True (sizing): 0->100 = acc -> steel -> warn -> bear (la droite = danger)."""
    f = max(0.0, min(100.0, frac))
    if invert:
        if f <= 50:
            t = f / 50
            return f"color-mix(in srgb,var(--acc) {(1 - t) * 100:.0f}%,var(--steel) {t * 100:.0f}%)"
        if f <= 77:
            t = (f - 50) / 27
            return f"color-mix(in srgb,var(--steel) {(1 - t) * 100:.0f}%,var(--warn) {t * 100:.0f}%)"
        t = (f - 77) / 23
        return f"color-mix(in srgb,var(--warn) {(1 - t) * 100:.0f}%,var(--bear) {t * 100:.0f}%)"
    if f <= 50:
        t = f / 50
        return f"color-mix(in srgb,var(--bear) {(1 - t) * 100:.0f}%,var(--steel) {t * 100:.0f}%)"
    t = (f - 50) / 50
    return f"color-mix(in srgb,var(--steel) {(1 - t) * 100:.0f}%,var(--acc) {t * 100:.0f}%)"


SECTOR_COLORS = {
    "Foundry & logic": "#3056D3",
    "Semi equipment": "#10A37F",
    "Memory": "#E14B62",
    "Semi materials": "#FB923C",
    "EDA": "#7E47C9",
    "Connectivity & optics": "#D154AB",
    "Hyperscalers": "#0D9488",
    "Power & electrification": "#B45D31",
    "Defense": "#475569",
    "Energy & raw materials": "#CA8A04",
    "Auto / robotics": "#0EAFC4",
}
TICKER_SECTOR = {
    "AMZN": "MAG 7",
    "ENTG": "AI Compute",
    "MP": "Matériaux rares",
    "MU": "AI Compute",
    "6857.T": "AI Compute",
    "VRT": "Data Center",
    "CCJ": "Énergie",
    "LNG": "Énergie",
    "TSLA": "Robotique",
}
SECTOR_ALIAS = {"EU Defense": "Defense"}


# Glossaire canonique (FR). Mapping dim internal name -> (label affiche, sens target,
# bucket Construction/Fragilite). Construction = ce qui structure le book.
# Fragilite = ce qui peut le briser maintenant.
_DIM_LABELS = {
    "quality_T1_plus": ("High solidity", "min", "construction"),
    "T2_redondant": ("Overlaps", "max", "construction"),
    "decorrelation_star": ("Other bets", "min", "construction"),
    "sizing_conviction": ("Calibration", "min", "construction"),
    "cluster_cap": ("Bet principal", "max", "construction"),
    "thesis_health": ("Health", "min", "fragilite"),
    "cycle_valo_exposure": ("Cycle / valo", "max", "fragilite"),
}


def _v2_cohort_panel() -> str:
    """Cohorte V2 vs V1 -- visualise le pivot scoring 30/05.

    V2 = signal_scorer_v2 (base-rate-first, 3 etapes), source unique post-30/05.
    V1 = estimate_probability (formule cap [0.50, 0.72]), legacy mono-bucket.
    Tant que zero prediction V2 n'est en ledger -> affiche message d'attente.
    """
    try:
        from shared import storage as _stg

        with _stg.db() as cx:
            # V2 = predictions issues des sources SEC EDGAR (8-K + insider)
            v2_n = cx.execute(
                "SELECT COUNT(*) c FROM predictions p "
                "JOIN signals sig ON p.signal_id = sig.id "
                "JOIN sources src ON sig.source_id = src.id "
                "WHERE src.name IN ('SEC EDGAR 8-K', 'SEC EDGAR Insider Cluster')"
            ).fetchone()['c']
            # V1 = tout le reste (newsletters)
            v1_n = cx.execute(
                "SELECT COUNT(*) c FROM predictions p "
                "JOIN signals sig ON p.signal_id = sig.id "
                "JOIN sources src ON sig.source_id = src.id "
                "WHERE src.name NOT IN ('SEC EDGAR 8-K', 'SEC EDGAR Insider Cluster')"
            ).fetchone()['c']
            v1_range = cx.execute(
                "SELECT MIN(probability_at_creation) lo, MAX(probability_at_creation) hi, "
                "       COUNT(DISTINCT ROUND(probability_at_creation, 2)) buckets "
                "FROM predictions p JOIN signals sig ON p.signal_id = sig.id "
                "JOIN sources src ON sig.source_id = src.id "
                "WHERE src.name NOT IN ('SEC EDGAR 8-K', 'SEC EDGAR Insider Cluster')"
            ).fetchone()
            v2_range = cx.execute(
                "SELECT MIN(probability_at_creation) lo, MAX(probability_at_creation) hi, "
                "       COUNT(DISTINCT ROUND(probability_at_creation, 2)) buckets "
                "FROM predictions p JOIN signals sig ON p.signal_id = sig.id "
                "JOIN sources src ON sig.source_id = src.id "
                "WHERE src.name IN ('SEC EDGAR 8-K', 'SEC EDGAR Insider Cluster')"
            ).fetchone()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">cohorte V2 indispo: {type(e).__name__}</div></div>'

    v1_lo, v1_hi, v1_b = v1_range['lo'] or 0, v1_range['hi'] or 0, v1_range['buckets'] or 0
    v2_lo, v2_hi, v2_b = v2_range['lo'] or 0, v2_range['hi'] or 0, v2_range['buckets'] or 0

    v2_status = (
        '<div class="v2-status v2-empty">First V2 cohort expected '
        '31/05 6:30 (cron 8-K scan + 6:20 insider clusters)</div>'
        if v2_n == 0
        else f'<div class="v2-stat-row">'
             f'<span class="v2-stat-n mono">n={v2_n}</span>'
             f'<span class="v2-stat-rg mono">[{v2_lo:.3f} - {v2_hi:.3f}]</span>'
             f'<span class="v2-stat-bk mono">{v2_b} bucket(s)</span></div>'
    )

    v1_block = (
        f'<div class="v2-stat-row">'
        f'<span class="v2-stat-n mono">n={v1_n}</span>'
        f'<span class="v2-stat-rg mono">[{v1_lo:.3f} - {v1_hi:.3f}]</span>'
        f'<span class="v2-stat-bk mono">{v1_b} bucket(s)</span></div>'
        if v1_n > 0
        else '<div class="v2-status v2-empty">no V1 prediction</div>'
    )

    return (
        '<div class="colhead"><span class="t">Cohort V2 vs V1 (scorer pivot 30/05)</span>'
        '<span class="a">V2 = SEC EDGAR primary content &middot; V1 = newsletter sentiment (mono-bucket)</span></div>'
        '<div class="card pad v2cohortcard" style="margin-bottom:var(--s4)">'
        '<div class="v2-grid">'
        '<div class="v2-side v2-current"><div class="v2-label">V2 (canonique post-30/05)</div>'
        f'{v2_status}</div>'
        '<div class="v2-side v2-legacy"><div class="v2-label">V1 (legacy, baseline 10/06)</div>'
        f'{v1_block}</div></div></div>'
    )


def _calibration_progress_panel() -> str:
    """Calibration scorer V2 -- progress bar n/30 (INSUFFICIENT_DATA) ou verdict OK/WARN/ALERT.

    Surface l'attente data-driven en signal visible quotidien. Cohorte calibration
    s'active automatiquement quand n_total >= 30 predictions resolved non-neutral.

    Pattern aligne v2_vigilance / wire_activity (cron-friendly, silent-success).
    """
    try:
        import sqlite3

        from intelligence import calibration_audit as _calib
        from shared import storage as _stg

        cx = sqlite3.connect(_stg.DB_PATH)
        cx.row_factory = sqlite3.Row
        result = _calib.check_scorer_calibration(cx)
        cx.close()
    except Exception as e:
        return (
            '<div class="card pad calibcard" style="margin-bottom:var(--s4)">'
            f'<div class="empty">calibration indisponible : {type(e).__name__}</div></div>'
        )

    target = _calib.MIN_N_TOTAL  # 30
    n_total = result.get("n_total", 0)

    if result["status"] == "INSUFFICIENT_DATA":
        pct = min(n_total / target * 100, 100) if target else 0
        remaining = max(target - n_total, 0)
        return (
            '<div class="colhead"><span class="t">Calibration scorer V2</span>'
            f'<span class="a">cohort accumulation &mdash; verdict activates at n&ge;{target} non-neutral resolved predictions</span></div>'
            '<div class="card pad calibcard" style="margin-bottom:var(--s4)">'
            '<div class="calib-progress">'
            f'<div class="calib-bar"><div class="calib-fill" style="width:{pct:.1f}%"></div></div>'
            '<div class="calib-meta">'
            f'<span class="calib-n mono">{n_total}/{target}</span>'
            f'<span class="calib-rem">{remaining} to wait</span>'
            '</div></div></div>'
        )

    # status = OK / WARN / ALERT
    brier = result.get("avg_brier")
    max_gap = result.get("max_gap_pp", 0)
    status_cls = {"OK": "acc", "WARN": "warn", "ALERT": "neg"}.get(result["status"], "")
    brier_str = f"{brier:.4f}" if brier is not None else "&mdash;"
    return (
        '<div class="colhead"><span class="t">Calibration scorer V2</span>'
        f'<span class="a">verdict reliability + Brier moyen sur cohorte n={n_total}</span></div>'
        '<div class="card pad calibcard" style="margin-bottom:var(--s4)">'
        f'<div class="calib-verdict">'
        f'<span class="calib-status {status_cls}">{result["status"]}</span>'
        f'<span class="calib-brier">Brier <span class="mono">{brier_str}</span></span>'
        f'<span class="calib-gap">max gap <span class="mono">{max_gap:+.1f}pp</span></span>'
        f'</div>'
        f'<div class="calib-msg">{result.get("message", "")}</div>'
        '</div>'
    )


def _wire_activity_panel() -> str:
    """Wire EDGAR activity -- timeline 8-K + insider clusters arrives dans le pipeline."""
    try:
        from shared import storage as _stg

        with _stg.db() as cx:
            counts = {}
            for window, label in [(1, "24h"), (7, "7j"), (30, "30j")]:
                n8k = cx.execute(
                    f"SELECT COUNT(*) c FROM filings_8k_log WHERE filed_at >= date('now', '-{window} days')"
                ).fetchone()['c']
                ncluster = cx.execute(
                    f"SELECT COUNT(*) c FROM insider_buy_clusters_log "
                    f"WHERE detected_at >= datetime('now', '-{window} days')"
                ).fetchone()['c']
                counts[label] = (n8k, ncluster)
            recent_8k = cx.execute(
                "SELECT ticker, filed_at, severity, items_raw FROM filings_8k_log "
                "ORDER BY filed_at DESC LIMIT 5"
            ).fetchall()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">wire activity indispo: {type(e).__name__}</div></div>'

    cells = "".join(
        f'<div class="wact-cell">'
        f'<div class="wact-label">{lbl}</div>'
        f'<div class="wact-v"><span class="mono">{n8k}</span> 8-K &middot; '
        f'<span class="mono">{ncluster}</span> cluster</div></div>'
        for lbl, (n8k, ncluster) in counts.items()
    )

    last_rows = "".join(
        f'<div class="wact-recent"><span class="wact-tk">{r["ticker"]}</span>'
        f'<span class="wact-when mono">{r["filed_at"]}</span>'
        f'<span class="wact-sev wact-{r["severity"]}">{r["severity"]}</span>'
        f'<span class="wact-items mono">{r["items_raw"]}</span></div>'
        for r in recent_8k
    ) or '<div class="empty">no 8-K logged</div>'

    return (
        '<div class="colhead"><span class="t">Wire EDGAR activity</span>'
        '<span class="a">8-K + insider clusters arrived in the V2 scoring pipeline</span></div>'
        '<div class="card pad wactcard" style="margin-bottom:var(--s4)">'
        f'<div class="wact-grid">{cells}</div>'
        '<div class="wact-recent-head">Latest 5 8-K filings (toutes severities)</div>'
        f'<div class="wact-recent-list">{last_rows}</div></div>'
    )


def _vigilance_panel() -> str:
    """3 vigilances V2 -- watch_rate, directional_spread, insider_clusters_alive."""
    try:
        from intelligence import v2_vigilance

        results = v2_vigilance.run_all_vigilances()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">vigilances indispo: {type(e).__name__}</div></div>'

    status_cls = {
        "OK": "vg-ok",
        "INFO": "vg-info",
        "WARN": "vg-warn",
        "ALERT": "vg-alert",
        "INSUFFICIENT_DATA": "vg-wait",
    }
    # HTML entity codes : check, info-i (U+2139), spark, siren, hourglass
    status_emoji = {
        "OK": "&#9989;",
        "INFO": "&#8505;",
        "WARN": "&#9889;",
        "ALERT": "&#128680;",
        "INSUFFICIENT_DATA": "&#8987;",
    }

    rows = []
    for r in results:
        cls = status_cls.get(r["status"], "vg-info")
        emoji = status_emoji.get(r["status"], "?")
        msg = (r.get("message") or "")
        # Escape HTML
        msg = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        rows.append(
            f'<div class="vg-row {cls}">'
            f'<div class="vg-head"><span class="vg-emoji">{emoji}</span>'
            f'<span class="vg-name">{r["name"]}</span>'
            f'<span class="vg-status">{r["status"]}</span></div>'
            f'<div class="vg-msg">{msg}</div></div>'
        )

    return (
        '<div class="colhead"><span class="t">Vigilances V2</span>'
        '<span class="a">3 fitness functions auto &middot; cron weekly lundi 7h &middot; push Telegram UNIQUEMENT si ALERT/WARN</span></div>'
        '<div class="card pad vgcard" style="margin-bottom:var(--s4)">'
        + "".join(rows) +
        "</div>"
    )


def _render_ballast_cell(target: dict) -> str:
    """Axe 4 (b) M1 doctrine : ballast live derive, jamais YAML statique.

    Le YAML risk_watch declarait current_ballast_strict_pct=14% en mai (pollution
    M1, valeur figee). Source verite ici = compute_ballast_strict(positions actuelles).
    Si live diverge du YAML, surface les 2 avec live prominent.
    """
    try:
        from intelligence.ballast_compute import compute_ballast_strict
        positions = _positions()
        bs = compute_ballast_strict(positions)
    except Exception:
        bs = None

    if not bs:
        # Fallback : YAML statique, marque "live indispo" (M1 honnete)
        return (
            f'<div class="rw-cell"><div class="rw-h">Strict decorrelated ballast</div>'
            f'<div class="rw-v mono">{target.get("current_ballast_strict_pct", "?")}%</div>'
            f'<div class="rw-t">target: {target.get("target_ballast_strict_pct", "?")}% · live indispo</div></div>'
        )

    sev_cls = {"breach": "neg", "warn": "warn", "ok": ""}.get(bs["severity"], "")
    sub_parts = [f'target: {bs["target_pct"]}%', f'gap {bs["gap_pp"]:+.1f}pp']
    if bs["declared_pct"] is not None and abs(bs["declared_pct"] - bs["current_pct"]) > 1.0:
        sub_parts.append(f'decl(YAML): {bs["declared_pct"]}%')
    if bs["tickers_missing"]:
        sub_parts.append(f'missing: {",".join(bs["tickers_missing"])}')

    return (
        f'<div class="rw-cell"><div class="rw-h">Strict decorrelated ballast</div>'
        f'<div class="rw-v mono {sev_cls}">{bs["current_pct"]}%</div>'
        f'<div class="rw-t">{" · ".join(sub_parts)}</div></div>'
    )


def _risk_watch_panel() -> str:
    """Top Risks declares - first-class surveillance sur Vue d'ensemble.

    Lit scripts/risk_watch.json (declaration user) + status courant des
    mitigations + signals surveillance. Pas une opinion bot, juste tracking
    de ce que l'user a explicitement designe comme risque #1.
    """
    # Phase 1.5 stage 2 (L17 doctrine) : YAML declaratif + DB live state.
    # load_risk_watch_with_live_state hydrate chaque signal avec son current_status
    # depuis table risk_signal_evaluations -- format dict compat ancien JSON.
    try:
        from shared.risk_watch import load_risk_watch_with_live_state

        risks = load_risk_watch_with_live_state() or {}
        risks_list = risks.get("risks") or []
    except Exception:
        risks_list = []
    if not risks_list:
        return ""
    out = []
    for r in risks_list:
        sev_cls = {"critical": "danger", "high": "warn", "medium": "neu", "low": "calm"}.get(
            r.get("severity", "neu"), "neu"
        )
        exposure = r.get("exposure") or {}
        target = r.get("target") or {}
        signals = r.get("surveillance_signals") or []
        mitigations = r.get("mitigation_plan") or []

        # Mitigation progress aggregated
        avg_progress = (
            sum(m.get("progress_pct", 0) for m in mitigations) / len(mitigations)
            if mitigations else 0
        )

        # Sprint 20.b : show eval reason when at_risk/triggered
        sig_rows = []
        for s in signals[:6]:
            status = s.get("current_status", "?")
            scls = "triggered" if status == "triggered" else ("atrisk" if status == "at_risk" else "monitoring")
            reason = (s.get("last_eval_reason") or "").strip()
            conf = s.get("last_eval_confidence")
            evidence = s.get("last_eval_evidence_ids") or []
            extra_html = ""
            if status in ("at_risk", "triggered") and reason:
                reason_safe = reason.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                ev_str = (f" · evidence : signal_{', signal_'.join(str(i) for i in evidence[:3])}"
                          if evidence else "")
                extra_html = (
                    f'<div class="rw-sig-reason">{reason_safe[:200]} '
                    f'<span class="rw-sig-conf">(conf {conf}{ev_str})</span></div>'
                )
            sig_rows.append(
                f'<div class="rw-sig {scls}">'
                f'<div class="rw-sig-head"><span class="rw-sig-l">{s.get("label", "?")}</span>'
                f'<span class="rw-sig-w">{s.get("weight", "")}</span>'
                f'<span class="rw-sig-s {scls}">{status}</span></div>'
                f'{extra_html}'
                f'</div>'
            )
        signals_html = "".join(sig_rows)

        mit_html = "".join(
            f'<div class="rw-mit"><div class="rw-mit-h">'
            f'<span class="rw-mit-l">{m.get("label", "?")}</span>'
            f'<span class="rw-mit-st {m.get("status", "?")}">'
            f'{m.get("progress_pct", 0)}%</span></div>'
            f'<div class="rw-mit-a">{m.get("action", "")[:200]}</div>'
            + (f'<div class="rw-mit-n">{m.get("notes", "")[:160]}</div>' if m.get("notes") else "")
            + '</div>'
            for m in mitigations
        )

        ballast_cell_html = _render_ballast_cell(target)
        out.append(
            '<div class="rw-card">'
            f'<div class="rw-head"><span class="rw-rank">#{r.get("rank", "?")}</span>'
            f'<span class="rw-name">{r.get("name", "?")}</span>'
            f'<span class="rw-sev {sev_cls}">{r.get("severity", "?")}</span></div>'
            f'<div class="rw-expo">Exposure: {exposure.get("pct_book", "?")}% of book '
            f'(cluster {exposure.get("cluster", "?")} &middot; factor {exposure.get("factor", "?")})</div>'
            '<div class="rw-grid">'
            f'<div class="rw-cell"><div class="rw-h">Estimated drawdown stress</div>'
            f'<div class="rw-v mono neg">{target.get("current_estimated_drawdown_stress", "?")}%</div>'
            f'<div class="rw-t">target: {target.get("target_estimated_drawdown_stress", "?")}%</div></div>'
            + ballast_cell_html +
            f'<div class="rw-cell"><div class="rw-h">Mitigation plan</div>'
            f'<div class="rw-v mono">{avg_progress:.0f}%</div>'
            f'<div class="rw-t">A/B/C levers in progress</div></div>'
            '</div>'
            '<div class="rw-section">'
            '<div class="rw-sh">Signal watch</div>'
            f'<div class="rw-sigs">{signals_html}</div>'
            '</div>'
            '<div class="rw-section">'
            '<div class="rw-sh">Mitigation plan</div>'
            f'<div class="rw-mits">{mit_html}</div>'
            '</div>'
            '</div>'
        )
    # Phase construction : cadre la lecture du risk_watch. La severity reste
    # "critical" (la menace marche est reelle), mais l'exposure 78% va se
    # diluer mecaniquement quand les decorrelants arrivent. Lecture : watch,
    # pas act-now sur le ratio.
    construction_lens = ""
    try:
        from pathlib import Path as _Path

        import yaml as _yaml

        _cfg = _yaml.safe_load(_Path("config.yaml").read_text())
        if (_cfg.get("user_strategy") or {}).get("construction_phase"):
            construction_lens = (
                '<div class="rw-lens">'
                'Active construction phase &middot; '
                "current exposure will mechanically dilute toward target "
                "as decorrelators (Energy-for-AI, Defense, Robotics) come in. "
                '<b>Reading: watch, do not correct.</b>'
                '</div>'
            )
    except Exception:
        pass
    return (
        '<div class="colhead"><span class="t">Top Risks watch</span>'
        f'<span class="a">{len(risks_list)} declared risk(s) &middot; thesis-level reflection</span></div>'
        '<div class="card pad riskwatchcard" style="margin-bottom:var(--s4)">'
        f'{construction_lens}'
        + "".join(out)
        + "</div>"
    )


def _fetch_portfolio_equity_curve():
    """Build equity curve depuis price_history (Axe 5 closing, M1 source unique).

    Avant : yfinance batch live a chaque regen 60s (lent + ban risk).
    Apres : SELECT depuis price_history persisted (instantane, single gateway).
    Si gap dans price_history -> ensure_price_history backfill automatique.

    Cache 1h pour eviter compute repete (concat 26 series).
    """
    import time as _t

    global _PORTFOLIO_HISTORY_CACHE
    now = _t.monotonic()
    if _PORTFOLIO_HISTORY_CACHE is not None:
        curve, ts = _PORTFOLIO_HISTORY_CACHE
        if now - ts < _PORTFOLIO_HISTORY_TTL:
            return curve

    try:
        import pandas as pd

        from shared import storage
        from shared.prices import ensure_price_history
    except Exception:
        return None

    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT ticker, qty FROM positions "
                "WHERE status='open' AND qty > 0"
            ).fetchall()
    except Exception:
        return None

    if not rows:
        return None

    qtys = {r[0]: float(r[1]) for r in rows}

    # Fenetre = 1y. ensure_price_history backfill on-demand si gap.
    from datetime import UTC as _UTC, datetime as _dt, timedelta as _td
    end_dt = _dt.now(_UTC)
    start_dt = end_dt - _td(days=365)

    # Build close DataFrame multi-ticker depuis price_history
    series_per_ticker = {}
    for ticker in qtys:
        try:
            df = ensure_price_history(ticker, start_dt, end_dt)
            if df is not None and not df.empty:
                s = df["price_native"]
                s.index = s.index.normalize()
                s = s.groupby(s.index).last()
                series_per_ticker[ticker] = s
        except Exception:
            continue

    if not series_per_ticker:
        return None

    close = pd.DataFrame(series_per_ticker)
    if close.empty:
        return None

    # Equity curve = sum(qty * prix native). KNOWN-GAP : mix devises
    # native (cf docstring _performance_panel). Ratios CAGR/Sharpe/DD valides relatifs.
    try:
        portfolio_values = pd.Series(0.0, index=close.index)
        for ticker in close.columns:
            if ticker in qtys:
                prices = close[ticker].ffill()
                portfolio_values = portfolio_values + (prices * qtys[ticker])
        portfolio_values = portfolio_values.dropna()
    except Exception:
        return None

    if len(portfolio_values) < 30:
        return None

    _PORTFOLIO_HISTORY_CACHE = (portfolio_values, now)
    return portfolio_values


def _fetch_benchmark_equity_curve():
    """Cache 1h SPY 1y daily. Pour comparaison Heimdall Performance panel V3."""
    import time as _t

    global _BENCHMARK_HISTORY_CACHE
    now = _t.monotonic()
    if _BENCHMARK_HISTORY_CACHE is not None:
        curve, ts = _BENCHMARK_HISTORY_CACHE
        if now - ts < _PORTFOLIO_HISTORY_TTL:
            return curve

    try:
        # Phase 4 #6 (dernier bypass yfinance render.py) : gateway canonique.
        # period="1y" yfinance = ~365j calendaires via relativedelta(years=1).
        # end=today+1 cf finding #3 end-exclusive.
        from datetime import UTC, datetime, timedelta

        import pandas as pd
        from dateutil.relativedelta import relativedelta

        from shared.prices import get_price_window

        today = datetime.now(UTC).date()
        end = today + timedelta(days=1)
        start = today - relativedelta(years=1)
        window = get_price_window(_BENCHMARK_TICKER, start, end)
        if len(window) < 30:
            return None
        # Reconstitue Series pandas indexée par Timestamp (contrat consumers
        # Heimdall Performance panel inchangé).
        close = pd.Series(
            [c for _, c in window],
            index=pd.DatetimeIndex([d for d, _ in window]),
        )
        _BENCHMARK_HISTORY_CACHE = (close, now)
        return close
    except Exception:
        return None


def _data_health_panel() -> str:
    """Axe 5 QUALITY_BAR : data health = as-of le plus vieux + source + # stale.

    Surface M1 triple (valeur, asof, source) visible. Doctrine : aucun nombre
    rendu sans son as-of. Stale -> flag. SLA : config/freshness.yaml.
    """
    try:
        from shared import storage
        from shared.freshness import classify_asof
    except Exception as e:
        return (
            '<div class="card data-health-card">'
            '<div class="card-h">Data health</div>'
            f'<div class="card-b">Indisponible : {type(e).__name__}</div>'
            '</div>'
        )

    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT ticker, price_asof, price_source, fx_asof, fx_source, "
                "       last_price_currency "
                "FROM positions WHERE status='open' AND qty > 0"
            ).fetchall()
    except Exception as e:
        return (
            '<div class="card data-health-card">'
            '<div class="card-h">Data health</div>'
            f'<div class="card-b">DB erreur : {e}</div>'
            '</div>'
        )

    if not rows:
        return (
            '<div class="card data-health-card">'
            '<div class="card-h">Data health</div>'
            '<div class="card-b">Aucune position ouverte.</div>'
            '</div>'
        )

    price_severities = {"green": 0, "amber": 0, "rouge": 0, "unknown": 0}
    fx_severities = {"green": 0, "amber": 0, "rouge": 0, "unknown": 0}
    oldest_price_age = -1.0
    oldest_price_ticker = None
    oldest_fx_age = -1.0
    oldest_fx_pair = None
    sources = {}

    for r in rows:
        ticker, price_asof, price_source, fx_asof, _fx_source, currency = r
        if price_asof:
            sev, age = classify_asof("price", price_asof)
            price_severities[sev] = price_severities.get(sev, 0) + 1
            if age > oldest_price_age:
                oldest_price_age = age
                oldest_price_ticker = ticker
            if price_source:
                sources[price_source] = sources.get(price_source, 0) + 1
        else:
            price_severities["unknown"] += 1
        if fx_asof and currency and currency != "EUR":
            sev_fx, age_fx = classify_asof("fx", fx_asof)
            fx_severities[sev_fx] = fx_severities.get(sev_fx, 0) + 1
            if age_fx > oldest_fx_age:
                oldest_fx_age = age_fx
                oldest_fx_pair = f"{currency}->EUR"

    n_total = len(rows)
    n_stale_price = price_severities["amber"] + price_severities["rouge"]
    n_unknown = price_severities["unknown"]

    def _fmt_age(sec):
        if sec < 0:
            return "—"
        if sec < 60:
            return f"{int(sec)}s"
        if sec < 3600:
            return f"{int(sec/60)}min"
        if sec < 86400:
            return f"{int(sec/3600)}h"
        return f"{int(sec/86400)}j"

    def _sev_class(sev):
        return {"green": "ok", "amber": "warn", "rouge": "neg", "unknown": "neu"}.get(sev, "neu")

    overall_sev = "green"
    for sev in ("rouge", "amber", "unknown"):
        if price_severities.get(sev, 0) > 0 or fx_severities.get(sev, 0) > 0:
            overall_sev = sev
            break

    sources_str = ", ".join(f"{s}x{n}" for s, n in sources.items()) if sources else "—"

    # Axe 2 QUALITY_BAR : composition orthogonal/narrative des sources (chip honnete).
    # Si 97% narrative_newsletter et 3% orthogonal -> on l'affiche, on ne masque pas.
    try:
        from intelligence.source_diversity import book_source_composition
        comp = book_source_composition()
        n_total_src = comp["total"]
        ortho_pct = comp["orthogonal_pct"]
        narr_pct = comp["narrative_pct"]
        # Severite : narrative > 80% = mono-culture confirmee (warn)
        narr_sev = "neg" if narr_pct >= 90 else ("warn" if narr_pct >= 70 else "ok")
        diversity_html = (
            '<div class="dh-distrib" style="margin-top:6px">'
            f'<span class="dh-chip {narr_sev}">'
            f'sources : {narr_pct:.0f}% narrative / {ortho_pct:.0f}% orthogonal · '
            f'n={n_total_src}</span>'
            '<span class="dh-chip neu" style="font-size:10px;opacity:0.7">'
            'Axe 2 garde-fou : 2 narratifs corrélés ≠ 2 lectures du marché'
            '</span>'
            '</div>'
        )
    except Exception:
        diversity_html = ""

    return (
        '<div class="card data-health-card">'
        f'<div class="card-h">Data health · M1 freshness ({_sev_class(overall_sev)})</div>'
        '<div class="card-meta">cf config/freshness.yaml SLA · L21 doctrine M1 triple</div>'
        '<div class="dh-grid">'
        f'<div class="dh-kpi"><div class="k">Book</div><div class="v mono">{n_total} pos</div></div>'
        f'<div class="dh-kpi"><div class="k">Stale prix</div><div class="v mono {_sev_class("amber" if n_stale_price else "green")}">{n_stale_price}/{n_total}</div></div>'
        f'<div class="dh-kpi"><div class="k">Inconnu</div><div class="v mono {_sev_class("unknown" if n_unknown else "green")}">{n_unknown}</div></div>'
        f'<div class="dh-kpi"><div class="k">Prix le + vieux</div><div class="v mono">{_fmt_age(oldest_price_age)}</div><div class="dh-tip">{oldest_price_ticker or "—"}</div></div>'
        f'<div class="dh-kpi"><div class="k">FX le + vieux</div><div class="v mono">{_fmt_age(oldest_fx_age)}</div><div class="dh-tip">{oldest_fx_pair or "—"}</div></div>'
        f'<div class="dh-kpi"><div class="k">Sources</div><div class="v mono" style="font-size:13px">{sources_str}</div></div>'
        '</div>'
        '<div class="dh-distrib">'
        f'<span class="dh-chip ok">green {price_severities["green"]}</span>'
        f'<span class="dh-chip warn">amber {price_severities["amber"]}</span>'
        f'<span class="dh-chip neg">rouge {price_severities["rouge"]}</span>'
        f'<span class="dh-chip neu">inconnu {price_severities["unknown"]}</span>'
        '</div>'
        + diversity_html +
        '</div>'
    )


def _performance_panel() -> str:
    """Performance panel Heimdall (post-audit 07/06, ffn integration).

    KPI cards : CAGR / Sharpe / Sortino / Calmar / Max DD / Volatility annuelle.
    Source : shared.portfolio_analytics wrappant ffn 1.1.5.

    Affiche "Pas encore assez d'historique" si <30j de positions ouvertes.
    KNOWN-GAP : pas de conversion FX exacte (cf docstring _fetch_portfolio_equity_curve).
    """
    try:
        prices = _fetch_portfolio_equity_curve()
    except Exception as e:
        return (
            '<div class="card performance-card">'
            '<div class="card-h">Performance</div>'
            f'<div class="card-b">Indisponible : {type(e).__name__}</div>'
            '</div>'
        )

    if prices is None:
        return (
            '<div class="card performance-card">'
            '<div class="card-h">Performance</div>'
            '<div class="card-b">Historique insuffisant (>30j requis) ou yfinance indisponible.</div>'
            '</div>'
        )

    try:
        from shared.portfolio_analytics import (
            compute_drawdown_series,
            compute_information_ratio,
            compute_perf_metrics,
        )
        metrics = compute_perf_metrics(prices, rf_annual=0.025)
        dd_series = compute_drawdown_series(prices)
    except Exception as e:
        return (
            '<div class="card performance-card">'
            '<div class="card-h">Performance</div>'
            f'<div class="card-b">Compute echec : {type(e).__name__}</div>'
            '</div>'
        )

    # V3 : SPY benchmark + IR
    bench_prices = _fetch_benchmark_equity_curve()
    bench_metrics: dict[str, float | None] = {}
    ir_value = None
    if bench_prices is not None:
        try:
            bench_metrics = compute_perf_metrics(bench_prices, rf_annual=0.025)
            # Align dates inner-join puis compute returns
            aligned_p, aligned_b = prices.align(bench_prices, join="inner")
            if len(aligned_p) >= 30:
                p_rets = aligned_p.pct_change().dropna()
                b_rets = aligned_b.pct_change().dropna()
                ir_value = compute_information_ratio(p_rets, b_rets)
        except Exception:
            pass

    def _fmt_pct(v):
        return f"{v*100:.1f}%" if v is not None else "—"

    def _fmt_num(v):
        return f"{v:.2f}" if v is not None else "—"

    def _fmt_sign(v):
        if v is None:
            return "—"
        sign = "+" if v >= 0 else ""
        return f"{sign}{v*100:.1f}%"

    cagr = _fmt_sign(metrics.get("cagr"))
    tot_ret = _fmt_sign(metrics.get("total_return"))
    max_dd = _fmt_pct(metrics.get("max_drawdown"))
    vol = _fmt_pct(metrics.get("volatility_annual"))
    sharpe = _fmt_num(metrics.get("sharpe"))
    sortino = _fmt_num(metrics.get("sortino"))
    calmar = _fmt_num(metrics.get("calmar"))

    dd_now = float(dd_series.iloc[-1]) if len(dd_series) else 0.0
    n_days = len(prices)

    # === Charts SVG inline : equity curve + drawdown area ===
    # Pattern coherent avec _macro_sparkline et autres SVG inline. Pas de
    # dep externe. Adaptatif au theme via var(--ink) / var(--bear) / etc.

    def _normalize_to_first(series, lo, hi):
        """Rebase une serie pour qu'elle partage le meme range lo/hi (overlay)."""
        s_lo, s_hi = min(series), max(series)
        s_rng = (s_hi - s_lo) or 1.0
        rng = (hi - lo) or 1.0
        # Map series[t] from [s_lo, s_hi] to [lo, hi]
        return [(v - s_lo) / s_rng * rng + lo for v in series]

    def _build_equity_sparkline(
        price_series, bench_series=None, width=720, height=60, pad=4
    ) -> str:
        """Polyline equity curve + optionnel bench SPY line gris.

        Overlay : SPY est NORMALISE sur le range de prices pour overlay visuel
        (les 2 series partent visuellement du meme niveau, on compare la pente).
        """
        vals = list(price_series.values)
        n = len(vals)
        if n < 2:
            return ""
        lo, hi = min(vals), max(vals)
        rng = (hi - lo) or 1.0
        pts = []
        for i, v in enumerate(vals):
            x = pad + (i / max(1, n - 1)) * (width - 2 * pad)
            y = pad + (height - 2 * pad) - ((v - lo) / rng) * (height - 2 * pad)
            pts.append(f"{x:.1f},{y:.1f}")
        last_x, last_y = pts[-1].split(",")
        color = "var(--acc)" if vals[-1] >= vals[0] else "var(--bear)"
        area_pts = " ".join(pts) + f" {width-pad:.1f},{height-pad:.1f} {pad:.1f},{height-pad:.1f}"

        # Optionnel : bench line
        bench_svg = ""
        if bench_series is not None and len(bench_series) >= 2:
            b_vals = list(bench_series.values)
            b_norm = _normalize_to_first(b_vals, lo, hi)
            b_n = len(b_norm)
            b_pts = []
            for i, v in enumerate(b_norm):
                x = pad + (i / max(1, b_n - 1)) * (width - 2 * pad)
                y = pad + (height - 2 * pad) - ((v - lo) / rng) * (height - 2 * pad)
                b_pts.append(f"{x:.1f},{y:.1f}")
            bench_svg = (
                f'<polyline points="{" ".join(b_pts)}" fill="none" '
                f'stroke="var(--steel)" stroke-width="1.2" stroke-dasharray="3,3" '
                f'opacity="0.7"/>'
            )

        return (
            f'<svg class="perf-equity-svg" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="none" width="100%" height="{height}">'
            f'<polygon points="{area_pts}" fill="{color}" opacity="0.08"/>'
            f'{bench_svg}'
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
            f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{last_x}" cy="{last_y}" r="2.5" fill="{color}"/>'
            f'</svg>'
        )

    def _build_drawdown_chart(dd_series, days=30, width=720, height=50, pad=4) -> str:
        """Drawdown area chart sur les `days` derniers points. Toujours rouge
        car DD est negatif. Area fill = severite visible."""
        vals = list(dd_series.tail(days).values)
        n = len(vals)
        if n < 2:
            return ""
        # DD est en [-1, 0] approximativement, on cale sur le min observe
        lo = min(min(vals), -0.01)  # min 1% pour graph
        hi = 0.0
        rng = (hi - lo) or 1.0
        pts = []
        for i, v in enumerate(vals):
            x = pad + (i / max(1, n - 1)) * (width - 2 * pad)
            # DD 0 en haut, DD -X en bas
            y = pad + ((hi - v) / rng) * (height - 2 * pad)
            pts.append(f"{x:.1f},{y:.1f}")
        # Area : ligne + ferme par les coins bas droite/gauche
        area_pts = " ".join(pts) + f" {width-pad:.1f},{height-pad:.1f} {pad:.1f},{height-pad:.1f}"
        return (
            f'<svg class="perf-dd-svg" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="none" width="100%" height="{height}">'
            f'<polygon points="{area_pts}" fill="var(--bear)" opacity="0.18"/>'
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="var(--bear)" '
            f'stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>'
            f'</svg>'
        )

    try:
        equity_chart = _build_equity_sparkline(prices, bench_series=bench_prices)
        dd_chart = _build_drawdown_chart(dd_series, days=30)
    except Exception:
        equity_chart = ""
        dd_chart = ""

    ir_fmt = _fmt_num(ir_value)
    bench_sharpe = _fmt_num(bench_metrics.get("sharpe"))
    bench_total = _fmt_sign(bench_metrics.get("total_return"))
    equity_label = "Equity curve (1y) vs SPY" if bench_prices is not None else "Equity curve (1y)"
    bench_meta = ""
    if bench_prices is not None:
        bench_meta = (
            f' · SPY Sharpe {bench_sharpe} · SPY total {bench_total}'
        )

    return (
        '<div class="card performance-card">'
        '<div class="card-h">'
        'Performance · ffn analytics (1y rolling) '
        '<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
        'font-size:10px;font-weight:600;background:#7a1f1f;color:#fff;'
        'margin-left:8px;letter-spacing:0.5px;">PRO-FORMA · PAS TRACK RECORD</span>'
        '</div>'
        '<div class="card-meta" style="margin-bottom:4px;color:#a06;font-weight:500;">'
        'Calcul = sum(qty_actuelle x prix_historique) sur 1y. Allocation d\'aujourd\'hui '
        'projetee retroactivement. Survivorship + construction-phase ignorees. '
        'Pas une mesure publishable de performance reelle.'
        '</div>'
        f'<div class="card-meta">N={n_days}j · rf=2.5%{bench_meta} · KNOWN-GAP: FX exact non applique</div>'
        '<div class="perf-grid">'
        f'<div class="perf-kpi"><div class="k">CAGR</div><div class="v mono">{cagr}</div></div>'
        f'<div class="perf-kpi"><div class="k">Total return</div><div class="v mono">{tot_ret}</div></div>'
        f'<div class="perf-kpi"><div class="k">Max DD</div><div class="v mono neg">{max_dd}</div></div>'
        f'<div class="perf-kpi"><div class="k">DD courant</div><div class="v mono">{dd_now*100:.1f}%</div></div>'
        f'<div class="perf-kpi"><div class="k">Vol ann.</div><div class="v mono">{vol}</div></div>'
        f'<div class="perf-kpi"><div class="k">Sharpe</div><div class="v mono">{sharpe}</div></div>'
        f'<div class="perf-kpi"><div class="k">Sortino</div><div class="v mono">{sortino}</div></div>'
        f'<div class="perf-kpi"><div class="k">Calmar</div><div class="v mono">{calmar}</div></div>'
        f'<div class="perf-kpi"><div class="k">IR vs SPY</div><div class="v mono">{ir_fmt}</div></div>'
        '</div>'
        + (
            '<div class="perf-chart-block">'
            f'<div class="perf-chart-h">{equity_label}</div>'
            f'{equity_chart}'
            '</div>' if equity_chart else ""
        )
        + (
            '<div class="perf-chart-block">'
            '<div class="perf-chart-h">Drawdown 30j</div>'
            f'{dd_chart}'
            '</div>' if dd_chart else ""
        )
        + '</div>'
    )


def _grade_panel() -> str:
    """Glossaire canonique : DEUX notes (Construction + Fragilite), chacune
    decomposee par axe. Vocabulaire FR clair, plus de jargon T1/T1★/cluster.

    - Construction = Solidite + Bet + Doublons + Calibrage (ce qui structure)
    - Fragilite = Sante + cycle/valo (ce qui peut briser maintenant)
    """
    try:
        from intelligence import portfolio_grade as _grade
        from shared import storage as _stg

        latest = _stg.get_latest_portfolio_grade()
        if latest:
            grade_letter = latest["overall_grade"]
            score = latest["overall_score"]
            dims = json.loads(latest["dimensions_json"]) if latest.get("dimensions_json") else {}
            snapshot_date = latest.get("snapshot_date", "")
            gates: list[str] = []  # not persisted in snapshot, can compute fresh if needed
        else:
            g = _grade.compute_grade()
            grade_letter = g["overall_grade"]
            score = g["overall_score"]
            dims = g["dimensions"]
            snapshot_date = g["snapshot_date"]
            gates = g.get("gates_applied") or []
        trend = _grade.compute_trend_7d()
        trend_str = {
            "improving": "&uarr; 7j",
            "stable": "&middot; stable 7j",
            "deteriorating": "&darr; 7j",
            "no_history": "snapshot J0",
        }.get(trend, "")
    except Exception as e:
        return f'<div class="card pad"><div class="empty">note PF indisponible: {type(e).__name__}</div></div>'

    # Decompose Construction vs Fragilite : sub-score = weighted dims dans le bucket
    construction_dims, fragilite_dims = [], []
    cw_total = fw_total = 0
    c_score_sum = f_score_sum = 0
    for dk, (_label, _kind, bucket) in _DIM_LABELS.items():
        d = dims.get(dk) or {}
        if d.get("status") == "data_insufficient":
            continue
        wt = d.get("weight", 0)
        sc = d.get("score", 0)
        if bucket == "construction":
            construction_dims.append(dk)
            cw_total += wt
            c_score_sum += sc * wt / 100
        else:
            fragilite_dims.append(dk)
            fw_total += wt
            f_score_sum += sc * wt / 100
    construction_score = round(c_score_sum * 100 / cw_total) if cw_total else 0
    fragilite_score = round(f_score_sum * 100 / fw_total) if fw_total else 0

    def _extract_tickers(evidence: str) -> list[str]:
        """Pull tickers from evidence text (uppercase symbols with optional .EX suffix)."""
        if not evidence:
            return []
        ticks = re.findall(r"\b([0-9]{4,6}\.[A-Z]{2}|[A-Z]{1,5}\.[A-Z]{2}|[A-Z]{1,6})\b", evidence)
        # Filter out common false positives
        skip = {"DB", "DR", "OR", "HBM", "DRAM", "EUV", "OK", "M", "EU", "AI", "PF", "ATE", "IDM", "GICS"}
        seen = []
        for t in ticks:
            if t in skip or len(t) < 2:
                continue
            if t not in seen:
                seen.append(t)
        return seen[:10]

    def _build_rows(keys: list[str]) -> str:
        rows = []
        for dk in keys:
            label, kind, _ = _DIM_LABELS[dk]
            d = dims.get(dk) or {}
            cur = d.get("current_pct", 0) or 0
            tgt = d.get("target_pct", 0) or 0
            evidence = d.get("evidence", "")
            tickers = _extract_tickers(evidence)
            bar_pct = max(0.0, min(100.0, cur))
            good = (cur >= tgt) if kind == "min" else (cur <= tgt)
            tcls = "good" if good else "bad"
            prefix = "&ge;" if kind == "min" else "&le;"
            chips_html = (
                "".join(
                    f'<span class="gsub-tk" onclick="event.stopPropagation();openLoupe(\'{t}\')">{t}</span>'
                    for t in tickers
                )
                if tickers else
                '<span class="gsub-empty">none ticker specifique cite dans l\'evidence</span>'
            )
            ev_safe = evidence.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:280]
            rows.append(
                f'<div class="grow-wrap">'
                f'<div class="grow has-acc">'
                f'<div class="glab">{label}</div>'
                f'<div class="gaxis"><div class="gfill {tcls}" style="width:{bar_pct:.1f}%"></div>'
                f'<div class="gtgt" style="left:{tgt:.1f}%"></div></div>'
                f'<div class="gnum"><span class="mono">{cur:.1f}%</span>'
                f'<span class="gt">target {prefix} {tgt:.0f}%</span></div>'
                f'</div>'
                f'<div class="gsub">'
                f'<div class="gsub-chips">{chips_html}</div>'
                f'<div class="gsub-ev">{ev_safe}</div>'
                f'</div>'
                f'</div>'
            )
        return "".join(rows) or '<div class="empty" style="padding:var(--s25) 0">&mdash;</div>'

    def _cls(s: int) -> str:
        return "good" if s >= 70 else ("warn" if s >= 50 else "bad")

    grade_cls = _cls(score)
    c_cls = _cls(construction_score)
    f_cls = _cls(fragilite_score)
    gates_html = ""
    if gates:
        gates_html = (
            '<div class="ggate">⚠ ' + " · ".join(g for g in gates) + '</div>'
        )
    return (
        '<div class="colhead"><span class="t">Portfolio grade</span>'
        f'<span class="a">{snapshot_date} &middot; {trend_str}</span></div>'
        '<div class="card pad gradecard" style="margin-bottom:var(--s4)">'
        f'{gates_html}'
        '<div class="ghead">'
        f'<div class="gletter {grade_cls}">{grade_letter}</div>'
        f'<div class="gscore"><div class="gscoreval mono">{score}<span class="gscoremax">/100</span></div>'
        f'<div class="gscorebar"><div class="gscorefill {grade_cls}" style="width:{score:.0f}%"></div></div></div>'
        "</div>"
        # Sub-notes split
        '<div class="gsplit">'
        '<div class="gsub">'
        f'<div class="gsubh">Construction</div>'
        f'<div class="gsubscore mono {c_cls}">{construction_score}<span class="gsubmax">/100</span></div>'
        f'<div class="gbody">{_build_rows(construction_dims)}</div>'
        '</div>'
        '<div class="gsub">'
        f'<div class="gsubh">Fragility</div>'
        f'<div class="gsubscore mono {f_cls}">{fragilite_score}<span class="gsubmax">/100</span></div>'
        f'<div class="gbody">{_build_rows(fragilite_dims)}</div>'
        '</div>'
        '</div>'
        "</div>"
    )


_VERDICT_LABEL = {
    "PROCEED": ("ok", "PROCEED"),
    "PRESSURE": ("warn", "PRESSURE"),
    "STRONG_OPPOSE": ("bad", "STRONG OPPOSE"),
}


def _blind_positions_panel() -> str:
    """F7 add 29/05 — surface positions en VOL AVEUGLE : these active sur
    position ouverte, mais au moins UN input critique manquant (entry,
    target_full, stop_price, invalidation_triggers). Self-disable si zero.

    Anti-pattern combattu : SNOW vivait en vol disclosuregle integral (tout NULL)
    et affichait '*' sain dans les panels existants. Le bot accepte que ses
    propres inputs soient creux.
    """
    try:
        from shared import storage as _stg

        with _stg.db() as cx:
            rows = cx.execute(
                "SELECT t.id, t.ticker, t.conviction, t.entry_price, "
                "t.target_full, t.stop_price, t.invalidation_triggers, t.opened_at "
                "FROM theses t INNER JOIN positions p ON p.ticker = t.ticker "
                "WHERE t.status='active' AND p.qty > 0 AND p.status='open' "
                "ORDER BY t.ticker"
            ).fetchall()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">vol disclosuregle indispo: {type(e).__name__}</div></div>'

    blind: list = []
    for r in rows:
        missing = []
        if r[3] is None:
            missing.append("entry")
        if r[4] is None:
            missing.append("target")
        if r[5] is None:
            missing.append("stop")
        if not r[6] or r[6] == "[]":
            missing.append("triggers")
        if missing:
            blind.append({
                "id": r[0],
                "ticker": r[1],
                "conviction": r[2],
                "missing": missing,
                "opened_at": (r[7] or "")[:10],
            })
    if not blind:
        return ""  # self-disable
    items = "".join(
        f'<div class="ba-row">'
        f'<div class="ba-head"><span class="ba-tk">{b["ticker"]}</span>'
        f'<span class="ba-conv">c{b["conviction"]}</span>'
        f'<span class="ba-since">depuis {b["opened_at"]}</span></div>'
        f'<div class="ba-missing">manque : '
        + ", ".join(f'<b>{m}</b>' for m in b["missing"])
        + "</div></div>"
        for b in blind
    )
    return (
        '<div class="colhead"><span class="t">Positions en vol disclosuregle</span>'
        f'<span class="a">{len(blind)} position(s) sans entry / target / stop / kill-criteria '
        '&middot; le bot ne peut RIEN evaluer dessus tant que ces champs sont creux</span></div>'
        '<div class="card pad blindcard" style="margin-bottom:var(--s4)">'
        + items
        + "</div>"
    )


def _copilot_panel() -> str:
    """Sprint 5/6 surface : derniere prises de position du copilot adversarial.

    Lecture froide : verdict + pressure_score + ancrage. Outcome 30j si resolu.
    """
    try:
        from shared import storage as _stg

        rows = _stg.get_recent_copilot_interventions(limit=8)
    except Exception as e:
        return f'<div class="card pad"><div class="empty">copilot indisponible: {type(e).__name__}: {e}</div></div>'
    if not rows:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "None intervention du copilot pour le moment. Les pressure-tests "
            "apparaitront ici a chaque /position_buy /position_sell /override."
            "</div></div>"
        )
    lis = []
    # Fix canal "ce que le bot a detecte -> ce qu'il met sous le nez" (29/05) :
    # avant on truncait l'ancrage a 200 chars et on cachait brief + biases_active,
    # exactement les champs qui contiennent la vraie detection (cf intervention_3
    # CCJ qui avait tout capte mais que l'user n'a jamais lu).
    def _esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    for r in rows:
        ver = r.get("verdict") or "?"
        cls, label = _VERDICT_LABEL.get(ver, ("calm", ver))
        score = r.get("pressure_score")
        score_s = f"{score:.0f}" if isinstance(score, int | float) else "?"
        date = (r.get("created_at") or "")[:10]
        tk = r.get("ticker") or "?"
        dtype = r.get("decision_type") or "?"
        anc = (r.get("ancrage") or "").strip()
        brief = (r.get("brief") or "").strip()
        # Biases nommes (chips visibles, le bot a deja fait le diagnostic)
        biases_html = ""
        try:
            import json as _j

            biases = _j.loads(r.get("biases_active_json") or "[]") or []
        except Exception:
            biases = []
        if biases:
            chips = "".join(f'<span class="cp-bias">{_esc(str(b))}</span>' for b in biases[:4])
            biases_html = f'<div class="cp-biases">{chips}</div>'
        outc = r.get("outcome_label") or ""
        ret30 = r.get("return_30d_pct")
        outc_html = ""
        if outc:
            good = "outcome_good" in outc
            ocls = "ok" if good else "bad"
            ret_s = f"  ret30j {ret30:+.1f}%" if isinstance(ret30, int | float) else ""
            outc_html = f'<span class="cp-outc {ocls}">{outc}{ret_s}</span>'
        # Elevation visuelle si PRESSURE/STRONG_OPPOSE
        row_cls = "cp-row" + (" cp-flagged" if ver in ("PRESSURE", "STRONG_OPPOSE") else "")
        # Brief en accordeon (le diagnostic actionnable, jamais affiche avant)
        brief_html = ""
        if brief:
            brief_html = (
                '<div class="cp-brief-wrap">'
                '<div class="cp-brief-label">Diagnostic complet</div>'
                f'<div class="cp-brief">{_esc(brief)}</div>'
                '</div>'
            )
        lis.append(
            f'<div class="{row_cls}"><div class="cp-head">'
            f'<span class="cp-tk">{tk}</span>'
            f'<span class="cp-dtype">{dtype}</span>'
            f'<span class="cp-ver {cls}">{label}&nbsp;&middot;&nbsp;{score_s}</span>'
            f'<span class="cp-date">{date}</span></div>'
            f'<div class="cp-anc">{_esc(anc) or "(pas d\'ancrage)"}</div>'
            f'{biases_html}'
            f'{brief_html}'
            f'{outc_html}</div>'
        )
    return (
        '<div class="colhead"><span class="t">Copilot pressure before trades</span></div>'
        '<div class="card pad copilotcard" style="margin-bottom:var(--s4)">'
        + "".join(lis)
        + "<script>document.querySelectorAll('.copilotcard .cp-row').forEach(function(e){"
        "e.addEventListener('click',function(){e.classList.toggle('open')})});</script>"
        + "</div>"
    )


def _return_clustering_panel() -> str:
    """Sprint 17 — Data-defined clusters par correlation rendements reels.

    Per la critique : 'Laisser les donnees definir les clusters. Plutot que
    des etiquettes de theme posees a la main, clusteriser par correlation
    de rendements reels.'
    """
    # Cache : on ne recompute pas a chaque regen serve (cout yfinance)
    # On lit le dernier snapshot persiste, ou message + bouton trigger.
    try:
        from shared import storage as _stg

        with _stg.db() as cx:
            row = cx.execute(
                "SELECT id, snapshot_date, snapshot_json FROM data_clusters_snapshots "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
    except Exception:
        row = None
    if not row:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "First overlap measurement by correlation scheduled Saturday 18:00. Once available, pairs moving together will appear here."
            "</div></div>"
        )
    import json as _json

    try:
        data = _json.loads(row[2] or "{}")
    except Exception:
        return '<div class="card pad"><div class="empty">snapshot corrompu</div></div>'
    pairs = data.get("high_corr_pairs") or []
    clusters = data.get("clusters") or []
    n_mixed = sum(1 for c in clusters if c.get("mixed"))
    snapshot_date = row[1]

    pairs_html = "".join(
        f'<div class="dc-row">'
        f'<span class="dc-pair">{p["ticker_a"]} &harr; {p["ticker_b"]}</span>'
        f'<span class="dc-corr mono">{p["correlation"]:.2f}</span></div>'
        for p in pairs[:12]
    ) or '<div class="empty" style="padding:var(--s2) 0">none paire >0.7</div>'

    cluster_rows = []
    for c in clusters:
        if not c.get("mixed"):
            continue
        members = ", ".join(
            f'{m["ticker"]}<span class="dc-mf">({m["macro_factor"][:14]})</span>'
            for m in c["members"]
        )
        cluster_rows.append(
            f'<div class="dc-mix">'
            f'<div class="dc-mix-h">cluster #{c["cluster_id"]} (n={c["n_members"]})</div>'
            f'<div class="dc-mix-members">{members}</div></div>'
        )
    mix_html = "".join(cluster_rows) or '<div class="empty" style="padding:var(--s2) 0">none cluster avec macro_factor melange</div>'

    return (
        '<div class="colhead"><span class="t">Overlaps seen by prices</span>'
        f'<span class="a">{snapshot_date} &middot; returns correlation &middot; what truly moves together</span></div>'
        '<div class="card pad clustercard" style="margin-bottom:var(--s4)">'
        '<div class="dc-sub">'
        f'<div class="dc-sh">Paires correlees (>0.7)</div>'
        f'<div class="dc-list">{pairs_html}</div></div>'
        '<div class="dc-sub">'
        f'<div class="dc-sh">Clusters mixed macro_factor (concentration cachee) — n={n_mixed}</div>'
        f'<div class="dc-list">{mix_html}</div></div>'
        '</div>'
    )


def _wrapper_panel() -> str:
    """Sprint 16 — Placement PEA / CTO + flag PEA-eligible mal places + tax-loss harvest."""
    try:
        from intelligence import wrapper_tax as _wt

        alloc = _wt.compute_wrapper_allocation()
        losses = _wt.compute_tax_loss_harvest_candidates(min_loss_pct=-5)
    except Exception as e:
        return f'<div class="card pad"><div class="empty">wrapper indispo: {type(e).__name__}</div></div>'
    rows_alloc = []
    for k in ("PEA", "CTO", "unknown"):
        pct = alloc["allocation_pct"][k]
        eur = alloc["allocation_eur"][k]
        if eur == 0:
            continue
        rows_alloc.append(
            f'<div class="wr-row"><span class="wr-key">{k}</span>'
            f'<span class="wr-pct mono">{pct:.1f}%</span>'
            f'<span class="wr-eur mono">{eur:,.0f}€</span></div>'
        )
    misalloc_html = ""
    if alloc["n_pea_misallocated"]:
        items = "".join(
            f'<div class="wr-mis"><span class="wr-mis-tk">{m["ticker"]}</span>'
            f'<span class="wr-mis-pct mono">{m["weight_pct"]:.1f}%</span>'
            f'<span class="wr-mis-eur mono">{m["weight_eur"]:,.0f}€</span></div>'
            for m in alloc["pea_misallocated_in_cto"]
        )
        misalloc_html = (
            '<div class="wr-section">'
            f'<div class="wr-sh">PEA-eligibles loges au CTO (n={alloc["n_pea_misallocated"]})</div>'
            + items + '</div>'
        )
    loss_html = ""
    if losses:
        items = "".join(
            f'<div class="wr-mis"><span class="wr-mis-tk">{loss["ticker"]}</span>'
            f'<span class="wr-mis-pct mono neg">{loss["pnl_pct"]:+.1f}%</span>'
            f'<span class="wr-mis-eur mono">{loss["moins_value_eur"]:+,.0f}€</span></div>'
            for loss in losses
        )
        loss_html = (
            '<div class="wr-section">'
            f'<div class="wr-sh">Recolte moins-values CTO (seuil -5%, n={len(losses)})</div>'
            + items + '</div>'
        )
    return (
        '<div class="colhead"><span class="t">Placement fiscal (PEA / CTO)</span>'
        '<span class="a">tax-loss harvest + flag PEA-eligibles mal places</span></div>'
        '<div class="card pad wrappercard" style="margin-bottom:var(--s4)">'
        f'<div class="wr-alloc">{"".join(rows_alloc)}</div>'
        f'{misalloc_html}{loss_html}'
        '</div>'
    )


def _fx_exposure_panel() -> str:
    """Sprint 16 — exposition par devise (book euro avec sleeve USD/JPY/KRW)."""
    try:
        from intelligence import wrapper_tax as _wt

        fx = _wt.compute_fx_exposure()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">FX indispo: {type(e).__name__}</div></div>'
    if not fx:
        return ""
    names = _names()
    rows = []
    for cur, d in fx.items():
        pct = d["pct"]
        wcls = "high" if pct >= 40 else ("mid" if pct >= 15 else "low")
        # Sub : pattern accordeon comme [[geo-item]] (toggle .open au clic).
        sub_items = []
        for h in d.get("holdings", []):
            tk = h["tk"]
            nm = names.get(tk, "")
            sub_items.append(
                f'<div class="fx-stk"><span class="gnm">{nm or tk}</span>'
                f'<span class="gtk">{tk if nm else ""}</span>'
                f'<span class="gpc">{h["pct_of_cur"]:.0f}%</span>'
                f'<span class="gw">{h["eur"]:,.0f}&euro;</span></div>'.replace(",", "&#8239;")
            )
        sub_html = "".join(sub_items)
        rows.append(
            f'<div class="fx-row fx-item">'
            f'<div class="fx-head"><span class="fx-cur">{cur}</span>'
            f'<span class="fx-pct {wcls} mono">{pct:.1f}%</span>'
            f'<span class="fx-eur mono">{d["eur"]:,.0f}€</span>'
            f'<span class="fx-n">n={d["n_positions"]}</span>'
            f'<svg class="fx-chev" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6l4 4 4-4"/></svg></div>'
            f'<div class="fx-bar"><div class="fx-fill {wcls}" style="width:{min(pct, 100):.1f}%"></div></div>'
            f'<div class="fx-sub">{sub_html}</div></div>'
        )
    return (
        '<div class="colhead"><span class="t">Exposition par devise</span></div>'
        '<div class="card pad fxcard" style="margin-bottom:var(--s4)">'
        + "".join(rows)
        + '<script>document.querySelectorAll(".fxcard .fx-item").forEach(function(e){'
        + 'e.addEventListener("click",function(){e.classList.toggle("open")})});</script>'
        + "</div>"
    )


def _benchmark_panel() -> str:
    """Sprint 16 — alpha vs SOX (book return vs benchmark sector)."""
    try:
        from intelligence import benchmark as _bm

        bench = _bm.compute_alpha_vs_sox(months=6)
    except Exception as e:
        return f'<div class="card pad"><div class="empty">benchmark indispo: {type(e).__name__}</div></div>'
    if "error" in bench:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "Benchmark indispo (yfinance non installe ou SOX fetch failed)."
            "</div></div>"
        )
    alpha = bench["alpha_pct"]
    book_r = bench["book_return_pct"]
    bench_r = bench["bench_return_pct"]
    acls = "pos" if alpha > 0 else ("neg" if alpha < 0 else "neu")
    warning = bench.get("warning")
    warning_html = (
        f'<div class="bm-warn">⚠️ {warning}</div>' if warning else ""
    )
    return (
        '<div class="colhead"><span class="t">Real outperformance vs sector</span>'
        f'<span class="a">{bench["bench_window"]} &middot; book vs indice semi-conducteurs PHLX</span></div>'
        '<div class="card pad benchcard" style="margin-bottom:var(--s4)">'
        f'{warning_html}'
        '<div class="bm-grid">'
        f'<div class="bm-cell"><div class="bm-h">Book</div><div class="bm-v mono">{book_r:+.1f}%</div></div>'
        f'<div class="bm-cell"><div class="bm-h">SOX</div><div class="bm-v mono">{bench_r:+.1f}%</div></div>'
        f'<div class="bm-cell"><div class="bm-h">Alpha</div><div class="bm-v mono {acls}">{alpha:+.1f}%</div></div>'
        '</div>'
        f'<div class="bm-foot">{bench["interpretation"]}</div>'
        '</div>'
    )


def _kill_criteria_panel() -> str:
    """Sprint 15 — kill-criteria status per these. Triggered/at_risk en haut."""
    try:
        from shared import storage as _stg

        rows = _stg.get_all_latest_kca()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">kill-criteria indispo: {type(e).__name__}</div></div>'
    if not rows:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "Premiere verification quotidienne prevue demain 07h30. Les theses dont les conditions d'invalidation se declenchent apparaitront ici."
            "</div></div>"
        )
    counts = {"triggered": 0, "at_risk": 0, "dormant": 0}
    for r in rows:
        s = r.get("status", "dormant")
        counts[s] = counts.get(s, 0) + 1
    items = []
    for r in rows:
        if r["status"] == "dormant":
            continue
        tk = r.get("ticker", "?")
        s = r.get("status", "?")
        cls = "triggered" if s == "triggered" else "at_risk"
        conf = r.get("confidence") or 0
        reason = (r.get("dominant_reason") or "").strip()
        if len(reason) > 240:
            reason = reason[:237] + "..."
        evidence = (r.get("evidence_quote") or "").strip()[:200]
        reason = reason.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        evidence = evidence.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        items.append(
            f'<div class="kc-row {cls}">'
            f'<div class="kc-head"><span class="kc-tk">{tk}</span>'
            f'<span class="kc-status {cls}">{s}</span>'
            f'<span class="kc-conf mono">conf {conf}</span></div>'
            f'<div class="kc-reason">{reason}</div>'
            f'<div class="kc-ev">{evidence}</div></div>'
        )
    items_html = "".join(items) or (
        '<div class="empty" style="padding:var(--s25) 0">none these triggered/at_risk &mdash; ' +
        f'{counts["dormant"]} dormant</div>'
    )
    return (
        '<div class="colhead"><span class="t">Conditions d\'invalidation des theses</span>'
        f'<span class="a">triggered {counts["triggered"]} &middot; at risk {counts["at_risk"]} &middot; '
        f'dormant {counts["dormant"]} &middot; checked 07:30</span></div>'
        '<div class="card pad killcard" style="margin-bottom:var(--s4)">'
        + items_html
        + "</div>"
    )


def _spof_panel() -> str:
    """Sprint 14 — Single points of failure upstream.

    Critique : 'Ta vraie concentration n'est pas dans le book, elle est en
    amont : TSMC fabrique pour AMD, Broadcom, Astera. Un incident TSMC touche
    far more than TSMC alone. HBM = 3 suppliers, EUV = ASML only.'
    """
    try:
        from intelligence import spof_and_sizing as _sp

        spofs = _sp.compute_spof_graph()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">SPOF indispo: {type(e).__name__}</div></div>'
    if not spofs:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "Ticker classification in progress. Tech sheets will appear here once the pass is complete."
            "</div></div>"
        )
    rows = []
    for node, d in list(spofs.items())[:10]:
        pct = d["pct_of_book"]
        wcls = "high" if pct >= 30 else ("mid" if pct >= 15 else "low")
        deps = ", ".join(f"{x['ticker']}({x['share']:.0%})" for x in d["dependents"][:8])
        if len(d["dependents"]) > 8:
            deps += f" +{len(d['dependents']) - 8}"
        rows.append(
            f'<div class="sp-row">'
            f'<div class="sp-head"><span class="sp-node">{node}</span>'
            f'<span class="sp-pct {wcls} mono">{pct:.1f}%</span>'
            f'<span class="sp-eur mono">{d["total_exposure_eur"]:,.0f}€</span>'
            f'<span class="sp-n">n={d["n_dependents"]}</span></div>'
            f'<div class="sp-bar"><div class="sp-fill {wcls}" style="width:{min(pct, 100):.1f}%"></div></div>'
            f'<div class="sp-deps">{deps}</div></div>'
        )
    return (
        '<div class="colhead"><span class="t">Hidden upstream dependencies</span>'
        '<span class="a">if an upstream supplier breaks, everything depending on it breaks too</span></div>'
        '<div class="card pad spofcard" style="margin-bottom:var(--s4)">'
        + "".join(rows)
        + "</div>"
    )


def _mauboussin_sizing_panel() -> str:
    """Sprint 14 — sizing implied par fade-rate vs sizing reel.

    Critique : 'Le sizing conviction devient alors l'ecart entre poids
    reel et poids-implicite-par-le-fade — rigoureux, pas un nombre magique'.
    """
    try:
        from intelligence import spof_and_sizing as _sp
        from shared import book as _bk

        sizing = _sp.compute_mauboussin_sizing()
        # F5 fix 29/05 : cross-reference valo_above_bull_case
        bull_tickers = {x["ticker"] for x in _sp.list_above_bull_case()}
        # F10 fix 29/05 round 2 : surface stop_distance% par row pour rendre
        # la contradiction stops decroches du fade visible. Astera fade=80
        # mais stop -51% (large), Synopsys fade=8 mais stop -20% (idem),
        # SK Hynix stop -43%. No relation coherente -- regression du
        # Day 5 sur l'asymetrie tautologique. Au lieu de le decrire dans
        # le TODO, on l'affiche : 3 colonnes (conv, fade, stop_dist%)
        # cote a cote permettent de voir l'incoherence d'un coup d'oeil.
        book_idx = _bk.get_book_index()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">Mauboussin sizing indispo: {type(e).__name__}</div></div>'
    if not sizing:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "Not yet de meta classifies pour calculer le sizing implicite."
            "</div></div>"
        )
    rows = []
    for tk, d in sizing.items():
        gap = d["gap_pp"]
        gcls = "neg" if gap > 0.5 else ("pos" if gap < -0.5 else "neu")
        fade = d.get("fade_rate_score") or 0
        fcls = "high" if fade >= 60 else ("mid" if fade >= 30 else "low")
        # Canonise via [[currency-native-invariant]] : stop_price stocke en
        # NATIVE -> doit etre compare a un current NATIVE, pas EUR.
        ln = book_idx.get(tk)
        stop_dist_html = '<span class="ms-stopd mono">stop ?</span>'
        stop_dist = _stop_distance_pct_native(tk, ln.stop_price) if ln and ln.stop_price else None
        if stop_dist is not None:
            outlier = (fade >= 60 and stop_dist > 40) or (fade <= 20 and stop_dist < 25)
            ocls = " outlier" if outlier else ""
            stop_dist_html = (
                f'<span class="ms-stopd mono{ocls}" '
                f'title="distance courant -> stop ; fade-coherence">'
                f'stop &minus;{stop_dist:.0f}%</span>'
            )
        fragile_flag = ""
        if tk in bull_tickers:
            fragile_flag = (
                '<span class="ms-frag" title="also flags valo > bull case '
                'in another view">valo &gt; bull</span>'
            )
        rows.append(
            f'<div class="ms-row">'
            f'<span class="ms-tk">{tk}</span>'
            f'<span class="ms-conv mono">c{d["conviction"]}</span>'
            f'<span class="ms-fade {fcls} mono">fade {fade}</span>'
            f'{stop_dist_html}'
            f'<span class="ms-target mono">target {d["target_pct"]:.1f}%</span>'
            f'<span class="ms-actual mono">reel {d["actual_pct"]:.1f}%</span>'
            f'<span class="ms-gap {gcls} mono">{gap:+.1f}pp</span>'
            f'{fragile_flag}</div>'
        )
    return (
        '<div class="colhead"><span class="t">Rigorous calibration</span>'
        '<span class="a">real size vs theoretical size (conviction &times; moat erosion speed)</span></div>'
        '<div class="card pad mauboussincard" style="margin-bottom:var(--s4)">'
        + "".join(rows)
        + "</div>"
    )


def _valo_above_bull_panel() -> str:
    """Sprint 14 — flag positions ou expectations > bull case (reverse-DCF)."""
    try:
        from intelligence import spof_and_sizing as _sp

        flags = _sp.list_above_bull_case()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">valo unavailable: {type(e).__name__}</div></div>'
    if not flags:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "None position avec expectations > bull case identifiees."
            "</div></div>"
        )
    rows = []
    for f in flags:
        pe = f.get("pe_or_proxy")
        pe_s = f"P/E {pe:.0f}" if pe else "P/E ?"
        rows.append(
            f'<div class="vb-row">'
            f'<div class="vb-head"><span class="vb-tk">{f["ticker"]}</span>'
            f'<span class="vb-pe mono">{pe_s}</span></div>'
            f'<div class="vb-priced">{f["what_priced_in"]}</div>'
            f'<div class="vb-rat">{f["rationale"]}</div></div>'
        )
    return (
        '<div class="colhead"><span class="t">Valuations already beyond bull case</span></div>'
        '<div class="card pad valocard" style="margin-bottom:var(--s4)">'
        + "".join(rows)
        + "</div>"
    )


def _factor_exposures_panel() -> str:
    """Sprint 13 — Decomposition du book en facteurs macro reels.

    Per critique : 'transforme 78% compute en risque chiffre et actionnable'.
    """
    try:
        from intelligence import factor_exposures as _fe

        facts = _fe.compute_factor_exposures()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">factor exposures indispo: {type(e).__name__}</div></div>'
    if not facts:
        return '<div class="card pad"><div class="empty">none position classifiee</div></div>'
    # Tri : composites en TETE (vue agregée d'abord), puis sub-buckets par pct
    sorted_f = sorted(facts.items(), key=lambda kv: (not kv[1].get("is_composite"), -kv[1]["pct_of_book"]))
    rows = []
    for name, d in sorted_f:
        pct = d["pct_of_book"]
        wcls = "high" if pct >= 30 else ("mid" if pct >= 10 else "low")
        # F9 fix : afficher le theme thesis user a cote de chaque ticker
        # quand il y a divergence entre le macro_factor (vue Bets) et le
        # theme (vue Theses). Ex MHI : macro="Industrial reshoring" mais
        # theme="Defense" -> classification croisee enfin visible.
        themes_overlay = d.get("themes_overlay") or {}
        tks_html_list = []
        for t in d["tickers"][:8]:
            th = themes_overlay.get(t)
            if th and th.lower() != name.lower():
                tks_html_list.append(f'{t}<span class="fe-th">→{th}</span>')
            else:
                tks_html_list.append(t)
        tks = ", ".join(tks_html_list)
        if len(d["tickers"]) > 8:
            tks += f" +{len(d['tickers']) - 8}"
        is_comp = d.get("is_composite")
        row_extra = ""
        if is_comp:
            row_extra = (
                f'<div class="fe-comp-note">'
                f'aggregat de {len(d.get("composes") or [])} facteurs co-stresses ('
                f'{", ".join(d.get("composes") or [])}) &middot; '
                "le scenario AI capex -30% les frappe ensemble"
                "</div>"
            )
        row_cls = "fe-row" + (" fe-composite" if is_comp else "")
        rows.append(
            f'<div class="{row_cls}">'
            f'<div class="fe-head"><span class="fe-name">{name}</span>'
            f'<span class="fe-pct {wcls} mono">{pct:.1f}%</span>'
            f'<span class="fe-eur mono">{d["eur"]:,.0f}€</span></div>'
            f'<div class="fe-bar"><div class="fe-fill {wcls}" style="width:{min(pct, 100):.1f}%"></div></div>'
            f'<div class="fe-tks">{tks}  (n={d["n_positions"]})</div>'
            f'{row_extra}'
            "</div>"
        )
    return (
        '<div class="colhead"><span class="t">Bets du portefeuille</span>'
        '<span class="a">what you really bet on, by macro factor &middot; a single big bet dominates</span></div>'
        '<div class="card pad factorscard" style="margin-bottom:var(--s4)">'
        + "".join(rows)
        + "</div>"
    )


# ============================================================================
# Position-card #1 (couche 3 render, spec user red-team 07/06)
# ----------------------------------------------------------------------------
# Vue plein-ecran d'UNE position. Spec corrigee (3 catches absorbes) :
# - Catch 1 : position_type assigne via hook tamper-evident (couche 1)
# - Catch 2 : exit_policy != size_action (couche 2 derive_steer)
# - Catch 3 : "ratio infini" remplace par "downside structurel non-borne par prix"
# Deep-link : section data-page="position-card", chaque card id="card-TICKER"
# ============================================================================


def _slug_ticker(ticker: str) -> str:
    """Convert ticker -> URL-safe id (ASML.AS -> ASML-AS)."""
    return ticker.replace(".", "-").upper()


def _position_card(inputs, steer_v2) -> str:
    """Rendre une seule position-card depuis CardInputs (etape 2) + SteerOutput
    (etape 3). Source UNIQUE -- aucune re-query, lis tout depuis inputs.

    Inputs :
      inputs   : intelligence.card_inputs.CardInputs (frozen, etape 2)
      steer_v2 : intelligence.card_steer.SteerOutput (frozen, etape 3)
    """
    from intelligence.position_steer import derive_steer

    thesis = inputs.thesis
    ticker = inputs.ticker
    slug = _slug_ticker(ticker)
    conv = inputs.conviction_current or "?"
    direction = thesis.get("direction") or "long"
    horizon = thesis.get("horizon") or "?"
    opened = (thesis.get("opened_at") or "")[:10]
    reviewed = (thesis.get("last_reviewed") or "")[:10] or "never"

    # Couche 1 lue depuis inputs
    ptype = inputs.position_type or "priced"
    tags = inputs.position_tags or []
    justif = inputs.structural_justification

    # Couche 2 verdict erosion + driver_status (depuis inputs)
    verdict = inputs.erosion_verdict
    erosion_computed_at = (inputs.erosion_computed_at or "")[:16] or None
    driver_status = inputs.erosion_driver_status or []

    # Position M1 depuis BookLine canonique (inputs.book_line)
    bl = inputs.book_line
    qty = (getattr(bl, "qty", 0) or 0) if bl else 0
    current_price = (
        getattr(bl, "last_price_native", None) if bl else None
    ) or (getattr(bl, "current_price_eur", None) if bl else None)
    ccy = (getattr(bl, "last_price_currency", None) if bl else None) or "EUR"
    price_asof = getattr(bl, "price_asof", None) if bl else None
    weight_pct = inputs.weight_pct
    cost_basis = (qty * (getattr(bl, "avg_cost_eur", 0) or 0)) if bl else 0
    # P&L canonique via helper #118 (avg_cost_eur + value_eur Datum fx-correct).
    # Avant : pnl_pct = (weight_market_eur / cost_basis - 1) * 100 -- mais
    # weight_market_eur derive de current_price_eur (calc separe potentiellement
    # avec un FX different de positions.fx_rate_to_eur) -> divergence ~7% sur
    # SK Hynix. Maintenant : value_eur recompute = qty * last_price_native * fx
    # cohérent dans la meme row positions.
    if bl and qty > 0 and cost_basis > 0:
        _last_native = getattr(bl, "last_price_native", None)
        _fx = getattr(bl, "fx_rate_to_eur", None)
        if _last_native and _fx:
            weight_eur = qty * _last_native * _fx  # value_eur canonique cohérent
            pnl_eur = weight_eur - cost_basis
            pnl_pct = (weight_eur / cost_basis - 1) * 100
        else:
            weight_eur = (getattr(bl, "weight_market_eur", 0) or 0)
            pnl_eur = (weight_eur - cost_basis) if weight_eur else 0
            pnl_pct = ((weight_eur / cost_basis - 1) * 100) if weight_eur else 0
    else:
        weight_eur = (getattr(bl, "weight_market_eur", 0) or 0) if bl else 0
        pnl_eur = 0
        pnl_pct = 0

    # Theses entry/partial/full/stop depuis thesis dict (inputs.thesis)
    entry = thesis.get("entry_price")
    partial = thesis.get("target_partial")
    full = thesis.get("target_full")
    stop = thesis.get("stop_price")
    invals = thesis.get("invalidation_triggers") or []
    if isinstance(invals, str):
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            invals = json.loads(invals)

    # Couche 2 (legacy) : derive_steer pour les sous-details (forbidden/allowed).
    # Le verdict UNIFIE 5-state est steer_v2 (etape 3).
    try:
        steer = derive_steer(
            position_type=ptype,
            erosion_verdict=verdict,
            current_weight_pct=weight_pct,
            conviction=conv if isinstance(conv, int) else 5,
        )
    except Exception:
        steer = None

    # Bandeau fail-closed (etape 3) -- adoption substrat alert_vocabulary :
    # consomme render_token(get_word("FAIL_CLOSED")) au lieu de hardcode #7a1f1f.
    # Premiere adoption REELLE en prod du vocabulary (cf #116, geste 2 Olivier).
    bandeau_html = ""
    if steer_v2 and steer_v2.bandeau:
        from shared.alert_vocabulary import get_word, render_token
        _fc_word = get_word("FAIL_CLOSED")
        _fc_rt = render_token(_fc_word)
        # Mapping token couleur -> CSS var existante du dashboard
        # (theme oklch ; les var sont definies dans le CSS global du dashboard).
        _color_bg = {
            "calm": "var(--steel-mute, #4a5560)",
            "neutral": "var(--steel, #5a6470)",
            "info": "var(--steel, #5a6470)",
            "warning": "var(--warn, #c08838)",
            "danger": "var(--bear, #7a1f1f)",
            "critical": "var(--bear, #7a1f1f)",
        }.get(_fc_rt.color, "var(--bear, #7a1f1f)")
        items = "".join(f"<span>{b}</span>" for b in steer_v2.bandeau)
        # Le LABEL "FAIL-CLOSED L15" reste user-facing (court, distinctif).
        # Le SUBSTRAT vocabulary fournit la COULEUR canonique (token "danger" -> var--bear)
        # et le tooltip enrichi via word.meaning -- pas un sweep du label.
        bandeau_html = (
            f'<div class="pc-bandeau" style="background:{_color_bg};color:#fff;'
            'padding:8px 12px;border-radius:4px;margin:-2px -2px 12px -2px;'
            'font-size:11px;font-weight:600;display:flex;gap:14px;align-items:center;" '
            f'data-vocab="FAIL_CLOSED" title="{_fc_word.meaning}">'
            '<span>⚠ FAIL-CLOSED L15</span>'
            f'<span style="opacity:0.9;font-weight:500;">{items}</span>'
            '</div>'
        )

    # #128 banner proxy price discret -- cohérent avec chip book row L6431.
    # SK Hynix : GDR EUR détenu, valo via cote KRW × fx (yfinance ne sert pas
    # le GDR EUR). Coût + realized restent EUR-corrects via ledger -- juste
    # info, pas alarme.
    proxy_banner_html = ""
    try:
        from shared.book import is_proxy_price as _ipp
        _proxy_reason = _ipp(ticker)
        if _proxy_reason:
            proxy_banner_html = (
                f'<div class="pc-proxy-banner" style="background:var(--bg-2);'
                'border-left:3px solid var(--steel);padding:6px 12px;margin:-2px -2px 12px -2px;'
                'font-size:11px;color:var(--steel);" '
                f'title="{_proxy_reason}">'
                '<span style="font-weight:600;">·proxy</span>'
                f'<span style="opacity:0.85;margin-left:8px;">{_proxy_reason}</span>'
                '</div>'
            )
    except Exception:
        pass

    # Verdict 5-state badge en tete
    verdict_v2_html = ""
    if steer_v2:
        v_color = {
            "HOLD": ("#3a9d4e", "#e8f5e9"),
            "TRIM_TO_X": ("#b8860b", "#fff8e1"),
            "ADD_TO_X": ("#1976d2", "#e3f2fd"),
            "EXIT": ("#7a1f1f", "#ffebee"),
            "REVIEW": ("#666", "#f5f5f5"),
        }.get(steer_v2.verdict.value, ("#666", "#f5f5f5"))
        verdict_v2_html = (
            f'<span style="display:inline-block;padding:3px 10px;border-radius:3px;'
            f'font-size:11px;font-weight:700;background:{v_color[0]};color:#fff;'
            f'margin-left:8px;letter-spacing:0.5px;">▶ {steer_v2.verdict.value}</span>'
        )

    # Adoption substrat sector_profiles : afficher tier d'evidence + sous-secteur.
    # Premiere adoption REELLE en prod du profile_for_ticker (cf #116, geste 2).
    # Tier S = expertise validee sur holdings ; tier B = UNCLASSIFIED fail-closed.
    sector_profile_html = ""
    try:
        from shared.sector_profiles import profile_for_ticker
        _sp, _sp_unc = profile_for_ticker(ticker)
        _tier_color = {"S": "var(--acc, #3a9d4e)", "A": "var(--steel, #5a6470)", "B": "var(--steel-mute, #888)"}.get(
            _sp.evidence_tier, "var(--steel-mute, #888)"
        )
        _tier_label = "validé holdings" if _sp.evidence_tier == "S" else ("prior littérature" if _sp.evidence_tier == "A" else "non-classé fail-closed")
        _kpis_n = len(_sp.deliverable_kpis)
        _kpis_label = f"{_kpis_n} KPIs mesurables" if _kpis_n else "aucun KPI (no_read)"
        _sp_data = "unclassified" if _sp_unc else _sp.name
        sector_profile_html = (
            f'<div class="pc-sector-profile" '
            f'data-profile="{_sp_data}" data-tier="{_sp.evidence_tier}" '
            f'style="font-size:10px;color:{_tier_color};opacity:0.85;margin:2px 0 6px 0;'
            'letter-spacing:0.3px;">'
            f'sector : <b>{_sp.name}</b> &middot; tier <b>{_sp.evidence_tier}</b> ({_tier_label}) '
            f'&middot; {_kpis_label}'
            '</div>'
        )
    except Exception as e:
        # render.py n'a pas de logger module ; silent-miss L7 (la card s'affiche sans le tag profile)
        print(f"[render] sector_profile_html for {ticker} failed: {e}")

    # Drift conviction surface si delta != 0
    drift_html = ""
    if inputs.conviction_drift_delta != 0:
        sign = "+" if inputs.conviction_drift_delta > 0 else ""
        drift_cls = "ok" if inputs.conviction_drift_delta > 0 else "warn"
        drift_html = (
            f'<span class="pc-drift {drift_cls}" style="margin-left:8px;'
            'font-size:10px;opacity:0.85">'
            f'drift {sign}{inputs.conviction_drift_delta} '
            f'(PIT c{inputs.conviction_at_entry} → now c{inputs.conviction_current}, '
            f'{inputs.conviction_n_drifts} change(s))'
            '</span>'
        )

    # Asymetrie : DERIVE UNE SEULE FOIS via PositionView (SPEC Phase 3).
    # Le calc local entry/full/stop est SUPPRIME -- toute la card consomme view.asym_ratio.
    # Test verrouillant : grep "ratio = (full" hors position_view = build rouge.
    from shared.position_view import compute_position
    _view = compute_position(
        thesis_id=inputs.thesis_id,
        card_inputs=inputs,
        steer_output=steer_v2,
        price_datum=None, fx_datum=None, value_eur_datum=None,
    )
    if ptype == "structural":
        # Catch 3 render.py:2293 -- downside non-borne par prix.
        # view.upside_pct est rempli (depuis target/entry), downside/ratio = None.
        up_html = (
            '<div class="pc-asym-line"><span class="pc-asym-k">upside</span>'
            f'<span class="pc-asym-v mono">+{_view.upside_pct:.1f}%</span></div>'
        ) if _view.upside_pct is not None else ""
        asym_html = up_html + (
            '<div class="pc-asym-line"><span class="pc-asym-k">downside</span>'
            '<span class="pc-asym-v">STRUCTUREL non-borne par prix</span></div>'
            '<div class="pc-asym-line"><span class="pc-asym-k">ratio</span>'
            '<span class="pc-asym-v" style="opacity:0.7">n/a (axe structural &ne; axe prix)</span></div>'
        )
    elif _view.asym_ratio is not None and _view.upside_pct is not None and _view.downside_pct is not None:
        # Priced/tactical : asym_ratio thesis-level via view (entry/target/stop)
        asym_html = (
            '<div class="pc-asym-line"><span class="pc-asym-k">upside</span>'
            f'<span class="pc-asym-v mono">{_view.upside_pct:+.1f}%</span></div>'
            '<div class="pc-asym-line"><span class="pc-asym-k">downside</span>'
            f'<span class="pc-asym-v mono">{_view.downside_pct:+.1f}%</span></div>'
            '<div class="pc-asym-line"><span class="pc-asym-k">ratio</span>'
            f'<span class="pc-asym-v mono">{_view.asym_ratio:.2f}&times;</span></div>'
        )
    else:
        asym_html = '<div class="pc-empty">stop/target non definis</div>'

    # Slider : UN SEUL MÈTRE — % depuis ton coût (cost_native via fx_now).
    # cf principe Olivier 09/06 23h+ : 0 = avg_cost (point de départ), stop/target
    # à leurs % depuis cost, dot à perf actuelle depuis cost (≡ P&L EUR). Tous
    # comparables sur le même axe signed. SK Hynix : target_pct ≈ -0.7% (cost
    # rattrapé via renforcements) → target sous 0 honnête, le split Closest/Beyond
    # le range correctement via cur_native ≥ target_native.
    _gp = _gauge_pcts_from_cost(bl)
    if _gp and _gp.get("dot_pct") is not None:
        slider_html = _position_axis_pct(
            _gp.get("stop_pct"),
            _gp.get("target_pct"),
            _gp.get("dot_pct"),
            pnl_position_pct=pnl_pct,
        )
    elif stop and entry and full and current_price:
        # Fallback ancien comportement entry-natif si BookLine EUR incomplet.
        slider_html = _position_axis(entry, stop, full, current_price, pnl_position_pct=pnl_pct)
    elif entry and full and current_price:
        # No stop (structural) : montre seulement entry-current-target
        cur_pct = (current_price / entry - 1) * 100
        tgt_pct = (full / entry - 1) * 100
        ax = max(abs(tgt_pct), abs(cur_pct), 10.0)
        cur_v = max(0.0, min(100.0, 50.0 + (cur_pct / ax) * 50.0))
        tgt_v = max(0.0, min(100.0, 50.0 + (tgt_pct / ax) * 50.0))
        slider_html = (
            '<div class="pc-slider" style="position:relative;height:8px;'
            'background:linear-gradient(90deg, var(--bg-2) 0%, var(--bg-2) 50%, '
            'rgba(56,142,60,0.18) 50%, rgba(56,142,60,0.32) 100%);'
            'border-radius:2px;margin:14px 0;">'
            f'<div style="position:absolute;left:50%;width:1px;height:14px;'
            'top:-3px;background:var(--ink-3);" title="entry"></div>'
            f'<div style="position:absolute;left:{tgt_v:.1f}%;width:1px;height:14px;'
            'top:-3px;background:#3a9d4e;" title="target"></div>'
            f'<div style="position:absolute;left:{cur_v:.1f}%;width:9px;height:9px;'
            'top:-1px;border-radius:50%;background:var(--ink-1);transform:translate(-50%,0);"></div>'
            '</div>'
            '<div class="pc-slider-l" style="display:flex;justify-content:space-between;'
            'font-size:10px;color:var(--ink-3);">'
            '<span>downside structurel</span><span>entry</span>'
            f'<span>+{tgt_pct:.0f}% target</span></div>'
        )
    else:
        slider_html = ""

    # Driver-status block (V1 : si erosion compute)
    if driver_status:
        drv_rows = ""
        for d in driver_status:
            st = d.get("status", "?")
            st_cls = {"intact": "ok", "eroding": "warn", "broken": "neg"}.get(st, "neu")
            net = d.get("net", 0)
            drv_rows += (
                '<div class="pc-driver">'
                f'<span class="pc-driver-name">{d.get("driver", "?")[:80]}</span>'
                f'<span class="pc-driver-st {st_cls}">{st}</span>'
                f'<span class="pc-driver-net mono">net {net:+.2f}</span>'
                '</div>'
            )
        n_conf = inputs.erosion_n_confirm
        n_ero = inputs.erosion_n_erode
        n_inv = inputs.erosion_n_invalidation_hit
        verdict_cls = {
            "INTACT": "ok", "EROSION_DETECTED": "warn",
            "INVALIDATION_HIT": "neg", "STALE_UNUPDATED": "warn",
            "REVIEW_DUE_DEGRADED": "neu",
        }.get(verdict, "neu")
        verdict_html = (
            '<div class="pc-section">'
            '<div class="pc-section-h">THESE -- VERDICT MOTEUR #2</div>'
            f'<div class="pc-verdict {verdict_cls}">{verdict or "?"} '
            f'<span style="font-size:10px;opacity:0.7">'
            f'computed {erosion_computed_at} &middot; '
            f'{n_conf} confirms / {n_ero} erodes / {n_inv} invalidations'
            '</span></div>'
            + drv_rows
            + '</div>'
        )
    else:
        verdict_html = (
            '<div class="pc-section">'
            '<div class="pc-section-h">THESE -- VERDICT MOTEUR #2</div>'
            '<div class="pc-verdict neu" style="font-style:italic">non compute '
            '(cron erosion pas encore wire) &middot; verdict sera disponible '
            'apres 1er run compute_all_active_theses</div>'
            '</div>'
        )

    # Invalidation triggers list (count fired depuis erosion)
    inv_html = ""
    if invals:
        inv_html = (
            '<div class="pc-section">'
            f'<div class="pc-section-h">INVALIDATION TRIGGERS '
            f'({inputs.erosion_n_invalidation_hit}/{len(invals)} fired)</div>'
            + "".join(
                f'<div class="pc-inv">&#9675; {(t if isinstance(t, str) else str(t))[:160]}</div>'
                for t in invals
            )
            + '</div>'
        )

    # ── Section WHAT CHANGED SINCE ENTRY (etape 6) ────────────────────────
    # Source : inputs.erosion_classifications (persistees couche 1).
    # Top-5 par materiality * confidence (signaux les plus impactants).
    what_changed_html = ""
    if inputs.erosion_classifications:
        scored = sorted(
            inputs.erosion_classifications,
            key=lambda c: float(c.get("materiality") or 0) * float(c.get("confidence") or 0),
            reverse=True,
        )[:5]
        rows = []
        for c in scored:
            rel = c.get("relation") or "neutral"
            bears = c.get("bears_on") or "none"
            mat = float(c.get("materiality") or 0)
            conf = float(c.get("confidence") or 0)
            idx = c.get("target_index")
            quote = (c.get("evidence_quote") or "")[:120]
            rationale = (c.get("rationale") or "")[:120]
            rel_cls = {
                "confirms": "ok", "erodes": "warn",
                "triggers": "neg", "neutral": "neu",
            }.get(rel, "neu")
            target_label = (
                f"{bears.upper()[0:3]}[{idx}]"
                if idx is not None and bears in ("driver", "invalidation")
                else "—"
            )
            rows.append(
                '<div class="pc-changed-row">'
                f'<span class="pc-changed-rel {rel_cls} mono">{rel}</span>'
                f'<span class="pc-changed-target mono">{target_label}</span>'
                f'<span class="pc-changed-conf mono" style="opacity:0.7">'
                f'mat {mat:.1f} · conf {conf:.2f}</span>'
                f'<span class="pc-changed-quote" style="font-size:11px">'
                f'{rationale or quote or "—"}</span>'
                '</div>'
            )
        what_changed_html = (
            '<div class="pc-section">'
            f'<div class="pc-section-h">WHAT CHANGED SINCE ENTRY '
            f'(top-{len(scored)}/{len(inputs.erosion_classifications)} classifications)</div>'
            + "".join(rows)
            + '</div>'
        )
    elif inputs.erosion_verdict is None:
        what_changed_html = (
            '<div class="pc-section">'
            '<div class="pc-section-h">WHAT CHANGED SINCE ENTRY</div>'
            '<div class="pc-empty" style="font-style:italic;opacity:0.7">'
            'aucune classification persistee (cron erosion pas encore wire ; '
            'compute_all_active_theses produira la timeline post-1er run)</div>'
            '</div>'
        )

    # ── Section DISCIPLINE FLAGS (etape 6) ────────────────────────────────
    # Compose les monitors existants par ticker (pas duplication).
    flags = []
    if inputs.kill_status and inputs.kill_status != "dormant":
        kc = "neg" if inputs.kill_status == "triggered" else "warn"
        flags.append(("KILL_CRITERIA", inputs.kill_status, kc))
    if inputs.over_cap_status == "over":
        op_pct = f"{inputs.over_cap_pct:.1f}%" if inputs.over_cap_pct else "?"
        flags.append(("OVER_CAP", f"weight {op_pct}", "warn"))
    if inputs.bias_events_open:
        bias_names = ", ".join(
            sorted({(b.get("bias") or "?") for b in inputs.bias_events_open})
        )
        flags.append(("BIAS_OPEN", f"{len(inputs.bias_events_open)} ({bias_names})", "warn"))
    if inputs.ballast_membership:
        flags.append(("BALLAST", "membre ballast_strict", "ok"))
    if inputs.conviction_n_drifts > 0:
        flags.append(
            ("CONV_DRIFT", f"{inputs.conviction_n_drifts} drift(s) historiques", "neu")
        )

    discipline_html = ""
    if flags:
        rows = []
        for label, value, cls in flags:
            rows.append(
                '<div class="pc-flag-row">'
                f'<span class="pc-flag-label {cls} mono">{label}</span>'
                f'<span class="pc-flag-value">{value}</span>'
                '</div>'
            )
        discipline_html = (
            '<div class="pc-section">'
            f'<div class="pc-section-h">DISCIPLINE FLAGS ({len(flags)} actifs)</div>'
            + "".join(rows)
            + '</div>'
        )

    # ── Section COUNTER-ARGUMENT (etape 6) ────────────────────────────────
    # Source : bot_copilot_interventions latest (decision_copilot pressure).
    counter_html = ""
    if inputs.counter_argument_brief:
        ca_at = (inputs.counter_argument_at or "")[:10]
        ps = inputs.counter_argument_pressure_score
        ps_chip = ""
        if ps is not None:
            ps_cls = "neg" if ps >= 7 else "warn" if ps >= 4 else "neu"
            ps_chip = (
                f'<span class="pc-ca-pressure {ps_cls} mono" style="margin-left:8px">'
                f'pressure {ps}/10</span>'
            )
        counter_html = (
            '<div class="pc-section">'
            f'<div class="pc-section-h">CONTRE-ARGUMENT (decision_copilot {ca_at})'
            f'{ps_chip}</div>'
            f'<div class="pc-ca-brief" style="font-style:italic">'
            f'« {inputs.counter_argument_brief[:400]} »</div>'
            '</div>'
        )

    # ── Section SIZING 3-WAY (levier #4 sizing asymetrie-first) ────────────
    # real (weight live) / target-conv (cap_for_conviction) / target-edge
    # (ruin_budget / |downside|). Le BINDING = min des 2 targets contraint.
    # Structural -> target_edge n/a (downside non-borne par prix).
    sizing_3way_html = ""
    if inputs.cap_for_conviction_pct is not None:
        # Determine couleur pour chaque cell
        cap_cls = "ok" if inputs.weight_pct <= inputs.cap_for_conviction_pct else "warn"
        if inputs.target_edge_pct is not None:
            edge_cls = "ok" if inputs.weight_pct <= inputs.target_edge_pct else "warn"
            edge_value = f"{inputs.target_edge_pct:.2f}%"
        else:
            edge_cls = "neu"
            edge_value = "structural" if inputs.position_type == "structural" else "n/a"
        real_cls = "ok" if (inputs.binding_target_pct and inputs.weight_pct <= inputs.binding_target_pct) else "neg"
        binding_label = {
            "conv": "cap_conviction (sub-Kelly N<100)",
            "edge": "target_edge (asymetrie-first, ruin_budget contraint)",
            "structural": "structural (downside non-borne par prix, cap conv prime)",
        }.get(inputs.sizing_binding or "", "?")
        binding_value = (
            f"{inputs.binding_target_pct:.2f}%"
            if inputs.binding_target_pct is not None else "?"
        )
        sizing_3way_html = (
            '<div class="pc-section">'
            '<div class="pc-section-h">SIZING 3-WAY (levier #4 asymetrie-first)</div>'
            '<div class="pc-sizing-grid" style="display:grid;'
            'grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:12px">'
            '<div class="pc-sizing-cell">'
            f'<div class="pc-sizing-k" style="opacity:0.6;font-size:10px">REAL (live)</div>'
            f'<div class="pc-sizing-v mono {real_cls}">{inputs.weight_pct:.2f}%</div>'
            '</div>'
            '<div class="pc-sizing-cell">'
            f'<div class="pc-sizing-k" style="opacity:0.6;font-size:10px">target-conv (cap c{inputs.conviction_current or "?"})</div>'
            f'<div class="pc-sizing-v mono {cap_cls}">{inputs.cap_for_conviction_pct:.2f}%</div>'
            '</div>'
            '<div class="pc-sizing-cell">'
            f'<div class="pc-sizing-k" style="opacity:0.6;font-size:10px">target-edge (ruin {inputs.ruin_budget_per_name_pct:.2f}%/NAV)</div>'
            f'<div class="pc-sizing-v mono {edge_cls}">{edge_value}</div>'
            '</div>'
            '</div>'
            f'<div class="pc-sizing-binding" style="margin-top:6px;font-size:11px">'
            f'<b>BINDING = {binding_value}</b> &middot; <span style="opacity:0.75">{binding_label}</span>'
            '</div>'
            '</div>'
        )

    # Steer block (Catch 2 : EXIT et SIZE separes)
    if steer:
        ep = steer.exit_policy
        sa = steer.size_action
        size_cls = {"no_action": "ok", "rightsize": "warn", "urgent_rightsize": "neg"}.get(sa.action, "neu")
        exit_cls = {"hold": "ok", "review": "warn", "review_due_degraded": "neu",
                    "exit_now": "neg", "tighten_stop": "warn", "trim_aggressive": "warn"}.get(ep.action, "neu")
        forbidden_html = ""
        if ep.forbidden:
            forbidden_html = (
                '<div class="pc-steer-list-h">INTERDIT (anti-pattern type ' + ptype + ') :</div>'
                + "".join(f'<div class="pc-steer-li neg">&#10007; {x}</div>' for x in ep.forbidden)
            )
        allowed_html = ""
        if ep.allowed:
            allowed_html = (
                '<div class="pc-steer-list-h">AUTORISE :</div>'
                + "".join(f'<div class="pc-steer-li ok">&#10003; {x}</div>' for x in ep.allowed)
            )
        size_extra = ""
        if sa.action != "no_action":
            size_extra = (
                f' &middot; trim qty {sa.target_qty_delta_pct:+.1f}% pour ramener au cap'
            )
        steer_html = (
            '<div class="pc-section">'
            '<div class="pc-section-h">STEER (Catch 2 : type &amp; cap = 2 axes orthogonaux)</div>'
            f'<div class="pc-steer-line"><span class="pc-steer-k {exit_cls}">EXIT</span>'
            f'<span class="pc-steer-action mono">{ep.action.upper()}</span></div>'
            f'<div class="pc-steer-reason">{ep.reason}</div>'
            f'<div class="pc-steer-line"><span class="pc-steer-k {size_cls}">SIZE</span>'
            f'<span class="pc-steer-action mono">{sa.action.upper()}</span></div>'
            f'<div class="pc-steer-reason">{sa.reason}{size_extra}</div>'
            + forbidden_html + allowed_html
            + '</div>'
        )
    else:
        steer_html = ""

    # Justification structural (si applicable)
    justif_html = ""
    if ptype == "structural" and justif:
        justif_html = (
            '<div class="pc-section">'
            '<div class="pc-section-h">STRUCTURAL JUSTIFICATION (tamper-evident ledger)</div>'
            f'<div class="pc-justif">{justif}</div>'
            '</div>'
        )

    # Tags
    tags_html = ""
    if tags:
        tags_html = " ".join(
            f'<span class="pc-tag">{t}</span>' for t in tags
        )

    # Cours + as-of
    asof_html = ""
    if price_asof:
        try:
            from shared.freshness import classify_asof
            sev, age = classify_asof("price", price_asof)
            sev_emoji = {"green": "✓", "amber": "🟠", "rouge": "✗", "unknown": "?"}.get(sev, "?")
            age_str = (
                f"{int(age)}s" if age < 60 else
                f"{int(age/60)}min" if age < 3600 else
                f"{int(age/3600)}h" if age < 86400 else
                f"{int(age/86400)}j"
            )
            asof_html = f' <span class="pc-asof">{sev_emoji} as-of {age_str}</span>'
        except Exception:
            asof_html = ""

    type_chip = f'<span class="pc-typechip {ptype}">{ptype}</span>'
    pnl_cls = "ok" if pnl_eur > 0 else "neg" if pnl_eur < 0 else "neu"
    cours_str = f"{current_price:.2f}" if current_price else "?"

    return (
        f'<div class="pc-card" id="card-{slug}">'
        # Bandeau fail-closed (en tete prioritaire si declenche)
        + bandeau_html
        # #128 banner proxy price discret (e.g. SK Hynix GDR EUR via cote KRW)
        + proxy_banner_html
        # Header avec verdict badge + drift conviction
        + '<div class="pc-head">'
        f'<span class="pc-tk mono">{ticker}</span>'
        f'{verdict_v2_html}'
        f'<span class="pc-conv">c{conv} {direction}</span>'
        f'{drift_html}'
        f'{type_chip}'
        f'{tags_html}'
        f'<span class="pc-meta">horizon {horizon} &middot; opened {opened} &middot; reviewed {reviewed}</span>'
        '</div>'
        # Sector profile : adoption substrat (cf #116)
        + sector_profile_html
        # Row 1 : Position + Asymetrie + Factor
        + '<div class="pc-row3">'
        '<div class="pc-cell"><div class="pc-cell-h">POSITION</div>'
        # qty : 3 decimales max (avant : 15 décimales du float synthetic)
        + f'<div class="pc-line"><span>qty</span><span class="mono">{qty:.3f}</span></div>'
        + f'<div class="pc-line"><span>MV</span><span class="mono">{weight_eur:,.0f}€ <span style="opacity:0.65">({weight_pct:.1f}% du book)</span></span></div>'
        + f'<div class="pc-line"><span>P&amp;L</span><span class="mono {pnl_cls}">{pnl_eur:+,.0f}€ ({pnl_pct:+.1f}%)</span></div>'
        # cours : format espaces de milliers pour KRW/JPY (lisible)
        + f'<div class="pc-line"><span>cours</span><span class="mono">{(f"{current_price:,.0f}".replace(",", " ") if current_price and current_price >= 1000 else cours_str)} {ccy}{asof_html}</span></div>'
        + '</div>'
        '<div class="pc-cell"><div class="pc-cell-h">ASYMETRIE</div>'
        f'{asym_html}'
        # entry/partial/full/stop : format espaces de milliers pour devise native lisible
        + f'<div class="pc-line"><span>entry</span><span class="mono">{(f"{entry:,.0f}".replace(",", " ") if entry and entry >= 1000 else (f"{entry:.2f}" if entry else "?"))}</span></div>'
        + f'<div class="pc-line"><span>partial</span><span class="mono">{(f"{partial:,.0f}".replace(",", " ") if partial and partial >= 1000 else (f"{partial:.2f}" if partial else "?"))}</span></div>'
        + f'<div class="pc-line"><span>full</span><span class="mono">{(f"{full:,.0f}".replace(",", " ") if full and full >= 1000 else (f"{full:.2f}" if full else "?"))}</span></div>'
        + f'<div class="pc-line"><span>stop</span><span class="mono">{(f"{stop:,.0f}".replace(",", " ") if stop and stop >= 1000 else (f"{stop:.2f}" if stop else "&empty; (structural)"))}</span></div>'
        + '</div>'
        '<div class="pc-cell"><div class="pc-cell-h">TYPE &amp; FACTOR</div>'
        f'<div class="pc-line"><span>type</span><span>{ptype}</span></div>'
        f'<div class="pc-line"><span>conv</span><span class="mono">c{conv}</span></div>'
        '<div class="pc-line"><span>tags</span><span style="font-size:11px">'
        + (", ".join(tags) if tags else "&mdash;") + '</span></div>'
        '</div>'
        '</div>'
        + slider_html
        + verdict_html
        + what_changed_html
        + inv_html
        + discipline_html
        + counter_html
        + justif_html
        + sizing_3way_html
        + steer_html
        + '</div>'
    )


def _position_card_panel() -> str:
    """Section data-page='position-card' : stack toutes les cards actives.

    Etape 5 (refactor) : assemble CardInputs + SteerOutput par these via
    helpers canoniques. Aucune re-query dans les cards individuelles.
    """
    from intelligence.card_inputs import assemble_card_inputs
    from intelligence.card_steer import derive_card_steer
    from shared import storage as _stg

    try:
        with _stg.db() as cx:
            thesis_ids = [r[0] for r in cx.execute(
                "SELECT id FROM theses WHERE status='active' "
                "ORDER BY conviction DESC, ticker",
            ).fetchall()]
    except Exception as e:
        return (
            '<section data-page="position-card" role="region" aria-label="Position cards">'
            f'<div class="phead"><h2>Position cards</h2></div>'
            f'<div class="pc-error">Indisponible : {type(e).__name__}: {e}</div>'
            '</section>'
        )

    cards = []
    n_review = 0
    n_exit = 0
    n_trim = 0
    n_hold = 0
    for tid in thesis_ids:
        inputs = assemble_card_inputs(tid)
        if inputs is None:
            continue
        steer_v2 = derive_card_steer(inputs)
        if steer_v2.verdict.value == "REVIEW":
            n_review += 1
        elif steer_v2.verdict.value == "EXIT":
            n_exit += 1
        elif steer_v2.verdict.value == "TRIM_TO_X":
            n_trim += 1
        else:
            n_hold += 1
        cards.append(_position_card(inputs, steer_v2))

    n = len(cards)
    # Resume verdicts en tete (steer global aiguilleur)
    summary_html = (
        '<div class="pc-summary" style="display:flex;gap:14px;padding:10px 0;'
        'font-size:12px;border-bottom:1px solid var(--line,#3a3a3a);'
        'margin-bottom:16px;">'
        f'<span><b>{n_hold}</b> HOLD</span>'
        f'<span><b>{n_trim}</b> TRIM</span>'
        f'<span><b>{n_exit}</b> EXIT</span>'
        f'<span style="color:#888"><b>{n_review}</b> REVIEW (fail-closed L15)</span>'
        '</div>'
    )
    return (
        '<section data-page="position-card" role="region" aria-label="Position cards">'
        '<div class="phead"><h2>Position cards</h2>'
        f'<div class="sub">Vue plein-ecran par position &middot; {n} active &middot; '
        'EXIT &amp; SIZE separes (Catch 2) &middot; deep-link #card-TICKER</div></div>'
        + summary_html
        + "".join(cards)
        + '</section>'
    )


def _stress_tests_panel() -> str:
    """Sprint 13 + Axe 4 QUALITY_BAR — scenarios deterministes appliques sur les
    factor exposures, taggues par gate status (ok/warn/breach) lu depuis le
    journal append-only stress_gate_alerts.
    """
    try:
        from intelligence import factor_exposures as _fe

        results = _fe.run_all_stress_tests()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">stress indispo: {type(e).__name__}</div></div>'

    # Charge gate status par scenario depuis le journal (Axe 4 L17).
    # Source unique : stress_gate_alerts. Si vide -> tag absent (rien fabrique).
    from shared import storage
    gate_by_scenario: dict[str, dict] = {}
    try:
        for row in storage.get_latest_stress_gate_all():
            gate_by_scenario[row["scenario_name"]] = row
    except Exception:
        pass

    n_breach = sum(1 for g in gate_by_scenario.values() if g["status"] == "breach")
    n_warn = sum(1 for g in gate_by_scenario.values() if g["status"] == "warn")

    # Header gate-aware : badge global etat (utilitaires existants pos/danger/warn)
    _bdg = ("display:inline-block;padding:2px 8px;border-radius:4px;"
            "font-weight:600;font-size:11px;margin-left:6px;")
    if n_breach > 0:
        gate_header = (
            f'<span style="{_bdg}background:#7a1f1f;color:#fff;">'
            f'BREACH&nbsp;x{n_breach}</span>'
        )
    elif n_warn > 0:
        gate_header = (
            f'<span style="{_bdg}background:#6e5410;color:#fff;">'
            f'WARN&nbsp;x{n_warn}</span>'
        )
    else:
        gate_header = (
            f'<span style="{_bdg}background:transparent;color:var(--ink-2,#888);'
            'border:1px solid var(--line,#3a3a3a);">gate ok</span>'
        )

    rows = []
    for s in results:
        if "error" in s:
            continue
        scenario = s["scenario"]
        dd_pct = s["total_drawdown_pct"]
        dd_eur = s["total_drawdown_eur"]
        n = s.get("n_positions_affected", 0)
        # Couleur lue depuis le journal (pas re-calculee ici -> source unique L17).
        gate = gate_by_scenario.get(scenario)
        _tag_base = ("display:inline-block;padding:1px 6px;border-radius:3px;"
                     "font-size:10px;margin-left:4px;font-weight:500;")
        if gate and gate["status"] == "breach":
            dcls = "danger"
            gate_tag = (
                f'<span style="{_tag_base}background:#7a1f1f;color:#fff;">breach</span>'
            )
        elif gate and gate["status"] == "warn":
            dcls = "warn"
            gate_tag = (
                f'<span style="{_tag_base}background:#6e5410;color:#fff;">warn</span>'
            )
        else:
            # ok ou gate absent (jamais evalue) : fallback fine couleur draw
            dcls = "pos" if dd_pct > 0 else ("warn" if dd_pct < -10 else "neu")
            if gate:
                gate_tag = (
                    f'<span style="{_tag_base}background:transparent;'
                    'color:var(--ink-3,#666);border:1px solid var(--line,#3a3a3a);">ok</span>'
                )
            else:
                gate_tag = ""
        rows.append(
            f'<div class="st-row">'
            f'<div class="st-name">{scenario} {gate_tag}</div>'
            f'<div class="st-impact"><span class="st-pct {dcls} mono">{dd_pct:+.1f}%</span>'
            f'<span class="st-eur mono">{dd_eur:+,.0f}€</span>'
            f'<span class="st-n">n={n}</span></div></div>'
        )
    return (
        '<div class="colhead"><span class="t">Si tel pari rate</span>'
        f'<span class="a">drawdown estime par scenario macro · gate Axe 4 {gate_header}</span></div>'
        '<div class="card pad stresscard" style="margin-bottom:var(--s4)">'
        + "".join(rows)
        + "</div>"
    )


def _user_strategy_panel() -> str:
    """Sprint 19 — affiche la strategie utilisateur declaree (targets custom)."""
    try:
        from pathlib import Path

        import yaml

        cfg = yaml.safe_load(Path("config.yaml").read_text())
        us = cfg.get("user_strategy") or {}
    except Exception:
        us = {}
    if not us:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "No declared user strategy. Defaults from config.yaml in use."
            "</div></div>"
        )
    desc = us.get("description", "")
    cap = us.get("target_cluster_cap_pct", 35)
    dec = us.get("target_decorrelation_pct", 15)
    bench = us.get("benchmark_ticker", "?")
    horizon = us.get("thesis_horizon_years", "?")
    accepted = us.get("accepted_concentrated_factors") or []
    tol_validated = bool(us.get("drawdown_tolerance_validated"))
    tol_validated_at = us.get("drawdown_tolerance_validated_at") or "?"
    accepted_html = ", ".join(accepted) if accepted else "(none)"
    # Phase construction : badge en tete pour cadrer la lecture du reste.
    # Tant que le book n'a pas atteint sa target (~70k€/~33 pos), les
    # metriques de concentration sont en convergence, pas en derive.
    construction_html = ""
    if us.get("construction_phase"):
        try:
            from intelligence.portfolio_grade import _fetch_state

            cur_eur = (_fetch_state() or {}).get("total_capital_eur") or 0
            cur_pos = len((_fetch_state() or {}).get("positions") or [])
        except Exception:
            cur_eur = 0
            cur_pos = 0
        tgt_eur = us.get("target_capital_eur") or 0
        tgt_pos = us.get("target_positions_count") or 0
        progress = (cur_eur / tgt_eur * 100) if tgt_eur else 0
        construction_html = (
            '<div class="us-construction">'
            '<div class="us-cstr-h">Construction phase</div>'
            f'<div class="us-cstr-b">Book is under construction: '
            f'<b class="mono">{cur_eur:,.0f}&nbsp;€</b> / '
            f'<b class="mono">{tgt_eur:,.0f}&nbsp;€</b> target '
            f'(<b>{progress:.0f}%</b> &middot; {cur_pos}/{tgt_pos} positions). '
            "Decorrelators (Energy-for-AI, Defense, Robotics) are being added. "
            "Current concentration ratios (cluster cap, strict ballast, AI capex expo) "
            "<b>will naturally converge</b> toward target. Informational only, "
            "not actionable: do not push trims until construction is complete."
            '</div>'
            '</div>'
        )
    # CTA "a valider" : lit le drawdown estime sur scenario AI capex -30%
    # depuis risk_watch.json. Tant que pas valide explicitement, la target
    # 75% n'a pas ete confirmee par un gut-check sur le chiffre reel.
    cta_html = ""
    if not tol_validated:
        try:
            from intelligence.portfolio_grade import _fetch_state
            from shared.risk_watch import load_risk_watch

            rw = load_risk_watch() or {}
            r0 = (rw.get("risks") or [{}])[0]
            de = r0.get("drawdown_estimates") or {}
            dd_mild = de.get("mild_derating_minus30")
            total_eur = (_fetch_state() or {}).get("total_capital_eur") or 0
            dd_eur = int(total_eur * (dd_mild or 0) / 100) if dd_mild else 0
        except Exception:
            dd_mild = None
            dd_eur = 0
        if dd_mild is not None:
            cta_html = (
                '<div class="us-cta">'
                '<div class="us-cta-h">A valider : ta tolerance drawdown</div>'
                f'<div class="us-cta-b">Ta target cluster {cap}% implique '
                f'<b class="neg mono">{dd_mild}%</b> sur scenario AI capex de-rating '
                f'-30% (~<b class="neg mono">{dd_eur:+,}&nbsp;€</b>). '
                "Si voir le book a ce level touche ta limite, baisse la target : la "
                "la note globale ne vaut que ce que vaut cette tolerance."
                '</div>'
                '<div class="us-cta-f">Pour valider : '
                '<code>config.yaml.user_strategy.drawdown_tolerance_validated: true</code>'
                '</div>'
                '</div>'
            )
    else:
        cta_html = (
            f'<div class="us-cta valid"><div class="us-cta-h">'
            f'Tolerance drawdown validee le {tol_validated_at[:10]}</div></div>'
        )
    return (
        '<div class="colhead"><span class="t">Your declared strategy</span></div>'
        '<div class="card pad strategiecard" style="margin-bottom:var(--s4)">'
        f'{construction_html}'
        '<div class="us-grid">'
        f'<div class="us-row"><span class="us-k">Main bet target</span><span class="us-v mono">{cap}%</span></div>'
        f'<div class="us-row"><span class="us-k">Other bets target</span><span class="us-v mono">{dec}%</span></div>'
        f'<div class="us-row"><span class="us-k">Benchmark</span><span class="us-v mono">{bench}</span></div>'
        f'<div class="us-row"><span class="us-k">Theses horizon</span><span class="us-v mono">{horizon} ans</span></div>'
        f'<div class="us-row"><span class="us-k">Accepted concentrations</span><span class="us-v">{accepted_html}</span></div>'
        '</div>'
        f'{cta_html}'
        f'<div class="us-desc">{desc}</div>'
        '</div>'
    )


def _trajectory_panel() -> str:
    """Sprint 13 — drift du grade et de chaque dim sur les 30 derniers jours."""
    try:
        from intelligence import factor_exposures as _fe

        t = _fe.format_grade_trajectory(n_days=30)
    except Exception as e:
        return f'<div class="card pad"><div class="empty">trajectory indispo: {type(e).__name__}</div></div>'
    snaps = t.get("snapshots") or []
    drift = t.get("drift") or {}
    if len(snaps) < 2:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            f"Trajectory : {len(snaps)} snapshot(s) — il en faut >=2 pour mesurer la derive. "
            "Les snapshots quotidiens s'accumulent via le cron 23h15."
            "</div></div>"
        )
    score_drift = drift.get("score") or {}
    delta_score = score_drift.get("delta", 0)
    arrow = "↑" if delta_score > 0 else ("↓" if delta_score < 0 else "·")
    cls = "pos" if delta_score > 0 else ("neg" if delta_score < 0 else "neu")
    # Use canonical glossary labels
    canon_labels = {
        "quality_T1_plus": "High solidity",
        "T2_redondant": "Overlaps",
        "decorrelation_star": "Other bets",
        "sizing_conviction": "Calibration",
        "cluster_cap": "Bet principal",
        "thesis_health": "Health",
    }
    rows = []
    for dk in ("quality_T1_plus", "T2_redondant", "decorrelation_star",
               "sizing_conviction", "cluster_cap", "thesis_health"):
        d = drift.get(dk) or {}
        delta = d.get("delta", 0)
        dcls = "pos" if delta > 0 else ("neg" if delta < 0 else "neu")
        dirsym = "↑" if delta > 0 else ("↓" if delta < 0 else "·")
        rows.append(
            f'<div class="tr-row">'
            f'<span class="tr-key">{canon_labels.get(dk, dk)}</span>'
            f'<span class="tr-from mono">{d.get("first", "?")}%</span>'
            f'<span class="tr-arr">→</span>'
            f'<span class="tr-to mono">{d.get("last", "?")}%</span>'
            f'<span class="tr-delta {dcls} mono">{dirsym} {delta:+.1f}</span></div>'
        )
    return (
        '<div class="colhead"><span class="t">Grade drift (30d)</span>'
        f'<span class="a">{len(snaps)} photos &middot; '
        f'{score_drift.get("first_date","?")} → {score_drift.get("last_date","?")}</span></div>'
        '<div class="card pad trajcard" style="margin-bottom:var(--s4)">'
        f'<div class="tr-hero">Score : {score_drift.get("first", "?")} '
        f'<span class="tr-arr">→</span> '
        f'{score_drift.get("last", "?")} '
        f'<span class="tr-delta {cls} mono">{arrow} {delta_score:+d}</span></div>'
        + "".join(rows)
        + "</div>"
    )


def _ticker_axes_panel() -> str:
    """Sprint 12 — Tagging per ticker (driver/stage/moat/macro_factor) pour
    redefinir REDONDANCE et DECORRELATION proprement. Cf. critique review.
    """
    try:
        from shared import storage as _stg

        rows = _stg.get_all_latest_ticker_axes()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">axes indispo: {type(e).__name__}</div></div>'
    if not rows:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "Axes tagging (driver/stage/moat/macro) pending. Tech sheets will appear here once classified."
            "</div></div>"
        )
    # Group by macro_factor (dominant macro view)
    by_macro: dict = {}
    for r in rows:
        by_macro.setdefault(r.get("macro_factor", "Other"), []).append(r)
    # Sort macros by count desc
    macros = sorted(by_macro.items(), key=lambda kv: -len(kv[1]))
    groups_html = []
    for macro, members in macros:
        lis = []
        for r in members:
            tk = r["ticker"]
            driver = (r.get("demand_driver") or "")[:70]
            stage = (r.get("value_chain_stage") or "")[:70]
            moat = (r.get("moat_source") or "")[:70]
            lis.append(
                f'<div class="ax-row">'
                f'<div class="ax-tk">{tk}</div>'
                f'<div class="ax-fields">'
                f'<div class="ax-f"><span class="ax-l">driver</span> {driver}</div>'
                f'<div class="ax-f"><span class="ax-l">stage</span> {stage}</div>'
                f'<div class="ax-f"><span class="ax-l">moat</span> {moat}</div>'
                f'</div></div>'
            )
        groups_html.append(
            f'<div class="ax-group"><div class="ax-h">'
            f'<span class="ax-macro">{macro}</span>'
            f'<span class="ax-n">n={len(members)}</span></div>'
            + "".join(lis) + "</div>"
        )
    return (
        '<div class="colhead"><span class="t">Fiches techniques par ticker</span>'
        '<span class="a">demand engine &middot; value chain layer &middot; moat nature &middot; macro factor</span></div>'
        '<div class="card pad axescard" style="margin-bottom:var(--s4)">'
        + "".join(groups_html)
        + "</div>"
    )


def _preferences_panel() -> str:
    """Layer 3 — ce qui MARCHE deterministically pour CE user.

    Pas d'opinion modele, juste les chiffres bruts groups par kind. La
    confidence est derivee du sample size (Wilson-conservative). No
    note magique : tout est expose avec n explicit.
    """
    try:
        import json as _json

        from shared import storage as _stg

        prefs = _stg.get_latest_preferences()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">preferences indispo: {type(e).__name__}</div></div>'
    if not prefs:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "Monthly calibration scheduled 1st of month. Preferences (what worked for you) will appear here once decisions accumulate."
            "</div></div>"
        )
    groups: list[str] = []
    for p in prefs:
        kind = p.get("kind", "?")
        n = p.get("n_samples") or 0
        conf = p.get("confidence") or 0
        date = (p.get("snapshot_date") or "")[:10]
        try:
            metric = _json.loads(p.get("metric_json") or "{}")
        except Exception:
            metric = {}
        rows = []
        if kind == "conviction_calibration":
            for c, v in (metric.get("buckets") or {}).items():
                rows.append(_pref_row(c, v["n"], v["mean_return_30d_pct"], v["winrate_pct"]))
        elif kind == "sector_outcome":
            for sec, v in (metric.get("clusters") or {}).items():
                rows.append(_pref_row(sec[:18], v["n"], v["mean_return_30d_pct"], v["winrate_pct"]))
        elif kind == "bias_outcome":
            for b, v in (metric.get("biases") or {}).items():
                rows.append(_pref_row(b[:18], v["n"], v["mean_return_30d_pct"], v["winrate_pct"]))
        elif kind == "sizing_outcome":
            for s, v in (metric.get("sizing") or {}).items():
                rows.append(_pref_row(s, v["n"], v["mean_return_30d_pct"], v["winrate_pct"]))
        elif kind == "copilot_outcome":
            for ver, v in (metric.get("verdicts") or {}).items():
                rows.append(_pref_row(ver, v["n"], v["mean_return_30d_pct"], v.get("outcome_good_pct", 0)))
        elif kind == "archetype_consistency":
            for t in (metric.get("timeline") or [])[:6]:
                rows.append(
                    f'<div class="pr-row"><span class="pr-key">{t.get("at","?")}</span>'
                    f'<span class="pr-mid">{t.get("label","?")}</span>'
                    f'<span class="pr-num mono">{t.get("score","?")}</span></div>'
                )
        else:
            rows.append('<div class="pr-row"><span class="pr-key">no formatter</span></div>')
        rows_html = "".join(rows) or '<div class="empty" style="padding:var(--s2) 0">none sample</div>'
        groups.append(
            f'<div class="pr-group"><div class="pr-h">'
            f'<span class="pr-kind">{kind.replace("_"," ")}</span>'
            f'<span class="pr-meta">n={n} conf={conf} ({date})</span></div>'
            f'{rows_html}</div>'
        )
    return (
        '<div class="colhead"><span class="t">What worked for you</span>'
        '<span class="a">samples + winrate on your real resolved decisions &middot; no model opinion</span></div>'
        '<div class="card pad preferencescard" style="margin-bottom:var(--s4)">'
        f'<div class="pr-grid">{"".join(groups)}</div>'
        '</div>'
    )


def _pref_row(key: str, n: int, mean_ret: float, win: float) -> str:
    rcls = "pos" if mean_ret > 0 else ("neg" if mean_ret < 0 else "neu")
    return (
        f'<div class="pr-row"><span class="pr-key">{key}</span>'
        f'<span class="pr-mid">n={n}</span>'
        f'<span class="pr-num mono {rcls}">{mean_ret:+.1f}%</span>'
        f'<span class="pr-win mono">win {win:.0f}%</span></div>'
    )


def _conceptions_panel() -> str:
    """Layer 2 — vue stable du bot per ticker. Synthese hebdo (cron Sun 19h)."""
    try:
        from shared import storage as _stg

        concs = _stg.get_all_current_conceptions()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">conceptions indispo: {type(e).__name__}</div></div>'
    if not concs:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "Weekly summary scheduled Sunday 19:00. Once generated, bot's stable per-ticker views will appear here."
            "</div></div>"
        )
    rows = []
    for c in concs[:40]:
        kind = c.get("kind", "?")
        target = c.get("target_key", "?")
        conv = c.get("conviction", 0) or 0
        val = c.get("valence")
        val_s = f"{val:+.2f}" if isinstance(val, int | float) else "·"
        vcls = "neg" if (isinstance(val, int | float) and val < -0.1) else (
            "pos" if (isinstance(val, int | float) and val > 0.1) else "neu"
        )
        text = (c.get("conception_text") or "").strip()
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # 1200+ chars = summarize via LLM upstream a posteriori. Aujourd'hui
        # max obs = 791, donc accordeon suffit. Cap hard a 1500 par securite.
        if len(text) > 1500:
            text = text[:1497] + "..."
        n = c.get("n_signals_used") or 0
        ccls = "high" if conv >= 60 else ("mid" if conv >= 35 else "low")
        rows.append(
            f'<div class="bc-row">'
            f'<div class="bc-head"><span class="bc-target">{target}</span>'
            f'<span class="bc-kind">{kind}</span>'
            f'<span class="bc-conv {ccls}">conv {conv}</span>'
            f'<span class="bc-val {vcls}">{val_s}</span>'
            f'<span class="bc-n">n={n}</span></div>'
            f'<div class="bc-text">{text}</div></div>'
        )
    return (
        '<div class="colhead"><span class="t">Ce que le bot pense par ticker</span>'
        '<span class="a">stable per-ticker summary updated weekly '
        '&middot; survole ou clique pour expand</span></div>'
        '<div class="card pad conceptionscard" style="margin-bottom:var(--s4)">'
        + "".join(rows)
        + "<script>document.querySelectorAll('.conceptionscard .bc-row').forEach(function(e){"
        "e.addEventListener('click',function(){e.classList.toggle('open')})});</script>"
        + "</div>"
    )


def _chat_signals_panel() -> str:
    """Sprint 9.d — soft signals extracted passively from chat conversations.

    Mine ce que l'user laisse echapper en conversation lambda (concerns,
    conviction shifts, sector views, blind spots). Boucle complete : recolte
    → analyse passive → digestion (alimente user_profile) → precision.
    """
    try:
        from shared import storage as _stg

        rows = _stg.get_recent_chat_signals(limit=20)
    except Exception as e:
        return f'<div class="card pad"><div class="empty">soft signals indispo: {type(e).__name__}</div></div>'
    if not rows:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "No soft signals extracted yet. Continue de discuter dans le "
            "chat — every casual conversation becomes an info goldmine for the profile."
            "</div></div>"
        )
    by_kind: dict = {}
    for r in rows:
        by_kind.setdefault(r.get("kind", "?"), []).append(r)
    # Order kinds : negatives first (concerns), then drifts, then positives, then views
    order = [
        "concern", "conviction_drift", "blind_spot",
        "sector_view", "thematic_view", "topic_interest", "heuristic",
        "sentiment", "conviction_endorse",
    ]
    groups_html = []
    for kind in [k for k in order if k in by_kind] + [k for k in by_kind if k not in order]:
        items = by_kind[kind][:6]
        lis = []
        for s in items:
            val = s.get("valence")
            val_s = f"{val:+.2f}" if isinstance(val, int | float) else "·"
            vcls = "neg" if (isinstance(val, int | float) and val < -0.1) else (
                "pos" if (isinstance(val, int | float) and val > 0.1) else "neu"
            )
            target = s.get("ticker") or s.get("sector") or s.get("theme") or "-"
            quote = (s.get("evidence_quote") or "").strip()
            if len(quote) > 200:
                quote = quote[:197] + "..."
            quote = quote.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            note = (s.get("note") or "").strip()[:160]
            note = note.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lis.append(
                f'<div class="cs-row">'
                f'<div class="cs-meta"><span class="cs-target">{target}</span>'
                f'<span class="cs-val {vcls}">{val_s}</span></div>'
                f'<div class="cs-quote">&ldquo;{quote}&rdquo;</div>'
                f'<div class="cs-note">{note}</div></div>'
            )
        groups_html.append(
            f'<div class="cs-group"><div class="cs-kind">{kind.replace("_", " ")}</div>'
            + "".join(lis) + "</div>"
        )
    return (
        '<div class="colhead"><span class="t">What you let slip in conversation</span>'
        '<span class="a">concerns / doubts / views the bot captures each message &middot; feeds your profile</span></div>'
        '<div class="card pad chatsigcard" style="margin-bottom:var(--s4)">'
        f'<div class="cs-grid">{"".join(groups_html)}</div>'
        '</div>'
    )


def _conversations_panel() -> str:
    """Sprint 9 — surface les conversations recentes (boucle recolte/digestion).

    Liste les 12 derniers messages chronologiquement (newest first), surface
    differenciee (dashboard / Telegram), role differencie (user / assistant).
    """
    try:
        from shared import storage as _stg

        rows = _stg.get_recent_chat_messages(limit=12)
    except Exception as e:
        return f'<div class="card pad"><div class="empty">conversations indispo: {type(e).__name__}</div></div>'
    if not rows:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "None conversation enregistree pour le moment. Les echanges chat "
            "(dashboard + Telegram) seront consignes ici et integres au profil utilisateur."
            "</div></div>"
        )
    lis = []
    for r in rows:
        role = r.get("role", "?")
        surface = r.get("surface", "?")
        date = (r.get("created_at") or "")[:16]
        content = (r.get("content") or "").strip()
        if len(content) > 240:
            content = content[:237] + "..."
        # Escape HTML rough
        content = (
            content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        rcls = "user" if role == "user" else "assistant"
        scls = "tg" if surface == "telegram" else "dash"
        lis.append(
            f'<div class="cv-row cv-{rcls}">'
            f'<div class="cv-meta"><span class="cv-role {rcls}">{role}</span>'
            f'<span class="cv-surf {scls}">{surface}</span>'
            f'<span class="cv-date">{date}</span></div>'
            f'<div class="cv-content">{content}</div></div>'
        )
    return (
        '<div class="colhead"><span class="t">Historique chat</span>'
        '<span class="a">all logged and re-integrated into profile over time</span></div>'
        '<div class="card pad conversationscard" style="margin-bottom:var(--s4)">'
        + "".join(lis)
        + "</div>"
    )


def _narrative_panel() -> str:
    """Sprint 6 surface : narrative clusters LLM + edges + redundant."""
    try:
        import json as _json

        from shared import storage as _stg

        raw = _stg.get_latest_narrative_snapshot()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">narrative indisponible: {type(e).__name__}: {e}</div></div>'
    if not raw:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "Weekly narrative synthesis scheduled Sunday 20:30. Narrative clusters will appear here once generated."
            "</div></div>"
        )
    clusters = _json.loads(raw.get("clusters_json") or "[]")
    edges_blob = _json.loads(raw.get("edges_json") or "{}")
    edges = edges_blob.get("edge_positions") or []
    redundant = edges_blob.get("redundant_positions") or []

    cluster_rows = []
    for cl in clusters:
        name = cl.get("name", "?")
        tks = cl.get("tickers") or []
        overlap = cl.get("narrative_overlap_score") or 0
        shared = (cl.get("shared_drivers") or "")[:200]
        ocls = "high" if overlap >= 70 else ("mid" if overlap >= 40 else "low")
        cluster_rows.append(
            f'<div class="nv-cluster"><div class="nv-cl-head">'
            f'<span class="nv-cl-name">{name}</span>'
            f'<span class="nv-cl-overlap {ocls}">overlap {overlap}</span>'
            f'<span class="nv-cl-n">n={len(tks)}</span></div>'
            f'<div class="nv-cl-tks">{", ".join(tks[:10])}</div>'
            f'<div class="nv-cl-driv">{shared}</div></div>'
        )

    edges_rows = "".join(
        f'<div class="nv-line"><span class="nv-tk">{e.get("ticker","?")}</span>'
        f'<span class="nv-why">{(e.get("reason") or "")[:200]}</span></div>'
        for e in edges
    ) or '<div class="empty" style="padding:var(--s25) 0">none edge identifie</div>'

    red_rows = "".join(
        f'<div class="nv-line"><span class="nv-tk">{r.get("ticker","?")}</span>'
        f'<span class="nv-with">redondant avec {r.get("redundant_with","?")}</span>'
        f'<span class="nv-why">{(r.get("reason") or "")[:160]}</span></div>'
        for r in redundant
    ) or '<div class="empty" style="padding:var(--s25) 0">none redondance</div>'

    return (
        '<div class="colhead"><span class="t">Clusters narratifs (LLM)</span>'
        f'<span class="a">{raw.get("snapshot_date","?")} &middot; consume par T2 + decorrelation du grade</span></div>'
        '<div class="card pad narrativecard" style="margin-bottom:var(--s4)">'
        f'<div class="nv-grid">{"".join(cluster_rows)}</div>'
        '<div class="nv-split">'
        '<div class="nv-col"><div class="nv-h">Edge positions (independantes)</div>'
        f'{edges_rows}</div>'
        '<div class="nv-col"><div class="nv-h">Redondances detectees</div>'
        f'{red_rows}</div>'
        '</div></div>'
    )


def _chat_memory_stats() -> tuple[int, int, str]:
    """Returns (n_messages, n_sessions, oldest_date) for chat memory depth."""
    try:
        from shared.storage import db

        with db() as cx:
            n_msg = cx.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
            n_sess = cx.execute("SELECT COUNT(DISTINCT session_id) FROM chat_messages").fetchone()[0]
            oldest = cx.execute("SELECT MIN(created_at) FROM chat_messages").fetchone()[0]
        return n_msg, n_sess, (oldest or "")[:10]
    except Exception:
        return 0, 0, ""


def _distribution_health_panel() -> str:
    """W13 sante distribution : surface des 6 vigilances v2_vigilance.run_all_vigilances()
    en panneau ROUGE/ORANGE/VERT data. Couvre watch_rate, directional_spread,
    insider_clusters_alive, horizon_diversification, conviction_distribution,
    fx_freshness. Cron weekly Mon 7h alimente Telegram pour ALERT/WARN ;
    dashboard reflechit live."""
    try:
        from intelligence import v2_vigilance as _v

        results = _v.run_all_vigilances()
    except Exception as e:
        return f'<div class="card pad" style="margin-bottom:var(--s4)">{_err(e)}</div>'

    status_tag = {
        "OK": "acc", "INFO": "calm", "INSUFFICIENT_DATA": "calm",
        "WARN": "warn", "ALERT": "bear",
    }
    label_map = {
        "watch_rate": "Watch-rate distribution",
        "directional_spread": "Spread probas",
        "insider_clusters_alive": "Pipeline insider clusters",
        "horizon_diversification": "Horizon diversification",
        "conviction_distribution": "Conviction spread",
        "fx_freshness": "FX live (max-age 24h)",
    }
    rows = ""
    for r in results:
        cls = status_tag.get(str(r.get("status") or ""), "calm")
        name = label_map.get(str(r.get("name") or ""), r.get("name", "?"))
        status = r.get("status", "?")
        msg = (r.get("message") or "").replace("<", "&lt;").replace(">", "&gt;")
        rows += (
            f'<div class="row" title="{msg}">'
            f'<div class="rt"><span style="font-weight:600">{name}</span>'
            f'<span class="tag {cls}">{status}</span></div>'
            f'<div class="rs"><span style="color:var(--steel);font-size:15px">{msg[:120]}</span></div>'
            f'</div>'
        )
    return (
        '<div class="colhead"><span class="t">Distribution health</span>'
        '<span class="a">extension scaffold ROUGE/ORANGE/VERT ops &mdash; data &middot; cron weekly Mon 7h push Telegram si !OK</span></div>'
        '<div class="card pad" style="margin-bottom:var(--s4)">'
        + rows
        + '</div>'
    )


def _track_record_panel() -> str:
    """E4 wave 7 : Track record en tete de Vue d'ensemble (user feedback 31/05).

    Etat honnete-tot : si N substantiels (non-neutral, non-v0) < 10, on AVOUE
    explicitement "INSUFFISANT pour conclure" plutot que d'afficher un chiffre
    qui pretend tenir. Se remplit auto post-batch 10/06 (40 nouvelles
    resolutions v1 attendues).

    Tokens : --t-h3 pour titres, --t-body pour valeurs principales, --t-caption
    pour secondaires. Couleurs : --acc si OK, --warn si insufficient, --bear
    si breach. Charte §1.4 + §4 (etats honnetes) + §3.5 (tags semantiques)."""
    try:
        import sqlite3 as _sql

        from statsmodels.stats.proportion import proportion_confint

        from shared import storage as _stg

        cx = _sql.connect(_q.__globals__["DB_PATH"]) if "DB_PATH" in _q.__globals__ else _sql.connect("data/bot.db")
        rows = cx.execute(
            "SELECT outcome, brier_score FROM predictions "
            "WHERE resolved_at IS NOT NULL AND outcome IN ('correct','incorrect') "
            f"AND {_stg.canonical_predictions_filter()}"
        ).fetchall()
        open_n = cx.execute(
            "SELECT COUNT(*) FROM predictions WHERE resolved_at IS NULL "
            f"AND {_stg.canonical_predictions_filter()}"
        ).fetchone()[0]
        v0_n = cx.execute(
            "SELECT COUNT(*) FROM predictions WHERE methodology_version = 'v0'"
        ).fetchone()[0]
        # ADR 014 § Archive-report rule : on surface explicitement le compte
        # V1 archive pour eviter la lecture "0 en attente" trompeuse quand
        # 155 v1 sont en realite open mais hors headline canonique.
        v1_resolved_n = cx.execute(
            "SELECT COUNT(*) FROM predictions WHERE methodology_version = 'v1' "
            "AND resolved_at IS NOT NULL"
        ).fetchone()[0]
        v1_open_n = cx.execute(
            "SELECT COUNT(*) FROM predictions WHERE methodology_version = 'v1' "
            "AND resolved_at IS NULL"
        ).fetchone()[0]
        cx.close()
    except Exception as e:
        return f'<div class="card pad" style="margin-bottom:var(--s4)">{_err(e)}</div>'

    n = len(rows)
    n_corr = sum(1 for r in rows if r[0] == "correct")
    briers = [r[1] for r in rows if r[1] is not None]
    n_brier = len(briers)
    brier_mean = sum(briers) / n_brier if briers else None

    MIN_CONCLUSIF = 10
    # Panel honnete-tot : disparait une fois la target atteinte (user feedback
    # 31/05 wave 7bis). Sa raison d'etre = combler l'absence de verdict. Quand
    # N>=10 sur les 2 metriques, le vrai chiffre vit ailleurs (KPI #2 +
    # calibration_audit). Le pipeline (batch 10/06) seul ne justifie pas le
    # panneau -- il sera affiche en footer normal de la page une fois activee.
    if n >= MIN_CONCLUSIF and n_brier >= MIN_CONCLUSIF:
        return ""
    _rate_str = f"{n_corr}/{n} ({n_corr/n:.0%})" if n else "—"
    if n >= 2:
        lo, hi = proportion_confint(n_corr, n, alpha=0.05, method="wilson")
        ci_str = f"IC95% [{lo:.0%}, {hi:.0%}]"
    else:
        ci_str = "IC indisponible"
    if n == 0:
        # ADR 014 : si canonical = 0, c'est parce que v2 n'a pas encore tire.
        # On dit "pas encore demarre" explicitement, jamais silent zero.
        _rate_cls, rate_verdict = "warn", (
            "V2 pas encore d&eacute;marr&eacute; &mdash; v1 archive cl&ocirc;ture au batch 10/06"
        )
    elif n < MIN_CONCLUSIF:
        _rate_cls, rate_verdict = "warn", f"INSUFFISANT &mdash; N&lt;{MIN_CONCLUSIF} pour conclure"
    elif n_corr / n >= 0.55:
        _rate_cls, rate_verdict = "acc", "verdict provisoire favorable"
    else:
        _rate_cls, rate_verdict = "bear", "verdict provisoire defavorable"

    brier_str = f"{brier_mean:.3f}" if brier_mean is not None else "—"
    if n_brier < MIN_CONCLUSIF or brier_mean is None:
        _brier_cls, brier_verdict = "warn", f"INSUFFISANT &mdash; N={n_brier}&lt;{MIN_CONCLUSIF}"
    elif brier_mean < 0.20:
        _brier_cls, brier_verdict = "acc", "sous la target 0.20"
    elif brier_mean < 0.25:
        _brier_cls, brier_verdict = "warn", "approche le seuil"
    else:
        _brier_cls, brier_verdict = "bear", "au-dessus du seuil"

    # Axe taux correct : 0% -> 100%, marker = position actuelle
    rate_frac = (n_corr / n * 100) if n else 0.0
    # Axe Brier : 0 -> 0.5, marker = brier_mean, ligne ref a target 0.20 (= 40%)
    brier_frac = (brier_mean / 0.5 * 100) if brier_mean is not None else None
    brier_target_x = 40.0  # 0.20 / 0.5
    # P2 canon : tick a 0.20 target (40%) + dot pour Brier mean. Pas de gradient.
    rate_pct = f"{n_corr/n:.0%}" if n else "&mdash;"

    return (
        f'<div class="colhead"><span class="t">Track record</span>'
        f'<span class="a">N={n} substantial &middot; honest-early disclosure if N&lt;{MIN_CONCLUSIF}</span></div>'
        f'<div class="card pad tr-card" style="margin-bottom:var(--s4)">'
        # Metric 1 : Taux correct (axe 0->100%)
        f'<div class="tr-metric">'
        f'<div class="tr-mlabel"><span class="tr-mname">Taux correct</span>'
        f'<span class="tr-mval mono">{n_corr}<span class="tr-mvsep">/</span>{n}</span>'
        f'<span class="tr-munit">soit {rate_pct}</span></div>'
        f'{_tbar(rate_frac, dot_color=_rate_cls, title=f"{rate_pct} correct")}'
        f'<div class="tr-mfoot"><span class="mono">IC95% {ci_str.replace("IC95% ", "")}</span>'
        f'<span class="tr-verdict">{rate_verdict}</span></div>'
        f'</div>'
        # Metric 2 : Brier rolling (axe 0->0.5, target 0.20)
        f'<div class="tr-metric">'
        f'<div class="tr-mlabel"><span class="tr-mname">Brier rolling</span>'
        f'<span class="tr-mval mono">{brier_str}</span>'
        f'<span class="tr-munit">sur 0&ndash;0,5</span></div>'
        f'{_tbar(brier_frac, ticks=[(brier_target_x, "target 0,20")], dot_color=_brier_cls, title="Brier sur 0-0,5")}'
        f'<div class="tr-mfoot"><span class="mono">target 0,20</span>'
        f'<span class="tr-verdict">{brier_verdict}</span></div>'
        f'</div>'
        # Metric 3 : Curve de fiabilite (cadre vide + diagonale qui se trace)
        f'<div class="tr-metric">'
        f'<div class="tr-mlabel"><span class="tr-mname">Reliability curve</span>'
        f'<span class="tr-munit">attend la first cohorte calibration</span></div>'
        f'<svg class="tr-rsvg" viewBox="0 0 100 60" preserveAspectRatio="none" aria-hidden="true">'
        f'<line x1="0" y1="60" x2="100" y2="0" class="tr-diag"/>'
        f'<line x1="0" y1="60" x2="100" y2="60" class="tr-frame"/>'
        f'<line x1="0" y1="0" x2="0" y2="60" class="tr-frame"/>'
        f'</svg>'
        f'<div class="tr-mfoot"><span class="mono">&mdash; &middot; N insuffisant</span>'
        f'<span class="tr-verdict">trace se construit post 10/06</span></div>'
        f'</div>'
        # Pipeline state -- plat, honnete. ADR 014 : on surface v0 quarantine
        # ET v1 archive separement pour eviter "0 en attente" trompeur.
        f'<div class="tr-pipe mono">'
        f'<span><b>{n}</b> resolved (canonique)</span><span class="tr-sep">&middot;</span>'
        f'<span><b>{open_n}</b> en attente (canonique)</span><span class="tr-sep">&middot;</span>'
        f'<span>+<b>{v1_resolved_n}/{v1_resolved_n + v1_open_n}</b> v1 archive</span>'
        f'<span class="tr-sep">&middot;</span>'
        f'<span>+<b>{v0_n}</b> v0 quarantine</span><span class="tr-sep">&middot;</span>'
        f'<span>prochaine cohorte <b>10/06</b></span>'
        f'</div>'
        f'</div>'
    )


def _copilot() -> str:
    """Page dediee Copilot : chat + pressure tests historique.
    Retraits 02/06 user (panneaux infinis rebarbatifs) :
    _conceptions_panel (redondant avec theses), _conversations_panel
    (redondant avec chat-log), _chat_signals_panel (niche). Code backend
    conserve, donnees disponibles pour reactivation future."""
    return (
        f'<section data-page="copilot" role="region" aria-label="Copilot">'
        f'<div class="phead"><h2>Copilot</h2></div>'
        f'{_chat_panel()}'
        f'<div class="vigie-sh" data-tip="Historical adversarial pressure tests: what the copilot challenged recently."><svg class="sh-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2C5 2 3 4 3 6.5c0 1.5.8 2.8 2 3.6V12c0 .6.4 1 1 1h4c.6 0 1-.4 1-1v-1.9c1.2-.8 2-2.1 2-3.6C13 4 11 2 8 2z"/><path d="M6 13v1c0 .5.4 1 1 1h2c.6 0 1-.5 1-1v-1"/></svg>Pressions adversariales</div>'
        f'{_copilot_panel()}'
        f'</section>'
    )


def _chat_panel() -> str:
    """Sprint 7 — Chat surface : pose une question, contexte assemble cote serveur."""
    return (
        '<div class="colhead"><span class="t">Ask the copilot</span></div>'
        '<div class="card pad chatcard" style="margin-bottom:var(--s4)">'
        '<div id="chat-log" class="chat-log"></div>'
        '<form id="chat-form" class="chat-form" onsubmit="return chatSend(event)">'
        '<textarea id="chat-input" class="chat-input" aria-label="Ask the copilot" placeholder="ex. What is my biggest fragility right now?" rows="2"></textarea>'
        '<button type="submit" class="chat-send" aria-label="Send message">Send</button>'
        '</form>'
        '<div class="chat-foot">Context (profile + grade + positions + interventions) is replayed on each message.</div>'
        '</div>'
        '<script>'
        # Sprint 19 : persist chat-log + textarea draft dans localStorage pour
        # survivre aux reloads page (la page auto-reload tous les ~60s pour
        # fresh data — sans ca, DOM chat-log et textarea se vident).
        'window._chatHistory=window._chatHistory||JSON.parse(localStorage.getItem("presage_chat_log")||"[]");'
        'window._chatSessionId=window._chatSessionId||localStorage.getItem("presage_chat_session")||(()=>{const s="s_"+Date.now().toString(36)+"_"+Math.random().toString(36).slice(2,8);localStorage.setItem("presage_chat_session",s);return s;})();'
        'function chatEsc(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}'
        'function chatPersist(){try{localStorage.setItem("presage_chat_log",JSON.stringify(window._chatHistory.slice(-40)));}catch(e){}}'
        'function chatAppend(role,text){const log=document.getElementById("chat-log");const div=document.createElement("div");div.className="chat-msg chat-"+role;div.innerHTML=chatEsc(text).replace(/\\n/g,"<br>");log.appendChild(div);log.scrollTop=log.scrollHeight;}'
        # Au load : init draft textarea + brancher save-on-input + idle timer.
        # chatRestore() RETIRE A LA SOURCE (user feedback 31/05 wave 14 :
        # "il faut regler ce genre de problemes a la source direct").
        # localStorage = strictement fenetre contexte LLM (histSend slice -10),
        # JAMAIS reaffiche au DOM. Le chat-log se rempli uniquement quand le
        # user envoie un message.
        'function chatInit(){const ta=document.getElementById("chat-input");if(ta){'
        'const draft=localStorage.getItem("presage_chat_draft")||"";if(draft)ta.value=draft;'
        'ta.addEventListener("input",function(){try{localStorage.setItem("presage_chat_draft",ta.value);}catch(e){}resetChatIdleTimer();});}'
        'startChatIdleTimer();}'
        'function clearChatDisplay(){const log=document.getElementById("chat-log");if(!log)return;log.innerHTML="";}'
        'function startChatIdleTimer(){if(window._chatIdleTimer)clearTimeout(window._chatIdleTimer);window._chatIdleTimer=setTimeout(clearChatDisplay,420000);}'
        'function resetChatIdleTimer(){startChatIdleTimer();}'
        '(function(){if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",chatInit);}else{chatInit();}})();'
        'async function chatSend(e){e.preventDefault();const ta=document.getElementById("chat-input");const msg=ta.value.trim();if(!msg)return false;'
        'chatAppend("user",msg);ta.value="";try{localStorage.removeItem("presage_chat_draft");}catch(e){}'
        'const histSend=window._chatHistory.slice(-10);'
        'const btn=document.querySelector(".chat-send");btn.disabled=true;btn.textContent="...";'
        'chatAppend("assistant","(reflexion en cours, l\'appel Opus prend 8-15s)");'
        'try{const r=await fetch("/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:msg,history:histSend,session_id:window._chatSessionId})});'
        # Surface real HTTP code + body snippet (content-type check before JSON.parse)
        'const ct=r.headers.get("content-type")||"";'
        'const last=document.querySelector(".chat-log .chat-msg:last-child");last.remove();'
        'if(!ct.includes("application/json")){const txt=(await r.text()).slice(0,200);chatAppend("assistant","ERREUR HTTP "+r.status+" "+r.statusText+" (server returned "+ct+", not JSON). Body : "+txt);}'
        'else{const d=await r.json();'
        'if(d.error){chatAppend("assistant","ERREUR serveur : "+d.error);}else{const reply=d.reply||"(reponse vide)";chatAppend("assistant",reply);window._chatHistory.push({role:"user",content:msg});window._chatHistory.push({role:"assistant",content:reply});chatPersist();resetChatIdleTimer();}'
        '}}catch(err){const last=document.querySelector(".chat-log .chat-msg:last-child");if(last)last.remove();chatAppend("assistant","ERREUR client/reseau : "+err.name+" : "+err.message);}'
        'btn.disabled=false;btn.textContent="Envoyer";return false;}'
        '</script>'
    )


def _clean_sector(sid: str | None) -> str:
    if not sid:
        return "Sans thesis"
    s = re.sub(r"_20\d\d$", "", sid).replace("_", " ").title()
    return (
        s.replace(" Ai", " AI")
        .replace("Ai ", "AI ")
        .replace("Hpq", "HPQ")
        .replace("Eu ", "EU ")
        .replace("Mag7", "MAG 7")
    )


def _positions(views: dict | None = None) -> list[dict]:
    """Builder unique consommé par _concentration, _cluster_health, _risk_watch_panel.

    MIGRATION 09/06 (Phase Lane 2 #1) — directive Olivier :
      Le builder UNIQUE de positions doit lire le seam `book.value_eur` (Datum
      canonique via prices.get + prices.fx live). Avant : weight = qty *
      current_price_eur (cache DB). Maintenant : weight = view.value_eur_datum.
      Trois panneaux deviennent cohérents d'un coup avec ce seul commit.

    Si `views` n'est pas passé, le builder appelle get_all_positions_views()
    lui-même (callsite hors render principal). Test invariant somme-parties
    (`tests/test_aggregate_sum_equals_parts.py`) verrouille la cohérence
    `Σ p["weight"] == Σ view.value_eur`.

    Fallback BookLine.weight_market_eur si view manquante (position sans
    thèse active OU view degraded fail-closed). Documente le degraded au
    moment de la migration.

    Shape backward-compat (inchangée vs avant) :
        ticker (str) · weight (float, EUR market value) · avg_cost · wrapper
        · qty · current_price_eur · cost_basis_eur
        + M1 typed columns (last_price_native, last_price_currency, price_asof,
          fx_rate_to_eur, fx_asof) -- TODO migration : ces colonnes legacy
          deviennent obsolètes une fois consumers migrés vers view.* direct.
    """
    try:
        from shared import book as _bk
    except Exception:
        return []

    if views is None:
        try:
            from shared.position_view import get_all_positions_views
            views = get_all_positions_views()
        except Exception:
            views = {}

    out = []
    for ln in _bk.get_held_lines():
        cost_basis = (ln.qty or 0) * (ln.avg_cost_eur or 0)
        # weight depuis le seam canonical (book.value_eur via prices.get/fx live).
        # Fallback BookLine si view absente (thèse non-active / view degraded).
        v = views.get(ln.ticker) if views else None
        if v is not None and v.value_eur_datum is not None:
            _v = v.value_eur_datum.value
            weight = float(_v.amount if hasattr(_v, "amount") else _v)
        else:
            weight = ln.weight_market_eur or 0
        out.append({
            "ticker": ln.ticker,
            "weight": weight,  # MARKET VALUE EUR via seam canonical (book.value_eur)
            "avg_cost": float(ln.avg_cost_eur or 0),
            "wrapper": (ln.wrapper or "CTO").upper(),
            "qty": float(ln.qty or 0),
            "current_price_eur": ln.current_price_eur,
            "cost_basis_eur": cost_basis,
            # M1 typed columns canoniques (Axe 3 / Axe 5).
            "last_price_native": ln.last_price_native,
            "last_price_currency": ln.last_price_currency,
            "price_asof": ln.price_asof,
            "fx_rate_to_eur": ln.fx_rate_to_eur,
            "fx_asof": ln.fx_asof,
        })
    return out


def _sectors() -> dict:
    sect_map = _cfg().get("sectors", {})
    out: dict = {}
    for sector, tickers in sect_map.items():
        for tk in tickers:
            out[tk] = sector
    return out


def _names() -> dict:
    for col in ("short_name", "name"):
        try:
            return {tk: nm for tk, nm in _q(f"SELECT ticker, {col} FROM ticker_names") if nm}
        except Exception:
            continue
    return {}


def _planned(held: set) -> list[dict]:
    out: list[dict] = []
    try:
        rows = _q("SELECT ticker, target_eur, target_weight_pct, bucket FROM portfolio_targets")
    except Exception:
        return out
    for tk, teur, tpct, bucket in rows:
        if tk in held:
            continue
        label = _clean_sector(bucket) if bucket else "&mdash;"
        out.append(
            {"ticker": tk, "weight": float(teur or 0), "pct": float(tpct or 0), "sector": label, "planned": True}
        )
    return out


def _pnl_map(computed: list[dict]) -> dict:
    out = {}
    for r in computed:
        e, c = r.get("entry") or 0, r.get("current_price") or 0
        if e:
            out[r["ticker"]] = (c - e) / e * 100
    return out


def _pnl_cost_map(positions: list[dict], views: dict | None = None) -> dict:
    """P&L map canonique EUR -- COMPUTE-ONCE-PROJECT (L29 #123 fix complet).

    HISTORIQUE des cures L29 :
    - efb3c59 (1ère cure) : SOURCE unifiée vers book.value_eur (cache→live)
    - Finding live checker post-W0 : Δ=0.658% > ε=0.5% sur BESI.AS (a GROSSI
      après cure). Diagnostic Olivier : source unifiée ≠ calcul unique.
      pnl_position est re-CALCULÉ par 2 producteurs (PositionView + ici) →
      2 fetches book.value_eur dans le même regen peuvent micro-diverger.
    - THIS FIX (#123) : compute-once-project canonique L27. Le pnl_position
      est calculé UNE FOIS dans shared.position_view.compute_position()
      (cf L351). _pnl_cost_map ne re-calcule plus -- il LIT view.pnl_position_pct
      depuis le dict views passé. Byte-identique garanti, fork mort pour de bon.

    Args:
        positions : liste dict positions (cf _positions() shape)
        views : dict {ticker: PositionView} pré-calculé (source canonique).
                Si None ou un ticker absent : fallback book.value_eur direct
                (KNOWN-GAP transitoire — divergence possible vs assembly).
    """
    out: dict = {}
    for p in positions:
        tk = p.get("ticker")
        if not tk:
            continue
        # COMPUTE-ONCE-PROJECT : lis pnl_position depuis PositionView (canonique)
        v = views.get(tk) if views else None
        if v is not None and getattr(v, "pnl_position_pct", None) is not None:
            pct = float(v.pnl_position_pct)
            out[tk] = pct
            # Republie dans concept_index avec source="render._pnl_cost_map.read"
            # — byte-identique avec "position_view" (même _views, même value lue).
            try:
                from shared.living_graph import register_concept
                register_concept(
                    concept_key="pnl_position",
                    value=pct,
                    source="render._pnl_cost_map.read",
                    ticker=tk,
                    op="read_from_position_view",
                )
            except Exception:
                pass
            continue
        # Fallback : pas de PositionView -- re-calcule (KNOWN-GAP transitoire,
        # divergence possible vs assembly si appelé sans views).
        qty = p.get("qty")
        avg_cost_eur = p.get("avg_cost_eur") or p.get("avg_cost")
        if not (qty and avg_cost_eur and qty > 0 and avg_cost_eur > 0):
            continue
        from shared.book import value_eur as bve
        bv = bve(tk, qty)
        if bv is None or bv.value is None:
            continue
        value_eur_now = bv.value.amount if hasattr(bv.value, "amount") else bv.value
        if not value_eur_now or value_eur_now <= 0:
            continue
        cost_basis_eur = qty * avg_cost_eur
        pct = (value_eur_now / cost_basis_eur - 1) * 100.0
        out[tk] = pct
        try:
            from shared.living_graph import register_concept
            register_concept(
                concept_key="pnl_position",
                value=pct,
                source="render._pnl_cost_map.fallback",
                ticker=tk,
                op="book_value_eur_div_cost_basis_eur",
            )
        except Exception:
            pass
    return out


def _rows_paliers(computed: list[dict]) -> tuple[str, int, str]:
    data = []
    for r in computed:
        e, t, c = r.get("entry") or 0, r.get("target_full") or 0, r.get("current_price") or 0
        if e and t and t != e:
            data.append(((c - e) / (t - e) * 100, (c - e) / e * 100, r["ticker"]))
    data.sort(key=lambda x: -x[0])
    top = f"{data[0][2]} {data[0][0]:.0f}%" if data else "&mdash;"
    rows, hits = [], 0
    for i, (prog, pnl, tk) in enumerate(data):
        pc = max(0.0, min(100.0, prog))
        hit = prog >= 100
        hits += 1 if hit else 0
        cls, arrow = ("up", "&#9650;") if pnl >= 0 else ("down", "&#9660;")
        flag = " &#127919;" if hit else ""
        d = i * 0.035
        rows.append(
            f'<div class="row" data-tk="{tk}" style="animation-delay:{d:.2f}s"><div class="rt">'
            f'<span class="tk">{_ticker_logo(tk)}{tk}{flag}</span><span class="tag {cls}">{arrow}&nbsp;{abs(pnl):.1f}%</span></div>'
            f'{_tbar(pc, title=f"{pc:.1f}%")}'
            f'<div class="rs"><span>toward target</span><span class="mono">{prog:.0f}%</span></div></div>'
        )
    return "".join(rows), hits, top


def _elan_watch(computed: list[dict]) -> tuple[str, int]:
    """Race toward target: winners near target (anti-bias #1 axis, positive framing)."""
    data = []
    for r in computed:
        e, t, c = r.get("entry") or 0, r.get("target_full") or 0, r.get("current_price") or 0
        if e and t and t != e:
            prog = (c - e) / (t - e) * 100
            if prog >= 75:
                data.append((prog, r["ticker"]))
    data.sort(key=lambda x: -x[0])
    # Fix ambiguite 31/05 user : "149% vers la target" pretait a confusion
    # (depassement vs progression). Split en 2 verbiages directionnels :
    # > 100% -> "+X% au-dela target" (overshoot, prends ton profit / rightsize)
    # < 100% -> "-X% sous target"   (reste a parcourir, marge restante)
    # = 100% -> "a la target"
    def _label(prog: float) -> str:
        if prog >= 100.5:
            return f"+{prog - 100:.0f}% beyond target"
        if prog <= 99.5:
            return f"&minus;{100 - prog:.0f}% below target"
        return "at target"

    rows = "".join(
        f'<div class="line"><span>{tk}</span><span class="mono">{_label(prog)}</span></div>'
        for prog, tk in data
    )
    watch = (
        rows or '<div class="empty" style="padding:var(--s4) 0">no position &ge;75% of target &mdash; remaining margins</div>'
    )
    return watch, len(data)


def _rows_risque(computed: list[dict], positions: list[dict] | None = None) -> tuple[str, int, float, str]:
    data = sorted(((r.get("downside_pct", 0), r["ticker"]) for r in computed), key=lambda x: x[0])
    tensions = [max(0.0, min(1.0, (20 - d) / 20)) for d, _ in data]
    # AUDIT v5 fix STRUCTUREL : heat = sum(weight_share * downside_pct) en %
    # capital at risk si tous les stops touches.
    # Convention pro (Pro Trader Dashboard / Van Tharp / Elder) : portfolio
    # heat = SOMME ponderee, pas max(). Avant : max(tensions) sous-estimait
    # le risque agrege. En crash, correlations spike, toutes les tensions
    # s'additionnent.
    if positions:
        weight_map = {p["ticker"]: float(p.get("weight", 0)) for p in positions}
        total_weight = sum(weight_map.values()) or 1.0
        # % capital at risk if all stops hit = sum (weight_share_i * downside_pct_i)
        heat = sum(
            (weight_map.get(tk, 0) / total_weight) * d
            for d, tk in data
        )
    else:
        # Fallback legacy (single-max) si positions pas fournies
        heat = (max(tensions) * 100) if tensions else 0.0
    rows, near, near_rows = [], 0, []
    for i, (down, tk) in enumerate(data):
        buf = max(0.0, min(100.0, down / 30 * 100))
        is_near = down < 10
        near += 1 if is_near else 0
        cls = "danger" if is_near else ("warn" if down < 20 else "calm")
        flag = " &#128308;" if is_near else ""
        d = i * 0.035
        rows.append(
            f'<div class="row" data-tk="{tk}" style="animation-delay:{d:.2f}s"><div class="rt">'
            f'<span class="tk">{tk}{flag}</span><span class="tag {cls}">{down:.0f}%</span></div>'
            f'{_tbar(buf, title=f"{buf:.1f}% margin before stop")}'
            f'<div class="rs"><span>margin before stop</span></div></div>'
        )
        if is_near:
            near_rows.append(f'<div class="line"><span>{tk}</span><span class="mono">{down:.0f}% de marge</span></div>')
    watch = (
        "".join(near_rows)
        or '<div class="empty" style="padding:var(--s4) 0">no low margin &mdash; calm</div>'
    )
    return "".join(rows), near, heat, watch


def _mover_blk(rows) -> str:
    return (
        "".join(
            f'<div class="line"><span class="mono">{tk}</span>'
            f'<span class="mono {"pos" if p >= 0 else "neg"}">{"+" if p >= 0 else ""}{p:.1f}%</span></div>'
            for tk, p in rows
        )
        or '<div class="empty" style="padding:var(--s35) 0">&mdash;</div>'
    )


def _movers(pnl: dict) -> tuple[str, str]:
    items = sorted(pnl.items(), key=lambda x: -x[1])

    return _mover_blk(items[:5]), _mover_blk(items[-5:][::-1] if len(items) > 5 else [])


def _day_movers(daily: dict) -> tuple[str, str]:
    vals = [(tk, v) for tk, v in daily.items() if v is not None]
    ups = sorted((x for x in vals if x[1] >= 0), key=lambda x: -x[1])[:5]
    dns = sorted((x for x in vals if x[1] < 0), key=lambda x: x[1])[:5]

    return _mover_blk(ups), _mover_blk(dns)


def _compute_ai_set() -> set[str]:
    """Membres du cluster correle = supergroupe 'Compute AI' (source unique = concentration.clusters)."""
    return set(_cfg().get("concentration", {}).get("clusters", {}).get("compute_ai", []))


def _cluster_health(positions: list[dict], pnl: dict) -> list[dict]:  # noqa: ARG001
    """Source unique des breaches de cluster correle (gouverneur de concentration).
    Consomme par la page Concentration (detail) ET le bandeau d'ecart (resume, haut de page).
    Une seule definition de la valeur EUR par ligne -> page et bandeau ne peuvent plus
    se contredire (cf. ancienne jauge 0 calme vs verdict ELEVEE)."""

    def _v(p: dict) -> float:
        return float(p["weight"])

    total = sum(_v(p) for p in positions) or 1
    _cfg = yaml.safe_load(Path("config.yaml").read_text())
    _conc = _cfg.get("concentration", {})
    # Axe 4 fix mensonge cluster : afficher le cap OPERATOIRE, pas le default
    # conservateur 35% (ADR 010) qui est OVERRIDE par user_strategy quand
    # archetype="concentrator_thematic". Le default 35 disait "tu es a 2x ton
    # cap" alors que le cap effectif est 70 -> ca poussait au trim biais
    # sell-too-early. Source de verite unique : user_strategy.
    _us = _cfg.get("user_strategy") or {}
    if _us.get("archetype") == "concentrator_thematic":
        ccap = float(_us.get("target_cluster_cap_pct", 35))
    else:
        ccap = float(_conc.get("cluster_max_pct", 0)) * 100
    out: list[dict] = []
    for cn, mem in (_conc.get("clusters") or {}).items():
        ms = set(mem)
        cv = sum(_v(p) for p in positions if p["ticker"] in ms)
        cp = cv / total * 100
        out.append(
            {
                "name": _clean_sector(cn),
                "pct": cp,
                "cap": ccap,
                "over_eur": cv - ccap / 100 * total,
                "breached": cp >= ccap,
            }
        )
    return out


def _concentration(
    positions: list[dict], planned: list[dict], sectors: dict, names: dict, pnl: dict, daily: dict
) -> str:
    def _v(p: dict) -> float:
        return float(p["weight"])  # market value post-migration 29/05

    # Post-migration : "cost_total" est maintenant explicitement cost basis.
    cost_total = sum(p.get("cost_basis_eur", p["weight"]) for p in positions) or 1
    total = sum(_v(p) for p in positions) or 1
    ps = sorted(positions, key=lambda p: -_v(p))
    top = ps[0] if ps else None
    top_tk = top["ticker"] if top else "&mdash;"
    top_nm = names.get(top_tk, top_tk) if top else "&mdash;"
    top_pct = (_v(top) / total * 100) if top else 0.0
    sw: dict[str, float] = {}
    for p in positions:
        key = sectors.get(p["ticker"], "Sans thesis")
        sw[key] = sw.get(key, 0.0) + _v(p)
    sw_real = {k: v for k, v in sw.items() if k != "Sans thesis"}
    dom_these = max(sw_real, key=lambda k: sw_real[k]) if sw_real else "&mdash;"
    dom_these_pct = (max(sw_real.values()) / total * 100) if sw_real else 0.0
    over_cap_tk = [p["ticker"] for p in ps if _v(p) / total * 100 >= POS_CAP]
    over_cap = len(over_cap_tk)
    over_nm = " &middot; ".join(names.get(t, t) for t in over_cap_tk[:3]) + ("&hellip;" if over_cap > 3 else "")
    _ch = _cluster_health(positions, pnl)
    cluster_breached = any(c["breached"] for c in _ch)
    cluster_excessive = any(c["pct"] >= 50 for c in _ch)
    if dom_these_pct >= 45 or top_pct >= 2 * POS_CAP or cluster_excessive:
        verdict, vcls = "EXCESSIVE", "danger"
    elif dom_these_pct >= NARRATIVE_CAP or over_cap or cluster_breached:
        verdict, vcls = "&Eacute;LEV&Eacute;E", "warn"
    else:
        verdict, vcls = "MESUR&Eacute;E", "calm"
    cbits = []
    if dom_these_pct >= NARRATIVE_CAP:
        cbits.append("thesis above cap")
    if over_cap:
        cbits.append(f"{over_cap} position(s) outside cap")
    if cluster_breached:
        cbits.append("correlated cluster above cap")
    cause = " &middot; ".join(cbits) or "all under caps"
    top_cls = "negc" if top_pct >= POS_CAP else "acc"
    these_cls = "negc" if dom_these_pct >= NARRATIVE_CAP else "acc"
    line_msg = f"{top_nm} &middot; {'&#9888; above cap' if top_pct >= POS_CAP else 'under cap'} {POS_CAP:.0f}%"
    these_msg = f"{dom_these} &middot; {'&#9888; trim' if dom_these_pct >= NARRATIVE_CAP else 'under cap'} {NARRATIVE_CAP:.0f}%"
    cap = f"{cost_total:,.0f}".replace(",", "&#8239;")
    # === Star Concentration : fusion verdict + cluster + 3 KPIs ===
    # Mapping verdict cls -> ps-val color class
    # vcls peut etre danger/warn/calm OU acc/warn/bear selon la source.
    # Normalise vers acc/warn/bear pour les ps-val color.
    def _to_pscls(c: str) -> str:
        return {"danger": "bear", "bear": "bear", "warn": "warn", "calm": "acc", "acc": "acc"}.get(c, "")
    _verdict_pcls = _to_pscls(vcls)
    _top_pcls = _to_pscls(top_cls)
    _these_pcls = _to_pscls(these_cls)
    # Footer : cluster gouverneur si breached. Color le depassement selon gravite.
    _cluster_foot = ""
    breached = [c for c in _ch if c["breached"]]
    if breached:
        c = breached[0]
        _ov = f"{c['over_eur']:,.0f}".replace(",", "&#8239;")
        _over_pct = max(0, c["pct"] - c["cap"])
        # Gravite : <2pp warn light, 2-5pp warn, >=5pp bear
        if _over_pct >= 5:
            _over_color = "bear"
        elif _over_pct >= 2:
            _over_color = "warn"
        else:
            _over_color = "warn"
        _cluster_foot = (
            f"Cluster <b>{c['name']}</b> at {c['pct']:.0f}% (cap {c['cap']:.0f}%) "
            f"&middot; <b class=\"{_over_color}\">+{_over_pct:.0f}%</b> au-dessus &middot; +{_ov}&nbsp;&euro;"
        )
    else:
        _cluster_foot = "Correlated cluster (governor): below cap"
    # Over_cap color selon gravite : 0 ligne = acc, 1-2 = warn, 3+ = bear
    if over_cap == 0:
        _oc_color = "acc"
    elif over_cap <= 2:
        _oc_color = "warn"
    else:
        _oc_color = "bear"
    _overcap_meta = (
        f'<b class="{_oc_color}">{over_cap}</b> position(s) above cap {POS_CAP:.0f}%'
        + (f" &middot; {over_nm}" if over_nm else "")
    )
    star_strate_verdict = (
        '<div class="ps-strate">'
        + '<div class="ps-lbl">Concentration verdict</div>'
        + '<div class="ps-macro-row">'
        + f'<div class="ps-val {_verdict_pcls}">{verdict}</div>'
        + f'<div class="ps-macro-meta">{cause}</div>'
        + "</div>"
        + f'<div class="ps-cap">{_overcap_meta}</div>'
        + "</div>"
    )
    star_strate_grid = (
        '<div class="ps-strate ps-grid">'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Position with highest individual weight in portfolio. Cap by conviction (c5 up to 22%, c4 up to 14%).">Top position</div><div class="ps-val {_top_pcls}">{_pct(top_pct)}%</div><div class="ps-cap">{line_msg}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Thesis with highest aggregated weight (sum of positions carrying it). Thematic concentration indicator.">Dominant thesis</div><div class="ps-val {_these_pcls}">{dom_these_pct:.0f}%</div><div class="ps-cap">{dom_these} &middot; {these_msg}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Cumulative capital invested in book (cost basis sum). Distinct from current value with PnL.">Capital invested</div><div class="ps-val">{cap}&nbsp;&euro;</div><div class="ps-cap">{len(positions)} positions &middot; {len(sw_real)} sectors</div></div>'
        + "</div>"
    )
    star_strate_foot = f'<div class="ps-strate ps-foot">{_cluster_foot}</div>'
    star_concentration = (
        f'<div class="page-star">{star_strate_verdict}{star_strate_grid}{star_strate_foot}</div>'
    )
    return (
        f'<section data-page="concentration" role="region" aria-label="Concentration"><div class="phead"><h2>Concentration</h2>'
        f'</div>'
        f"{star_concentration}"
        # Retrait 02/06 user : sb-bars (horizontal bars par sector) = doublon
        # evident avec donut sectors page Positions. JS sb-bars handler conserve
        # dans le code, panneau retire de la page Concentration.
        f'<div class="card pad"><div class="colhead"><span class="t">By sector</span></div>{_sector_blocks(positions, planned, sectors, pnl, names, daily)}</div>'
        f'<div class="card pad" style="margin-top:var(--s4)"><div class="colhead"><span class="t">By country</span><span class="a">headquarters &middot; not real supply chain (Taiwan underweighted)</span></div>{_geo_bars(positions)}</div>'
        f'<div style="margin-top:var(--s4)">{_fx_exposure_panel()}</div>'
        f"</section>"
    )


def _render_bucket(
    name: str, rows: list, total: float, pnl: dict, names: dict, daily: dict, fx: float, sub: bool = False
) -> tuple[str, float]:
    rows = sorted(rows, key=lambda r: -r["w"])
    sw = sum(r["w"] for r in rows)
    spct = sw / total * 100
    wbase = sum(r["w"] for r in rows if not r["prev"] and pnl.get(r["tk"]) is not None)
    wpl = sum(r["w"] * pnl[r["tk"]] for r in rows if not r["prev"] and pnl.get(r["tk"]) is not None)
    spl = (wpl / wbase) if wbase else None
    plmeta = ""
    if spl is not None:
        plmeta = (
            f' &middot; <span class="sec-pl {"pos" if spl >= 0 else "neg"}">{"+" if spl >= 0 else ""}{spl:.1f}%</span>'
        )
    lines = ""
    for r in rows:
        tk = r["tk"]
        w = r["w"]
        usd = w / fx
        pct = w / total * 100
        badge = '<span class="bdg">planned</span>' if r["prev"] else ""
        nm = names.get(tk, "")
        nmspan = f'<span class="sec-nm">{nm}</span>' if nm else ""
        pl = None if r["prev"] else pnl.get(tk)
        dv = None if r["prev"] else daily.get(tk)
        plc = (
            '<span class="num">&mdash;</span>'
            if pl is None
            else f'<span class="num {"pos" if pl >= 0 else "neg"}">{"+" if pl >= 0 else ""}{pl:.1f}%</span>'
        )
        dvc = (
            '<span class="num">&mdash;</span>'
            if dv is None
            else f'<span class="num {"pos" if dv >= 0 else "neg"}">{"+" if dv >= 0 else ""}{dv:.1f}%</span>'
        )
        lines += (
            f'<div class="sec-row" data-tk="{tk}" data-w="{w:.2f}" data-pct="{pct:.4f}" data-dv="{dv if dv is not None else -1e9:.2f}" data-pl="{pl if pl is not None else -1e9:.2f}">'
            f'<span class="sec-tk">{_ticker_logo(tk)}{tk}{badge}{nmspan}</span>'
            f'<span class="num">{w:.0f}&euro;</span><span class="num">${usd:.0f}</span>'
            f'<span class="num">{pct:.1f}%</span>{dvc}{plc}</div>'
        )
    cls = "sec-grp sub" if sub else "sec-grp"
    return (
        f'<div class="{cls}"><div class="sec-h"><span class="sec-name">{name}</span>'
        f'<span class="sec-meta">{len(rows)} &middot; {sw:.0f}&euro; &middot; {spct:.1f}%{plmeta}</span></div>'
        f'<div class="sec-rows">{lines}</div></div>'
    ), sw


def _sector_blocks(
    positions: list[dict], planned: list[dict], sectors: dict, pnl: dict, names: dict, daily: dict
) -> str:
    real_t = sum(p["weight"] for p in positions)
    plan_t = sum(p["weight"] for p in planned)
    total = (real_t + plan_t) or 1
    fx = FX_USD
    _cl = _compute_ai_set()
    fine: dict = {}
    for p in positions:
        fine.setdefault(sectors.get(p["ticker"], "Autre"), []).append(
            {"tk": p["ticker"], "w": p["weight"], "prev": False}
        )
    for p in planned:
        fine.setdefault(p.get("sector") or "Autre", []).append({"tk": p["ticker"], "w": p["weight"], "prev": True})
    # Compute AI (L1) = membres DETENUS du cluster, niches sous leur bucket fin (L2). Reste top-level.
    compute_sub: dict = {}
    standalone: dict = {}
    for fb, rws in fine.items():
        mem = [r for r in rws if r["tk"] in _cl]
        rest = [r for r in rws if r["tk"] not in _cl]
        if mem:
            compute_sub[fb] = mem
        if rest:
            standalone[fb] = rest
    blocks = ""
    if compute_sub:
        sub_order = sorted(compute_sub, key=lambda fb: -sum(r["w"] for r in compute_sub[fb]))
        subhtml = ""
        c_rows: list = []
        for fb in sub_order:
            h, _sw = _render_bucket(fb, compute_sub[fb], total, pnl, names, daily, fx, sub=True)
            subhtml += h
            c_rows += compute_sub[fb]
        c_sw = sum(r["w"] for r in c_rows)
        c_pct = c_sw / total * 100
        c_wb = sum(r["w"] for r in c_rows if not r["prev"] and pnl.get(r["tk"]) is not None)
        c_wp = sum(r["w"] * pnl[r["tk"]] for r in c_rows if not r["prev"] and pnl.get(r["tk"]) is not None)
        c_spl = (c_wp / c_wb) if c_wb else None
        c_pm = (
            ""
            if c_spl is None
            else f' &middot; <span class="sec-pl {"pos" if c_spl >= 0 else "neg"}">{"+" if c_spl >= 0 else ""}{c_spl:.1f}%</span>'
        )
        blocks += (
            f'<div class="sec-super"><div class="sec-superh"><span class="sec-supername">Compute AI</span>'
            f'<span class="sec-meta">{len(c_rows)} &middot; {c_sw:.0f}&euro; &middot; {c_pct:.1f}%{c_pm}</span></div>'
            f'<div class="sec-subwrap">{subhtml}</div></div>'
        )
    order = sorted(standalone, key=lambda fb: -sum(r["w"] for r in standalone[fb]))
    for fb in order:
        h, _sw = _render_bucket(fb, standalone[fb], total, pnl, names, daily, fx)
        blocks += h
    return (
        f'<div class="sec-cols"><span></span><span class="num">&euro;</span><span class="num">$</span>'
        f'<span class="num">%</span><span class="num">Day</span><span class="num">P&amp;L</span></div>'
        f"{blocks}"
    )


def _geo_bars(positions: list[dict]) -> str:
    total = sum(p["weight"] for p in positions) or 1
    cw: dict[str, float] = {}
    cstk: dict[str, list[tuple[str, float]]] = {}
    for p in positions:
        c = _country(p["ticker"])
        cw[c] = cw.get(c, 0.0) + p["weight"]
        cstk.setdefault(c, []).append((p["ticker"], p["weight"]))
    from collections.abc import Callable
    _gsn: Callable[[str], str | None] | None
    try:
        from shared.ticker_names import get_short_name as _gsn_real
        _gsn = _gsn_real
    except Exception:
        _gsn = None
    css = (
        "<style>"
        ".geo-item{cursor:pointer}"
        ".geo-item .row{transition:background .15s;border-radius:var(--r2)}"
        ".geo-item:hover .row{background:color-mix(in srgb,var(--ink) 4%,transparent)}"
        ".geo-sub{max-height:0;overflow:hidden;opacity:0;"
        "transition:max-height .3s ease,opacity .2s ease,margin .3s ease}"
        ".geo-item.open .geo-sub{max-height:360px;opacity:1;margin:var(--s1) 0 14px}"
        ".geo-stk{display:flex;align-items:center;gap:var(--s3);padding:var(--s15) 6px 5px 16px;"
        "font-size:15px;border-left:2px solid var(--line2);margin-left:3px}"
        ".geo-stk .gnm{color:var(--ink)}"
        ".geo-stk .gtk{color:var(--steel);font-family:var(--fm);font-size:14px}"
        ".geo-stk .gpc{margin-left:auto;color:var(--steel);font-family:var(--fm);font-size:14px}"
        ".geo-stk .gw{color:var(--ink);font-family:var(--fm);min-width:62px;text-align:right}"
        "</style>"
    )
    bars = ""
    for country, w in sorted(cw.items(), key=lambda x: -x[1]):
        pct = w / total * 100
        sub = ""
        for tk, sw in sorted(cstk.get(country, []), key=lambda x: -x[1]):
            nm = ""
            if _gsn is not None:
                try:
                    nm = _gsn(tk) or ""
                except Exception:
                    nm = ""
            spc = (sw / w * 100) if w else 0
            sub += (
                f'<div class="geo-stk"><span class="gnm">{nm or tk}</span>'
                f'<span class="gtk">{tk if nm else ""}</span>'
                f'<span class="gpc">{spc:.0f}%</span>'
                f'<span class="gw">{sw:.0f}&euro;</span></div>'
            )
        bars += (
            f'<div class="geo-item">'
            f'<div class="row"><div class="rt"><span class="tk">{country}</span>'
            f'<span class="tag acc2">{pct:.0f}%</span></div>'
            f'{_tbar(pct, title=f"{pct:.1f}%")}'
            f'<div class="rs"><span>exposition</span><span class="mono">{w:.0f}&euro;</span></div></div>'
            f'<div class="geo-sub">{sub}</div></div>'
        )
    js = (
        "<script>document.querySelectorAll('.geo-item').forEach(function(e){"
        "e.addEventListener('click',function(){e.classList.toggle('open')})});</script>"
    )
    return css + bars + js


def _fx_status_label_html() -> str:
    """E4 craft : badge discret FX freshness dans la foot. Resume l'etat des
    pairs FX utilisees en pratique (USD/JPY/KRW/HKD vers EUR). Vert subtle
    si tout live_cached, warn si une pair tombe en fallback hardcoded ou
    stale > 24h, neutre si never_queried (= cold start dashboard).

    Honnete : on dit explicitement "FX live" / "FX HARDCODED" / etc., pas
    de fausse precision."""
    try:
        from shared.prices import fx_freshness, fx_is_stale, get_fx_rate

        pairs = [("USD", "EUR"), ("JPY", "EUR"), ("KRW", "EUR"), ("HKD", "EUR")]
        # Warm cache : le dashboard regen appelle deja get_fx_rate via d'autres
        # voies (positions display, etc.), mais on s'assure pour le badge.
        for f, t in pairs:
            get_fx_rate(f, t)
        statuses = [fx_freshness(f, t) for f, t in pairs]
        n_live = sum(1 for s in statuses if s["source"] == "live_cached")
        n_stale = sum(1 for f, t in pairs if fx_is_stale(f, t))
        n_fallback = sum(1 for s in statuses if s["source"] in ("never_queried",))
        if n_live == len(pairs):
            txt, cls = "FX&nbsp;live", "calm"
        elif n_fallback > 0:
            txt, cls = f"FX&nbsp;{n_fallback}/{len(pairs)}&nbsp;hardcoded", "warn"
        elif n_stale > 0:
            txt, cls = f"FX&nbsp;{n_stale}/{len(pairs)}&nbsp;stale", "warn"
        else:
            txt, cls = "FX&nbsp;live", "calm"
        # Tooltip detail : etat par pair
        title_parts = []
        for (f, t), s in zip(pairs, statuses, strict=False):
            age = s.get("age_seconds")
            title_parts.append(f"{f}/{t}: {s['source']}" + (f" ({age}s)" if age else ""))
        title = " ; ".join(title_parts)
        color = "var(--acc)" if cls == "calm" else "var(--warn)"
        return (
            f'<span class="mono" style="font-size:14px;opacity:.65;padding:0 var(--s2);color:{color}"'
            f' title="{title}">{txt}</span>'
        )
    except Exception:
        return ""


def _insider_flow_strip_html() -> str:
    """E2 wire-up A3 (31/05/2026) : surface insider_snapshots (~401 rows
    captures quotidiennes par insider_digest cron) qui etaient ingerees mais
    pas affichees au dashboard. Top 10 flow net agrege 7j, sort par |net_m|
    desc, star pour tickers en portefeuille user (highlight = "tes positions
    voient insiders dumper ?")."""
    try:
        owned = set()
        try:
            for (tk,) in _q("SELECT ticker FROM positions WHERE status='open' AND qty > 0"):
                owned.add(str(tk).upper())
        except Exception:
            pass
        rows = ""
        for tk, net_m, buys, sells in _q(
            "SELECT ticker, ROUND(SUM(net_m), 1) AS net_7d, "
            "       COALESCE(SUM(n_buys),0), COALESCE(SUM(n_sells),0) "
            "FROM insider_snapshots WHERE snapshot_date >= date('now', '-7 days') "
            "GROUP BY ticker HAVING net_7d IS NOT NULL AND ABS(net_7d) > 0 "
            "ORDER BY ABS(net_7d) DESC LIMIT 10"
        ):
            tk_u = str(tk).upper()
            star = "&#9733; " if tk_u in owned else ""
            net = float(net_m or 0)
            abs_net = abs(net)
            if net > 0:
                tag_cls, tag_lbl = "acc", f"+${net:.1f}M"
            elif abs_net > 500:
                tag_cls, tag_lbl = "danger", f"-${abs_net:.0f}M"
            elif abs_net > 100:
                tag_cls, tag_lbl = "warn", f"-${abs_net:.0f}M"
            else:
                tag_cls, tag_lbl = "calm", f"-${abs_net:.1f}M"
            rows += (
                f'<div class="row"><div class="rt"><span class="tk tkc" data-tk="{tk_u}">{star}{tk_u}</span>'
                f'<span class="tag {tag_cls}">{tag_lbl}</span></div>'
                f'<div class="rs"><span>{int(buys)} buys &middot; {int(sells)} sells</span>'
                f'<span class="mono">7&nbsp;j</span></div></div>'
            )
        return rows or (
            '<div class="empty">'
            '<span class="empty-ico">i</span>'
            '<b>No insider flow</b>'
            'No transactions Form 4 SEC sur la fen&ecirc;tre 7&nbsp;j.'
            '<span class="hint">Filled by executive buys/sells &gt; $50k</span>'
            '</div>'
        )
    except Exception as e:
        return _err(e)


def _loop() -> str:
    """Page Loop -- decision provenance per ticker.

    Revolutionary surface : pour chaque ticker actif, montre la chaine
    causale visuelle des 60 derniers jours : signaux entrants (sources)
    + predictions emises + decisions journees + outcomes resolus.

    State 02/06 : 354 signals, 173 preds 60d, 65 audit logs (V0 epoch -- pas
    de ticker direct), 18 outcomes resolved. Le graph se densifie post J-day
    10/06. Per-ticker view = lisible MEME sur peu de data.
    """
    try:
        from shared import storage as _stg_loop
        # ADR 014 § Substance tier : LLM-loop audit affiche les predictions
        # LLM (v1 archive + v2 canonical). Exclut shadow/fallback non-LLM.
        _loop_filter = _stg_loop.substance_predictions_filter().replace(
            "methodology_version", "p.methodology_version"
        )
        # All predictions last 60d with source name
        preds = _q(
            "SELECT p.id, p.ticker, p.direction, p.outcome, p.brier_score, "
            "       p.baseline_date, p.resolved_at, "
            "       COALESCE(src.name, 'manual') as sig_source, "
            "       p.probability_at_creation "
            "FROM predictions p "
            "LEFT JOIN signals s ON s.id = p.signal_id "
            "LEFT JOIN sources src ON src.id = s.source_id "
            f"WHERE {_loop_filter} "
            "  AND p.baseline_date >= date('now', '-60 days') "
            "ORDER BY p.ticker, p.baseline_date ASC"
        )
        audits = _q(
            "SELECT ticker, event_type, occurred_at "
            "FROM position_audit_log "
            "WHERE occurred_at >= datetime('now', '-60 days') "
            "  AND event_type IN ('buy', 'sell', 'partial_sell', 'trim') "
            "ORDER BY occurred_at ASC"
        )
    except Exception as e:
        return _err(e)

    # Filter universe : held positions + planned only (user 02/06).
    # Le bot scanne 354 signals sur ~50 tickers mais l'user ne suit que ses
    # positions actuelles et planifiees.
    try:
        held_rows = _q("SELECT DISTINCT ticker FROM positions")
        planned_rows = _q("SELECT DISTINCT ticker FROM portfolio_targets")
        universe = {r[0] for r in held_rows} | {r[0] for r in planned_rows}
    except Exception:
        universe = set()

    # Group by ticker (only those in universe)
    from collections import defaultdict
    from datetime import date, timedelta
    by_ticker: dict[str, dict] = defaultdict(lambda: {
        "preds": [], "audits": [], "sources": set(),
    })
    for r in preds:
        pid, tk, direction, outcome, brier, baseline, resolved, source, prob = r
        if universe and tk not in universe:
            continue
        by_ticker[tk]["preds"].append({
            "id": pid, "dir": direction, "outcome": outcome,
            "brier": brier, "baseline": baseline, "resolved": resolved,
            "source": source or "?", "prob": prob,
        })
        if source:
            by_ticker[tk]["sources"].add(source)
    for tk, evt, occ in audits:
        if universe and tk not in universe:
            continue
        if tk in by_ticker:
            by_ticker[tk]["audits"].append({"event": evt, "occurred": occ})

    # User 02/06 : positions apparaissent au compte-gouttes selon signaux
    # emergents. Pas de signal -> pas de row. Drip-feed dynamic.
    # Sort tickers par activite recente (most recent prediction first)
    def _latest_activity(kv):
        prs = kv[1]["preds"]
        if not prs:
            return ""
        return max((p["baseline"] or "") for p in prs)
    sorted_tk = sorted(
        ((tk, d) for tk, d in by_ticker.items() if d["preds"] or d["audits"]),
        key=lambda kv: _latest_activity(kv),
        reverse=True,
    )

    # Time window
    end = date.today()
    start = end - timedelta(days=60)
    span_days = max(1, (end - start).days)

    def x_pct(date_str: str) -> float:
        if not date_str:
            return 0.0
        try:
            d = date.fromisoformat(date_str[:10])
            return max(0.0, min(100.0, (d - start).days / span_days * 100))
        except Exception:
            return 0.0

    # Build per-ticker rows
    rows_html = []
    for tk, data in sorted_tk[:50]:  # cap 50 tickers
        n_pred = len(data["preds"])
        n_resolved = sum(1 for p in data["preds"] if p["outcome"] is not None)
        briers = [p["brier"] for p in data["preds"] if p["brier"] is not None]
        avg_brier = sum(briers) / len(briers) if briers else None
        n_sources = len(data["sources"])
        n_audits = len(data["audits"])

        # Brier badge
        if avg_brier is None:
            brier_html = '<span class="lp-badge muted">N/A</span>'
        elif avg_brier < 0.20:
            brier_html = f'<span class="lp-badge acc">{avg_brier:.2f}</span>'
        elif avg_brier < 0.25:
            brier_html = f'<span class="lp-badge warn">{avg_brier:.2f}</span>'
        else:
            brier_html = f'<span class="lp-badge bear">{avg_brier:.2f}</span>'

        # Build events on a timeline
        events_html = []
        for p in data["preds"]:
            x = x_pct(p["baseline"])
            if p["outcome"] == "correct":
                cls = "ev-pred acc"
            elif p["outcome"] == "incorrect":
                cls = "ev-pred bear"
            elif p["outcome"] == "neutral":
                cls = "ev-pred steel"
            else:
                cls = "ev-pred open"
            tip = f"pred#{p['id']} {p['dir']} {p['source'][:30]} {p['baseline']}"
            if p["brier"] is not None:
                tip += f" Brier {p['brier']:.3f}"
            events_html.append(
                f'<span class="ev {cls}" style="left:{x:.1f}%" title="{tip}"></span>'
            )
            # Resolution dot if resolved
            if p["resolved"]:
                xr = x_pct(p["resolved"])
                events_html.append(
                    f'<span class="ev ev-out" style="left:{xr:.1f}%" title="resolved {p["resolved"][:10]}"></span>'
                )
        for a in data["audits"]:
            x = x_pct(a["occurred"])
            evt = a["event"]
            cls = "ev-dec bear" if evt in ("sell", "partial_sell", "trim") else "ev-dec acc"
            events_html.append(
                f'<span class="ev {cls}" style="left:{x:.1f}%" title="{evt} {a["occurred"][:10]}"></span>'
            )

        rows_html.append(
            f'<div class="lp-row" data-ticker="{tk}">'
            f'<div class="lp-tk">'
            f'<span class="lp-tkname">{tk}</span>'
            f'<span class="lp-tkmeta">{n_pred} pred &middot; {n_sources} src &middot; {n_audits} dec</span>'
            f'</div>'
            f'<div class="lp-track">{"".join(events_html)}</div>'
            f'<div class="lp-stats">'
            f'<span class="lp-resolved">{n_resolved}/{n_pred}</span>'
            f'{brier_html}'
            f'</div>'
            f'</div>'
        )

    # Date axis labels (top of grid)
    axis_marks = []
    for w in (0, 7, 14, 21, 28, 35, 42, 49, 56):
        if w > 60:
            continue
        d = start + timedelta(days=w)
        x = w / span_days * 100
        axis_marks.append(
            f'<span class="lp-mark" style="left:{x:.1f}%">{d.strftime("%d/%m")}</span>'
        )

    # Aggregate stats
    n_sig = len({p["source"] for tk_data in by_ticker.values() for p in tk_data["preds"]})
    n_pred_total = sum(len(d["preds"]) for d in by_ticker.values())
    _n_dec = len(audits)
    n_out = sum(1 for d in by_ticker.values() for p in d["preds"] if p["outcome"])

    stats = (
        f'<div class="loop-stats">'
        f'<div class="loop-stat"><span class="ls-val">{len(sorted_tk)}</span>'
        f'<span class="ls-lbl">active tickers</span></div>'
        f'<div class="loop-stat"><span class="ls-val">{n_sig}</span>'
        f'<span class="ls-lbl">distinct sources</span></div>'
        f'<div class="loop-stat"><span class="ls-val">{n_pred_total}</span>'
        f'<span class="ls-lbl">predictions 60d</span></div>'
        f'<div class="loop-stat"><span class="ls-val">{n_out}</span>'
        f'<span class="ls-lbl">resolved outcomes</span></div>'
        f'</div>'
    )

    css = """
<style>
  .loop-stats { display:grid; grid-template-columns:repeat(4, 1fr); gap:var(--s3); margin-bottom:var(--s4); }
  .loop-stat { background:var(--panel); border:1px solid var(--line); border-radius:var(--r2); padding:var(--s3) var(--s4); display:flex; flex-direction:column; gap:4px; }
  .loop-stat .ls-val { font-family:var(--fm); font-size:32px; font-weight:600; color:var(--ink); font-variant-numeric:tabular-nums; }
  .loop-stat .ls-lbl { font-family:var(--fm); font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--steel); }

  .lp-wrap { background:var(--panel); border:1px solid var(--line); border-radius:var(--r2); padding:var(--s35) var(--s3) var(--s2); }
  .lp-axis { position:relative; height:18px; margin: 0 0 8px 130px; border-bottom:1px solid var(--line); }
  .lp-mark { position:absolute; transform:translateX(-50%); font-family:var(--fm); font-size:10px; color:var(--steel); top:0; }
  .lp-mark::after { content:""; position:absolute; left:50%; top:14px; width:1px; height:4px; background:var(--line); }

  .lp-row { display:grid; grid-template-columns:130px 1fr 110px; gap:var(--s3); align-items:center; padding:6px 0; border-bottom:1px solid color-mix(in srgb, var(--line) 60%, transparent); transition:background .12s; }
  .lp-row:hover { background:color-mix(in srgb, var(--acc) 4%, transparent); }
  .lp-row:last-child { border-bottom:none; }

  .lp-tk { display:flex; flex-direction:column; gap:2px; }
  .lp-tkname { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); letter-spacing:.04em; }
  .lp-tkmeta { font-family:var(--fm); font-size:10px; color:var(--steel); letter-spacing:.04em; }

  .lp-track { position:relative; height:18px; background:linear-gradient(to right, color-mix(in srgb, var(--line) 30%, transparent), color-mix(in srgb, var(--line) 60%, transparent), color-mix(in srgb, var(--line) 30%, transparent)); border-radius:9px; }
  .lp-track .ev { position:absolute; top:50%; transform:translate(-50%, -50%); border-radius:50%; }
  .lp-track .ev-pred { width:9px; height:9px; }
  .lp-track .ev-pred.open { background:var(--panel); border:1.5px solid var(--ink); }
  .lp-track .ev-pred.acc { background:var(--acc); }
  .lp-track .ev-pred.bear { background:var(--bear); }
  .lp-track .ev-pred.steel { background:var(--steel); }
  .lp-track .ev-out { width:5px; height:5px; background:var(--ink); opacity:.5; }
  .lp-track .ev-dec { width:8px; height:8px; transform:translate(-50%, -50%) rotate(45deg); border-radius:1px; }
  .lp-track .ev-dec.acc { background:var(--acc); }
  .lp-track .ev-dec.bear { background:var(--bear); }
  .lp-track .ev:hover { box-shadow:0 0 0 4px color-mix(in srgb, var(--acc) 25%, transparent); z-index:5; cursor:help; }

  .lp-stats { display:flex; align-items:center; gap:8px; justify-content:flex-end; font-family:var(--fm); font-size:12px; }
  .lp-resolved { color:var(--steel); font-variant-numeric:tabular-nums; }
  .lp-badge { font-family:var(--fm); font-size:11px; font-weight:600; padding:2px 8px; border-radius:99px; border:1px solid currentColor; font-variant-numeric:tabular-nums; }
  .lp-badge.acc { color:var(--acc); }
  .lp-badge.warn { color:var(--warn); }
  .lp-badge.bear { color:var(--bear); }
  .lp-badge.muted { color:var(--steel); opacity:.6; }

  .lp-legend { display:flex; gap:18px; margin-top:var(--s3); padding-top:var(--s2); border-top:1px solid var(--line); font-family:var(--fm); font-size:11px; color:var(--steel); flex-wrap:wrap; }
  .lp-legend-item { display:flex; align-items:center; gap:6px; }
  .lp-leg-dot { display:inline-block; width:10px; height:10px; border-radius:50%; }
  .lp-leg-dot.open { background:var(--panel); border:1.5px solid var(--ink); }
  .lp-leg-dot.acc { background:var(--acc); }
  .lp-leg-dot.bear { background:var(--bear); }
  .lp-leg-dot.dec { transform:rotate(45deg); border-radius:1px; }
</style>
"""

    legend = (
        '<div class="lp-legend">'
        '<div class="lp-legend-item"><span class="lp-leg-dot open"></span> Open prediction</div>'
        '<div class="lp-legend-item"><span class="lp-leg-dot acc"></span> Correct</div>'
        '<div class="lp-legend-item"><span class="lp-leg-dot bear"></span> Incorrect</div>'
        '<div class="lp-legend-item"><span class="lp-leg-dot dec acc"></span> Buy decision</div>'
        '<div class="lp-legend-item"><span class="lp-leg-dot dec bear"></span> Sell/trim decision</div>'
        '<div class="lp-legend-item">Brier badge: green &lt;0.20, amber &lt;0.25, red &ge;0.25</div>'
        '</div>'
    )

    return (
        f'{css}'
        f'<div class="ph3" style="margin-top:var(--s5)" data-tip="Per-ticker provenance timeline -- 60d window. Signals -> predictions -> decisions -> outcomes.">Loop &mdash; provenance timeline</div>'
        f'{stats}'
        f'<div class="lp-wrap">'
        f'<div class="lp-axis">{"".join(axis_marks)}</div>'
        f'{"".join(rows_html)}'
        f'{legend}'
        f'</div>'
    )



def _signaux() -> str:
    try:
        s24 = _q("SELECT COUNT(*) FROM signals WHERE timestamp > datetime('now','-1 day')")[0][0]
        s30 = _q("SELECT COUNT(*) FROM signals WHERE timestamp > datetime('now','-30 day')")[0][0]
        n8k = _q("SELECT COUNT(*) FROM filings_8k_log WHERE filed_at > datetime('now','-60 day')")[0][0]
    except Exception as e:
        return f'<section data-page="methode" role="region" aria-label="Method"><div class="phead"><h2>Method</h2></div>{_err(e)}</section>'

    sevcls = {"HIGH": "danger", "MEDIUM": "warn", "MED": "warn", "LOW": "calm"}
    sev_order = (
        "CASE UPPER(COALESCE(severity,'')) WHEN 'HIGH' THEN 0 "
        "WHEN 'MEDIUM' THEN 1 WHEN 'MED' THEN 1 WHEN 'LOW' THEN 2 ELSE 3 END"
    )
    try:
        tally = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "INCONNU": 0}
        for sev, cnt in _q(
            "SELECT UPPER(COALESCE(severity,'')), COUNT(*) FROM filings_8k_log "
            "WHERE filed_at > datetime('now','-60 day') GROUP BY UPPER(COALESCE(severity,''))"
        ):
            key = sev if sev in ("HIGH", "MEDIUM", "LOW") else ("MEDIUM" if sev == "MED" else "INCONNU")
            tally[key] += int(cnt)
        tally_str = " &middot; ".join(f"{c} {k}" for k, c in tally.items() if c) or "&mdash;"
        rows8k = ""
        # Filter book : 8-K externes au book = bruit (user mandate 02/06).
        for tk, sev, codes, reason, filed in _q(
            "SELECT ticker, COALESCE(severity,''), COALESCE(item_codes,''), COALESCE(severity_reason,''), filed_at "
            "FROM filings_8k_log WHERE filed_at > datetime('now','-60 day') "
            "  AND ticker IN (SELECT DISTINCT ticker FROM positions "
            "                  UNION SELECT DISTINCT ticker FROM portfolio_targets) "
            "ORDER BY " + sev_order + ", filed_at DESC LIMIT 12"
        ):
            su = str(sev).upper()
            cls = sevcls.get(su, "calm")
            disp = su if su in ("HIGH", "MEDIUM", "LOW") else ("MEDIUM" if su == "MED" else "INCONNU")
            raw = (str(reason) or str(codes)) or "&mdash;"
            label = raw if len(raw) <= 52 else raw[:52].rsplit(" ", 1)[0] + "&hellip;"
            rows8k += (
                f'<div class="row"><div class="rt"><span class="tk tkc" data-tk="{tk}">{tk}</span>'
                f'<span class="tag {cls}">{disp}</span></div>'
                f'<div class="rs"><span>{label}</span><span class="mono">{str(filed)[:10]}</span></div></div>'
            )
        eightk = rows8k or (
            '<div class="empty">'
            '<span class="empty-ico">8</span>'
            '<b>No 8-K filing</b>'
            'No SEC regulatory filings over 60d.'
            '<span class="hint">Se remplit avec acquisitions, departures CEO, materiel events</span>'
            '</div>'
        )
    except Exception as e:
        eightk, tally_str = _err(e), "&mdash;"

    try:
        rowsib = ""
        # Filter book : insider clusters external = bruit (user mandate 02/06).
        for tk, det, buyers, buym, strength in _q(
            "SELECT ticker, detected_at, COALESCE(distinct_buyers,0), COALESCE(total_buy_m,0), COALESCE(cluster_strength,'') "
            "FROM insider_buy_clusters_log "
            "WHERE ticker IN (SELECT DISTINCT ticker FROM positions "
            "                 UNION SELECT DISTINCT ticker FROM portfolio_targets) "
            "ORDER BY detected_at DESC LIMIT 8"
        ):
            rowsib += (
                f'<div class="row"><div class="rt"><span class="tk tkc" data-tk="{tk}">{tk}</span>'
                f'<span class="tag acc2">{strength or "&mdash;"}</span></div>'
                f'<div class="rs"><span>{int(buyers)} acheteurs &middot; {float(buym):.1f}M$</span>'
                f'<span class="mono">{str(det)[:10]}</span></div></div>'
            )
        insiders = (
            rowsib
            or '<div class="empty" style="padding:var(--s4) 0">no clustered buy detected</div>'
        )
    except Exception as e:
        insiders = _err(e)

    try:
        nsrc = _q("SELECT COUNT(*) FROM sources")[0][0]
        # #72 + #75 : Brier mesure rolling 180j par source (calibration empirique).
        # Pre-J-day, N=0 -> badge "—". Post-J+30, badge OK/WARN/ALERT visible.
        brier_by_src: dict[str, dict] = {}
        try:
            from intelligence.calibration_audit import compute_brier_by_source
            cx = sqlite3.connect(DB, uri=True)
            try:
                cx.row_factory = sqlite3.Row
                brier_data = compute_brier_by_source(cx, days=180)
            finally:
                cx.close()
            brier_by_src = {b["source_name"]: b for b in brier_data}
        except Exception:
            brier_by_src = {}

        src_rows = ""
        for name, cred, n in _q(
            "SELECT name, credibility, COALESCE(n_signals,0) FROM sources ORDER BY credibility DESC, n_signals DESC LIMIT 10"
        ):
            cv = float(cred or 0)
            col = "acc2" if cv >= 0.65 else ("warn" if cv >= 0.45 else "calm")
            # Brier badge si dispo
            b_info = brier_by_src.get(name)
            if b_info and b_info["status"] != "INSUFFICIENT_DATA":
                b_cls = {"OK": "acc", "WARN": "warn", "ALERT": "bear"}.get(b_info["status"], "")
                b_badge = (
                    f' <span class="tag {b_cls}" '
                    f'title="Brier {b_info["brier_avg"]:.2f} sur {b_info["n_resolved"]} resolutions">'
                    f'B={b_info["brier_avg"]:.2f}</span>'
                )
            elif b_info:
                b_badge = (
                    f' <span class="tag" title="N={b_info["n_resolved"]} insuffisant">'
                    f'B=—</span>'
                )
            else:
                b_badge = ''
            src_rows += (
                f'<div class="row"><div class="rt"><span class="tk">{str(name)[:24]}</span>'
                f'<span class="tag {col}">{cv:.2f}</span>{b_badge}</div>'
                f'{_tbar(cv * 100, title=f"credibility {cv:.2f}")}'
                f'<div class="rs"><span>credibility a priori</span><span class="mono">{int(n)} signaux</span></div></div>'
            )
    except Exception as e:
        src_rows, nsrc = _err(e), 0

    # === Star Signaux : verdict activite + 3 KPIs flow + tally severite ===
    # Verdict activite 24h : ACTIF si s24 >= 5, sinon CALME (seuil approximatif
    # ajuste si besoin avec backlog reel observe).
    if s24 >= 5:
        _act_cls, _act_lbl, _act_cap = "warn", "ACTIVE", f"{s24} incoming signals 24h"
    elif s24 >= 1:
        _act_cls, _act_lbl, _act_cap = "", "MOD&Eacute;R&Eacute;", f"{s24} signal(aux) 24h &middot; flux normal"
    else:
        _act_cls, _act_lbl, _act_cap = "acc", "CALME", "none signal 24h"
    star_strate_act = (
        '<div class="ps-strate">'
        + '<div class="ps-lbl">Signal activity 24h</div>'
        + '<div class="ps-macro-row">'
        + f'<div class="ps-val {_act_cls}">{_act_lbl}</div>'
        + f'<div class="ps-macro-meta">{_act_cap}</div>'
        + "</div>"
        + "</div>"
    )
    star_strate_kpis = (
        '<div class="ps-strate ps-grid">'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Incoming signals over last 24h via Gmail (analyst newsletters) + EDGAR (8-K and insider Form 4).">Signaux 24&nbsp;h</div><div class="ps-val">{s24}</div><div class="ps-cap">Gmail + EDGAR</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Total signal volume ingested over rolling 30 days. Used to judge overall activity.">Signals 30d</div><div class="ps-val">{s30}</div><div class="ps-cap">rolling window</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Regulatory 8-K filings over 60 days (material SEC changes). Tally shows HIGH/MEDIUM/LOW severity breakdown.">8-K &middot; 60&nbsp;j</div><div class="ps-val">{n8k}</div><div class="ps-cap">{tally_str}</div></div>'
        + "</div>"
    )
    star_strate_foot = (
        '<div class="ps-strate ps-foot">'
        + f'{nsrc} active sources &middot; credibility recalibration 1st of month'
        + "</div>"
    )
    star_signaux = (
        f'<div class="page-star">{star_strate_act}{star_strate_kpis}{star_strate_foot}</div>'
    )
    cols = (
        f'<div class="cols">'
        f'<div class="col"><div class="colhead"><span class="t">Recent 8-K</span><span class="a">{tally_str}</span></div><div class="card">{eightk}</div></div>'
        f'<div class="col"><div class="colhead"><span class="t">Source credibility</span><span class="a">{nsrc} sources &middot; recal 1st of month</span></div><div class="card">{src_rows}</div></div>'
        f"</div>"
    )
    insider_flow = _insider_flow_strip_html()
    insider_flow_strip = (
        f'<div class="colhead spaced"><span class="t">Insider flow &middot; 7&nbsp;j</span>'
        f'<span class="a">aggregated net buy/sell &middot; &#9733; = en portefeuille</span></div>'
        f'<div class="card pad">{insider_flow}</div>'
    )
    # Clusters strip : montre seulement si non-empty (insider_buy_clusters_log
    # actuellement vide, s'affichera quand cluster detection fire).
    empty_clusters_msg = "no clustered buy"
    insider_clusters_strip = ""
    if empty_clusters_msg not in insiders:
        insider_clusters_strip = (
            f'<div class="colhead spaced"><span class="t">Clustered buys</span>'
            f'<span class="a">60&nbsp;j &middot; Form 4 EDGAR</span></div>'
            f'<div class="card pad">{insiders}</div>'
        )
    # Track record + sante distribution remontes ici (depuis vue d'ensemble)
    # 01/06 user pref : la page signaux groupe le pilotage qualite des signaux
    # (track record + 6 vigilances + 8-K + insider flux).
    # Performance + data_health deplaces ici 07/06 user pref :
    # - Performance ffn = retro-test pro-forma (sum(qty_actuelle x prix_historique)),
    #   pas track record reel -> a sa place en Method, pas Vue d'ensemble.
    # - Data health = M1 freshness des inputs (instrumentation), audience
    #   methodologique -> Method, pas verite-du-jour.
    performance_html_method = _performance_panel()
    data_health_html_method = _data_health_panel()
    return (
        f'<section data-page="methode" role="region" aria-label="Method"><div class="phead"><h2>Method</h2>'
        f'<div class="sub">How the bot reads signals + how it monitors your biases &middot; track record &middot; insider flow &middot; loop provenance</div></div>'
        f"{star_signaux}{_track_record_panel()}{_distribution_health_panel()}{cols}{insider_flow_strip}{insider_clusters_strip}"
        f"{_discipline_biais_panel()}"
        f"{data_health_html_method}"
        f"{performance_html_method}"
        f"{_loop()}"
        f"</section>"
    )


# Chip labels canoniques pour macro_book_warnings (Positions + Theses).
# Source UNIQUE (06/06 v2 readability) : pas de duplication par panel.
_RULE_CHIP_LABELS = {
    "R1_semis_concentration": "SEMIS",
    "R2_carry_unwind_jp": "JP FX",
    "R3_growth_tech_dominance": "GROWTH",
    "R4_auto_ev_stress": "AUTO",
    "R5_complacent_hedge": "HEDGE",
}


# 06/06 architecture : _MACRO_BANDS + _MACRO_TIPS desormais loaded depuis
# config/calibration.yaml via shared.calibration. Source unique canonique
# evolutive (audit refresh tous les 10j via Phase B cron).
from shared.calibration import (
    get_all_bands as _calib_get_all_bands,
    get_all_tooltips as _calib_get_all_tooltips,
)

_MACRO_BANDS: dict[str, tuple[float, float, bool]] = _calib_get_all_bands()
_MACRO_TIPS: dict[str, str] = _calib_get_all_tooltips()


def _macro_dot(ind: str, v: float, phase: int | None = None) -> str:
    """Couleur du point macro -- TOUJOURS l'une des 3 : calm / warn / danger.

    Pas de "mute" : user 02/06 "green yellow and red". Donnee absente
    (no band + no phase) -> defaut WARN (yellow) car incertain = posture
    prudente, jamais vert silencieux.

    Priorite : (1) bands locales level-based (VIX/HY_OAS/...), (2) phase
    stockee par composite V3 (Gold/BankReserves/...), (3) fallback warn.
    """
    band = _MACRO_BANDS.get(ind)
    if band is not None:
        warn, danger, hi_bad = band
        if hi_bad:
            return "danger" if v >= danger else ("warn" if v >= warn else "calm")
        return "danger" if v <= danger else ("warn" if v <= warn else "calm")
    if phase is not None:
        try:
            p = int(phase)
        except Exception:
            return "warn"
        if p >= 4:
            return "danger"
        if p == 3:
            return "warn"
        if p in (1, 2):
            return "calm"
    return "warn"


# === Equity internals: RSI(14) + Breadth (RSP/SPY) — cache TTL 30min ===
_RSI_CACHE: dict[str, float | None] = {}
_RSI_CACHE_TS: dict[str, float] = {}
_RSI_TTL = 1800.0


def _rsi_14(ticker: str) -> float | None:
    """RSI(14) daily via gateway canonique prices.get_price_window.

    Migration 08/06 (Phase 4 bypass yfinance) : ne fetche plus yfinance
    localement, consomme le gateway unique shared.prices.get_price_window.
    Cache 30min conservé (le gateway throttle via _PRICE_CACHE de prices.py).

    Algorithme RSI(14) inchangé : rolling mean gain/loss sur 14 closes.
    """
    import time as _t
    from datetime import UTC, datetime, timedelta

    now = _t.time()
    if ticker in _RSI_CACHE and now - _RSI_CACHE_TS.get(ticker, 0) < _RSI_TTL:
        return _RSI_CACHE[ticker]
    try:
        from shared.prices import get_price_window
        # yfinance history(start, end) est END-EXCLUSIVE -> on passe today+1
        # pour inclure le close du jour, comme period="2mo" l'ancien comportement.
        today = datetime.now(UTC).date()
        end = today + timedelta(days=1)
        start = today - timedelta(days=70)
        window = get_price_window(ticker, start, end)
        if len(window) < 15:
            _RSI_CACHE[ticker] = None
            _RSI_CACHE_TS[ticker] = now
            return None
        # window est list[(date_str, close_float)] -> extraire closes en pd.Series
        import pandas as pd
        closes = pd.Series([c for _, c in window]).dropna()
        if len(closes) < 15:
            _RSI_CACHE[ticker] = None
            _RSI_CACHE_TS[ticker] = now
            return None
        delta = closes.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-10)
        rsi: float | None = float((100 - 100 / (1 + rs)).iloc[-1])
    except Exception:
        rsi = None
    _RSI_CACHE[ticker] = rsi
    _RSI_CACHE_TS[ticker] = now
    return rsi


def _market_rsi() -> str:
    """4 lignes RSI : SPY, QQQ, SMH, IWM avec data-tip + couleurs OB/OS."""
    import html as _h

    tickers = [
        ("SPY", "S&P 500", "Momentum S&P 500. > 70 sur-achete (correction probable), < 30 sur-vendu (rebond probable)."),
        ("QQQ", "Nasdaq 100", "Momentum Nasdaq 100 (tech). Plus proche du book."),
        ("SMH", "Semis", "Momentum semis (exposition AI_compute). > 75 = zone de prise de profit, < 30 = zone de renforcement."),
        ("IWM", "Russell 2000", "Petites capitalisations. Si IWM decroche pendant que SMH monte, la hausse est etroite."),
    ]
    rows = ""
    for tk, name, tip in tickers:
        rsi = _rsi_14(tk)
        if rsi is None:
            num, dot, tag = "n/a", "mute", ""
        else:
            num = f"{rsi:.1f}"
            if rsi >= 80 or rsi <= 20:
                dot, tag = "danger", ("OB" if rsi >= 80 else "OS")
            elif rsi >= 70 or rsi <= 30:
                dot, tag = "warn", ("OB" if rsi >= 70 else "OS")
            else:
                dot, tag = "calm", ""
        tip_attr = f' data-tip="{_h.escape(tip, quote=True)}"'
        tag_html = f'<span class="dp">{tag}</span>' if tag else '<span class="dp"></span>'
        rows += (
            f'<div class="drow"{tip_attr}><span class="ddot {dot}"></span>'
            f'<span class="dname">{name} <span style="color:var(--steel);font-size:14px">({tk})</span></span>'
            f'<span class="dval {dot}">{num}</span>{tag_html}</div>'
        )
    return rows


def _breadth_rsp_spy() -> str:
    """Breadth: ratio RSP/SPY vs MA50. Baisse = mega-caps portent seuls, fragile."""
    import html as _h

    fallback = '<div class="drow"><span class="ddot mute"></span><span class="dname">RSP / SPY ratio</span><span class="dval mute">n/a</span><span class="dp"></span></div>'
    try:
        # Migration Phase 4 #4 : gateway canonique prices.get_price_window
        # au lieu de yfinance.Ticker direct. -2 bypasses yfinance.
        # Note end-exclusive : end=today+1 pour inclure today (cf finding #3).
        from datetime import UTC, datetime, timedelta

        import pandas as pd

        from shared.prices import get_price_window

        today = datetime.now(UTC).date()
        end = today + timedelta(days=1)
        start = today - timedelta(days=100)  # ~3mo en daily (équiv period="3mo")
        rsp_window = get_price_window("RSP", start, end)
        spy_window = get_price_window("SPY", start, end)
        rsp = pd.Series([c for _, c in rsp_window]).dropna()
        spy = pd.Series([c for _, c in spy_window]).dropna()
        if len(rsp) < 50 or len(spy) < 50:
            return fallback
        # Aligner par taille : prend la plus petite des deux (closes alignées
        # ordre chronologique sur même calendrier de trading)
        n = min(len(rsp), len(spy))
        rsp = rsp.iloc[-n:].reset_index(drop=True)
        spy = spy.iloc[-n:].reset_index(drop=True)
        ratio = (rsp / spy).dropna()
        if len(ratio) < 50:
            return fallback
        cur = float(ratio.iloc[-1])
        ma50 = float(ratio.tail(50).mean())
        delta_pct = (cur - ma50) / ma50 * 100
    except Exception:
        return fallback
    if delta_pct >= 1.0:
        dot, tag = "calm", "LARGE"
    elif delta_pct <= -2.0:
        dot, tag = "danger", "&Eacute;TROIT"
    elif delta_pct <= -0.5:
        dot, tag = "warn", "&Eacute;TROIT"
    else:
        dot, tag = "calm", ""
    tip = "Equal-weight (RSP) vs cap-weighted (SPY). > MA50 = broad rally (healthy). < MA50 = isolated mega-caps (fragile)."
    tip_attr = f' data-tip="{_h.escape(tip, quote=True)}"'
    return (
        f'<div class="drow"{tip_attr}><span class="ddot {dot}"></span>'
        f'<span class="dname">RSP / SPY ratio <span style="color:var(--steel);font-size:14px">vs MM50</span></span>'
        f'<span class="dval {dot}">{delta_pct:+.2f}%</span><span class="dp">{tag}</span></div>'
    )


def _urgence(_watch: str, near: int, positions: list[dict], pnl: dict, _elan: str = "", near_t: int = 0) -> str:
    debt_map = {
        # Tier 1: Marché & liquidité — alertes en haut, crédit/peur/FX/sentiment, hedge en bas
        "TYX": (1, "US 30Y rate (%)", 4, False),
        "USDJPY": (1, "USD/JPY", 2, False),
        "HY_OAS": (1, "Spread HY (bp)", 2, False),
        "VIX": (1, "VIX", 2, False),
        "DXY": (1, "Dollar (DXY)", 2, False),
        "BTC_drawdown180": (1, "BTC drawdown 6M (%)", 1, False),
        "Gold": (1, "Or ($/oz)", 0, True),
        # Tier 2: Stress bancaire & liquidité Fed — signaux avancés en haut, plomberie milieu, slow bas
        # RepoSRF retire 02/06 -- replace par BankReserves (ADR 006 audit : ON RRP ambigu post-QT).
        "MOVE": (2, "Bond vol (MOVE)", 2, False),
        "T10Y2Y": (2, "10Y-2Y slope (%)", 4, False),
        "BankReserves": (2, "Fed bank reserves ($M)", 0, True),
        "KRE": (2, "Regional banks ($)", 2, False),
        "CopperGold": (2, "Copper/gold ratio", 4, False),
        # Tier 3: Macro lente -- canonical V3 names (CPI/MfgIP raw legacy supprimes 02/06)
        "CoreCPI": (3, "Core inflation (%)", 4, False),
        "MfgIP_yoy": (3, "Industrial production (%)", 4, False),
        "FedBalance_yoy": (3, "Bilan Fed YoY (%)", 1, False),
    }
    # tnames retire (Phase C bucket triage remplace tier grouping). Tier_short
    # chip preserve l'origine sur chaque row via le mapping inline plus bas.
    try:
        sig = _q(
            "SELECT indicator_name, value, phase, timestamp FROM debt_signals WHERE id IN (SELECT MAX(id) FROM debt_signals GROUP BY indicator_name) ORDER BY timestamp DESC"
        )
    except Exception:
        sig = []
    import datetime as _dt

    _today = _dt.date.today()
    _STALE = {1: 3, 2: 10, 3: 40, 9: 10}  # tolerance jours: daily / hebdo / mensuel
    import html as _html_esc

    _pos = {k: i for i, k in enumerate(debt_map.keys())}
    _dot_priority = {"danger": 0, "warn": 1, "calm": 2, "mute": 3}
    bucket_rows: dict[str, list[tuple]] = {}
    # Phase A : capture readings pour classify_regime apres la boucle.
    readings_for_regime: dict[str, dict] = {}
    for ind, val, phase, ts in sig:
        tier, label, dec, thou = debt_map.get(ind, (9, ind, 2, False))
        # L3 etat honnete : val=NULL -> "no data", pas 0.0 affiche en vert.
        data_missing = val is None
        if data_missing:
            num = "&mdash;"
            dot = "mute"
            vcls = "mute"
        else:
            v = float(val)
            num = f"{v:,.{dec}f}" if thou else f"{v:.{dec}f}"
            dot = _macro_dot(ind, v, phase)
            vcls = dot  # user 02/06 "green yellow red only"
        ph = int(phase or 1)
        try:
            _age = (_today - _dt.date.fromisoformat(str(ts)[:10])).days
        except Exception:
            _age = 0
        is_stale = (not data_missing) and _age > _STALE.get(tier, 10)
        if data_missing:
            badge = '<span class="nodata">no data</span>'
        elif is_stale:
            badge = f'<span class="stale">stale {_age}d</span>'
        else:
            badge = ""
        tip = _MACRO_TIPS.get(ind, "")
        tip_attr = f' data-tip="{_html_esc.escape(tip, quote=True)}"' if tip else ""
        # Stale/no-data ranges apres fresh de meme dot (focus visuel sur donnees actuelles).
        _stale_rank = 1 if (data_missing or is_stale) else 0
        sort_key = (_dot_priority.get(dot, 9), _stale_rank, _pos.get(ind, 999), ind)
        # Tier chip pour preserver l'origine du signal (M&L / BANK / SLOW) malgre
        # le regroupement par bucket de stress.
        _tier_short = {1: "M&amp;L", 2: "BANK", 3: "SLOW", 9: "OTH"}.get(tier, "?")
        tier_chip = f'<span class="dtchip">{_tier_short}</span>'
        row_html = (
            f'<div class="drow"{tip_attr}><span class="ddot {dot}"></span>'
            f'<span class="dname">{label}{tier_chip}</span>'
            f'<span class="dval {vcls}">{num}</span><span class="dp">P{ph}</span>{badge}</div>'
        )
        # Bucket de triage : ACT NOW > WATCH > ASLEEP > SILENT (no-data/stale-mute).
        bucket = (
            "act" if dot == "danger"
            else "watch" if dot == "warn"
            else "silent" if dot == "mute"
            else "asleep"
        )
        bucket_rows.setdefault(bucket, []).append((sort_key, row_html))
        # Phase A : feed classify_regime input. NULL values -> None.
        readings_for_regime[ind] = {
            "indicator": ind,
            "value": None if data_missing else float(val),
            "dot": dot,
        }
    # Render buckets in stress order. Headers incluent count chip + intent line.
    _BUCKET_META = [
        ("act", "ACT NOW", "bear", "stress materiel, posture defensive maintenant"),
        ("watch", "WATCH", "warn", "borderline, suivre direction sur 7j"),
        ("asleep", "CALM", "steel", "zone calme, pas d'action requise"),
        ("silent", "SILENT", "steel", "donnee absente/stale, non-decidable"),
    ]
    blocks_parts = []
    for _bkey, _blabel, _bcls, _btip in _BUCKET_META:
        _brows = bucket_rows.get(_bkey, [])
        if not _brows:
            continue
        _bcount = len(_brows)
        _btip_attr = f' data-tip="{_html_esc.escape(_btip, quote=True)}"'
        blocks_parts.append(
            f'<div class="dbucket dbucket-{_bkey}"{_btip_attr}>'
            f'<span class="dbucket-lbl {_bcls}">{_blabel}</span>'
            f'<span class="dbucket-count">{_bcount}</span>'
            f'</div>'
        )
        blocks_parts.append("".join(h for _, h in sorted(_brows)))
    blocks = "".join(blocks_parts)
    # Diagnostic counts (utilise par Phase A regime detector + close ritual).
    _bucket_counts = {k: len(v) for k, v in bucket_rows.items()}
    try:
        comp = _q("SELECT score, phase FROM debt_composite ORDER BY timestamp DESC LIMIT 1")
    except Exception:
        comp = []
    score, cphase = (float(comp[0][0] or 0), int(comp[0][1] or 1)) if comp else (0.0, 1)
    # Phase A : classify_regime + chip dans le header. Decouple du V3 score
    # (V3 exploratoire, biais centriste). Regime = confluence rules deterministe.
    _regime_label = "RISK_ON"
    try:
        from intelligence.macro_regime import classify_regime
        _reg = classify_regime(readings_for_regime)
        _regime_label = _reg["regime"]
        _REGIME_COLOR = {
            "COMPLACENT": "warn",  # melt-up risk, attention
            "RISK_ON": "calm",
            "LATE_CYCLE": "warn",
            "FRAGILE": "warn",
            "STRESS": "bear",
        }
        _reg_cls = _REGIME_COLOR.get(_reg["regime"], "steel")
        _reg_tip = _html_esc.escape(
            f"Regime: {_reg['regime']}. Triggers: {', '.join(_reg['triggers'])}. "
            f"Buckets: ACT {_reg['danger_count']} / WATCH {_reg['warn_count']} / "
            f"CALM {_reg['asleep_count']} / SILENT {_reg['silent_count']}. "
            f"Source: classify_regime deterministe (independant V3 composite, demote 02/06).",
            quote=True,
        )
        _regime_chip_html = (
            f'<span class="regime-chip regime-{_reg_cls}" data-tip="{_reg_tip}">'
            f'&middot; {_reg["regime"].replace("_", " ")}</span>'
        )
    except Exception:
        # Fallback silencieux : presentation layer ne doit pas crasher le dashboard.
        _regime_chip_html = ""
    # 06/06 Phase A canonical : chip audit metadata (date last audit + version).
    try:
        from shared.calibration import get_audit_metadata
        _amd = get_audit_metadata()
        _audit_last = _amd.get("last_audit", "?")
        _audit_ver = _amd.get("audit_version", "?")
        _audit_next = _amd.get("next_audit_due", "?")
        _audit_report = _amd.get("audit_report", "?")
        _audit_tip = _html_esc.escape(
            f"Calibration {_audit_ver} — last audit {_audit_last}. "
            f"Next audit due {_audit_next} (cron 10j Phase B). "
            f"Source: config/calibration.yaml. Rapport: {_audit_report}.",
            quote=True,
        )
        _audit_chip_html = (
            f'<span class="audit-chip" data-tip="{_audit_tip}">'
            f'calib {_audit_ver} &middot; {_audit_last}</span>'
        )
    except Exception:
        _audit_chip_html = ""
    # Phase B : tie-to-book warnings (regime x book composition).
    try:
        from intelligence.macro_book_warnings import compute_book_warnings
        _ind_vals = {
            k: (v.get("value") if isinstance(v, dict) else None)
            for k, v in readings_for_regime.items()
        }
        _warnings = compute_book_warnings(_regime_label, positions, _ind_vals)
    except Exception:
        _warnings = []
    if _warnings:
        _SEV_CLS = {"high": "bear", "med": "warn", "low": "steel"}
        _warn_rows = []
        for _w in _warnings:
            _sev_cls = _SEV_CLS.get(_w["severity"], "steel")
            _tk_str = " &middot; ".join(_w["tickers"][:5]) if _w["tickers"] else ""
            _why_safe = _html_esc.escape(_w["rationale"], quote=True)
            _warn_rows.append(
                f'<div class="bookwarn-row" data-tip="{_why_safe}">'
                f'<span class="bookwarn-sev {_sev_cls}">{_w["severity"].upper()}</span>'
                f'<span class="bookwarn-action">{_html_esc.escape(_w["action"])}</span>'
                f'<span class="bookwarn-tk">{_tk_str}</span>'
                f'</div>'
            )
        _book_warnings_html = (
            '<div class="bookwarn-block" data-tip="Confluence regime macro x composition book courante. '
            'Regles deterministes (no LLM). Hover chaque row pour le rationale complet.">'
            '<div class="bookwarn-hdr">Macro impact on book</div>'
            + "".join(_warn_rows)
            + '</div>'
        )
    else:
        _book_warnings_html = ""
    # Macro composite sparkline 30 derniers points
    try:
        _macro_hist = [r[0] for r in _q(
            "SELECT score FROM debt_composite ORDER BY timestamp DESC LIMIT 30"
        )]
        _macro_hist.reverse()
    except Exception:
        _macro_hist = []
    if len(_macro_hist) >= 2:
        _mh_lo, _mh_hi = min(_macro_hist), max(_macro_hist)
        _mh_rng = (_mh_hi - _mh_lo) or 1.0
        _mh_w, _mh_h, _mh_pad = 240, 18, 2
        _mh_pts = []
        for _i, _v in enumerate(_macro_hist):
            _mx = _mh_pad + (_i / max(1, len(_macro_hist) - 1)) * (_mh_w - 2 * _mh_pad)
            _my = _mh_pad + (_mh_h - 2 * _mh_pad) - ((_v - _mh_lo) / _mh_rng) * (_mh_h - 2 * _mh_pad)
            _mh_pts.append(f"{_mx:.1f},{_my:.1f}")
        _mh_color = "var(--warn)" if _macro_hist[-1] >= _macro_hist[0] else "var(--acc)"
        _mh_last_x, _mh_last_y = _mh_pts[-1].split(",")
        _macro_sparkline = (
            f'<svg class="ps-macro-spark" viewBox="0 0 {_mh_w} {_mh_h}" width="{_mh_w}" height="{_mh_h}" '
            f'style="overflow:visible">'
            f'<polyline points="{" ".join(_mh_pts)}" fill="none" stroke="{_mh_color}" '
            f'stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{_mh_last_x}" cy="{_mh_last_y}" r="2" fill="{_mh_color}"/>'
            f'</svg>'
        )
    else:
        _macro_sparkline = ""
    _rk = _cfg().get("risk", {})
    _vthr = _rk.get("vol_scaling_threshold_vix", 21)
    _vsf = _rk.get("vol_scaling_factor", 0.7)
    # 06/06 v5 audit pro : 2-tier scaling (convention CTA QuantPedia).
    # VIX > 30 = panique reelle -> factor 0.5 (halve exposure).
    try:
        from shared.calibration import get_drawdown_thresholds
        _dd_calib = get_drawdown_thresholds()
        _vthr_panic = float(_dd_calib.get("vol_scaling_vix_panic_threshold") or 30.0)
        _vsf_panic = float(_dd_calib.get("vol_scaling_vix_panic_factor") or 0.5)
    except Exception:
        _vthr_panic, _vsf_panic = 30.0, 0.5
    _vix = next((float(v or 0) for i, v, p, t in sig if i == "VIX"), None)
    _panic = _vix is not None and _vix >= _vthr_panic
    _reduced = _vix is not None and _vix >= _vthr
    if _panic:
        _sfac = _vsf_panic
        _size_msg = f"VIX {_vix:.1f} &ge; {_vthr_panic:.0f} PANIC (sizing x{_vsf_panic:.1f})"
    elif _reduced:
        _sfac = _vsf
        _size_msg = f"VIX {_vix:.1f} &ge; {_vthr} stress (sizing x{_vsf:.1f})"
    else:
        _sfac = 1.0
        _size_msg = f"VIX {_vix:.1f} &lt; {_vthr} normal (sizing x1.0)" if _vix is not None else "VIX indisponible"
    # Sizing 2-tier : warn zone (VIX > vthr) + panic zone (VIX > panic threshold).
    # Convention CTA QuantPedia 2026 + BIS papers. Decouple de la frise V3.
    size_txt = _size_msg
    # Frise macro V3 (task #42 portage 01/06) : formule debt_monitor avec 3
    # transformations structurelles (BTC_drawdown180 / FedBalance_yoy / MfgIP
    # P4 -5%).
    #
    # STATUT (cf docs/decision_logs/02_macro_v3_holdout_strict.md) : V3 a
    # ECHOUE le HOLDOUT strict 4/8 (02/06/2026). Biais centriste P2
    # structurel : V3 ne genere JAMAIS de P1 (3/3 dates calmes -> P2) et
    # sous-estime certains P3 (oct 2018 -> P2). DEMOTE a 'exploratoire' /
    # NON VALIDEE OOS. V4 a venir avec changement structurel. La frise est
    # affichee comme indicatif, taguee "exploratoire" pour respecter L3
    # (etat honnete > contenu invente).
    _PHASE_LBL = {1: "STABLE", 2: "STRESS", 3: "ALERTE", 4: "CRISE"}
    _PHASE_COL = {1: "acc", 2: "warn", 3: "warn", 4: "bear"}
    clabel = _PHASE_LBL.get(cphase, "INCONNU")
    _conc = []
    for _c in _cluster_health(positions, pnl):
        if _c["breached"]:
            _ov = f"{_c['over_eur']:,.0f}".replace(",", "&#8239;")
            _conc.append(f"trim {_c['name']} &middot; +{_ov}&#8239;&euro;")
    _phase_col = _PHASE_COL.get(cphase, "steel")
    # Tally indicateurs par phase (responsive : on voit combien d'indicateurs
    # contribuent a chaque niveau de stress, pas juste le score agrege).
    _phase_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for _ind, _val, _ph, _ts in sig:
        try:
            _pi = int(_ph) if _ph is not None else 0
        except Exception:
            _pi = 0
        if _pi in _phase_counts:
            _phase_counts[_pi] += 1
    # Top stressor : indicateur en phase >= 3 avec le plus fort phase. Surface
    # le name lisible (debt_map) pour que l'user voie quel signal allume la frise.
    _non_none = [(_i, _v, int(_p)) for _i, _v, _p, _t in sig if _p is not None]
    _top_stressor_html = ""
    if _non_none:
        _worst = max(_non_none, key=lambda r: r[2])
        if _worst[2] >= 3:
            _wlabel = debt_map.get(_worst[0], (9, _worst[0], 2, False))[1]
            _cls = "bear" if _worst[2] >= 4 else "warn"
            _top_stressor_html = (
                f'<div class="ps-stressor">top stressor: '
                f'<b class="{_cls}">{_wlabel}</b> &middot; phase {_worst[2]}/4</div>'
            )
    # Delta composite vs reading precedente -> direction (improving/worsening).
    _delta_html = ""
    try:
        _deltq = _q("SELECT score FROM debt_composite ORDER BY timestamp DESC LIMIT 2")
        if len(_deltq) == 2:
            _prev = float(_deltq[1][0] or 0)
            _diff = score - _prev
            if abs(_diff) >= 1:
                _arr = "&uarr;" if _diff > 0 else "&darr;"
                _cls = "bear" if _diff > 0 else "acc"
                _delta_html = f' <span class="ps-delta {_cls}">{_arr}{abs(_diff):.0f}</span>'
    except Exception:
        pass
    # Strate 1 : etat macro + frise STRESS pleine largeur + tag exploratoire
    # (cf decision_log 02 -- V3 demote, V4 a venir).
    star_macro = (
        '<div class="ps-strate">'
        + '<div class="ps-lbl" data-tip="V3 composite macro phase (debt_monitor). STATUS: exploratory -- strict HOLDOUT 4/8 (02/06). V3 never generates P1 (centrist bias). Do not drive decisions on this value. V4 forthcoming (cf decision_log 02).">Macro state <span class="ps-tag-explor">exploratory</span></div>'
        + '<div class="ps-macro-row">'
        + f'<div class="ps-val {_phase_col}">{clabel}</div>'
        + f'<div class="ps-macro-meta">phase {cphase}/4 &middot; indice {score:.0f}{_delta_html}</div>'
        + "</div>"
        + '<div class="ps-frise-wrap">'
        + f'<div class="ps-frise"><div class="ps-frise-mark" style="left:{(cphase - 0.5) * 25:.0f}%"></div></div>'
        + '<div class="ps-frise-labs" data-tip="Macro regime scale (V3 debt_monitor composite, exploratory). STABLE = calm vol + tight spreads + risk-on. STRESS = rising vol or widening credit, no panic. ALERT = clear deterioration, defensive posture warranted. CRISIS = full risk-off, large drawdowns, severe credit/vol stress.">'
        + '<span>stable</span><span>stress</span><span>alert</span><span>crisis</span>'
        + '</div>'
        + '<div class="ps-frise-tally" data-tip="Distribution courante des indicateurs sous-jacents par phase. Si P3+P4 montent, la frise va vers la droite. Permet de voir lesquels contribuent au stress sans cliquer dans le panneau d\'indicateurs.">'
        + f'<span class="ps-tally-cell"><span class="ps-tally-dot ph1"></span>P1 {_phase_counts[1]}</span>'
        + f'<span class="ps-tally-cell"><span class="ps-tally-dot ph2"></span>P2 {_phase_counts[2]}</span>'
        + f'<span class="ps-tally-cell"><span class="ps-tally-dot ph3"></span>P3 {_phase_counts[3]}</span>'
        + f'<span class="ps-tally-cell"><span class="ps-tally-dot ph4"></span>P4 {_phase_counts[4]}</span>'
        + '</div>'
        + '</div>'
        + f'{_top_stressor_html}'
        + f'{_macro_sparkline}'
        + "</div>"
    )
    # Strate 2 : 3 cellules (frictions, targets, stops)
    if _conc:
        f_cls, f_val, f_lbl, f_cap = "bear", len(_conc), "FRICTIONS", _conc[0]
    else:
        f_cls, f_val, f_lbl, f_cap = "acc", 0, "ALIGNED", "concentration under caps"
    t_cap = "margin remaining OK" if near_t else "nothing close to target"
    s_cls = "bear" if near else "acc"
    s_cap = "to watch" if near else "calm"
    star_grid = (
        '<div class="ps-strate ps-grid">'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Correlated cluster whose cumulative position exceeds cap = action recommended.">{f_lbl}</div><div class="ps-val {f_cls}">{f_val}</div><div class="ps-cap">{f_cap}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Positions ≥75% along entry -> target path. Take-profit zone to watch.">Targets &ge;75%</div><div class="ps-val">{near_t}</div><div class="ps-cap">{t_cap}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Positions less than 10% from their stop. Low margin, check before session.">Stops &lt;10%</div><div class="ps-val {s_cls}">{near}</div><div class="ps-cap">{s_cap}</div></div>'
        + "</div>"
    )
    # Strate 3 : footer technique (VIX + sizing)
    star_foot = (
        '<div class="ps-strate ps-foot">'
        + f'{size_txt} &middot; sizing <b>&times;{_sfac:.1f}</b>'
        + "</div>"
    )
    star = f'<div class="page-star">{star_macro}{star_grid}{star_foot}</div>'
    rsi_html = _market_rsi()
    breadth_html = _breadth_rsp_spy()
    return (
        f'<section data-page="urgence" role="region" aria-label="Alerts"><div class="phead"><h2>Alerts</h2>'
        f'</div>'
        f"{star}"
        # Layout 02/06 user "organize, evitons les trous" : macro stress
        # full-width au-dessus (indicateurs naturellement nombreux), puis
        # RSI + breadth cote-a-cote en bas.
        f'<div class="ph3">Macro stress monitor &mdash; score {score:.0f} {_regime_chip_html} {_audit_chip_html}</div>'
        f'<div class="card pad" style="margin-bottom:var(--s4)"><div class="dlist"><style>.ddot.mute{{background:var(--steel);box-shadow:none;opacity:.6}}</style>{blocks}</div>{_book_warnings_html}</div>'
        f'<div class="cols">'
        f'<div><div class="ph3">Market momentum &middot; RSI(14) daily &middot; 30min cache</div>'
        f'<div class="card pad"><div class="dlist">{rsi_html}</div></div></div>'
        f'<div><div class="ph3">Market breadth &middot; participation</div>'
        f'<div class="card pad"><div class="dlist">{breadth_html}</div></div></div>'
        f"</div></section>"
    )


def _tape_8k() -> str:
    sevcls = {"HIGH": "neg", "MEDIUM": "warn", "MED": "warn", "LOW": "pos"}
    try:
        # Filter book : tape8k externes au book = bruit (user mandate 02/06).
        rows = _q(
            "SELECT ticker, COALESCE(severity,''), COALESCE(severity_reason,''), COALESCE(item_codes,''), filed_at "
            "FROM filings_8k_log WHERE filed_at > datetime('now','-60 day') "
            "  AND ticker IN (SELECT DISTINCT ticker FROM positions "
            "                 UNION SELECT DISTINCT ticker FROM portfolio_targets) "
            "ORDER BY filed_at DESC LIMIT 18"
        )
    except Exception:
        return ""
    if not rows:
        return ""
    items = ""
    for tk, sev, reason, codes, _filed in rows:
        cls = sevcls.get(str(sev).upper(), "")
        raw = (str(reason) or str(codes)) or ""
        # E4 craft 31/05 : retrait truncature "..." -- 1/3 des news etaient
        # coupees, lisibilite degradee. Le ticker scrolle horizontal de toute
        # facon, longueur libre. Title= en bonus si CSS overflow cache encore.
        items += f'<span class="ti" title="{raw}"><span class="tk tkc" data-tk="{tk}">{tk}</span> <span class="{cls}">8-K</span> {raw}</span>'
    return f'<div class="tape tape8k"><div class="track2">{items}{items}</div></div>'


def _rail_foot(near: int, heat: float) -> str:
    try:
        row = _q("SELECT score, phase FROM debt_composite ORDER BY rowid DESC LIMIT 1")
        score, phase = row[0] if row else (None, None)
    except Exception:
        score, phase = None, None
    if near == 0 and heat < 33:
        posture, tone = "CALME", "calm"
    elif heat < 60 and near <= 1:
        posture, tone = "VIGILANCE", "warn"
    else:
        posture, tone = "D&Eacute;FENSIF", "alert"
    macro = ""
    if score is not None:
        dcol = {1: "var(--acc)", 2: "var(--warn)", 3: "var(--warn)", 4: "var(--bear)"}.get(int(phase or 1), "var(--bear)")
        macro = f'<span class="rfmacro" style="background:{dcol}" title="Macro phase {int(phase or 1)}"></span>'
    return (
        f'<div class="rfoot" title="Portefeuille {posture} &middot; surchauffe {heat:.0f}&deg; &middot; {near} marge(s) faible(s)">'
        f'<span class="statedot {tone}"></span>'
        f'<span class="rfm">{heat:.0f}&deg;</span>'
        f'<span class="rfm">{near}&#9888;</span>'
        f"{macro}</div>"
    )


def _sizing_overcap(positions: list[dict], conv_by_tk: dict, caps: dict, pnl: dict) -> list[str]:  # noqa: ARG001
    """Lignes dont le poids courant depasse leur cap de conviction (signal de TAILLE, prix-agnostique)."""
    vtot = sum(p["weight"] for p in positions) or 1
    over = []
    for p in positions:
        wv = p["weight"] / vtot * 100
        cap = caps.get(conv_by_tk.get(p["ticker"]))
        if cap and wv > cap * 100:
            over.append((wv - cap * 100, p["ticker"]))
    return [tk for _, tk in sorted(over, reverse=True)]


def _pi(n: int, tks: list, lab: str, cls: str) -> str:
    nm = " &middot; ".join(tks[:3]) + ("&hellip;" if len(tks) > 3 else "")
    return f'<div class="pi {cls}"><span class="pn">{n}</span><span class="pl">{lab}</span><span class="pt">{nm or "&mdash;"}</span></div>'


def _cockpit() -> str:
    """Cockpit vitals: surfaces discipline gaps at top of dashboard.
    Read-only. Aggregates from decisions + predictions + RECONCILE_FLAGS.
    Display-only; no behavior change."""
    from datetime import date

    dec_30d = _q("SELECT count(*) FROM decisions WHERE created_at > datetime('now','-30 days')")[0][0]
    preds_due = _q("SELECT count(*) FROM predictions WHERE resolved_at IS NULL AND target_date < '2026-06-11'")[0][0]
    panic = _q(
        "SELECT count(*) FROM decisions "
        "WHERE LOWER(COALESCE(bias_tags,'')) LIKE '%panic%' "
        "OR LOWER(COALESCE(decision_type,'')) LIKE '%panic%'"
    )[0][0]

    jun10 = date(2026, 6, 10)
    days_to_jun10 = (jun10 - date.today()).days

    drift_count = len(RECONCILE_FLAGS)
    drift_sub = (
        "; ".join(f"{f['ticker']} ~{int(f['drift_eur'])} EUR" for f in RECONCILE_FLAGS) if drift_count else "none"
    )

    INK, WARN, DANGER = "var(--ink)", "var(--warn)", "var(--bear)"

    if dec_30d < 2:
        dec_color, dec_sub = DANGER, "under-fed journal"
    elif dec_30d < 5:
        dec_color, dec_sub = WARN, "feed le journal"
    else:
        dec_color, dec_sub = INK, f"{dec_30d} dec. / 30d"

    drift_color = WARN if drift_count else INK
    panic_color = INK if panic == 0 else DANGER
    panic_sub = "KPI #4 tenu" if panic == 0 else f"KPI #4 broken ({panic})"

    if days_to_jun10 <= 3:
        cd_color = DANGER
    elif days_to_jun10 <= 7:
        cd_color = WARN
    else:
        cd_color = INK

    if days_to_jun10 > 0:
        countdown, countdown_sub = f"J-{days_to_jun10}", f"10/06 &middot; {preds_due} pred. resolve"
    elif days_to_jun10 == 0:
        countdown, countdown_sub = "TODAY", f"{preds_due} pred. resolve"
    else:
        countdown, countdown_sub = f"J+{-days_to_jun10}", f"batch past &middot; {preds_due} en retard"

    css = (
        "<style>"
        ".ck-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:var(--s3);margin-top:var(--s2)}"
        ".ck-cell{padding:var(--s35) 4px;border-bottom:1px solid var(--line)}"
        ".ck-label{font-size:15px;color:var(--steel);letter-spacing:.01em}"
        ".ck-num{font-family:var(--fm);font-size:25px;font-weight:500;margin-top:var(--s15);line-height:1.05;letter-spacing:-.01em}"
        ".ck-sub{font-size:15px;color:var(--steel);margin-top:var(--s15);line-height:1.4}"
        "</style>"
    )

    def cell(label: str, value: str, sub: str, color: str) -> str:
        return (
            f'<div class="ck-cell">'
            f'<div class="ck-label">{label}</div>'
            f'<div class="ck-num" style="color:{color}">{value}</div>'
            f'<div class="ck-sub">{sub}</div>'
            f"</div>"
        )

    cells = (
        cell("Decisions logged &middot; 30d", str(dec_30d), dec_sub, dec_color)
        + cell("Batch Brier", countdown, countdown_sub, cd_color)
        + cell(
            "Book reconciliation", f"{drift_count} position{'s' if drift_count > 1 else ''}", drift_sub, drift_color
        )
        + cell("Panic sells core", str(panic), panic_sub, panic_color)
    )

    return css + f'<div class="ck-grid">{cells}</div>'


def _journal() -> str:
    try:
        rows = _q("SELECT created_at, ticker, decision_type, reasoning FROM decisions ORDER BY created_at DESC LIMIT 6")
    except Exception:
        return ""
    if not rows:
        return ""
    tmap = {
        "entry": "Entry",
        "scale_in": "Renforcement",
        "partial_exit": "Trim",
        "full_exit": "Sortie",
        "override": "Override",
        "no_action_flag": "Documented no-action",
    }
    out = ""
    for created, tk, dtype, reason in rows:
        lab = tmap.get(dtype, str(dtype))
        parts = str(created)[:10].split("-")
        d = f"{parts[2]}.{parts[1]}" if len(parts) == 3 else str(created)[:10]
        rs = str(reason or "")[:80].replace("&", "&amp;").replace("<", "&lt;")
        out += (
            f'<div class="line"><span><span class="mono">{tk}</span> &middot; {lab}'
            f'<span class="nm">{rs}</span></span><span class="mono">{d}</span></div>'
        )
    return out


# Brand mark PRESAGE : star 4 points + flare horizontal + 7 signal dots fading.
# Source = dashboard/static/brand/presage_symbol.svg (user-provided 01/06).


def _cycle_chip_cls_via_vocab(phase: str) -> str:
    """Adoption vocabulary canonique : retourne la CSS class pour un cycle chip.

    Doctrine : CYCLE_EARLY/MID/LATE/CONTRACTION sont tous STATE dans le
    vocabulary -> earns_attention=False TOUJOURS. Un STATE n'attire JAMAIS
    l'oeil (cf SPEC_ALERT_VOCABULARY §1). Donc tous les phases cycle ->
    classe calme (steel-mute), pas warn/bear/acc qui crient.

    C'est la cure du "mur de rouge" : avant, "late" -> warn (orange criant),
    "contraction" -> bear (rouge alarme) -- alors que ces phases sont du
    CONTEXTE, pas des alarmes. La doctrine delta-pas-etat exige que l'oeil
    n'accroche que sur EVENT (delta) + FLAG actif + STEER act-class.

    Fallback "steel-mute" si phase non-mappee (cf STATE non-declare = pas
    de fabrication panel-locale, mais ici fallback safe pour pas casser
    l'affichage sur phases legacy).
    """
    from shared.alert_vocabulary import attention_earning, get_word
    phase_norm = phase.upper().replace("-", "_")
    try:
        word = get_word(f"CYCLE_{phase_norm}")
        if not attention_earning(word):
            # STATE -> calme, contexte (cf SPEC §1 regle d'attention)
            return "steel-mute"
        # Safety : si un cycle chip etait declaré attention-earning, fallback warn
        # (mais le yaml force false pour tous CYCLE_*)
        return "warn"
    except KeyError:
        # Phase non-mappee (legacy ou faute frappe) -> calme par défaut
        return "steel-mute"


_TIER_LABEL = {
    5: "Conviction 5 &middot; highest",
    4: "Conviction 4",
    3: "Conviction 3 &middot; median",
    2: "Conviction 2",
    1: "Conviction 1 &middot; faibles",
}


def _theses(names: dict, sectors: dict, positions: list, pnl: dict) -> str:
    "Page Theses : asymetrie target/stop par conviction + gap target partielle."
    import html as _h_th
    # 06/06 : connect Theses panel a shared/sectors + macro_state +
    # macro_book_warnings. Chaque thesis affiche cycle phase + warning chips.
    try:
        from shared.sectors import cycle_phase_for_ticker as _cp_for
    except Exception:
        def _cp_for(_t: str) -> str:
            return "unknown"
    _th_warnings = _ticker_warnings_map(positions)
    # Cure racine 09/06 : book_idx pour migration _position_axis_price (5 repères
    # EUR axe-ouvert). Tue le bug visuel dot collé bord droit sur BEYOND.
    try:
        from shared import book as _bk_th
        _book_idx_th_inner = _bk_th.get_book_index()
    except Exception:
        _book_idx_th_inner = {}
    # _CP_CLS_TH mort -- remplace par _cycle_chip_cls_via_vocab (#117 vocabulary)
    rows = _q(
        "SELECT ticker, conviction, direction, entry_price, stop_price, target_full, "
        "target_partial, last_price FROM theses WHERE status='active' "
        "ORDER BY conviction DESC, ticker"
    )
    if not rows:
        return (
            '<section data-page="theses" role="region" aria-label="Theses"><div class="phead"><h2>Theses</h2>'
            '<div class="sub">none thesis active</div></div></section>'
        )
    _u = _cfg().get("universe", {})
    crypto_tk = set(_u.get("core", {}).get("crypto_core", [])) | set(_u.get("extended", {}).get("crypto_etfs", []))
    ths = []
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    n_missing = n_near_tgt = n_near = n_profit = 0
    for r in rows:
        tk, conv, direction, entry, stop, tgt, tpart, last = r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]
        conv = int(conv or 0)
        if conv in dist:
            dist[conv] += 1
        if not tpart:
            n_missing += 1
        # Bug fix 31/05 wave 9 : stop_price + target_full sont stockes en
        # NATIVE currency (cf [[currency-native-invariant]]). Comparer a un
        # current_price EUR donnait des % absurdes (4063.T target +23876% etc.).
        # Native vs native -> ratios FX-invariants corrects.
        current = _cached_price_native(tk) or last or entry
        d_stop = d_tgt = ratio = frac = entry_frac = pnl_e = None
        # Canonical position gauge requires entry/stop/target/current.
        # _position_axis helper builds the bar a partir de ces 4 valeurs raw.
        has_bar = bool(current and stop and tgt and tgt != stop and entry)
        if has_bar:
            d_stop = abs(stop - current) / current * 100
            d_tgt = abs(tgt - current) / current * 100
            ratio = d_tgt / d_stop if d_stop else None
            frac = max(0.0, min(100.0, (current - stop) / (tgt - stop) * 100))
            entry_frac = max(0.0, min(100.0, (entry - stop) / (tgt - stop) * 100))
            # Fix "tout d'un bloc" 08/06 : remplacer compute_perf_thesis_pct
            # (perf vs entry native -- divergeait du P&L broker car FX historique
            # different du fx_now) par le P&L canonique broker (pnl.get(tk) =
            # pnl_position_pct_eur via avg_cost_eur). UNE SEULE source de verite
            # partout dans le dashboard. Plus de "perf depuis entry" qui creait
            # confusion avec le P&L broker.
            pnl_e = pnl.get(tk)
            if d_tgt is not None and d_tgt < 12:
                n_near_tgt += 1
            if d_stop < 10:
                n_near += 1
            # Fix bug 31/05 : "EN GAIN 27/27" trompeur. La KPI doit refleter
            # le PnL REEL de la position user (cours vs avg_cost = cost basis
            # actuel), pas le PnL "depuis ecriture de la thèse" qui est
            # quasi-toujours positif (l'user ecrit ses theses pres du bottom).
            # pnl dict est calcule par compute_pnl_pct(positions) en amont :
            # pnl[tk] = (current_eur - avg_cost_eur) / avg_cost_eur * 100
            pnl_real = pnl.get(tk)
            if pnl_real is not None and pnl_real >= 0:
                n_profit += 1
        # Thesis-frame natif (target posé en natif, FX-clean) : les 4 valeurs
        # entry/stop/target/current restent en native currency du ticker.
        # Money-invariant L28 : JAMAIS mix entry_native + current_eur (= +176056%
        # SK Hynix natif KRW). Les ratios KPI d_stop/d_tgt/ratio/frac (calculés
        # ci-dessus en native) restent FX-invariants. Aucune conversion ici.
        _entry_g, _stop_g, _tgt_g, _cur_g = entry, stop, tgt, current
        ths.append(
            {
                "tk": tk,
                "conv": conv,
                "dir": (direction or "long"),
                "nm": names.get(tk, tk),
                "d_stop": d_stop,
                "d_tgt": d_tgt,
                "ratio": ratio,
                "frac": frac,
                "entry_frac": entry_frac,
                "pnl_e": pnl_e,
                "has_bar": has_bar,
                "cat": sectors.get(tk, ""),
                "tpart": tpart,
                "_entry": _entry_g if has_bar else None,
                "_stop": _stop_g if has_bar else None,
                "_tgt": _tgt_g if has_bar else None,
                "_cur": _cur_g if has_bar else None,
            }
        )
    n = len(ths)
    med = sorted(t["conv"] for t in ths)[n // 2]
    c5_pct = dist[5] / n * 100
    infl = c5_pct > 20

    # Distribution by conviction : inline string dans la strate hero
    # (panel separe + bar chart elimines 03/06 user : pas de panel-pour-5-counts.
    # L'info vit dans le foot de la strate Convictions, point.)
    _dist_inline = " &middot; ".join(f"c{c} <b>{dist[c]}</b>" for c in (5, 4, 3, 2, 1))
    infl_msg = (
        f"&#9888; conviction inflation: c5 = {c5_pct:.0f}% (threshold 20%)"
        if infl
        else f"c5 = {c5_pct:.0f}% &middot; no inflation (threshold 20%)"
    )

    # === Star Theses : conviction mediane + 3 cells (targets, gain, marges) ===
    pcls = "acc" if n_profit * 2 >= n else "bear"
    ncls = "bear" if n_near else "acc"
    _tg_cls = "acc" if n_near_tgt else ""
    _conv_lbl = f"MEDIAN c{med}"
    _conv_cap = f"{n} active thesis(es) &middot; {dist[5]} c5 ({c5_pct:.0f}%)"
    if infl:
        _conv_cls = "warn"
    elif med >= 4:
        _conv_cls = "acc"
    else:
        _conv_cls = ""
    hero = (
        f'<div class="page-star">'
        f'<div class="ps-strate ps-grid">'
        f'<div class="ps-cell"><div class="ps-lbl" data-tip="Theses whose current position is less than 12% from target_full. Take-profit zone.">Closer to target</div><div class="ps-val {_tg_cls}">{n_near_tgt}</div><div class="ps-cap">margin &lt; 12%</div></div>'
        f'<div class="ps-cell"><div class="ps-lbl" data-tip="Theses whose current price is above thesis entry cost (entry_price).">In profit</div><div class="ps-val {pcls}">{n_profit}/{n}</div><div class="ps-cap">price &gt; entry cost</div></div>'
        f'<div class="ps-cell"><div class="ps-lbl" data-tip="Theses less than 10% from stop. Critical zone to review.">Low margins</div><div class="ps-val {ncls}">{n_near}</div><div class="ps-cap">margin &lt; 10% from stop</div></div>'
        f'</div>'
        f'<div class="ps-strate"><div class="ps-lbl">Convictions</div>'
        f'<div class="ps-macro-row"><div class="ps-val {_conv_cls}">{_conv_lbl}</div>'
        f'<div class="ps-macro-meta">{_conv_cap}</div></div>'
        f'<div class="ps-cap">{_dist_inline}</div>'
        f'<div class="ps-cap">{infl_msg}</div></div>'
        f'</div>'
    )
    # Panel "Distribution by conviction" supprime 03/06 user : info inline
    # dans la strate Convictions ci-dessus. Pas de card pour 5 nombres.
    kpis = ""

    gap = ""

    vtot = sum(p["weight"] for p in positions) or 1
    vmap = {p["ticker"]: p["weight"] / vtot * 100 for p in positions}
    _caps = _CFG.get("concentration", {}).get("line_cap_by_conviction", {})
    _sumcaps = sum(_caps.get(t["conv"], 0.0) for t in ths if vmap.get(t["tk"], 0.0) > 0) or 1.0
    groups = ""
    for c in (5, 4, 3, 2, 1):
        tier = [t for t in ths if t["conv"] == c]
        secw: dict[str, float] = {}
        for _t in tier:
            secw[_t["cat"]] = secw.get(_t["cat"], 0.0) + vmap.get(_t["tk"], 0.0)
        grp = sorted(tier, key=lambda t: (-secw.get(t["cat"], 0.0), t["cat"] or "~~~", -vmap.get(t["tk"], 0.0)))
        if not grp:
            continue
        _tgt_tier = (_caps.get(c, 0) / _sumcaps * 100) if _caps.get(c) else None
        _tgt_lab = f" &middot; target {_tgt_tier:.1f}%/position" if _tgt_tier else ""
        groups += f'<div class="th-grp">{_TIER_LABEL.get(c, "Conviction " + str(c))} &middot; {len(grp)}{_tgt_lab}</div><div class="th-grid">'
        for t in grp:
            if t["has_bar"]:
                # Theses panel : UN SEUL MÈTRE — % depuis cost (cf _position_axis_pct).
                _tk_th = t["tk"]
                _gp_th = _gauge_pcts_from_cost(_book_idx_th_inner.get(_tk_th)) if _book_idx_th_inner else {}
                if _gp_th and _gp_th.get("dot_pct") is not None:
                    _pa = _position_axis_pct(
                        _gp_th.get("stop_pct"),
                        _gp_th.get("target_pct"),
                        _gp_th.get("dot_pct"),
                        pnl_position_pct=_gp_th.get("dot_pct"),
                    )
                else:
                    # Fallback legacy natif
                    _entry_v, _cur_v = t["_entry"], t["_cur"]
                    _perf_e = ((_cur_v / _entry_v - 1) * 100.0) if (_entry_v and _cur_v and _entry_v != 0) else None
                    _pa = _position_axis(_entry_v, t["_stop"], t["_tgt"], _cur_v,
                                         pnl_position_pct=_perf_e)
                bar = f'<div class="th-bar">{_pa}</div>' if _pa else '<div class="th-na">incomplete price data</div>'
            else:
                bar = '<div class="th-na">incomplete price data</div>'
            anchor = ""
            # #114 fix : "Position in profit" doit utiliser le P&L POSITION reel
            # (pnl.get(tk) = pnl_position_pct depuis avg_cost EUR, fx-correct),
            # PAS la perf these (t["pnl_e"] depuis entry_price native). Les
            # deux baselines divergent enormement sur les winners tenus avant
            # formalisation de la these (AMD: perf these +21% vs pnl position +218%).
            # Le message parle de la POSITION -> utiliser le PnL position.
            _pnl_position_pct = pnl.get(t["tk"])
            if t["has_bar"] and _pnl_position_pct is not None:
                _crypto = t["tk"] in crypto_tk
                if _pnl_position_pct >= 12 and not _crypto:
                    _acls = "acc"
                    _amsg = "Position in profit, upside margin remaining."
                    anchor = f'<div class="th-anchor {_acls}" style="grid-column:1/-1">{_amsg}</div>'
            cat_html = f'<span class="th-cat">{t["cat"]}</span>' if t["cat"] else ""
            wv = vmap.get(t["tk"], 0.0)
            _cap = _caps.get(t["conv"])
            sizebar = ""
            adj = ""
            if wv <= 0:
                wtxt = "&mdash;"
            elif _cap:
                _tgt = _cap / _sumcaps * 100
                _cappct = _cap * 100
                _heat = max(0.0, min((wv - _tgt) / (_cappct - _tgt), 1.0)) if _cappct > _tgt else 0.0
                _hue = 150 - 125 * _heat
                _lt = 0.60 + 0.20 * (_hue / 150)
                wtxt = f'<span style="color:oklch({_lt:.2f} 0.22 {_hue:.0f})">{wv:.1f}%</span>'
                # Sizebar redesign 02/06 user "bump -> tend vers vert optimal".
                # Target = 50% visuel (zone verte optimale). 0% = no position
                # (rouge -- under), 100% = cap exceeded (rouge -- over).
                # Marker en green zone => action en cours est bonne; marker
                # en red zone => correction necessaire.
                if wv <= _tgt:
                    _w_pos = (wv / _tgt) * 50.0 if _tgt > 0 else 0.0
                else:
                    extra = wv - _tgt
                    span = _cappct - _tgt if _cappct > _tgt else 1.0
                    _w_pos = 50.0 + min(50.0, extra / span * 50.0)
                _w_pos = max(0.0, min(100.0, _w_pos))
                # P2 canon : tick a 50% target + dot pour position weight.
                _w_dot_cls = "bear" if _w_pos < 25 or _w_pos > 75 else ("acc" if 40 < _w_pos < 60 else "")
                sizebar = _tbar(
                    _w_pos,
                    ticks=[(50.0, "target")],
                    dot_color=_w_dot_cls,
                    title=f"weight {wv:.1f}% / target {_tgt:.1f}%",
                    extra_class="sizebar",
                )
                _d = wv - _tgt
                _v = abs(_d) / 100 * vtot
                _de = f"{_v / 1000:.1f}k" if _v >= 1000 else f"{round(_v / 50) * 50:.0f}"
                if _d > 0.4:
                    _tail = f" &middot; &gt; cap {_cappct:.0f}%" if wv > _cappct else ""
                    adj = f'<div class="th-adj trim">trim &minus;{_de}&nbsp;&euro;{_tail}</div>'
                elif _d < -0.4:
                    adj = f'<div class="th-adj add">bump +{_de}&nbsp;&euro;</div>'
                else:
                    adj = '<div class="th-adj ok">&check; on weight</div>'
            else:
                wtxt = f"{wv:.1f}%"
            # Cycle phase chip via vocabulary canonique (#117 -- adoption STATE calme).
            # Avant : _CP_CLS_TH mappait late->warn / contraction->bear, faisant
            # CRIER des STATE (mur de rouge). Maintenant via vocabulary : un
            # STATE n'attire jamais l'oeil -> classe calme partout.
            _cp_th = _cp_for(t["tk"])
            _cp_cls_th = _cycle_chip_cls_via_vocab(_cp_th)
            _cp_chip_th = (
                f'<span class="cycle-chip cycle-{_cp_cls_th}" '
                f'data-tip="Cycle phase {_cp_th} (config/sectors.yaml).">{_cp_th}</span>'
                if _cp_th != "unknown" else ""
            )
            _tw_chips_th = ""
            # Signaux per-ticker une fois par row (orthogonal macro warnings).
            try:
                from shared.ticker_outlook import outlook_phrase as _op_th, recent_outlook as _ro_th
                _outlook_th = _op_th(_ro_th(t["tk"]))
            except Exception:
                _outlook_th = ""
            for _tw in _th_warnings.get(t["tk"], [])[:3]:
                _rid = _tw.get("rule_id", "?")
                _sev = _tw.get("severity", "med")
                _sev_cls = {"high": "bear", "med": "warn", "low": "steel"}.get(_sev, "steel")
                _label = _RULE_CHIP_LABELS.get(_rid, _rid.split("_")[0])
                _action = _tw.get("action", "").rstrip(".")
                _why = _tw.get("rationale", "").rstrip(".")
                _tip = f"{_action}.\n\n{_why}.\n\n{_outlook_th}" if _outlook_th else f"{_action}.\n\n{_why}."
                _tw_chips_th += (
                    f'<span class="warn-chip warn-chip-{_sev_cls}" '
                    f'data-tip="{_h_th.escape(_tip, quote=True)}">{_label}</span>'
                )
            groups += (
                f'<div class="th-row" data-tk="{t["tk"]}">'
                f'<div class="th-id"><span class="th-conv c{t["conv"]}">c{t["conv"]}</span>'
                f'<span class="th-tk">{t["nm"]}</span>{cat_html}{_cp_chip_th}{_tw_chips_th}</div>'
                f'<div class="th-w">{wtxt}</div><div class="th-szcol">{sizebar}{adj}</div>{bar}{anchor}</div>'
            )
        groups += "</div>"

    return (
        '<section data-page="theses" role="region" aria-label="Theses"><div class="phead"><h2>Theses</h2>'
        '<div class="sub">Target/stop asymmetry, by conviction level</div></div>'
        f"{_TH_CSS}{hero}{kpis}{gap}{groups}</section>"
    )



# Direction esthetique #37 -- cahier de bord instrument (Bloomberg / cockpit).
# Override CSS active via body.cahier-de-bord (toggle JS).





_PERF_CACHE: dict = {}
_PERF_TTL = 840


def _perf_dwm(ticker: str) -> dict:
    """% sur dernieres 24h / semaine / mois via gateway canonique.

    Migration Phase 4 #5 : daily close-to-close via prices.get_price_window
    (gateway unique). Simplification convention-wide : "d" devient daily
    close-to-close (close[-1] vs close[-2]) aligné avec _dp_pct (panneau
    voisin TOP MOVERS). Plus de fetch intraday 1h yfinance — la part
    intraday "24h rolling vrai" est sacrifiée pour la cohérence convention
    (matche broker/Yahoo daily%, cf finding _dp_pct).

    "d" = close jour J vs close jour J-1 (daily approximation canonique
    Yahoo/Robinhood "Today").
    "w" = close[-1] vs close[-6] (~5 jours business)
    "m" = close[-1] vs close[0] (~21 jours business sur 1mo window)
    """
    import time
    from datetime import UTC, datetime, timedelta

    now = time.monotonic()
    hit = _PERF_CACHE.get(ticker)
    if hit and now - hit[0] < _PERF_TTL:
        return dict(hit[1])
    out: dict = {"d": None, "w": None, "m": None}
    try:
        from shared.prices import get_price_window

        today = datetime.now(UTC).date()
        end = today + timedelta(days=1)  # end-exclusive cf finding #3
        # period="1mo" yfinance utilise relativedelta(months=1) :
        # 2026-06-08 - 1mo = 2026-05-08 (pas 2026-05-07). Pour matcher exactement
        # cette sémantique calendar-month, on utilise dateutil.relativedelta.
        # Finding #5 iter 3 : today-32d donnait 2026-05-07 (1 jour de trop) →
        # closes[0] inclut un close supplémentaire → "m" diverge ×2.5.
        from dateutil.relativedelta import relativedelta
        start = today - relativedelta(months=1)
        window = get_price_window(ticker, start, end)
        if len(window) >= 2:
            closes = [c for _, c in window]
            last = float(closes[-1])
            out["d"] = round((last / float(closes[-2]) - 1) * 100, 1)
            out["m"] = round((last / float(closes[0]) - 1) * 100, 1)
            if len(closes) >= 6:
                out["w"] = round((last / float(closes[-6]) - 1) * 100, 1)
    except Exception:
        pass
    _PERF_CACHE[ticker] = (now, out)
    return out


def _universe_status() -> dict:
    # Statut de chaque ticker depuis config.yaml: watch / core / extended (held gere ailleurs).
    out: dict = {}
    try:
        import yaml

        cfg = yaml.safe_load(Path("config.yaml").read_text())
        uni = (cfg or {}).get("universe", {}) or {}
        for grp in (uni.get("core", {}) or {}).values():
            for tk in grp or []:
                out[tk] = "core"
        for grp in (uni.get("extended", {}) or {}).values():
            for tk in grp or []:
                out[tk] = "extended"
        for tk in uni.get("watch", []) or []:
            out[tk] = "watch"
    except Exception:
        pass
    return out


def _smart_summary(content: str, max_chars: int = 500) -> str:
    """Extrait juste l'activite + position marche du content.

    Strip le prefix "SECTION HEADER - " (BUSINESS QUALITY -, etc.), prend le
    1er paragraphe au sentence boundary le plus proche de max_chars. Si pas
    de boundary propre, hard-cut au dernier mot complet.

    L'analyse complete reste accessible via /analyze TICKER ou chat
    "analyse TICKER".
    """
    if not content:
        return ""
    s = content.strip()
    # Strip leading section header pattern : "[A-Z _]+ - "
    m = re.match(r"^[A-Z_ ]+\s*-\s+", s)
    if m:
        s = s[m.end():]
    if len(s) <= max_chars:
        return s
    snippet = s[:max_chars]
    # Last sentence boundary in the snippet (. ! ?)
    last_punct = max(
        snippet.rfind(". "),
        snippet.rfind("! "),
        snippet.rfind("? "),
    )
    if last_punct > max_chars * 0.4:
        return s[:last_punct + 1]
    # Otherwise cut at last word boundary
    last_space = snippet.rfind(" ")
    if last_space > max_chars * 0.6:
        return s[:last_space] + "…"
    return snippet + "…"


def _loupe_data(positions: list[dict], sectors: dict, names: dict, pnl: dict, computed: list[dict], perf: dict) -> dict:
    by = {r["ticker"]: r for r in computed}
    ana: dict = {}
    try:
        for tk, typ, ts, content, meta in _q(
            "SELECT ticker, COALESCE(type,''), timestamp, COALESCE(content,''), COALESCE(metadata,'') "
            "FROM analyses WHERE id IN (SELECT MAX(id) FROM analyses GROUP BY ticker)"
        ):
            scores: dict = {}
            regime: str = ""
            narr: list = []
            try:
                md = json.loads(meta) if meta else {}
                scores = md.get("scores", {}) or {}
                regime = md.get("regime_at_time", "") or ""
                narr = md.get("narratives_active", []) or []
            except Exception:
                pass
            # Drilldown : juste l'activite + position marche, pas le dump
            # multi-paragraphe (BUSINESS QUALITY + FINANCIAL HEALTH + valo + ...).
            # On extrait le 1er paragraphe propre, sentence-aware, ~500 chars max.
            exc = _smart_summary(str(content), max_chars=500)
            exc = exc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            ana[tk] = {
                "date": str(ts)[:10],
                "type": str(typ),
                "excerpt": exc,
                "scores": scores,
                "regime": str(regime),
                "narr": narr,
            }
    except Exception:
        ana = {}
    total = sum(p["weight"] for p in positions) or 1
    held = {p["ticker"] for p in positions}
    ustat = _universe_status()
    out: dict = {}
    for p in positions:
        tk = p["ticker"]
        r = by.get(tk, {})
        dn, up, rt = r.get("downside_pct"), r.get("upside_pct"), r.get("asymmetry_ratio")
        out[tk] = {
            "name": names.get(tk, ""),
            "sector": sectors.get(tk, "Sans thesis"),
            "country": _country(tk),
            "status": "held",
            "weight_eur": round(p["weight"]),
            "weight_pct": round(p["weight"] / total * 100, 1),
            "pnl": round(pnl[tk], 1) if tk in pnl else None,
            "down": round(dn, 1) if dn is not None else None,
            "up": round(up, 1) if up is not None else None,
            "ratio": round(rt, 2) if rt is not None else None,
            "perf": perf.get(tk),
            "analysis": ana.get(tk),
        }
    for tk, status in ustat.items():
        if tk in held:
            continue
        out[tk] = {
            "name": names.get(tk, ""),
            "sector": sectors.get(tk, "Sans thesis"),
            "country": _country(tk),
            "status": status,
            "weight_eur": None,
            "weight_pct": None,
            "pnl": None,
            "down": None,
            "up": None,
            "ratio": None,
            "analysis": ana.get(tk),
        }
    return out






def _broker(tk: str) -> str:
    return "bourso" if tk.endswith(_EU_SUFFIX) else "tr"


def _broker_value(p: dict, pnl: dict) -> float:  # noqa: ARG001
    return float(p["weight"])  # market value post-migration


def _sector_mix(ps: list, pnl: dict, sectors: dict) -> list:
    agg: dict[str, float] = {}
    for p in ps:
        sec = sectors.get(p["ticker"], "Sans thesis")
        agg[sec] = agg.get(sec, 0.0) + _broker_value(p, pnl)
    return sorted(agg.items(), key=lambda kv: -kv[1])


def _sector_donut(segs: list) -> str:
    """Horizontal bars list — modern Linear/Vercel pattern (replaces donut+legend)."""
    total = sum(v for _, v in segs) or 1
    if not segs:
        return ""
    sorted_segs = sorted(segs, key=lambda kv: -kv[1])
    max_pct = sorted_segs[0][1] / total * 100
    rows = []
    for label, v in sorted_segs:
        col = SECTOR_COLORS.get(label, "#6B7686")
        pct = v / total * 100
        fill_pct = pct / max_pct * 100 if max_pct else 0
        vstr = f"{v / 1000:.0f}k" if v >= 1000 else f"{v:.0f}"
        rows.append(
            f'<div class="brk-row">'
            f'<div class="brk-row-name"><span class="brk-row-dot" style="background:{col}"></span>'
            f'<span class="brk-row-label">{label}</span></div>'
            f'<div class="brk-row-bar"><div class="brk-row-fill" style="width:{fill_pct:.1f}%;background:{col}"></div></div>'
            f'<div class="brk-row-pct">{pct:.0f}%</div>'
            f'<div class="brk-row-val">{vstr}&nbsp;&euro;</div>'
            f"</div>"
        )
    return f'<div class="brk-viz"><div class="brk-bars">{"".join(rows)}</div></div>'


def _asym_format(ratio):
    """Format asymmetry_ratio avec class de coloration via doctrine vocabulary.

    Migration 08/06 (#115 fondu) : appliquer la regle d'attention canonique.
    Le ratio asymetrie est un STATE descriptif (sa valeur courante), pas un
    EVENT delta. Donc par doctrine il NE doit PAS crier (cf SPEC_ALERT_VOCABULARY §1).

    Mais l'EVENT TARGET_HIT (current >= target_full) est un DELTA (crossing) -- il
    crie legitiment (earns_attention=True dans vocabulary).

    Convention apres migration :
    - ratio >= 999   -> EVENT TARGET_HIT  -> 'num acc' (vert, attire l'oeil legitime)
    - ratio >= 3.0   -> STATE favorable    -> 'num' (calme, descriptif)
    - 1.0 <= r < 3.0 -> STATE neutre       -> 'num' (calme, descriptif)
    - r < 1.0        -> STATE defavorable  -> 'num steel-mute' (calme, descriptif)
    - None           -> '—'

    Le rouge / vert criant ('acc' favorable, 'neg' rouge defavorable) est
    REMPLACE par calme par defaut. Quand on detectera ASYM_COMPRESSION
    (EVENT delta vs t-1 dans vocabulary), CELUI-LA criera -- pas le state.
    """
    if ratio is None:
        return ('num', '&mdash;')
    if ratio >= 999:
        # TARGET_HIT : EVENT delta legitime (cross-over) -- doit crier
        return ('num acc', 'target &check;')
    # STATE descriptif -- ne crie pas, neutre/calme partout
    if ratio >= 1.0:
        return ('num', f'{ratio:.1f}&times;')
    # r < 1.0 : STATE defavorable -- AVANT rouge ('num neg'), MAINTENANT calme.
    # L'alarme sur asym defavorable viendra via EVENT ASYM_COMPRESSION
    # (delta materiel vs t-1), pas via le state actuel.
    return ('num steel-mute', f'{ratio:.1f}&times;')


def _broker_one(label: str, note: str, ps: list, grand: float, names: dict, pnl: dict, sectors: dict, asym: dict, gauges: dict | None = None, ticker_warnings: dict | None = None) -> str:
    import html as _h_esc

    from shared.book import is_proxy_price  # #128 chip valo proxy (SK Hynix KRW→EUR)
    # Cure racine 09/06 : book_idx pour migration gauge book row vers
    # _position_axis_price (5 repères EUR axe-ouvert).
    try:
        from shared import book as _bk_one
        _book_idx = _bk_one.get_book_index()
    except Exception:
        _book_idx = {}
    gauges = gauges or {}
    ticker_warnings = ticker_warnings or {}
    ps = sorted(ps, key=lambda p: -_broker_value(p, pnl))
    tot = sum(_broker_value(p, pnl) for p in ps)
    share = tot / grand * 100
    # 06/06 : cycle_phase chip canonique via shared.sectors (source unique
    # sectors.yaml, partagee avec /review handler + macro_book_warnings).
    try:
        from shared.sectors import cycle_phase_for_ticker
    except Exception:
        def cycle_phase_for_ticker(_t: str) -> str:  # graceful degrade
            return "unknown"
    rows = ""
    for p in ps:
        tk = p["ticker"]
        v = _broker_value(p, pnl)
        w = v / grand * 100
        pc = pnl.get(tk)
        pcls = "pos" if (pc or 0) >= 0 else "neg"
        pstr = "&mdash;" if pc is None else f"{'+' if pc >= 0 else ''}{pc:.1f}%"
        nm = names.get(tk, tk)
        vstr = f"{v:,.0f}".replace(",", "&#8239;")
        asym_cls, asym_str = _asym_format(asym.get(tk))
        g = gauges.get(tk)
        if g:
            # Thesis-frame tooltip : perf depuis entry (cohérent dot), pas pnl_position
            # cost-frame (qui vit dans la col "P&L" séparée de la table).
            # Book row Progress : UN SEUL MÈTRE — % depuis cost (cf principe
            # Olivier 09/06 23h+, _position_axis_pct). Stop/target/dot tous
            # calculés depuis cost_native via fx_now → cohérents, comparables.
            _gp_row = _gauge_pcts_from_cost(_book_idx.get(tk))
            if _gp_row and _gp_row.get("dot_pct") is not None:
                gauge_html = _position_axis_pct(
                    _gp_row.get("stop_pct"),
                    _gp_row.get("target_pct"),
                    _gp_row.get("dot_pct"),
                    extra_class="row-bar",
                    pnl_position_pct=_gp_row.get("dot_pct"),
                ) or '<span class="num" style="color:var(--steel);opacity:.5">&mdash;</span>'
            else:
                # Fallback legacy native si BookLine EUR absente (rare)
                _e_g, _c_g = g["_entry"], g["_cur"]
                _perf_e_row_n = ((_c_g / _e_g - 1) * 100.0) if (_e_g and _c_g and _e_g != 0) else None
                gauge_html = _position_axis(
                    g["_entry"], g["_stop"], g["_tgt"], g["_cur"], extra_class="row-bar",
                    pnl_position_pct=_perf_e_row_n,
                ) or '<span class="num" style="color:var(--steel);opacity:.5">&mdash;</span>'
        else:
            gauge_html = '<span class="num" style="color:var(--steel);opacity:.5">&mdash;</span>'
        # Cycle phase chip via vocabulary canonique (#117 -- adoption STATE calme).
        # Avant : _CP_CLS mappait late->warn / contraction->bear, faisant CRIER
        # des STATE (mur de rouge dans le book). Maintenant via vocabulary :
        # un STATE n'attire jamais l'oeil -> classe calme partout.
        _cp = cycle_phase_for_ticker(tk)
        _cp_cls = _cycle_chip_cls_via_vocab(_cp)
        _cp_chip = (
            f'<span class="cycle-chip cycle-{_cp_cls}" '
            f'data-tip="Cycle phase {_cp} (source config/sectors.yaml).">{_cp}</span>'
            if _cp != "unknown" else ""
        )
        # Macro book warning chips (06/06 v2 readability + ticker outlook v3) :
        # - Chip label = cluster identifiable (SEMIS/JP FX/...) au lieu de R1/R2
        # - Tooltip = action + pourquoi + Signaux 30j per-ticker (contexte signal)
        _tw_chips = ""
        _tw_list = ticker_warnings.get(tk, [])
        # Signaux per-ticker (orthogonal aux warnings macro portfolio-level).
        try:
            from shared.ticker_outlook import outlook_phrase, recent_outlook
            _outlook_str = outlook_phrase(recent_outlook(tk))
        except Exception:
            _outlook_str = ""
        for _tw in _tw_list[:3]:  # cap 3 chips par ticker
            _rid = _tw.get("rule_id", "?")
            _sev = _tw.get("severity", "med")
            _sev_cls = {"high": "bear", "med": "warn", "low": "steel"}.get(_sev, "steel")
            _label = _RULE_CHIP_LABELS.get(_rid, _rid.split("_")[0])
            _action = _tw.get("action", "").rstrip(".")
            _why = _tw.get("rationale", "").rstrip(".")
            _tw_tip = f"{_action}.\n\n{_why}.\n\n{_outlook_str}" if _outlook_str else f"{_action}.\n\n{_why}."
            _tw_chips += (
                f'<span class="warn-chip warn-chip-{_sev_cls}" '
                f'data-tip="{_h_esc.escape(_tw_tip, quote=True)}">{_label}</span>'
            )
        # #128 : badge "proxy" discret si valo MtM passe par une cote ≠ instrument détenu
        # (e.g. SK Hynix GDR EUR détenu mais yfinance retourne cote coréenne KRW × fx).
        # Affichage : petit "·proxy" steel-muted avec tooltip explicite. Pas d'alerte
        # (cost/realized restent EUR-corrects via ledger) — juste informer.
        _proxy_reason = is_proxy_price(tk)
        _proxy_chip = (
            f'<span class="proxy-chip" style="font-size:9px;opacity:.55;margin-left:4px;'
            f'color:var(--steel);font-weight:500" '
            f'data-tip="{_h_esc.escape(_proxy_reason, quote=True)}">&middot;proxy</span>'
            if _proxy_reason else ""
        )
        rows += (
            f'<tr data-tk="{tk}" data-v="{v:.2f}" data-w="{w:.2f}" data-p="{pc if pc is not None else -9999}"><td class="tk">{_ticker_logo(tk)}{tk}<span class="nm">{nm}</span>{_cp_chip}{_tw_chips}</td>'
            f'<td class="num mono">{vstr}&nbsp;&euro;{_proxy_chip}</td><td class="num">{w:.1f}%</td>'
            f'<td class="num {pcls}">{pstr}</td>'
            f'<td class="{asym_cls}">{asym_str}</td>'
            f'<td class="row-gauge">{gauge_html}</td></tr>'
        )
    if not ps:
        rows = '<tr><td class="empty" colspan="6" style="padding:var(--s4) 0">no position</td></tr>'
    tot_str = f"{tot:,.0f}".replace(",", "&#8239;")
    donut = _sector_donut(_sector_mix(ps, pnl, sectors)) if ps else ""
    return (
        f'<div class="brk"><div class="brk-h"><div><span class="brk-n">{label}</span>'
        f'<span class="brk-note">{note}</span></div>'
        f'<div class="brk-tot">{tot_str}&nbsp;&euro; <span>&middot; {len(ps)} positions &middot; {share:.0f}% of total</span></div></div>'
        f'<div class="brk-body">{donut}<div class="brk-tbl"><div class="card pad" style="padding:var(--s1) 18px"><table class="dt"><thead><tr><th>Position</th>'
        f'<th class="num">Valeur</th><th class="num">Poids</th><th class="num">P&amp;L</th>'
        f'<th class="num" title="upside_to_target / downside_to_stop. >3 = barbell (laisser courir). <1 = inverse (candidate trim).">Asymmetry</th>'
        f'<th title="Stop -> target progress (marker = current price, tick = target).">Progress</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div></div></div></div>"
    )


def _ticker_warnings_map(positions: list[dict]) -> dict[str, list[dict]]:
    """Map ticker -> list of macro_book_warnings affecting it.

    Source canonique : compute_book_warnings + current_macro_state.
    Permet a tout panel (Positions, Theses) d'afficher quels regles
    macro touchent quelle position.
    """
    try:
        from intelligence.macro_book_warnings import compute_book_warnings
        from shared.macro_state import current_macro_state
        ms = current_macro_state()
        ind_vals = {
            k: (v.get("value") if isinstance(v, dict) else None)
            for k, v in ms["readings_for_regime"].items()
        }
        warnings = compute_book_warnings(ms["regime"], positions, ind_vals)
        out: dict[str, list[dict]] = {}
        for w in warnings:
            for tk in w.get("tickers", []):
                out.setdefault(tk, []).append(dict(w))
        return out
    except Exception:
        return {}


def _broker_tables(positions: list[dict], names: dict, pnl: dict, sectors: dict) -> str:
    grand = sum(_broker_value(p, pnl) for p in positions) or 1
    asym = {}
    gauges: dict[str, dict] = {}
    try:
        from shared import book as _bk
        _book_idx = _bk.get_book_index()
    except Exception:
        _book_idx = {}
    try:
        asym_results = asym_mod.compute_portfolio_asymmetry()
        for r in asym_results:
            tk = r.get("ticker")
            if not tk:
                continue
            if r.get("asymmetry_ratio") is not None:
                asym[tk] = r["asymmetry_ratio"]
            st, tg, c = r.get("stop") or 0, r.get("target_full") or 0, r.get("current_price") or 0
            up, dn = r.get("upside_pct"), r.get("downside_pct")
            ln = _book_idx.get(tk)
            # Book row col "Progress" = stop->target progress (proximité-cible)
            # → thesis-frame natif : target posé en natif, FX-clean.
            # Money-invariant L28 : JAMAIS mix entry_native + current_eur.
            # entry/stop/target/current TOUS natifs même devise (KRW/JPY/EUR
            # selon le titre). Le P&L cost-frame vit dans la col "P&L" séparée.
            _entry_g = ln.entry_price if ln else None
            _stop_g = st
            _tgt_g = tg
            _cur_g = c
            if _stop_g and _tgt_g and _tgt_g != _stop_g and _cur_g and up is not None and dn is not None:
                gauges[tk] = {
                    "_entry": _entry_g,
                    "_stop": _stop_g,
                    "_tgt": _tgt_g,
                    "_cur": _cur_g,
                    "up": up,
                    "dn": dn,
                }
    except Exception:
        pass
    # 06/06 : warnings macro_book par ticker. Source canonique
    # shared.macro_state + macro_book_warnings. Permet d'afficher R1/R2/R4
    # chip a cote de chaque ticker affecte.
    ticker_warnings = _ticker_warnings_map(positions)
    tr = [p for p in positions if _broker(p["ticker"]) == "tr"]
    eu = [p for p in positions if _broker(p["ticker"]) == "bourso"]
    head = (
        '<div class="colhead tight"><span class="t">Comptes</span></div>'
    )
    return (
        head
        + _broker_one("Trade Republic", "hors Europe", tr, grand, names, pnl, sectors, asym, gauges, ticker_warnings)
        + _broker_one("Boursorama", "PEA &middot; Europe", eu, grand, names, pnl, sectors, asym, gauges, ticker_warnings)
    )











def _dba_eur(n: float) -> str:
    """Format EUR FR canon : separateur narrow no-break space, 0 decimale.
    Aligne avec '70 180' deja dans le panneau (litteral) -- evite l'ambiguite
    virgule = decimale en FR."""
    return f"{n:,.0f}".replace(",", "&#8239;")


def _dba_bar(state: str, count: int, total: int) -> str:
    """Bar canonique : la classe d'etat (dormant/at_risk/triggered) porte
    la severite ; CSS colore label + count + fill. Une row a 0 reste typee
    (opacity au row) -- le label triggered en rouge bold meme a count=0."""
    width = (count / total * 100) if total else 0
    zero = " zero" if count == 0 else ""
    return (
        f'<div class="dba-hbar {state}{zero}">'
        f'<span class="dba-hlab">{state}</span>'
        f'<div class="dba-haxis"><div class="dba-hfill" '
        f'style="width:{width:.0f}%"></div></div>'
        f'<span class="dba-hn">{count}</span></div>'
    )


def _dba_predictions_brier_html(brier_avg: float | None, brier_n: int) -> str:
    """Calibration card honnete (DNA v2 surface d'honnetete).

    Design : visualisation Brier vs baseline 0.25 (predicteur constante 0.5).
    Le honnete = afficher la baseline explicitement, badge fiabilite N<20,
    nommer le drift quand applicable."""
    if not brier_n:
        return (
            '<div class="calib-card">'
            '<div class="calib-row">'
            '<span class="calib-lbl">BRIER</span>'
            '<span class="calib-val muted">--</span>'
            '<span class="calib-baseline">baseline 0.250</span>'
            '</div>'
            '<div class="calib-meta">N=0 &middot; no resolved prediction yet</div>'
            '</div>'
        )
    # Position du marker sur axis 0..0.50 (visual range)
    AXIS_MAX = 0.50
    brier_pos = max(0.0, min(100.0, brier_avg / AXIS_MAX * 100))
    baseline_pos = 0.25 / AXIS_MAX * 100  # 50%
    # Drift signal vs baseline
    delta = brier_avg - 0.25
    delta_str = f"{'+' if delta >= 0 else ''}{delta:.3f}"
    drift_cls = "bear" if delta > 0 else "acc"
    drift_lbl = "worse than baseline" if delta > 0 else "beats baseline"
    # Fiabilite badge
    if brier_n < 20:
        reliability = (
            f'<span class="calib-badge warn" title="N&lt;20 = not yet reliable">'
            f'N={brier_n} &middot; not yet reliable</span>'
        )
    else:
        reliability = (
            f'<span class="calib-badge acc" title="N&ge;20 = reliable enough to compare">'
            f'N={brier_n} &middot; reliable</span>'
        )
    val_cls = "acc" if brier_avg < 0.20 else ("warn" if brier_avg < 0.25 else "bear")
    return (
        '<div class="calib-card">'
        '<div class="calib-row">'
        '<span class="calib-lbl">BRIER</span>'
        f'<span class="calib-val {val_cls}">{brier_avg:.3f}</span>'
        '<span class="calib-baseline">baseline 0.250</span>'
        f'<span class="calib-delta {drift_cls}">{delta_str} &middot; {drift_lbl}</span>'
        '</div>'
        '<div class="calib-axis">'
        '<div class="calib-track"></div>'
        f'<div class="calib-baseline-tick" style="left:{baseline_pos:.1f}%" title="baseline 0.250"></div>'
        f'<div class="calib-mark" style="left:{brier_pos:.1f}%" title="Brier {brier_avg:.3f}"></div>'
        '<div class="calib-scale"><span>0</span><span>0.25 baseline</span><span>0.5</span></div>'
        '</div>'
        '<div class="calib-meta">'
        f'{reliability}'
        '</div>'
        '<div class="calib-honest">'
        'Baseline 0.250 = constant 0.5 predictor (weakest possible). '
        'Beating it requires meaningful prediction skill ; matching it = no signal. '
        'Real benchmark = base-rate predictor b(1-b), shown post J+30 batch when N=35.'
        '</div>'
        '</div>'
    )


def _discipline_biais_panel() -> str:
    """Pile 1.1 -- surface de la mission PRESAGE (compteur disciplines + biais).
    Etat honnete-tot (user 01/06) : afficher creux + raisons. Conformite
    lexique etat-de-canal cf docs/GLOSSARY.md sect 'Etat de canal d'instrumentation'.
    Densite reelle viendra a J+30 quand les premiers biais se resolvent."""

    # Predictions cluster KPI #2 -- batch 10/06 specifique : V1 dont
    # target_date <= 2026-06-10. User 01/06 critique : la query precedente
    # comptait TOUTES les V1 resolues, biais vers "5 du cluster" alors qu'none
    # n'est du batch 10/06. Cluster target = 35 predictions a J-day.
    #
    # ADR 014 § Archive-report rule : panneau archive-V1 explicite. On NE
    # filtre PAS via canonical_predictions_filter() (qui exclut v1 -> 0/0).
    # Le label "V1 (exclu du headline canonique)" est rendu plus bas pour
    # eviter qu'un visiteur cite ce Brier comme track record canonique.
    n_cluster_total = _q(
        "SELECT COUNT(*) FROM predictions "
        "WHERE methodology_version = 'v1' AND target_date <= '2026-06-10'"
    )[0][0]
    n_resolved = _q(
        "SELECT COUNT(*) FROM predictions WHERE resolved_at IS NOT NULL "
        "AND outcome != 'neutral' AND methodology_version = 'v1' "
        "AND target_date <= '2026-06-10'"
    )[0][0]
    brier_row = _q(
        "SELECT AVG(brier_score), COUNT(brier_score) FROM predictions "
        "WHERE brier_score IS NOT NULL AND methodology_version = 'v1' "
        "AND resolved_at IS NOT NULL AND target_date <= '2026-06-10'"
    )[0]
    brier_avg, brier_n = brier_row[0], brier_row[1] or 0

    # KCA counts (last status per these active)
    kca_counts = {
        r[0]: r[1] for r in _q(
            "SELECT kca.status, COUNT(*) "
            "FROM (SELECT thesis_id, MAX(id) AS mid "
            "      FROM kill_criteria_alerts GROUP BY thesis_id) m "
            "JOIN kill_criteria_alerts kca ON kca.id = m.mid "
            "JOIN theses t ON t.id = kca.thesis_id "
            "WHERE t.status='active' "
            "GROUP BY kca.status"
        )
    }
    kca_dormant = kca_counts.get("dormant", 0)
    kca_at_risk = kca_counts.get("at_risk", 0)
    kca_triggered = kca_counts.get("triggered", 0)
    kca_total = max(kca_dormant + kca_at_risk + kca_triggered, 1)
    n_active_theses = _q("SELECT COUNT(*) FROM theses WHERE status='active'")[0][0]

    # User 01/06 critique : "derniere eval" est faux -- kca skip INSERT si
    # prev=new=dormant, donc MAX(created_at) = derniere TRANSITION persistee,
    # nornier run cron. Libelle reformule pour la verite.
    last_trans = _q("SELECT MAX(created_at) FROM kill_criteria_alerts")[0][0]
    last_trans_str = last_trans[:16].replace("T", " ") if last_trans else "none"

    # bias_events compteurs
    n_bias_open = _q("SELECT COUNT(*) FROM bias_events WHERE status='open'")[0][0]
    n_bias_resolved = _q("SELECT COUNT(*) FROM bias_events WHERE status='resolved'")[0][0]

    # over_cap live (classify_position du monitor = source de verite)
    try:
        from intelligence.bias_events import MissingDataError
        from intelligence.over_cap_monitor import classify_position
        from shared import book as _bk

        caps = _CFG.get("concentration", {}).get("line_cap_by_conviction", {})
        raw = list(_bk.get_held_lines())
        lines = [
            {"ticker": ln.ticker, "weight": ln.weight_market_eur,
             "qty": float(ln.qty or 0), "current_price_eur": ln.current_price_eur}
            for ln in raw
        ]
        convs_rows = _q(
            "SELECT ticker, conviction FROM theses WHERE status='active'"
        )
        convs = {r[0]: r[1] for r in convs_rows if isinstance(r[1], int)}
        over_tk: list[str] = []
        for ln in lines:
            tk_str = str(ln["ticker"])
            try:
                cls = classify_position(tk_str, lines, convs, caps)
                if cls and cls["status"] == "over":
                    over_tk.append(tk_str)
            except MissingDataError:
                pass
        book_total_eur = sum(float(ln.get("weight") or 0) for ln in lines)
    except Exception:
        over_tk = []
        book_total_eur = 0

    over_tags_html = (
        '<div class="dba-tags">'
        + "".join(f'<span class="dba-tag">{t}</span>' for t in over_tk)
        + "</div>"
    ) if over_tk else ""

    pred_marker = "&#10003;" if n_resolved >= 5 else "&#9675;"

    # === Star Discipline : KPI #2 + Brier + biais counts ===
    from datetime import date as _date
    _today_d = _date.today()
    _jday = _date(2026, 6, 10)
    _delta_jday = (_jday - _today_d).days
    if _delta_jday > 0:
        _jday_str = f"J-{_delta_jday} before batch 10/06"
    elif _delta_jday == 0:
        _jday_str = "J-day batch 10/06 (aujourd'hui)"
    else:
        _jday_str = f"J+{-_delta_jday} after batch 10/06"
    _kpi2_cls = "acc" if n_resolved >= 5 else "warn"
    _kpi2_cap = "calibration active" if n_resolved >= 5 else f"need {5 - n_resolved} more"
    _brier_cls = ""
    if brier_n >= 5:
        _brier_cls = "acc" if brier_avg < 0.20 else ("warn" if brier_avg < 0.25 else "bear")
    _brier_str = f"{brier_avg:.3f}" if brier_n else "&mdash;"
    _brier_cap = f"N={brier_n}" + ("" if brier_n >= 5 else f" &middot; besoin {5 - brier_n}")
    star_discipline = (
        '<div class="page-star">'
        + '<div class="ps-strate">'
        + '<div class="ps-lbl">Discipline &amp; Bias</div>'
        + '<div class="ps-macro-row">'
        + f'<div class="ps-val {_kpi2_cls}">{n_resolved}/{n_cluster_total}</div>'
        + '<div class="ps-macro-meta">resolved predictions &middot; KPI #2 &ge;5</div>'
        + '</div>'
        + f'<div class="ps-cap">{_kpi2_cap} &middot; {_jday_str}</div>'
        + '<div class="ps-cap" style="opacity:.65">V1 transitional &middot; '
          'exclu du headline canonique public (ADR 014)</div>'
        + '</div>'
        + '<div class="ps-strate ps-grid">'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Probabilistic prediction calibration score. Mean (prob - outcome)^2. &lt; 0.20 good, &lt; 0.25 acceptable, &gt;= 0.25 to fix.">Brier mean</div><div class="ps-val {_brier_cls}">{_brier_str}</div><div class="ps-cap">{_brier_cap}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Open bias_event candidates (lock_in/fomo_greed). +30d observation window post-detection.">Open biases</div><div class="ps-val">{n_bias_open}</div><div class="ps-cap">events under observation</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Resolved bias events with canonical +30d scoring. Enriched with later +60/+90d observations.">Resolved biases</div><div class="ps-val acc">{n_bias_resolved}</div><div class="ps-cap">post-resolution</div></div>'
        + '</div>'
        + '<div class="ps-strate ps-foot">'
        + 'Predictions &middot; fomo_greed (2 canaux) &middot; lock_in (Surface 2 v2.c.6 shipped) ci-dessous'
        + '</div>'
        + '</div>'
    )
    return (
        # Migre 02/06 user : fusion dans page Methode (data-page="methode").
        # Wrapper section retire -- ce bloc est inline dans _signaux().
        '<div class="dba-block">'
        + _DBA_CSS
        + '<div class="dba-sh" data-tip="PRESAGE mission counter: calibrated predictions + mechanized behavioral biases."><svg class="sh-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6l1.5 1.5L8.5 4.5"/><path d="M10 6h4"/><path d="M4 11l1.5 1.5L8.5 9.5"/><path d="M10 11h4"/></svg>Discipline &amp; mechanized biases'
        '<span class="dba-sh-aside">mission counter &middot; real density at J+30</span></div>'
        + star_discipline
        # ─── PREDICTIONS ─────────────────────────────────────────────────
        + '<div class="dba-sh" data-tip="Predictions resolved at J+28: probabilistic marker (Brier score) on estimate calibration."><svg class="sh-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="3"/><circle cx="8" cy="8" r="0.8" fill="currentColor" stroke="none"/></svg>Predictions'
        '<span class="dba-sh-aside">cluster KPI #2 &mdash; J+28 batch 10/06</span></div>'
        '<div class="dba-card">'
        f'<div class="dba-chrow"><span class="lab">{n_resolved}/{n_cluster_total} '
        f'resolved &middot; KPI #2 &ge;5 {pred_marker}</span>'
        '<span class="stat actif">active</span></div>'
        f'{_dba_predictions_brier_html(brier_avg, brier_n)}'
        '</div>'
        # ─── BIAIS fomo_greed ────────────────────────────────────────────
        '<div class="dba-sh" data-tip="FOMO/greed bias: not trimming when discipline called for it. Instrumented on 2 channels: kill_criteria + over_cap."><svg class="sh-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 14c-3 0-5-2-5-5 0-2 1.5-3.5 2.5-4 0 1.5 1 2 1.5 2 0-2 1-4 3-5 .5 2 3 3 3 6 0 4-2 6-5 6z"/><path d="M7 11.5c0-1 .5-1.5 1-2 .5.5 1 1 1 2 0 .7-.5 1.2-1 1.2s-1-.5-1-1.2z"/></svg>Biais &mdash; fomo_greed'
        '<span class="dba-sh-aside">hold beyond top &middot; 2 channels instrumented</span></div>'
        # Canal kill_criteria
        '<div class="dba-card">'
        '<div class="dba-chrow"><span class="lab">kill_criteria</span>'
        '<span class="stat actif">active</span></div>'
        f'<div class="dba-meta">{n_active_theses} theses monitored '
        f'(daily monitoring) &middot; last transition '
        f'recorded {last_trans_str}</div>'
        '<div class="dba-bars">'
        + _dba_bar("dormant", kca_dormant, kca_total)
        + _dba_bar("at_risk", kca_at_risk, kca_total)
        + _dba_bar("triggered", kca_triggered, kca_total)
        + '</div>'
        f'<div class="dba-arrow">&rsaquo; <span class="v">{n_bias_open}</span> '
        f'candidat{"s" if n_bias_open != 1 else ""} ouvert{"s" if n_bias_open != 1 else ""} '
        f'&middot; <span class="v">{n_bias_resolved}</span> '
        f'resolved{"s" if n_bias_resolved != 1 else ""}</div>'
        '</div>'
        # Canal over_cap
        '<div class="dba-card">'
        '<div class="dba-chrow"><span class="lab">over_cap</span>'
        '<span class="stat veille">en veille (par decision)</span></div>'
        f'<div class="dba-meta">Book {_dba_eur(book_total_eur)}&nbsp;&euro; &rarr; '
        f'{_dba_eur(70180)}&nbsp;&euro; target &middot; construction phase</div>'
        f'<div class="dba-count">{len(over_tk)} OVER detected'
        f'{"s" if len(over_tk) != 1 else ""} actuellement</div>'
        f'{over_tags_html}'
        '<div class="dba-honest">Marginals: all return below cap at '
        '70k = denominator artifacts, not real over-concentration. '
        'Firing now = measuring a discipline that did not say &laquo;&nbsp;trim&nbsp;&raquo;.</div>'
        '<div class="dba-cond">Re-activation: book &ge; 65&nbsp;k&euro; '
        'OU construction_phase flag raised</div>'
        '<div class="dba-arrow">&rsaquo; <span class="v">0</span> candidate emitted '
        '&middot; resolution N/A</div>'
        '</div>'
        # ─── BIAIS lock_in ──────────────────────────────────────────────
        '<div class="dba-sh" data-tip="Lock-in bias: selling winners too early. PRESAGE bias #1 per ADR-010. Mechanized via Surface 2 (sell winner sync capture)."><svg class="sh-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="10" height="7" rx="1"/><path d="M5 7V5a3 3 0 0 1 6 0v2"/><circle cx="8" cy="10.5" r=".9" fill="currentColor" stroke="none"/></svg>Biais &mdash; lock_in'
        '<span class="dba-sh-aside">selling winners too early</span></div>'
        '<div class="dba-card">'
        '<div class="dba-chrow">'
        '<span class="lab">Surface 2 &mdash; capture synchrone vente winner</span>'
        '<span class="stat non-inst">not instrumented</span></div>'
        '<div class="dba-meta">Path planned by ADR-010 §2. '
        'No capture channel today &mdash; PRESAGE bias #1, to fill in.</div>'
        '<div class="dba-cond">No candidat capturable tant que ce chemin '
        'not yet shipped.</div>'
        '</div>'
        '</div>'
    )


def render() -> Path:
    # === COEUR UNIQUE (SPEC_MONEY_INVARIANT §8 + SPEC_POSITIONS_CARD_LINK §7.bis) ===
    # Battement unique : appele 1x/regen au top, tous les panneaux projettent.
    # Pour l'instant additif zero-diff -- les panneaux ne le consomment pas encore.
    # Migration etagee panel-par-panel par visibilite decroissante (L27, byte-identite).
    from shared.position_view import get_all_positions_views
    _views = get_all_positions_views()  # dict[ticker -> PositionView]
    # #123 compute-once-project : register pnl_position UNE FOIS par ticker depuis
    # le point unique _views. Le register a été retiré de compute_position()
    # (sinon multiple writes = faux forks). Source canonique "position_view".
    try:
        from shared.living_graph import register_concept
        for _tk, _v in _views.items():
            _pnl = getattr(_v, "pnl_position_pct", None)
            if _pnl is not None:
                register_concept(
                    concept_key="pnl_position",
                    value=float(_pnl),
                    source="position_view",
                    ticker=_tk,
                    op="value_eur_datum_div_cost_basis_eur",
                )
    except Exception:
        pass

    # Bug fix 31/05 wave 9b : asymmetry compare current vs stop_price/target_full.
    # Comme ces derniers sont stockes NATIVE (cf currency_native_invariant),
    # current doit etre NATIVE aussi pour des ratios FX-invariants. Ancien
    # patch vers _cached_price_eur produisait "Marges les plus faibles" avec
    # target +175408% (000660.KS KRW vs current EUR).
    asym_mod._get_current_price = _cached_price_native
    full = asym_mod.compute_portfolio_asymmetry()
    computed = [r for r in full if "asymmetry_ratio" in r]
    # Builder _positions() consomme le seam _views (cœur unique).
    # Concentration / cluster_health / risk_watch_panel consomment ce dict,
    # donc cohérence canonical pour les 3 panneaux d'un coup.
    positions = _positions(_views)
    sectors = _sectors()
    held = {p["ticker"] for p in positions}
    planned = _planned(held)
    names = _names()
    pnl = _pnl_cost_map(positions, views=_views)
    perf = {p["ticker"]: _perf_dwm(p["ticker"]) for p in positions}
    daily = {tk: v.get("d") for tk, v in perf.items()}
    loupe_data = _loupe_data(positions, sectors, names, pnl, computed, perf)
    sb_down = {r["ticker"]: r.get("downside_pct") for r in computed}
    sb_secs: dict = {}
    for p in positions:
        sb_secs.setdefault(sectors.get(p["ticker"], "Sans thesis"), []).append(
            {
                "tk": p["ticker"],
                "w": round(p["weight"] or 0),
                "pnl": round(pnl[p["ticker"]], 1) if p["ticker"] in pnl else None,
                "down": round(sb_down[p["ticker"]] or 0, 1) if sb_down.get(p["ticker"]) is not None else None,
            }
        )
    sb_ordered = sorted(sb_secs.items(), key=lambda kv: (kv[0] == "Sans thesis", -sum(x["w"] for x in kv[1])))
    sb_data = [{"name": nm, "col": SECTOR_COLORS.get(nm, "#6B7686"), "t": rows} for nm, rows in sb_ordered]

    _ris, near, _heat, watch = _rows_risque(computed, positions)  # AUDIT v5 : pass positions pour weighted heat
    gain, _lose = _movers(pnl)
    # day_up/day_dn computes pour _urgence() seulement (D2 retire de Vigie 02/06).
    _day_up, _day_dn = _day_movers(daily)
    _stamp = datetime.now().strftime("%d.%m.%Y &middot; %H:%M")
    today = datetime.now().strftime("%Y-%m-%d")
    erows = ""
    for rdate, rlab in sorted(REVIEWS):
        rpast = rdate < today
        rdd = f"{rdate[8:10]}.{rdate[5:7]}"
        rop = ' style="opacity:.45"' if rpast else ""
        rtag = " &middot; passed" if rpast else ""
        erows += f'<div class="line"{rop}><span>{rlab}{rtag}</span><span class="mono">{rdd}</span></div>'
    erows = erows or '<div class="empty" style="padding:var(--s35) 0">none deadline</div>'

    wbase = sum(p["weight"] for p in positions if p["ticker"] in pnl) or 1
    port_pnl = sum(p["weight"] * pnl[p["ticker"]] for p in positions if p["ticker"] in pnl) / wbase
    _gain_eur = sum(p["weight"] for p in positions if pnl.get(p["ticker"], 0) >= 0 and p["ticker"] in pnl)
    _n_gain = sum(1 for p in positions if pnl.get(p["ticker"], 0) >= 0 and p["ticker"] in pnl)
    _n_pnl = sum(1 for p in positions if p["ticker"] in pnl) or 1
    _gpct = _gain_eur / wbase * 100
    # Post-migration 29/05 round 2 : p["weight"] est MARKET VALUE, cost basis
    # est explicitement dans p["cost_basis_eur"]. Avant le sed, le hero
    # affichait double-PnL (cost * (1+pnl) au lieu de market).
    _pfcost = sum(p.get("cost_basis_eur", 0) for p in positions)
    pf_value = sum(p["weight"] for p in positions)
    pf_pnl_eur = pf_value - _pfcost
    # Star Vue d'ensemble : .ps-val attend acc/warn/bear (pas pos/neg legacy)
    _pnl_star_cls = "acc" if pf_pnl_eur >= 0 else "bear"
    pf_arrow = "&#9650;" if pf_pnl_eur >= 0 else "&#9660;"
    pf_val_str = f"{pf_value:,.0f}".replace(",", "&#8239;")
    _pf_cost_str = f"{_pfcost:,.0f}".replace(",", "&#8239;")  # D5 retire Vigie, conserve compute (re-use eventuelle)
    pf_pe = f"{abs(pf_pnl_eur):,.0f}".replace(",", "&#8239;")
    near_stop_tk = [
        r["ticker"]
        for r in sorted(computed, key=lambda r: r.get("downside_pct", 999.0))
        if r.get("downside_pct") is not None and r["downside_pct"] < 10
    ]
    near_tgt_tk = [
        r["ticker"]
        for r in sorted(computed, key=lambda r: r.get("upside_pct", 999.0))
        if r.get("upside_pct") is not None and r["upside_pct"] < 12
    ]
    _conv_tk = {row[0]: row[1] for row in _q("SELECT ticker, conviction FROM theses WHERE status='active'")}
    _over_cap_tk = _sizing_overcap(
        positions, _conv_tk, _CFG.get("concentration", {}).get("line_cap_by_conviction", {}), pnl
    )

    # disc_hero (Cockpit posture hero) retire 31/05 user feedback
    # _pi() helper toujours utilise par d'autres panneaux (.plan etc.)

    # Tape ticker DAILY % (user 02/06 "valeurs tickers en daily%"). Avant
    # on affichait pnl[tk] = lifetime PnL since entry -> incoherent avec
    # un bandeau "roulant" qui suggere flux temps-reel.
    tape_items = ""
    tape_data = []
    for tk in pnl:
        dp = _dp_pct(tk)
        if dp is not None:
            tape_data.append((tk, dp))
    for tk, dp in sorted(tape_data, key=lambda x: -x[1]):
        cls = "pos" if dp >= 0 else "neg"
        arrow = "&#9650;" if dp >= 0 else "&#9660;"
        tape_items += f'<span class="ti">{_ticker_logo(tk)}<span class="tk tkc" data-tk="{tk}">{tk}</span> <span class="{cls}">{arrow}&nbsp;{abs(dp):.1f}%</span></span>'
    tape = f'<div class="tape"><div class="track2">{tape_items}{tape_items}</div></div>'
    # tape8k (8-K events scrolling ticker) supprime 02/06 user "delete le
    # bandeau des events". Tape ticker daily% conserve.
    tape8k = ""

    # Journal block retire 02/06 Vigie -- compute conserve pour reactivation eventuelle.
    _journal_html = _journal()
    # === Phase 4 migration L27 : _axis projete depuis _views (coeur unique) ===
    # Avant : reconstruit depuis computed (asym_mod.compute_portfolio_asymmetry qui
    # re-fetche yfinance localement -- violation L27). Apres : projection pure
    # depuis _views[tk] qui sont les Datums canoniques deja calcules une fois.
    # Byte-identite garantie tant que asym_mod produit les memes (stop, target_full,
    # current, upside_pct, downside_pct) que PositionView -- ce sont les memes
    # sources DB. Tout diff = finding (au moins un des deux est faux).
    _axis: dict[str, dict[str, float]] = {}
    for tk, view in _views.items():
        st = view.stop_native or 0
        tg = view.target_full_native or 0
        c = view.price_native or 0
        up = view.upside_pct
        dn = view.downside_pct
        if st and tg and tg != st and c and up is not None and dn is not None:
            frac_raw = (c - st) / (tg - st) * 100
            _axis[tk] = {
                "frac": max(0.0, min(100.0, frac_raw)),
                "frac_raw": frac_raw,
                "up": up,
                "dn": dn,
                "tg_pct": (c / tg - 1) * 100 if tg else 0,
                "_stop": st,
                "_tgt": tg,
                "_cur": c,
            }
    # Split Closest/Beyond — test correct = cur_native >= target_native
    # (FX-invariant, pas de piège de signe). Cf catch Olivier 09/06 23h+ :
    # frac_raw >= 100 misclassifie SK Hynix (target_pct=-0.7% via cost rattrapé
    # → frac_raw=-2571% < 100 → wrongly Closest). cur >= target s'en moque.
    _beyond = sorted(
        [tk for tk in _axis if _axis[tk]["_cur"] >= _axis[tk]["_tgt"]],
        key=lambda tk: -(_axis[tk]["_cur"] / _axis[tk]["_tgt"] if _axis[tk]["_tgt"] else 0),
    )[:6]
    _targets = sorted(
        [tk for tk in _axis if _axis[tk]["_cur"] < _axis[tk]["_tgt"]],
        key=lambda tk: -(_axis[tk]["_cur"] / _axis[tk]["_tgt"] if _axis[tk]["_tgt"] else 0),
    )[:6]
    _stops = sorted(_axis, key=lambda tk: _axis[tk]["frac_raw"])[:6]

    # F13 fix : "proche de la target" n'est PAS une victoire mecanique. Si la
    # position est aussi fragile / valo > bull / solidite faible, atteindre
    # la target = signal de prendre profit, pas la these qui marche. On surface
    # ce tag explicite sur chaque row qui meriterait un trim.
    try:
        from shared import book as _bk

        _book_idx = _bk.get_book_index()
    except Exception:
        _book_idx = {}

    def _axisrow(tk: str) -> str:
        a = _axis[tk]
        frac_raw = a["frac_raw"]
        ln = _book_idx.get(tk)
        beyond_pct = a["tg_pct"]
        # 06/06 FX-aware tooltip : pour tickers en native non-EUR, compute la
        # divergence target_native vs PnL_EUR reel (cas SK Hynix : "target hit
        # en KRW mais EUR PnL seulement +8.6%"). Doctrine currency-native-invariant
        # preservee, juste enrichit le tooltip.
        fx_tip = ""
        if ln and ln.avg_cost_eur:
            try:
                px_eur = _cached_price_eur(tk)
                px_native = a["_cur"]
                if px_eur and px_native:
                    implied_fx = px_native / px_eur
                    avg_eur = float(ln.avg_cost_eur)
                    # FX-divergence detectee si difference avg/native >> 1
                    # (tickers JP/KR/non-USD avec movement FX signifiant)
                    if implied_fx > 2 and avg_eur > 0:  # heuristic : KRW/JPY/etc
                        pnl_eur_pct = (px_eur / avg_eur - 1) * 100
                        fx_tip = (
                            f"native {a['_cur']:,.0f} vs target {a['_tgt']:,.0f} = "
                            f"{beyond_pct:+.1f}% en native | "
                            f"EUR : {px_eur:.2f} vs avg cost {avg_eur:.2f} = "
                            f"{pnl_eur_pct:+.1f}% gain réel"
                        )
            except Exception:
                pass
        profit_chip = ""
        if frac_raw > 100:
            chip_tip_attr = f' data-tip="{fx_tip}"' if fx_tip else ""
            profit_chip = (
                f'<span class="th-pt acc"{chip_tip_attr}>target +{beyond_pct:.1f}% beyond</span>'
            )
        elif ln and a["frac"] > 80:
            risky = ln.valo_above_bull_case or ln.solidite in ("Fragile", "Incertain")
            if risky:
                chip_tip_attr = f' data-tip="{fx_tip}"' if fx_tip else ""
                profit_chip = f'<span class="th-pt"{chip_tip_attr}>target hit</span>'
        # Asym CLOSEST_TO_TARGET : UN SEUL MÈTRE — % depuis cost. Le panneau est
        # rangé via cur_native >= target_native, donc Closest = approche legitime,
        # Beyond = passé. La gauge montre l'avancement sans mélange.
        _gp_ar = _gauge_pcts_from_cost(ln)
        if _gp_ar and _gp_ar.get("dot_pct") is not None:
            bar = _position_axis_pct(
                _gp_ar.get("stop_pct"),
                _gp_ar.get("target_pct"),
                _gp_ar.get("dot_pct"),
                pnl_position_pct=_gp_ar.get("dot_pct"),
            ) or (
                f'{_tbar(max(0.0, min(100.0, frac_raw / 150.0 * 100)), ticks=[(0.0, "stop", "stop"), (66.67, "target", "target")], title=f"progress {frac_raw:.0f}%")}'
            )
        else:
            # Fallback legacy natif
            _e = ln.entry_price if ln else None
            _s, _t, _c = a["_stop"], a["_tgt"], a["_cur"]
            _pnl_p = (_c / _e - 1) * 100.0 if (_e and _c and _e != 0) else None
            bar = _position_axis(_e, _s, _t, _c, pnl_position_pct=_pnl_p) or (
                f'{_tbar(max(0.0, min(100.0, frac_raw / 150.0 * 100)), ticks=[(0.0, "stop", "stop"), (66.67, "target", "target")], title=f"progress {frac_raw:.0f}%")}'
            )
        return (
            f'<div class="row" data-tk="{tk}"><div class="rt"><span class="tk">{tk}</span>{profit_chip}</div>'
            f'{bar}</div>'
        )

    gain = "".join(_axisrow(tk) for tk in _targets) or '<div class="empty" style="padding:var(--s4) 0">&mdash;</div>'
    beyond = "".join(_axisrow(tk) for tk in _beyond) or '<div class="empty" style="padding:var(--s4) 0">&mdash;</div>'
    _lose_stops = "".join(_axisrow(tk) for tk in _stops) or '<div class="empty" style="padding:var(--s4) 0">&mdash;</div>'  # D1 retire Vigie, compute conserve
    # cockpit_html (Cockpit discipline panel) retire 31/05 user feedback
    # _cockpit() helper toujours dispo si reactivation future
    grade_html = _grade_panel()
    # performance_html + data_health_html retires 07/06 user :
    # - performance = pro-forma retro-fictif, pas track record reel
    # - data_health = inputs M1 freshness (instrumentation), pas verite-du-jour
    # Les deux migrent vers page Method ou ils sont plus honnetes
    # (audience methodologique vs lecture operationnelle).
    blind_html = _blind_positions_panel()
    # chat_html + conceptions_html + copilot_html retires 31/05 wave 5 :
    # migration vers section Copilot dediee (_copilot() entre Positions et
    # Theses). Les helpers _chat_panel / _conceptions_panel / _copilot_panel
    # restent appeles par _copilot() directement.
    # V2 monitoring panels retires 31/05 user feedback (code backend conserve,
    # alertes Telegram via cron weekly prennent le relais)
    # v2_cohort_html / wire_activity_html / vigilance_html / calib_progress_html
    # Sprint 18 : _narrative_panel deprecated (faux flags AMD~TSM, SAF~HO)
    # Retraits 02/06 page Strategie (panneaux infinis rebarbatifs) :
    # _ticker_axes_panel / _factor_exposures_panel / _stress_tests_panel /
    # _spof_panel / _mauboussin_sizing_panel -- code backend conserve,
    # donnees disponibles pour reactivation future.
    trajectory_html = _trajectory_panel()
    valo_html = _valo_above_bull_panel()
    # Star Vue d'ensemble : extract grade data pour 3-strate hero
    try:
        from intelligence import portfolio_grade as _pgrade
        from shared import storage as _stg_g
        _latest_g = _stg_g.get_latest_portfolio_grade()
        if _latest_g:
            _grade_letter = _latest_g["overall_grade"]
            _grade_score = _latest_g["overall_score"]
        else:
            _g_fresh = _pgrade.compute_grade()
            _grade_letter = _g_fresh["overall_grade"]
            _grade_score = _g_fresh["overall_score"]
        _trend = _pgrade.compute_trend_7d()
        _grade_trend_str = {
            "improving": "&uarr; 7j",
            "stable": "stable 7j",
            "deteriorating": "&darr; 7j",
            "no_history": "snapshot J0",
        }.get(_trend, "")
    except Exception:
        _grade_letter, _grade_score, _grade_trend_str = "&mdash;", 0, "indisponible"
    # grade_html n'est plus affiche separement (integre dans Star). Conserve
    # _grade_panel() call pour side-effects DB potentiels mais on supprime
    # le rendu dupliqué.
    _ = grade_html  # ne pas retirer l'appel : side-effects DB potentiels
    # Sparkline hero 30j depuis portfolio_snapshots (Robinhood/TR pattern).
    # Aggregate par jour (MAX 1 valeur/jour, prend la plus recente) pour
    # accuracy : evite step pattern cause par snapshots multiples meme date.
    try:
        _spark_raw = list(_q(
            "SELECT snapshot_date, total_value_eur FROM portfolio_snapshots "
            "WHERE total_value_eur IS NOT NULL "
            "AND snapshot_date >= date('now','-31 day') "
            "ORDER BY snapshot_date ASC, captured_at ASC"
        ))
        # Aggregate : 1 valeur par date (la plus recente)
        _spark_by_day = {}
        for _d, _v in _spark_raw:
            _spark_by_day[_d] = _v
        _spark_dates_sorted = sorted(_spark_by_day.keys())
        _spark_vals = [_spark_by_day[k] for k in _spark_dates_sorted]
        _spark_dates = _spark_dates_sorted
        # Append live value si snapshot du jour pas encore present (snapshot
        # tourne dans evening_chain 23:00 -- en attendant, le widget refletait
        # hier soir au lieu de maintenant -> sparkline endpoint + delta vs J-1
        # tous deux mensongers. Cf docs/audit_2026-06-03 Pattern 2 + 3.
        _today_iso = datetime.now(UTC).strftime("%Y-%m-%d")
        if pf_value > 0 and (not _spark_dates or _spark_dates[-1] != _today_iso):
            _spark_vals.append(pf_value)
            _spark_dates.append(_today_iso)
    except Exception:
        _spark_vals = []
        _spark_dates = []
    # Delta valeur portefeuille vs J-1 pour trend indicator
    _val_delta_str = ""
    if len(_spark_vals) >= 2:
        _val_d = _spark_vals[-1] - _spark_vals[-2]
        _val_d_pct = (_val_d / _spark_vals[-2] * 100) if _spark_vals[-2] else 0
        _val_arrow_d = "&#9650;" if _val_d >= 0 else "&#9660;"
        _val_col_d = "acc" if _val_d >= 0 else "bear"
        _val_delta_str = (
            f'<span class="ps-trend-delta {_val_col_d}">{_val_arrow_d} '
            f'{abs(_val_d):,.0f}&nbsp;&euro; ({"+" if _val_d_pct >= 0 else ""}{_val_d_pct:.2f}%) vs J-1</span>'
        ).replace(",", "&#8239;")
    if len(_spark_vals) >= 2:
        _spk_lo, _spk_hi = min(_spark_vals), max(_spark_vals)
        _spk_rng = (_spk_hi - _spk_lo) or 1.0
        _spk_w, _spk_h, _spk_pad = 130, 32, 3
        _spk_pts = []
        _spk_n = len(_spark_vals)
        for _i, _v in enumerate(_spark_vals):
            _x = _spk_pad + (_i / max(1, _spk_n - 1)) * (_spk_w - 2 * _spk_pad)
            _y = _spk_pad + (_spk_h - 2 * _spk_pad) - ((_v - _spk_lo) / _spk_rng) * (_spk_h - 2 * _spk_pad)
            _spk_pts.append(f"{_x:.1f},{_y:.1f}")
        _spk_color = "var(--acc)" if _spark_vals[-1] >= _spark_vals[0] else "var(--bear)"
        _spk_last_x, _spk_last_y = _spk_pts[-1].split(",")
        # Smoothing via Catmull-Rom -> cubic Bezier path (lisse les angles).
        def _spk_smooth_path(pts):
            if len(pts) < 2:
                return ""
            xs_ys = [(float(p.split(",")[0]), float(p.split(",")[1])) for p in pts]
            d = f"M {xs_ys[0][0]:.1f} {xs_ys[0][1]:.1f}"
            for i in range(1, len(xs_ys)):
                p0 = xs_ys[i-2] if i >= 2 else xs_ys[i-1]
                p1 = xs_ys[i-1]
                p2 = xs_ys[i]
                p3 = xs_ys[i+1] if i+1 < len(xs_ys) else p2
                c1x = p1[0] + (p2[0] - p0[0]) / 6
                c1y = p1[1] + (p2[1] - p0[1]) / 6
                c2x = p2[0] - (p3[0] - p1[0]) / 6
                c2y = p2[1] - (p3[1] - p1[1]) / 6
                d += f" C {c1x:.1f} {c1y:.1f} {c2x:.1f} {c2y:.1f} {p2[0]:.1f} {p2[1]:.1f}"
            return d
        _spk_path = _spk_smooth_path(_spk_pts)
        # Encode points+dates pour hover interactif (data attrs : x|y|val|date)
        _spk_pts_data = ";".join(
            f"{_spk_pts[_i].split(',')[0]}|{_spk_pts[_i].split(',')[1]}|{_spark_vals[_i]:.0f}|{_spark_dates[_i]}"
            for _i in range(len(_spk_pts))
        )
        # DNA v2 : sparkline mono-trait, no area fill, no pulsing animation.
        # Hover crosshair conserve (epistemic data reveal, pas celebration).
        _sparkline = (
            f'<span class="ps-spark-wrap"><svg class="ps-spark" viewBox="0 0 {_spk_w} {_spk_h}" width="{_spk_w}" height="{_spk_h}" '
            f'style="overflow:visible" aria-label="Trajectoire 30j" '
            f'data-pts="{_spk_pts_data}" data-w="{_spk_w}" data-h="{_spk_h}" data-color="{_spk_color}">'
            f'<path d="{_spk_path}" fill="none" stroke="{_spk_color}" '
            f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{_spk_last_x}" cy="{_spk_last_y}" r="2.5" fill="{_spk_color}"/>'
            f'<line class="spk-cross" x1="0" y1="0" x2="0" y2="{_spk_h}" stroke="{_spk_color}" stroke-width="1" opacity="0" stroke-dasharray="2 2"/>'
            f'<circle class="spk-cur" cx="0" cy="0" r="3" fill="{_spk_color}" opacity="0"/>'
            f'</svg><span class="spk-tip" style="display:none"></span></span>'
        )
    else:
        _sparkline = ""
    # Color note + bar selon score (consistent avec _cls() interne grade_panel)
    try:
        _gscore_int = int(_grade_score) if _grade_score is not None else 0
    except Exception:
        _gscore_int = 0
    _grade_color = "acc" if _gscore_int >= 70 else ("warn" if _gscore_int >= 50 else "bear")
    # (Grade sparkline retire 01/06 user feedback : pas besoin sur Portfolio grade)
    # === Macro state strate (06/06 user "tout connecter aux memes sources") ===
    # Lecture canonique : shared.macro_state.current_macro_state(). Meme dict
    # que celui consomme par _urgence panel. Source unique.
    try:
        import html as _html

        from shared.macro_state import current_macro_state, regime_color
        _ms = current_macro_state()
        _ms_regime = _ms["regime"]
        _ms_score = _ms["score"]
        _ms_buckets = _ms["bucket_counts"]
        _ms_color = regime_color(_ms_regime)
        _ms_tip = (
            f"Etat macro courant. Regime: {_ms_regime}. Score V3: {_ms_score:.0f}. "
            f"Indicateurs : ACT {_ms_buckets.get('act', 0)} / "
            f"WATCH {_ms_buckets.get('watch', 0)} / CALM {_ms_buckets.get('calm', 0)} / "
            f"SILENT {_ms_buckets.get('silent', 0)}. "
            "Source : shared.macro_state. Detail : page Alerts."
        )
        _macro_state_strate = (
            '<div class="ps-strate" data-tip="' + _html.escape(_ms_tip, quote=True) + '">'
            + '<div class="ps-lbl">Macro state</div>'
            + '<div class="ps-macro-row" style="align-items:baseline;gap:var(--s4)">'
            + f'<div class="ps-val {_ms_color}" style="font-size:24px">{_ms_regime.replace("_", " ")}</div>'
            + f'<div class="ps-macro-meta">score {_ms_score:.0f}</div>'
            + '<div class="ps-macro-meta" style="margin-left:auto">'
            + f'<span class="bear" style="font-weight:600">ACT {_ms_buckets.get("act", 0)}</span>'
            + ' &middot; '
            + f'<span class="warn" style="font-weight:600">WATCH {_ms_buckets.get("watch", 0)}</span>'
            + f' &middot; CALM {_ms_buckets.get("calm", 0)} &middot; SILENT {_ms_buckets.get("silent", 0)}'
            + '</div>'
            + '</div>'
            + '</div>'
        )
    except Exception:
        _macro_state_strate = ""
    vigie = (
        '<section data-page="vigie" class="active" role="region" aria-label="Overview"><div class="phead"><h2>Overview</h2>'
        '<div class="sub">Discipline posture &middot; what to act on today</div></div>'
        # === Star Vue d'ensemble (unifie) : valeur+PnL+capital sous-jacent
        # a gauche, grade A+ + bar a droite. Strate 2 = repartition lignes
        # pleine largeur. Gradecard detail retire (vide visuel).
        + '<div class="page-star">'
        + '<div class="ps-strate">'
        + '<div class="ps-hero-row">'
        + '<div class="ps-hero-left">'
        + '<div class="ps-lbl">Portfolio value</div>'
        + '<div class="ps-macro-row" style="align-items:baseline">'
        + f'<div class="ps-val" style="font-size:37px">{pf_val_str}&nbsp;&euro;</div>'
        + f'<div class="ps-val {_pnl_star_cls}" style="font-size:21px">{pf_arrow}&nbsp;{pf_pe}&nbsp;&euro; ({"+" if port_pnl >= 0 else ""}{port_pnl:.1f}%)</div>'
        + f'{_sparkline}'
        + '</div>'
        + f'<div class="ps-sub-lien">{_val_delta_str}</div>'
        + '</div>'
        + '<div class="ps-hero-right">'
        + '<div class="ps-lbl" data-tip="Global Construction + Fragility grade. Construction = Solidity/Bet/Overlap/Calibration. Fragility = Health/cycle/valo. &gt;= 70 acc, &gt;= 50 warn, &lt; 50 bear.">Portfolio grade</div>'
        + '<div class="ps-grade-row">'
        + f'<div class="ps-grade-letter {_grade_color}">{_grade_letter}</div>'
        + f'<div class="ps-grade-score"><div class="ps-grade-num">{_grade_score}<span class="ps-grade-max">/100</span></div>'
        + f'<div class="ps-grade-bar"><div class="ps-grade-fill {_grade_color}" style="width:{_grade_score:.0f}%"></div></div></div>'
        + '</div></div>'
        + '</div></div>'
        # === Macro state strate 06/06 (Vigie connectee a shared.macro_state) ===
        + _macro_state_strate
        # D5 retire 02/06 user : "Capital investi" duplique avec Star Concentration.
        # Vigie garde valeur PF + grade en haut (suffisant pour posture).
        + f'</div>'
        # Track record + Sante distribution deplaces vers page "signaux"
        # (user feedback 01/06 : pilotage qualite des signaux groupe ensemble).
        # Reordre 01/06 soir (user feedback) : Opportunites + Mouvement
        # AU-DESSUS de "Etat -- lignes a examiner" (top risque). Lecture :
        # d'abord ce sur quoi agir (ops), puis ce qui bouge, puis ce qui
        # demande surveillance approfondie.
        # ── BLOC 1 : OPPORTUNITES -- proches target (winners en realisation) ──
        # D1 retire 02/06 : "Marges les plus faibles" duplique avec page Urgence.
        # Cure racine 09/06 : "Closest to target" filtre frac_raw < 100 (vraies
        # positions approchant) ; positions DÉPASSÉES vont dans panneau séparé
        # "Beyond target" (take-profit zone). Sémantiquement juste, plus de dot
        # "toujours au-dessus du target" dans le mauvais panneau.
        f'<div class="colhead"><span class="t">Closest to target</span><span class="a">approche &mdash; dot &lt; tick vert</span></div>'
        f'<div class="card pad">{gain}</div>'
        f'<div class="colhead"><span class="t">Beyond target</span><span class="a">prise de profit &mdash; dot &gt; tick vert</span></div>'
        f'<div class="card pad">{beyond}</div>'
        # ── BLOC 2 : MOUVEMENT DU JOUR -- restaure 02/06 user (winners/losers %) ──
        '<div class="vigie-sh" data-tip="Biggest movers over the last 24 hours (rolling, intraday-based when available)."><svg class="sh-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12l3-4 3 2 3-5 3 3"/></svg>Last 24h movers</div>'
        f'<div class="cols">'
        f'<div class="col"><div class="colhead"><span class="t">Top winners</span><span class="a">last 24h</span></div><div class="card pad">{_day_up}</div></div>'
        f'<div class="col"><div class="colhead"><span class="t">Top losers</span><span class="a">last 24h</span></div><div class="card pad">{_day_dn}</div></div>'
        f'</div>'
        # ── BLOC 3 : URGENCE -- positions en danger immediat (top risque) ──
        '<div class="vigie-sh" data-tip="Book positions to review first: critical margins (stop &lt; 10%), at_risk kill_criteria zones, blind vol."><svg class="sh-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6.5"/><path d="M8 4.5v3.5l2.5 1.5"/></svg>State &mdash; positions to review</div>'
        f'{_risk_watch_panel()}'
        f"{blind_html}"
        # Journal & deadlines retire 02/06 user (useless boards :
        # TEST_E2E_DEC pollue + deadlines disponibles ailleurs).
        f"</section>"
    )

    # ─── Page Strategie : lecture analytique du book (vocabulaire canonique) ───
    # Refonte 31/05 user feedback : retire placement fiscal + chat_signals + conversations
    # Ordre : declaration -> etat -> risques caches -> meta (4 sections au lieu de 5)
    # === Star Strategie : 4 axes lecture + conviction stats ===
    try:
        _t_rows = _q("SELECT conviction FROM theses WHERE status='active'")
        _conv_list = [int(r[0]) for r in _t_rows if r[0]]
        _n_act_t = len(_conv_list)
        _conv_med_s = sorted(_conv_list)[_n_act_t // 2] if _n_act_t else 0
        _n_c5_s = sum(1 for c in _conv_list if c == 5)
        _pct_c5_s = (_n_c5_s / _n_act_t * 100) if _n_act_t else 0
    except Exception:
        _n_act_t, _conv_med_s, _pct_c5_s = 0, 0, 0
    try:
        _n_bias_open_s = _q("SELECT COUNT(*) FROM bias_events WHERE status='open'")[0][0]
        _n_bias_resolved_s = _q("SELECT COUNT(*) FROM bias_events WHERE status='resolved'")[0][0]
    except Exception:
        _n_bias_open_s, _n_bias_resolved_s = 0, 0
    # Determine biais mecanise status : ✓ si au moins 1 surface lock_in cable
    _bias_msg = "lock_in (winners sold too early) + fomo_greed mechanized"
    _bias_cls = "acc"
    _med_cls = "acc" if _conv_med_s >= 4 else ("warn" if _pct_c5_s > 20 else "")
    star_strategie = (
        '<div class="page-star">'
        + '<div class="ps-strate">'
        + '<div class="ps-lbl">Book reading</div>'
        + '<div class="ps-macro-row">'
        + f'<div class="ps-val {_med_cls}">MEDIAN c{_conv_med_s}</div>'
        + f'<div class="ps-macro-meta">{_n_act_t} active theses &middot; {_n_c5_s} c5 ({_pct_c5_s:.0f}%)</div>'
        + '</div>'
        + '<div class="ps-cap">Declared vs book reading vs hidden risks &mdash; 3 levels below</div>'
        + '</div>'
        + '<div class="ps-strate ps-grid">'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Number of instrumented behavioral biases (automatic capture). lock_in = selling winners too early. fomo_greed = holding beyond top.">Mechanized biases</div><div class="ps-val {_bias_cls}">2</div><div class="ps-cap">{_bias_msg}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="bias_event candidates under observation (+30d window post-detection). Verdict frozen at +30d then enriched +60/+90.">Open biases</div><div class="ps-val">{_n_bias_open_s}</div><div class="ps-cap">events under observation</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Post-resolution bias events +30d with immutable canonical scoring. Enriched with +60/+90d observations per B3 architecture.">Resolved biases</div><div class="ps-val acc">{_n_bias_resolved_s}</div><div class="ps-cap">events post-resolution</div></div>'
        + '</div>'
        + '<div class="ps-strate ps-foot">'
        + 'Declared strategy &middot; book reading &middot; hidden risks below'
        + '</div>'
        + '</div>'
    )
    strategie_html = (
        '<section data-page="strategie" role="region" aria-label="Strategy"><div class="phead"><h2>Strategy</h2>'
        '<div class="sub">Declared reference &middot; trajectory vs plan &middot; positions beyond bull</div></div>'
        f'{star_strategie}'
        # 1. Strategie declaree -- referentiel (ce qu'on veut faire)
        '<div class="strat-sh" data-tip="What you wrote as objective (theses, horizon, conviction). The reference against which book is read."><svg class="sh-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2v12"/><path d="M3 3h7l-1.5 2.5L10 8H3"/></svg>Declared strategy &mdash; reference</div>'
        f'{_user_strategy_panel()}'
        # 2. Lecture du livre -- trajectoire vs declare
        '<div class="strat-sh" data-tip="Actual book trajectory vs declared plan."><svg class="sh-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="7" r="4.5"/><path d="M10.3 10.3L14 14"/></svg>Book reading &mdash; trajectory</div>'
        f'{trajectory_html}'
        # 3. Actionnable -- positions au-dessus du bull case (candidats fomo_greed)
        '<div class="strat-sh" data-tip="Positions beyond their bull case = trim candidates (mechanized via fomo_greed gate)."><svg class="sh-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2L14.5 13H1.5L8 2z"/><path d="M8 6.5v3.5"/><circle cx="8" cy="11.5" r=".7" fill="currentColor" stroke="none"/></svg>Beyond bull &mdash; trim candidates</div>'
        f'{valo_html}'
        # Retraits 02/06 user feedback (panneaux infinis rebarbatifs) :
        # factor_html / stress_html / spof_html / mauboussin_html /
        # _return_clustering_panel / axes_html -- code backend conserve,
        # donnees disponibles pour reactivation future.
        '</section>'
    )

    watch_zone_tk = [
        r["ticker"]
        for r in sorted(computed, key=lambda r: r.get("downside_pct", 999.0))
        if r.get("downside_pct") is not None and 10 <= r["downside_pct"] < 20
    ]
    # === Star Positions : posture portefeuille en 3 strates ===
    # Recompute sizing context (_sfac + size_txt) localement -- defini dans
    # _urgence() seulement, pas accessible ici. Source unique = VIX courant.
    try:
        _vix_p = _cached_price_native("^VIX") or 0
    except Exception:
        _vix_p = 0
    try:
        _rk_p = _cfg().get("risk", {})
        _vthr_p = float(_rk_p.get("vol_scaling_threshold_vix", 21))
        _vsf_p = float(_rk_p.get("vol_scaling_factor", 0.7))
        # v5 audit pro : 2-tier scaling (VIX panique > 30 -> halve).
        from shared.calibration import get_drawdown_thresholds
        _dd_p = get_drawdown_thresholds()
        _vthr_panic_p = float(_dd_p.get("vol_scaling_vix_panic_threshold") or 30.0)
        _vsf_panic_p = float(_dd_p.get("vol_scaling_vix_panic_factor") or 0.5)
    except Exception:
        _vthr_p, _vsf_p = 21.0, 0.7
        _vthr_panic_p, _vsf_panic_p = 30.0, 0.5
    _panic_p = _vix_p and _vix_p >= _vthr_panic_p
    _reduced_p = _vix_p and _vix_p >= _vthr_p
    if _panic_p:
        _sfac = _vsf_panic_p
        size_txt = f"VIX {_vix_p:.1f} &ge; {_vthr_panic_p:.0f} PANIC (sizing x{_vsf_panic_p:.1f})"
    elif _reduced_p:
        _sfac = _vsf_p
        size_txt = f"VIX {_vix_p:.1f} &ge; {_vthr_p:.0f} stress (sizing x{_vsf_p:.1f})"
    else:
        _sfac = 1.0
        size_txt = f"VIX {_vix_p:.1f} &lt; {_vthr_p:.0f} normal" if _vix_p else "VIX indisponible"
    n_stop, n_watch, n_tgt = len(near_stop_tk), len(watch_zone_tk), len(near_tgt_tk)
    if n_stop:
        _post_cls, _post_lbl = "bear", "ALERT"
        _post_cap = f"{n_stop} position(s) at stop &lt; 10% &middot; check before session"
    elif n_watch:
        _post_cls, _post_lbl = "warn", "WATCH"
        _post_cap = f"{n_watch} position(s) in 10-20% from stop zone &middot; remaining margin"
    elif n_tgt:
        _post_cls, _post_lbl = "acc", "TAKE&nbsp;PROFIT"
        _post_cap = f"{n_tgt} position(s) near a level"
    else:
        _post_cls, _post_lbl = "acc", "AT&nbsp;REST"
        _post_cap = "no position en zone critique &middot; surveiller la drift"
    _star_stop_cls = "bear" if n_stop else "acc"
    _star_watch_cls = "warn" if n_watch else "acc"
    _star_tgt_cls = "warn" if n_tgt else "acc"
    star_strate_post = (
        '<div class="ps-strate">'
        + '<div class="ps-lbl">Positions posture</div>'
        + '<div class="ps-macro-row">'
        + f'<div class="ps-val {_post_cls}">{_post_lbl}</div>'
        + f'<div class="ps-macro-meta">{len(positions)} positions &middot; sizing &times;{_sfac:.1f}</div>'
        + "</div>"
        + f'<div class="ps-cap">{_post_cap}</div>'
        + "</div>"
    )
    _stop_caption = (", ".join(near_stop_tk[:3]) + ("…" if len(near_stop_tk) > 3 else "")) if near_stop_tk else "none"
    _watch_caption = (", ".join(watch_zone_tk[:3]) + ("…" if len(watch_zone_tk) > 3 else "")) if watch_zone_tk else "none"
    _tgt_caption = (", ".join(near_tgt_tk[:3]) + ("…" if len(near_tgt_tk) > 3 else "")) if near_tgt_tk else "none"
    star_strate_grid = (
        '<div class="ps-strate ps-grid">'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Positions less than 10% from stop trigger. Critical margin: review thesis or trailing stop before session.">At stop &lt;10%</div><div class="ps-val {_star_stop_cls}">{n_stop}</div><div class="ps-cap">{_stop_caption}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Intermediate alert zone 10-20% from stop. Watch, no immediate action.">Watch 10-20%</div><div class="ps-val {_star_watch_cls}">{n_watch}</div><div class="ps-cap">{_watch_caption}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl" data-tip="Positions less than 12% from target (target_full). Take-profit zone for winners with valo &gt; bull.">Near target</div><div class="ps-val {_star_tgt_cls}">{n_tgt}</div><div class="ps-cap">{_tgt_caption}</div></div>'
        + "</div>"
    )
    star_strate_foot = (
        '<div class="ps-strate ps-foot">'
        + f'{size_txt} &middot; sizing <b>&times;{_sfac:.1f}</b>'
        + "</div>"
    )
    star_positions = (
        f'<div class="page-star">{star_strate_post}{star_strate_grid}{star_strate_foot}</div>'
    )
    broker_html = _broker_tables(positions, names, pnl, sectors)
    positions_pg = (
        f'<section data-page="positions" role="region" aria-label="Positions"><div class="phead"><h2>Positions</h2>'
        f'<div class="sub">Upside margin to target &middot; downside to stop</div></div>'
        f"{star_positions}{broker_html}</section>"
    )

    # --- Bandeau d'ecart de discipline (sticky, haut de page) ---
    # v1: axe concentration (cluster hors cap, source unique _cluster_health) + axe stop (near).
    # axe prise-profit -> ajoute apres ADR target_partial.
    # E4 craft 31/05 : "A CALIBRER" -> "A AJUSTER" (eviter confusion avec
    # calibration scorer). Smart routing : si seulement clusters -> nav
    # concentration ; si seulement stops -> nav risque ; sinon concentration
    # par defaut. Title= breakdown explicite.
    _dev_items = []  # liste de (label, nav_target)
    for _c in _cluster_health(positions, pnl):
        if _c["breached"]:
            _ov = f"{_c['over_eur']:,.0f}".replace(",", "&#8239;")
            _dev_items.append(
                (f"trim {_c['name']} &middot; +{_ov}&#8239;&euro;", "concentration")
            )
    if near:
        _dev_items.append((f"{near} position(s) &lt; 10% from stop", "risque"))
    _dn = len(_dev_items)
    _dcls, _dverdict = ("bear", "FRICTIONS") if _dn else ("acc", "ALIGNED")
    _ddetail = (
        " &nbsp;&middot;&nbsp; ".join(item[0] for item in _dev_items)
        if _dev_items else "all under rules"
    )
    # Nav target : si tous les items pointent au meme endroit, on y va direct.
    # Sinon, on tombe sur concentration (la "premiere" categorie historique).
    _nav_targets = {item[1] for item in _dev_items}
    _nav_target = next(iter(_nav_targets)) if len(_nav_targets) == 1 else "concentration"
    # Title= breakdown explicite pour ergonomie (cf charte E4 §5.1)
    _dtitle = (
        " ; ".join(item[0].replace("&middot;", "·").replace("&eacute;", "é")
                   .replace("&Agrave;", "À").replace("&agrave;", "à")
                   .replace("&euro;", "€").replace("&#8239;", " ")
                   .replace("&lt;", "<").replace("&nbsp;", " ")
                   for item in _dev_items)
        if _dev_items else "none friction de discipline"
    )
    _dband = (
        f'<div class="dband {_dcls}" title="{_dtitle}" '
        f'onclick="document.querySelector(&#39;[data-nav={_nav_target}]&#39;).click()">'
        f'<span class="dd"></span><span class="dv">{_dverdict}</span>'
        f'<span class="dx">{_ddetail}</span>'
        f'<span class="dn">{_dn} axe(s)</span><span class="dc">&rsaquo;</span></div>'
    )
    elan, near_t = _elan_watch(computed)
    body = (
        f'<aside class="sidebar" role="complementary" aria-label="Barre laterale"><div class="logo">{_LOGO}<span class="wm">PRESAGE<small>intelligence &middot; signal &middot; advantage</small></span></div>'
        f'{_NAV}<div class="foot">'
        f'{_FOOT_METHOD}<div class="foot-sep"></div>{_MODE_BTN}'
        f'</div></aside>{_SORT_JS}{_CSORT_JS}{_DONUT_JS}'
        f'<div class="wrap">{tape}{tape8k}<main class="main">{_dband}'
        + vigie
        + positions_pg
        + _concentration(positions, planned, sectors, names, pnl, daily)
        + _theses(names, sectors, positions, pnl)
        + strategie_html
        + _signaux()
        + _urgence(watch, near, positions, pnl, elan, near_t)
        + _copilot()
        # Position-card #1 couche 3 : section deep-linkable par ticker.
        # Acces via nav (a ajouter dans _NAV) OU via hash #card-TICKER deep-link.
        + _position_card_panel()
        + "</main></div>"
        + _LOUPE_HTML
    )

    html = (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta http-equiv="refresh" content="1800">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><script>try{if(sessionStorage.getItem("h_seen"))document.documentElement.classList.add("noanim");sessionStorage.setItem("h_seen","1");}catch(e){}</script><title>PRESAGE</title><link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg%20viewBox%3D%220%200%2064%2064%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%3E%3Crect%20width%3D%2264%22%20height%3D%2264%22%20rx%3D%2214%22%20fill%3D%22%230c0c0e%22%2F%3E%3Cg%20transform%3D%22translate%288.00%2C19.57%29%20scale%280.13079%29%22%20fill%3D%22%23ECEFF4%22%3E%3Cg%20transform%3D%22translate%280.000000%2C190.000000%29%20scale%280.100000%2C-0.100000%29%22%20%20stroke%3D%22none%22%3E%20%3Cpath%20d%3D%22M1335%201890%20c-11%20-4%20-200%20-189%20-419%20-409%20l-399%20-401%20251%200%20250%200%20254%20260%20253%20260%2071%200%2071%200%2058%20-62%20c32%20-35%20168%20-174%20301%20-309%20l242%20-246%2069%20-7%20c37%20-4%20148%20-11%20246%20-16%2098%20-4%20181%20-11%20184%20-14%204%20-3%20-45%20-6%20-108%20-6%20-63%200%20-175%20-5%20-249%20-10%20l-135%20-11%20-72%20-72%20c-40%20-39%20-73%20-76%20-73%20-82%200%20-6%2051%20-61%20114%20-124%20l113%20-113%20184%20187%20184%20186%20330%209%20c182%205%20394%209%20473%2010%20l142%200%200%2030%200%2030%20-127%201%20c-71%201%20-284%204%20-474%207%20l-346%207%20-87%2082%20c-47%2045%20-126%20129%20-175%20186%20-131%20153%20-581%20617%20-609%20628%20-29%2011%20-490%2011%20-517%20-1z%22%2F%3E%20%3Cpath%20d%3D%22M2308%201888%20c-9%20-7%20-26%20-33%20-37%20-58%20-12%20-25%20-44%20-68%20-72%20-97%20l-51%20-52%20105%20-108%20105%20-107%2064%2067%2063%2067%2072%200%2071%200%20253%20-260%20252%20-260%20244%200%20c238%200%20244%200%20231%2019%20-23%2032%20-760%20775%20-782%20788%20-30%2018%20-496%2018%20-518%201z%22%2F%3E%20%3Cpath%20d%3D%22M1693%201259%20c-54%20-61%20-109%20-127%20-123%20-145%20-14%20-19%20-51%20-54%20-83%20-78%20l-58%20-43%20-487%20-7%20c-268%20-3%20-589%20-9%20-715%20-13%20-207%20-5%20-227%20-7%20-227%20-23%200%20-16%2024%20-18%20298%20-24%20163%20-4%20488%20-11%20721%20-17%20l424%20-10%2061%20-44%20c89%20-63%20148%20-125%20236%20-250%2053%20-75%20150%20-184%20305%20-345%20125%20-129%20237%20-240%20249%20-247%2015%20-9%2095%20-12%20276%20-13%20l254%200%20411%20410%20410%20410%20-245%200%20-245%200%20-255%20-255%20-255%20-255%20-81%200%20-80%200%20-244%20253%20c-309%20320%20-340%20349%20-388%20353%20-20%201%20-91%208%20-157%2013%20-66%206%20-176%2011%20-245%2012%20-149%202%20-118%2016%2039%2018%2056%200%20169%206%20250%2012%20l146%2011%2073%2071%20c39%2040%2071%2075%2070%2079%20-5%2013%20-221%20238%20-229%20238%20-4%200%20-52%20-50%20-106%20-111z%22%2F%3E%20%3Cpath%20d%3D%22M715%20618%20c110%20-112%20290%20-295%20402%20-408%20l202%20-205%20161%20-3%20c182%20-4%20206%203%20285%2077%2052%2049%20126%2093%20193%20115%20l54%2018%20-112%20112%20-111%20111%20-58%20-62%20-57%20-63%20-81%200%20-80%200%20-176%20178%20c-96%2097%20-208%20212%20-247%20255%20l-72%2077%20-251%200%20-251%200%20199%20-202z%22%2F%3E%20%3C%2Fg%3E%3C%2Fg%3E%3C%2Fsvg%3E">'
        ""
        # Geist auto-hosted depuis dashboard/static/fonts/ (cf tokens.css
        # @font-face block). No CDN Google Fonts (zero round-trip externe,
        # zero tracking, souveraine).
        ''
        "<style>"
        + _TOKENS_CSS
        + _CSS
        + "</style>"
        # _THEME_INIT injecte AVANT </head> -> applique la class midnight
        # AVANT le paint initial, evite FOUC light->dark sur chaque refresh.
        + _THEME_INIT
        + "</head><body>"
        + body
        + "<script>window.TK="
        + json.dumps(loupe_data)
        + ";window.SB_DATA="
        + json.dumps(sb_data)
        + ";</script>"
        + ""
        + "<script>"
        + _APP_JS.replace("__TKDOMAIN_JSON__", json.dumps(_ticker_logos_mod.TICKER_DOMAIN)).replace("__TKLOCAL_JSON__", json.dumps(_ticker_logos_mod._scan_local_logos()))
        + "</script>"
        # Live-reload : poll Last-Modified toutes les 1s (vs 600s ancien). User
        # spec close-session : "Live-reload + Geist auto-hebergé = maintenant
        # (30 min, ca accelere tout le reste)". Iteration design instantanee
        # vs regen 60s. isTyping protege la zone chat. Charge negligeable
        # (HEAD request, 1KB, local serve.py).
        # #93 phase B : LLM status badge fixe bottom-right (resilience surface).
        + _llm_status_badge()
        # Sprint 4 CTA flottant bas : Recherche seule (Compact + Filtrer retires
        # 01/06 user feedback : Compact none interet, Filtrer no utilite plug)
        + '<div class="cta-bar" role="toolbar" aria-label="Recherche rapide">'
        + '<button id="ctaSearch" title="Search (Cmd+K)"><span aria-hidden="true">&#9906;</span> Search</button>'
        + "</div>"
        + '<div class="cta-modal" id="ctaSearchModal" role="dialog" aria-modal="true" aria-label="Recherche ticker">'
        + '<div class="cta-modal-inner">'
        + '<input class="cta-search-input" id="ctaSearchInput" placeholder="Ticker ou nom de societe..." autocomplete="off" spellcheck="false" />'
        + '<div class="cta-search-chips" id="ctaSearchChips"></div>'
        + '<div class="cta-search-results" id="ctaSearchResults"></div>'
        + "</div></div>"
        + "<script>"
        + _CTA_JS
        + "</script>"
        + "<script>(function(){var b=null;function isTyping(){var ta=document.getElementById('chat-input');if(ta&&ta.value.trim().length>0)return true;if(ta&&document.activeElement===ta)return true;return false;}function c(){if(isTyping())return;fetch(location.pathname,{method:'HEAD',cache:'no-store'}).then(function(r){var m=r.headers.get('Last-Modified');if(m){if(b===null)b=m;else if(m!==b)location.reload();}}).catch(function(){});}setInterval(c,1000);})();</script>"
        # Hover continuous sur les .tbar : displays valeur under cursor.
        # MODES :
        #   - axis-mode="price" (axe-prix EUR) : affiche "€X.XX" (prix interpolé)
        #   - axis-mode absent (axe-perf legacy, data-axmin/axmax = % signed) :
        #     affiche "+X.X%" / "-X.X%" signed depuis 0 logique
        #   - sinon : affiche position % visuelle
        # Cure 09/06 23h+ : le mode "price" résout le bug "+1820%" au hover
        # quand axmax=1820 EUR (bornes prix interprétées comme %).
        + "<script>(function(){function fmtPct(v){var s=v>=0?'+':'\\u2212';return s+Math.abs(v).toFixed(1)+'%';}function fmtEur(v){return v.toLocaleString('fr-FR',{style:'currency',currency:'EUR',maximumFractionDigits:2});}function wire(){document.querySelectorAll('.tbar').forEach(function(bar){var tip=bar.querySelector('.tbar-hover-tip');if(!tip||bar.dataset.tbarWired)return;bar.dataset.tbarWired='1';var axmin=parseFloat(bar.dataset.axmin);var axmax=parseFloat(bar.dataset.axmax);var mode=bar.dataset.axisMode||'';var hasAxis=!isNaN(axmin)&&!isNaN(axmax);bar.addEventListener('mousemove',function(e){var r=bar.getBoundingClientRect();if(r.width<=0)return;var p=Math.max(0,Math.min(100,(e.clientX-r.left)/r.width*100));tip.style.left=p.toFixed(1)+'%';if(hasAxis){var v=axmin+(axmax-axmin)*(p/100);if(mode==='price'){tip.textContent=fmtEur(v);tip.classList.remove('pos','neg');}else{tip.textContent=fmtPct(v);tip.classList.toggle('pos',v>0.05);tip.classList.toggle('neg',v<-0.05);}}else{tip.textContent=p.toFixed(0)+'%';tip.classList.remove('pos','neg');}});});}wire();new MutationObserver(wire).observe(document.body,{childList:true,subtree:true});})();</script>"
        + "</body></html>"
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        if OUTPUT.exists() and OUTPUT.read_text() == html:
            return OUTPUT
    except OSError:
        pass
    OUTPUT.write_text(html)

    # LIVING GRAPH W0 (#110, SPEC §3.3+§4) : detect_forks au regen-end.
    # Le regen EST le battement -- les producteurs canoniques (ledger_pmp,
    # BookLine helpers...) viennent de tourner et register_concept'd leurs
    # valeurs. Si fork détecté au-delà ε du concept (concept_keys.yaml) ->
    # log WARN + Telegram alert OPS analogue L29 fail-loud. Silent-miss L7
    # si living_graph indispo (n'impacte pas le render).
    try:
        from shared.living_graph import detect_forks
        _forks = detect_forks()
        if _forks:
            import logging as _lg
            _lg.getLogger("dashboard").warning("LIVING_GRAPH forks detected (n=%d): %s",
                                                len(_forks), _forks)
            try:
                from shared import notify
                _lines = [f"[OPS] LIVING_GRAPH fork détecté ({len(_forks)} concept(s))"]
                for f in _forks[:5]:
                    cands = ", ".join(f"{c['source']}={c['value']:.6g}" for c in f["candidates"])
                    _lines.append(
                        f"- {f['concept_key']} {f['ticker'] or 'global'} {f['bucket']} "
                        f"| Δ={f['max_div_rel']:.3%} > ε={f['epsilon_rel']:.3%} | {cands}"
                    )
                notify.send_text("\n".join(_lines))
            except Exception:
                pass
    except Exception:
        pass

    return OUTPUT


if __name__ == "__main__":
    p = render()
    print(f"[OK] {p} ({p.stat().st_size} bytes)")
