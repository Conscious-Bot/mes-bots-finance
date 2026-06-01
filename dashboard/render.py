"""PRESAGE dashboard. Static-gen, READ-ONLY, REAL data.
Weights from positions.eur_invested (EUR cost basis). Sectors from theses.sector_thesis_id.
Perf as ratio % (currency-invariant). DB read-only; per-panel try/except. Leaflet geo."""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import yaml

from intelligence import asymmetry as asym_mod

# Sprint 3 logos tickers : import + force-reload pour bypass cache sys.modules
# tant que serve.py n'est pas restart pour activer le nouveau watch.
import importlib  # noqa: E402
import shared.ticker_logos as _ticker_logos_mod  # noqa: E402
importlib.reload(_ticker_logos_mod)
_ticker_logo = _ticker_logos_mod.logo_html

# Reconciliation flags - known book/broker drifts not yet journaled.
# Clear an entry when reconciled via /position_sell + /position_buy.
RECONCILE_FLAGS: list[dict] = []


def _cfg() -> dict:
    try:
        return yaml.safe_load(Path("config.yaml").read_text())
    except Exception:
        return {}


_CFG = _cfg()
POS_CAP = float(_CFG.get("style", {}).get("position_max_pct", 0.05)) * 100
NARRATIVE_CAP = float(_CFG.get("style", {}).get("narrative_max_pct", 0.30)) * 100
DD_REDUCE = float(_CFG.get("risk", {}).get("drawdown_reduce_pct", 0.08)) * 100
DD_STOP = float(_CFG.get("risk", {}).get("drawdown_stop_pct", 0.20)) * 100
FX_USD = 0.858
REVIEWS = [
    ("2026-05-30", "R&eacute;solution Brier (KPI#2)"),
    ("2026-05-30", "Revue COHR"),
    ("2026-06-16", "Revue orphelins c1 (J+30)"),
]

OUTPUT = Path("dashboard/dashboard.html")
DB = "file:data/bot.db?mode=ro"

COUNTRY = {
    "TSM": "Ta&iuml;wan",
    "TSEM": "Isra&euml;l",
    "ASML": "Pays-Bas",
    "NVO": "Danemark",
    "ARM": "Royaume-Uni",
    "IFNNY": "Allemagne",
    "BABA": "Chine",
    "TCEHY": "Chine",
    "PDD": "Chine",
    "STM": "France",
}
SUFFIX = {
    ".KS": "Cor&eacute;e",
    ".T": "Japon",
    ".TW": "Ta&iuml;wan",
    ".PA": "France",
    ".AS": "Pays-Bas",
    ".L": "Royaume-Uni",
    ".HK": "Chine",
    ".DE": "Allemagne",
    ".MI": "Italie",
    ".ST": "Su&egrave;de",
    ".AX": "Australie",
    ".TO": "Canada",
    ".SS": "Chine",
    ".SZ": "Chine",
    ".SW": "Suisse",
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
    cible +23876%, 000660.KS cible +175408%)."""
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


_DP_CACHE: dict[str, tuple[float | None, float]] = {}
_DP_TTL = 840.0


def _dp_pct(ticker: str) -> float | None:
    # Variation % du jour (cloture veille -> dernier close). Invariant en devise: aucune conversion FX.
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
    return "&Eacute;tats-Unis"


def _q(sql: str) -> list:
    con = sqlite3.connect(DB, uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _err(e: Exception) -> str:
    return f'<div class="empty"><b>Requ&ecirc;te &agrave; ajuster</b><span class="mono" style="font-size:11px">{type(e).__name__}: {str(e)[:130]}</span></div>'


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
    "Foundry & logique": "#3056D3",
    "Équipement semi": "#10A37F",
    "Mémoire": "#E14B62",
    "Matériaux semi": "#FB923C",
    "EDA": "#7E47C9",
    "Connectivité & optique": "#D154AB",
    "Hyperscalers": "#0D9488",
    "Power & électrification": "#B45D31",
    "Défense": "#475569",
    "Énergie & matières premières": "#CA8A04",
    "Auto / robotique": "#0EAFC4",
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


# Glossaire canonique (FR). Mapping dim internal name -> (label affiche, sens cible,
# bucket Construction/Fragilite). Construction = ce qui structure le book.
# Fragilite = ce qui peut le briser maintenant.
_DIM_LABELS = {
    "quality_T1_plus": ("Solidit&eacute; haute", "min", "construction"),
    "T2_redondant": ("Doublons", "max", "construction"),
    "decorrelation_star": ("Autres paris", "min", "construction"),
    "sizing_conviction": ("Calibrage", "min", "construction"),
    "cluster_cap": ("Pari principal", "max", "construction"),
    "thesis_health": ("Sant&eacute;", "min", "fragilite"),
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
        '<div class="v2-status v2-empty">Premi&egrave;re coh&egrave;rte V2 attendue '
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
        else '<div class="v2-status v2-empty">aucune pr&eacute;diction V1</div>'
    )

    return (
        '<div class="card pad v2cohortcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Coh&egrave;rte V2 vs V1 (scorer pivot 30/05)</span>'
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
            f'<span class="a">accumulation cohorte &mdash; verdict s&apos;active &agrave; n&ge;{target} predictions r&eacute;solues non-neutral</span></div>'
            '<div class="calib-progress">'
            f'<div class="calib-bar"><div class="calib-fill" style="width:{pct:.1f}%"></div></div>'
            '<div class="calib-meta">'
            f'<span class="calib-n mono">{n_total}/{target}</span>'
            f'<span class="calib-rem">{remaining} &agrave; attendre</span>'
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
    ) or '<div class="empty">aucune 8-K log&eacute;e</div>'

    return (
        '<div class="card pad wactcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Wire EDGAR activity</span>'
        '<span class="a">8-K + insider clusters arriv&eacute;s dans le pipeline scoring V2</span></div>'
        f'<div class="wact-grid">{cells}</div>'
        '<div class="wact-recent-head">Derni&egrave;res 5 d&eacute;p&ocirc;ts 8-K (toutes severities)</div>'
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
    """Top Risques declares - first-class surveillance sur Vue d'ensemble.

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
            f'<div class="rw-expo">Exposure : {exposure.get("pct_book", "?")}% du book '
            f'(cluster {exposure.get("cluster", "?")} &middot; facteur {exposure.get("factor", "?")})</div>'
            '<div class="rw-grid">'
            f'<div class="rw-cell"><div class="rw-h">Drawdown stress estime</div>'
            f'<div class="rw-v mono neg">{target.get("current_estimated_drawdown_stress", "?")}%</div>'
            f'<div class="rw-t">target : {target.get("target_estimated_drawdown_stress", "?")}%</div></div>'
            f'<div class="rw-cell"><div class="rw-h">Ballast decorrele strict</div>'
            f'<div class="rw-v mono">{target.get("current_ballast_strict_pct", "?")}%</div>'
            f'<div class="rw-t">target : {target.get("target_ballast_strict_pct", "?")}%</div></div>'
            f'<div class="rw-cell"><div class="rw-h">Plan mitigation</div>'
            f'<div class="rw-v mono">{avg_progress:.0f}%</div>'
            f'<div class="rw-t">leviers A/B/C en cours</div></div>'
            '</div>'
            '<div class="rw-section">'
            '<div class="rw-sh">Surveillance signaux</div>'
            f'<div class="rw-sigs">{signals_html}</div>'
            '</div>'
            '<div class="rw-section">'
            '<div class="rw-sh">Plan mitigation</div>'
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
                'Phase construction active &middot; '
                "l'expo actuelle se diluera mecaniquement vers la cible "
                "quand les decorrelants (Energie-pour-IA, Defense, Robotique) entreront. "
                '<b>Lecture : surveiller, pas corriger.</b>'
                '</div>'
            )
    except Exception:
        pass
    return (
        '<div class="card pad riskwatchcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Top Risques surveillance</span>'
        f'<span class="a">{len(risks_list)} risque(s) declare(s) &middot; thesis-level reflection</span></div>'
        f'{construction_lens}'
        + "".join(out)
        + "</div>"
    )


def _grade_panel() -> str:
    """Glossaire canonique : DEUX notes (Construction + Fragilite), chacune
    decomposee par axe. Vocabulaire FR clair, plus de jargon T1/T1★/cluster.

    - Construction = Solidite + Pari + Doublons + Calibrage (ce qui structure)
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
            gates = []  # not persisted in snapshot, can compute fresh if needed
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
                '<span class="gsub-empty">aucun ticker specifique cite dans l\'evidence</span>'
            )
            ev_safe = evidence.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:280]
            rows.append(
                f'<div class="grow-wrap">'
                f'<div class="grow has-acc">'
                f'<div class="glab">{label}</div>'
                f'<div class="gaxis"><div class="gfill {tcls}" style="width:{bar_pct:.1f}%"></div>'
                f'<div class="gtgt" style="left:{tgt:.1f}%"></div></div>'
                f'<div class="gnum"><span class="mono">{cur:.1f}%</span>'
                f'<span class="gt">cible {prefix} {tgt:.0f}%</span></div>'
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
        '<div class="colhead"><span class="t">Note du portefeuille</span>'
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
        f'<div class="gsubh">Fragilit&eacute;</div>'
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

    Anti-pattern combattu : SNOW vivait en vol aveugle integral (tout NULL)
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
        return f'<div class="card pad"><div class="empty">vol aveugle indispo: {type(e).__name__}</div></div>'

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
        '<div class="colhead"><span class="t">Positions en vol aveugle</span>'
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
            "Aucune intervention du copilot pour le moment. Les pressure-tests "
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
        '<div class="colhead"><span class="t">Pressions du copilot avant tes trades</span>'
        '<span class="a">survole/clique une ligne pour le diagnostic complet &middot; verdict m&eacute;canique avant chaque action</span></div>'
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
            "Premiere mesure des doublons par correlation prevue samedi 18h. Une fois disponible, les paires qui bougent ensemble apparaitront ici."
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
    ) or '<div class="empty" style="padding:var(--s2) 0">aucune paire >0.7</div>'

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
    mix_html = "".join(cluster_rows) or '<div class="empty" style="padding:var(--s2) 0">aucun cluster avec macro_factor melange</div>'

    return (
        '<div class="card pad clustercard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Doublons vus par les prix</span>'
        f'<span class="a">{snapshot_date} &middot; corr&eacute;lation rendements &middot; ce qui bouge ensemble vraiment</span></div>'
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
    rows = []
    for cur, d in fx.items():
        pct = d["pct"]
        wcls = "high" if pct >= 40 else ("mid" if pct >= 15 else "low")
        tks = ", ".join(d["tickers"][:8])
        if len(d["tickers"]) > 8:
            tks += f" +{len(d['tickers']) - 8}"
        rows.append(
            f'<div class="fx-row">'
            f'<div class="fx-head"><span class="fx-cur">{cur}</span>'
            f'<span class="fx-pct {wcls} mono">{pct:.1f}%</span>'
            f'<span class="fx-eur mono">{d["eur"]:,.0f}€</span>'
            f'<span class="fx-n">n={d["n_positions"]}</span></div>'
            f'<div class="fx-bar"><div class="fx-fill {wcls}" style="width:{min(pct, 100):.1f}%"></div></div>'
            f'<div class="fx-tks">{tks}</div></div>'
        )
    return (
        '<div class="card pad fxcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Exposition par devise</span>'
        '<span class="a">book euro mais positions cot&eacute;es ailleurs &middot; pas de hedge FX</span></div>'
        + "".join(rows)
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
        '<div class="colhead"><span class="t">Surperformance r&eacute;elle vs secteur</span>'
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
        '<div class="empty" style="padding:var(--s25) 0">aucune these triggered/at_risk &mdash; ' +
        f'{counts["dormant"]} dormantes</div>'
    )
    return (
        '<div class="card pad killcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Conditions d\'invalidation des th&egrave;ses</span>'
        f'<span class="a">d&eacute;clench&eacute;es {counts["triggered"]} &middot; &agrave; risque {counts["at_risk"]} &middot; '
        f'dormantes {counts["dormant"]} &middot; v&eacute;rifi&eacute; 07h30</span></div>'
        + items_html
        + "</div>"
    )


def _spof_panel() -> str:
    """Sprint 14 — Single points of failure upstream.

    Critique : 'Ta vraie concentration n'est pas dans le book, elle est en
    amont : TSMC fabrique pour AMD, Broadcom, Astera. Un incident TSMC touche
    bien plus que la ligne TSMC. HBM = 3 fournisseurs, EUV = ASML seul.'
    """
    try:
        from intelligence import spof_and_sizing as _sp

        spofs = _sp.compute_spof_graph()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">SPOF indispo: {type(e).__name__}</div></div>'
    if not spofs:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "Classification des tickers en cours. Les fiches techniques apparaitront ici une fois la passe terminee."
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
        '<div class="colhead"><span class="t">D&eacute;pendances cach&eacute;es en amont</span>'
        '<span class="a">si un fournisseur en amont casse, tout ce qui en d&eacute;pend casse aussi</span></div>'
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
        # SK Hynix stop -43%. Pas de relation coherente -- regression du
        # Day 5 sur l'asymetrie tautologique. Au lieu de le decrire dans
        # le TODO, on l'affiche : 3 colonnes (conv, fade, stop_dist%)
        # cote a cote permettent de voir l'incoherence d'un coup d'oeil.
        book_idx = _bk.get_book_index()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">Mauboussin sizing indispo: {type(e).__name__}</div></div>'
    if not sizing:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "Pas encore de meta classifies pour calculer le sizing implicite."
            "</div></div>"
        )
    rows = []
    for tk, d in sizing.items():
        gap = d["gap_pp"]
        gcls = "neg" if gap > 0.5 else ("pos" if gap < -0.5 else "neu")
        fade = d.get("fade_rate_score") or 0
        fcls = "high" if fade >= 60 else ("mid" if fade >= 30 else "low")
        # F10 : stop_distance% = (current - stop) / current * 100
        ln = book_idx.get(tk)
        stop_dist_html = '<span class="ms-stopd mono">stop ?</span>'
        if ln and ln.stop_price and ln.current_price_eur:
            stop_dist = (ln.current_price_eur - ln.stop_price) / ln.current_price_eur * 100
            # Outlier flag : haut fade attend stop serre (<25%), bas fade
            # tolere stop large. Si fade>=60 ET stop_dist>40% : INCOHERENT.
            # Si fade<=20 ET stop_dist<25% : aussi INCOHERENT (trop serre).
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
                '<span class="ms-frag" title="aussi flagge valo > bull case '
                'dans une autre vue">valo &gt; bull</span>'
            )
        rows.append(
            f'<div class="ms-row">'
            f'<span class="ms-tk">{tk}</span>'
            f'<span class="ms-conv mono">c{d["conviction"]}</span>'
            f'<span class="ms-fade {fcls} mono">fade {fade}</span>'
            f'{stop_dist_html}'
            f'<span class="ms-target mono">cible {d["target_pct"]:.1f}%</span>'
            f'<span class="ms-actual mono">reel {d["actual_pct"]:.1f}%</span>'
            f'<span class="ms-gap {gcls} mono">{gap:+.1f}pp</span>'
            f'{fragile_flag}</div>'
        )
    return (
        '<div class="card pad mauboussincard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Calibrage rigoureux</span>'
        '<span class="a">taille r&eacute;elle vs taille th&eacute;orique (conviction &times; vitesse d\'&eacute;rosion du moat)</span></div>'
        + "".join(rows)
        + "</div>"
    )


def _valo_above_bull_panel() -> str:
    """Sprint 14 — flag positions ou expectations > bull case (reverse-DCF)."""
    try:
        from intelligence import spof_and_sizing as _sp

        flags = _sp.list_above_bull_case()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">valo indispo: {type(e).__name__}</div></div>'
    if not flags:
        return (
            '<div class="card pad"><div class="empty" style="padding:var(--s35) 0">'
            "Aucune position avec expectations > bull case identifiees."
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
        '<div class="colhead"><span class="t">Valos d&eacute;j&agrave; au-del&agrave; du bull case</span>'
        '<span class="a">le prix actuel exige plus que le sc&eacute;nario haussier raisonnable</span></div>'
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
        return '<div class="card pad"><div class="empty">aucune position classifiee</div></div>'
    # Tri : composites en TETE (vue agregée d'abord), puis sub-buckets par pct
    sorted_f = sorted(facts.items(), key=lambda kv: (not kv[1].get("is_composite"), -kv[1]["pct_of_book"]))
    rows = []
    for name, d in sorted_f:
        pct = d["pct_of_book"]
        wcls = "high" if pct >= 30 else ("mid" if pct >= 10 else "low")
        # F9 fix : afficher le theme thesis user a cote de chaque ticker
        # quand il y a divergence entre le macro_factor (vue Paris) et le
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
        '<div class="colhead"><span class="t">Paris du portefeuille</span>'
        '<span class="a">sur quoi tu paries vraiment, par facteur macro &middot; un seul gros pari domine</span></div>'
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
    """Sprint 19 — affiche la strategie utilisateur declaree (cibles custom)."""
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
            "Pas de strategie utilisateur declaree. Defaults config.yaml utilises."
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
    accepted_html = ", ".join(accepted) if accepted else "(aucun)"
    # Phase construction : badge en tete pour cadrer la lecture du reste.
    # Tant que le book n'a pas atteint sa cible (~70k€/~33 pos), les
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
            '<div class="us-cstr-h">Phase construction</div>'
            f'<div class="us-cstr-b">Le book est en cours de constitution : '
            f'<b class="mono">{cur_eur:,.0f}&nbsp;€</b> / '
            f'<b class="mono">{tgt_eur:,.0f}&nbsp;€</b> cible '
            f'(<b>{progress:.0f}%</b> &middot; {cur_pos}/{tgt_pos} positions). '
            "Les decorrelants (Energie-pour-IA, Defense, Robotique) sont en "
            "cours d'ajout. Les ratios de concentration actuels (cluster cap, "
            "ballast strict, expo AI capex) <b>convergeront naturellement</b> "
            "vers la cible. Lecture informative, pas actionnable : on ne "
            "pousse pas a trim tant que la construction n'est pas terminee."
            '</div>'
            '</div>'
        )
    # CTA "a valider" : lit le drawdown estime sur scenario AI capex -30%
    # depuis risk_watch.json. Tant que pas valide explicitement, la cible
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
                f'<div class="us-cta-b">Ta cible cluster {cap}% implique '
                f'<b class="neg mono">{dd_mild}%</b> sur scenario AI capex de-rating '
                f'-30% (~<b class="neg mono">{dd_eur:+,}&nbsp;€</b>). '
                "Si voir le book a ce niveau touche ta limite, baisse la cible : la "
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
        '<div class="colhead"><span class="t">Ta strategie declaree</span>'
        f'<span class="a">archetype = {archetype} &middot; depuis {declared} &middot; surcharge les defaults</span></div>'
        f'{construction_html}'
        '<div class="us-grid">'
        f'<div class="us-row"><span class="us-k">Pari principal cible</span><span class="us-v mono">{cap}%</span></div>'
        f'<div class="us-row"><span class="us-k">Autres paris cible</span><span class="us-v mono">{dec}%</span></div>'
        f'<div class="us-row"><span class="us-k">Benchmark</span><span class="us-v mono">{bench}</span></div>'
        f'<div class="us-row"><span class="us-k">Horizon th&egrave;ses</span><span class="us-v mono">{horizon} ans</span></div>'
        f'<div class="us-row"><span class="us-k">Concentrations accept&eacute;es</span><span class="us-v">{accepted_html}</span></div>'
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
        "quality_T1_plus": "Solidit&eacute; haute",
        "T2_redondant": "Doublons",
        "decorrelation_star": "Autres paris",
        "sizing_conviction": "Calibrage",
        "cluster_cap": "Pari principal",
        "thesis_health": "Sant&eacute;",
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
        '<div class="colhead"><span class="t">D&eacute;rive de la note (30j)</span>'
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
            "Tagging axes (driver/stage/moat/macro) en attente. Les fiches techniques apparaitront ici une fois classifies."
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
        '<span class="a">moteur de demande &middot; &eacute;tage chaine de valeur &middot; nature du moat &middot; facteur macro</span></div>'
        + "".join(groups_html)
        + "</div>"
    )


def _preferences_panel() -> str:
    """Layer 3 — ce qui MARCHE deterministically pour CE user.

    Pas d'opinion modele, juste les chiffres bruts groupes par kind. La
    confidence est derivee du sample size (Wilson-conservative). Pas de
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
            "Calibration mensuelle prevue le 1er du mois. Les preferences (ce qui a marche chez toi) apparaitront ici une fois les decisions accumulees."
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
        rows_html = "".join(rows) or '<div class="empty" style="padding:var(--s2) 0">aucun sample</div>'
        groups.append(
            f'<div class="pr-group"><div class="pr-h">'
            f'<span class="pr-kind">{kind.replace("_"," ")}</span>'
            f'<span class="pr-meta">n={n} conf={conf} ({date})</span></div>'
            f'{rows_html}</div>'
        )
    return (
        '<div class="card pad preferencescard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Ce qui a march&eacute; chez toi</span>'
        '<span class="a">samples + winrate sur tes vraies d&eacute;cisions r&eacute;solues &middot; pas d\'opinion mod&egrave;le</span></div>'
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
            "Synthese hebdomadaire prevue dimanche 19h. Une fois generees, les vues stables du bot par ticker apparaitront ici."
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
        '<span class="a">synth&egrave;se stable per ticker mise &agrave; jour chaque semaine '
        '&middot; survole ou clique pour d&eacute;rouler</span></div>'
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
            "Pas encore de signaux soft extraits. Continue de discuter dans le "
            "chat — chaque conversation lambda devient une mine d'infos pour le profil."
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
        '<div class="colhead"><span class="t">Ce que tu laisses &eacute;chapper en conversation</span>'
        '<span class="a">concerns / doutes / vues que le bot capte chaque message &middot; nourrit ton profil</span></div>'
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
            "Aucune conversation enregistree pour le moment. Les echanges chat "
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
        '<span class="a">tout est consign&eacute; et r&eacute;-int&eacute;gr&eacute; au profil au fil du temps</span></div>'
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
            "Synthese narrative hebdomadaire prevue dimanche 20h30. Les clusters narratifs apparaitront ici une fois generes."
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
    ) or '<div class="empty" style="padding:var(--s25) 0">aucun edge identifie</div>'

    red_rows = "".join(
        f'<div class="nv-line"><span class="nv-tk">{r.get("ticker","?")}</span>'
        f'<span class="nv-with">redondant avec {r.get("redundant_with","?")}</span>'
        f'<span class="nv-why">{(r.get("reason") or "")[:160]}</span></div>'
        for r in redundant
    ) or '<div class="empty" style="padding:var(--s25) 0">aucune redondance</div>'

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
        "directional_spread": "Probas étalées",
        "insider_clusters_alive": "Pipeline insider clusters",
        "horizon_diversification": "Horizons diversifiés",
        "conviction_distribution": "Conviction étalée",
        "fx_freshness": "FX live (max-age 24h)",
    }
    rows = ""
    for r in results:
        cls = status_tag.get(r.get("status"), "calm")
        name = label_map.get(r.get("name"), r.get("name", "?"))
        status = r.get("status", "?")
        msg = (r.get("message") or "").replace("<", "&lt;").replace(">", "&gt;")
        rows += (
            f'<div class="row" title="{msg}">'
            f'<div class="rt"><span style="font-weight:600">{name}</span>'
            f'<span class="tag {cls}">{status}</span></div>'
            f'<div class="rs"><span style="color:var(--steel);font-size:12px">{msg[:120]}</span></div>'
            f'</div>'
        )
    return (
        '<div class="card pad" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Santé distribution</span>'
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
    # Panel honnete-tot : disparait une fois la cible atteinte (user feedback
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
    if n_brier < MIN_CONCLUSIF:
        _brier_cls, brier_verdict = "warn", f"INSUFFISANT &mdash; N={n_brier}&lt;{MIN_CONCLUSIF}"
    elif brier_mean < 0.20:
        _brier_cls, brier_verdict = "acc", "sous la cible 0.20"
    elif brier_mean < 0.25:
        _brier_cls, brier_verdict = "warn", "approche le seuil"
    else:
        _brier_cls, brier_verdict = "bear", "au-dessus du seuil"

    # Axe taux correct : 0% -> 100%, marker = position actuelle
    rate_frac = (n_corr / n * 100) if n else 0.0
    # Axe Brier : 0 -> 0.5, marker = brier_mean, ligne ref a cible 0.20 (= 40%)
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
        f'<span class="a">N={n} substantiel(s) &middot; aveu honn&ecirc;te-t&ocirc;t si N&lt;{MIN_CONCLUSIF}</span></div>'
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
        # Metric 2 : Brier rolling (axe 0->0.5, cible 0.20)
        f'<div class="tr-metric">'
        f'<div class="tr-mlabel"><span class="tr-mname">Brier rolling</span>'
        f'<span class="tr-mval mono">{brier_str}</span>'
        f'<span class="tr-munit">sur 0&ndash;0,5</span></div>'
        f'<div class="axis tr-axis-brier">'
        f'<div class="tr-axref" style="left:{brier_target_x:.0f}%" title="cible 0,20"></div>'
        f'{brier_marker}'
        f'</div>'
        f'<div class="tr-mfoot"><span class="mono">cible 0,20</span>'
        f'<span class="tr-verdict">{brier_verdict}</span></div>'
        f'</div>'
        # Metric 3 : Courbe de fiabilite (cadre vide + diagonale qui se trace)
        f'<div class="tr-metric">'
        f'<div class="tr-mlabel"><span class="tr-mname">Courbe de fiabilit&eacute;</span>'
        f'<span class="tr-munit">attend la premi&egrave;re cohorte calibration</span></div>'
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
        f'<span><b>{n}</b> r&eacute;solu(s)</span><span class="tr-sep">&middot;</span>'
        f'<span><b>{open_n}</b> en attente (hors v0)</span><span class="tr-sep">&middot;</span>'
        f'<span>+<b>{v0_n}</b> v0 quarantine</span><span class="tr-sep">&middot;</span>'
        f'<span>prochaine cohorte <b>10/06</b></span>'
        f'</div>'
        f'</div>'
    )


def _copilot() -> str:
    """Page dediee Copilot (user feedback 31/05) : chat + historique + ce que
    le bot pense par ticker + signaux soft extraits du chat. Place entre
    Positions et Theses en nav. Reactive _conversations_panel + _chat_signals_panel
    qui etaient defines mais non-utilises depuis le retrait 27/05 (commit c4ecebc)."""
    return (
        f'<section data-page="copilot" role="region" aria-label="Copilot">'
        f'<div class="phead"><h2>Copilot</h2>'
        f'<div class="sub">Discussion &middot; synth&egrave;se interventions &middot; historique &middot; ce qu&rsquo;il pense par ticker</div></div>'
        f'{_chat_panel()}'
        f'<div class="vigie-sh">Synth&egrave;se copilot</div>'
        f'{_copilot_panel()}'
        f'{_conceptions_panel()}'
        f'{_conversations_panel()}'
        f'{_chat_signals_panel()}'
        f'</section>'
    )


def _chat_panel() -> str:
    """Sprint 7 — Chat surface : pose une question, contexte assemble cote serveur."""
    n_msg, n_sess, oldest = _chat_memory_stats()
    mem_str = (
        f"il connait ton profil, ta note PF, tes positions, tes theses, "
        f"interventions &middot; m&eacute;moire : {n_msg} messages sur {n_sess} sessions depuis {oldest}"
        if n_msg > 0 else
        "il connait ton profil, ta note PF, tes positions, tes th&egrave;ses et son historique d'interventions"
    )
    return (
        '<div class="card pad chatcard" style="margin-bottom:var(--s4)">'
        '<div class="colhead"><span class="t">Pose une question au copilot</span>'
        f'<span class="a">{mem_str}</span></div>'
        '<div id="chat-log" class="chat-log"></div>'
        '<form id="chat-form" class="chat-form" onsubmit="return chatSend(event)">'
        '<textarea id="chat-input" class="chat-input" aria-label="Pose une question au copilot" placeholder="ex. Quelle est ma plus grosse fragilite en ce moment ?" rows="2"></textarea>'
        '<button type="submit" class="chat-send" aria-label="Envoyer le message">Envoyer</button>'
        '</form>'
        '<div class="chat-foot">Le contexte (profil + grade + positions + interventions) est rejoue a chaque message.</div>'
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
        return "Sans th&egrave;se"
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
            f'<div class="rs"><span>vers la cible</span><span class="mono">{prog:.0f}%</span></div></div>'
        )
    return "".join(rows), hits, top


def _elan_watch(computed: list[dict]) -> tuple[str, int]:
    """Course vers la cible : winners proches du target (axe anti-biais #1, cadrage positif)."""
    data = []
    for r in computed:
        e, t, c = r.get("entry") or 0, r.get("target_full") or 0, r.get("current_price") or 0
        if e and t and t != e:
            prog = (c - e) / (t - e) * 100
            if prog >= 75:
                data.append((prog, r["ticker"]))
    data.sort(key=lambda x: -x[0])
    # Fix ambiguite 31/05 user : "149% vers la cible" pretait a confusion
    # (depassement vs progression). Split en 2 verbiages directionnels :
    # > 100% -> "+X% au-dela cible" (overshoot, prends ton profit / rightsize)
    # < 100% -> "-X% sous cible"   (reste a parcourir, marge restante)
    # = 100% -> "a la cible"
    def _label(prog: float) -> str:
        if prog >= 100.5:
            return f"+{prog - 100:.0f}% au-del&agrave; cible"
        if prog <= 99.5:
            return f"&minus;{100 - prog:.0f}% sous cible"
        return "&agrave; la cible"

    rows = "".join(
        f'<div class="line"><span>{tk}</span><span class="mono">{_label(prog)}</span></div>'
        for prog, tk in data
    )
    watch = (
        rows or '<div class="empty" style="padding:var(--s4) 0">aucune ligne &agrave; &ge;75% de la cible &mdash; marges restantes</div>'
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
            f'<div class="rs"><span>marge avant le stop</span></div></div>'
        )
        if is_near:
            near_rows.append(f'<div class="line"><span>{tk}</span><span class="mono">{down:.0f}% de marge</span></div>')
    watch = (
        "".join(near_rows)
        or '<div class="empty" style="padding:var(--s4) 0">aucune marge faible &mdash; calme</div>'
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
        return p["weight"]

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
        return p["weight"]  # market value post-migration 29/05

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
        key = sectors.get(p["ticker"], "Sans th&egrave;se")
        sw[key] = sw.get(key, 0.0) + _v(p)
    sw_real = {k: v for k, v in sw.items() if k != "Sans th&egrave;se"}
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
        cbits.append("th&egrave;se au-dessus du plafond")
    if over_cap:
        cbits.append(f"{over_cap} ligne(s) hors plafond")
    if cluster_breached:
        cbits.append("cluster corr&eacute;l&eacute; au-dessus du plafond")
    cause = " &middot; ".join(cbits) or "tout sous les plafonds"
    top_cls = "negc" if top_pct >= POS_CAP else "acc"
    these_cls = "negc" if dom_these_pct >= NARRATIVE_CAP else "acc"
    line_msg = f"{top_nm} &middot; {'&#9888; au-dessus du plafond' if top_pct >= POS_CAP else 'sous le plafond'} {POS_CAP:.0f}%"
    these_msg = f"{dom_these} &middot; {'&#9888; all&eacute;ger' if dom_these_pct >= NARRATIVE_CAP else 'sous le plafond'} {NARRATIVE_CAP:.0f}%"
    cap = f"{cost_total:,.0f}".replace(",", "&#8239;")
    # === Star Concentration : fusion verdict + cluster + 3 KPIs ===
    # (ancien rendu cluster row-by-row retire 01/06 -- le Star ne montre que
    # le breach principal en footer, le detail multi-clusters est superflu)
    # Mapping vcls (acc/warn/bear) -> ps-val color class
    _verdict_pcls = {"acc": "acc", "warn": "warn", "bear": "bear"}.get(vcls, "")
    _top_pcls = {"acc": "acc", "warn": "warn", "bear": "bear"}.get(top_cls, "")
    _these_pcls = {"acc": "acc", "warn": "warn", "bear": "bear"}.get(these_cls, "")
    # Footer : cluster gouverneur si breached
    _cluster_foot = ""
    breached = [c for c in _ch if c["breached"]]
    if breached:
        c = breached[0]
        _ov = f"{c['over_eur']:,.0f}".replace(",", "&#8239;")
        _cluster_foot = f"Cluster <b>{c['name']}</b> &agrave; {c['pct']:.0f}% (plafond {c['cap']:.0f}%) &middot; d&eacute;passement +{_ov}&nbsp;&euro;"
    else:
        _cluster_foot = "Cluster corr&eacute;l&eacute; (gouverneur) : sous plafond"
    _overcap_meta = (
        f"{over_cap} ligne(s) au-dessus du plafond {POS_CAP:.0f}%"
        + (f" &middot; {over_nm}" if over_nm else "")
    )
    star_strate_verdict = (
        '<div class="ps-strate">'
        + '<div class="ps-lbl">Verdict concentration</div>'
        + '<div class="ps-macro-row">'
        + f'<div class="ps-val {_verdict_pcls}">{verdict}</div>'
        + f'<div class="ps-macro-meta">{cause}</div>'
        + "</div>"
        + f'<div class="ps-cap">{_overcap_meta}</div>'
        + "</div>"
    )
    star_strate_grid = (
        '<div class="ps-strate ps-grid">'
        + f'<div class="ps-cell"><div class="ps-lbl">Premi&egrave;re ligne</div><div class="ps-val {_top_pcls}">{_pct(top_pct)}%</div><div class="ps-cap">{line_msg}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl">Th&egrave;se dominante</div><div class="ps-val {_these_pcls}">{dom_these_pct:.0f}%</div><div class="ps-cap">{dom_these} &middot; {these_msg}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl">Capital investi</div><div class="ps-val">{cap}&nbsp;&euro;</div><div class="ps-cap">{len(positions)} lignes &middot; {len(sw_real)} secteurs</div></div>'
        + "</div>"
    )
    star_strate_foot = f'<div class="ps-strate ps-foot">{_cluster_foot}</div>'
    star_concentration = (
        f'<div class="page-star">{star_strate_verdict}{star_strate_grid}{star_strate_foot}</div>'
    )
    return (
        f'<section data-page="concentration" role="region" aria-label="Concentration"><div class="phead"><h2>Concentration</h2>'
        f'<div class="sub">Trois axes de concentration &mdash; par ligne, par secteur, par g&eacute;ographie</div></div>'
        f"{star_concentration}"
        f'<div class="card pad"><div class="sbwrap"><div class="sb-top"><div class="sb-kpi"><span class="sb-kl">CAPITAL D&Eacute;PLOY&Eacute;</span><span class="sb-kv">{cap}&nbsp;&euro;</span></div><div class="sb-kpi"><span class="sb-kl">SECTEURS</span><span class="sb-kv">{len(sw_real)}</span></div><div class="sb-kpi"><span class="sb-kl">PLUS GROSSE EXPOSITION</span><span class="sb-kv">{dom_these} &middot; {dom_these_pct:.0f}%</span></div></div><div id="sb-bars" class="sb-bars"></div><div id="sb-panel"></div></div></div>'
        f'<div class="card pad" style="margin-top:var(--s4)"><div class="colhead"><span class="t">Par secteur</span></div>{_sector_blocks(positions, planned, sectors, pnl, names, daily)}</div>'
        f'<div class="card pad" style="margin-top:var(--s4)"><div class="colhead"><span class="t">Par pays</span><span class="a">si&egrave;ge social &middot; pas la cha&icirc;ne d&rsquo;approvisionnement r&eacute;elle (Ta&iuml;wan sous-estim&eacute;)</span></div>{_geo_bars(positions)}</div>'
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
        badge = '<span class="bdg">pr&eacute;vu</span>' if r["prev"] else ""
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
        f"D&eacute;tenu {real_t:.0f}&euro; &middot; pr&eacute;vu {plan_t:.0f}&euro; &middot; "
        f"total {total:.0f}&euro; (${total / fx:.0f}) &middot; {len(order) + (1 if compute_sub else 0)} groupes"
    )
    return (
        f'<div class="sub" style="margin-bottom:var(--s25)">{sub}</div>'
        f'<div class="sec-cols"><span></span><span class="num">&euro;</span><span class="num">$</span>'
        f'<span class="num">%</span><span class="num">Jour</span><span class="num">P&amp;L</span></div>'
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
    try:
        from shared.ticker_names import get_short_name as _gsn
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
        "font-size:12px;border-left:2px solid var(--line2);margin-left:3px}"
        ".geo-stk .gnm{color:var(--ink)}"
        ".geo-stk .gtk{color:var(--steel);font-family:var(--fm);font-size:11px}"
        ".geo-stk .gpc{margin-left:auto;color:var(--steel);font-family:var(--fm);font-size:11px}"
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
            f'<span class="mono" style="font-size:11px;opacity:.65;padding:0 var(--s2);color:{color}"'
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
                f'<div class="rs"><span>{int(buys)} achats &middot; {int(sells)} ventes</span>'
                f'<span class="mono">7&nbsp;j</span></div></div>'
            )
        return rows or '<div class="empty" style="padding:var(--s4) 0">aucun flux insider sur 7&nbsp;j</div>'
    except Exception as e:
        return _err(e)


def _signaux() -> str:
    try:
        s24 = _q("SELECT COUNT(*) FROM signals WHERE timestamp > datetime('now','-1 day')")[0][0]
        s30 = _q("SELECT COUNT(*) FROM signals WHERE timestamp > datetime('now','-30 day')")[0][0]
        n8k = _q("SELECT COUNT(*) FROM filings_8k_log WHERE filed_at > datetime('now','-60 day')")[0][0]
    except Exception as e:
        return f'<section data-page="signaux" role="region" aria-label="Signaux"><div class="phead"><h2>Signaux</h2></div>{_err(e)}</section>'

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
        for tk, sev, codes, reason, filed in _q(
            "SELECT ticker, COALESCE(severity,''), COALESCE(item_codes,''), COALESCE(severity_reason,''), filed_at "
            "FROM filings_8k_log WHERE filed_at > datetime('now','-60 day') "
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
        eightk = rows8k or '<div class="empty" style="padding:var(--s4) 0">aucun 8-K sur 60&nbsp;j</div>'
    except Exception as e:
        eightk, tally_str = _err(e), "&mdash;"

    try:
        rowsib = ""
        for tk, det, buyers, buym, strength in _q(
            "SELECT ticker, detected_at, COALESCE(distinct_buyers,0), COALESCE(total_buy_m,0), COALESCE(cluster_strength,'') "
            "FROM insider_buy_clusters_log ORDER BY detected_at DESC LIMIT 8"
        ):
            rowsib += (
                f'<div class="row"><div class="rt"><span class="tk tkc" data-tk="{tk}">{tk}</span>'
                f'<span class="tag acc2">{strength or "&mdash;"}</span></div>'
                f'<div class="rs"><span>{int(buyers)} acheteurs &middot; {float(buym):.1f}M$</span>'
                f'<span class="mono">{str(det)[:10]}</span></div></div>'
            )
        insiders = (
            rowsib
            or '<div class="empty" style="padding:var(--s4) 0">aucun cluster d\'achats group&eacute;s d&eacute;tect&eacute;</div>'
        )
    except Exception as e:
        insiders = _err(e)

    try:
        nsrc = _q("SELECT COUNT(*) FROM sources")[0][0]
        src_rows = ""
        for name, cred, n in _q(
            "SELECT name, credibility, COALESCE(n_signals,0) FROM sources ORDER BY credibility DESC, n_signals DESC LIMIT 10"
        ):
            cv = float(cred or 0)
            col = "acc2" if cv >= 0.65 else ("warn" if cv >= 0.45 else "calm")
            src_rows += (
                f'<div class="row"><div class="rt"><span class="tk">{str(name)[:24]}</span>'
                f'<span class="tag {col}">{cv:.2f}</span></div>'
                f'<div class="axis"><div class="axis-mark" style="left:{max(2.0, min(100.0, cv * 100)):.1f}%" title="cr&eacute;dibilit&eacute; {cv:.2f}"></div></div>'
                f'<div class="rs"><span>cr&eacute;dibilit&eacute;</span><span class="mono">{int(n)} signaux</span></div></div>'
            )
    except Exception as e:
        src_rows, nsrc = _err(e), 0

    # === Star Signaux : verdict activite + 3 KPIs flow + tally severite ===
    # Verdict activite 24h : ACTIF si s24 >= 5, sinon CALME (seuil approximatif
    # ajuste si besoin avec backlog reel observe).
    if s24 >= 5:
        _act_cls, _act_lbl, _act_cap = "warn", "ACTIF", f"{s24} signaux entrants 24h"
    elif s24 >= 1:
        _act_cls, _act_lbl, _act_cap = "", "MOD&Eacute;R&Eacute;", f"{s24} signal(aux) 24h &middot; flux normal"
    else:
        _act_cls, _act_lbl, _act_cap = "acc", "CALME", "aucun signal 24h"
    star_strate_act = (
        '<div class="ps-strate">'
        + '<div class="ps-lbl">Activit&eacute; signaux 24h</div>'
        + '<div class="ps-macro-row">'
        + f'<div class="ps-val {_act_cls}">{_act_lbl}</div>'
        + f'<div class="ps-macro-meta">{_act_cap}</div>'
        + "</div>"
        + "</div>"
    )
    star_strate_kpis = (
        '<div class="ps-strate ps-grid">'
        + f'<div class="ps-cell"><div class="ps-lbl">Signaux 24&nbsp;h</div><div class="ps-val">{s24}</div><div class="ps-cap">Gmail + EDGAR</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl">Signaux 30&nbsp;j</div><div class="ps-val">{s30}</div><div class="ps-cap">fen&ecirc;tre roulante</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl">8-K &middot; 60&nbsp;j</div><div class="ps-val">{n8k}</div><div class="ps-cap">{tally_str}</div></div>'
        + "</div>"
    )
    star_strate_foot = (
        '<div class="ps-strate ps-foot">'
        + f'{nsrc} sources actives &middot; recalibrage cr&eacute;dibilit&eacute; 1er du mois'
        + "</div>"
    )
    star_signaux = (
        f'<div class="page-star">{star_strate_act}{star_strate_kpis}{star_strate_foot}</div>'
    )
    cols = (
        f'<div class="cols">'
        f'<div class="col"><div class="colhead"><span class="t">8-K r&eacute;cents</span><span class="a">{tally_str}</span></div><div class="card">{eightk}</div></div>'
        f'<div class="col"><div class="colhead"><span class="t">Cr&eacute;dibilit&eacute; des sources</span><span class="a">{nsrc} sources &middot; recal 1er du mois</span></div><div class="card">{src_rows}</div></div>'
        f"</div>"
    )
    insider_flow = _insider_flow_strip_html()
    insider_flow_strip = (
        f'<div class="colhead spaced"><span class="t">Flux d\'initi&eacute;s &middot; 7&nbsp;j</span>'
        f'<span class="a">net buy/sell agr&eacute;g&eacute; &middot; &#9733; = en portefeuille</span></div>'
        f'<div class="card pad">{insider_flow}</div>'
    )
    # Clusters strip : montre seulement si non-empty (insider_buy_clusters_log
    # actuellement vide, s'affichera quand cluster detection fire).
    empty_clusters_msg = "aucun cluster d'achats group"
    insider_clusters_strip = ""
    if empty_clusters_msg not in insiders:
        insider_clusters_strip = (
            f'<div class="colhead spaced"><span class="t">Clusters d\'achats group&eacute;s</span>'
            f'<span class="a">60&nbsp;j &middot; Form 4 EDGAR</span></div>'
            f'<div class="card pad">{insiders}</div>'
        )
    # Track record + sante distribution remontes ici (depuis vue d'ensemble)
    # 01/06 user pref : la page signaux groupe le pilotage qualite des signaux
    # (track record + 6 vigilances + 8-K + insider flux).
    return (
        f'<section data-page="signaux" role="region" aria-label="Signaux"><div class="phead"><h2>Signaux</h2>'
        f'<div class="sub">Track record &middot; sant&eacute; distribution &middot; d&eacute;p&ocirc;ts 8-K &middot; flux d\'initi&eacute;s</div></div>'
        f"{star_signaux}{_track_record_panel()}{_distribution_health_panel()}{cols}{insider_flow_strip}{insider_clusters_strip}</section>"
    )


_MACRO_BANDS = {
    "VIX": (22.0, 30.0, True),
    "HY_OAS": (350.0, 500.0, True),
    "MOVE": (100.0, 130.0, True),
    "USDJPY": (152.0, 160.0, True),
    "TYX": (4.5, 5.0, True),
    "DXY": (104.0, 108.0, True),
    "CoreCPI": (3.0, 4.0, True),
    "CPI": (3.0, 4.0, True),
    "T10Y2Y": (0.2, 0.0, False),
    "MfgIP": (0.0, -2.0, False),
    # V3 (task #42) : drawdown BTC, lower = worse (hi_bad=False)
    "BTC_drawdown180": (-30.0, -50.0, False),
}


_MACRO_TIPS: dict[str, str] = {
    "TYX": "Coût capital long. > 5% = multiples growth/tech craquent historiquement.",
    "Gold": "Couverture taux réels / débasement / géopol. Lecture interprétative.",
    "USDJPY": "Baromètre carry trade. > 160 = zone intervention BoJ → tail risk unwind tech US.",
    "VIX": "Vol implicite S&P 500 30j. < 15 euphorie, > 25 stress, > 40 panique.",
    "HY_OAS": "Prime obligations haut rendement vs Treasury. < 300 = complacent, > 600 = panique. Signal avancé.",
    "DXY": "USD vs 6 majeures. > 105 = vent contraire multinationales US ; > 110 = stress global.",
    "BTC_drawdown180": "Drawdown BTC vs max 6 mois. < -30% = bear risk-off, < -50% = capitulation. Capte le stress crypto reel sans confondre avec niveau brut.",
    "MOVE": "VIX des Treasuries. > 130 = stress obligataire, souvent avancé sur actions.",
    "T10Y2Y": "Courbe des taux 10A-2A. Dé-inversion (passage <0 vers >0) = récession dans 3-6 mois.",
    "BankReserves": "Cash bancaire à la Fed. < 2.5T = stress plomberie imminent.",
    "RepoSRF": "Standing Repo Facility. > 30B = banques court de cash, alarme plomberie aiguë.",
    "FedBalance_yoy": "Bilan Fed variation YoY %. > +20% = QE emergency (Fed combat crash). < -10% = QT agressif. +- 5% = stable.",
    "KRE": "ETF banques régionales. Décrochage brutal = signal stress type SVB.",
    "CopperGold": "Cuivre industriel vs or refuge. Monte = cycle haussier, baisse = peur récession.",
    "CoreCPI": "Core CPI YoY. > 2.5% = Fed bloquée en restrictif → vent contraire growth/tech.",
    "CPI": "Core CPI YoY. > 2.5% = Fed bloquée en restrictif → vent contraire growth/tech.",
    "MfgIP": "Production industrielle YoY. > 0 = expansion molle ou forte.",
    "MfgIP_yoy": "Production industrielle YoY. > 0 = expansion molle ou forte.",
}


def _macro_dot(ind: str, v: float) -> str:
    "Couleur du point macro selon le niveau reel (decouplee de la phase). Inconnu -> mute."
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
            f'<span class="dname">{name} <span style="color:var(--steel);font-size:11px">({tk})</span></span>'
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
    tip = "Equipondere (RSP) vs ponder&eacute; capitalisation (SPY). > MM50 = hausse large (saine). < MM50 = mega-caps isol&eacute;es (fragile)."
    tip_attr = f' data-tip="{_h.escape(tip, quote=True)}"'
    return (
        f'<div class="drow"{tip_attr}><span class="ddot {dot}"></span>'
        f'<span class="dname">RSP / SPY ratio <span style="color:var(--steel);font-size:11px">vs MM50</span></span>'
        f'<span class="dval {dot}">{delta_pct:+.2f}%</span><span class="dp">{tag}</span></div>'
    )


def _urgence(watch: str, near: int, positions: list[dict], pnl: dict, elan: str = "", near_t: int = 0) -> str:
    debt_map = {
        # Tier 1: Marché & liquidité — alertes en haut, crédit/peur/FX/sentiment, hedge en bas
        "TYX": (1, "Taux US 30 ans (%)", 4, False),
        "USDJPY": (1, "USD/JPY", 2, False),
        "HY_OAS": (1, "Spread HY (bp)", 2, False),
        "VIX": (1, "VIX", 2, False),
        "DXY": (1, "Dollar (DXY)", 2, False),
        "BTC_drawdown180": (1, "BTC drawdown 6 mois (%)", 1, False),
        "Gold": (1, "Or ($/oz)", 0, True),
        # Tier 2: Stress bancaire & liquidité Fed — signaux avancés en haut, plomberie milieu, slow bas
        "MOVE": (2, "Vol. obligataire (MOVE)", 2, False),
        "T10Y2Y": (2, "Pente 10a-2a (%)", 4, False),
        "BankReserves": (2, "R&eacute;serves bancaires Fed ($M)", 0, True),
        "RepoSRF": (2, "Standing Repo Facility ($B)", 2, False),
        "KRE": (2, "Banques r&eacute;gionales ($)", 2, False),
        "CopperGold": (2, "Ratio cuivre/or", 4, False),
        # Tier 3: Macro lente
        "CoreCPI": (3, "Inflation core (%)", 4, False),
        "CPI": (3, "Inflation core (%)", 4, False),
        "MfgIP": (3, "Production industrielle (%)", 4, False),
        "MfgIP_yoy": (3, "Production industrielle (%)", 4, False),
        "FedBalance_yoy": (3, "Bilan Fed YoY (%)", 1, False),
    }
    tnames = {
        1: "March&eacute; &amp; liquidit&eacute;",
        2: "Stress bancaire &amp; liquidit&eacute; Fed",
        3: "Macro lente",
        9: "Autres",
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
        stale = '<span class="stale">p&eacute;rim&eacute;</span>' if _age > _STALE.get(tier, 10) else ""
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
        f"VIX {_vix:.1f} {'&ge;' if _reduced else '&lt;'} {_vthr} (r&egrave;gle VIX seule)"
        if _vix is not None else "VIX indisponible"
    )
    # Frise macro V3 (task #42 portage 01/06) : formule debt_monitor avec 3
    # transformations structurelles (BTC_drawdown180 / FedBalance_yoy / MfgIP
    # P4 -5%). Validee OOS 7/8 dates non-anchor + 5/5 regimes soutenus
    # (cf docs/backtests/debt_composite_2017_2026_v3_insample.csv).
    _PHASE_LBL = {1: "STABLE", 2: "STRESS", 3: "ALERTE", 4: "CRISE"}
    _PHASE_COL = {1: "acc", 2: "warn", 3: "warn", 4: "bear"}
    clabel = _PHASE_LBL.get(cphase, "INCONNU")
    _conc = []
    for _c in _cluster_health(positions, pnl):
        if _c["breached"]:
            _ov = f"{_c['over_eur']:,.0f}".replace(",", "&#8239;")
            _conc.append(f"all&eacute;ger {_c['name']} &middot; +{_ov}&#8239;&euro;")
    _phase_col = _PHASE_COL.get(cphase, "steel")
    # Strate 1 : etat macro + frise STRESS pleine largeur
    star_macro = (
        '<div class="ps-strate">'
        + '<div class="ps-lbl">&Eacute;tat macro</div>'
        + '<div class="ps-macro-row">'
        + f'<div class="ps-val {_phase_col}">{clabel}</div>'
        + f'<div class="ps-macro-meta">phase {cphase}/4 &middot; indice {score:.0f}</div>'
        + "</div>"
        + f'<div class="ps-frise"><div class="ps-frise-mark" style="left:{(cphase - 0.5) * 25:.0f}%"></div></div>'
        + '<div class="ps-frise-labs"><span>stable</span><span>stress</span><span>alerte</span><span>crise</span></div>'
        + "</div>"
    )
    # Strate 2 : 3 cellules (frictions, cibles, stops)
    if _conc:
        f_cls, f_val, f_lbl, f_cap = "bear", len(_conc), "FRICTIONS", _conc[0]
    else:
        f_cls, f_val, f_lbl, f_cap = "acc", 0, "ALIGN&Eacute;", "concentration sous les plafonds"
    t_cap = "marge restante OK" if near_t else "rien proche de la cible"
    s_cls = "bear" if near else "acc"
    s_cap = "&agrave; surveiller" if near else "calme"
    star_grid = (
        '<div class="ps-strate ps-grid">'
        + f'<div class="ps-cell"><div class="ps-lbl">{f_lbl}</div><div class="ps-val {f_cls}">{f_val}</div><div class="ps-cap">{f_cap}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl">Cibles &ge;75%</div><div class="ps-val">{near_t}</div><div class="ps-cap">{t_cap}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl">Stops &lt;10%</div><div class="ps-val {s_cls}">{near}</div><div class="ps-cap">{s_cap}</div></div>'
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
        f'<section data-page="urgence" role="region" aria-label="Urgence"><div class="phead"><h2>Urgence</h2>'
        f'<div class="sub">&Eacute;lan vers les cibles &middot; marge avant les stops &middot; stress macro</div></div>'
        f"{star}"
        f'<div class="cols">'
        f'<div><div class="ph3">Course vers la cible</div><div class="card pad">{elan}</div></div>'
        f'<div><div class="ph3">Marges les plus faibles</div><div class="card pad">{watch}</div></div>'
        f'<div><div class="ph3">Moniteur de stress macro &mdash; score {score:.0f}</div>'
        f'<div class="card pad"><div class="dlist"><style>.ddot.mute{{background:var(--steel);box-shadow:none;opacity:.6}}</style>{blocks}</div></div></div></div>'
        f'<div class="cols">'
        f'<div><div class="ph3">Momentum march&eacute; &middot; RSI(14) daily &middot; cache 30min</div>'
        f'<div class="card pad"><div class="dlist">{rsi_html}</div></div></div>'
        f'<div><div class="ph3">Largeur du march&eacute; &middot; participation</div>'
        f'<div class="card pad"><div class="dlist">{breadth_html}</div></div></div>'
        f"</div></section>"
    )


def _tape_8k() -> str:
    sevcls = {"HIGH": "neg", "MEDIUM": "warn", "MED": "warn", "LOW": "pos"}
    try:
        rows = _q(
            "SELECT ticker, COALESCE(severity,''), COALESCE(severity_reason,''), COALESCE(item_codes,''), filed_at "
            "FROM filings_8k_log WHERE filed_at > datetime('now','-60 day') ORDER BY filed_at DESC LIMIT 18"
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
        "; ".join(f"{f['ticker']} ~{int(f['drift_eur'])} EUR" for f in RECONCILE_FLAGS) if drift_count else "aucune"
    )

    INK, WARN, DANGER = "var(--ink)", "var(--warn)", "var(--bear)"

    if dec_30d < 2:
        dec_color, dec_sub = DANGER, "journal sous-aliment&eacute;"
    elif dec_30d < 5:
        dec_color, dec_sub = WARN, "feed le journal"
    else:
        dec_color, dec_sub = INK, f"{dec_30d} d&eacute;c. / 30j"

    drift_color = WARN if drift_count else INK
    panic_color = INK if panic == 0 else DANGER
    panic_sub = "KPI #4 tenu" if panic == 0 else f"KPI #4 cass&eacute; ({panic})"

    if days_to_jun10 <= 3:
        cd_color = DANGER
    elif days_to_jun10 <= 7:
        cd_color = WARN
    else:
        cd_color = INK

    if days_to_jun10 > 0:
        countdown, countdown_sub = f"J-{days_to_jun10}", f"10/06 &middot; {preds_due} pred. r&eacute;solvent"
    elif days_to_jun10 == 0:
        countdown, countdown_sub = "AUJOURD'HUI", f"{preds_due} pred. r&eacute;solvent"
    else:
        countdown, countdown_sub = f"J+{-days_to_jun10}", f"batch pass&eacute; &middot; {preds_due} en retard"

    css = (
        "<style>"
        ".ck-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:var(--s3);margin-top:var(--s2)}"
        ".ck-cell{padding:var(--s35) 4px;border-bottom:1px solid var(--line)}"
        ".ck-label{font-size:12px;color:var(--steel);letter-spacing:.01em}"
        ".ck-num{font-family:var(--fm);font-size:22px;font-weight:500;margin-top:var(--s15);line-height:1.05;letter-spacing:-.01em}"
        ".ck-sub{font-size:12px;color:var(--steel);margin-top:var(--s15);line-height:1.4}"
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
        cell("D&eacute;cisions logg&eacute;es &middot; 30j", str(dec_30d), dec_sub, dec_color)
        + cell("Batch Brier", countdown, countdown_sub, cd_color)
        + cell(
            "R&eacute;conciliation book", f"{drift_count} ligne{'s' if drift_count > 1 else ''}", drift_sub, drift_color
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
        "entry": "Entr&eacute;e",
        "scale_in": "Renforcement",
        "partial_exit": "All&egrave;gement",
        "full_exit": "Sortie",
        "override": "D&eacute;rogation",
        "no_action_flag": "Non-action document&eacute;e",
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
_LOGO = (Path(__file__).parent / "static" / "brand" / "presage_symbol.svg").read_text(encoding="utf-8")

_TH_CSS = """
<style>
  .th-gap { margin-bottom:var(--s4); }
  .th-hist { display:flex; flex-direction:column; gap:var(--s15); padding:2px 0; }
  .th-hbar { display:flex; align-items:center; gap:11px; font-family:var(--fm); font-size:12px; }
  .th-hlab { width:24px; color:var(--steel); }
  .th-hbar .axis { flex:1; margin:0; }
  .th-hn { width:22px; text-align:right; color:var(--ink); font-weight:600; }
  .th-grp { font-family:var(--fb); font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin:34px 2px 13px; display:flex; align-items:center; gap:var(--s3); }
  .th-grp::after { content:""; flex:1; height:1px; background:var(--line); }
  /* Sprint 2 purge borders TR-style : retire border + bg fill par thesis row.
     Garde padding pour respiration + grid layout + hover propre. Separation
     entre rows via whitespace + une hairline subtile via border-bottom. */
  .th-row { display:grid; grid-template-columns:160px 46px 1fr; gap:var(--s3); align-items:center; padding:14px 4px; border-bottom:1px solid var(--line); margin-bottom:0; cursor:pointer; transition:background .15s; }
  .th-row:last-child { border-bottom:none; }
  .th-row:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); }
  .th-id { display:flex; align-items:center; gap:9px; flex-wrap:wrap; }
  .th-conv { font-family:var(--fm); font-weight:600; font-size:11px; letter-spacing:.04em; padding:2px 7px; border-radius:var(--r1); }
  .th-conv.c5 { color:var(--bg); background:var(--ink); }
  .th-conv.c4 { color:var(--bg); background:var(--acc); }
  .th-conv.c3 { color:var(--bg); background:var(--warn); }
  .th-conv.c2 { color:var(--steel); border:1px solid var(--line2); }
  .th-conv.c1 { color:var(--steel); border:1px solid var(--line); opacity:.65; }
  .th-tk { font-weight:600; font-size:13px; }
  .th-w { font-family:var(--fm); font-size:12px; font-weight:600; color:var(--ink); text-align:right; align-self:center; }
  .th-dir { font-family:var(--fb); font-size:11px; color:var(--steel); text-transform:uppercase; letter-spacing:.12em; }
  .th-bar { display:flex; flex-direction:column; gap:var(--s15); grid-column:1/-1; margin-top:var(--s2); }
  .sizebar { margin:var(--s15) 0 4px; }
  .th-adj { font-family:var(--fm); font-size:11px; letter-spacing:.02em; line-height:1.3; }
  .th-adj.trim { color:var(--warn); }
  .th-adj.add { color:var(--acc2); }
  .th-adj.ok { color:var(--steel); }
  .th-szcol { display:flex; flex-direction:column; gap:5px; }
  .th-zone-loss { position:absolute; left:0; top:0; bottom:0; background:color-mix(in srgb, var(--bear) 13%, transparent); }
  .th-zone-profit { position:absolute; right:0; top:0; bottom:0; background:color-mix(in srgb, var(--acc) 13%, transparent); }
  .th-ends { display:flex; justify-content:space-between; align-items:baseline; font-family:var(--fm); font-size:11px; }
  .th-stop { color:var(--bear); }
  .th-tgt { color:var(--acc); font-weight:600; }
  .th-pt { font-family:var(--fm); font-size:11px; padding:1px 7px; border-radius:var(--r1); background:color-mix(in srgb,var(--bear) 16%,transparent); color:var(--bear); letter-spacing:.04em; margin-left:var(--s2); text-transform:uppercase; }
  .th-na { font-family:var(--fm); font-size:11px; color:var(--steel); }
  .th-cat { font-family:var(--fm); font-size:11px; letter-spacing:.03em; color:var(--steel); background:color-mix(in srgb, var(--steel) 10%, transparent); border:1px solid var(--line); border-radius:var(--r1); padding:2px 8px; margin-left:2px; white-space:nowrap; }
</style>
"""

_TIER_LABEL = {
    5: "Conviction 5 &middot; la plus forte",
    4: "Conviction 4",
    3: "Conviction 3 &middot; m&eacute;diane",
    2: "Conviction 2",
    1: "Conviction 1 &middot; faibles",
}


def _theses(names: dict, sectors: dict, positions: list, pnl: dict) -> str:
    "Page Theses : asymetrie cible/stop par conviction + gap cible partielle."
    rows = _q(
        "SELECT ticker, conviction, direction, entry_price, stop_price, target_full, "
        "target_partial, last_price FROM theses WHERE status='active' "
        "ORDER BY conviction DESC, ticker"
    )
    if not rows:
        return (
            '<section data-page="theses" role="region" aria-label="Theses"><div class="phead"><h2>Th&egrave;ses</h2>'
            '<div class="sub">aucune th&egrave;se active</div></div></section>'
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
        # current_price EUR donnait des % absurdes (4063.T cible +23876% etc.).
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
        f"&#9888; inflation de conviction : c5 = {c5_pct:.0f}% (seuil 20%)"
        if infl
        else f"c5 = {c5_pct:.0f}% &middot; pas d&rsquo;inflation (seuil 20%)"
    )

    # === Star Theses : conviction mediane + 3 cells (cibles, gain, marges) ===
    pcls = "acc" if n_profit * 2 >= n else "bear"
    ncls = "bear" if n_near else "acc"
    _tg_cls = "acc" if n_near_tgt else ""
    _conv_lbl = f"M&Eacute;DIANE c{med}"
    _conv_cap = f"{n} th&egrave;se(s) active(s) &middot; {dist[5]} c5 ({c5_pct:.0f}%)"
    if infl:
        _conv_cls = "warn"
    elif med >= 4:
        _conv_cls = "acc"
    else:
        _conv_cls = ""
    hero = (
        f'<div class="page-star">'
        f'<div class="ps-strate ps-grid">'
        f'<div class="ps-cell"><div class="ps-lbl">Proches de la cible</div><div class="ps-val {_tg_cls}">{n_near_tgt}</div><div class="ps-cap">marge &lt; 12%</div></div>'
        f'<div class="ps-cell"><div class="ps-lbl">En gain</div><div class="ps-val {pcls}">{n_profit}/{n}</div><div class="ps-cap">cours &gt; co&ucirc;t d&rsquo;entr&eacute;e</div></div>'
        f'<div class="ps-cell"><div class="ps-lbl">Marges faibles</div><div class="ps-val {ncls}">{n_near}</div><div class="ps-cap">marge &lt; 10% du stop</div></div>'
        f'</div>'
        f'<div class="ps-strate"><div class="ps-lbl">Convictions</div>'
        f'<div class="ps-macro-row"><div class="ps-val {_conv_cls}">{_conv_lbl}</div>'
        f'<div class="ps-macro-meta">{_conv_cap}</div></div>'
        f'<div class="ps-cap">{infl_msg}</div></div>'
        f'<div class="ps-strate ps-foot">R&eacute;partition par conviction ci-dessous</div>'
        f'</div>'
    )
    # Repartition par conviction (ancien hero 2nd col) reste en panneau detail
    kpis = (
        f'<div class="card pad" style="margin-bottom:var(--s4)">'
        f'<div class="ps-lbl" style="margin-bottom:14px">R&eacute;partition par conviction</div>'
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
        secw = {}
        for _t in tier:
            secw[_t["cat"]] = secw.get(_t["cat"], 0.0) + vmap.get(_t["tk"], 0.0)
        grp = sorted(tier, key=lambda t: (-secw.get(t["cat"], 0.0), t["cat"] or "~~~", -vmap.get(t["tk"], 0.0)))
        if not grp:
            continue
        _tgt_tier = (_caps.get(c, 0) / _sumcaps * 100) if _caps.get(c) else None
        _tgt_lab = f" &middot; cible {_tgt_tier:.1f}%/ligne" if _tgt_tier else ""
        groups += f'<div class="th-grp">{_TIER_LABEL.get(c, "Conviction " + str(c))} &middot; {len(grp)}{_tgt_lab}</div><div class="th-grid">'
        for t in grp:
            if t["has_bar"]:
                if t["entry_frac"] is not None:
                    zones = f'<div class="axis-tick dash" style="left:{t["entry_frac"]:.1f}%"></div>'
                else:
                    zones = ""
                bar = (
                    '<div class="th-bar"><div class="axis">'
                    f'{zones}<div class="axis-mark" style="left:{t["frac"]:.1f}%" title="position {t["frac"]:.1f}% entre stop et cible"></div></div>'
                    '<div class="th-ends">'
                    f'<span class="th-stop">stop &minus;{t["d_stop"]:.0f}%</span>'
                    f'<span class="th-tgt">cible +{t["d_tgt"]:.0f}%</span></div></div>'
                )
            else:
                bar = '<div class="th-na">donn&eacute;es de prix incompl&egrave;tes</div>'
            anchor = ""
            if t["has_bar"] and t["pnl_e"] is not None:
                _crypto = t["tk"] in crypto_tk
                if t["pnl_e"] >= 12 and not _crypto:
                    _acls = "acc"
                    _amsg = "Ligne en gain, marge de hausse restante. Biais : s&eacute;curiser trop t&ocirc;t. R&egrave;gle : laisser courir vers la cible."
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
                _scale = _cappct * 1.3
                _tgt_pos = min(_tgt / _scale * 100, 100.0)
                _w_pos = min(max(wv / _scale * 100, 0.0), 100.0)
                sizebar = (
                    '<div class="axis sizebar">'
                    f'<div class="axis-tick" style="left:{_tgt_pos:.1f}%"></div>'
                    '<div class="axis-tick strong" style="left:76.9%"></div>'
                    f'<div class="axis-mark" style="left:{_w_pos:.1f}%" title="poids {_w_pos:.1f}%"></div>'
                    '</div>'
                )
                _d = wv - _tgt
                _v = abs(_d) / 100 * vtot
                _de = f"{_v / 1000:.1f}k" if _v >= 1000 else f"{round(_v / 50) * 50:.0f}"
                if _d > 0.4:
                    _tail = f" &middot; &gt; cap {_cappct:.0f}%" if wv > _cappct else ""
                    adj = f'<div class="th-adj trim">all&eacute;ger &minus;{_de}&nbsp;&euro;{_tail}</div>'
                elif _d < -0.4:
                    adj = f'<div class="th-adj add">renforcer +{_de}&nbsp;&euro;</div>'
                else:
                    adj = '<div class="th-adj ok">&check; au poids</div>'
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
        '<section data-page="theses" role="region" aria-label="Theses"><div class="phead"><h2>Th&egrave;ses</h2>'
        '<div class="sub">Asym&eacute;trie cible / stop, par niveau de conviction</div></div>'
        f"{_TH_CSS}{hero}{kpis}{gap}{groups}</section>"
    )


_NAV = (
    '<nav class="nav" role="navigation" aria-label="Navigation principale">'
    '<div class="nitem on" data-nav="vigie"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14a8 8 0 0 1 16 0"/><path d="M12 14l4.5-3.5"/><circle cx="12" cy="14" r="1.3" fill="currentColor" stroke="none"/></svg><span class="nlab">Vue d&rsquo;ensemble</span></div>'
    '<div class="nitem" data-nav="discipline"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg><span class="nlab">Discipline &amp; Biais</span></div>'
    '<div class="nitem" data-nav="positions"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4l8 4-8 4-8-4 8-4z"/><path d="M4 12l8 4 8-4"/><path d="M4 16l8 4 8-4"/></svg><span class="nlab">Positions</span></div>'
    '<div class="nitem" data-nav="copilot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg><span class="nlab">Copilot</span></div>'
    '<div class="nitem" data-nav="theses"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/></svg><span class="nlab">Th&egrave;ses</span></div>'
    '<div class="nitem" data-nav="strategie"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M5 9 L7 14 L10 10 L12 14 L14 10 L17 14 L19 9 V18 H5 Z"/><path d="M5 14h14"/></svg><span class="nlab">Strat&eacute;gie</span></div>'
    '<div class="nitem" data-nav="concentration"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><path d="M12 12V4"/><path d="M12 12l6.5 4"/></svg><span class="nlab">Concentration</span></div>'
    '<div class="nitem" data-nav="signaux"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="13" r="1.6" fill="currentColor" stroke="none"/><path d="M8.6 9.6a5 5 0 0 0 0 6.8"/><path d="M15.4 9.6a5 5 0 0 1 0 6.8"/><path d="M6 7a8.5 8.5 0 0 0 0 12"/><path d="M18 7a8.5 8.5 0 0 1 0 12"/></svg><span class="nlab">Signaux</span></div>'
    '<div class="nitem" data-nav="urgence"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4l8.5 15H3.5L12 4z"/><path d="M12 10v4.5"/><circle cx="12" cy="17.5" r="0.7" fill="currentColor" stroke="none"/></svg><span class="nlab">Urgence</span></div></nav>'
)

_TOKENS_CSS = (Path(__file__).parent / "tokens.css").read_text(encoding="utf-8")

_CSS = """
  * { box-sizing:border-box; }
  /* Accessibility focus-visible (keyboard nav). Polish DA 31/05.
     - Suppress browser default outline-on-click (ugly, non-keyboard)
     - Outline propre pour TAB navigation (keyboard) avec offset coherent palette
     - Cohorent dark/light : utilise var(--ink) qui flip automatiquement */
  :focus { outline: none; }
  :focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; border-radius: var(--r1); }
  .modetgl:focus-visible { outline-color: var(--ink); }
  /* Respect prefers-reduced-motion : users avec sensibilite vestibulaire / a11y.
     Force animations/transitions ultra-courtes (= comportement quasi-instantane).
     Polish DA 31/05. */
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }
  }
  .dband { position:sticky; top:var(--s25); z-index:45; display:flex; align-items:center; gap:13px; padding:11px 17px; margin:0 0 22px; border:1px solid var(--line3); border-radius:var(--r3); background:color-mix(in srgb,var(--panel) 85%,transparent); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); cursor:pointer; transition:border-color .15s,background .15s; }
  .dband:hover { background:color-mix(in srgb,var(--panel) 95%,transparent); }
  .dband .dd { width:9px; height:9px; border-radius:50%; flex:none; }
  .dband.bear .dd { background:var(--bear); }
  .dband.acc .dd { background:var(--acc); } .dband.size .dd { background:var(--metal); }
  .dband .dv { font-family:var(--fd); font-weight:500; font-size:11px; letter-spacing:.18em; text-transform:uppercase; flex:none; }
  .dband.bear .dv { color:var(--bear); }
  .dband.acc .dv { color:var(--acc); }
  .dband.size .dv { color:var(--metal); }
  .dband .dx { font-family:var(--fm); font-size:12px; color:var(--steel); flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .dband .dn { font-family:var(--fm); font-size:12px; color:var(--ink); font-weight:600; flex:none; }
  .dband .dc { font-size:18px; line-height:1; color:var(--steel); flex:none; transition:transform .15s,color .15s; }
  .dband:hover .dc { color:var(--ink); transform:translateX(3px); }
  .dband.bear .dx, .dband.bear .dn, .dband.bear .dc { color:var(--bear); } .dband.acc .dx, .dband.acc .dn, .dband.acc .dc { color:var(--acc); }
  .sec-super { border:1px solid var(--line2); border-radius:var(--r2); padding:var(--s1) 8px 8px; margin-bottom:16px; background:color-mix(in srgb,var(--ink) 2%,transparent); }
  .sec-superh { display:flex; align-items:baseline; justify-content:space-between; gap:var(--s3); padding:13px 12px 10px; flex-wrap:wrap; }
  .sec-supername { font-family:var(--fd); font-weight:500; font-size:18px; letter-spacing:0; color:var(--ink); }
  .sec-subwrap { display:flex; flex-direction:column; gap:var(--s1); }
  .sec-super .sec-grp.sub { margin:0; border-left:2px solid var(--line); border-radius:0 10px 10px 0; }
  .sec-super .sec-grp.sub .sec-name { font-family:var(--fd); font-weight:600; font-size:13px; color:var(--steel); letter-spacing:0; }
  body { font-family:var(--fb); font-size:var(--t-base); color:var(--ink); margin:0; display:flex; min-height:100vh; background:var(--bg); -webkit-font-smoothing:antialiased; transition:background .3s ease,color .3s ease; }
  .sidebar { width:78px; flex-shrink:0; background:transparent; border-right:1px solid var(--line); padding:20px 0; display:flex; flex-direction:column; align-items:center; position:sticky; top:0; align-self:flex-start; height:100vh; }
  .logo { display:flex; align-items:center; justify-content:center; margin-bottom:22px; padding:0; }
  .logo svg { width:66px; height:auto; color:var(--ink); }
  .logo .wm { display:none; }
  .nav { display:flex; flex-direction:column; gap:var(--s1); align-items:center; width:100%; }
  .nitem { position:relative; display:flex; align-items:center; justify-content:center; width:48px; height:48px; border-radius:var(--r3); cursor:pointer; color:var(--steel); border-left:2px solid transparent; transition:.15s; }
  .nitem svg { width:26px; height:26px; }
  .nitem:hover { background:color-mix(in srgb,var(--ink) 4%,transparent); color:var(--ink); }
  .nitem.on { background:color-mix(in srgb,var(--id) 13%,transparent); color:var(--ink); border-left-color:var(--id); box-shadow:inset 0 0 22px -10px color-mix(in srgb,var(--id) 55%,transparent); }
  .nlab { position:absolute; left:56px; top:50%; transform:translateY(-50%); white-space:nowrap; background:var(--panel); border:1px solid var(--line2); border-radius:var(--r2); padding:var(--s2) 12px; font-family:var(--fb); font-size:13px; font-weight:500; color:var(--ink); opacity:0; pointer-events:none; transition:opacity .14s ease; z-index:80; box-shadow:0 10px 26px -12px #000; }
  .nitem:hover .nlab { opacity:1; }
  .foot { margin-top:auto; padding:var(--s3) 0 2px; display:flex; flex-direction:column; align-items:center; gap:7px; }
  .rfoot { display:flex; flex-direction:column; align-items:center; gap:var(--s15); }
  .rfm { font-family:var(--fm); font-size:11px; color:var(--steel); }
  .rfmacro { width:8px; height:8px; border-radius:2px; }
  .dot { width:7px; height:7px; border-radius:50%; background:var(--acc); }
  .wrap { flex:1; display:flex; flex-direction:column; min-width:0; }
  .tape { overflow:hidden; white-space:nowrap; padding:11px 0; }
  .tape .track2 { display:inline-block; animation:scroll 60s linear infinite; }
  .tape:hover .track2 { animation-play-state:paused; }
  .tape .ti { font-family:var(--fm); font-size:12px; margin:0 30px; letter-spacing:.02em; } .tape .ti b { color:var(--ink); } .tape .ti .pos { color:var(--acc); } .tape .ti .neg { color:var(--bear); }
  @keyframes scroll { from{transform:translateX(0);} to{transform:translateX(-50%);} }
  .tape8k { background:var(--tape); padding:var(--s2) 0; } .tape8k .ti .warn { color:var(--warn); } .tape8k .track2 { animation-duration:75s; }
  .statedot { width:8px; height:8px; border-radius:50%; }
  .statedot.calm { background:var(--acc); color:var(--acc); } .statedot.warn { background:var(--warn); color:var(--warn); } .statedot.alert { background:var(--bear); color:var(--bear); }
  .main { padding:30px 52px 54px; max-width:1340px; }
  .phead { margin-bottom:22px; } .phead h2 { font-family:var(--fd); font-weight:300; font-size:32px; margin:0 0 6px; letter-spacing:.16em; text-transform:uppercase; color:var(--ink); } .phead .sub { font-family:var(--fb); font-weight:400; font-size:12px; letter-spacing:.04em; color:var(--steel); }
  [data-page] { display:none; } [data-page].active { display:block; animation:fadein .42s ease; } @keyframes fadein { from { opacity:0; transform:translateY(5px); } to { opacity:1; transform:none; } }
  /* Cascade signature Vue d'ensemble : page load orchestre, blocs en revel
     staggered 60ms. Remplace le fadein page generique sur vigie uniquement.
     Direction "instrument vivant qui se decouvre" (task #37 axe 4). */
  [data-page="vigie"].active { animation:none; }
  [data-page="vigie"].active > * { animation:presage-cascade .32s var(--ease) both; }
  [data-page="vigie"].active > *:nth-child(1) { animation-delay:0ms; }
  [data-page="vigie"].active > *:nth-child(2) { animation-delay:60ms; }
  [data-page="vigie"].active > *:nth-child(3) { animation-delay:120ms; }
  [data-page="vigie"].active > *:nth-child(4) { animation-delay:180ms; }
  [data-page="vigie"].active > *:nth-child(5) { animation-delay:240ms; }
  [data-page="vigie"].active > *:nth-child(6) { animation-delay:300ms; }
  [data-page="vigie"].active > *:nth-child(7) { animation-delay:360ms; }
  [data-page="vigie"].active > *:nth-child(8) { animation-delay:420ms; }
  [data-page="vigie"].active > *:nth-child(n+9) { animation-delay:480ms; }
  @keyframes presage-cascade { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:none; } }
  .noanim [data-page="vigie"].active > * { animation:none; opacity:1; transform:none; }
  .hero { background:var(--panel); border:1px solid var(--line3); border-radius:var(--r3); padding:28px 34px; margin-bottom:26px; display:flex; align-items:center; gap:28px; flex-wrap:wrap; }
  .hero .big { font-family:var(--fm); font-weight:500; font-size:42px; line-height:.95; letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .hero .big.pos { color:var(--acc); } .hero .big.neg { color:var(--bear); }
  .hero .hl { font-family:var(--fb); font-size:11px; letter-spacing:.2em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s2); }
  .hero .hsub { font-size:13px; color:var(--steel); margin-top:var(--s15); }
  .distbar { flex:1; min-width:240px; } .distline { display:flex; height:8px; border-radius:var(--r1); overflow:hidden; }
  .distline .g { background:var(--acc); } .distline .r { background:var(--bear); }
  .kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:var(--s4); margin-bottom:26px; }
  .kpi { background:var(--panel); border:1px solid var(--line); border-radius:var(--r2); padding:13px 16px; }
  .kl { display:block; font-family:var(--fb); font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s2); }
  .kv { font-family:var(--fm); font-weight:500; font-size:28px; letter-spacing:-.01em; line-height:1; font-variant-numeric:tabular-nums; }
  .kv, .gvm, .big { color:var(--c, var(--ink)); }
  .kv.bear { --c:var(--bear); } .kv.acc { --c:var(--acc); } .kv.warn { --c:var(--warn); } .kv.id { --c:var(--id); }
  .kv.acc { color:var(--acc); } .kv.negc { color:var(--bear); } .kv.warn { color:var(--warn); } .kv.hot { color:var(--warn); } .kv.danger { color:var(--bear); } .kv.calm { color:var(--acc); }
  .kd { display:block; font-size:11px; color:var(--steel); margin-top:var(--s15); }
  .cols { display:grid; grid-template-columns:1fr 1fr; gap:30px; align-items:start; }
  .colhead { display:flex; align-items:baseline; gap:9px; margin-bottom:var(--s3); padding-left:2px; } .colhead .t { font-family:var(--fd); font-weight:500; font-size:13px; } .colhead .a { font-family:var(--fm); font-size:12px; color:var(--steel); }
  .colhead.tight { margin-top:var(--s15); } /* 6px : aerer un peu apres un bloc voisin */
  .colhead.spaced { margin-top:var(--s4); } /* 20px : separateur de section, sous-titre marque */
  .sec-cols { display:grid; grid-template-columns:1fr 92px 96px 58px 72px 78px; gap:var(--s3); padding:2px 16px 9px; font-family:var(--fb); font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); border-bottom:1px solid var(--line); margin-bottom:var(--s3); }
  .sec-cols .num { text-align:right; }
  .sec-grp { margin-bottom:22px; }
  .sec-h { display:flex; align-items:baseline; justify-content:space-between; gap:var(--s3); margin:0 4px 9px; }
  .sec-name { font-family:var(--fd); font-weight:500; font-size:16px; color:var(--ink); display:flex; align-items:center; gap:9px; }
  .sec-name::before { content:""; width:6px; height:6px; border-radius:2px; background:var(--id); }
  .sec-meta { font-family:var(--fm); font-size:12px; color:var(--steel); white-space:nowrap; }
  .sec-pl.pos { color:var(--acc); } .sec-pl.neg { color:var(--bear); }
  .sec-rows { display:flex; flex-direction:column; gap:1px; }
  .sec-row { display:grid; grid-template-columns:1fr 92px 96px 58px 72px 78px; gap:var(--s3); align-items:center; padding:var(--s2) 16px; border-radius:var(--r2); font-family:var(--fm); font-size:13px; cursor:pointer; transition:background .12s; }
  .sec-row:hover { background:color-mix(in srgb,var(--ink) 4%,transparent); }
  .sec-row .num { text-align:right; color:var(--ink); font-variant-numeric:tabular-nums; }
  .sec-row .num.pos, .sec-pl.pos { color:var(--acc); } .sec-row .num.neg { color:var(--bear); }
  .sec-tk { font-weight:600; color:var(--ink); }
  .sec-nm { color:var(--steel); font-family:var(--fb); font-size:11px; margin-left:9px; font-weight:400; }
  /*CHER*/
  .card, .kpi { transition:transform .16s ease, box-shadow .16s ease; }
  .card:hover, .kpi:hover { border-color:var(--line2); }
  .tape .ti::after { content:"·"; margin-left:30px; color:var(--steel); opacity:.4; }
  /*METAL2*/
  .card, .kpi, .hero, .pfcard { border-top:1px solid color-mix(in srgb,var(--ink) 16%,var(--line)); }
  .th-grid { display:grid; grid-template-columns:1fr 1fr; gap:13px; margin-bottom:var(--s15); }
  .th-anchor { grid-column:1/-1; margin-top:var(--s2); padding:var(--s2) 11px; border-radius:var(--r2); font-family:var(--fb); font-size:12px; line-height:1.5; color:var(--ink); border-left:2px solid var(--id); }
  .th-anchor.acc { border-left-color:var(--acc); background:color-mix(in srgb,var(--acc) 7%,transparent); }
  .th-anchor.warn { border-left-color:var(--warn); background:color-mix(in srgb,var(--warn) 9%,transparent); }
  /*THEME-ICO*/
  .modetgl .ico-sun { display:none; } body.midnight .modetgl .ico-moon { display:none; } body.midnight .modetgl .ico-sun { display:inline-block; }
  /*DVAL-STATE*/
  .dval.calm { color:var(--acc); } .dval.warn { color:var(--warn); } .dval.danger { color:var(--bear); } .dval.mute { color:var(--steel); }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:var(--r2); padding:var(--s2) 24px; } .card.pad { padding:var(--s35) 18px; }
  .line { display:flex; justify-content:space-between; padding:9px 0; border-bottom:1px solid var(--line); font-size:13px; } .line:last-child { border-bottom:none; }
  .mono { font-family:var(--fm); font-weight:600; color:var(--ink); } .mono.pos { color:var(--acc); } .mono.neg { color:var(--bear); }
  .gauge { background:var(--panel); border:1px solid var(--line); border-radius:var(--r2); padding:16px 20px; margin-bottom:15px; }
  .ghead { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:11px; } .ghead .gl { font-family:var(--fb); font-weight:600; font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); } .ghead .gv { font-family:var(--fm); font-weight:500; font-size:22px; letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .gtrack { position:relative; height:6px; border-radius:3px; background:linear-gradient(90deg, var(--acc), var(--warn) 52%, var(--bear)); }
  .glab { margin-top:9px; font-size:11px; color:var(--steel); display:flex; justify-content:space-between; font-family:var(--fm); letter-spacing:.08em; }
  .row { padding:9px 0; border-bottom:1px solid var(--line); opacity:0; animation:fade .45s ease forwards; } .row:last-child { border-bottom:none; }
  .row[data-tk] { cursor:pointer; } .row[data-tk]:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); }
  .rt { display:flex; justify-content:space-between; align-items:center; margin-bottom:9px; gap:8px; } .tk { font-family:var(--fm); font-weight:600; font-size:13px; display:inline-flex; align-items:center; gap:7px; }
  /* Sprint 3 logos tickers (Clearbit + fallback initiale, cf shared/ticker_logos.py) */
  .tklogo { width:18px; height:18px; border-radius:50%; object-fit:contain; background:#fff; padding:2px; vertical-align:middle; flex-shrink:0; box-sizing:border-box; border:1px solid var(--line); margin-right:6px; }
  .tklogo.tkfb { display:inline-flex; align-items:center; justify-content:center; background:var(--steel); color:var(--bg); font-family:var(--fm); font-size:9px; font-weight:700; padding:0; border:none; }
  .tape .tklogo { width:16px; height:16px; padding:1px; margin-right:5px; }
  .lp-h .tklogo { width:32px; height:32px; padding:3px; margin-right:10px; align-self:center; }
  .lp-h .tklogo.tkfb { font-size:14px; }
  .lp-h { align-items:center !important; }
  /* === Page Star : panneau hero "verdict 3 secondes" par page === */
  /* User feedback 01/06 : un panneau clair, bien espace, hierarchie typo
     restreinte (label uppercase steel + value 24-28px ink + caption steel),
     3 strates separees par hairlines, padding genereux (32-40px). */
  .page-star { background:var(--panel); border:1px solid var(--line); border-radius:var(--r3); padding:32px 36px; margin-bottom:var(--s4); }
  .page-star .ps-strate { padding:18px 0; }
  .page-star .ps-strate:first-child { padding-top:0; }
  .page-star .ps-strate:last-child { padding-bottom:0; }
  .page-star .ps-strate + .ps-strate { border-top:1px solid var(--line); }
  .page-star .ps-lbl { font-family:var(--fm); font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin-bottom:8px; }
  .page-star .ps-val { font-family:var(--fb); font-size:24px; font-weight:500; color:var(--ink); line-height:1.1; }
  .page-star .ps-val.bear { color:var(--bear); }
  .page-star .ps-val.acc { color:var(--acc); }
  .page-star .ps-val.warn { color:var(--warn); }
  .page-star .ps-cap { font-family:var(--fb); font-size:13px; color:var(--steel); margin-top:8px; line-height:1.4; }
  .page-star .ps-macro-row { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }
  .page-star .ps-macro-meta { font-family:var(--fm); font-size:13px; color:var(--steel); }
  .page-star .ps-frise { height:6px; border-radius:3px; background:linear-gradient(90deg,var(--acc),var(--warn) 52%,var(--bear)); position:relative; margin-top:18px; }
  .page-star .ps-frise-mark { position:absolute; top:50%; width:14px; height:14px; background:var(--ink); border-radius:50%; transform:translate(-50%,-50%); border:2px solid var(--panel); }
  .page-star .ps-frise-labs { display:flex; justify-content:space-between; font-family:var(--fm); font-size:11px; color:var(--steel); margin-top:10px; letter-spacing:.06em; }
  .page-star .ps-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:38px; }
  .page-star .ps-cell { display:flex; flex-direction:column; }
  .page-star .ps-foot { font-family:var(--fm); font-size:12px; color:var(--steel); }
  .page-star .ps-foot b { color:var(--ink); font-weight:500; }
  /* Hero row 2-col pour Vue d'ensemble Star (Valeur + Grade aesthetic) */
  .page-star .ps-hero-row { display:grid; grid-template-columns:1fr 1fr; gap:48px; align-items:start; }
  .page-star .ps-hero-left, .page-star .ps-hero-right { min-width:0; }
  .page-star .ps-grade-row { display:flex; align-items:center; gap:18px; margin-top:8px; }
  .page-star .ps-grade-letter { font-family:var(--fb); font-size:42px; font-weight:500; line-height:1; flex-shrink:0; }
  .page-star .ps-grade-letter.acc { color:var(--acc); }
  .page-star .ps-grade-letter.warn { color:var(--warn); }
  .page-star .ps-grade-letter.bear { color:var(--bear); }
  .page-star .ps-grade-score { flex:1; min-width:140px; }
  .page-star .ps-grade-num { font-family:var(--fb); font-size:22px; font-weight:500; color:var(--ink); margin-bottom:8px; }
  .page-star .ps-grade-max { font-family:var(--fm); font-size:13px; color:var(--steel); font-weight:400; }
  .page-star .ps-grade-bar { height:6px; background:color-mix(in srgb,var(--line) 90%,transparent); border-radius:3px; overflow:hidden; }
  .page-star .ps-grade-fill { height:100%; transition:width .3s ease; }
  .page-star .ps-grade-fill.acc { background:var(--acc); }
  .page-star .ps-grade-fill.warn { background:var(--warn); }
  .page-star .ps-grade-fill.bear { background:var(--bear); }
  /* Ligne sous Valeur portefeuille (sub-info en lien typographique) */
  .page-star .ps-sub-lien { font-family:var(--fb); font-size:13px; color:var(--steel); margin-top:8px; }
  .page-star .ps-sub-lien b { color:var(--ink); font-weight:500; }
  .page-star .ps-sub-lien b.acc { color:var(--acc); }
  /* Sprint 4 CTA flottants bas (TR/RH-inspired) : 3 pills sticky bottom */
  .cta-bar { position:fixed; bottom:22px; left:50%; transform:translateX(-50%); background:color-mix(in srgb,var(--panel) 95%,transparent); border:1px solid var(--line2); border-radius:32px; padding:6px; display:flex; gap:2px; z-index:50; box-shadow:0 12px 32px -10px rgba(0,0,0,.18); backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px); }
  .cta-bar button { font-family:var(--fb); font-size:13px; font-weight:500; color:var(--ink); background:transparent; border:none; padding:10px 18px; border-radius:24px; cursor:pointer; display:flex; align-items:center; gap:8px; transition:background .15s,color .15s; }
  .cta-bar button:hover { background:color-mix(in srgb,var(--ink) 6%,transparent); }
  .cta-bar button.act { background:var(--ink); color:var(--bg); }
  .cta-bar kbd { font-family:var(--fm); font-size:10px; padding:1px 5px; background:color-mix(in srgb,var(--ink) 10%,transparent); border-radius:4px; opacity:.7; border:none; }
  .cta-bar button.act kbd { background:color-mix(in srgb,var(--bg) 25%,transparent); color:var(--bg); }
  /* Search modal */
  .cta-modal { position:fixed; inset:0; background:rgba(0,0,0,.4); z-index:100; display:none; align-items:flex-start; justify-content:center; padding-top:14vh; }
  .cta-modal.open { display:flex; }
  .cta-modal-inner { background:var(--panel); border:1px solid var(--line2); border-radius:12px; width:min(560px,92vw); max-height:64vh; overflow:hidden; display:flex; flex-direction:column; box-shadow:0 24px 64px -16px rgba(0,0,0,.4); }
  .cta-search-input { width:100%; padding:18px 24px; font-family:var(--fb); font-size:16px; background:transparent; border:none; border-bottom:1px solid var(--line); color:var(--ink); outline:none; box-sizing:border-box; }
  .cta-search-results { max-height:50vh; overflow-y:auto; padding:4px; }
  .cta-result { padding:10px 16px; display:flex; align-items:center; gap:10px; cursor:pointer; border-radius:8px; }
  .cta-result:hover, .cta-result.sel { background:color-mix(in srgb,var(--ink) 6%,transparent); }
  .cta-result .ctk { font-family:var(--fm); font-weight:600; color:var(--ink); }
  .cta-result .cnm { color:var(--steel); font-size:13px; }
  .tag { font-family:var(--fm); font-weight:600; font-size:11px; padding:3px 9px; border-radius:var(--r1); }
  .tag.up { color:var(--acc); background:color-mix(in srgb, var(--acc) 12%, transparent); } .tag.acc2 { color:var(--acc2); background:color-mix(in srgb, var(--acc2) 12%, transparent); }
  .tag.down,.tag.danger { color:var(--bear); background:color-mix(in srgb, var(--bear) 13%, transparent); } .tag.warn { color:var(--warn); background:color-mix(in srgb, var(--warn) 14%, transparent); } .tag.calm { color:var(--steel); background:color-mix(in srgb, var(--steel) 12%, transparent); } .tag.mute { color:var(--steel); background:color-mix(in srgb, var(--steel) 12%, transparent); }
  /* Signal-subtil PRESAGE : axe gradient red->neutral->green + dot noir-bezel-gold */
  .axis { position:relative; height:5px; border-radius:2.5px; margin:var(--s35) 0 6px;
    background:linear-gradient(90deg,
      var(--bear) 0%,
      color-mix(in srgb,var(--bear) 45%,transparent) 25%,
      color-mix(in srgb,var(--steel) 35%,transparent) 50%,
      color-mix(in srgb,var(--acc) 45%,transparent) 75%,
      var(--acc) 100%); }
  .axis.sizebar { background:linear-gradient(90deg,
    color-mix(in srgb,var(--acc) 75%,transparent) 0%,
    color-mix(in srgb,var(--acc) 30%,transparent) 35%,
    color-mix(in srgb,var(--steel) 35%,transparent) 60%,
    color-mix(in srgb,var(--warn) 55%,transparent) 77%,
    var(--bear) 100%); }
  .axis::before, .axis::after { content:""; position:absolute; top:-3px; width:1px; height:10px; background:var(--line2); }
  .axis::before { left:0; } .axis::after { right:0; }
  .axis-mark { position:absolute; top:50%; width:32px; height:15px;
    background-color:var(--ink);
    -webkit-mask:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 24'><path d='M1 12 Q26 10 30 1 Q34 10 59 12 Q34 14 30 23 Q26 14 1 12 Z' fill='%23ffffff'/></svg>") no-repeat center / contain;
    mask:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 24'><path d='M1 12 Q26 10 30 1 Q34 10 59 12 Q34 14 30 23 Q26 14 1 12 Z' fill='%23ffffff'/></svg>") no-repeat center / contain;
    transform:translate(-50%,-50%); z-index:2; transition:left .6s cubic-bezier(.2,.8,.2,1); }
  .axis-mark.pos { background-color:var(--acc); }
  .axis-mark.neg, .axis-mark.danger { background-color:var(--bear); }
  .axis-mark.warn { background-color:var(--warn); }
  .axis-mark.mute { background-color:var(--steel); opacity:.6; }
  .axis-tick { position:absolute; top:-3px; width:1px; height:7px; background:var(--line2); }
  .axis-tick.strong { top:-4px; height:9px; background:var(--ink); opacity:.55; }
  .axis-tick.dash { border-left:1px dashed var(--steel); background:transparent; opacity:.6; }
  .noanim .axis-mark { transition:none !important; }

  /* Track record refonte W14 (31/05) : axes = primitive, filets fins, encre,
     courbe fiabilite SVG cadre vide + diagonale qui se trace au load. */
  .tr-card .tr-metric { padding:var(--s35) 0; border-bottom:1px solid var(--line); }
  .tr-card .tr-metric:last-of-type { border-bottom:none; }
  .tr-card .tr-mlabel { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s2); flex-wrap:wrap; }
  .tr-card .tr-mname { font-weight:600; font-size:var(--t-base); color:var(--ink); }
  .tr-card .tr-mval { font-size:var(--t-h3); color:var(--ink); letter-spacing:-.01em; }
  .tr-card .tr-mvsep { color:var(--steel); padding:0 2px; }
  .tr-card .tr-munit { font-size:var(--t-caption); color:var(--steel); }
  .tr-card .tr-axis-brier { background:linear-gradient(to right, var(--acc) 0%, var(--acc) 40%, var(--line2) 40%, var(--bear) 100%); }
  .tr-card .tr-axref { position:absolute; top:-3px; bottom:-3px; width:1px; background:var(--ink); opacity:.45; }
  .tr-card .tr-axref::after { content:""; position:absolute; top:-4px; left:-3px; width:7px; height:1px; background:var(--ink); opacity:.55; }
  .tr-card .tr-mfoot { display:flex; justify-content:space-between; margin-top:var(--s2); font-size:var(--t-caption); }
  .tr-card .tr-mfoot .mono { color:var(--ink2); }
  .tr-card .tr-verdict { color:var(--steel); }
  .tr-card .tr-rsvg { display:block; width:100%; height:96px; margin:var(--s2) 0; }
  .tr-card .tr-diag { stroke:var(--ink); stroke-width:.8; fill:none; stroke-dasharray:160; stroke-dashoffset:160; animation:trDiagDraw 1.4s cubic-bezier(.22,.61,.36,1) .15s forwards; }
  .tr-card .tr-frame { stroke:var(--line2); stroke-width:.5; fill:none; }
  .tr-card .tr-pipe { display:flex; flex-wrap:wrap; gap:var(--s2) var(--s3); padding-top:var(--s35); color:var(--ink2); font-size:var(--t-body); }
  .tr-card .tr-pipe b { color:var(--ink); font-weight:600; }
  .tr-card .tr-sep { color:var(--line3); }
  @keyframes trDiagDraw { to { stroke-dashoffset:0; } }
  .noanim .tr-diag { animation:none; stroke-dashoffset:0; }
  .rs { display:flex; justify-content:space-between; margin-top:var(--s15); font-size:11px; color:var(--steel); }
  .dwrap { display:flex; align-items:center; gap:var(--s5); flex-wrap:wrap; }
  .legend { display:flex; flex-direction:column; gap:var(--s2); flex:1; min-width:200px; }
  .empty { padding:30px 0; text-align:center; color:var(--steel); } .empty b { display:block; font-family:var(--fd); font-size:16px; color:var(--ink); margin-bottom:var(--s2); }
  .dt { width:100%; border-collapse:collapse; font-size:13px; }
  .dt th { text-align:left; font-family:var(--fb); font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--steel); padding:var(--s2) 10px; border-bottom:1px solid var(--line2); cursor:pointer; user-select:none; }
  .dt th.num { text-align:right; } .dt th:hover { color:var(--ink); }
  .dt td { padding:var(--s2) 10px; border-bottom:1px solid var(--line); } .dt td.num { text-align:right; font-family:var(--fm); }
  .dt td.tk { font-family:var(--fm); font-weight:600; } .dt tr:hover td { background:color-mix(in srgb,var(--ink) 2.5%,transparent); }
  .dt td.pos { color:var(--acc); } .dt td.neg { color:var(--bear); }
  .bdg { display:inline-block; margin-left:var(--s2); font-family:var(--fb); font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--id); border:1px solid color-mix(in srgb, var(--acc2) 40%, transparent); border-radius:3px; padding:1px 5px; vertical-align:middle; }
  .dt tr.prev td { opacity:.72; } .dt tr.prev td.tk { color:var(--id); }
  .nm { display:block; font-size:11px; font-weight:400; color:var(--steel); margin-top:2px; }
  .ph3 { font-family:var(--fb); font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--steel); margin:0 0 12px; }
  .dtier { font-family:var(--fb); font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--steel); margin:16px 0 6px; padding-bottom:var(--s15); border-bottom:1px solid var(--line); }
  .dlist > .dtier:first-child { margin-top:0; }
  [data-tip]{position:relative;cursor:help}
  [data-tip]:hover::after{content:attr(data-tip);position:absolute;left:0;top:calc(100% + 4px);background:var(--panel);color:var(--ink);border:1px solid var(--line2);padding:var(--s2) 11px;border-radius:var(--r1);font-family:var(--fb);font-size:11px;font-weight:400;letter-spacing:0;text-transform:none;white-space:normal;max-width:300px;width:max-content;z-index:1000;box-shadow:0 6px 18px rgba(0,0,0,.5);pointer-events:none;line-height:1.4}
  body.midnight [data-tip]:hover::after{box-shadow:0 6px 18px rgba(0,0,0,.55)}
  .drow { display:grid; grid-template-columns:14px 1fr auto auto auto; align-items:center; gap:var(--s3); padding:var(--s2) 0; font-size:13px; }
  .ddot { width:8px; height:8px; border-radius:50%; }
  .ddot.calm { background:var(--acc); } .ddot.warn { background:var(--warn); }
  .ddot.hot { background:var(--warn); } .ddot.danger { background:var(--bear); }
  .dname { color:var(--ink); } .dval { font-family:var(--fm); text-align:right; color:var(--ink); } .dp { font-family:var(--fm); font-size:11px; color:var(--steel); }
  .stale { font-family:var(--fb); font-size:11px; color:var(--steel); opacity:.7; text-transform:uppercase; letter-spacing:.08em; }
  @keyframes fade { to { opacity:1; } }
  .noanim [data-page].active, .noanim .row { animation:none !important; }
  .noanim .row { opacity:1 !important; }
  .plan { background:var(--panel); border:1px solid var(--line3); border-radius:var(--r2); padding:15px 20px; margin-bottom:var(--s4); }
  .plan-h { font-family:var(--fb); font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:13px; }
  .plan-row { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
  .pi { display:flex; flex-direction:column; gap:var(--s1); padding-left:13px; border-left:2px solid var(--line2); border-radius:0; }
  .pi.danger { border-left-color:var(--bear); } .pi.warn { border-left-color:var(--warn); } .pi.calm { border-left-color:var(--acc); } .pi.size { border-left-color:var(--steel); }
  .pn { font-family:var(--fm); font-weight:500; font-size:22px; line-height:1; letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .pi.danger .pn { color:var(--bear); } .pi.warn .pn { color:var(--warn); } .pi.calm .pn { color:var(--acc); } .pi.size .pn { color:var(--metal); }
  .pl { font-size:12px; color:var(--ink); } .pt { font-family:var(--fm); font-size:11px; color:var(--steel); }
  .dt tbody tr:not(.prev) { cursor:pointer; }
  .loupe { position:fixed; inset:0; z-index:60; display:none; align-items:center; justify-content:center; background:rgba(6,10,18,.72); backdrop-filter:blur(6px); padding:34px; }
  .loupe.open { display:flex; }
  .loupe-card { position:relative; width:min(560px,100%); max-height:86vh; overflow:auto; background:var(--panel); border:1px solid var(--line2); border-radius:var(--r3); padding:28px 30px; box-shadow:0 30px 90px -20px #000; }
  .loupe-x { position:absolute; top:var(--s35); right:var(--s4); background:none; border:none; color:var(--steel); font-size:22px; line-height:1; cursor:pointer; }
  .loupe-x:hover { color:var(--ink); }
  .lp-h { display:flex; align-items:baseline; gap:11px; }
  .lp-tk { font-family:var(--fm); font-weight:500; font-size:22px; letter-spacing:.02em; color:var(--ink); }
  .lp-nm { font-size:13px; color:var(--steel); }
  .lp-meta { font-family:var(--fm); font-size:11px; color:var(--steel); margin:var(--s15) 0 18px; }
  .lp-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:var(--s3); }
  .lp-mom { display:grid; grid-template-columns:repeat(3,1fr); gap:var(--s3); }
  .lp-stat { background:var(--panel); border:1px solid var(--line); border-radius:var(--r2); padding:11px 13px; }
  .lp-sl { font-family:var(--fb); font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--steel); }
  .lp-sv { font-family:var(--fm); font-weight:500; font-size:18px; letter-spacing:-.01em; margin-top:var(--s15); font-variant-numeric:tabular-nums; }
  .lp-sec { font-family:var(--fb); font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin:20px 0 10px; border-top:1px solid var(--line); padding-top:var(--s35); }
  .lp-score { display:flex; align-items:center; gap:var(--s3); margin:var(--s2) 0; font-size:12px; }
  .lp-score .ln { width:92px; color:var(--steel); }
  .lp-score .bar { flex:1; height:6px; background:var(--barbg); border-radius:3px; overflow:hidden; }
  .lp-score .bf { display:block; height:100%; background:linear-gradient(90deg,var(--acc),var(--acc)); }
  .lp-score .vv { font-family:var(--fm); width:32px; text-align:right; }
  .lp-ex { font-size:13px; color:var(--ink); line-height:1.6; opacity:.82; }
  .lp-empty { font-size:12px; color:var(--steel); padding:var(--s15) 0; }
  .lp-hint { font-family:var(--fm); font-size:11px; color:var(--steel); margin-top:var(--s35); padding-top:var(--s3); border-top:1px solid color-mix(in srgb,var(--ink) 5%,transparent); line-height:1.5; }
  .lp-hint code { font-family:var(--fm); font-weight:600; color:var(--ink); background:color-mix(in srgb,var(--ink) 5%,transparent); padding:1px 5px; border-radius:3px; font-size:11px; }
  .tkc { cursor:pointer; transition:color .12s; } .tkc:hover { color:var(--id); }
  .lp-badge { display:inline-block; font-family:var(--fb); font-size:11px; letter-spacing:.1em; text-transform:uppercase; padding:2px 8px; border-radius:var(--r1); border:1px solid currentColor; }
  .lp-badge.held { color:var(--acc); } .lp-badge.watch { color:var(--warn); } .lp-badge.univ { color:var(--acc2); } .lp-badge.out { color:var(--steel); }
  .sbwrap { display:flex; flex-direction:column; gap:var(--s5); }
  .sb-top { display:grid; grid-template-columns:repeat(3,1fr); gap:32px; width:100%; padding:var(--s2) 4px 16px; border-bottom:1px solid var(--line); }
  .sb-kpi { display:flex; flex-direction:column; gap:var(--s15); }
  .sb-kl { font-family:var(--fb); font-weight:600; font-size:11px; letter-spacing:.18em; color:var(--steel); }
  .sb-kv { font-family:var(--fm); font-weight:500; font-size:22px; color:var(--ink); letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .sb-bars { display:flex; flex-direction:column; gap:2px; width:100%; }
  .sb-row { display:grid; grid-template-columns:minmax(160px,1.4fr) minmax(120px,3fr) 50px 70px; align-items:center; gap:16px; padding:var(--s25) 6px; border-radius:var(--r1); cursor:pointer; transition:background .15s,opacity .2s; }
  .sb-row:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); }
  .sb-row.on { background:color-mix(in srgb,var(--ink) 5%,transparent); }
  .sb-bars:has(.sb-row.on) .sb-row.dim { opacity:.28; }
  .sb-row-name { display:flex; align-items:center; gap:var(--s3); min-width:0; }
  .sb-row-dot { width:8px; height:8px; border-radius:50%; flex:0 0 auto; }
  .sb-row-label { font-family:var(--fb); font-weight:500; font-size:13px; color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .sb-row-bar { height:4px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:2px; overflow:hidden; }
  .sb-row-fill { height:100%; border-radius:2px; transition:width .4s cubic-bezier(.2,.8,.2,1); }
  .sb-row-pct { font-family:var(--fm); font-weight:500; font-size:13px; color:var(--ink); text-align:right; font-variant-numeric:tabular-nums; }
  .sb-row-val { font-family:var(--fm); font-weight:400; font-size:12px; color:var(--steel); text-align:right; font-variant-numeric:tabular-nums; }
  #sb-panel { width:100%; font-size:13px; padding:var(--s3) 0 0; }
  #sb-panel:empty { display:none; }
  .sbrow { display:flex; justify-content:space-between; align-items:center; padding:var(--s2) 0; border-bottom:.5px solid var(--line); cursor:pointer; } .sbrow:last-child { border-bottom:none; } .sbrow:hover { background:color-mix(in srgb,var(--ink) 2.5%,transparent); }
  .qs { position:fixed; inset:0; z-index:70; display:none; align-items:flex-start; justify-content:center; background:rgba(6,10,18,.72); backdrop-filter:blur(6px); padding:12vh 20px 20px; }
  .qs.open { display:flex; }
  .qs-card { width:min(560px,100%); background:var(--panel); border:1px solid var(--line2); border-radius:var(--r3); box-shadow:0 30px 90px -20px #000; overflow:hidden; }
  #qs-input { width:100%; box-sizing:border-box; background:transparent; border:none; outline:none; color:var(--ink); font-family:var(--fb); font-size:18px; padding:var(--s4) 20px; border-bottom:1px solid var(--line); }
  #qs-input::placeholder { color:var(--steel); }
  #qs-res { max-height:50vh; overflow:auto; }
  .qs-row { display:flex; align-items:center; gap:var(--s3); padding:11px 20px; cursor:pointer; border-bottom:.5px solid var(--line); }
  .qs-row:last-child { border-bottom:none; } .qs-row.on, .qs-row:hover { background:color-mix(in srgb, var(--acc) 10%, transparent); }
  .qs-tk { font-family:var(--fm); font-weight:600; font-size:13px; width:78px; }
  .qs-nm { flex:1; font-size:13px; color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .qs-st { font-family:var(--fb); font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--steel); }
  .qs-st.held { color:var(--acc); } .qs-st.watch { color:var(--warn); } .qs-st.core, .qs-st.extended { color:var(--acc2); }
  .qs-empty { padding:22px 20px; color:var(--steel); font-size:13px; text-align:center; }
  .hero.posture { display:block; }
  .hero.posture .plan-row { margin-top:var(--s35); gap:var(--s5); }
  .hero.posture .pn { font-size:28px; }
  .hrow { display:grid; grid-template-columns:1.3fr 1fr; gap:var(--s4); margin-bottom:20px; align-items:stretch; }
  /* hero-single : refonte vigie 31/05 -- pfcard seule sans disc_hero a droite */
  .hero-single { display:block; margin-bottom:var(--s4); }
  .hero-single .pfcard { max-width:none; }
  .hrow .hero.posture { margin-bottom:0; height:100%; }
  .pfcard { background:var(--panel); border:1px solid var(--line3); border-radius:var(--r3); padding:20px 24px; display:flex; flex-direction:column; }
  .pfcard .v { font-family:var(--fm); font-weight:500; font-size:32px; letter-spacing:-.01em; line-height:1; margin:var(--s2) 0 5px; color:var(--ink); font-variant-numeric:tabular-nums; }
  .pfcard .d { font-family:var(--fm); font-size:13px; font-weight:600; } .pfcard .d.pos { color:var(--acc); } .pfcard .d.neg { color:var(--bear); }
  .pfcard .distline { margin:16px 0 0; height:20px; gap:3px; border-radius:0; overflow:visible; }
  .pfcard .distline .g { background:var(--acc); border-radius:var(--r1); }
  .pfcard .distline .r { background:var(--bear); border-radius:var(--r1); }
  .pfcard .distcap { display:flex; justify-content:space-between; font-family:var(--fm); font-size:12px; margin-top:9px; }
  .pfcard .distcap .cg { color:var(--acc); font-weight:600; }
  .pfcard .distcap .cr { color:var(--bear); font-weight:600; }
  .pfcard .sub2 { font-size:12px; color:var(--steel); margin-top:auto; padding-top:13px; } .pfcard .sub2 b { color:var(--ink); font-weight:600; }
  @media (max-width:980px) { .hrow { grid-template-columns:1fr; } }
  /* Star treatment - hero row au top de Vue d'ensemble */
  .hrow.star { gap:22px; margin-bottom:28px; }
  .hrow.star .pfcard { padding:30px 36px; }
  .hrow.star .pfcard .hl { font-size:11px; letter-spacing:.22em; }
  .hrow.star .pfcard .v { font-size:46px; margin:var(--s35) 0 9px; line-height:.95; }
  .hrow.star .pfcard .d { font-size:18px; }
  .hrow.star .pfcard .distline { margin-top:22px; height:24px; }
  .hrow.star .pfcard .distcap { font-size:13px; margin-top:var(--s3); }
  .hrow.star .pfcard .sub2 { font-size:13px; padding-top:var(--s4); }
  .hrow.star .hero.posture { padding:30px 36px; }
  .hrow.star .hero.posture .hl { font-size:11px; letter-spacing:.22em; }
  .hrow.star .hero.posture .pn { font-size:42px; line-height:.95; }
  .hrow.star .hero.posture .plan-row { margin-top:var(--s4); gap:30px; }
  /* Sprint 5 - Note du portefeuille */
  .gradecard .ghead { display:flex; align-items:center; gap:22px; margin:var(--s35) 0 18px; padding-bottom:var(--s4); border-bottom:1px solid var(--line); }
  .gradecard .gletter { font-family:var(--fm); font-weight:500; font-size:56px; line-height:.9; letter-spacing:-.02em; padding:0 18px; border-radius:var(--r2); }
  .gradecard .gletter.good { color:var(--acc); }
  .gradecard .gletter.warn { color:var(--warn); }
  .gradecard .gletter.bad { color:var(--bear); }
  .gradecard .gscore { flex:1; display:flex; flex-direction:column; gap:var(--s15); }
  .gradecard .gscoreval { font-size:28px; font-weight:500; letter-spacing:-.01em; line-height:1; color:var(--ink); }
  .gradecard .gscoremax { color:var(--steel); font-weight:400; font-size:16px; margin-left:2px; }
  .gradecard .gscorebar { height:6px; background:color-mix(in srgb,var(--ink) 6%,transparent); border-radius:var(--r1); overflow:hidden; }
  .gradecard .gscorefill { height:100%; border-radius:var(--r1); transition:width .4s ease; }
  .gradecard .gscorefill.good { background:var(--acc); }
  .gradecard .gscorefill.warn { background:var(--warn); }
  .gradecard .gscorefill.bad { background:var(--bear); }
  .gradecard .gbody { display:grid; gap:var(--s3); }
  .gradecard .grow { display:grid; grid-template-columns:200px 1fr 180px; align-items:center; gap:var(--s35); }
  .gradecard .glab { font-family:var(--fm); font-size:13px; color:var(--steel); font-weight:500; }
  .gradecard .gaxis { position:relative; height:6px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r1); }
  .gradecard .gfill { position:absolute; left:0; top:0; height:100%; border-radius:var(--r1); }
  .gradecard .gfill.good { background:var(--acc); }
  .gradecard .gfill.bad { background:var(--bear); opacity:.55; }
  /* Needle iconic canonique (diamant SVG noir/blanc — meme forme que .axis-mark) */
  .gradecard .gtgt { position:absolute; top:50%; width:28px; height:13px;
    background-color:var(--ink);
    -webkit-mask:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 24'><path d='M1 12 Q26 10 30 1 Q34 10 59 12 Q34 14 30 23 Q26 14 1 12 Z' fill='%23ffffff'/></svg>") no-repeat center / contain;
    mask:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 24'><path d='M1 12 Q26 10 30 1 Q34 10 59 12 Q34 14 30 23 Q26 14 1 12 Z' fill='%23ffffff'/></svg>") no-repeat center / contain;
    transform:translate(-50%,-50%); z-index:2; opacity:.85; }
  .gradecard .gnum { display:flex; align-items:center; gap:var(--s3); justify-content:flex-end; font-size:12px; color:var(--ink); }
  .gradecard .gnum .gt { color:var(--steel); font-size:11px; }
  @media (max-width:980px) { .gradecard .grow { grid-template-columns:1fr; gap:var(--s1); } .gradecard .gnum { justify-content:flex-start; } }
  /* Sprint 21 - Accordion dim qui deroule INLINE en dessous (pattern geo) */
  .gradecard .grow-wrap { cursor:pointer; }
  .gradecard .grow.has-acc { transition:background .15s; border-radius:var(--r2); padding:2px 4px; margin:0 -4px; }
  .gradecard .grow-wrap:hover .grow.has-acc { background:color-mix(in srgb,var(--ink) 4%,transparent); }
  .gradecard .gsub { max-height:0; overflow:hidden; opacity:0; transition:max-height .3s ease, opacity .2s ease, margin .3s ease, padding .3s ease; padding:0 10px; margin:0; }
  .gradecard .grow-wrap.open .gsub { max-height:260px; opacity:1; margin:var(--s15) 0 14px; padding:var(--s25) 14px; }
  .gradecard .gsub { background:color-mix(in srgb,var(--ink) 3%,transparent); border-left:2px solid var(--line2); border-radius:0 var(--r2) var(--r2) 0; margin-left:var(--s15); }
  .gradecard .gsub-chips { display:flex; flex-wrap:wrap; gap:var(--s15); margin-bottom:var(--s2); }
  .gradecard .gsub-tk { font-family:var(--fm); font-size:11px; font-weight:600; color:var(--ink); background:color-mix(in srgb,var(--ink) 8%,transparent); padding:3px 9px; border-radius:var(--r1); cursor:pointer; transition:.12s; }
  .gradecard .gsub-tk:hover { background:color-mix(in srgb,var(--id) 16%,transparent); color:var(--id); }
  .gradecard .gsub-empty { font-family:var(--fm); font-size:11px; color:var(--steel); font-style:italic; }
  .gradecard .gsub-ev { font-family:var(--fm); font-size:11px; color:var(--steel); line-height:1.55; padding-top:var(--s15); border-top:1px solid color-mix(in srgb,var(--ink) 6%,transparent); }
  /* Sub-notes Construction + Fragilite (glossaire canonique) */
  .gradecard .gsplit { display:grid; grid-template-columns:1fr 1fr; gap:var(--s5); margin-top:var(--s4); padding-top:var(--s4); border-top:1px solid var(--line); }
  .gradecard .gsub { display:flex; flex-direction:column; gap:var(--s3); }
  .gradecard .gsubh { font-family:var(--fb); font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); font-weight:600; }
  .gradecard .gsubscore { font-size:32px; font-weight:500; line-height:1; letter-spacing:-.02em; }
  .gradecard .gsubscore.good { color:var(--acc); }
  .gradecard .gsubscore.warn { color:var(--warn); }
  .gradecard .gsubscore.bad { color:var(--bear); }
  .gradecard .gsubmax { color:var(--steel); font-size:13px; margin-left:1px; font-weight:400; }
  @media (max-width:980px) { .gradecard .gsplit { grid-template-columns:1fr; gap:var(--s35); } }
  .gradecard .ggate { font-family:var(--fm); font-size:12px; color:var(--bear); background:color-mix(in srgb,var(--bear) 10%,transparent); padding:var(--s25) 14px; border-radius:var(--r2); margin:var(--s35) 0; border-left:3px solid var(--bear); }
  /* Top Risques surveillance */
  .riskwatchcard .rw-lens { font-family:var(--fm); margin:var(--s25) 0 4px; padding:9px 12px; background:color-mix(in srgb, var(--warn) 5%, transparent); border-left:2px solid var(--warn); border-radius:2px; font-size:12px; color:var(--ink); line-height:1.55; }
  .riskwatchcard .rw-card { padding:16px 0; border-bottom:1px solid var(--line); }
  .riskwatchcard .rw-card:last-child { border-bottom:none; }
  .riskwatchcard .rw-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s2); }
  .riskwatchcard .rw-rank { font-family:var(--fm); font-weight:700; font-size:18px; color:var(--bear); }
  .riskwatchcard .rw-name { font-family:var(--fm); font-weight:500; font-size:16px; color:var(--ink); flex:1; }
  .riskwatchcard .rw-sev { font-family:var(--fb); font-size:11px; letter-spacing:.15em; text-transform:uppercase; font-weight:600; padding:2px 7px; border-radius:var(--r1); }
  .riskwatchcard .rw-sev.danger { background:color-mix(in srgb,var(--bear) 18%,transparent); color:var(--bear); }
  .riskwatchcard .rw-sev.warn { background:color-mix(in srgb,var(--warn) 18%,transparent); color:var(--warn); }
  .riskwatchcard .rw-expo { font-family:var(--fm); font-size:12px; color:var(--steel); margin-bottom:var(--s35); }
  .riskwatchcard .rw-grid { display:grid; grid-template-columns:repeat(3, 1fr); gap:var(--s35); margin-bottom:var(--s4); }
  .riskwatchcard .rw-cell { padding:var(--s3) var(--s35); background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); }
  .riskwatchcard .rw-h { font-family:var(--fb); font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s15); }
  .riskwatchcard .rw-v { font-family:var(--fm); font-size:22px; font-weight:500; color:var(--ink); line-height:1; }
  .riskwatchcard .rw-v.neg { color:var(--bear); }
  .riskwatchcard .rw-t { font-family:var(--fm); font-size:11px; color:var(--steel); margin-top:var(--s1); }
  .riskwatchcard .rw-section { margin-top:var(--s35); }
  .riskwatchcard .rw-sh { font-family:var(--fb); font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s25); }
  .riskwatchcard .rw-sig { padding:var(--s2) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .riskwatchcard .rw-sig.atrisk { border-left:3px solid var(--warn); padding-left:var(--s25); margin-left:-10px; background:color-mix(in srgb,var(--warn) 4%,transparent); }
  .riskwatchcard .rw-sig.triggered { border-left:3px solid var(--bear); padding-left:var(--s25); margin-left:-10px; background:color-mix(in srgb,var(--bear) 5%,transparent); }
  .riskwatchcard .rw-sig-head { display:grid; grid-template-columns:1fr 100px 90px; gap:var(--s3); font-size:12px; align-items:baseline; }
  .riskwatchcard .rw-sig-l { color:var(--ink); }
  .riskwatchcard .rw-sig-w { font-family:var(--fb); font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--steel); text-align:right; }
  .riskwatchcard .rw-sig-s { font-family:var(--fm); font-size:11px; text-align:right; padding:1px 6px; border-radius:var(--r1); font-weight:600; }
  .riskwatchcard .rw-sig-s.monitoring { color:var(--steel); background:color-mix(in srgb,var(--ink) 6%,transparent); }
  .riskwatchcard .rw-sig-s.atrisk { color:var(--warn); background:color-mix(in srgb,var(--warn) 14%,transparent); }
  .riskwatchcard .rw-sig-s.triggered { color:var(--bear); background:color-mix(in srgb,var(--bear) 16%,transparent); }
  .riskwatchcard .rw-sig-reason { font-family:var(--fm); font-size:11px; color:var(--ink); opacity:.85; line-height:1.45; margin-top:var(--s15); }
  .riskwatchcard .rw-sig-conf { color:var(--steel); font-size:11px; }
  .riskwatchcard .rw-mit { padding:var(--s25) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .riskwatchcard .rw-mit:last-child { border-bottom:none; }
  .riskwatchcard .rw-mit-h { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s15); }
  .riskwatchcard .rw-mit-l { font-family:var(--fm); font-weight:500; font-size:13px; color:var(--ink); flex:1; }
  .riskwatchcard .rw-mit-st { font-family:var(--fm); font-size:11px; font-variant-numeric:tabular-nums; padding:1px 6px; border-radius:var(--r1); font-weight:600; }
  .riskwatchcard .rw-mit-st.started { background:color-mix(in srgb,var(--warn) 12%,transparent); color:var(--warn); }
  .riskwatchcard .rw-mit-st.in_progress { background:color-mix(in srgb,var(--acc) 12%,transparent); color:var(--acc); }
  .riskwatchcard .rw-mit-st.pending { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--steel); }
  .riskwatchcard .rw-mit-a { font-family:var(--fm); font-size:12px; color:var(--ink); opacity:.85; line-height:1.5; margin-bottom:3px; }
  .riskwatchcard .rw-mit-n { font-family:var(--fm); font-size:11px; color:var(--steel); font-style:italic; }
  @media (max-width:980px) { .riskwatchcard .rw-grid { grid-template-columns:1fr; } .riskwatchcard .rw-sig { grid-template-columns:1fr; } }
  /* Calibration progress panel (action #3 31/05) -- s'active a n>=30 */
  .calibcard .calib-progress { display:flex; align-items:center; gap:var(--s4); margin-top:var(--s35); }
  .calibcard .calib-bar { flex:1; height:8px; background:color-mix(in srgb, var(--steel) 12%, transparent); border-radius:2px; overflow:hidden; position:relative; }
  .calibcard .calib-fill { height:100%; background:linear-gradient(90deg, var(--acc), color-mix(in srgb, var(--acc) 70%, var(--gold))); transition:width .4s ease; }
  .calibcard .calib-meta { display:flex; align-items:baseline; gap:var(--s35); min-width:160px; justify-content:flex-end; }
  .calibcard .calib-n { font-family:var(--fmono); font-size:18px; font-weight:500; color:var(--ink); font-variant-numeric:tabular-nums; }
  .calibcard .calib-rem { font-family:var(--fm); font-size:12px; color:var(--steel); }
  .calibcard .calib-verdict { display:flex; align-items:baseline; gap:var(--s4); margin-top:var(--s35); flex-wrap:wrap; }
  .calibcard .calib-status { font-family:var(--fm); font-weight:500; font-size:13px; letter-spacing:.08em; text-transform:uppercase; padding:3px 10px; border-radius:2px; background:color-mix(in srgb, var(--ink) 6%, transparent); }
  .calibcard .calib-status.acc { color:var(--acc); background:color-mix(in srgb, var(--acc) 10%, transparent); }
  .calibcard .calib-status.warn { color:var(--warn); background:color-mix(in srgb, var(--warn) 12%, transparent); }
  .calibcard .calib-status.neg { color:var(--bear); background:color-mix(in srgb, var(--bear) 12%, transparent); }
  .calibcard .calib-brier, .calibcard .calib-gap { font-family:var(--fm); font-size:13px; color:var(--steel); }
  .calibcard .calib-brier .mono, .calibcard .calib-gap .mono { color:var(--ink); margin-left:var(--s1); }
  .calibcard .calib-msg { margin-top:var(--s25); font-family:var(--fm); font-size:13px; color:var(--ink2); line-height:1.55; padding-top:var(--s25); border-top:1px solid var(--line); }
  /* Page Strategie : sub-section headers */
  .strat-sh { font-family:var(--fb); font-weight:500; font-size:13px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin:32px 0 14px; padding-bottom:var(--s2); border-bottom:1px solid var(--line); }
  .strat-sh:first-of-type { margin-top:var(--s35); }
  /* Section headers page vigie (refonte hierarchie 30/05 -- 3 blocs : Operationnel / Systeme V2 / Contextuel) */
  .vigie-sh { font-family:var(--fb); font-weight:500; font-size:13px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin:28px 0 12px; padding-bottom:var(--s2); border-bottom:1px solid var(--line); }
  .vigie-sh:first-of-type { margin-top:var(--s4); }
  /* Sprint 19 - User strategy panel */
  .strategiecard .us-grid { display:grid; grid-template-columns:1fr; gap:var(--s2); margin:var(--s35) 0; padding-bottom:var(--s35); border-bottom:1px solid var(--line); }
  .strategiecard .us-row { display:flex; align-items:baseline; gap:var(--s35); padding:var(--s15) 0; }
  .strategiecard .us-k { font-family:var(--fm); font-size:12px; color:var(--steel); min-width:200px; }
  .strategiecard .us-v { font-family:var(--fm); font-size:13px; color:var(--ink); font-variant-numeric:tabular-nums; }
  .strategiecard .us-desc { font-family:var(--fm); font-size:12px; color:var(--steel); line-height:1.55; font-style:italic; margin-top:var(--s35); }
  .strategiecard .us-cta { font-family:var(--fm); margin:var(--s2) 0 14px; padding:var(--s3) var(--s35); border-left:2px solid var(--accent-red, #c44); background:color-mix(in srgb, var(--accent-red, #c44) 5%, transparent); border-radius:2px; }
  .strategiecard .us-cta.valid { border-left-color:var(--accent-green, #4a8); background:color-mix(in srgb, var(--accent-green, #4a8) 4%, transparent); }
  .strategiecard .us-cta-h { font-size:11px; color:var(--steel); text-transform:uppercase; letter-spacing:.05em; margin-bottom:var(--s15); }
  .strategiecard .us-cta-b { font-size:13px; color:var(--ink); line-height:1.55; }
  .strategiecard .us-cta-f { font-size:11px; color:var(--steel); margin-top:var(--s2); font-family:var(--fm-mono, monospace); }
  .strategiecard .us-cta-f code { background:color-mix(in srgb, var(--ink) 6%, transparent); padding:2px 6px; border-radius:2px; font-size:11px; }
  .strategiecard .us-construction { font-family:var(--fm); margin:var(--s2) 0 14px; padding:var(--s3) var(--s35); border-left:2px solid var(--warn); background:color-mix(in srgb, var(--warn) 5%, transparent); border-radius:2px; }
  .strategiecard .us-cstr-h { font-size:11px; color:var(--warn); text-transform:uppercase; letter-spacing:.05em; font-weight:600; margin-bottom:var(--s15); }
  .strategiecard .us-cstr-b { font-size:13px; color:var(--ink); line-height:1.6; }
  /* F7 add 29/05 - Positions en vol aveugle (entry/target/stop/triggers manquants) */
  .blindcard { border-left:2px solid var(--bear); padding-left:var(--s35) !important; }
  .blindcard .ba-row { padding:var(--s25) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .blindcard .ba-row:last-child { border-bottom:none; }
  .blindcard .ba-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s1); }
  .blindcard .ba-tk { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); }
  .blindcard .ba-conv { font-family:var(--fm); font-size:11px; color:var(--steel); padding:1px 6px; background:color-mix(in srgb,var(--ink) 8%,transparent); border-radius:var(--r1); }
  .blindcard .ba-since { font-family:var(--fm); font-size:11px; color:var(--steel); margin-left:auto; }
  .blindcard .ba-missing { font-family:var(--fm); font-size:12px; color:var(--ink); opacity:.85; }
  .blindcard .ba-missing b { color:var(--bear); font-weight:600; }
  /* Sprint 5/6 - Copilot interventions panel */
  .copilotcard .cp-row { padding:var(--s3) var(--s35); border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); cursor:pointer; transition:background .15s; }
  .copilotcard .cp-row:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); border-radius:var(--r2); }
  .copilotcard .cp-row:last-child { border-bottom:none; }
  .copilotcard .cp-row.cp-flagged { border-left:2px solid var(--bear); padding-left:var(--s3); background:color-mix(in srgb,var(--bear) 3%,transparent); }
  .copilotcard .cp-biases { display:flex; gap:var(--s15); flex-wrap:wrap; margin-top:var(--s2); }
  .copilotcard .cp-bias { font-family:var(--fm); font-size:11px; padding:2px 8px; border-radius:var(--r1); background:color-mix(in srgb,var(--bear) 12%,transparent); color:var(--bear); letter-spacing:.03em; }
  .copilotcard .cp-brief-wrap { max-height:0; overflow:hidden; opacity:0; transition:max-height .3s ease, opacity .2s ease, margin .3s ease; }
  .copilotcard .cp-row.open .cp-brief-wrap { max-height:600px; opacity:1; margin-top:var(--s25); }
  .copilotcard .cp-brief-label { font-family:var(--fb); font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s15); }
  .copilotcard .cp-brief { font-family:var(--fm); font-size:13px; color:var(--ink); line-height:1.6; padding:var(--s25) 12px; background:color-mix(in srgb,var(--ink) 4%,transparent); border-radius:var(--r2); border-left:2px solid color-mix(in srgb,var(--ink) 15%,transparent); }
  .copilotcard .cp-head { display:flex; align-items:center; gap:var(--s3); flex-wrap:wrap; margin-bottom:var(--s15); }
  .copilotcard .cp-tk { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); }
  .copilotcard .cp-dtype { font-family:var(--fb); font-size:11px; letter-spacing:.15em; text-transform:uppercase; color:var(--steel); }
  .copilotcard .cp-ver { font-family:var(--fb); font-size:11px; letter-spacing:.15em; font-weight:600; padding:2px 6px; border-radius:var(--r1); }
  .copilotcard .cp-ver.ok { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .copilotcard .cp-ver.warn { background:color-mix(in srgb,var(--warn) 14%,transparent); color:var(--warn); }
  .copilotcard .cp-ver.bad { background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); }
  .copilotcard .cp-date { font-family:var(--fm); font-size:11px; color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .copilotcard .cp-anc { font-family:var(--fm); font-size:12px; color:var(--ink); line-height:1.45; opacity:.85; }
  .copilotcard .cp-outc { display:inline-block; margin-top:var(--s15); font-family:var(--fb); font-size:11px; letter-spacing:.12em; padding:2px 6px; border-radius:var(--r1); }
  .copilotcard .cp-outc.ok { background:color-mix(in srgb,var(--acc) 12%,transparent); color:var(--acc); }
  .copilotcard .cp-outc.bad { background:color-mix(in srgb,var(--bear) 12%,transparent); color:var(--bear); }
  /* Sprint 6 - Narrative clusters panel */
  .narrativecard .nv-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:var(--s3); margin:var(--s35) 0 18px; }
  .narrativecard .nv-cluster { background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); padding:var(--s35) 16px; }
  .narrativecard .nv-cl-head { display:flex; align-items:baseline; gap:var(--s2); margin-bottom:var(--s15); flex-wrap:wrap; }
  .narrativecard .nv-cl-name { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); flex:1; min-width:0; }
  .narrativecard .nv-cl-overlap { font-family:var(--fb); font-size:11px; letter-spacing:.12em; padding:2px 6px; border-radius:var(--r1); font-weight:600; }
  .narrativecard .nv-cl-overlap.high { background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); }
  .narrativecard .nv-cl-overlap.mid { background:color-mix(in srgb,var(--warn) 14%,transparent); color:var(--warn); }
  .narrativecard .nv-cl-overlap.low { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .narrativecard .nv-cl-n { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; }
  .narrativecard .nv-cl-tks { font-family:var(--fm); font-size:11px; color:var(--ink); margin-bottom:var(--s15); opacity:.8; font-variant-numeric:tabular-nums; }
  .narrativecard .nv-cl-driv { font-family:var(--fm); font-size:12px; color:var(--steel); line-height:1.4; }
  .narrativecard .nv-split { display:grid; grid-template-columns:1fr 1fr; gap:var(--s4); border-top:1px solid var(--line); padding-top:var(--s35); }
  .narrativecard .nv-h { font-family:var(--fb); font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s2); }
  .narrativecard .nv-line { display:flex; align-items:baseline; gap:var(--s2); padding:var(--s15) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); font-size:12px; }
  .narrativecard .nv-line:last-child { border-bottom:none; }
  .narrativecard .nv-tk { font-family:var(--fm); font-weight:600; color:var(--ink); min-width:70px; }
  .narrativecard .nv-with { font-family:var(--fm); color:var(--steel); font-size:11px; }
  .narrativecard .nv-why { font-family:var(--fm); color:var(--ink); opacity:.85; line-height:1.4; flex:1; }
  @media (max-width:980px) { .narrativecard .nv-split { grid-template-columns:1fr; } }
  /* Sprint 9 - Conversations recentes */
  .conversationscard .cv-row { padding:var(--s25) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .conversationscard .cv-row:last-child { border-bottom:none; }
  .conversationscard .cv-meta { display:flex; align-items:center; gap:var(--s2); margin-bottom:var(--s15); font-family:var(--fb); font-size:11px; letter-spacing:.14em; text-transform:uppercase; }
  .conversationscard .cv-role { font-weight:600; padding:2px 6px; border-radius:var(--r1); }
  .conversationscard .cv-role.user { background:color-mix(in srgb,var(--id) 14%,transparent); color:var(--id); }
  .conversationscard .cv-role.assistant { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--ink); }
  .conversationscard .cv-surf { color:var(--steel); }
  .conversationscard .cv-date { margin-left:auto; color:var(--steel); font-variant-numeric:tabular-nums; }
  .conversationscard .cv-content { font-family:var(--fm); font-size:12px; line-height:1.45; color:var(--ink); opacity:.85; }
  .conversationscard .cv-user .cv-content { color:var(--ink); opacity:.95; }
  /* Sprint 9.d - Soft signals panel */
  .chatsigcard .cs-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:var(--s35); margin-top:var(--s35); }
  .chatsigcard .cs-group { background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); padding:var(--s3) var(--s35); }
  .chatsigcard .cs-kind { font-family:var(--fb); font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s25); }
  .chatsigcard .cs-row { padding:var(--s2) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .chatsigcard .cs-row:last-child { border-bottom:none; }
  .chatsigcard .cs-meta { display:flex; align-items:baseline; gap:var(--s2); margin-bottom:var(--s1); }
  .chatsigcard .cs-target { font-family:var(--fm); font-weight:600; font-size:12px; color:var(--ink); }
  .chatsigcard .cs-val { font-family:var(--fm); font-size:11px; font-variant-numeric:tabular-nums; padding:1px 6px; border-radius:var(--r1); margin-left:auto; }
  .chatsigcard .cs-val.neg { background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); }
  .chatsigcard .cs-val.pos { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .chatsigcard .cs-val.neu { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--steel); }
  .chatsigcard .cs-quote { font-family:var(--fm); font-size:12px; font-style:italic; color:var(--ink); opacity:.85; line-height:1.4; margin-bottom:3px; }
  .chatsigcard .cs-note { font-family:var(--fm); font-size:11px; color:var(--steel); line-height:1.4; }
  /* Layer 2 - Conceptions du bot */
  .conceptionscard .bc-row { padding:var(--s35) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); cursor:pointer; }
  .conceptionscard .bc-row:last-child { border-bottom:none; }
  .conceptionscard .bc-row:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); border-radius:var(--r2); }
  .conceptionscard .bc-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s2); flex-wrap:wrap; }
  .conceptionscard .bc-target { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); }
  .conceptionscard .bc-kind { font-family:var(--fb); font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); }
  .conceptionscard .bc-conv { font-family:var(--fm); font-size:11px; font-variant-numeric:tabular-nums; padding:1px 6px; border-radius:var(--r1); font-weight:600; }
  .conceptionscard .bc-conv.high { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .conceptionscard .bc-conv.mid { background:color-mix(in srgb,var(--warn) 14%,transparent); color:var(--warn); }
  .conceptionscard .bc-conv.low { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--steel); }
  .conceptionscard .bc-val { font-family:var(--fm); font-size:11px; font-variant-numeric:tabular-nums; padding:1px 6px; border-radius:var(--r1); }
  .conceptionscard .bc-val.neg { background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); }
  .conceptionscard .bc-val.pos { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .conceptionscard .bc-val.neu { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--steel); }
  .conceptionscard .bc-n { font-family:var(--fm); font-size:11px; color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .conceptionscard .bc-text { font-family:var(--fm); font-size:13px; line-height:1.55; color:var(--ink); opacity:.88; max-height:62px; overflow:hidden; position:relative; transition:max-height .3s ease; }
  .conceptionscard .bc-text::after { content:""; position:absolute; bottom:0; left:0; right:0; height:24px; background:linear-gradient(to bottom, transparent, var(--paper, #f5efe3)); pointer-events:none; transition:opacity .2s ease; }
  .conceptionscard .bc-row.open .bc-text { max-height:600px; }
  .conceptionscard .bc-row:hover .bc-text::after, .conceptionscard .bc-row.open .bc-text::after { opacity:0; }
  /* Layer 3 - Preferences calibrees */
  .preferencescard .pr-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:var(--s35); margin-top:var(--s35); }
  .preferencescard .pr-group { background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); padding:var(--s3) var(--s35); }
  .preferencescard .pr-h { display:flex; align-items:baseline; gap:var(--s2); margin-bottom:var(--s25); }
  .preferencescard .pr-kind { font-family:var(--fb); font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--ink); font-weight:600; }
  .preferencescard .pr-meta { font-family:var(--fm); font-size:11px; color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .preferencescard .pr-row { display:flex; align-items:baseline; gap:var(--s3); padding:var(--s15) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 3%,transparent); font-size:12px; }
  .preferencescard .pr-row:last-child { border-bottom:none; }
  .preferencescard .pr-key { font-family:var(--fm); font-weight:500; color:var(--ink); min-width:60px; }
  .preferencescard .pr-mid { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; }
  .preferencescard .pr-num { margin-left:auto; font-variant-numeric:tabular-nums; }
  .preferencescard .pr-num.pos { color:var(--acc); }
  .preferencescard .pr-num.neg { color:var(--bear); }
  .preferencescard .pr-num.neu { color:var(--steel); }
  .preferencescard .pr-win { font-family:var(--fm); font-size:11px; color:var(--steel); min-width:50px; text-align:right; }
  /* Sprint 12 - Ticker axes */
  .axescard .ax-group { background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); padding:var(--s35) 16px; margin-top:var(--s35); }
  .axescard .ax-h { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s25); padding-bottom:var(--s2); border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .axescard .ax-macro { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); }
  .axescard .ax-n { font-family:var(--fm); font-size:11px; color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .axescard .ax-row { display:grid; grid-template-columns:78px 1fr; gap:var(--s35); padding:var(--s2) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .axescard .ax-row:last-child { border-bottom:none; }
  .axescard .ax-tk { font-family:var(--fm); font-weight:600; font-size:12px; color:var(--ink); }
  .axescard .ax-fields { display:flex; flex-direction:column; gap:3px; }
  .axescard .ax-f { font-family:var(--fm); font-size:11px; color:var(--ink); opacity:.82; line-height:1.4; }
  .axescard .ax-l { display:inline-block; font-family:var(--fb); font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--steel); width:50px; }
  /* Sprint 13 - Factor exposures + Stress + Trajectory */
  .factorscard .fe-row { padding:var(--s3) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .factorscard .fe-row:last-child { border-bottom:none; }
  .factorscard .fe-row.fe-composite { padding:var(--s35) 14px; margin:0 -14px 8px; background:color-mix(in srgb,var(--bear) 6%,transparent); border-left:2px solid var(--bear); border-radius:2px; border-bottom:none; }
  .factorscard .fe-row.fe-composite .fe-name { font-weight:600; }
  .factorscard .fe-comp-note { font-family:var(--fm); font-size:11px; color:var(--steel); margin-top:var(--s15); line-height:1.45; font-style:italic; }
  .factorscard .fe-th { font-family:var(--fm); font-size:11px; color:var(--steel); margin-left:2px; padding:0 4px; background:color-mix(in srgb,var(--ink) 6%,transparent); border-radius:var(--r1); }
  .factorscard .fe-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s15); }
  .factorscard .fe-name { font-family:var(--fm); font-weight:500; font-size:13px; color:var(--ink); flex:1; }
  .factorscard .fe-pct { font-family:var(--fm); font-size:13px; font-weight:600; font-variant-numeric:tabular-nums; }
  .factorscard .fe-pct.high { color:var(--bear); }
  .factorscard .fe-pct.mid { color:var(--warn); }
  .factorscard .fe-pct.low { color:var(--acc); }
  .factorscard .fe-eur { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; min-width:75px; text-align:right; }
  .factorscard .fe-bar { height:5px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r1); overflow:hidden; margin:var(--s1) 0 6px; }
  .factorscard .fe-fill { height:100%; border-radius:var(--r1); }
  .factorscard .fe-fill.high { background:var(--bear); }
  .factorscard .fe-fill.mid { background:var(--warn); }
  .factorscard .fe-fill.low { background:var(--acc); }
  .factorscard .fe-tks { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; }
  .stresscard .st-row { display:flex; align-items:baseline; gap:var(--s35); padding:var(--s25) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .stresscard .st-row:last-child { border-bottom:none; }
  .stresscard .st-name { font-family:var(--fm); font-size:12px; color:var(--ink); flex:1; }
  .stresscard .st-impact { display:flex; align-items:baseline; gap:var(--s3); }
  .stresscard .st-pct { font-family:var(--fm); font-size:13px; font-weight:600; font-variant-numeric:tabular-nums; min-width:60px; text-align:right; }
  .stresscard .st-pct.pos { color:var(--acc); }
  .stresscard .st-pct.danger { color:var(--bear); }
  .stresscard .st-pct.warn { color:var(--warn); }
  .stresscard .st-pct.neu { color:var(--steel); }
  .stresscard .st-eur { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; min-width:90px; text-align:right; }
  .stresscard .st-n { font-family:var(--fm); font-size:11px; color:var(--steel); min-width:40px; text-align:right; font-variant-numeric:tabular-nums; }
  .trajcard .tr-hero { font-family:var(--fm); font-size:18px; font-weight:500; color:var(--ink); padding:var(--s35) 0 16px; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); margin-bottom:var(--s2); display:flex; align-items:baseline; gap:var(--s2); }
  .trajcard .tr-row { display:flex; align-items:baseline; gap:var(--s3); padding:var(--s2) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 3%,transparent); font-size:12px; }
  .trajcard .tr-row:last-child { border-bottom:none; }
  .trajcard .tr-key { font-family:var(--fm); color:var(--ink); flex:1; }
  .trajcard .tr-from, .trajcard .tr-to { font-variant-numeric:tabular-nums; color:var(--ink); opacity:.85; min-width:48px; text-align:right; }
  .trajcard .tr-arr { color:var(--steel); font-size:11px; }
  .trajcard .tr-delta { font-variant-numeric:tabular-nums; min-width:64px; text-align:right; font-weight:500; }
  .trajcard .tr-delta.pos { color:var(--acc); }
  .trajcard .tr-delta.neg { color:var(--bear); }
  .trajcard .tr-delta.neu { color:var(--steel); }
  /* Sprint 14 - SPOF + Mauboussin + Valo */
  .spofcard .sp-row { padding:var(--s3) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .spofcard .sp-row:last-child { border-bottom:none; }
  .spofcard .sp-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s15); }
  .spofcard .sp-node { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); flex:1; }
  .spofcard .sp-pct { font-family:var(--fm); font-size:13px; font-weight:600; font-variant-numeric:tabular-nums; }
  .spofcard .sp-pct.high { color:var(--bear); }
  .spofcard .sp-pct.mid { color:var(--warn); }
  .spofcard .sp-pct.low { color:var(--acc); }
  .spofcard .sp-eur { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; min-width:80px; text-align:right; }
  .spofcard .sp-n { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; min-width:38px; text-align:right; }
  .spofcard .sp-bar { height:5px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r1); overflow:hidden; margin:var(--s1) 0 6px; }
  .spofcard .sp-fill { height:100%; border-radius:var(--r1); }
  .spofcard .sp-fill.high { background:var(--bear); }
  .spofcard .sp-fill.mid { background:var(--warn); }
  .spofcard .sp-fill.low { background:var(--acc); }
  .spofcard .sp-deps { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; }
  .mauboussincard .ms-row { display:grid; grid-template-columns:70px 50px 65px 75px 75px 75px 65px auto; align-items:center; gap:var(--s3); padding:var(--s2) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 3%,transparent); font-size:12px; }
  .mauboussincard .ms-frag { font-family:var(--fm); font-size:11px; padding:2px 7px; border-radius:var(--r1); background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); letter-spacing:.03em; justify-self:start; }
  .mauboussincard .ms-stopd { font-family:var(--fm); color:var(--steel); }
  .mauboussincard .ms-stopd.outlier { color:var(--bear); font-weight:600; background:color-mix(in srgb,var(--bear) 10%,transparent); padding:1px 5px; border-radius:var(--r1); }
  .mauboussincard .ms-row:last-child { border-bottom:none; }
  .mauboussincard .ms-tk { font-family:var(--fm); font-weight:600; color:var(--ink); }
  .mauboussincard .ms-conv { font-family:var(--fm); color:var(--steel); }
  .mauboussincard .ms-fade { font-family:var(--fm); padding:1px 5px; border-radius:var(--r1); font-size:11px; text-align:center; }
  .mauboussincard .ms-fade.low { background:color-mix(in srgb,var(--acc) 12%,transparent); color:var(--acc); }
  .mauboussincard .ms-fade.mid { background:color-mix(in srgb,var(--warn) 12%,transparent); color:var(--warn); }
  .mauboussincard .ms-fade.high { background:color-mix(in srgb,var(--bear) 12%,transparent); color:var(--bear); }
  .mauboussincard .ms-target, .mauboussincard .ms-actual { font-family:var(--fm); color:var(--ink); opacity:.85; text-align:right; font-variant-numeric:tabular-nums; }
  .mauboussincard .ms-gap { font-family:var(--fm); font-weight:600; text-align:right; font-variant-numeric:tabular-nums; }
  .mauboussincard .ms-gap.pos { color:var(--acc); }
  .mauboussincard .ms-gap.neg { color:var(--bear); }
  .mauboussincard .ms-gap.neu { color:var(--steel); }
  .valocard .vb-row { padding:var(--s3) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .valocard .vb-row:last-child { border-bottom:none; }
  .valocard .vb-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s15); }
  .valocard .vb-tk { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); }
  .valocard .vb-pe { font-family:var(--fm); font-size:12px; color:var(--bear); font-variant-numeric:tabular-nums; margin-left:auto; }
  .valocard .vb-priced { font-family:var(--fm); font-size:12px; color:var(--ink); opacity:.9; line-height:1.45; margin-bottom:var(--s1); font-style:italic; }
  .valocard .vb-rat { font-family:var(--fm); font-size:11px; color:var(--steel); line-height:1.4; }
  @media (max-width:980px) { .mauboussincard .ms-row { grid-template-columns:60px 40px 1fr 65px; } .mauboussincard .ms-target, .mauboussincard .ms-actual { display:none; } }
  /* Sprint 15 - Kill-criteria */
  .killcard .kc-row { padding:var(--s3) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .killcard .kc-row:last-child { border-bottom:none; }
  .killcard .kc-row.triggered { border-left:3px solid var(--bear); padding-left:var(--s3); margin-left:-12px; }
  .killcard .kc-row.at_risk { border-left:3px solid var(--warn); padding-left:var(--s3); margin-left:-12px; }
  .killcard .kc-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s15); }
  .killcard .kc-tk { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); }
  .killcard .kc-status { font-family:var(--fb); font-size:11px; letter-spacing:.15em; text-transform:uppercase; font-weight:600; padding:2px 7px; border-radius:var(--r1); }
  .killcard .kc-status.triggered { background:color-mix(in srgb,var(--bear) 16%,transparent); color:var(--bear); }
  .killcard .kc-status.at_risk { background:color-mix(in srgb,var(--warn) 16%,transparent); color:var(--warn); }
  .killcard .kc-conf { font-family:var(--fm); font-size:11px; color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .killcard .kc-reason { font-family:var(--fm); font-size:12px; color:var(--ink); opacity:.88; line-height:1.5; margin-bottom:var(--s1); }
  .killcard .kc-ev { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; }
  /* 30/05 nuit -- arc V2 panels (vigilance + cohorte + wire activity) */
  .vgcard .vg-row { padding:var(--s25) 12px; border-radius:var(--r1); margin-bottom:var(--s15); background:color-mix(in srgb,var(--ink) 2%,transparent); border-left:3px solid transparent; }
  .vgcard .vg-row.vg-ok { border-left-color:var(--acc); }
  .vgcard .vg-row.vg-info { border-left-color:var(--steel); opacity:.75; }
  .vgcard .vg-row.vg-warn { border-left-color:var(--warn); background:color-mix(in srgb,var(--warn) 6%,transparent); }
  .vgcard .vg-row.vg-alert { border-left-color:var(--bear); background:color-mix(in srgb,var(--bear) 8%,transparent); }
  .vgcard .vg-row.vg-wait { border-left-color:color-mix(in srgb,var(--steel) 40%,transparent); opacity:.6; }
  .vgcard .vg-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s1); }
  .vgcard .vg-emoji { font-size:13px; }
  .vgcard .vg-name { font-family:var(--fb); font-size:11px; letter-spacing:.05em; text-transform:uppercase; font-weight:600; color:var(--ink); }
  .vgcard .vg-status { font-family:var(--fb); font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-left:auto; }
  .vgcard .vg-msg { font-family:var(--fm); font-size:12px; color:var(--ink); opacity:.85; line-height:1.5; }
  .v2cohortcard .v2-grid { display:grid; grid-template-columns:1fr 1fr; gap:var(--s35); margin-top:var(--s3); }
  .v2cohortcard .v2-side { padding:var(--s35); border:1px solid var(--line); border-radius:var(--r2); background:color-mix(in srgb,var(--ink) 2%,transparent); }
  .v2cohortcard .v2-current { border-left:3px solid var(--acc); }
  .v2cohortcard .v2-legacy { border-left:3px solid color-mix(in srgb,var(--steel) 50%,transparent); opacity:.85; }
  .v2cohortcard .v2-label { font-family:var(--fb); font-size:11px; letter-spacing:.16em; text-transform:uppercase; font-weight:600; color:var(--steel); margin-bottom:var(--s2); }
  .v2cohortcard .v2-stat-row { display:flex; gap:var(--s35); align-items:baseline; font-family:var(--fm); font-size:13px; font-variant-numeric:tabular-nums; }
  .v2cohortcard .v2-stat-n { font-weight:600; color:var(--ink); }
  .v2cohortcard .v2-stat-rg, .v2cohortcard .v2-stat-bk { color:var(--steel); font-size:12px; }
  .v2cohortcard .v2-status.v2-empty { font-family:var(--fm); font-size:12px; color:var(--steel); font-style:italic; line-height:1.4; }
  .wactcard .wact-grid { display:flex; gap:var(--s35); margin:var(--s3) 0 16px; }
  .wactcard .wact-cell { flex:1; padding:var(--s25) 14px; background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); }
  .wactcard .wact-label { font-family:var(--fb); font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); font-weight:600; margin-bottom:var(--s1); }
  .wactcard .wact-v { font-family:var(--fm); font-size:13px; color:var(--ink); }
  .wactcard .wact-recent-head { font-family:var(--fb); font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); font-weight:600; margin-bottom:var(--s2); padding-top:var(--s15); border-top:1px solid var(--line); }
  .wactcard .wact-recent { display:flex; gap:var(--s3); align-items:baseline; padding:var(--s15) 0; font-family:var(--fm); font-size:12px; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .wactcard .wact-recent:last-child { border-bottom:none; }
  .wactcard .wact-tk { font-family:var(--fb); font-weight:600; min-width:60px; color:var(--ink); }
  .wactcard .wact-when { color:var(--steel); font-variant-numeric:tabular-nums; }
  .wactcard .wact-sev { font-family:var(--fb); font-size:11px; letter-spacing:.14em; text-transform:uppercase; font-weight:600; padding:1px 6px; border-radius:var(--r1); }
  .wactcard .wact-sev.wact-catastrophic, .wactcard .wact-sev.wact-high { background:color-mix(in srgb,var(--bear) 16%,transparent); color:var(--bear); }
  .wactcard .wact-sev.wact-medium { background:color-mix(in srgb,var(--warn) 16%,transparent); color:var(--warn); }
  .wactcard .wact-sev.wact-low, .wactcard .wact-sev.wact-unknown { background:color-mix(in srgb,var(--steel) 12%,transparent); color:var(--steel); }
  .wactcard .wact-items { margin-left:auto; color:var(--steel); font-variant-numeric:tabular-nums; }
  @media (max-width:980px) {
    .v2cohortcard .v2-grid { grid-template-columns:1fr; }
    .wactcard .wact-grid { flex-direction:column; }
    .wactcard .wact-recent { flex-wrap:wrap; gap:var(--s15) 12px; }
    .wactcard .wact-items { margin-left:0; flex-basis:100%; font-size:11px; }
    /* wrappercard PEA/CTO alloc -- seul vrai panel a casser mobile (3-4 wrappers horizontal) */
    .wrappercard .wr-alloc { flex-direction:column; gap:var(--s3); }
    /* Note : autres panels (chatcard/chatsig/conversations/conceptions/preferences/axes/traj/fx)
       utilisent deja repeat(auto-fit, minmax(280px,1fr)) = responsive natif sans media query. */
  }
  /* Sprint 16 - Wrapper PEA/CTO + FX + Benchmark */
  .wrappercard .wr-alloc { display:flex; gap:var(--s4); margin:var(--s35) 0 18px; padding-bottom:var(--s35); border-bottom:1px solid var(--line); }
  .wrappercard .wr-row { flex:1; padding:var(--s3) var(--s35); background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); display:flex; flex-direction:column; gap:var(--s1); }
  .wrappercard .wr-key { font-family:var(--fb); font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); font-weight:600; }
  .wrappercard .wr-pct { font-family:var(--fm); font-size:22px; font-weight:500; color:var(--ink); font-variant-numeric:tabular-nums; }
  .wrappercard .wr-eur { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; }
  .wrappercard .wr-section { margin-top:var(--s35); }
  .wrappercard .wr-sh { font-family:var(--fb); font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s2); }
  .wrappercard .wr-mis { display:flex; align-items:baseline; gap:var(--s3); padding:var(--s15) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 3%,transparent); font-size:12px; }
  .wrappercard .wr-mis:last-child { border-bottom:none; }
  .wrappercard .wr-mis-tk { font-family:var(--fm); font-weight:600; color:var(--ink); min-width:80px; }
  .wrappercard .wr-mis-pct { font-family:var(--fm); color:var(--ink); margin-left:auto; font-variant-numeric:tabular-nums; min-width:55px; text-align:right; }
  .wrappercard .wr-mis-pct.neg { color:var(--bear); }
  .wrappercard .wr-mis-eur { font-family:var(--fm); color:var(--steel); font-variant-numeric:tabular-nums; min-width:80px; text-align:right; }
  .fxcard .fx-row { padding:var(--s3) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .fxcard .fx-row:last-child { border-bottom:none; }
  .fxcard .fx-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s15); }
  .fxcard .fx-cur { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); }
  .fxcard .fx-pct { font-family:var(--fm); font-size:13px; font-weight:600; font-variant-numeric:tabular-nums; }
  .fxcard .fx-pct.high { color:var(--bear); }
  .fxcard .fx-pct.mid { color:var(--warn); }
  .fxcard .fx-pct.low { color:var(--acc); }
  .fxcard .fx-eur { font-family:var(--fm); font-size:11px; color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .fxcard .fx-n { font-family:var(--fm); font-size:11px; color:var(--steel); min-width:32px; text-align:right; font-variant-numeric:tabular-nums; }
  .fxcard .fx-bar { height:5px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r1); overflow:hidden; margin:var(--s1) 0 6px; }
  .fxcard .fx-fill { height:100%; border-radius:var(--r1); }
  .fxcard .fx-fill.high { background:var(--bear); }
  .fxcard .fx-fill.mid { background:var(--warn); }
  .fxcard .fx-fill.low { background:var(--acc); }
  .fxcard .fx-tks { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; }
  .benchcard .bm-grid { display:grid; grid-template-columns:repeat(3, 1fr); gap:var(--s4); margin:var(--s35) 0; }
  .benchcard .bm-cell { padding:var(--s35) 18px; background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); }
  .benchcard .bm-h { font-family:var(--fb); font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); font-weight:600; margin-bottom:var(--s15); }
  .benchcard .bm-v { font-family:var(--fm); font-size:22px; font-weight:500; color:var(--ink); font-variant-numeric:tabular-nums; }
  .benchcard .bm-v.pos { color:var(--acc); }
  .benchcard .bm-v.neg { color:var(--bear); }
  .benchcard .bm-v.neu { color:var(--steel); }
  .benchcard .bm-foot { font-family:var(--fm); font-size:12px; color:var(--steel); margin-top:var(--s25); padding-top:var(--s25); border-top:1px solid var(--line); }
  .benchcard .bm-warn { font-family:var(--fm); font-size:12px; color:var(--warn); background:color-mix(in srgb,var(--warn) 8%,transparent); padding:var(--s2) 12px; border-radius:var(--r2); margin:var(--s3) 0 0; }
  /* Sprint 17 - Data-defined clusters */
  .clustercard .dc-sub { margin-top:var(--s35); }
  .clustercard .dc-sh { font-family:var(--fb); font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s2); }
  .clustercard .dc-row { display:flex; align-items:baseline; gap:var(--s3); padding:var(--s15) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); font-size:12px; }
  .clustercard .dc-row:last-child { border-bottom:none; }
  .clustercard .dc-pair { font-family:var(--fm); font-weight:500; color:var(--ink); flex:1; }
  .clustercard .dc-corr { font-family:var(--fm); color:var(--bear); font-weight:600; font-variant-numeric:tabular-nums; }
  .clustercard .dc-mix { padding:var(--s25) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .clustercard .dc-mix:last-child { border-bottom:none; }
  .clustercard .dc-mix-h { font-family:var(--fb); font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s15); }
  .clustercard .dc-mix-members { font-family:var(--fm); font-size:12px; color:var(--ink); line-height:1.5; }
  .clustercard .dc-mf { color:var(--steel); font-size:11px; margin-left:2px; }
  /* Sprint 7 - Chat surface */
  .chatcard .chat-log { max-height:340px; overflow-y:auto; padding:var(--s3) 0; margin-bottom:var(--s35); display:flex; flex-direction:column; gap:var(--s3); }
  .chatcard .chat-log:empty { display:none; }
  .chatcard .chat-msg { font-family:var(--fm); font-size:13px; line-height:1.5; padding:var(--s25) 14px; border-radius:var(--r2); max-width:88%; }
  .chatcard .chat-user { align-self:flex-end; background:color-mix(in srgb,var(--id) 14%,transparent); color:var(--ink); }
  .chatcard .chat-assistant { align-self:flex-start; background:color-mix(in srgb,var(--ink) 5%,transparent); color:var(--ink); }
  .chatcard .chat-form { display:flex; gap:var(--s3); align-items:flex-start; }
  .chatcard .chat-input { flex:1; font-family:var(--fm); font-size:13px; padding:var(--s25) 12px; border:1px solid var(--line2); background:var(--panel); color:var(--ink); border-radius:var(--r2); resize:vertical; min-height:54px; }
  .chatcard .chat-input:focus { outline:none; border-color:var(--id); }
  .chatcard .chat-send { font-family:var(--fb); font-size:12px; letter-spacing:.15em; text-transform:uppercase; padding:0 22px; height:54px; border-radius:var(--r2); border:1px solid var(--id); background:var(--id); color:var(--bg); cursor:pointer; transition:.15s; }
  .chatcard .chat-send:hover:not(:disabled) { opacity:.85; }
  .chatcard .chat-send:disabled { opacity:.5; cursor:default; }
  .chatcard .chat-foot { font-family:var(--fm); font-size:11px; color:var(--steel); margin-top:var(--s25); }
  .chatcard .chat-idle-clear { align-self:center; background:color-mix(in srgb,var(--steel) 8%,transparent); color:var(--steel); font-style:italic; font-size:12px; padding:var(--s2) 14px; }
  /* CANONIQUE charte §15 : switch light/dark TOUJOURS visible bas-gauche.
     SEULE position:fixed est canonique (suit la vision user au scroll).
     L'esthetique reste soft/discrete (border 1px --line, color --steel,
     bg --bg). z-index 90 = au-dessus du tape (80) mais sous loupe (1000). */
  .modetgl { position:fixed !important; left:var(--s25) !important;
             bottom:var(--s25) !important; z-index:90 !important;
             display:flex; align-items:center; justify-content:center;
             width:44px; height:44px; border-radius:var(--r3);
             border:1px solid var(--line); background:var(--bg);
             color:var(--steel); cursor:pointer; transition:.15s; }
  .foot .modetgl { margin-top:var(--s4); padding-top:0; }
  .foot::before { content:""; display:block; width:30px; height:1px; background:var(--line); margin:var(--s35) auto 4px; }
  .modetgl svg { width:20px; height:20px; }
  /* duplicate .modetgl:hover supprime 31/05 close W14b -- override la regle
     canonique §15 (background:var(--ink) color:var(--bg)) en noir-sur-noir.
     La regle canonique en haut du fichier est l'unique source de verite. */
  .hero, .pfcard { box-shadow:var(--elev); }
  .card, .kpi, .gauge, .plan { box-shadow:var(--elev); }
  .loupe-card { box-shadow:0 30px 90px -20px #000; }
  .nitem.on { box-shadow:inset 0 0 20px -10px color-mix(in srgb,var(--id) 55%,transparent); }
  .nitem.on svg { filter:drop-shadow(0 0 6px color-mix(in srgb,var(--id) 70%,transparent)); }
  .tape { box-shadow:none; }
  .row[data-tk]:hover, .dt tbody tr:hover td, .th-row:hover, .sbrow:hover { background:color-mix(in srgb,var(--ink) 3.5%,transparent); }
  .brk { margin-bottom:var(--s4); }
  .brk-h { display:flex; justify-content:space-between; align-items:baseline; margin:0 2px 10px; flex-wrap:wrap; gap:var(--s2); }
  .brk-n { font-family:var(--fm); font-weight:500; font-size:16px; letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .brk-note { font-family:var(--fm); font-size:11px; color:var(--steel); margin-left:var(--s2); }
  .brk-tot { font-family:var(--fm); font-size:13px; color:var(--ink); } .brk-tot span { color:var(--steel); font-size:12px; }
  .brk-body { display:flex; gap:var(--s5); align-items:flex-start; flex-wrap:wrap; }
  .brk-viz { flex:0 0 320px; max-width:320px; }
  .brk-tbl { flex:1; min-width:300px; }
  .brk-bars { display:flex; flex-direction:column; gap:2px; }
  .brk-row { display:grid; grid-template-columns:minmax(110px,1.3fr) minmax(60px,2.5fr) 42px 56px; align-items:center; gap:var(--s3); padding:var(--s2) 4px; border-radius:var(--r1); transition:background .15s; }
  .brk-row:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); }
  .brk-row-name { display:flex; align-items:center; gap:var(--s2); min-width:0; }
  .brk-row-dot { width:8px; height:8px; border-radius:50%; flex:0 0 auto; }
  .brk-row-label { font-family:var(--fb); font-weight:500; font-size:12px; color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .brk-row-bar { height:4px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:2px; overflow:hidden; }
  .brk-row-fill { height:100%; border-radius:2px; transition:width .4s cubic-bezier(.2,.8,.2,1); }
  .brk-row-pct { font-family:var(--fm); font-weight:500; font-size:12px; color:var(--ink); text-align:right; font-variant-numeric:tabular-nums; }
  .brk-row-val { font-family:var(--fm); font-weight:400; font-size:11px; color:var(--steel); text-align:right; font-variant-numeric:tabular-nums; }
"""

_CTA_JS = """
(function(){
  var modal=document.getElementById('ctaSearchModal');
  var input=document.getElementById('ctaSearchInput');
  var results=document.getElementById('ctaSearchResults');
  var btnSearch=document.getElementById('ctaSearch');
  var tkData=window.TK||{};
  var allTk=Object.keys(window._TKDOMAIN||{});
  var dataKeys=Object.keys(tkData);
  var uniq={}; allTk.concat(dataKeys).forEach(function(t){uniq[t]=1;});
  var allTickers=Object.keys(uniq).sort();
  var selIdx=0;
  function makeLogo(tk){
    if(typeof _tkLogoJs==='function') return _tkLogoJs(tk);
    return '<span class="tklogo tkfb">'+String(tk||'?').charAt(0).toUpperCase()+'</span>';
  }
  function render(q){
    var ql=(q||'').toLowerCase();
    var matches;
    if(!ql){ matches=allTickers.slice(0,25); }
    else {
      matches=allTickers.filter(function(tk){
        var nm=(tkData[tk]||{}).name||'';
        return tk.toLowerCase().indexOf(ql)>=0 || nm.toLowerCase().indexOf(ql)>=0;
      }).slice(0,40);
    }
    selIdx=0;
    if(!matches.length){ results.innerHTML='<div class="cta-result" style="opacity:.5">Aucun resultat</div>'; return; }
    results.innerHTML=matches.map(function(tk,i){
      var nm=(tkData[tk]||{}).name||'';
      return '<div class="cta-result '+(i===0?'sel':'')+'" data-tk="'+tk+'">'+makeLogo(tk)+'<span class="ctk">'+tk+'</span><span class="cnm">'+nm+'</span></div>';
    }).join('');
  }
  function open(){ modal.classList.add('open'); input.value=''; render(''); setTimeout(function(){input.focus();},50); }
  function close(){ modal.classList.remove('open'); }
  function chooseSel(){
    var els=results.querySelectorAll('.cta-result[data-tk]');
    if(els[selIdx]){
      var tk=els[selIdx].getAttribute('data-tk');
      close();
      if(typeof openLoupe==='function') openLoupe(tk);
    }
  }
  if(btnSearch) btnSearch.addEventListener('click',open);
  if(input){
    input.addEventListener('input',function(e){render(e.target.value);});
    input.addEventListener('keydown',function(e){
      if(e.key==='Escape'){ e.preventDefault(); close(); return; }
      if(e.key==='Enter'){ e.preventDefault(); chooseSel(); return; }
      if(e.key==='ArrowDown'||e.key==='ArrowUp'){
        e.preventDefault();
        var els=results.querySelectorAll('.cta-result[data-tk]');
        if(!els.length) return;
        selIdx=(selIdx+(e.key==='ArrowDown'?1:-1)+els.length)%els.length;
        els.forEach(function(el,i){el.classList.toggle('sel',i===selIdx);});
        els[selIdx].scrollIntoView({block:'nearest'});
      }
    });
  }
  if(modal) modal.addEventListener('click',function(e){
    if(e.target===modal){ close(); return; }
    var r=e.target.closest('.cta-result[data-tk]');
    if(r){ var tk=r.getAttribute('data-tk'); close(); if(typeof openLoupe==='function') openLoupe(tk); }
  });
  document.addEventListener('keydown',function(e){
    if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){ e.preventDefault(); open(); }
  });
})();
"""

_APP_JS = """
  const items=document.querySelectorAll('[data-nav]'),pages=document.querySelectorAll('[data-page]');
  document.querySelectorAll('table.dt th').forEach(function(th){
    th.addEventListener('click',function(){
      var tb=th.closest('table').querySelector('tbody'), rows=[].slice.call(tb.children);
      var k=th.dataset.k, num=th.classList.contains('num');
      var dir=th.dataset.dir==='asc'?-1:1; th.dataset.dir=dir===1?'asc':'desc';
      rows.sort(function(a,b){var x=a.dataset[k],y=b.dataset[k]; if(num){x=parseFloat(x);y=parseFloat(y);} return x<y?-dir:(x>y?dir:0);});
      rows.forEach(function(r){tb.appendChild(r);});
    });
  });
  function show(id){
    pages.forEach(p=>p.classList.toggle('active',p.dataset.page===id));
    items.forEach(n=>n.classList.toggle('on',n.dataset.nav===id));

    if(history.replaceState){history.replaceState(null,'','#'+id);}
  }
  items.forEach(n=>n.addEventListener('click',()=>show(n.dataset.nav)));
  var _h=(location.hash||'').replace('#','');if(_h&&/^[a-z]+$/.test(_h))show(_h);
  function _pct(v,sg){ return v==null?'&mdash;':((sg&&v>=0?'+':'')+v+'%'); }
  function mom(l,v){var c=v==null?'var(--steel)':(v>=0?'var(--acc)':'var(--bear)');return '<div class="lp-stat"><div class="lp-sl">'+l+'</div><div class="lp-sv" style="color:'+c+';font-size:16px">'+(v==null?'&mdash;':((v>=0?'+':'')+v+'%'))+'</div></div>';}
  // Sprint 3 logos tickers : map JS mirror du shared/ticker_logos.py
  window._TKDOMAIN = __TKDOMAIN_JSON__;
  window._TKLOCAL = __TKLOCAL_JSON__;
  function _tkLogoJs(tk){
    var init=String(tk||'?').charAt(0).toUpperCase();
    var fb="this.outerHTML='<span class=&quot;tklogo tkfb&quot;>"+init+"</span>'";
    // Priorite 1 : fichier local self-host (offline, sans appel externe)
    var localFile=(window._TKLOCAL||{})[tk]||(window._TKLOCAL||{})[String(tk).toUpperCase()];
    if(localFile){
      return '<img class="tklogo" src="/static/brand/logos/'+localFile+'" alt="" onerror="'+fb+'">';
    }
    var dom=(window._TKDOMAIN||{})[tk]||(window._TKDOMAIN||{})[String(tk).toUpperCase()];
    if(!dom) return '<span class="tklogo tkfb">'+init+'</span>';
    var ddg='https://icons.duckduckgo.com/ip3/'+dom+'.ico';
    var fb2="this.onerror=function(){"+fb+"};this.src='"+ddg+"'";
    return '<img class="tklogo" src="https://www.google.com/s2/favicons?domain='+dom+'&amp;sz=64" alt="" onerror="'+fb2+'">';
  }
  function openLoupe(tk){
    var d=(window.TK||{})[tk]||{};
    var st=d.status||'out';
    var stm={held:['d&eacute;tenu','held'],watch:['watchlist','watch'],core:['univers core','univ'],extended:['univers &eacute;tendu','univ'],out:['hors-univers','out']};
    var sb=stm[st]||stm.out;
    var badge='<span class="lp-badge '+sb[1]+'">'+sb[0]+(st==='held'&&d.weight_pct!=null?' &middot; '+d.weight_pct+'%':'')+'</span>';
    var a=d.analysis, sc='';
    if(a&&a.scores){
      var nm={quality:'Qualit&eacute;',growth:'Croissance',profitability:'Rentabilit&eacute;',valuation:'Valorisation',risk:'Risque',momentum:'Momentum',macro_alignment:'Macro'};
      for(var k in nm){ if(a.scores[k]!=null){ var v=Math.round(a.scores[k]); sc+='<div class="lp-score"><span class="ln">'+nm[k]+'</span><span class="bar"><span class="bf" style="width:'+v+'%"></span></span><span class="vv">'+v+'</span></div>'; } }
    }
    var ana = a ? ('<div class="lp-sec">Derni&egrave;re analyse &middot; '+a.date+(a.type?' &middot; '+a.type:'')+'</div>'+sc+(a.regime?'<div class="lp-meta">R&eacute;gime '+a.regime+(a.narr&&a.narr.length?' &middot; '+a.narr.join(', '):'')+'</div>':'')+(a.excerpt?'<div class="lp-ex">'+a.excerpt+'</div>':'')+'<div class="lp-hint">Analyse compl&egrave;te : <code>/analyze '+tk+'</code> sur Telegram, ou demande-la dans le chat.</div>') : '<div class="lp-sec">Analyse</div><div class="lp-empty">Aucune analyse stock&eacute;e. <code>/analyze '+tk+'</code> sur Telegram pour g&eacute;n&eacute;rer.</div>';
    document.getElementById('loupe-body').innerHTML =
      '<div class="lp-h">'+_tkLogoJs(tk)+'<span class="lp-tk">'+tk+'</span><span class="lp-nm">'+(d.name||'')+'</span></div>'
      +'<div class="lp-meta">'+badge+' &middot; '+(d.sector||'&mdash;')+' &middot; '+(d.country||'&mdash;')+'</div>'
      +((st==='held')?('<div class="lp-grid">'
      +'<div class="lp-stat"><div class="lp-sl">Poids</div><div class="lp-sv">'+d.weight_pct+'%</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">Investi</div><div class="lp-sv">'+d.weight_eur+'&euro;</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">P&amp;L</div><div class="lp-sv">'+_pct(d.pnl,true)+'</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">Marge stop</div><div class="lp-sv">'+_pct(d.down)+'</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">Vers cible</div><div class="lp-sv">'+_pct(d.up)+'</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">Asym&eacute;trie</div><div class="lp-sv">'+(d.ratio==null?'&mdash;':d.ratio+'x')+'</div></div>'
      +'</div>'+(d.perf?('<div class="lp-sec" style="margin-top:16px">Momentum r&eacute;cent</div><div class="lp-mom">'+mom('Jour',d.perf.d)+mom('Semaine',d.perf.w)+mom('Mois',d.perf.m)+'</div>'):'')):'<div class="lp-empty" style="padding:var(--s25) 0 2px">Pas de position ouverte sur ce titre.</div>')+ana;
    document.getElementById('loupe').classList.add('open');
  }
  function closeLoupe(){ var el=document.getElementById('loupe'); if(el)el.classList.remove('open'); }
  (function(){
    var BARS=document.getElementById('sb-bars'),PANEL=document.getElementById('sb-panel');
    if(!BARS||!PANEL||!window.SB_DATA)return;
    var DATA=window.SB_DATA;
    DATA.forEach(function(s){s.tw=s.t.reduce(function(a,x){return a+(x.w||0);},0);});
    var total=DATA.reduce(function(a,s){return a+s.tw;},0);
    if(total<=0)return;
    var sorted=DATA.slice().sort(function(a,b){return b.tw-a.tw;});
    var maxPct=sorted[0].tw/total*100;
    var groups={};
    var html='';
    sorted.forEach(function(s){
      var pct=s.tw/total*100,fillPct=pct/maxPct*100;
      var val=Math.round(s.tw/1000)+'k'+String.fromCharCode(8364);
      html+='<div class="sb-row" data-sec="'+s.name+'" tabindex="0">'
        +'<div class="sb-row-name"><span class="sb-row-dot" style="background:'+s.col+'"></span><span class="sb-row-label">'+s.name+'</span></div>'
        +'<div class="sb-row-bar"><div class="sb-row-fill" style="width:'+fillPct.toFixed(1)+'%;background:'+s.col+'"></div></div>'
        +'<div class="sb-row-pct">'+pct.toFixed(1)+'%</div>'
        +'<div class="sb-row-val">'+val+'</div>'
        +'</div>';
    });
    BARS.innerHTML=html;
    BARS.querySelectorAll('.sb-row').forEach(function(r){
      groups[r.dataset.sec]=r;
      r.addEventListener('click',function(){showSector(r.dataset.sec);});
      r.addEventListener('keydown',function(e){if(e.key==='Enter')showSector(r.dataset.sec);});
    });
    var n=sorted.length;
    function pv(p){return p==null?'&mdash;':((p>=0?'+':'')+p+'%');}
    function rw(l,v,c){return '<div style="display:flex;justify-content:space-between;padding:var(--s15) 0;border-bottom:.5px solid var(--line)"><span style="color:var(--steel)">'+l+'</span><span class="mono" style="color:'+(c||'var(--ink)')+'">'+v+'</span></div>';}
    function overview(){
      for(var k in groups){groups[k].classList.remove('on');groups[k].classList.remove('dim');}
      var top=sorted[0],tp=Math.round(top.tw/total*100),ov=tp>=30;
      PANEL.innerHTML='<div style="font-family:var(--fb);font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--steel);margin-bottom:var(--s25)">Vue d&rsquo;ensemble</div>'
        +rw('Plus gros secteur',top.name+' &middot; '+tp+'%',ov?'var(--bear)':'var(--acc)')
        +rw('Lignes total',DATA.reduce(function(a,s){return a+s.t.length;},0)+'')
        +'<div style="margin-top:var(--s3);font-size:12px;color:'+(ov?'var(--warn)':'var(--steel)')+'">'+(ov?('&#9888; '+top.name+' au-dessus du plafond 30%'):'sous le plafond 30%')+'</div>'
        +'<div style="margin-top:var(--s35);font-size:11px;color:var(--steel)">clique un secteur pour voir ses lignes</div>';
    }
    function showSector(name){
      var s=null;DATA.forEach(function(d){if(d.name===name)s=d;});if(!s)return;
      for(var k in groups){if(k===name){groups[k].classList.add('on');groups[k].classList.remove('dim');}else{groups[k].classList.remove('on');groups[k].classList.add('dim');}}
      var rows=s.t.slice().sort(function(a,b){return b.w-a.w;}).map(function(x){var pc=x.pnl==null?'var(--steel)':(x.pnl>=0?'var(--acc)':'var(--bear)');return '<div class="sbrow" data-tk="'+x.tk+'"><span class="mono">'+x.tk+'</span><span style="display:flex;gap:var(--s3);align-items:center"><span class="mono" style="width:48px;text-align:right;color:'+pc+'">'+pv(x.pnl)+'</span><span class="mono" style="color:var(--steel);font-size:11px">stop '+(x.down==null?'&mdash;':x.down+'%')+'</span></span></div>';}).join('');
      PANEL.innerHTML='<div class="sb-back" style="cursor:pointer;color:var(--steel);font-size:11px;margin-bottom:var(--s2)">&larr; vue d&rsquo;ensemble</div><div style="display:flex;align-items:center;gap:var(--s2);margin-bottom:var(--s25)"><span style="width:10px;height:10px;border-radius:2px;background:'+s.col+'"></span><span style="font-family:var(--fd);font-weight:500;font-size:13px">'+s.name+'</span><span class="mono" style="color:var(--steel);font-size:12px">'+Math.round(s.tw/total*100)+'% &middot; '+s.t.length+' lignes</span></div>'+rows+'<div style="margin-top:var(--s25);font-size:11px;color:var(--steel)">clique un titre pour sa fiche</div>';
    }
    PANEL.addEventListener('click',function(e){if(e.target.closest&&e.target.closest('.sb-back'))overview();});
    overview();
  })();
  document.addEventListener('click',function(ev){
    var r=ev.target.closest&&ev.target.closest('[data-tk]'); if(r&&r.dataset.tk){ openLoupe(r.dataset.tk); }
    if(ev.target.id==='loupe'){ closeLoupe(); }
  });
  document.addEventListener('keydown',function(ev){ if(ev.key==='Escape')closeLoupe(); });
  (function(){
    var box=document.createElement('div');box.id='qsearch';box.className='qs';
    box.innerHTML='<div class="qs-card"><input id="qs-input" type="text" aria-label="Rechercher un titre ou un nom" placeholder="Rechercher un titre ou un nom..." autocomplete="off"><div id="qs-res"></div></div>';
    document.body.appendChild(box);
    var inp=box.querySelector('#qs-input'),res=box.querySelector('#qs-res'),sel=0,cur=[];
    var rk={held:0,watch:1,core:2,extended:3,out:4};
    function lab(st){return {held:'d&eacute;tenu',watch:'watch',core:'core',extended:'&eacute;tendu'}[st]||'hors-univers';}
    function openQS(){box.classList.add('open');inp.value='';qrender('');setTimeout(function(){inp.focus();},30);}
    function closeQS(){box.classList.remove('open');}
    function qrender(q){
      var TK=window.TK||{},ql=q.trim().toLowerCase(),out=[];
      for(var tk in TK){var d=TK[tk],nm=(d.name||'').toLowerCase();
        if(!ql||tk.toLowerCase().indexOf(ql)>=0||nm.indexOf(ql)>=0){out.push([tk,d]);}}
      out.sort(function(a,b){return (rk[a[1].status]||9)-(rk[b[1].status]||9);});
      cur=out.slice(0,8);sel=0;
      res.innerHTML=cur.length?cur.map(function(e,i){var d=e[1];
        return '<div class="qs-row'+(i===0?' on':'')+'" data-qtk="'+e[0]+'"><span class="qs-tk">'+e[0]+'</span><span class="qs-nm">'+(d.name||'')+'</span><span class="qs-st '+(d.status||'out')+'">'+lab(d.status||'out')+'</span></div>';
      }).join(''):'<div class="qs-empty">aucun titre</div>';
    }
    function pick(tk){if(!tk)return;closeQS();openLoupe(tk);}
    function hi(){var rows=res.querySelectorAll('.qs-row');for(var i=0;i<rows.length;i++){rows[i].classList.toggle('on',i===sel);}}
    inp.addEventListener('input',function(){qrender(inp.value);});
    res.addEventListener('click',function(e){var r=e.target.closest('.qs-row');if(r)pick(r.dataset.qtk);});
    box.addEventListener('click',function(e){if(e.target===box)closeQS();});
    document.addEventListener('keydown',function(e){
      if((e.metaKey||e.ctrlKey)&&(e.key==='k'||e.key==='K')){e.preventDefault();box.classList.contains('open')?closeQS():openQS();return;}
      if(!box.classList.contains('open'))return;
      if(e.key==='Escape'){closeQS();}
      else if(e.key==='ArrowDown'){e.preventDefault();sel=Math.min(cur.length-1,sel+1);hi();}
      else if(e.key==='ArrowUp'){e.preventDefault();sel=Math.max(0,sel-1);hi();}
      else if(e.key==='Enter'){e.preventDefault();if(cur[sel])pick(cur[sel][0]);}
    });
  })();
  (function(){
    try{var sy=sessionStorage.getItem('h_scroll');if(sy)window.scrollTo(0,parseFloat(sy)||0);}catch(e){}
    var lastAct=Date.now();
    ['mousemove','keydown','touchstart','wheel'].forEach(function(ev){document.addEventListener(ev,function(){lastAct=Date.now();},{passive:true});});
    setInterval(function(){
      var lp=document.getElementById('loupe');
      if(lp&&lp.classList.contains('open'))return;
      if(document.hidden)return;
      if(Date.now()-lastAct<6000)return;
      try{sessionStorage.setItem('h_scroll',String(window.scrollY||window.pageYOffset||0));}catch(e){}
      void 0;  /* auto-reload navigateur retire -- rafraichir avec Cmd+R */
    },75000);
  })();
"""


_PERF_CACHE: dict = {}
_PERF_TTL = 840


def _perf_dwm(ticker: str) -> dict:
    # % jour / semaine / mois depuis closes journaliers (1 appel yfinance, cache TTL).
    import time

    now = time.monotonic()
    hit = _PERF_CACHE.get(ticker)
    if hit and now - hit[0] < _PERF_TTL:
        return hit[1]
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
            scores, regime, narr = {}, "", []
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
            "sector": sectors.get(tk, "Sans th&egrave;se"),
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
            "sector": sectors.get(tk, "Sans th&egrave;se"),
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


_LOUPE_HTML = (
    '<div id="loupe" class="loupe"><div class="loupe-card">'
    '<button class="loupe-x" onclick="closeLoupe()" aria-label="Fermer">&times;</button>'
    '<div id="loupe-body"></div></div></div>'
)


_EU_SUFFIX = (
    ".PA",
    ".AS",
    ".DE",
    ".MI",
    ".ST",
    ".BR",
    ".MC",
    ".SW",
    ".VI",
    ".HE",
    ".CO",
    ".OL",
    ".LS",
    ".L",
    ".F",
    ".PL",
    ".WA",
    ".AT",
)


def _broker(tk: str) -> str:
    return "bourso" if tk.endswith(_EU_SUFFIX) else "tr"


def _broker_value(p: dict, pnl: dict) -> float:  # noqa: ARG001
    return p["weight"]  # market value post-migration


def _sector_mix(ps: list, pnl: dict, sectors: dict) -> list:
    agg: dict[str, float] = {}
    for p in ps:
        sec = sectors.get(p["ticker"], "Sans th&egrave;se")
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
    - ratio >= 3.0  -> 'barbell' (asymetrie favorable, laisser courir) -> .acc (olive)
    - 1.0 <= r < 3.0 -> 'modere' (neutre) -> .num (ink2)
    - r < 1.0       -> 'inverse' (downside > upside, candidate trim) -> .neg (oxblood)
    - None          -> '—'
    """
    if ratio is None:
        return ('num', '&mdash;')
    if ratio >= 3.0:
        return ('num acc', f'{ratio:.1f}&times;')
    if ratio >= 1.0:
        return ('num', f'{ratio:.1f}&times;')
    return ('num neg', f'{ratio:.1f}&times;')


def _broker_one(label: str, note: str, ps: list, grand: float, names: dict, pnl: dict, sectors: dict, asym: dict) -> str:
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
        rows += (
            f'<tr data-tk="{tk}" data-v="{v:.2f}" data-w="{w:.2f}" data-p="{pc if pc is not None else -9999}"><td class="tk">{_ticker_logo(tk)}{tk}<span class="nm">{nm}</span></td>'
            f'<td class="num mono">{vstr}&nbsp;&euro;</td><td class="num">{w:.1f}%</td>'
            f'<td class="num {pcls}">{pstr}</td>'
            f'<td class="{asym_cls}">{asym_str}</td></tr>'
        )
    if not ps:
        rows = '<tr><td class="empty" colspan="5" style="padding:var(--s4) 0">aucune ligne</td></tr>'
    tot_str = f"{tot:,.0f}".replace(",", "&#8239;")
    donut = _sector_donut(_sector_mix(ps, pnl, sectors)) if ps else ""
    return (
        f'<div class="brk"><div class="brk-h"><div><span class="brk-n">{label}</span>'
        f'<span class="brk-note">{note}</span></div>'
        f'<div class="brk-tot">{tot_str}&nbsp;&euro; <span>&middot; {len(ps)} lignes &middot; {share:.0f}% du total</span></div></div>'
        f'<div class="brk-body">{donut}<div class="brk-tbl"><div class="card pad" style="padding:var(--s1) 18px"><table class="dt"><thead><tr><th>Ligne</th>'
        f'<th class="num">Valeur</th><th class="num">Poids</th><th class="num">P&amp;L</th>'
        f'<th class="num" title="upside_to_target / downside_to_stop. >3 = barbell (laisser courir). <1 = inverse (candidate trim).">Asym&eacute;trie</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div></div></div></div>"
    )


def _broker_tables(positions: list[dict], names: dict, pnl: dict, sectors: dict) -> str:
    grand = sum(_broker_value(p, pnl) for p in positions) or 1
    # Fetch asymmetry par ticker (cf intelligence/asymmetry.py compute_portfolio_asymmetry)
    asym = {}
    try:
        asym_results = asym_mod.compute_portfolio_asymmetry()
        for r in asym_results:
            tk = r.get("ticker")
            if tk and r.get("asymmetry_ratio") is not None:
                asym[tk] = r["asymmetry_ratio"]
    except Exception:
        pass  # self-disable si calcul fail, fallback "—" affiche
    tr = [p for p in positions if _broker(p["ticker"]) == "tr"]
    eu = [p for p in positions if _broker(p["ticker"]) == "bourso"]
    head = (
        '<div class="colhead tight"><span class="t">Comptes</span>'
        '<span class="a">par courtier &middot; tri&eacute; par valeur &middot; '
        'asym&eacute;trie = upside_to_target / downside_to_stop (Taleb barbell)</span></div>'
    )
    return (
        head
        + _broker_one("Trade Republic", "hors Europe", tr, grand, names, pnl, sectors, asym)
        + _broker_one("Boursorama", "PEA &middot; Europe", eu, grand, names, pnl, sectors, asym)
    )


_MODE_BTN = """<button class="modetgl" title="Mode jour / nuit" aria-label="Basculer mode jour / nuit" onclick="document.body.classList.toggle('midnight');try{localStorage.setItem('hmdl-theme',document.body.classList.contains('midnight')?'midnight':'parchment')}catch(e){}"><svg class="ico-sun" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg><svg class="ico-moon" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button>"""
_THEME_INIT = (
    "<script>"
    "try{"
    "var t=localStorage.getItem('hmdl-theme');"
    "if(t==='midnight'){document.body.classList.add('midnight');}"
    "else if(t==='parchment'){/* explicit light, ne rien faire */}"
    "else if(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches){"
    "document.body.classList.add('midnight');"
    "}"
    "}catch(e){}"
    "</script>"
)


_SORT_JS = """<script>document.addEventListener('DOMContentLoaded',function(){
document.querySelectorAll('table.dt').forEach(function(t){
  var tb=t.tBodies[0]; if(!tb) return;
  var dir={};
  t.querySelectorAll('thead th').forEach(function(th,ci){
    var key={0:'tk',1:'v',2:'w',3:'p'}[ci]; if(!key) return;
    th.style.cursor='pointer';
    th.addEventListener('click',function(){
      var num=key!=='tk', d=dir[ci]=-(dir[ci]||1);
      var rows=[].slice.call(tb.rows).filter(function(r){return r.hasAttribute('data-'+key);});
      rows.sort(function(a,b){
        var x=a.getAttribute('data-'+key), y=b.getAttribute('data-'+key);
        if(num){return (parseFloat(x)-parseFloat(y))*d;}
        return x<y?-d:(x>y?d:0);
      });
      rows.forEach(function(r){tb.appendChild(r);});
      t.querySelectorAll('thead th').forEach(function(h){h.removeAttribute('aria-sort');});
      th.setAttribute('aria-sort',d<0?'descending':'ascending');
    });
  });
});
});</script>"""


_DONUT_JS = ""  # legacy slot — tooltips no longer needed (info inline in .brk-row)

_CSORT_JS = """<script>document.addEventListener('DOMContentLoaded',function(){
document.querySelectorAll('.sec-cols').forEach(function(hdr){
  var root=hdr.parentElement, map={1:'w',2:'w',3:'pct',4:'dv',5:'pl'}, dir={};
  hdr.querySelectorAll('span').forEach(function(sp,ci){
    var key=map[ci]; if(!key) return;
    sp.style.cursor='pointer';
    sp.addEventListener('click',function(){
      var d=dir[ci]=-(dir[ci]||1);
      root.querySelectorAll('.sec-rows').forEach(function(box){
        var rows=[].slice.call(box.children).filter(function(r){return r.classList.contains('sec-row');});
        rows.sort(function(a,b){return (parseFloat(a.getAttribute('data-'+key))-parseFloat(b.getAttribute('data-'+key)))*d;});
        rows.forEach(function(r){box.appendChild(r);});
      });
    });
  });
});
});</script>"""


_DBA_CSS = r"""
<style>
  .dba-sh { font-family:var(--fb); font-size:13px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin: var(--s5) 2px var(--s2); display:flex; align-items:baseline; gap:var(--s3); }
  .dba-sh::after { content:""; flex:1; height:1px; background:var(--line); }
  .dba-sh-aside { text-transform:none; letter-spacing:0; color:var(--steel); font-weight:normal; font-size:11px; margin-left:6px; }
  .dba-card { padding: var(--s4); border:1px solid var(--line); border-radius:var(--r3); background:color-mix(in srgb,var(--ink) 1.2%, transparent); margin-bottom:var(--s3); }
  .dba-chrow { display:flex; justify-content:space-between; align-items:baseline; gap:var(--s4); font-family:var(--fm); }
  .dba-chrow .lab { font-weight:600; color:var(--ink); font-size:13px; }
  .dba-chrow .stat { font-size:11px; letter-spacing:.06em; text-transform:uppercase; padding:2px 9px; border-radius:var(--r1); border:1px solid var(--line); white-space:nowrap; }
  .dba-chrow .stat.actif { color:var(--acc); border-color:color-mix(in srgb, var(--acc) 30%, var(--line)); }
  .dba-chrow .stat.veille { color:var(--warn); border-color:color-mix(in srgb, var(--warn) 30%, var(--line)); }
  .dba-chrow .stat.non-inst { color:var(--steel); opacity:.7; }
  .dba-meta { font-family:var(--fm); font-size:11px; color:var(--steel); margin-top:6px; line-height:1.5; }
  .dba-bars { margin-top:var(--s3); }
  /* Bars : couleur = SEVERITE (etat), pas presence. Label + count
     portent la couleur ; la fill l'amplifie. Row a 0 reste typee. */
  .dba-hbar { display:flex; align-items:center; gap:11px; font-family:var(--fm); font-size:12px; margin:6px 0; }
  .dba-hbar.zero { opacity:.55; }
  .dba-hlab { width:80px; }
  .dba-haxis { flex:1; height:6px; background:color-mix(in srgb, var(--steel) 12%, transparent); border-radius:3px; overflow:hidden; }
  .dba-hfill { height:100%; background:var(--steel); }
  .dba-hn { width:30px; text-align:right; font-weight:600; }
  .dba-hbar.dormant .dba-hlab,
  .dba-hbar.dormant .dba-hn { color:var(--steel); }
  .dba-hbar.dormant .dba-hfill { background:var(--steel); }
  .dba-hbar.at_risk .dba-hlab,
  .dba-hbar.at_risk .dba-hn { color:var(--warn); font-weight:700; }
  .dba-hbar.at_risk .dba-hfill { background:var(--warn); }
  .dba-hbar.triggered .dba-hlab,
  .dba-hbar.triggered .dba-hn { color:var(--bear); font-weight:700; }
  .dba-hbar.triggered .dba-hfill { background:var(--bear); }
  .dba-count { font-family:var(--fm); font-size:14px; color:var(--ink); margin-top:var(--s2); font-weight:600; }
  .dba-tags { display:flex; flex-wrap:wrap; gap:6px; margin-top:6px; }
  .dba-tag { font-family:var(--fm); font-size:11px; padding:2px 8px; border-radius:var(--r1); background:color-mix(in srgb, var(--steel) 10%, transparent); color:var(--steel); }
  .dba-cond { font-family:var(--fm); font-size:11px; color:var(--steel); margin-top:8px; font-style:italic; }
  .dba-honest { font-family:var(--fm); font-size:11px; color:var(--warn); margin-top:8px; padding:7px 11px; background:color-mix(in srgb, var(--warn) 6%, transparent); border-left:2px solid var(--warn); border-radius:var(--r1); line-height:1.5; }
  .dba-arrow { font-family:var(--fm); font-size:12px; color:var(--steel); margin-top:var(--s3); }
  .dba-arrow .v { color:var(--ink); font-weight:600; }
</style>
"""


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
        return '<div class="dba-meta">Brier : aucune pr&eacute;diction r&eacute;solue &agrave; mesurer</div>'
    if brier_n < 10:
        return (f'<div class="dba-meta">Brier : N={brier_n} '
                f'(insuffisant &mdash; seuil meaningful N&ge;10)</div>')
    return (
        f'<div class="dba-meta">Brier moyen : {brier_avg:.3f} sur N={brier_n} '
        f'&middot; vs 0.25 (pr&eacute;dicteur constante 0.5, baseline le plus faible)</div>'
        f'<div class="dba-honest">Cohorte V1 fig&eacute;e (probability_at_creation = '
        f'snapshot cr&eacute;dibilit&eacute; source &asymp; 0.5). Battre 0.25 ne d&eacute;montre '
        f'pas un skill &mdash; juste une am&eacute;lioration sur le pr&eacute;dicteur le plus '
        f'b&ecirc;te. Vraie calibration V2 = post-ao&ucirc;t (N V2 suffisant + comparaison '
        f'au pr&eacute;dicteur taux-de-base).</div>'
    )


def _discipline_biais_panel() -> str:
    """Pile 1.1 -- surface de la mission PRESAGE (compteur disciplines + biais).
    Etat honnete-tot (user 01/06) : afficher creux + raisons. Conformite
    lexique etat-de-canal cf docs/GLOSSARY.md sect 'Etat de canal d'instrumentation'.
    Densite reelle viendra a J+30 quand les premiers biais se resolvent."""

    # Predictions cluster KPI #2 -- batch 10/06 specifique : V1 dont
    # target_date <= 2026-06-10. User 01/06 critique : la query precedente
    # comptait TOUTES les V1 resolues, biais vers "5 du cluster" alors qu'aucune
    # n'est du batch 10/06. Cluster cible = 35 predictions a J-day.
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
    # pas dernier run cron. Libelle reformule pour la verite.
    last_trans = _q("SELECT MAX(created_at) FROM kill_criteria_alerts")[0][0]
    last_trans_str = last_trans[:16].replace("T", " ") if last_trans else "aucune"

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
            try:
                cls = classify_position(ln["ticker"], lines, convs, caps)
                if cls and cls["status"] == "over":
                    over_tk.append(ln["ticker"])
            except MissingDataError:
                pass
        book_total_eur = sum((ln.get("weight") or 0) for ln in lines)
    except Exception:
        over_tk = []
        book_total_eur = 0

    over_tags_html = (
        '<div class="dba-tags">'
        + "".join(f'<span class="dba-tag">{t}</span>' for t in over_tk)
        + "</div>"
    ) if over_tk else ""

    pred_marker = "&#10003;" if n_resolved >= 5 else "&#9675;"

    return (
        '<section data-page="discipline" role="region" aria-label="Discipline et Biais">'
        + _DBA_CSS
        + '<div class="phead"><h2>Discipline &amp; Biais</h2>'
        '<div class="sub">Compteur de la mission : pr&eacute;dictions calibr&eacute;es '
        '+ biais comportementaux m&eacute;canis&eacute;s. &Eacute;tat honn&ecirc;te, '
        'densit&eacute; &agrave; J+30.</div></div>'
        # ─── PREDICTIONS ─────────────────────────────────────────────────
        '<div class="dba-sh">Pr&eacute;dictions'
        '<span class="dba-sh-aside">cluster KPI #2 &mdash; J+28 batch 10/06</span></div>'
        '<div class="dba-card">'
        f'<div class="dba-chrow"><span class="lab">{n_resolved}/{n_cluster_total} '
        f'r&eacute;solues &middot; KPI #2 &ge;5 {pred_marker}</span>'
        '<span class="stat actif">actif</span></div>'
        f'{_dba_predictions_brier_html(brier_avg, brier_n)}'
        '</div>'
        # ─── BIAIS fomo_greed ────────────────────────────────────────────
        '<div class="dba-sh">Biais &mdash; fomo_greed'
        '<span class="dba-sh-aside">tenir au-del&agrave; du top &middot; 2 canaux instrument&eacute;s</span></div>'
        # Canal kill_criteria
        '<div class="dba-card">'
        '<div class="dba-chrow"><span class="lab">kill_criteria</span>'
        '<span class="stat actif">actif</span></div>'
        f'<div class="dba-meta">{n_active_theses} th&egrave;ses surveill&eacute;es '
        f'(monitoring quotidien) &middot; derni&egrave;re transition '
        f'enregistr&eacute;e {last_trans_str}</div>'
        '<div class="dba-bars">'
        + _dba_bar("dormant", kca_dormant, kca_total)
        + _dba_bar("at_risk", kca_at_risk, kca_total)
        + _dba_bar("triggered", kca_triggered, kca_total)
        + '</div>'
        f'<div class="dba-arrow">&rsaquo; <span class="v">{n_bias_open}</span> '
        f'candidat{"s" if n_bias_open != 1 else ""} ouvert{"s" if n_bias_open != 1 else ""} '
        f'&middot; <span class="v">{n_bias_resolved}</span> '
        f'r&eacute;solu{"s" if n_bias_resolved != 1 else ""}</div>'
        '</div>'
        # Canal over_cap
        '<div class="dba-card">'
        '<div class="dba-chrow"><span class="lab">over_cap</span>'
        '<span class="stat veille">en veille (par d&eacute;cision)</span></div>'
        f'<div class="dba-meta">Book {_dba_eur(book_total_eur)}&nbsp;&euro; &rarr; '
        f'{_dba_eur(70180)}&nbsp;&euro; cible &middot; phase construction</div>'
        f'<div class="dba-count">{len(over_tk)} OVER d&eacute;tect&eacute;'
        f'{"s" if len(over_tk) != 1 else ""} actuellement</div>'
        f'{over_tags_html}'
        '<div class="dba-honest">Marginaux : tous repassent sous leur cap &agrave; '
        '70&nbsp;k = artefacts du d&eacute;nominateur, pas sur-concentration r&eacute;elle. '
        'Firer maintenant = mesurer une discipline qui n\'a pas dit &laquo;&nbsp;trimme&nbsp;&raquo;.</div>'
        '<div class="dba-cond">R&eacute;-activation : book &ge; 65&nbsp;k&euro; '
        'OU flag construction_phase lev&eacute;</div>'
        '<div class="dba-arrow">&rsaquo; <span class="v">0</span> candidat &eacute;mis '
        '&middot; r&eacute;solution N/A</div>'
        '</div>'
        # ─── BIAIS lock_in ──────────────────────────────────────────────
        '<div class="dba-sh">Biais &mdash; lock_in'
        '<span class="dba-sh-aside">vendre les gagnants trop t&ocirc;t</span></div>'
        '<div class="dba-card">'
        '<div class="dba-chrow">'
        '<span class="lab">Surface 2 &mdash; capture synchrone vente winner</span>'
        '<span class="stat non-inst">non instrument&eacute;</span></div>'
        '<div class="dba-meta">Chemin pr&eacute;vu par ADR-010 &sect;2. '
        'Pas de canal de capture aujourd\'hui &mdash; biais #1 de PRESAGE, &agrave; combler.</div>'
        '<div class="dba-cond">Pas de candidat capturable tant que ce chemin '
        'n\'est pas livr&eacute;.</div>'
        '</div>'
        '</section>'
    )


def render() -> Path:
    # Bug fix 31/05 wave 9b : asymmetry compare current vs stop_price/target_full.
    # Comme ces derniers sont stockes NATIVE (cf currency_native_invariant),
    # current doit etre NATIVE aussi pour des ratios FX-invariants. Ancien
    # patch vers _cached_price_eur produisait "Marges les plus faibles" avec
    # cible +175408% (000660.KS KRW vs current EUR).
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
        sb_secs.setdefault(sectors.get(p["ticker"], "Sans th&egrave;se"), []).append(
            {
                "tk": p["ticker"],
                "w": round(p["weight"]),
                "pnl": round(pnl[p["ticker"]], 1) if p["ticker"] in pnl else None,
                "down": round(sb_down[p["ticker"]], 1) if sb_down.get(p["ticker"]) is not None else None,
            }
        )
    sb_ordered = sorted(sb_secs.items(), key=lambda kv: (kv[0] == "Sans th&egrave;se", -sum(x["w"] for x in kv[1])))
    sb_data = [{"name": nm, "col": SECTOR_COLORS.get(nm, "#6B7686"), "t": rows} for nm, rows in sb_ordered]

    _ris, near, _heat, watch = _rows_risque(computed)
    gain, lose = _movers(pnl)
    day_up, day_dn = _day_movers(daily)
    _stamp = datetime.now().strftime("%d.%m.%Y &middot; %H:%M")
    today = datetime.now().strftime("%Y-%m-%d")
    erows = ""
    for rdate, rlab in sorted(REVIEWS):
        rpast = rdate < today
        rdd = f"{rdate[8:10]}.{rdate[5:7]}"
        rop = ' style="opacity:.45"' if rpast else ""
        rtag = " &middot; pass&eacute;e" if rpast else ""
        erows += f'<div class="line"{rop}><span>{rlab}{rtag}</span><span class="mono">{rdd}</span></div>'
    erows = erows or '<div class="empty" style="padding:var(--s35) 0">aucune &eacute;ch&eacute;ance</div>'

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
    vcls = "pos" if pf_pnl_eur >= 0 else "neg"
    pf_arrow = "&#9650;" if pf_pnl_eur >= 0 else "&#9660;"
    pf_val_str = f"{pf_value:,.0f}".replace(",", "&#8239;")
    pf_cost_str = f"{_pfcost:,.0f}".replace(",", "&#8239;")
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

    journal_html = _journal()
    journal_block = (
        (
            '<div class="colhead spaced"><span class="t">Derni&egrave;res d&eacute;cisions</span><span class="a">journal Telegram</span></div>'
            f'<div class="card pad">{journal_html}</div>'
        )
        if journal_html
        else ""
    )
    _axis: dict[str, dict[str, float]] = {}
    for r in computed:
        st, tg, c = r.get("stop") or 0, r.get("target_full") or 0, r.get("current_price") or 0
        up, dn = r.get("upside_pct"), r.get("downside_pct")
        if st and tg and tg != st and c and up is not None and dn is not None:
            _axis[r["ticker"]] = {"frac": max(0.0, min(100.0, (c - st) / (tg - st) * 100)), "up": up, "dn": dn}
    _cibles = sorted(_axis, key=lambda tk: -_axis[tk]["frac"])[:6]
    _stops = sorted(_axis, key=lambda tk: _axis[tk]["frac"])[:6]

    # F13 fix : "proche de la cible" n'est PAS une victoire mecanique. Si la
    # position est aussi fragile / valo > bull / solidite faible, atteindre
    # la cible = signal de prendre profit, pas la these qui marche. On surface
    # ce tag explicite sur chaque row qui meriterait un trim.
    try:
        from shared import book as _bk

        _book_idx = _bk.get_book_index()
    except Exception:
        _book_idx = {}

    def _axisrow(tk: str) -> str:
        a = _axis[tk]
        # Profit-take flag si frac > 80% AND (valo>bull OR solidite Fragile/Incertain)
        profit_chip = ""
        ln = _book_idx.get(tk)
        if ln and a["frac"] > 80:
            risky = ln.valo_above_bull_case or ln.solidite in ("Fragile", "Incertain")
            if risky:
                profit_chip = '<span class="th-pt">cible atteinte</span>'
        return (
            f'<div class="row" data-tk="{tk}"><div class="rt"><span class="tk">{tk}</span>{profit_chip}</div>'
            f'<div class="axis"><div class="axis-mark" style="left:{a["frac"]:.1f}%" title="{a["frac"]:.1f}%"></div></div>'
            f'<div class="th-ends"><span class="th-stop">stop &minus;{a["dn"]:.0f}%</span>'
            f'<span class="th-tgt">cible +{a["up"]:.0f}%</span></div></div>'
        )

    gain = "".join(_axisrow(tk) for tk in _cibles) or '<div class="empty" style="padding:var(--s4) 0">&mdash;</div>'
    lose = "".join(_axisrow(tk) for tk in _stops) or '<div class="empty" style="padding:var(--s4) 0">&mdash;</div>'
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
    axes_html = _ticker_axes_panel()
    factor_html = _factor_exposures_panel()
    stress_html = _stress_tests_panel()
    trajectory_html = _trajectory_panel()
    spof_html = _spof_panel()
    mauboussin_html = _mauboussin_sizing_panel()
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
    # Add CSS class .below-star au gradecard pour cacher la ghead duplicate
    _grade_html_below_star = grade_html.replace(
        'class="card pad gradecard"',
        'class="card pad gradecard below-star"',
    )
    vigie = (
        f'<section data-page="vigie" class="active" role="region" aria-label="Vue d&#39;ensemble"><div class="phead"><h2>Vue d\'ensemble</h2>'
        f'<div class="sub">Posture de discipline &middot; sur quoi agir aujourd&rsquo;hui</div></div>'
        # === Star Vue d'ensemble (unifie) : valeur+PnL+capital sous-jacent
        # a gauche, grade A+ + bar a droite. Strate 2 = repartition lignes
        # pleine largeur. Gradecard detail retire (vide visuel).
        + f'<div class="page-star">'
        + f'<div class="ps-strate">'
        + f'<div class="ps-hero-row">'
        + f'<div class="ps-hero-left">'
        + f'<div class="ps-lbl">Valeur du portefeuille</div>'
        + f'<div class="ps-macro-row" style="align-items:baseline">'
        + f'<div class="ps-val" style="font-size:34px">{pf_val_str}&nbsp;&euro;</div>'
        + f'<div class="ps-val {vcls}" style="font-size:18px">{pf_arrow}&nbsp;{pf_pe}&nbsp;&euro; ({"+" if port_pnl >= 0 else ""}{port_pnl:.1f}%)</div>'
        + f'</div>'
        + f'<div class="ps-sub-lien"><b class="acc">{gpct:.0f}%</b> en gain &middot; {n_gain} lignes &middot; {n_pnl - n_gain} en perte ({100 - gpct:.0f}%)</div>'
        + f'</div>'
        + f'<div class="ps-hero-right">'
        + f'<div class="ps-lbl">Note du portefeuille</div>'
        + f'<div class="ps-grade-row">'
        + f'<div class="ps-grade-letter acc">{_grade_letter}</div>'
        + f'<div class="ps-grade-score"><div class="ps-grade-num">{_grade_score}<span class="ps-grade-max">/100</span></div>'
        + f'<div class="ps-grade-bar"><div class="ps-grade-fill acc" style="width:{_grade_score:.0f}%"></div></div></div>'
        + f'</div></div>'
        + f'</div></div>'
        + f'<div class="ps-strate">'
        + f'<div class="ps-lbl">Capital investi</div>'
        + f'<div class="ps-macro-row" style="margin-top:4px"><div class="ps-val" style="font-size:22px">{pf_cost_str}&nbsp;&euro;</div>'
        + f'<div class="ps-macro-meta">{n_pnl} lignes &middot; snapshot {_grade_trend_str}</div></div>'
        + f'</div>'
        + f'</div>'
        # Track record + Sante distribution deplaces vers page "signaux"
        # (user feedback 01/06 : pilotage qualite des signaux groupe ensemble).
        # ── BLOC 1 : URGENCE -- positions en danger immediat ──
        # (kill_criteria_panel retire 31/05 user feedback, code backend conserve.
        # chat_html migre vers section Copilot dediee 31/05 wave 5)
        '<div class="vigie-sh">&Eacute;tat &mdash; lignes &agrave; examiner</div>'
        f'{_risk_watch_panel()}'
        f"{blind_html}"
        # ── BLOC 2 : OPPORTUNITES -- a cloturer ou consolider ──
        '<div class="vigie-sh">Opportunit&eacute;s &mdash; cl&ocirc;turer ou consolider</div>'
        f'<div class="cols"><div class="col"><div class="colhead"><span class="t">Plus proches de la cible</span><span class="a">th&egrave;se en cours de r&eacute;alisation &middot; surveiller valo &gt; bull et fragilit&eacute;</span></div>'
        f'<div class="card pad">{gain}</div></div><div class="col"><div class="colhead"><span class="t">Marges les plus faibles</span><span class="a">avant invalidation du stop</span></div>'
        f'<div class="card pad">{lose}</div></div></div>'
        # ── BLOC 3 : MOUVEMENT -- info dynamique du jour ──
        '<div class="vigie-sh">Mouvement du jour</div>'
        f'<div class="cols"><div class="col"><div class="colhead"><span class="t">Hausses du jour</span><span class="a">vs cl&ocirc;ture veille</span></div>'
        f'<div class="card pad">{day_up}</div></div><div class="col"><div class="colhead"><span class="t">Baisses du jour</span><span class="a">vs cl&ocirc;ture veille</span></div>'
        f'<div class="card pad">{day_dn}</div></div></div>'
        # ── BLOC 4 : SYNTHESE COPILOT (interventions adversariales) ──
        # (Retraits 31/05 user feedback : wire_activity / vigilance_v2 / v2_cohort /
        # calib_progress / cockpit / disc_hero -- code backend conserve, alertes Telegram
        # via cron weekly_v2_vigilance + weekly_calibration_audit prennent le relais)
        # Synthese copilot retiree 31/05 wave 5bis : migre vers section Copilot dediee.
        # ── BLOC 5 : JOURNAL -- echeances + log decisions (chat remonte au BLOC 1) ──
        '<div class="vigie-sh">Journal &amp; &eacute;ch&eacute;ances</div>'
        f'<div class="colhead tight"><span class="t">&Eacute;ch&eacute;ances &agrave; venir</span></div>'
        f'<div class="card pad">{erows}</div>'
        f"{journal_block}</section>"
    )

    # ─── Page Strategie : lecture analytique du book (vocabulaire canonique) ───
    # Refonte 31/05 user feedback : retire placement fiscal + chat_signals + conversations
    # Ordre : declaration -> etat -> risques caches -> meta (4 sections au lieu de 5)
    strategie_html = (
        '<section data-page="strategie" role="region" aria-label="Strategie"><div class="phead"><h2>Strat&eacute;gie</h2>'
        '<div class="sub">Lire le livre en profondeur &middot; pourquoi la note '
        'est ce qu\'elle est, et ou est la vraie fragilit&eacute;</div></div>'
        # 1. Strategie declaree -- referentiel (ce qu'on veut faire)
        '<div class="strat-sh">Strat&eacute;gie d&eacute;clar&eacute;e &mdash; r&eacute;f&eacute;rentiel</div>'
        f'{_user_strategy_panel()}'
        # 2. Lecture du livre -- etat actuel vs declare (trajectoire, paris macro, stress)
        # Retrait 31/05 user : bench_html (Surperformance reelle vs secteur)
        '<div class="strat-sh">Lecture du livre &mdash; &eacute;tat actuel</div>'
        f'{trajectory_html}'
        f'{factor_html}'
        f'{stress_html}'
        # 3. Risques caches -- fusion Concentration + Doublons (= ce que la surface cache)
        '<div class="strat-sh">Risques cach&eacute;s &mdash; concentration &amp; doublons</div>'
        f'{spof_html}'
        f'{mauboussin_html}'
        f'{valo_html}'
        f'{_return_clustering_panel()}'
        f'{axes_html}'
        # 4. Apprentissage du bot retire 31/05 wave 5 : conceptions migre vers
        # section Copilot dediee (avec chat + historique + signaux soft)
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
        f"VIX {_vix_p:.1f} {'&ge;' if _reduced_p else '&lt;'} {_vthr_p:.0f} (r&egrave;gle VIX seule)"
        if _vix_p else "VIX indisponible"
    )
    n_stop, n_watch, n_tgt = len(near_stop_tk), len(watch_zone_tk), len(near_tgt_tk)
    if n_stop:
        _post_cls, _post_lbl = "bear", "VIGILANCE"
        _post_cap = f"{n_stop} ligne(s) au stop &lt; 10% &middot; v&eacute;rifier avant la s&eacute;ance"
    elif n_watch:
        _post_cls, _post_lbl = "warn", "SURVEILLANCE"
        _post_cap = f"{n_watch} ligne(s) en zone 10-20% du stop &middot; marge restante"
    elif n_tgt:
        _post_cls, _post_lbl = "acc", "PRISE&nbsp;DE&nbsp;PROFIT"
        _post_cap = f"{n_tgt} ligne(s) proche(s) d&rsquo;un palier"
    else:
        _post_cls, _post_lbl = "acc", "AU&nbsp;REPOS"
        _post_cap = "aucune ligne en zone critique &middot; surveiller la d&eacute;rive"
    _star_stop_cls = "bear" if n_stop else "acc"
    _star_watch_cls = "warn" if n_watch else "acc"
    _star_tgt_cls = "warn" if n_tgt else "acc"
    star_strate_post = (
        '<div class="ps-strate">'
        + '<div class="ps-lbl">Posture positions</div>'
        + '<div class="ps-macro-row">'
        + f'<div class="ps-val {_post_cls}">{_post_lbl}</div>'
        + f'<div class="ps-macro-meta">{len(positions)} lignes &middot; sizing &times;{_sfac:.1f}</div>'
        + "</div>"
        + f'<div class="ps-cap">{_post_cap}</div>'
        + "</div>"
    )
    _stop_caption = (", ".join(near_stop_tk[:3]) + ("…" if len(near_stop_tk) > 3 else "")) if near_stop_tk else "aucune"
    _watch_caption = (", ".join(watch_zone_tk[:3]) + ("…" if len(watch_zone_tk) > 3 else "")) if watch_zone_tk else "aucune"
    _tgt_caption = (", ".join(near_tgt_tk[:3]) + ("…" if len(near_tgt_tk) > 3 else "")) if near_tgt_tk else "aucune"
    star_strate_grid = (
        '<div class="ps-strate ps-grid">'
        + f'<div class="ps-cell"><div class="ps-lbl">Au stop &lt;10%</div><div class="ps-val {_star_stop_cls}">{n_stop}</div><div class="ps-cap">{_stop_caption}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl">Surveillance 10-20%</div><div class="ps-val {_star_watch_cls}">{n_watch}</div><div class="ps-cap">{_watch_caption}</div></div>'
        + f'<div class="ps-cell"><div class="ps-lbl">Proche cible</div><div class="ps-val {_star_tgt_cls}">{n_tgt}</div><div class="ps-cap">{_tgt_caption}</div></div>'
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
        f'<div class="sub">Marge &agrave; la hausse vers la cible &middot; &agrave; la baisse vers le stop</div></div>'
        f"{star_positions}{broker_html}</section>"
    )

    # --- Bandeau d'ecart de discipline (sticky, haut de page) ---
    # v1: axe concentration (cluster hors plafond, source unique _cluster_health) + axe stop (near).
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
                (f"all&eacute;ger {_c['name']} &middot; +{_ov}&#8239;&euro;", "concentration")
            )
    if near:
        _dev_items.append((f"{near} ligne(s) &lt; 10% du stop", "risque"))
    _dn = len(_dev_items)
    _dcls, _dverdict = ("bear", "FRICTIONS") if _dn else ("acc", "ALIGN&Eacute;")
    _ddetail = (
        " &nbsp;&middot;&nbsp; ".join(item[0] for item in _dev_items)
        if _dev_items else "tout sous les r&egrave;gles"
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
        if _dev_items else "aucune friction de discipline"
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
        + _discipline_biais_panel()
        + positions_pg
        + _copilot()
        + _theses(names, sectors, positions, pnl)
        + strategie_html
        + _concentration(positions, planned, sectors, names, pnl, daily)
        + _signaux()
        + _urgence(watch, near, positions, pnl, elan, near_t)
        + "</main></div>"
        + _LOUPE_HTML
    )

    html = (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta http-equiv="refresh" content="1800">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><script>try{if(sessionStorage.getItem("h_seen"))document.documentElement.classList.add("noanim");sessionStorage.setItem("h_seen","1");}catch(e){}</script><title>PRESAGE</title><link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg%20viewBox%3D%220%200%2064%2064%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%3E%3Crect%20width%3D%2264%22%20height%3D%2264%22%20rx%3D%2214%22%20fill%3D%22%230c0c0e%22%2F%3E%3Cg%20transform%3D%22translate%288.00%2C19.57%29%20scale%280.13079%29%22%20fill%3D%22%23ECEFF4%22%3E%3Cg%20transform%3D%22translate%280.000000%2C190.000000%29%20scale%280.100000%2C-0.100000%29%22%20%20stroke%3D%22none%22%3E%20%3Cpath%20d%3D%22M1335%201890%20c-11%20-4%20-200%20-189%20-419%20-409%20l-399%20-401%20251%200%20250%200%20254%20260%20253%20260%2071%200%2071%200%2058%20-62%20c32%20-35%20168%20-174%20301%20-309%20l242%20-246%2069%20-7%20c37%20-4%20148%20-11%20246%20-16%2098%20-4%20181%20-11%20184%20-14%204%20-3%20-45%20-6%20-108%20-6%20-63%200%20-175%20-5%20-249%20-10%20l-135%20-11%20-72%20-72%20c-40%20-39%20-73%20-76%20-73%20-82%200%20-6%2051%20-61%20114%20-124%20l113%20-113%20184%20187%20184%20186%20330%209%20c182%205%20394%209%20473%2010%20l142%200%200%2030%200%2030%20-127%201%20c-71%201%20-284%204%20-474%207%20l-346%207%20-87%2082%20c-47%2045%20-126%20129%20-175%20186%20-131%20153%20-581%20617%20-609%20628%20-29%2011%20-490%2011%20-517%20-1z%22%2F%3E%20%3Cpath%20d%3D%22M2308%201888%20c-9%20-7%20-26%20-33%20-37%20-58%20-12%20-25%20-44%20-68%20-72%20-97%20l-51%20-52%20105%20-108%20105%20-107%2064%2067%2063%2067%2072%200%2071%200%20253%20-260%20252%20-260%20244%200%20c238%200%20244%200%20231%2019%20-23%2032%20-760%20775%20-782%20788%20-30%2018%20-496%2018%20-518%201z%22%2F%3E%20%3Cpath%20d%3D%22M1693%201259%20c-54%20-61%20-109%20-127%20-123%20-145%20-14%20-19%20-51%20-54%20-83%20-78%20l-58%20-43%20-487%20-7%20c-268%20-3%20-589%20-9%20-715%20-13%20-207%20-5%20-227%20-7%20-227%20-23%200%20-16%2024%20-18%20298%20-24%20163%20-4%20488%20-11%20721%20-17%20l424%20-10%2061%20-44%20c89%20-63%20148%20-125%20236%20-250%2053%20-75%20150%20-184%20305%20-345%20125%20-129%20237%20-240%20249%20-247%2015%20-9%2095%20-12%20276%20-13%20l254%200%20411%20410%20410%20410%20-245%200%20-245%200%20-255%20-255%20-255%20-255%20-81%200%20-80%200%20-244%20253%20c-309%20320%20-340%20349%20-388%20353%20-20%201%20-91%208%20-157%2013%20-66%206%20-176%2011%20-245%2012%20-149%202%20-118%2016%2039%2018%2056%200%20169%206%20250%2012%20l146%2011%2073%2071%20c39%2040%2071%2075%2070%2079%20-5%2013%20-221%20238%20-229%20238%20-4%200%20-52%20-50%20-106%20-111z%22%2F%3E%20%3Cpath%20d%3D%22M715%20618%20c110%20-112%20290%20-295%20402%20-408%20l202%20-205%20161%20-3%20c182%20-4%20206%203%20285%2077%2052%2049%20126%2093%20193%20115%20l54%2018%20-112%20112%20-111%20111%20-58%20-62%20-57%20-63%20-81%200%20-80%200%20-176%20178%20c-96%2097%20-208%20212%20-247%20255%20l-72%2077%20-251%200%20-251%200%20199%20-202z%22%2F%3E%20%3C%2Fg%3E%3C%2Fg%3E%3C%2Fsvg%3E">'
        ""
        # Geist auto-hosted depuis dashboard/static/fonts/ (cf tokens.css
        # @font-face block). Pas de CDN Google Fonts (zero round-trip externe,
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
        # 01/06 user feedback : Compact aucun interet, Filtrer pas de utilite plug)
        + '<div class="cta-bar" role="toolbar" aria-label="Recherche rapide">'
        + '<button id="ctaSearch" title="Rechercher (Cmd+K)"><span aria-hidden="true">&#9906;</span> Rechercher <kbd>&#8984;K</kbd></button>'
        + "</div>"
        + '<div class="cta-modal" id="ctaSearchModal" role="dialog" aria-modal="true" aria-label="Recherche ticker">'
        + '<div class="cta-modal-inner">'
        + '<input class="cta-search-input" id="ctaSearchInput" placeholder="Ticker ou nom de societe..." autocomplete="off" spellcheck="false" />'
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
