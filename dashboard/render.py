"""PRESAGE dashboard. Static-gen, READ-ONLY, REAL data.
Weights from positions.eur_invested (EUR cost basis). Sectors from theses.sector_thesis_id.
Perf as ratio % (currency-invariant). DB read-only; per-panel try/except. Leaflet geo."""

# Sprint 3 logos tickers : import + force-reload pour bypass cache sys.modules
# tant que serve.py n'est pas restart pour activer le nouveau watch.
import importlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import yaml

import shared.ticker_logos as _ticker_logos_mod
from dashboard._scripts import (
    _APP_JS,
    _CSORT_JS,
    _CTA_JS,
    _DONUT_JS,
    _EU_SUFFIX,
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
POS_CAP = float(_CFG.get("style", {}).get("position_max_pct", 0.05)) * 100
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
    # Variation % du jour (cloture veille -> dernier close). Invariant en devise: none conversion FX.
    import time as _t

    now = _t.monotonic()
    hit = _DP_CACHE.get(ticker)
    if hit is not None and now - hit[1] < _DP_TTL:
        return hit[0]
    v: float | None = hit[0] if hit is not None else None
    try:
        import yfinance as yf

        closes = yf.Ticker(ticker).history(period="5d", interval="1d")["Close"].dropna()
        if len(closes) >= 2:
            v = round((float(closes.iloc[-1]) / float(closes.iloc[-2]) - 1.0) * 100.0, 1)
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
        '<div class="card pad v2cohortcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Cohort V2 vs V1 (scorer pivot 30/05)</span>'
        '<span class="a">V2 = SEC EDGAR primary content &middot; V1 = newsletter sentiment (mono-bucket)</span></div>'
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
            '<div class="card pad calibcard" style="margin-bottom:var(--s4)">'
            '<div class="colhead"><span class="t">Calibration scorer V2</span>'
            f'<span class="a">cohort accumulation &mdash; verdict activates at n&ge;{target} non-neutral resolved predictions</span></div>'
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
        '<div class="card pad calibcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Calibration scorer V2</span>'
        f'<span class="a">verdict reliability + Brier moyen sur cohorte n={n_total}</span></div>'
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
        '<div class="card pad wactcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Wire EDGAR activity</span>'
        '<span class="a">8-K + insider clusters arrived in the V2 scoring pipeline</span></div>'
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
        '<div class="card pad vgcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Vigilances V2</span>'
        '<span class="a">3 fitness functions auto &middot; cron weekly lundi 7h &middot; push Telegram UNIQUEMENT si ALERT/WARN</span></div>'
        + "".join(rows) +
        "</div>"
    )


def _risk_watch_panel() -> str:
    """Top Risks declares - first-class surveillance sur Vue d'ensemble.

    Lit scripts/risk_watch.json (declaration user) + status courant des
    mitigations + signals surveillance. Pas une opinion bot, juste tracking
    de ce que l'user a explicitement designe comme risque #1.
    """
    try:
        from pathlib import Path

        risks = json.loads(Path("scripts/risk_watch.json").read_text())
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
            f'<div class="rw-cell"><div class="rw-h">Strict decorrelated ballast</div>'
            f'<div class="rw-v mono">{target.get("current_ballast_strict_pct", "?")}%</div>'
            f'<div class="rw-t">target: {target.get("target_ballast_strict_pct", "?")}%</div></div>'
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
        '<div class="card pad riskwatchcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Top Risks watch</span>'
        f'<span class="a">{len(risks_list)} declared risk(s) &middot; thesis-level reflection</span></div>'
        f'{construction_lens}'
        + "".join(out)
        + "</div>"
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
        '<div class="card pad gradecard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Portfolio grade</span>'
        f'<span class="a">{snapshot_date} &middot; {trend_str}</span></div>'
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
        '<div class="card pad blindcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Positions en vol disclosuregle</span>'
        f'<span class="a">{len(blind)} position(s) sans entry / target / stop / kill-criteria '
        '&middot; le bot ne peut RIEN evaluer dessus tant que ces champs sont creux</span></div>'
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
        '<div class="card pad copilotcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Copilot pressure before trades</span>'
        '<span class="a">hover/click a row for full diagnostic &middot; mechanical verdict before each action</span></div>'
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
        '<div class="card pad clustercard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Overlaps seen by prices</span>'
        f'<span class="a">{snapshot_date} &middot; returns correlation &middot; what truly moves together</span></div>'
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
        '<div class="card pad wrappercard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Placement fiscal (PEA / CTO)</span>'
        '<span class="a">tax-loss harvest + flag PEA-eligibles mal places</span></div>'
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
        '<div class="card pad fxcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Exposition par devise</span>'
        '<span class="a">click a row to expand positions &middot; no FX hedge</span></div>'
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
        '<div class="card pad benchcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Real outperformance vs sector</span>'
        f'<span class="a">{bench["bench_window"]} &middot; book vs indice semi-conducteurs PHLX</span></div>'
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
        '<div class="card pad killcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Conditions d\'invalidation des theses</span>'
        f'<span class="a">triggered {counts["triggered"]} &middot; at risk {counts["at_risk"]} &middot; '
        f'dormant {counts["dormant"]} &middot; checked 07:30</span></div>'
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
        '<div class="card pad spofcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Hidden upstream dependencies</span>'
        '<span class="a">if an upstream supplier breaks, everything depending on it breaks too</span></div>'
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
        '<div class="card pad mauboussincard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Rigorous calibration</span>'
        '<span class="a">real size vs theoretical size (conviction &times; moat erosion speed)</span></div>'
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
        '<div class="card pad valocard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Valuations already beyond bull case</span>'
        '<span class="a">current price requires more than a reasonable bull case</span></div>'
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
        '<div class="card pad factorscard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Bets du portefeuille</span>'
        '<span class="a">what you really bet on, by macro factor &middot; a single big bet dominates</span></div>'
        + "".join(rows)
        + "</div>"
    )


def _stress_tests_panel() -> str:
    """Sprint 13 — scenarios deterministes appliques sur les factor exposures."""
    try:
        from intelligence import factor_exposures as _fe

        results = _fe.run_all_stress_tests()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">stress indispo: {type(e).__name__}</div></div>'
    rows = []
    for s in results:
        if "error" in s:
            continue
        scenario = s["scenario"]
        dd_pct = s["total_drawdown_pct"]
        dd_eur = s["total_drawdown_eur"]
        n = s.get("n_positions_affected", 0)
        dcls = "pos" if dd_pct > 0 else ("danger" if dd_pct < -5 else "warn" if dd_pct < 0 else "neu")
        rows.append(
            f'<div class="st-row">'
            f'<div class="st-name">{scenario}</div>'
            f'<div class="st-impact"><span class="st-pct {dcls} mono">{dd_pct:+.1f}%</span>'
            f'<span class="st-eur mono">{dd_eur:+,.0f}€</span>'
            f'<span class="st-n">n={n}</span></div></div>'
        )
    return (
        '<div class="card pad stresscard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Si tel pari rate</span>'
        '<span class="a">drawdown estime par scenario macro &middot; transforme le 73% en chiffre concret</span></div>'
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
    archetype = us.get("archetype", "?")
    desc = us.get("description", "")
    cap = us.get("target_cluster_cap_pct", 35)
    dec = us.get("target_decorrelation_pct", 15)
    bench = us.get("benchmark_ticker", "?")
    horizon = us.get("thesis_horizon_years", "?")
    accepted = us.get("accepted_concentrated_factors") or []
    declared = us.get("declared_at", "?")
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
            from pathlib import Path

            from intelligence.portfolio_grade import _fetch_state

            rw = json.loads(Path("scripts/risk_watch.json").read_text())
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
        '<div class="card pad strategiecard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Your declared strategy</span>'
        f'<span class="a">archetype = {archetype} &middot; depuis {declared} &middot; surcharge les defaults</span></div>'
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
        '<div class="card pad trajcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Grade drift (30d)</span>'
        f'<span class="a">{len(snaps)} photos &middot; '
        f'{score_drift.get("first_date","?")} → {score_drift.get("last_date","?")}</span></div>'
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
        '<div class="card pad axescard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Fiches techniques par ticker</span>'
        '<span class="a">demand engine &middot; value chain layer &middot; moat nature &middot; macro factor</span></div>'
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
        '<div class="card pad preferencescard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">What worked for you</span>'
        '<span class="a">samples + winrate on your real resolved decisions &middot; no model opinion</span></div>'
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
        '<div class="card pad conceptionscard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Ce que le bot pense par ticker</span>'
        '<span class="a">stable per-ticker summary updated weekly '
        '&middot; survole ou clique pour expand</span></div>'
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
        '<div class="card pad chatsigcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">What you let slip in conversation</span>'
        '<span class="a">concerns / doubts / views the bot captures each message &middot; feeds your profile</span></div>'
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
        '<div class="card pad conversationscard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Historique chat</span>'
        '<span class="a">all logged and re-integrated into profile over time</span></div>'
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
        '<div class="card pad narrativecard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Clusters narratifs (LLM)</span>'
        f'<span class="a">{raw.get("snapshot_date","?")} &middot; consume par T2 + decorrelation du grade</span></div>'
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
        '<div class="card pad" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Distribution health</span>'
        '<span class="a">extension scaffold ROUGE/ORANGE/VERT ops &mdash; data &middot; cron weekly Mon 7h push Telegram si !OK</span></div>'
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

        cx = _sql.connect(_q.__globals__["DB_PATH"]) if "DB_PATH" in _q.__globals__ else _sql.connect("data/bot.db")
        rows = cx.execute(
            "SELECT outcome, brier_score FROM predictions "
            "WHERE resolved_at IS NOT NULL AND outcome IN ('correct','incorrect') "
            "AND methodology_version != 'v0'"
        ).fetchall()
        open_n = cx.execute(
            "SELECT COUNT(*) FROM predictions WHERE resolved_at IS NULL "
            "AND methodology_version != 'v0'"
        ).fetchone()[0]
        v0_n = cx.execute(
            "SELECT COUNT(*) FROM predictions WHERE methodology_version = 'v0'"
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
    if n < MIN_CONCLUSIF:
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
    brier_marker = (
        f'<div class="axis-mark" style="left:{min(99.0, brier_frac):.1f}%" title="Brier {brier_mean:.3f} sur 0&ndash;0,5"></div>'
        if brier_frac is not None else ""
    )
    rate_pct = f"{n_corr/n:.0%}" if n else "&mdash;"

    return (
        f'<div class="card pad tr-card" style="margin-bottom:var(--s4)">'
        f'<div class="colhead"><span class="t">Track record</span>'
        f'<span class="a">N={n} substantial &middot; honest-early disclosure if N&lt;{MIN_CONCLUSIF}</span></div>'
        # Metric 1 : Taux correct (axe 0->100%)
        f'<div class="tr-metric">'
        f'<div class="tr-mlabel"><span class="tr-mname">Taux correct</span>'
        f'<span class="tr-mval mono">{n_corr}<span class="tr-mvsep">/</span>{n}</span>'
        f'<span class="tr-munit">soit {rate_pct}</span></div>'
        f'<div class="axis">'
        f'<div class="axis-mark" style="left:{rate_frac:.1f}%" title="{rate_pct} correct"></div>'
        f'</div>'
        f'<div class="tr-mfoot"><span class="mono">IC95% {ci_str.replace("IC95% ", "")}</span>'
        f'<span class="tr-verdict">{rate_verdict}</span></div>'
        f'</div>'
        # Metric 2 : Brier rolling (axe 0->0.5, target 0.20)
        f'<div class="tr-metric">'
        f'<div class="tr-mlabel"><span class="tr-mname">Brier rolling</span>'
        f'<span class="tr-mval mono">{brier_str}</span>'
        f'<span class="tr-munit">sur 0&ndash;0,5</span></div>'
        f'<div class="axis tr-axis-brier">'
        f'<div class="tr-axref" style="left:{brier_target_x:.0f}%" title="target 0,20"></div>'
        f'{brier_marker}'
        f'</div>'
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
        # Pipeline state -- plat, honnete
        f'<div class="tr-pipe mono">'
        f'<span><b>{n}</b> resolved(s)</span><span class="tr-sep">&middot;</span>'
        f'<span><b>{open_n}</b> en attente (hors v0)</span><span class="tr-sep">&middot;</span>'
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
        f'<div class="phead"><h2>Copilot</h2>'
        f'<div class="sub">Chat &middot; adversarial interventions summary</div></div>'
        f'{_chat_panel()}'
        f'<div class="vigie-sh" data-tip="Historical adversarial pressure tests: what the copilot challenged recently."><svg class="sh-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2C5 2 3 4 3 6.5c0 1.5.8 2.8 2 3.6V12c0 .6.4 1 1 1h4c.6 0 1-.4 1-1v-1.9c1.2-.8 2-2.1 2-3.6C13 4 11 2 8 2z"/><path d="M6 13v1c0 .5.4 1 1 1h2c.6 0 1-.5 1-1v-1"/></svg>Pressions adversariales</div>'
        f'{_copilot_panel()}'
        f'</section>'
    )


def _chat_panel() -> str:
    """Sprint 7 — Chat surface : pose une question, contexte assemble cote serveur."""
    n_msg, n_sess, oldest = _chat_memory_stats()
    mem_str = (
        f"it knows your profile, PF grade, positions, theses, "
        f"interventions &middot; memory : {n_msg} messages on {n_sess} sessions since {oldest}"
        if n_msg > 0 else
        "it knows your profile, PF grade, positions, theses and intervention history"
    )
    return (
        '<div class="card pad chatcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Ask the copilot</span>'
        f'<span class="a">{mem_str}</span></div>'
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


def _positions() -> list[dict]:
    """MIGRATED 29/05 round 2 -- lit shared.book canonical (commit cf book.py).

    Avant : weight = qty * avg_cost (cost basis) OU eur_invested du notes.
    Apres : weight = MARKET VALUE (qty * current_price_eur). C'est la fix
    de F11 racine : tous les lecteurs en aval voient le meme poids que
    portfolio_grade -- plus de "AMD 3.4% vs 1.4% selon vue".

    Shape backward-compat etendue :
        ticker (str) -- unchange
        weight (float, EUR) -- MARKET VALUE (avant : cost basis)
        avg_cost (float, EUR/share) -- unchange
        wrapper (str) -- unchange
        # nouveaux pour les lecteurs qui veulent l'autre info :
        qty (float)
        current_price_eur (float | None)
        cost_basis_eur (float, EUR) -- l'ancien sens de "weight"
    """
    try:
        from shared import book as _bk
    except Exception:
        return []
    out = []
    for ln in _bk.get_held_lines():
        cost_basis = (ln.qty or 0) * (ln.avg_cost_eur or 0)
        out.append({
            "ticker": ln.ticker,
            "weight": ln.weight_market_eur,  # MARKET VALUE (was cost basis)
            "avg_cost": float(ln.avg_cost_eur or 0),
            "wrapper": (ln.wrapper or "CTO").upper(),
            "qty": float(ln.qty or 0),
            "current_price_eur": ln.current_price_eur,
            "cost_basis_eur": cost_basis,
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


def _pnl_cost_map(positions: list[dict]) -> dict:
    out: dict = {}
    for p in positions:
        ac = p.get("avg_cost") or 0
        if ac <= 0:
            continue
        try:
            c = _cached_price_eur(p["ticker"])
        except Exception:
            c = None
        if c:
            out[p["ticker"]] = (c - ac) / ac * 100
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
            f'<div class="axis"><div class="axis-mark" style="left:{pc:.1f}%" title="{pc:.1f}%"></div></div>'
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


def _rows_risque(computed: list[dict]) -> tuple[str, int, float, str]:
    data = sorted(((r.get("downside_pct", 0), r["ticker"]) for r in computed), key=lambda x: x[0])
    tensions = [max(0.0, min(1.0, (20 - d) / 20)) for d, _ in data]
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
            f'<div class="axis"><div class="axis-mark" style="left:{buf:.1f}%" title="{buf:.1f}%"></div></div>'
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
    _conc = yaml.safe_load(Path("config.yaml").read_text()).get("concentration", {})
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
        f'<div class="sub">Three concentration axes &mdash; by position, by sector, by geography</div></div>'
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
    sub = (
        f"Held {real_t:.0f}&euro; &middot; planned {plan_t:.0f}&euro; &middot; "
        f"total {total:.0f}&euro; (${total / fx:.0f}) &middot; {len(order) + (1 if compute_sub else 0)} groups"
    )
    return (
        f'<div class="sub" style="margin-bottom:var(--s25)">{sub}</div>'
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
            f'<div class="axis"><div class="axis-mark" style="left:{max(2.0, min(100.0, pct)):.1f}%" title="{pct:.1f}%"></div></div>'
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
        # All predictions last 60d with source name
        preds = _q(
            "SELECT p.id, p.ticker, p.direction, p.outcome, p.brier_score, "
            "       p.baseline_date, p.resolved_at, "
            "       COALESCE(src.name, 'manual') as sig_source, "
            "       p.probability_at_creation "
            "FROM predictions p "
            "LEFT JOIN signals s ON s.id = p.signal_id "
            "LEFT JOIN sources src ON src.id = s.source_id "
            "WHERE p.methodology_version != 'v0' "
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
        return (
            f'<section data-page="loop" role="region" aria-label="Loop">'
            f'<div class="phead"><h2>Loop</h2></div>{_err(e)}</section>'
        )

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
        f'<section data-page="loop" role="region" aria-label="Loop">'
        f'{css}'
        f'<div class="phead"><h2>Loop</h2>'
        f'<div class="sub">Per-ticker provenance timeline &middot; 60d window &middot; '
        f'signals &rarr; predictions &rarr; decisions &rarr; outcomes</div></div>'
        f'{stats}'
        f'<div class="lp-wrap">'
        f'<div class="lp-axis">{"".join(axis_marks)}</div>'
        f'{"".join(rows_html)}'
        f'{legend}'
        f'</div>'
        f'</section>'
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
                f'<div class="axis"><div class="axis-mark" style="left:{max(2.0, min(100.0, cv * 100)):.1f}%" title="credibility {cv:.2f}"></div></div>'
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
    return (
        f'<section data-page="methode" role="region" aria-label="Method"><div class="phead"><h2>Method</h2>'
        f'<div class="sub">How the bot reads signals + how it monitors your biases &middot; track record &middot; insider flow</div></div>'
        f"{star_signaux}{_track_record_panel()}{_distribution_health_panel()}{cols}{insider_flow_strip}{insider_clusters_strip}"
        f"{_discipline_biais_panel()}</section>"
    )


_MACRO_BANDS = {
    # Tightened 02/06 user "plus dur dans ta gradation" : warn earlier,
    # danger plus tot. Calm = vraiment calme. (warn_threshold, danger_threshold, hi_bad)
    "VIX": (16.0, 22.0, True),         # was (22, 30) -- 15 euphorie, >25 stress
    "HY_OAS": (250.0, 400.0, True),    # was (350, 500) -- <300 complacent, >600 panique
    "MOVE": (85.0, 110.0, True),       # was (100, 130) -- vol bonds plus tot warn
    "USDJPY": (148.0, 155.0, True),    # was (152, 160) -- carry stress plus tot
    "TYX": (4.0, 4.6, True),           # was (4.5, 5) -- >4% cost capital deja contraint
    "DXY": (100.0, 105.0, True),       # was (104, 108) -- USD strength plus stricte
    "CoreCPI": (2.5, 3.5, True),       # was (3, 4) -- Fed bloque deja >2.5
    "CPI": (2.5, 3.5, True),
    "T10Y2Y": (0.5, 0.0, False),       # was (0.2, 0) -- de-inversion warn plus tot
    "MfgIP": (0.5, -1.0, False),       # was (0, -2) -- expansion fragile <0.5
    # V3 BTC drawdown (hi_bad=False : lower = worse)
    "BTC_drawdown180": (-20.0, -35.0, False),  # was (-30, -50) -- crypto stress plus tot
}


_MACRO_TIPS: dict[str, str] = {
    "TYX": "Coût capital long. > 5% = multiples growth/tech craquent historiquement.",
    "Gold": "Couverture taux réels / débasement / géopol. Lecture interprétative.",
    "USDJPY": "Baromètre carry trade. > 160 = zone intervention BoJ → tail risk unwind tech US.",
    "VIX": "Vol implicite S&P 500 30j. < 15 euphorie, > 25 stress, > 40 panique.",
    "HY_OAS": "Prime obligations haut rendement vs Treasury. < 300 = complacent, > 600 = panique. Signal avancé.",
    "DXY": "USD vs 6 majeures. > 105 = vent contraire multinationales US ; > 110 = stress global.",
    "BTC_drawdown180": "Drawdown BTC vs max 6 mois. < -30% = bear risk-off, < -50% = capitulation. Capte le stress crypto reel sans confondre avec level brut.",
    "MOVE": "VIX des Treasuries. > 130 = stress obligataire, souvent avancé sur actions.",
    "T10Y2Y": "10Y-2Y rate curve. De-inversion (cross from <0 to >0) = recession in 3-6 months.",
    "BankReserves": "Cash bancaire à la Fed. < 2.5T = stress plomberie imminent.",
    "RepoSRF": "Standing Repo Facility. > 30B = banques court de cash, alarme plomberie aiguë.",
    "FedBalance_yoy": "Bilan Fed variation YoY %. > +20% = QE emergency (Fed combat crash). < -10% = QT agressif. +- 5% = stable.",
    "KRE": "ETF banques régionales. Décrochage brutal = signal stress type SVB.",
    "CopperGold": "Cuivre industriel vs or refuge. Monte = cycle haussier, baisse = peur récession.",
    "CoreCPI": "Core CPI YoY. > 2.5% = Fed bloquée en restrictif → vent contraire growth/tech.",
    "CPI": "Core CPI YoY. > 2.5% = Fed bloquée en restrictif → vent contraire growth/tech.",
    "MfgIP": "Industrial production YoY. > 0 = soft or strong expansion.",
    "MfgIP_yoy": "Industrial production YoY. > 0 = soft or strong expansion.",
}


def _macro_dot(ind: str, v: float) -> str:
    "Couleur du point macro selon le level reel (decouplee de la phase). Inconnu -> mute."
    band = _MACRO_BANDS.get(ind)
    if band is None:
        return "mute"
    warn, danger, hi_bad = band
    if hi_bad:
        return "danger" if v >= danger else ("warn" if v >= warn else "calm")
    return "danger" if v <= danger else ("warn" if v <= warn else "calm")


# === Equity internals: RSI(14) + Breadth (RSP/SPY) — cache TTL 30min ===
_RSI_CACHE: dict[str, float | None] = {}
_RSI_CACHE_TS: dict[str, float] = {}
_RSI_TTL = 1800.0


def _rsi_14(ticker: str) -> float | None:
    """RSI(14) daily via simple rolling mean. Cache 30min (anti-ban yfinance)."""
    import time as _t

    now = _t.time()
    if ticker in _RSI_CACHE and now - _RSI_CACHE_TS.get(ticker, 0) < _RSI_TTL:
        return _RSI_CACHE[ticker]
    try:
        import yfinance as yf

        closes = yf.Ticker(ticker).history(period="2mo", interval="1d")["Close"].dropna()
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
        import yfinance as yf

        rsp = yf.Ticker("RSP").history(period="3mo", interval="1d")["Close"].dropna()
        spy = yf.Ticker("SPY").history(period="3mo", interval="1d")["Close"].dropna()
        if len(rsp) < 50 or len(spy) < 50:
            return fallback
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
        "MOVE": (2, "Bond vol (MOVE)", 2, False),
        "T10Y2Y": (2, "10Y-2Y slope (%)", 4, False),
        "BankReserves": (2, "Fed bank reserves ($M)", 0, True),
        "RepoSRF": (2, "Standing Repo Facility ($B)", 2, False),
        "KRE": (2, "Regional banks ($)", 2, False),
        "CopperGold": (2, "Copper/gold ratio", 4, False),
        # Tier 3: Macro lente
        "CoreCPI": (3, "Core inflation (%)", 4, False),
        "CPI": (3, "Core inflation (%)", 4, False),
        "MfgIP": (3, "Industrial production (%)", 4, False),
        "MfgIP_yoy": (3, "Industrial production (%)", 4, False),
        "FedBalance_yoy": (3, "Bilan Fed YoY (%)", 1, False),
    }
    tnames = {
        1: "Market &amp; liquidity",
        2: "Banking stress &amp; Fed liquidity",
        3: "Slow macro",
        9: "Other",
    }
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
    tier_rows: dict[int, list[tuple]] = {}
    for ind, val, phase, ts in sig:
        tier, label, dec, thou = debt_map.get(ind, (9, ind, 2, False))
        v = float(val or 0)
        num = f"{v:,.{dec}f}" if thou else f"{v:.{dec}f}"
        ph = int(phase or 1)
        dot = _macro_dot(ind, v)
        try:
            _age = (_today - _dt.date.fromisoformat(str(ts)[:10])).days
        except Exception:
            _age = 0
        stale = '<span class="stale">stale</span>' if _age > _STALE.get(tier, 10) else ""
        vcls = "mute" if stale else dot
        tip = _MACRO_TIPS.get(ind, "")
        tip_attr = f' data-tip="{_html_esc.escape(tip, quote=True)}"' if tip else ""
        sort_key = (_dot_priority.get(dot, 9), _pos.get(ind, 999), ind)
        row_html = (
            f'<div class="drow"{tip_attr}><span class="ddot {dot}"></span><span class="dname">{label}</span>'
            f'<span class="dval {vcls}">{num}</span><span class="dp">P{ph}</span>{stale}</div>'
        )
        tier_rows.setdefault(tier, []).append((sort_key, row_html))
    tiers: dict[int, str] = {t: "".join(h for _, h in sorted(rows)) for t, rows in tier_rows.items()}
    blocks = "".join(f'<div class="dtier">{tnames[t]}</div>{tiers[t]}' for t in (1, 2, 3, 9) if tiers.get(t))
    try:
        comp = _q("SELECT score, phase FROM debt_composite ORDER BY timestamp DESC LIMIT 1")
    except Exception:
        comp = []
    score, cphase = (float(comp[0][0] or 0), int(comp[0][1] or 1)) if comp else (0.0, 1)
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
    _vthr = _rk.get("vol_scaling_threshold_vix", 25)
    _vsf = _rk.get("vol_scaling_factor", 0.7)
    _vix = next((float(v or 0) for i, v, p, t in sig if i == "VIX"), None)
    _reduced = _vix is not None and _vix >= _vthr
    _sfac = _vsf if _reduced else 1.0
    # Sizing est calcule sur VIX seul (regle empiriquement validee, BIS papers
    # 30+ ans). Composite phase frise sert d'overlay informationnel macro,
    # decouple du sizing trading (= different domaines decisionnels).
    size_txt = (
        f"VIX {_vix:.1f} {'&ge;' if _reduced else '&lt;'} {_vthr} (VIX-only rule)"
        if _vix is not None else "VIX indisponible"
    )
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
    # Strate 1 : etat macro + frise STRESS pleine largeur + tag exploratoire
    # (cf decision_log 02 -- V3 demote, V4 a venir).
    star_macro = (
        '<div class="ps-strate">'
        + '<div class="ps-lbl" data-tip="V3 composite macro phase (debt_monitor). STATUS: exploratory -- strict HOLDOUT 4/8 (02/06). V3 never generates P1 (centrist bias). Do not drive decisions on this value. V4 forthcoming (cf decision_log 02).">Macro state <span class="ps-tag-explor">exploratory</span></div>'
        + '<div class="ps-macro-row">'
        + f'<div class="ps-val {_phase_col}">{clabel}</div>'
        + f'<div class="ps-macro-meta">phase {cphase}/4 &middot; indice {score:.0f}</div>'
        + "</div>"
        + f'<div class="ps-frise"><div class="ps-frise-mark" style="left:{(cphase - 0.5) * 25:.0f}%"></div></div>'
        + '<div class="ps-frise-labs"><span>stable</span><span>stress</span><span>alerte</span><span>crise</span></div>'
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
        f'<div class="sub">Momentum toward targets &middot; margin before stops &middot; macro stress</div></div>'
        f"{star}"
        # Layout 02/06 user "organize, evitons les trous" : macro stress
        # full-width au-dessus (indicateurs naturellement nombreux), puis
        # RSI + breadth cote-a-cote en bas.
        f'<div class="ph3">Macro stress monitor &mdash; score {score:.0f}</div>'
        f'<div class="card pad" style="margin-bottom:var(--s4)"><div class="dlist"><style>.ddot.mute{{background:var(--steel);box-shadow:none;opacity:.6}}</style>{blocks}</div></div>'
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


_TIER_LABEL = {
    5: "Conviction 5 &middot; la plus forte",
    4: "Conviction 4",
    3: "Conviction 3 &middot; median",
    2: "Conviction 2",
    1: "Conviction 1 &middot; faibles",
}


def _theses(names: dict, sectors: dict, positions: list, pnl: dict) -> str:
    "Page Theses : asymetrie target/stop par conviction + gap target partielle."
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
        has_bar = bool(current and stop and tgt and tgt != stop)
        if has_bar:
            d_stop = abs(stop - current) / current * 100
            d_tgt = abs(tgt - current) / current * 100
            ratio = d_tgt / d_stop if d_stop else None
            frac = max(0.0, min(100.0, (current - stop) / (tgt - stop) * 100))
            if entry:
                entry_frac = max(0.0, min(100.0, (entry - stop) / (tgt - stop) * 100))
                # pnl_e calcule via entry de THESE (= prix quand thèse écrite) en NATIVE.
                # Sert au tracking "depuis rédaction de la thèse" SEULEMENT.
                pnl_e = (current - entry) / entry * 100
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
            }
        )
    n = len(ths)
    med = sorted(t["conv"] for t in ths)[n // 2]
    c5_pct = dist[5] / n * 100
    infl = c5_pct > 20
    maxc = max(dist.values()) or 1

    hist = '<div class="th-hist">'
    for c in (5, 4, 3, 2, 1):
        hist += (
            f'<div class="th-hbar"><span class="th-hlab">c{c}</span>'
            f'<div class="axis"><div class="axis-mark" style="left:{max(2.0, min(100.0, dist[c] / maxc * 100)):.1f}%" title="{dist[c]/maxc*100:.1f}%"></div></div>'
            f'<span class="th-hn">{dist[c]}</span></div>'
        )
    hist += "</div>"
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
        f'<div class="ps-cap">{infl_msg}</div></div>'
        f'<div class="ps-strate ps-foot">Distribution by conviction below</div>'
        f'</div>'
    )
    # Repartition par conviction (ancien hero 2nd col) reste en panneau detail
    kpis = (
        f'<div class="card pad" style="margin-bottom:var(--s4)">'
        f'<div class="ps-lbl" style="margin-bottom:14px">Distribution by conviction</div>'
        f'{hist}</div>'
    )

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
                if t["entry_frac"] is not None:
                    zones = f'<div class="axis-tick dash" style="left:{t["entry_frac"]:.1f}%"></div>'
                else:
                    zones = ""
                bar = (
                    '<div class="th-bar"><div class="axis">'
                    f'{zones}<div class="axis-mark" style="left:{t["frac"]:.1f}%" title="position {t["frac"]:.1f}% entre stop et target"></div></div>'
                    '<div class="th-ends">'
                    f'<span class="th-stop">stop &minus;{t["d_stop"]:.0f}%</span>'
                    f'<span class="th-tgt">target +{t["d_tgt"]:.0f}%</span></div></div>'
                )
            else:
                bar = '<div class="th-na">incomplete price data</div>'
            anchor = ""
            if t["has_bar"] and t["pnl_e"] is not None:
                _crypto = t["tk"] in crypto_tk
                if t["pnl_e"] >= 12 and not _crypto:
                    _acls = "acc"
                    _amsg = "Position in profit, upside margin remaining. Bias: securing too early. Rule: let it run toward target."
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
                sizebar = (
                    '<div class="axis sizebar">'
                    f'<div class="axis-target-tick" style="left:50%" title="target"></div>'
                    f'<div class="axis-mark" style="left:{_w_pos:.1f}%" title="weight {wv:.1f}% / target {_tgt:.1f}%"></div>'
                    '</div>'
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
            groups += (
                f'<div class="th-row" data-tk="{t["tk"]}">'
                f'<div class="th-id"><span class="th-conv c{t["conv"]}">c{t["conv"]}</span>'
                f'<span class="th-tk">{t["nm"]}</span>{cat_html}</div>'
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
    # % jour / semaine / mois depuis closes journaliers (1 appel yfinance, cache TTL).
    import time

    now = time.monotonic()
    hit = _PERF_CACHE.get(ticker)
    if hit and now - hit[0] < _PERF_TTL:
        return dict(hit[1])
    out: dict = {"d": None, "w": None, "m": None}
    try:
        import yfinance as yf

        c = yf.Ticker(ticker).history(period="1mo", interval="1d")["Close"].dropna()
        if len(c) >= 2:
            last = float(c.iloc[-1])
            out["d"] = round((last / float(c.iloc[-2]) - 1) * 100, 1)
            out["m"] = round((last / float(c.iloc[0]) - 1) * 100, 1)
            if len(c) >= 6:
                out["w"] = round((last / float(c.iloc[-6]) - 1) * 100, 1)
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
    """Format asymmetry_ratio avec class de coloration parchemin.

    Convention Taleb barbell :
    - ratio >= 999   -> sentinel TARGET_HIT (current >= target_full) -> 'target' badge
    - ratio >= 3.0   -> 'barbell' (asymetrie favorable, laisser courir) -> .acc (olive)
    - 1.0 <= r < 3.0 -> 'modere' (neutre) -> .num (ink2)
    - r < 1.0        -> 'inverse' (downside > upside, candidate trim) -> .neg (oxblood)
    - None           -> '—'
    """
    if ratio is None:
        return ('num', '&mdash;')
    if ratio >= 999:
        return ('num acc', 'target &check;')
    if ratio >= 3.0:
        return ('num acc', f'{ratio:.1f}&times;')
    if ratio >= 1.0:
        return ('num', f'{ratio:.1f}&times;')
    return ('num neg', f'{ratio:.1f}&times;')


def _broker_one(label: str, note: str, ps: list, grand: float, names: dict, pnl: dict, sectors: dict, asym: dict, gauges: dict | None = None) -> str:
    gauges = gauges or {}
    ps = sorted(ps, key=lambda p: -_broker_value(p, pnl))
    tot = sum(_broker_value(p, pnl) for p in ps)
    share = tot / grand * 100
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
            gauge_html = (
                f'<div class="axis row-axis" title="stop {-g["dn"]:.0f}% / target +{g["up"]:.0f}%">'
                f'<div class="axis-target-tick" style="left:{g["target_tick"]:.1f}%"></div>'
                f'<div class="axis-mark" style="left:{g["pos"]:.1f}%"></div>'
                f'</div>'
            )
        else:
            gauge_html = '<span class="num" style="color:var(--steel);opacity:.5">&mdash;</span>'
        rows += (
            f'<tr data-tk="{tk}" data-v="{v:.2f}" data-w="{w:.2f}" data-p="{pc if pc is not None else -9999}"><td class="tk">{_ticker_logo(tk)}{tk}<span class="nm">{nm}</span></td>'
            f'<td class="num mono">{vstr}&nbsp;&euro;</td><td class="num">{w:.1f}%</td>'
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


def _broker_tables(positions: list[dict], names: dict, pnl: dict, sectors: dict) -> str:
    grand = sum(_broker_value(p, pnl) for p in positions) or 1
    # Fetch asymmetry + stop/target progress par ticker
    asym = {}
    gauges: dict[str, dict] = {}
    try:
        asym_results = asym_mod.compute_portfolio_asymmetry()
        for r in asym_results:
            tk = r.get("ticker")
            if not tk:
                continue
            if r.get("asymmetry_ratio") is not None:
                asym[tk] = r["asymmetry_ratio"]
            # Stop / current / target -> frac 0..150% pour mini-gauge
            st, tg, c = r.get("stop") or 0, r.get("target_full") or 0, r.get("current_price") or 0
            up, dn = r.get("upside_pct"), r.get("downside_pct")
            if st and tg and tg != st and c and up is not None and dn is not None:
                frac_raw = (c - st) / (tg - st) * 100
                VISUAL_MAX = 150.0
                visual_pct = max(0.0, min(100.0, frac_raw / VISUAL_MAX * 100))
                target_tick_pct = 100.0 / VISUAL_MAX * 100
                gauges[tk] = {
                    "pos": visual_pct,
                    "target_tick": target_tick_pct,
                    "up": up,
                    "dn": dn,
                    "frac_raw": frac_raw,
                }
    except Exception:
        pass
    tr = [p for p in positions if _broker(p["ticker"]) == "tr"]
    eu = [p for p in positions if _broker(p["ticker"]) == "bourso"]
    head = (
        '<div class="colhead tight"><span class="t">Comptes</span>'
        '<span class="a">by broker &middot; sorted by value &middot; '
        'asymmetry = upside_to_target / downside_to_stop (Taleb barbell)</span></div>'
    )
    return (
        head
        + _broker_one("Trade Republic", "hors Europe", tr, grand, names, pnl, sectors, asym, gauges)
        + _broker_one("Boursorama", "PEA &middot; Europe", eu, grand, names, pnl, sectors, asym, gauges)
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
    """Affichage Brier honnete (user 01/06) : N<10 = bruit, ne pas afficher
    comme metrique. N>=10 sur cohorte V1 figee = caveater fort.

    Baseline canonique : 0.25 = Brier du predicteur constante 0.5 (le plus
    faible, qui hedge tout a 50/50). Le NOMMER explicitement -- sinon
    'Brier 0.25' lit faussement comme victoire alors que c'est le no-info.
    Le vrai referent de skill = b(1-b) avec b = taux de base (post-J-day,
    quand N=35 le justifiera)."""
    if not brier_n:
        return '<div class="dba-meta">Brier: no resolved prediction to measure</div>'
    if brier_n < 10:
        return (f'<div class="dba-meta">Brier: N={brier_n} '
                f'(insufficient &mdash; meaningful threshold N&ge;10)</div>')
    return (
        f'<div class="dba-meta">Brier mean: {brier_avg:.3f} sur N={brier_n} '
        f'&middot; vs 0.25 (constant 0.5 predictor, weakest baseline)</div>'
        f'<div class="dba-honest">V1 cohort frozen (probability_at_creation = '
        f'source credibility snapshot &asymp; 0.5). Beating 0.25 does not demonstrate '
        f'not a skill -- just an improvement over the weakest predictor '
        f'weak. Real V2 calibration = post-August (N V2 suffisant + comparaison '
        f'to the base-rate predictor).</div>'
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
    n_cluster_total = _q(
        "SELECT COUNT(*) FROM predictions "
        "WHERE methodology_version != 'v0' AND target_date <= '2026-06-10'"
    )[0][0]
    n_resolved = _q(
        "SELECT COUNT(*) FROM predictions WHERE resolved_at IS NOT NULL "
        "AND outcome != 'neutral' AND methodology_version != 'v0' "
        "AND target_date <= '2026-06-10'"
    )[0][0]
    brier_row = _q(
        "SELECT AVG(brier_score), COUNT(brier_score) FROM predictions "
        "WHERE brier_score IS NOT NULL AND methodology_version != 'v0' "
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
    # Bug fix 31/05 wave 9b : asymmetry compare current vs stop_price/target_full.
    # Comme ces derniers sont stockes NATIVE (cf currency_native_invariant),
    # current doit etre NATIVE aussi pour des ratios FX-invariants. Ancien
    # patch vers _cached_price_eur produisait "Marges les plus faibles" avec
    # target +175408% (000660.KS KRW vs current EUR).
    asym_mod._get_current_price = _cached_price_native
    full = asym_mod.compute_portfolio_asymmetry()
    computed = [r for r in full if "asymmetry_ratio" in r]
    positions = _positions()
    sectors = _sectors()
    held = {p["ticker"] for p in positions}
    planned = _planned(held)
    names = _names()
    pnl = _pnl_cost_map(positions)
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

    _ris, near, _heat, watch = _rows_risque(computed)
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
    gain_eur = sum(p["weight"] for p in positions if pnl.get(p["ticker"], 0) >= 0 and p["ticker"] in pnl)
    n_gain = sum(1 for p in positions if pnl.get(p["ticker"], 0) >= 0 and p["ticker"] in pnl)
    n_pnl = sum(1 for p in positions if p["ticker"] in pnl) or 1
    gpct = gain_eur / wbase * 100
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

    tape_items = ""
    for tk, p in sorted(pnl.items(), key=lambda x: -x[1]):
        cls = "pos" if p >= 0 else "neg"
        arrow = "&#9650;" if p >= 0 else "&#9660;"
        tape_items += f'<span class="ti">{_ticker_logo(tk)}<span class="tk tkc" data-tk="{tk}">{tk}</span> <span class="{cls}">{arrow}&nbsp;{abs(p):.1f}%</span></span>'
    tape = f'<div class="tape"><div class="track2">{tape_items}{tape_items}</div></div>'
    tape8k = _tape_8k()

    # Journal block retire 02/06 Vigie -- compute conserve pour reactivation eventuelle.
    _journal_html = _journal()
    _axis: dict[str, dict[str, float]] = {}
    for r in computed:
        st, tg, c = r.get("stop") or 0, r.get("target_full") or 0, r.get("current_price") or 0
        up, dn = r.get("upside_pct"), r.get("downside_pct")
        if st and tg and tg != st and c and up is not None and dn is not None:
            # frac_raw : 0 = at stop, 100 = at target, >100 = beyond target.
            # Conserve la valeur > 100 pour visualiser overshoot.
            frac_raw = (c - st) / (tg - st) * 100
            _axis[r["ticker"]] = {
                "frac": max(0.0, min(100.0, frac_raw)),
                "frac_raw": frac_raw,
                "up": up,
                "dn": dn,
                "tg_pct": (c / tg - 1) * 100 if tg else 0,  # % beyond target (negative = below)
            }
    _targets = sorted(_axis, key=lambda tk: -_axis[tk]["frac_raw"])[:6]
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
        # Gauge redesign 02/06 user : montrer overshoot visuellement.
        # Bar = 0..150% mapped to width. Target = 100%, overshoot zone = 100..150%.
        # Marker position visuelle : map frac_raw [0..150+] -> [0..100]% visual width.
        VISUAL_MAX = 150.0  # frac_raw at visual right edge
        frac_raw = a["frac_raw"]
        # Si overshoot > 50%, on cap visual et on a un "+overshoot" badge
        visual_pct = max(0.0, min(100.0, frac_raw / VISUAL_MAX * 100))
        # Profit-take chip
        profit_chip = ""
        ln = _book_idx.get(tk)
        beyond_pct = a["tg_pct"]
        if frac_raw > 100:
            profit_chip = f'<span class="th-pt acc">target +{beyond_pct:.1f}% beyond</span>'
        elif ln and a["frac"] > 80:
            risky = ln.valo_above_bull_case or ln.solidite in ("Fragile", "Incertain")
            if risky:
                profit_chip = '<span class="th-pt">target hit</span>'
        # Target tick marker at 100/150 = 66.67% of visual width
        target_tick_pct = 100.0 / VISUAL_MAX * 100
        return (
            f'<div class="row" data-tk="{tk}"><div class="rt"><span class="tk">{tk}</span>{profit_chip}</div>'
            f'<div class="axis">'
            f'<div class="axis-target-tick" style="left:{target_tick_pct:.1f}%" title="target"></div>'
            f'<div class="axis-mark" style="left:{visual_pct:.1f}%" title="progress {frac_raw:.0f}%"></div>'
            f'</div>'
            f'<div class="th-ends"><span class="th-stop">stop &minus;{a["dn"]:.0f}%</span>'
            f'<span class="th-tgt">target +{a["up"]:.0f}%</span></div></div>'
        )

    gain = "".join(_axisrow(tk) for tk in _targets) or '<div class="empty" style="padding:var(--s4) 0">&mdash;</div>'
    _lose_stops = "".join(_axisrow(tk) for tk in _stops) or '<div class="empty" style="padding:var(--s4) 0">&mdash;</div>'  # D1 retire Vigie, compute conserve
    # cockpit_html (Cockpit discipline panel) retire 31/05 user feedback
    # _cockpit() helper toujours dispo si reactivation future
    grade_html = _grade_panel()
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
        # Area fill : meme curve + ferme vers le bas (style Robinhood)
        _spk_area = _spk_path + f" L {_spk_w - _spk_pad:.1f} {_spk_h - _spk_pad:.1f} L {_spk_pad:.1f} {_spk_h - _spk_pad:.1f} Z"
        _gradient_id = "spk-grad-up" if _spark_vals[-1] >= _spark_vals[0] else "spk-grad-dn"
        # Encode points+dates pour hover interactif (data attrs : x|y|val|date)
        _spk_pts_data = ";".join(
            f"{_spk_pts[_i].split(',')[0]}|{_spk_pts[_i].split(',')[1]}|{_spark_vals[_i]:.0f}|{_spark_dates[_i]}"
            for _i in range(len(_spk_pts))
        )
        _sparkline = (
            f'<span class="ps-spark-wrap"><svg class="ps-spark" viewBox="0 0 {_spk_w} {_spk_h}" width="{_spk_w}" height="{_spk_h}" '
            f'style="overflow:visible" aria-label="Trajectoire 30j" '
            f'data-pts="{_spk_pts_data}" data-w="{_spk_w}" data-h="{_spk_h}" data-color="{_spk_color}">'
            f'<defs><linearGradient id="{_gradient_id}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="{_spk_color}" stop-opacity="0.25"/>'
            f'<stop offset="100%" stop-color="{_spk_color}" stop-opacity="0"/>'
            f'</linearGradient></defs>'
            f'<path d="{_spk_area}" fill="url(#{_gradient_id})" stroke="none"/>'
            f'<path d="{_spk_path}" fill="none" stroke="{_spk_color}" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{_spk_last_x}" cy="{_spk_last_y}" r="2.8" fill="{_spk_color}"/>'
            f'<circle cx="{_spk_last_x}" cy="{_spk_last_y}" r="5" fill="{_spk_color}" opacity="0.25"><animate attributeName="r" values="5;8;5" dur="2.4s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.25;0.05;0.25" dur="2.4s" repeatCount="indefinite"/></circle>'
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
        + f'<div class="ps-sub-lien"><b class="acc">{gpct:.0f}%</b> in profit &middot; {n_gain} positions &middot; {n_pnl - n_gain} in loss ({100 - gpct:.0f}%) {_val_delta_str}</div>'
        + '</div>'
        + '<div class="ps-hero-right">'
        + '<div class="ps-lbl" data-tip="Global Construction + Fragility grade. Construction = Solidity/Bet/Overlap/Calibration. Fragility = Health/cycle/valo. &gt;= 70 acc, &gt;= 50 warn, &lt; 50 bear.">Portfolio grade</div>'
        + '<div class="ps-grade-row">'
        + f'<div class="ps-grade-letter {_grade_color}">{_grade_letter}</div>'
        + f'<div class="ps-grade-score"><div class="ps-grade-num">{_grade_score}<span class="ps-grade-max">/100</span></div>'
        + f'<div class="ps-grade-bar"><div class="ps-grade-fill {_grade_color}" style="width:{_grade_score:.0f}%"></div></div></div>'
        + '</div></div>'
        + '</div></div>'
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
        '<div class="vigie-sh" data-tip="Positions close to target (take-profit zone, valo &gt; bull) -- mechanized trim candidates via fomo_greed gate."><svg class="sh-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 13l4-4 3 3 4-6"/><path d="M11 6h3v3"/></svg>Opportunities &mdash; close or consolidate</div>'
        f'<div class="colhead"><span class="t">Closest to target</span><span class="a">thesis in realization &middot; watch valo &gt; bull and fragility</span></div>'
        f'<div class="card pad">{gain}</div>'
        # ── BLOC 2 : MOUVEMENT DU JOUR -- restaure 02/06 user (winners/losers %) ──
        '<div class="vigie-sh" data-tip="Today\'s biggest intraday movers (vs prior close)."><svg class="sh-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12l3-4 3 2 3-5 3 3"/></svg>Today&rsquo;s movers</div>'
        f'<div class="cols">'
        f'<div class="col"><div class="colhead"><span class="t">Top winners</span><span class="a">vs prior close</span></div><div class="card pad">{_day_up}</div></div>'
        f'<div class="col"><div class="colhead"><span class="t">Top losers</span><span class="a">vs prior close</span></div><div class="card pad">{_day_dn}</div></div>'
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
        _vthr_p = float(_rk_p.get("vol_scaling_threshold_vix", 25))
        _vsf_p = float(_rk_p.get("vol_scaling_factor", 0.7))
    except Exception:
        _vthr_p, _vsf_p = 25.0, 0.7
    _reduced_p = _vix_p and _vix_p >= _vthr_p
    _sfac = _vsf_p if _reduced_p else 1.0
    size_txt = (
        f"VIX {_vix_p:.1f} {'&ge;' if _reduced_p else '&lt;'} {_vthr_p:.0f} (VIX-only rule)"
        if _vix_p else "VIX indisponible"
    )
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
        f'{_MODE_BTN}</div></aside>{_THEME_INIT}{_SORT_JS}{_CSORT_JS}{_DONUT_JS}'
        f'<div class="wrap">{tape}{tape8k}<main class="main">{_dband}'
        + vigie
        + positions_pg
        + _concentration(positions, planned, sectors, names, pnl, daily)
        + _theses(names, sectors, positions, pnl)
        + strategie_html
        + _signaux()
        + _loop()
        + _urgence(watch, near, positions, pnl, elan, near_t)
        + _copilot()
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
        + "</style></head><body>"
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
        + "</body></html>"
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        if OUTPUT.exists() and OUTPUT.read_text() == html:
            return OUTPUT
    except OSError:
        pass
    OUTPUT.write_text(html)
    return OUTPUT


if __name__ == "__main__":
    p = render()
    print(f"[OK] {p} ({p.stat().st_size} bytes)")
