"""Heimdall — Sentinel dashboard. Static-gen, READ-ONLY, REAL data.
Weights from positions.eur_invested (EUR cost basis). Sectors from theses.sector_thesis_id.
Perf as ratio % (currency-invariant). DB read-only; per-panel try/except. Leaflet geo."""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import yaml

from intelligence import asymmetry as asym_mod

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
    """Source de prix du dashboard: throttle les fetchs live a un burst par TTL.

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
}


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
        else:
            g = _grade.compute_grade()
            grade_letter = g["overall_grade"]
            score = g["overall_score"]
            dims = g["dimensions"]
            snapshot_date = g["snapshot_date"]
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

    def _build_rows(keys: list[str]) -> str:
        rows = []
        for dk in keys:
            label, kind, _ = _DIM_LABELS[dk]
            d = dims.get(dk) or {}
            cur = d.get("current_pct", 0) or 0
            tgt = d.get("target_pct", 0) or 0
            bar_pct = max(0.0, min(100.0, cur))
            good = (cur >= tgt) if kind == "min" else (cur <= tgt)
            tcls = "good" if good else "bad"
            prefix = "&ge;" if kind == "min" else "&le;"
            rows.append(
                f'<div class="grow"><div class="glab">{label}</div>'
                f'<div class="gaxis"><div class="gfill {tcls}" style="width:{bar_pct:.1f}%"></div>'
                f'<div class="gtgt" style="left:{tgt:.1f}%"></div></div>'
                f'<div class="gnum"><span class="mono">{cur:.1f}%</span>'
                f'<span class="gt">cible {prefix} {tgt:.0f}%</span></div></div>'
            )
        return "".join(rows) or '<div class="empty" style="padding:10px 0">&mdash;</div>'

    def _cls(s: int) -> str:
        return "good" if s >= 70 else ("warn" if s >= 50 else "bad")

    grade_cls = _cls(score)
    c_cls = _cls(construction_score)
    f_cls = _cls(fragilite_score)
    return (
        '<div class="card pad gradecard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Note du portefeuille</span>'
        f'<span class="a">{snapshot_date} &middot; {trend_str}</span></div>'
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
            '<div class="card pad"><div class="empty" style="padding:14px 0">'
            "Aucune intervention du copilot pour le moment. Les pressure-tests "
            "apparaitront ici a chaque /position_buy /position_sell /override."
            "</div></div>"
        )
    lis = []
    for r in rows:
        ver = r.get("verdict") or "?"
        cls, label = _VERDICT_LABEL.get(ver, ("calm", ver))
        score = r.get("pressure_score")
        score_s = f"{score:.0f}" if isinstance(score, int | float) else "?"
        date = (r.get("created_at") or "")[:10]
        tk = r.get("ticker") or "?"
        dtype = r.get("decision_type") or "?"
        anc = (r.get("ancrage") or "").strip()
        if len(anc) > 200:
            anc = anc[:197] + "..."
        outc = r.get("outcome_label") or ""
        ret30 = r.get("return_30d_pct")
        outc_html = ""
        if outc:
            good = "outcome_good" in outc
            ocls = "ok" if good else "bad"
            ret_s = f"  ret30j {ret30:+.1f}%" if isinstance(ret30, int | float) else ""
            outc_html = f'<span class="cp-outc {ocls}">{outc}{ret_s}</span>'
        lis.append(
            f'<div class="cp-row"><div class="cp-head">'
            f'<span class="cp-tk">{tk}</span>'
            f'<span class="cp-dtype">{dtype}</span>'
            f'<span class="cp-ver {cls}">{label}&nbsp;&middot;&nbsp;{score_s}</span>'
            f'<span class="cp-date">{date}</span></div>'
            f'<div class="cp-anc">{anc or "(pas d\'ancrage)"}</div>'
            f'{outc_html}</div>'
        )
    return (
        '<div class="card pad copilotcard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Copilot &mdash; pressure-tests recents</span>'
        '<span class="a">verdict mecanique avant chaque trade, outcome 30j</span></div>'
        + "".join(lis)
        + "</div>"
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
        '<div class="card pad wrappercard" style="margin-bottom:18px">'
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
        '<div class="card pad fxcard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Exposition FX</span>'
        '<span class="a">book euro avec sleeves USD / JPY / KRW non-hedges</span></div>'
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
            '<div class="card pad"><div class="empty" style="padding:14px 0">'
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
        '<div class="card pad benchcard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Alpha vs SOX</span>'
        f'<span class="a">{bench["bench_window"]} &middot; book vs PHLX Semiconductor</span></div>'
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
            '<div class="card pad"><div class="empty" style="padding:14px 0">'
            "Pas encore de check kill-criteria. Cron quotidien 07h30 ou trigger : "
            "<code>venv/bin/python -c \"from intelligence import kill_criteria_monitor; kill_criteria_monitor.check_all_active_theses()\"</code>."
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
        '<div class="empty" style="padding:10px 0">aucune these triggered/at_risk &mdash; ' +
        f'{counts["dormant"]} dormantes</div>'
    )
    return (
        '<div class="card pad killcard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Kill-criteria (Sprint 15)</span>'
        f'<span class="a">triggered {counts["triggered"]} &middot; at_risk {counts["at_risk"]} &middot; '
        f'dormant {counts["dormant"]} &middot; cron 07h30</span></div>'
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
            '<div class="card pad"><div class="empty" style="padding:14px 0">'
            "Pas de meta classifies (Sprint 14). Trigger : "
            "<code>venv/bin/python -c \"from intelligence import ticker_meta_classifier; ticker_meta_classifier.classify_all_held_tickers()\"</code>."
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
        '<div class="card pad spofcard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Single points of failure upstream (Sprint 14)</span>'
        '<span class="a">concentration cachee en amont &middot; share = % revenue/capacite</span></div>'
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

        sizing = _sp.compute_mauboussin_sizing()
    except Exception as e:
        return f'<div class="card pad"><div class="empty">Mauboussin sizing indispo: {type(e).__name__}</div></div>'
    if not sizing:
        return (
            '<div class="card pad"><div class="empty" style="padding:14px 0">'
            "Pas encore de meta classifies pour calculer le sizing implicite."
            "</div></div>"
        )
    rows = []
    for tk, d in sizing.items():
        gap = d["gap_pp"]
        gcls = "neg" if gap > 0.5 else ("pos" if gap < -0.5 else "neu")
        fade = d.get("fade_rate_score") or 0
        fcls = "high" if fade >= 60 else ("mid" if fade >= 30 else "low")
        rows.append(
            f'<div class="ms-row">'
            f'<span class="ms-tk">{tk}</span>'
            f'<span class="ms-conv mono">c{d["conviction"]}</span>'
            f'<span class="ms-fade {fcls} mono">fade {fade}</span>'
            f'<span class="ms-target mono">cible {d["target_pct"]:.1f}%</span>'
            f'<span class="ms-actual mono">reel {d["actual_pct"]:.1f}%</span>'
            f'<span class="ms-gap {gcls} mono">{gap:+.1f}pp</span></div>'
        )
    return (
        '<div class="card pad mauboussincard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Mauboussin implied sizing (Sprint 14)</span>'
        '<span class="a">cible = base_cap conviction &times; fade_factor &middot; gap = reel - cible</span></div>'
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
            '<div class="card pad"><div class="empty" style="padding:14px 0">'
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
        '<div class="card pad valocard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Expectations > bull case (Sprint 14 reverse-DCF)</span>'
        '<span class="a">positions ou le prix actuel exige plus que le scenario haussier raisonnable</span></div>'
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
    sorted_f = sorted(facts.items(), key=lambda kv: -kv[1]["pct_of_book"])
    rows = []
    for name, d in sorted_f:
        pct = d["pct_of_book"]
        wcls = "high" if pct >= 30 else ("mid" if pct >= 10 else "low")
        tks = ", ".join(d["tickers"][:8])
        if len(d["tickers"]) > 8:
            tks += f" +{len(d['tickers']) - 8}"
        rows.append(
            f'<div class="fe-row">'
            f'<div class="fe-head"><span class="fe-name">{name}</span>'
            f'<span class="fe-pct {wcls} mono">{pct:.1f}%</span>'
            f'<span class="fe-eur mono">{d["eur"]:,.0f}€</span></div>'
            f'<div class="fe-bar"><div class="fe-fill {wcls}" style="width:{min(pct, 100):.1f}%"></div></div>'
            f'<div class="fe-tks">{tks}  (n={d["n_positions"]})</div></div>'
        )
    return (
        '<div class="card pad factorscard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Factor exposures (Sprint 13)</span>'
        '<span class="a">decomposition par facteur macro &middot; source = Sprint 12 axes</span></div>'
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
        '<div class="card pad stresscard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Stress tests (Sprint 13)</span>'
        '<span class="a">scenarios deterministes &middot; drawdown estime par facteur</span></div>'
        + "".join(rows)
        + "</div>"
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
            '<div class="card pad"><div class="empty" style="padding:14px 0">'
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
        '<div class="card pad trajcard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Trajectory grade (30j)</span>'
        f'<span class="a">{len(snaps)} snapshots &middot; '
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
            '<div class="card pad"><div class="empty" style="padding:14px 0">'
            "Pas encore de tagging axes. Trigger : "
            "<code>venv/bin/python -c \"from intelligence import ticker_classifier; ticker_classifier.classify_all_held_tickers()\"</code>."
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
        '<div class="card pad axescard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Tagging axes par ticker (Sprint 12 — refactor critique)</span>'
        '<span class="a">redondance = driver+stage match strict &middot; decorrelation = unicite macro_factor</span></div>'
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
            '<div class="card pad"><div class="empty" style="padding:14px 0">'
            "Pas encore de preferences calibrees. Cron mensuel 1er du mois 04h, "
            "trigger manuel : <code>venv/bin/python -m intelligence.bot_preferences</code>."
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
        rows_html = "".join(rows) or '<div class="empty" style="padding:8px 0">aucun sample</div>'
        groups.append(
            f'<div class="pr-group"><div class="pr-h">'
            f'<span class="pr-kind">{kind.replace("_"," ")}</span>'
            f'<span class="pr-meta">n={n} conf={conf} ({date})</span></div>'
            f'{rows_html}</div>'
        )
    return (
        '<div class="card pad preferencescard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Preferences calibrees (Layer 3)</span>'
        '<span class="a">ce qui a MARCHE deterministically &middot; samples + win rate, pas d\'opinion</span></div>'
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
            '<div class="card pad"><div class="empty" style="padding:14px 0">'
            "Pas encore de conceptions synthetisees. Cron hebdo dimanche 19h, "
            "ou trigger manuel : <code>venv/bin/python -m intelligence.bot_conceptions</code>."
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
        if len(text) > 380:
            text = text[:377] + "..."
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
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
        '<div class="card pad conceptionscard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Conceptions du bot (Layer 2)</span>'
        '<span class="a">vue stable per ticker &middot; synthese hebdo &middot; injectee dans le copilot pre-trade</span></div>'
        + "".join(rows)
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
            '<div class="card pad"><div class="empty" style="padding:14px 0">'
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
        '<div class="card pad chatsigcard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Signaux soft extraits du chat</span>'
        '<span class="a">murmures captures en conversation lambda &middot; alimente le profil</span></div>'
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
            '<div class="card pad"><div class="empty" style="padding:14px 0">'
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
        '<div class="card pad conversationscard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Conversations recentes</span>'
        '<span class="a">consignees, sauvegardees, integrees au profil &middot; '
        'boucle recolte &rarr; analyse &rarr; digestion &rarr; precision</span></div>'
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
            '<div class="card pad"><div class="empty" style="padding:14px 0">'
            "Pas encore de synthese narrative LLM. Le cron tourne chaque dimanche 20h30, "
            "ou trigger manuel : <code>venv/bin/python -m intelligence.portfolio_grade_llm</code>."
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
    ) or '<div class="empty" style="padding:10px 0">aucun edge identifie</div>'

    red_rows = "".join(
        f'<div class="nv-line"><span class="nv-tk">{r.get("ticker","?")}</span>'
        f'<span class="nv-with">redondant avec {r.get("redundant_with","?")}</span>'
        f'<span class="nv-why">{(r.get("reason") or "")[:160]}</span></div>'
        for r in redundant
    ) or '<div class="empty" style="padding:10px 0">aucune redondance</div>'

    return (
        '<div class="card pad narrativecard" style="margin-bottom:18px">'
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


def _chat_panel() -> str:
    """Sprint 7 — Chat surface : pose une question, contexte assemble cote serveur."""
    return (
        '<div class="card pad chatcard" style="margin-bottom:18px">'
        '<div class="colhead"><span class="t">Pose une question au copilot</span>'
        '<span class="a">il connait ton profil, ta note PF, tes positions, tes theses et son historique d\'interventions</span></div>'
        '<div id="chat-log" class="chat-log"></div>'
        '<form id="chat-form" class="chat-form" onsubmit="return chatSend(event)">'
        '<textarea id="chat-input" class="chat-input" placeholder="ex. Quelle est ma plus grosse fragilite en ce moment ?" rows="2"></textarea>'
        '<button type="submit" class="chat-send">Envoyer</button>'
        '</form>'
        '<div class="chat-foot">Le contexte (profil + grade + positions + interventions) est rejoue a chaque message.</div>'
        '</div>'
        '<script>'
        'window._chatHistory=window._chatHistory||[];'
        'window._chatSessionId=window._chatSessionId||localStorage.getItem("heimdall_chat_session")||(()=>{const s="s_"+Date.now().toString(36)+"_"+Math.random().toString(36).slice(2,8);localStorage.setItem("heimdall_chat_session",s);return s;})();'
        'function chatEsc(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}'
        'function chatAppend(role,text){const log=document.getElementById("chat-log");const div=document.createElement("div");div.className="chat-msg chat-"+role;div.innerHTML=chatEsc(text).replace(/\\n/g,"<br>");log.appendChild(div);log.scrollTop=log.scrollHeight;}'
        'async function chatSend(e){e.preventDefault();const ta=document.getElementById("chat-input");const msg=ta.value.trim();if(!msg)return false;'
        'chatAppend("user",msg);ta.value="";'
        'const histSend=window._chatHistory.slice(-10);'
        'const btn=document.querySelector(".chat-send");btn.disabled=true;btn.textContent="...";'
        'chatAppend("assistant","(reflexion en cours, l\'appel Opus prend 8-15s)");'
        'try{const r=await fetch("/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:msg,history:histSend,session_id:window._chatSessionId})});'
        'const d=await r.json();'
        'const last=document.querySelector(".chat-log .chat-msg:last-child");last.remove();'
        'if(d.error){chatAppend("assistant","ERREUR : "+d.error);}else{const reply=d.reply||"(reponse vide)";chatAppend("assistant",reply);window._chatHistory.push({role:"user",content:msg});window._chatHistory.push({role:"assistant",content:reply});}'
        '}catch(err){const last=document.querySelector(".chat-log .chat-msg:last-child");if(last)last.remove();chatAppend("assistant","ERREUR reseau : "+err);}'
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
    try:
        rows = _q("SELECT ticker, qty, avg_cost, notes FROM positions WHERE status NOT IN ('closed', 'sold')")
    except Exception:
        return []
    out = []
    for tk, qty, ac, notes in rows:
        m = re.search(r"eur_invested=([0-9.]+)", notes or "")
        w = float(m.group(1)) if m else float(qty or 0) * float(ac or 0)
        out.append({"ticker": tk, "weight": w, "avg_cost": float(ac or 0)})
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
        cls, sign = ("up", "+") if pnl >= 0 else ("down", "")
        flag = " &#127919;" if hit else ""
        d = i * 0.035
        rows.append(
            f'<div class="row" data-tk="{tk}" style="animation-delay:{d:.2f}s"><div class="rt">'
            f'<span class="tk">{tk}{flag}</span><span class="tag {cls}">{sign}{pnl:.1f}%</span></div>'
            f'<div class="axis"><div class="axis-mark" style="left:{pc:.1f}%"></div></div>'
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
    rows = "".join(
        f'<div class="line"><span>{tk}</span><span class="mono">{prog:.0f}% vers la cible</span></div>'
        for prog, tk in data
    )
    watch = (
        rows or '<div class="empty" style="padding:18px 0">aucune ligne &agrave; &ge;75% de la cible &mdash; laisser courir</div>'
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
            f'<div class="axis"><div class="axis-mark" style="left:{buf:.1f}%"></div></div>'
            f'<div class="rs"><span>marge avant le stop</span></div></div>'
        )
        if is_near:
            near_rows.append(f'<div class="line"><span>{tk}</span><span class="mono">{down:.0f}% de marge</span></div>')
    watch = (
        "".join(near_rows)
        or '<div class="empty" style="padding:18px 0">aucune marge faible &mdash; calme</div>'
    )
    return "".join(rows), near, heat, watch


def _mover_blk(rows) -> str:
    return (
        "".join(
            f'<div class="line"><span class="mono">{tk}</span>'
            f'<span class="mono {"pos" if p >= 0 else "neg"}">{"+" if p >= 0 else ""}{p:.1f}%</span></div>'
            for tk, p in rows
        )
        or '<div class="empty" style="padding:14px 0">&mdash;</div>'
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


def _cluster_health(positions: list[dict], pnl: dict) -> list[dict]:
    """Source unique des breaches de cluster correle (gouverneur de concentration).
    Consomme par la page Concentration (detail) ET le bandeau d'ecart (resume, haut de page).
    Une seule definition de la valeur EUR par ligne -> page et bandeau ne peuvent plus
    se contredire (cf. ancienne jauge 0 calme vs verdict ELEVEE)."""

    def _v(p: dict) -> float:
        return p["weight"] * (1 + pnl.get(p["ticker"], 0) / 100.0)

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
        return p["weight"] * (1 + pnl.get(p["ticker"], 0) / 100.0)

    cost_total = sum(p["weight"] for p in positions) or 1
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
    # --- Cluster correle (gouverneur de concentration, policy 25/05) ---
    # source unique partagee avec le bandeau d'ecart (cf. _cluster_health)
    _crows = []
    for _c in _ch:
        _ccls = "danger" if _c["breached"] else "calm"
        _otxt = (
            f"d&eacute;passement +{_c['over_eur']:,.0f}&#8239;&euro; &rarr; all&eacute;ger"
            if _c["over_eur"] > 0
            else "sous le plafond"
        ).replace(",", "&#8239;")
        _crows.append(
            f'<div class="pi {_ccls}"><span class="pn">{_c["pct"]:.0f}%</span>'
            f'<span class="pl">{_c["name"]} &middot; plafond {_c["cap"]:.0f}%</span>'
            f'<span class="pt">{_otxt}</span></div>'
        )
    cluster_card = (
        (
            '<div class="plan"><div class="plan-h">Cluster corr&eacute;l&eacute; (gouverneur)</div><div class="plan-row">'
            + "".join(_crows)
            + "</div></div>"
        )
        if _crows
        else ""
    )
    verdict_card = (
        '<div class="plan"><div class="plan-h">Verdict concentration</div>'
        '<div class="plan-row" style="grid-template-columns:minmax(160px,1fr) 2fr">'
        + f'<div class="pi {vcls}"><span class="pn">{verdict}</span><span class="pl">posture concentration</span><span class="pt">{cause}</span></div>'
        + f'<div class="pi"><span class="pl">{over_cap} ligne(s) au-dessus du plafond {POS_CAP:.0f}%</span>'
        + f'<span class="pt" style="font-size:12.5px;color:var(--ink);margin-top:4px;line-height:1.5">{over_nm or "aucune"}</span></div>'
        + "</div></div>"
    )
    return (
        f'<section data-page="concentration"><div class="phead"><h2>Concentration</h2>'
        f'<div class="sub">Trois axes de concentration &mdash; par ligne, par secteur, par g&eacute;ographie</div></div>'
        f"{verdict_card}"
        f"{cluster_card}"
        f'<div class="kpis" style="grid-template-columns:repeat(3,1fr)">'
        f'<div class="kpi"><span class="kl">Premi&egrave;re ligne</span><span class="kv {top_cls}">{_pct(top_pct)}%</span><span class="kd">{line_msg}</span></div>'
        f'<div class="kpi"><span class="kl">Th&egrave;se dominante</span><span class="kv {these_cls}">{dom_these_pct:.0f}%</span><span class="kd">{these_msg}</span></div>'
        f'<div class="kpi"><span class="kl">Capital investi</span><span class="kv">{cap}&nbsp;&euro;</span><span class="kd">{len(positions)} lignes</span></div></div>'
        f'<div class="card pad"><div class="sbwrap"><div class="sb-top"><div class="sb-kpi"><span class="sb-kl">CAPITAL D&Eacute;PLOY&Eacute;</span><span class="sb-kv">{cap}&nbsp;&euro;</span></div><div class="sb-kpi"><span class="sb-kl">SECTEURS</span><span class="sb-kv">{len(sw_real)}</span></div><div class="sb-kpi"><span class="sb-kl">PLUS GROSSE EXPOSITION</span><span class="sb-kv">{dom_these} &middot; {dom_these_pct:.0f}%</span></div></div><div id="sb-bars" class="sb-bars"></div><div id="sb-panel"></div></div></div>'
        f'<div class="card pad" style="margin-top:18px"><div class="colhead"><span class="t">Par secteur</span></div>{_sector_blocks(positions, planned, sectors, pnl, names, daily)}</div>'
        f'<div class="card pad" style="margin-top:18px"><div class="colhead"><span class="t">Par pays</span><span class="a">si&egrave;ge social &middot; pas la cha&icirc;ne d&rsquo;approvisionnement r&eacute;elle (Ta&iuml;wan sous-estim&eacute;)</span></div>{_geo_bars(positions)}</div>'
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
            f'<span class="sec-tk">{tk}{badge}{nmspan}</span>'
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
        f'<div class="sub" style="margin-bottom:10px">{sub}</div>'
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
        ".geo-item:hover .geo-sub,.geo-item.open .geo-sub{max-height:360px;opacity:1;margin:4px 0 14px}"
        ".geo-stk{display:flex;align-items:center;gap:10px;padding:5px 6px 5px 16px;"
        "font-size:12px;border-left:2px solid var(--line2);margin-left:3px}"
        ".geo-stk .gnm{color:var(--ink)}"
        ".geo-stk .gtk{color:var(--steel);font-family:var(--fm);font-size:10.5px}"
        ".geo-stk .gpc{margin-left:auto;color:var(--steel);font-family:var(--fm);font-size:10.5px}"
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
            f'<div class="axis"><div class="axis-mark" style="left:{max(2.0, min(100.0, pct)):.1f}%"></div></div>'
            f'<div class="rs"><span>exposition</span><span class="mono">{w:.0f}&euro;</span></div></div>'
            f'<div class="geo-sub">{sub}</div></div>'
        )
    js = (
        "<script>document.querySelectorAll('.geo-item').forEach(function(e){"
        "e.addEventListener('click',function(){e.classList.toggle('open')})});</script>"
    )
    return css + bars + js


def _signaux() -> str:
    try:
        s24 = _q("SELECT COUNT(*) FROM signals WHERE timestamp > datetime('now','-1 day')")[0][0]
        s30 = _q("SELECT COUNT(*) FROM signals WHERE timestamp > datetime('now','-30 day')")[0][0]
        n8k = _q("SELECT COUNT(*) FROM filings_8k_log WHERE filed_at > datetime('now','-60 day')")[0][0]
    except Exception as e:
        return f'<section data-page="signaux"><div class="phead"><h2>Signaux</h2></div>{_err(e)}</section>'

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
        eightk = rows8k or '<div class="empty" style="padding:18px 0">aucun 8-K sur 60&nbsp;j</div>'
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
            or '<div class="empty" style="padding:18px 0">aucun cluster d\'achats group&eacute;s d&eacute;tect&eacute;</div>'
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
                f'<div class="axis"><div class="axis-mark" style="left:{max(2.0, min(100.0, cv * 100)):.1f}%"></div></div>'
                f'<div class="rs"><span>cr&eacute;dibilit&eacute;</span><span class="mono">{int(n)} signaux</span></div></div>'
            )
    except Exception as e:
        src_rows, nsrc = _err(e), 0

    kpis = (
        f'<div class="kpis" style="grid-template-columns:repeat(3,1fr)">'
        f'<div class="kpi"><span class="kl">Signaux 24&nbsp;h</span><span class="kv">{s24}</span><span class="kd">Gmail + EDGAR</span></div>'
        f'<div class="kpi"><span class="kl">Signaux 30&nbsp;j</span><span class="kv">{s30}</span><span class="kd">fen&ecirc;tre roulante</span></div>'
        f'<div class="kpi"><span class="kl">D&eacute;p&ocirc;ts 8-K &middot; 60&nbsp;j</span><span class="kv">{n8k}</span><span class="kd">source EDGAR</span></div></div>'
    )
    cols = (
        f'<div class="cols">'
        f'<div class="col"><div class="colhead"><span class="t">8-K r&eacute;cents</span><span class="a">{tally_str}</span></div><div class="card">{eightk}</div></div>'
        f'<div class="col"><div class="colhead"><span class="t">Cr&eacute;dibilit&eacute; des sources</span><span class="a">{nsrc} sources &middot; recal 1er du mois</span></div><div class="card">{src_rows}</div></div>'
        f"</div>"
    )
    insider_strip = (
        f'<div class="colhead" style="margin-top:24px"><span class="t">Achats d\'initi&eacute;s group&eacute;s</span><span class="a">60&nbsp;j &middot; Form 4 EDGAR</span></div>'
        f'<div class="card pad">{insiders}</div>'
    )
    return (
        f'<section data-page="signaux"><div class="phead"><h2>Signaux</h2>'
        f'<div class="sub">D&eacute;p&ocirc;ts 8-K par s&eacute;v&eacute;rit&eacute; &middot; cr&eacute;dibilit&eacute; des sources &middot; achats d\'initi&eacute;s</div></div>'
        f"{kpis}{cols}{insider_strip}</section>"
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
}


_MACRO_TIPS: dict[str, str] = {
    "TYX": "Coût capital long. > 5% = multiples growth/tech craquent historiquement.",
    "Gold": "Couverture taux réels / débasement / géopol. Lecture interprétative.",
    "USDJPY": "Baromètre carry trade. > 160 = zone intervention BoJ → tail risk unwind tech US.",
    "VIX": "Vol implicite S&P 500 30j. < 15 euphorie, > 25 stress, > 40 panique.",
    "HY_OAS": "Prime obligations haut rendement vs Treasury. < 300 = complacent, > 600 = panique. Signal avancé.",
    "DXY": "USD vs 6 majeures. > 105 = vent contraire multinationales US ; > 110 = stress global.",
    "BTC": "Baromètre appétit pour le risque et proxy de liquidité globale.",
    "MOVE": "VIX des Treasuries. > 130 = stress obligataire, souvent avancé sur actions.",
    "T10Y2Y": "Courbe des taux 10A-2A. Dé-inversion (passage <0 vers >0) = récession dans 3-6 mois.",
    "BankReserves": "Cash bancaire à la Fed. < 2.5T = stress plomberie imminent.",
    "RepoSRF": "Standing Repo Facility. > 30B = banques court de cash, alarme plomberie aiguë.",
    "FedBalance": "Bilan Fed. Contraction (QT) = liquidité retirée, vent contraire actifs risqués.",
    "FedBalanceSheet": "Bilan Fed. Contraction (QT) = liquidité retirée, vent contraire actifs risqués.",
    "FedBS": "Bilan Fed. Contraction (QT) = liquidité retirée, vent contraire actifs risqués.",
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
            f'<span class="dname">{name} <span style="color:var(--steel);font-size:10px">({tk})</span></span>'
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
        f'<span class="dname">RSP / SPY ratio <span style="color:var(--steel);font-size:10px">vs MM50</span></span>'
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
        "BTC": (1, "Bitcoin ($)", 0, True),
        "Gold": (1, "Or ($/oz)", 0, True),
        # Tier 2: Stress bancaire & liquidité Fed — signaux avancés en haut, plomberie milieu, slow bas
        "MOVE": (2, "Vol. obligataire (MOVE)", 2, False),
        "T10Y2Y": (2, "Pente 10a-2a (%)", 4, False),
        "BankReserves": (2, "R&eacute;serves bancaires Fed ($M)", 0, True),
        "RepoSRF": (2, "Standing Repo Facility ($B)", 2, False),
        "FedBalance": (2, "Bilan Fed ($M)", 0, True),
        "FedBalanceSheet": (2, "Bilan Fed ($M)", 0, True),
        "FedBS": (2, "Bilan Fed ($M)", 0, True),
        "KRE": (2, "Banques r&eacute;gionales ($)", 2, False),
        "CopperGold": (2, "Ratio cuivre/or", 4, False),
        # Tier 3: Macro lente
        "CoreCPI": (3, "Inflation core (%)", 4, False),
        "CPI": (3, "Inflation core (%)", 4, False),
        "MfgIP": (3, "Production industrielle (%)", 4, False),
        "MfgIP_yoy": (3, "Production industrielle (%)", 4, False),
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
    size_txt = f"VIX {_vix:.1f} {'&ge;' if _reduced else '&lt;'} {_vthr}" if _vix is not None else "VIX indisponible"
    clabel = {1: "STABLE", 2: "STRESS", 3: "ALERTE", 4: "CRISE"}.get(cphase, "CRISE")
    _conc = []
    for _c in _cluster_health(positions, pnl):
        if _c["breached"]:
            _ov = f"{_c['over_eur']:,.0f}".replace(",", "&#8239;")
            _conc.append(f"all&eacute;ger {_c['name']} &middot; +{_ov}&#8239;&euro;")
    _dev_cls, _dev_lab = ("danger", "&Agrave; CALIBRER") if _conc else ("calm", "AU CALME")
    _dev_txt = " &nbsp;&middot;&nbsp; ".join(_conc) if _conc else "concentration sous les plafonds"
    feu = (
        '<div class="plan"><div class="plan-h">&Agrave; arbitrer aujourd&rsquo;hui</div><div class="plan-row">'
        + f'<div class="pi {_dev_cls}"><span class="pn">{_dev_lab}</span><span class="pl">&eacute;cart de discipline</span><span class="pt">{_dev_txt}</span></div>'
        + f'<div class="pi calm"><span class="pn">{near_t}</span><span class="pl">ligne(s) &agrave; &ge;75% de la cible</span><span class="pt">laisser courir &middot; tenir le cap</span></div>'
        + f'<div class="pi {"danger" if near else "calm"}"><span class="pn">{near}</span><span class="pl">ligne(s) &agrave; &lt;10% du stop</span><span class="pt">{"&agrave; surveiller" if near else "calme"}</span></div>'
        + "</div>"
        + '<div style="margin-top:16px;padding-top:13px;border-top:1px solid var(--line);display:flex;gap:30px;flex-wrap:wrap;font-size:11.5px;color:var(--steel)">'
        + f'<span>{size_txt} &middot; sizing <b style="color:var(--ink)">&times;{_sfac:.1f}</b></span>'
        + "</div></div>"
    )
    _phase_col = {1: "acc", 2: "warn", 3: "warn", 4: "bear"}.get(cphase, "bear")
    gauge = (
        '<div class="gauge"><div class="ghead">'
        '<span class="gl">Sant&eacute; macro &middot; cr&eacute;dit / or / taux 30a / inflation / VIX</span>'
        + f'<span class="gv"><span class="gvm" style="--c:var(--{_phase_col})">{clabel}</span><span style="font-size:12px;color:var(--steel);font-weight:500"> &middot; phase {cphase}/4 &middot; indice {score:.0f}</span></span></div>'
        + f'<div class="gtrack"><div class="axis-mark" style="left:{(cphase - 0.5) * 25:.0f}%"></div></div>'
        '<div class="glab"><span>stable</span><span>stress</span><span>alerte</span><span>crise</span></div></div>'
    )
    rsi_html = _market_rsi()
    breadth_html = _breadth_rsp_spy()
    return (
        f'<section data-page="urgence"><div class="phead"><h2>Urgence</h2>'
        f'<div class="sub">&Eacute;lan vers les cibles &middot; marge avant les stops &middot; stress macro</div></div>'
        f"{feu}{gauge}"
        f'<div class="cols">'
        f'<div><div class="ph3">Course vers la cible</div><div class="card pad">{elan}</div></div>'
        f'<div><div class="ph3">Marges les plus faibles</div><div class="card pad">{watch}</div></div>'
        f'<div><div class="ph3">Moniteur de stress macro &mdash; {clabel}</div>'
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
        lab = raw if len(raw) <= 40 else raw[:40].rsplit(" ", 1)[0] + "&hellip;"
        items += f'<span class="ti"><b>{tk}</b> <span class="{cls}">8-K</span> {lab}</span>'
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
        dcol = {1: "#37E0A0", 2: "#FFB020", 3: "#FB923C", 4: "#FF6B6B"}.get(int(phase or 1), "#FF6B6B")
        macro = f'<span class="rfmacro" style="background:{dcol}" title="Macro phase {int(phase or 1)}"></span>'
    return (
        f'<div class="rfoot" title="Portefeuille {posture} &middot; surchauffe {heat:.0f}&deg; &middot; {near} marge(s) faible(s)">'
        f'<span class="statedot {tone}"></span>'
        f'<span class="rfm">{heat:.0f}&deg;</span>'
        f'<span class="rfm">{near}&#9888;</span>'
        f"{macro}</div>"
    )


def _sizing_overcap(positions: list[dict], conv_by_tk: dict, caps: dict, pnl: dict) -> list[str]:
    """Lignes dont le poids courant depasse leur cap de conviction (signal de TAILLE, prix-agnostique)."""
    vtot = sum(p["weight"] * (1 + pnl.get(p["ticker"], 0) / 100.0) for p in positions) or 1
    over = []
    for p in positions:
        wv = p["weight"] * (1 + pnl.get(p["ticker"], 0) / 100.0) / vtot * 100
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
        ".ck-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:8px}"
        ".ck-cell{background:color-mix(in srgb,var(--ink) 2%,transparent);border:1px solid var(--line);border-radius:var(--r2);padding:14px 16px}"
        ".ck-label{font-size:12px;color:var(--steel);letter-spacing:.01em}"
        ".ck-num{font-family:var(--fm);font-size:26px;font-weight:500;margin-top:6px;line-height:1.05;letter-spacing:-.01em}"
        ".ck-sub{font-size:11.5px;color:var(--steel);margin-top:5px;line-height:1.4}"
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


_LOGO = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='270 202 906 483' role='img' aria-label='PRESAGE' fill='currentColor'><g transform='translate(375,195)'><g transform='translate(0.000000,380.000000) scale(0.100000,-0.100000)' fill='currentColor' stroke='none'><path d='M2330 3208 c-223 -222 -441 -439 -485 -483 l-81 -80 -17 -53 -17 -54 7 -194 6 -195 141 3 141 3 5 150 5 150 12 20 c6 11 215 222 462 470 l451 450 0 15 0 15 -93 93 -92 92 -20 0 -19 0 -406 -402z'/><path d='M4114 3528 c-45 -46 -87 -94 -94 -107 l-12 -23 463 -464 464 -464 5 -158 5 -157 134 -3 134 -3 8 8 8 8 3 195 3 195 -26 55 -27 55 -471 470 -471 470 -23 3 -22 3 -81 -83z'/><path d='M3485 2454 c-3 -22 -17 -75 -31 -119 l-25 -80 -30 -47 c-38 -59 -95 -110 -157 -142 l-48 -24 -60 -11 -59 -10 -305 -6 c-168 -3 -640 -12 -1050 -20 -829 -16 -1399 -33 -1475 -44 l-50 -7 370 -12 c204 -7 674 -19 1045 -27 371 -8 862 -19 1090 -25 l415 -10 60 -15 60 -16 48 -31 c61 -39 111 -98 147 -173 l28 -60 12 -65 c7 -36 16 -76 20 -90 l7 -25 8 40 c16 87 38 162 62 213 l26 53 42 47 43 48 49 26 c27 15 70 32 96 37 l47 11 342 10 c189 6 667 17 1063 25 396 8 887 20 1090 27 l370 13 -65 6 c-139 15 -885 35 -2205 59 l-580 11 -60 15 -60 15 -41 24 -42 24 -45 51 -46 51 -25 52 -26 52 -19 88 c-11 49 -22 91 -25 94 -2 3 -7 -12 -11 -33z'/><path d='M1738 1613 c-2 -76 -3 -168 -2 -204 l0 -66 27 -55 27 -55 52 -44 c29 -24 242 -231 474 -461 l420 -418 25 0 24 0 88 91 88 92 -3 13 c-2 8 -210 221 -463 474 l-460 460 -3 148 -4 147 -11 7 -12 8 -132 0 -133 0 -2 -137z'/><path d='M4953 1744 l-13 -6 -1 -136 c0 -75 -3 -144 -7 -153 -4 -9 -211 -223 -459 -474 l-453 -458 0 -16 0 -16 87 -87 88 -88 25 0 24 0 459 457 458 458 27 44 26 45 11 55 10 56 -5 160 -5 160 -130 2 c-71 1 -136 -1 -142 -3z'/></g></g><g transform='translate(265,598)'><g transform='translate(0.000000,100.000000) scale(0.100000,-0.100000)' fill='currentColor' stroke='none'><path d='M174 841 c-2 -2 -4 -136 -4 -298 l0 -293 45 0 45 0 0 100 0 100 98 0 c53 0 114 5 135 11 163 45 185 285 31 359 -42 21 -62 23 -196 24 -82 1 -152 -1 -154 -3z m301 -95 c89 -37 83 -166 -9 -201 -28 -11 -66 -15 -121 -13 l-80 3 -3 113 -3 112 91 0 c56 0 104 -5 125 -14z'/><path d='M1534 835 c-3 -6 -3 -141 -2 -300 l3 -290 45 0 45 0 3 113 3 112 62 0 63 0 78 -110 77 -110 56 0 55 0 -17 28 c-10 15 -45 65 -78 112 -33 46 -55 86 -49 88 24 8 76 49 96 75 15 20 21 46 24 95 4 87 -22 135 -91 171 -45 23 -59 25 -209 25 -100 1 -162 -3 -164 -9z m347 -113 c53 -59 29 -140 -49 -162 -20 -5 -74 -10 -119 -10 l-83 0 0 106 0 106 111 -4 c111 -3 111 -3 140 -36z'/><path d='M2988 843 l-48 -4 0 -295 0 -294 220 0 220 0 0 40 0 40 -175 0 -175 0 0 85 0 85 150 0 150 0 0 45 0 45 -150 0 -150 0 0 85 0 85 173 2 172 3 3 34 c2 20 -2 37 -10 42 -13 8 -283 9 -380 2z'/><path d='M4435 832 c-105 -49 -135 -171 -62 -250 31 -34 59 -46 172 -76 113 -30 135 -45 135 -93 0 -41 -26 -68 -80 -83 -57 -15 -121 -3 -185 35 l-55 34 -27 -36 c-27 -35 -27 -36 -8 -50 62 -46 121 -67 207 -71 76 -4 92 -1 140 21 89 40 131 140 93 221 -25 52 -56 70 -190 110 -127 37 -148 51 -143 100 7 73 128 96 223 43 l49 -28 25 26 c33 32 23 51 -45 85 -66 34 -190 40 -249 12z'/><path d='M5918 843 l-36 -4 -112 -262 c-62 -144 -119 -277 -127 -294 l-13 -33 52 0 53 0 23 58 c99 244 175 422 181 422 4 0 13 -17 20 -37 7 -21 24 -63 37 -93 13 -30 50 -120 83 -200 l59 -145 51 -5 c34 -4 51 -2 51 6 0 6 -48 121 -106 255 -58 134 -113 262 -121 284 -9 22 -17 41 -17 41 -4 6 -48 10 -78 7z'/><path d='M7273 829 c-73 -28 -135 -92 -163 -165 -44 -118 -12 -278 71 -348 60 -51 109 -69 195 -74 93 -5 159 12 221 57 l38 28 -1 89 c-1 49 -2 104 -3 122 l-1 32 -121 0 -120 0 3 -42 3 -43 73 -3 72 -3 0 -59 0 -58 -47 -19 c-115 -43 -232 -6 -282 91 -59 114 -7 274 102 315 68 26 178 9 228 -36 15 -13 20 -11 43 14 15 15 25 34 24 42 -2 7 -27 27 -57 44 -47 27 -66 31 -140 34 -69 3 -97 -1 -138 -18z'/><path d='M8567 843 c-4 -3 -7 -138 -7 -300 l0 -293 220 0 220 0 0 40 0 40 -172 2 -173 3 -3 82 -3 82 148 3 148 3 3 43 3 42 -151 0 -151 0 3 83 3 82 170 5 170 5 3 36 3 36 -53 6 c-70 9 -373 9 -381 0z'/></g></g></svg>"

_TH_CSS = """
<style>
  .th-gap { margin-bottom:18px; }
  .th-hist { display:flex; flex-direction:column; gap:6px; padding:2px 0; }
  .th-hbar { display:flex; align-items:center; gap:11px; font-family:var(--fm); font-size:11.5px; }
  .th-hlab { width:24px; color:var(--steel); }
  .th-hbar .axis { flex:1; margin:0; }
  .th-hn { width:22px; text-align:right; color:var(--ink); font-weight:600; }
  .th-grp { font-family:var(--fb); font-size:10.5px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin:34px 2px 13px; display:flex; align-items:center; gap:10px; }
  .th-grp::after { content:""; flex:1; height:1px; background:var(--line); }
  .th-row { display:grid; grid-template-columns:160px 46px 1fr; gap:12px; align-items:center; padding:13px 15px; border:1px solid var(--line); border-radius:var(--r3); margin-bottom:0; background:color-mix(in srgb,var(--ink) 1.2%,transparent); cursor:pointer; transition:.15s; }
  .th-row:hover { border-color:var(--line2); background:color-mix(in srgb,var(--ink) 3.5%,transparent); }
  .th-id { display:flex; align-items:center; gap:9px; flex-wrap:wrap; }
  .th-conv { font-family:var(--fm); font-weight:600; font-size:10.5px; letter-spacing:.04em; padding:2px 7px; border-radius:var(--r1); }
  .th-conv.c5 { color:var(--bg); background:var(--ink); }
  .th-conv.c4 { color:var(--bg); background:var(--acc); }
  .th-conv.c3 { color:var(--bg); background:var(--warn); }
  .th-conv.c2 { color:var(--steel); border:1px solid var(--line2); }
  .th-conv.c1 { color:var(--steel); border:1px solid var(--line); opacity:.65; }
  .th-tk { font-weight:600; font-size:14px; }
  .th-w { font-family:var(--fm); font-size:12px; font-weight:600; color:var(--ink); text-align:right; align-self:center; }
  .th-dir { font-family:var(--fb); font-size:9.5px; color:var(--steel); text-transform:uppercase; letter-spacing:.12em; }
  .th-bar { display:flex; flex-direction:column; gap:6px; grid-column:1/-1; margin-top:8px; }
  .sizebar { margin:6px 0 4px; }
  .th-adj { font-family:var(--fm); font-size:10.5px; letter-spacing:.02em; line-height:1.3; }
  .th-adj.trim { color:var(--warn); }
  .th-adj.add { color:var(--acc2); }
  .th-adj.ok { color:var(--steel); }
  .th-szcol { display:flex; flex-direction:column; gap:5px; }
  .th-zone-loss { position:absolute; left:0; top:0; bottom:0; background:rgba(255,107,107,.13); }
  .th-zone-profit { position:absolute; right:0; top:0; bottom:0; background:rgba(55,224,160,.13); }
  .th-ends { display:flex; justify-content:space-between; align-items:baseline; font-family:var(--fm); font-size:10.5px; }
  .th-stop { color:var(--bear); }
  .th-tgt { color:var(--acc); font-weight:600; }
  .th-na { font-family:var(--fm); font-size:11px; color:var(--steel); }
  .th-cat { font-family:var(--fm); font-size:10px; letter-spacing:.03em; color:var(--steel); background:rgba(124,137,166,.10); border:1px solid var(--line); border-radius:var(--r1); padding:2px 8px; margin-left:2px; white-space:nowrap; }
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
            '<section data-page="theses"><div class="phead"><h2>Th&egrave;ses</h2>'
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
        current = _cached_price_eur(tk) or last or entry
        d_stop = d_tgt = ratio = frac = entry_frac = pnl_e = None
        has_bar = bool(current and stop and tgt and tgt != stop)
        if has_bar:
            d_stop = abs(stop - current) / current * 100
            d_tgt = abs(tgt - current) / current * 100
            ratio = d_tgt / d_stop if d_stop else None
            frac = max(0.0, min(100.0, (current - stop) / (tgt - stop) * 100))
            if entry:
                entry_frac = max(0.0, min(100.0, (entry - stop) / (tgt - stop) * 100))
                pnl_e = (current - entry) / entry * 100
            if d_tgt is not None and d_tgt < 12:
                n_near_tgt += 1
            if d_stop < 10:
                n_near += 1
            if pnl_e is not None and pnl_e >= 0:
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
            f'<div class="axis"><div class="axis-mark" style="left:{max(2.0, min(100.0, dist[c] / maxc * 100)):.1f}%"></div></div>'
            f'<span class="th-hn">{dist[c]}</span></div>'
        )
    hist += "</div>"
    infl_msg = (
        f"&#9888; inflation de conviction : c5 = {c5_pct:.0f}% (seuil 20%)"
        if infl
        else f"c5 = {c5_pct:.0f}% &middot; pas d&rsquo;inflation (seuil 20%)"
    )

    hero = (
        '<div class="hero"><div><div class="hl">Th&egrave;ses actives</div>'
        f'<div class="big" style="--c:var(--id)">{n}</div>'
        f'<div class="hsub">m&eacute;diane c{med} &middot; {n_near} marge(s) faible(s) &middot; {n_near_tgt} proche(s) de la cible</div></div>'
        '<div style="flex:1;min-width:250px"><div class="hl">R&eacute;partition par conviction</div>'
        f'{hist}<div class="hsub" style="margin-top:7px">{infl_msg}</div></div></div>'
    )

    pcls = "acc" if n_profit * 2 >= n else "negc"
    ncls = "negc" if n_near else "acc"
    kpis = (
        '<div class="kpis" style="grid-template-columns:repeat(3,1fr)">'
        f'<div class="kpi"><span class="kl">Proches de la cible</span><span class="kv acc">{n_near_tgt}</span><span class="kd">marge &lt; 12%</span></div>'
        f'<div class="kpi"><span class="kl">En gain</span><span class="kv {pcls}">{n_profit}/{n}</span><span class="kd">cours &gt; co&ucirc;t d&rsquo;entr&eacute;e</span></div>'
        f'<div class="kpi"><span class="kl">Marges faibles</span><span class="kv {ncls}">{n_near}</span><span class="kd">marge &lt; 10% du stop</span></div></div>'
    )

    gap = ""

    vtot = sum(p["weight"] * (1 + pnl.get(p["ticker"], 0) / 100.0) for p in positions) or 1
    vmap = {p["ticker"]: p["weight"] * (1 + pnl.get(p["ticker"], 0) / 100.0) / vtot * 100 for p in positions}
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
                    f'{zones}<div class="axis-mark" style="left:{t["frac"]:.1f}%"></div></div>'
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
                    f'<div class="axis-mark" style="left:{_w_pos:.1f}%"></div>'
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
        '<section data-page="theses"><div class="phead"><h2>Th&egrave;ses</h2>'
        '<div class="sub">Asym&eacute;trie cible / stop, par niveau de conviction</div></div>'
        f"{_TH_CSS}{hero}{kpis}{gap}{groups}</section>"
    )


_NAV = (
    '<nav class="nav">'
    '<div class="nitem on" data-nav="vigie"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14a8 8 0 0 1 16 0"/><path d="M12 14l4.5-3.5"/><circle cx="12" cy="14" r="1.3" fill="currentColor" stroke="none"/></svg><span class="nlab">Vue d&rsquo;ensemble</span></div>'
    '<div class="nitem" data-nav="positions"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4l8 4-8 4-8-4 8-4z"/><path d="M4 12l8 4 8-4"/><path d="M4 16l8 4 8-4"/></svg><span class="nlab">Positions</span></div>'
    '<div class="nitem" data-nav="theses"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/></svg><span class="nlab">Th&egrave;ses</span></div>'
    '<div class="nitem" data-nav="concentration"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><path d="M12 12V4"/><path d="M12 12l6.5 4"/></svg><span class="nlab">Concentration</span></div>'
    '<div class="nitem" data-nav="signaux"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="13" r="1.6" fill="currentColor" stroke="none"/><path d="M8.6 9.6a5 5 0 0 0 0 6.8"/><path d="M15.4 9.6a5 5 0 0 1 0 6.8"/><path d="M6 7a8.5 8.5 0 0 0 0 12"/><path d="M18 7a8.5 8.5 0 0 1 0 12"/></svg><span class="nlab">Signaux</span></div>'
    '<div class="nitem" data-nav="urgence"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4l8.5 15H3.5L12 4z"/><path d="M12 10v4.5"/><circle cx="12" cy="17.5" r="0.7" fill="currentColor" stroke="none"/></svg><span class="nlab">Urgence</span></div></nav>'
)

_CSS = """
  :root { --bg:#F9F6F3; --panel:#F9F6F3; --line:#E5E0DB; --line2:#CFC7BF; --ink:#1A1814; --ink2:#3A352D; --steel:#7E7770; --metal:#7E7770;
    --acc:#5A7548; --acc2:#5A7548; --id:#1A1814; --bear:#9B3A2E; --warn:#A87325;
    --fd:"Geist",ui-sans-serif,system-ui,sans-serif; --fb:"Geist",ui-sans-serif,system-ui,sans-serif; --fm:"Geist Mono",ui-monospace,SFMono-Regular,monospace; --fo:"Geist",ui-sans-serif,sans-serif;
    --elev:none;
    --glass:rgba(249,246,243,.92); --glass2:rgba(249,246,243,.88); --tape:rgba(249,246,243,.96); --barbg:#EDE8E2;
    --r1:4px; --r2:8px; --r3:12px;
    --s1:4px; --s2:8px; --s3:12px; --s4:20px; --s5:32px; --s6:52px; }
  body.midnight { --bg:#0E0D0B; --panel:#16140F; --line:#2A2520; --line2:#3D362E; --ink:#F1ECE3; --ink2:#CFC6B5; --steel:#8C8273; --metal:#8C8273;
    --acc:#88A671; --acc2:#88A671; --id:#F1ECE3; --bear:#C75B4F; --warn:#D6A058;
    --elev:0 12px 32px -18px rgba(0,0,0,.65);
    --glass:rgba(22,20,15,.85); --glass2:rgba(14,13,11,.7); --tape:rgba(14,13,11,.9); --barbg:#1F1C18; }
  * { box-sizing:border-box; }
  .dband { position:sticky; top:10px; z-index:45; display:flex; align-items:center; gap:13px; padding:11px 17px; margin:0 0 22px; border:1px solid var(--line2); border-radius:var(--r3); background:color-mix(in srgb,var(--panel) 85%,transparent); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); cursor:pointer; transition:border-color .15s,background .15s; }
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
  .sec-super { border:1px solid var(--line2); border-radius:var(--r2); padding:4px 8px 8px; margin-bottom:16px; background:color-mix(in srgb,var(--ink) 2%,transparent); }
  .sec-superh { display:flex; align-items:baseline; justify-content:space-between; gap:12px; padding:13px 12px 10px; flex-wrap:wrap; }
  .sec-supername { font-family:var(--fd); font-weight:500; font-size:18px; letter-spacing:0; color:var(--ink); }
  .sec-subwrap { display:flex; flex-direction:column; gap:4px; }
  .sec-super .sec-grp.sub { margin:0; border-left:2px solid var(--line); border-radius:0 10px 10px 0; }
  .sec-super .sec-grp.sub .sec-name { font-family:var(--fd); font-weight:600; font-size:13.5px; color:var(--steel); letter-spacing:0; }
  body { font-family:var(--fb); color:var(--ink); margin:0; display:flex; min-height:100vh; background:var(--bg); -webkit-font-smoothing:antialiased; transition:background .3s ease,color .3s ease; }
  .sidebar { width:78px; flex-shrink:0; background:transparent; border-right:1px solid var(--line); padding:20px 0; display:flex; flex-direction:column; align-items:center; position:sticky; top:0; align-self:flex-start; height:100vh; }
  .logo { display:flex; align-items:center; justify-content:center; margin-bottom:22px; padding:0; }
  .logo svg { width:66px; height:auto; color:var(--ink); }
  .logo .wm { display:none; }
  .nav { display:flex; flex-direction:column; gap:4px; align-items:center; width:100%; }
  .nitem { position:relative; display:flex; align-items:center; justify-content:center; width:48px; height:48px; border-radius:var(--r3); cursor:pointer; color:var(--steel); border-left:2px solid transparent; transition:.15s; }
  .nitem svg { width:26px; height:26px; }
  .nitem:hover { background:color-mix(in srgb,var(--ink) 4%,transparent); color:var(--ink); }
  .nitem.on { background:color-mix(in srgb,var(--id) 13%,transparent); color:var(--ink); border-left-color:var(--id); box-shadow:inset 0 0 22px -10px color-mix(in srgb,var(--id) 55%,transparent); }
  .nlab { position:absolute; left:56px; top:50%; transform:translateY(-50%); white-space:nowrap; background:var(--panel); border:1px solid var(--line2); border-radius:var(--r2); padding:7px 12px; font-family:var(--fb); font-size:12.5px; font-weight:500; color:var(--ink); opacity:0; pointer-events:none; transition:opacity .14s ease; z-index:80; box-shadow:0 10px 26px -12px #000; }
  .nitem:hover .nlab { opacity:1; }
  .foot { margin-top:auto; padding:12px 0 2px; display:flex; flex-direction:column; align-items:center; gap:7px; }
  .rfoot { display:flex; flex-direction:column; align-items:center; gap:6px; }
  .rfm { font-family:var(--fm); font-size:10.5px; color:var(--steel); }
  .rfmacro { width:8px; height:8px; border-radius:2px; }
  .dot { width:7px; height:7px; border-radius:50%; background:var(--acc); }
  .wrap { flex:1; display:flex; flex-direction:column; min-width:0; }
  .tape { overflow:hidden; white-space:nowrap; padding:11px 0; }
  .tape .track2 { display:inline-block; animation:scroll 60s linear infinite; }
  .tape:hover .track2 { animation-play-state:paused; }
  .tape .ti { font-family:var(--fm); font-size:11.5px; margin:0 30px; letter-spacing:.02em; } .tape .ti b { color:var(--ink); } .tape .ti .pos { color:var(--acc); } .tape .ti .neg { color:var(--bear); }
  @keyframes scroll { from{transform:translateX(0);} to{transform:translateX(-50%);} }
  .tape8k { background:var(--tape); padding:7px 0; } .tape8k .ti .warn { color:var(--warn); } .tape8k .track2 { animation-duration:75s; }
  .statedot { width:8px; height:8px; border-radius:50%; }
  .statedot.calm { background:var(--acc); color:var(--acc); } .statedot.warn { background:var(--warn); color:var(--warn); } .statedot.alert { background:var(--bear); color:var(--bear); }
  .main { padding:30px 52px 54px; max-width:1340px; }
  .phead { margin-bottom:22px; } .phead h2 { font-family:var(--fd); font-weight:300; font-size:32px; margin:0 0 6px; letter-spacing:.16em; text-transform:uppercase; color:var(--ink); } .phead .sub { font-family:var(--fb); font-weight:400; font-size:12px; letter-spacing:.04em; color:var(--steel); }
  [data-page] { display:none; } [data-page].active { display:block; animation:fadein .42s ease; } @keyframes fadein { from { opacity:0; transform:translateY(5px); } to { opacity:1; transform:none; } }
  .hero { background:var(--panel); border:1px solid var(--line2); border-radius:var(--r3); padding:28px 34px; margin-bottom:26px; display:flex; align-items:center; gap:28px; flex-wrap:wrap; }
  .hero .big { font-family:var(--fm); font-weight:500; font-size:42px; line-height:.95; letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .hero .big.pos { color:var(--acc); } .hero .big.neg { color:var(--bear); }
  .hero .hl { font-family:var(--fb); font-size:9.5px; letter-spacing:.2em; text-transform:uppercase; color:var(--steel); margin-bottom:8px; }
  .hero .hsub { font-size:12.5px; color:var(--steel); margin-top:6px; }
  .distbar { flex:1; min-width:240px; } .distline { display:flex; height:8px; border-radius:var(--r1); overflow:hidden; }
  .distline .g { background:oklch(0.72 0.16 150); } .distline .r { background:oklch(0.62 0.18 25); }
  .kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:18px; margin-bottom:26px; }
  .kpi { background:var(--panel); border:1px solid var(--line); border-radius:var(--r2); padding:13px 16px; }
  .kl { display:block; font-family:var(--fb); font-size:9px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:7px; }
  .kv { font-family:var(--fm); font-weight:500; font-size:28px; letter-spacing:-.01em; line-height:1; font-variant-numeric:tabular-nums; }
  .kv, .gvm, .big { color:var(--c, var(--ink)); }
  .kv.bear { --c:var(--bear); } .kv.acc { --c:var(--acc); } .kv.warn { --c:var(--warn); } .kv.id { --c:var(--id); }
  .kv.acc { color:var(--acc); } .kv.negc { color:var(--bear); } .kv.warn { color:var(--warn); } .kv.hot { color:#FB923C; } .kv.danger { color:var(--bear); } .kv.calm { color:var(--acc); }
  .kd { display:block; font-size:10px; color:var(--steel); margin-top:6px; }
  .cols { display:grid; grid-template-columns:1fr 1fr; gap:30px; align-items:start; }
  .colhead { display:flex; align-items:baseline; gap:9px; margin-bottom:12px; padding-left:2px; } .colhead .t { font-family:var(--fd); font-weight:500; font-size:14px; } .colhead .a { font-family:var(--fm); font-size:11.5px; color:var(--steel); }
  .sec-cols { display:grid; grid-template-columns:1fr 92px 96px 58px 72px 78px; gap:10px; padding:2px 16px 9px; font-family:var(--fb); font-size:9.5px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); border-bottom:1px solid var(--line); margin-bottom:12px; }
  .sec-cols .num { text-align:right; }
  .sec-grp { margin-bottom:22px; }
  .sec-h { display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin:0 4px 9px; }
  .sec-name { font-family:var(--fd); font-weight:500; font-size:16px; color:var(--ink); display:flex; align-items:center; gap:9px; }
  .sec-name::before { content:""; width:6px; height:6px; border-radius:2px; background:var(--id); }
  .sec-meta { font-family:var(--fm); font-size:11.5px; color:var(--steel); white-space:nowrap; }
  .sec-pl.pos { color:var(--acc); } .sec-pl.neg { color:var(--bear); }
  .sec-rows { display:flex; flex-direction:column; gap:1px; }
  .sec-row { display:grid; grid-template-columns:1fr 92px 96px 58px 72px 78px; gap:10px; align-items:center; padding:7px 16px; border-radius:var(--r2); font-family:var(--fm); font-size:12.5px; cursor:pointer; transition:background .12s; }
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
  .th-grid { display:grid; grid-template-columns:1fr 1fr; gap:13px; margin-bottom:6px; }
  .th-anchor { grid-column:1/-1; margin-top:8px; padding:8px 11px; border-radius:var(--r2); font-family:var(--fb); font-size:11.5px; line-height:1.5; color:var(--ink); border-left:2px solid var(--id); }
  .th-anchor.acc { border-left-color:var(--acc); background:color-mix(in srgb,var(--acc) 7%,transparent); }
  .th-anchor.warn { border-left-color:var(--warn); background:color-mix(in srgb,var(--warn) 9%,transparent); }
  /*THEME-ICO*/
  .modetgl .ico-sun { display:none; } body.midnight .modetgl .ico-moon { display:none; } body.midnight .modetgl .ico-sun { display:inline-block; }
  /*DVAL-STATE*/
  .dval.calm { color:var(--acc); } .dval.warn { color:#E0A33A; } .dval.danger { color:#EF4444; } .dval.mute { color:var(--steel); }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:var(--r2); padding:7px 24px; } .card.pad { padding:14px 18px; }
  .line { display:flex; justify-content:space-between; padding:9px 0; border-bottom:1px solid var(--line); font-size:13px; } .line:last-child { border-bottom:none; }
  .mono { font-family:var(--fm); font-weight:600; color:var(--ink); } .mono.pos { color:var(--acc); } .mono.neg { color:var(--bear); }
  .gauge { background:var(--panel); border:1px solid var(--line); border-radius:var(--r2); padding:16px 20px; margin-bottom:15px; }
  .ghead { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:11px; } .ghead .gl { font-family:var(--fb); font-weight:600; font-size:9.5px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); } .ghead .gv { font-family:var(--fm); font-weight:500; font-size:20px; letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .gtrack { position:relative; height:6px; border-radius:3px; background:linear-gradient(90deg in oklch,oklch(0.80 0.15 150),oklch(0.80 0.16 90) 52%,oklch(0.63 0.18 25)); }
  .glab { margin-top:9px; font-size:10px; color:var(--steel); display:flex; justify-content:space-between; font-family:var(--fm); letter-spacing:.08em; }
  .row { padding:9px 0; border-bottom:1px solid var(--line); opacity:0; animation:fade .45s ease forwards; } .row:last-child { border-bottom:none; }
  .row[data-tk] { cursor:pointer; } .row[data-tk]:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); }
  .rt { display:flex; justify-content:space-between; align-items:center; margin-bottom:9px; } .tk { font-family:var(--fm); font-weight:600; font-size:13px; }
  .tag { font-family:var(--fm); font-weight:600; font-size:11px; padding:3px 9px; border-radius:var(--r1); }
  .tag.up { color:var(--acc); background:rgba(55,224,160,.12); } .tag.acc2 { color:var(--acc2); background:rgba(61,139,255,.12); }
  .tag.down,.tag.danger { color:var(--bear); background:rgba(255,107,107,.13); } .tag.warn { color:var(--warn); background:rgba(255,176,32,.14); } .tag.calm { color:var(--steel); background:rgba(124,137,166,.12); } .tag.mute { color:var(--steel); background:rgba(124,137,166,.12); }
  /* Signal-subtil PRESAGE : axe gradient red->neutral->green + dot noir-bezel-gold */
  .axis { position:relative; height:5px; border-radius:2.5px; margin:14px 0 6px;
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
  .rs { display:flex; justify-content:space-between; margin-top:6px; font-size:11px; color:var(--steel); }
  .dwrap { display:flex; align-items:center; gap:24px; flex-wrap:wrap; }
  .legend { display:flex; flex-direction:column; gap:8px; flex:1; min-width:200px; }
  .empty { padding:30px 0; text-align:center; color:var(--steel); } .empty b { display:block; font-family:var(--fd); font-size:15px; color:var(--ink); margin-bottom:8px; }
  .dt { width:100%; border-collapse:collapse; font-size:12.5px; }
  .dt th { text-align:left; font-family:var(--fb); font-size:9.5px; letter-spacing:.12em; text-transform:uppercase; color:var(--steel); padding:8px 10px; border-bottom:1px solid var(--line2); cursor:pointer; user-select:none; }
  .dt th.num { text-align:right; } .dt th:hover { color:var(--ink); }
  .dt td { padding:8px 10px; border-bottom:1px solid var(--line); } .dt td.num { text-align:right; font-family:var(--fm); }
  .dt td.tk { font-family:var(--fm); font-weight:600; } .dt tr:hover td { background:color-mix(in srgb,var(--ink) 2.5%,transparent); }
  .dt td.pos { color:var(--acc); } .dt td.neg { color:var(--bear); }
  .bdg { display:inline-block; margin-left:7px; font-family:var(--fb); font-size:8px; letter-spacing:.1em; text-transform:uppercase; color:var(--id); border:1px solid rgba(61,139,255,.4); border-radius:3px; padding:1px 5px; vertical-align:middle; }
  .dt tr.prev td { opacity:.72; } .dt tr.prev td.tk { color:var(--id); }
  .nm { display:block; font-size:10px; font-weight:400; color:var(--steel); margin-top:2px; }
  .ph3 { font-family:var(--fb); font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--steel); margin:0 0 12px; }
  .dtier { font-family:var(--fb); font-size:9.5px; letter-spacing:.12em; text-transform:uppercase; color:var(--steel); margin:16px 0 6px; padding-bottom:6px; border-bottom:1px solid var(--line); }
  .dlist > .dtier:first-child { margin-top:0; }
  [data-tip]{position:relative;cursor:help}
  [data-tip]:hover::after{content:attr(data-tip);position:absolute;left:0;top:calc(100% + 4px);background:var(--panel);color:var(--ink);border:1px solid var(--line2);padding:7px 11px;border-radius:var(--r1);font-family:var(--fb);font-size:11px;font-weight:400;letter-spacing:0;text-transform:none;white-space:normal;max-width:300px;width:max-content;z-index:1000;box-shadow:0 6px 18px rgba(0,0,0,.5);pointer-events:none;line-height:1.4}
  body.midnight [data-tip]:hover::after{box-shadow:0 6px 18px rgba(0,0,0,.55)}
  .drow { display:grid; grid-template-columns:14px 1fr auto auto auto; align-items:center; gap:10px; padding:7px 0; font-size:13px; }
  .ddot { width:8px; height:8px; border-radius:50%; }
  .ddot.calm { background:#37E0A0; } .ddot.warn { background:#FACC15; }
  .ddot.hot { background:#FB923C; } .ddot.danger { background:#EF4444; }
  .dname { color:var(--ink); } .dval { font-family:var(--fm); text-align:right; color:var(--ink); } .dp { font-family:var(--fm); font-size:10px; color:var(--steel); }
  .stale { font-family:var(--fb); font-size:9px; color:var(--steel); opacity:.7; text-transform:uppercase; letter-spacing:.08em; }
  @keyframes fade { to { opacity:1; } }
  .noanim [data-page].active, .noanim .row { animation:none !important; }
  .noanim .row { opacity:1 !important; }
  .plan { background:var(--panel); border:1px solid var(--line); border-radius:var(--r2); padding:15px 20px; margin-bottom:18px; }
  .plan-h { font-family:var(--fb); font-size:9.5px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:13px; }
  .plan-row { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
  .pi { display:flex; flex-direction:column; gap:4px; padding-left:13px; border-left:2px solid var(--line2); border-radius:0; }
  .pi.danger { border-left-color:var(--bear); } .pi.warn { border-left-color:var(--warn); } .pi.calm { border-left-color:var(--acc); } .pi.size { border-left-color:var(--steel); }
  .pn { font-family:var(--fm); font-weight:500; font-size:24px; line-height:1; letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .pi.danger .pn { color:var(--bear); } .pi.warn .pn { color:var(--warn); } .pi.calm .pn { color:var(--acc); } .pi.size .pn { color:var(--metal); }
  .pl { font-size:11.5px; color:var(--ink); } .pt { font-family:var(--fm); font-size:10.5px; color:var(--steel); }
  .dt tbody tr:not(.prev) { cursor:pointer; }
  .loupe { position:fixed; inset:0; z-index:60; display:none; align-items:center; justify-content:center; background:rgba(6,10,18,.72); backdrop-filter:blur(6px); padding:34px; }
  .loupe.open { display:flex; }
  .loupe-card { position:relative; width:min(560px,100%); max-height:86vh; overflow:auto; background:var(--panel); border:1px solid var(--line2); border-radius:var(--r3); padding:28px 30px; box-shadow:0 30px 90px -20px #000; }
  .loupe-x { position:absolute; top:14px; right:18px; background:none; border:none; color:var(--steel); font-size:26px; line-height:1; cursor:pointer; }
  .loupe-x:hover { color:var(--ink); }
  .lp-h { display:flex; align-items:baseline; gap:11px; }
  .lp-tk { font-family:var(--fm); font-weight:500; font-size:22px; letter-spacing:.02em; color:var(--ink); }
  .lp-nm { font-size:13px; color:var(--steel); }
  .lp-meta { font-family:var(--fm); font-size:11px; color:var(--steel); margin:6px 0 18px; }
  .lp-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
  .lp-mom { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
  .lp-stat { background:var(--panel); border:1px solid var(--line); border-radius:var(--r2); padding:11px 13px; }
  .lp-sl { font-family:var(--fb); font-size:8.5px; letter-spacing:.14em; text-transform:uppercase; color:var(--steel); }
  .lp-sv { font-family:var(--fm); font-weight:500; font-size:18px; letter-spacing:-.01em; margin-top:5px; font-variant-numeric:tabular-nums; }
  .lp-sec { font-family:var(--fb); font-size:10px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin:20px 0 10px; border-top:1px solid var(--line); padding-top:14px; }
  .lp-score { display:flex; align-items:center; gap:10px; margin:8px 0; font-size:12px; }
  .lp-score .ln { width:92px; color:var(--steel); }
  .lp-score .bar { flex:1; height:6px; background:var(--barbg); border-radius:3px; overflow:hidden; }
  .lp-score .bf { display:block; height:100%; background:linear-gradient(90deg,#00E0FF,#37E0A0); }
  .lp-score .vv { font-family:var(--fm); width:32px; text-align:right; }
  .lp-ex { font-size:12.5px; color:var(--ink); line-height:1.6; opacity:.82; }
  .lp-empty { font-size:12px; color:var(--steel); padding:6px 0; }
  .tkc { cursor:pointer; transition:color .12s; } .tkc:hover { color:var(--id); }
  .lp-badge { display:inline-block; font-family:var(--fb); font-size:10px; letter-spacing:.1em; text-transform:uppercase; padding:2px 8px; border-radius:var(--r1); border:1px solid currentColor; }
  .lp-badge.held { color:var(--acc); } .lp-badge.watch { color:var(--warn); } .lp-badge.univ { color:var(--acc2); } .lp-badge.out { color:var(--steel); }
  .sbwrap { display:flex; flex-direction:column; gap:24px; }
  .sb-top { display:grid; grid-template-columns:repeat(3,1fr); gap:32px; width:100%; padding:8px 4px 16px; border-bottom:1px solid var(--line); }
  .sb-kpi { display:flex; flex-direction:column; gap:6px; }
  .sb-kl { font-family:var(--fb); font-weight:600; font-size:9.5px; letter-spacing:.18em; color:var(--steel); }
  .sb-kv { font-family:var(--fm); font-weight:500; font-size:20px; color:var(--ink); letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .sb-bars { display:flex; flex-direction:column; gap:2px; width:100%; }
  .sb-row { display:grid; grid-template-columns:minmax(160px,1.4fr) minmax(120px,3fr) 50px 70px; align-items:center; gap:16px; padding:10px 6px; border-radius:var(--r1); cursor:pointer; transition:background .15s,opacity .2s; }
  .sb-row:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); }
  .sb-row.on { background:color-mix(in srgb,var(--ink) 5%,transparent); }
  .sb-bars:has(.sb-row.on) .sb-row.dim { opacity:.28; }
  .sb-row-name { display:flex; align-items:center; gap:10px; min-width:0; }
  .sb-row-dot { width:8px; height:8px; border-radius:50%; flex:0 0 auto; }
  .sb-row-label { font-family:var(--fb); font-weight:500; font-size:13px; color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .sb-row-bar { height:4px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:2px; overflow:hidden; }
  .sb-row-fill { height:100%; border-radius:2px; transition:width .4s cubic-bezier(.2,.8,.2,1); }
  .sb-row-pct { font-family:var(--fm); font-weight:500; font-size:13px; color:var(--ink); text-align:right; font-variant-numeric:tabular-nums; }
  .sb-row-val { font-family:var(--fm); font-weight:400; font-size:12px; color:var(--steel); text-align:right; font-variant-numeric:tabular-nums; }
  #sb-panel { width:100%; font-size:13px; padding:12px 0 0; }
  #sb-panel:empty { display:none; }
  .sbrow { display:flex; justify-content:space-between; align-items:center; padding:7px 0; border-bottom:.5px solid var(--line); cursor:pointer; } .sbrow:last-child { border-bottom:none; } .sbrow:hover { background:color-mix(in srgb,var(--ink) 2.5%,transparent); }
  .qs { position:fixed; inset:0; z-index:70; display:none; align-items:flex-start; justify-content:center; background:rgba(6,10,18,.72); backdrop-filter:blur(6px); padding:12vh 20px 20px; }
  .qs.open { display:flex; }
  .qs-card { width:min(560px,100%); background:var(--panel); border:1px solid var(--line2); border-radius:var(--r3); box-shadow:0 30px 90px -20px #000; overflow:hidden; }
  #qs-input { width:100%; box-sizing:border-box; background:transparent; border:none; outline:none; color:var(--ink); font-family:var(--fb); font-size:17px; padding:18px 20px; border-bottom:1px solid var(--line); }
  #qs-input::placeholder { color:var(--steel); }
  #qs-res { max-height:50vh; overflow:auto; }
  .qs-row { display:flex; align-items:center; gap:12px; padding:11px 20px; cursor:pointer; border-bottom:.5px solid var(--line); }
  .qs-row:last-child { border-bottom:none; } .qs-row.on, .qs-row:hover { background:rgba(55,224,160,.10); }
  .qs-tk { font-family:var(--fm); font-weight:600; font-size:13px; width:78px; }
  .qs-nm { flex:1; font-size:13px; color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .qs-st { font-family:var(--fb); font-size:9.5px; letter-spacing:.08em; text-transform:uppercase; color:var(--steel); }
  .qs-st.held { color:var(--acc); } .qs-st.watch { color:var(--warn); } .qs-st.core, .qs-st.extended { color:var(--acc2); }
  .qs-empty { padding:22px 20px; color:var(--steel); font-size:13px; text-align:center; }
  .hero.posture { display:block; }
  .hero.posture .plan-row { margin-top:14px; gap:24px; }
  .hero.posture .pn { font-size:29px; }
  .hrow { display:grid; grid-template-columns:1.3fr 1fr; gap:18px; margin-bottom:20px; align-items:stretch; }
  .hrow .hero.posture { margin-bottom:0; height:100%; }
  .pfcard { background:var(--panel); border:1px solid var(--line2); border-radius:var(--r3); padding:20px 24px; display:flex; flex-direction:column; }
  .pfcard .v { font-family:var(--fm); font-weight:500; font-size:30px; letter-spacing:-.01em; line-height:1; margin:8px 0 5px; color:var(--ink); font-variant-numeric:tabular-nums; }
  .pfcard .d { font-family:var(--fm); font-size:14px; font-weight:600; } .pfcard .d.pos { color:var(--acc); } .pfcard .d.neg { color:var(--bear); }
  .pfcard .distline { margin:16px 0 0; height:20px; gap:3px; border-radius:0; overflow:visible; }
  .pfcard .distline .g { background:var(--acc); border-radius:var(--r1); }
  .pfcard .distline .r { background:var(--bear); border-radius:var(--r1); }
  .pfcard .distcap { display:flex; justify-content:space-between; font-family:var(--fm); font-size:11.5px; margin-top:9px; }
  .pfcard .distcap .cg { color:var(--acc); font-weight:600; }
  .pfcard .distcap .cr { color:var(--bear); font-weight:600; }
  .pfcard .sub2 { font-size:11.5px; color:var(--steel); margin-top:auto; padding-top:13px; } .pfcard .sub2 b { color:var(--ink); font-weight:600; }
  @media (max-width:980px) { .hrow { grid-template-columns:1fr; } }
  /* Star treatment - hero row au top de Vue d'ensemble */
  .hrow.star { gap:22px; margin-bottom:28px; }
  .hrow.star .pfcard { padding:30px 36px; }
  .hrow.star .pfcard .hl { font-size:10.5px; letter-spacing:.22em; }
  .hrow.star .pfcard .v { font-size:46px; margin:14px 0 9px; line-height:.95; }
  .hrow.star .pfcard .d { font-size:17px; }
  .hrow.star .pfcard .distline { margin-top:22px; height:24px; }
  .hrow.star .pfcard .distcap { font-size:12.5px; margin-top:12px; }
  .hrow.star .pfcard .sub2 { font-size:12.5px; padding-top:18px; }
  .hrow.star .hero.posture { padding:30px 36px; }
  .hrow.star .hero.posture .hl { font-size:10.5px; letter-spacing:.22em; }
  .hrow.star .hero.posture .pn { font-size:42px; line-height:.95; }
  .hrow.star .hero.posture .plan-row { margin-top:18px; gap:30px; }
  /* Sprint 5 - Note du portefeuille */
  .gradecard .ghead { display:flex; align-items:center; gap:22px; margin:14px 0 18px; padding-bottom:18px; border-bottom:1px solid var(--line); }
  .gradecard .gletter { font-family:var(--fm); font-weight:500; font-size:56px; line-height:.9; letter-spacing:-.02em; padding:0 18px; border-radius:var(--r2); }
  .gradecard .gletter.good { color:var(--acc); }
  .gradecard .gletter.warn { color:#c89b00; }
  .gradecard .gletter.bad { color:var(--bear); }
  .gradecard .gscore { flex:1; display:flex; flex-direction:column; gap:6px; }
  .gradecard .gscoreval { font-size:28px; font-weight:500; letter-spacing:-.01em; line-height:1; color:var(--ink); }
  .gradecard .gscoremax { color:var(--steel); font-weight:400; font-size:16px; margin-left:2px; }
  .gradecard .gscorebar { height:6px; background:color-mix(in srgb,var(--ink) 6%,transparent); border-radius:var(--r1); overflow:hidden; }
  .gradecard .gscorefill { height:100%; border-radius:var(--r1); transition:width .4s ease; }
  .gradecard .gscorefill.good { background:var(--acc); }
  .gradecard .gscorefill.warn { background:#c89b00; }
  .gradecard .gscorefill.bad { background:var(--bear); }
  .gradecard .gbody { display:grid; gap:12px; }
  .gradecard .grow { display:grid; grid-template-columns:200px 1fr 180px; align-items:center; gap:14px; }
  .gradecard .glab { font-family:var(--fm); font-size:12.5px; color:var(--steel); font-weight:500; }
  .gradecard .gaxis { position:relative; height:6px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r1); }
  .gradecard .gfill { position:absolute; left:0; top:0; height:100%; border-radius:var(--r1); }
  .gradecard .gfill.good { background:var(--acc); }
  .gradecard .gfill.bad { background:var(--bear); opacity:.55; }
  .gradecard .gtgt { position:absolute; top:-2px; bottom:-2px; width:2px; background:var(--ink); opacity:.6; }
  .gradecard .gnum { display:flex; align-items:center; gap:10px; justify-content:flex-end; font-size:12px; color:var(--ink); }
  .gradecard .gnum .gt { color:var(--steel); font-size:11px; }
  @media (max-width:980px) { .gradecard .grow { grid-template-columns:1fr; gap:4px; } .gradecard .gnum { justify-content:flex-start; } }
  /* Sub-notes Construction + Fragilite (glossaire canonique) */
  .gradecard .gsplit { display:grid; grid-template-columns:1fr 1fr; gap:24px; margin-top:18px; padding-top:18px; border-top:1px solid var(--line); }
  .gradecard .gsub { display:flex; flex-direction:column; gap:10px; }
  .gradecard .gsubh { font-family:var(--fb); font-size:10.5px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); font-weight:600; }
  .gradecard .gsubscore { font-size:32px; font-weight:500; line-height:1; letter-spacing:-.02em; }
  .gradecard .gsubscore.good { color:var(--acc); }
  .gradecard .gsubscore.warn { color:#c89b00; }
  .gradecard .gsubscore.bad { color:var(--bear); }
  .gradecard .gsubmax { color:var(--steel); font-size:14px; margin-left:1px; font-weight:400; }
  @media (max-width:980px) { .gradecard .gsplit { grid-template-columns:1fr; gap:14px; } }
  /* Sprint 5/6 - Copilot interventions panel */
  .copilotcard .cp-row { padding:12px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .copilotcard .cp-row:last-child { border-bottom:none; }
  .copilotcard .cp-head { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:6px; }
  .copilotcard .cp-tk { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); }
  .copilotcard .cp-dtype { font-family:var(--fb); font-size:10px; letter-spacing:.15em; text-transform:uppercase; color:var(--steel); }
  .copilotcard .cp-ver { font-family:var(--fb); font-size:10px; letter-spacing:.15em; font-weight:600; padding:2px 6px; border-radius:var(--r1); }
  .copilotcard .cp-ver.ok { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .copilotcard .cp-ver.warn { background:color-mix(in srgb,#c89b00 14%,transparent); color:#c89b00; }
  .copilotcard .cp-ver.bad { background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); }
  .copilotcard .cp-date { font-family:var(--fm); font-size:11px; color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .copilotcard .cp-anc { font-family:var(--fm); font-size:12px; color:var(--ink); line-height:1.45; opacity:.85; }
  .copilotcard .cp-outc { display:inline-block; margin-top:5px; font-family:var(--fb); font-size:10px; letter-spacing:.12em; padding:2px 6px; border-radius:var(--r1); }
  .copilotcard .cp-outc.ok { background:color-mix(in srgb,var(--acc) 12%,transparent); color:var(--acc); }
  .copilotcard .cp-outc.bad { background:color-mix(in srgb,var(--bear) 12%,transparent); color:var(--bear); }
  /* Sprint 6 - Narrative clusters panel */
  .narrativecard .nv-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:12px; margin:14px 0 18px; }
  .narrativecard .nv-cluster { background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); padding:14px 16px; }
  .narrativecard .nv-cl-head { display:flex; align-items:baseline; gap:8px; margin-bottom:6px; flex-wrap:wrap; }
  .narrativecard .nv-cl-name { font-family:var(--fm); font-weight:600; font-size:12.5px; color:var(--ink); flex:1; min-width:0; }
  .narrativecard .nv-cl-overlap { font-family:var(--fb); font-size:9.5px; letter-spacing:.12em; padding:2px 6px; border-radius:var(--r1); font-weight:600; }
  .narrativecard .nv-cl-overlap.high { background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); }
  .narrativecard .nv-cl-overlap.mid { background:color-mix(in srgb,#c89b00 14%,transparent); color:#c89b00; }
  .narrativecard .nv-cl-overlap.low { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .narrativecard .nv-cl-n { font-family:var(--fm); font-size:10.5px; color:var(--steel); font-variant-numeric:tabular-nums; }
  .narrativecard .nv-cl-tks { font-family:var(--fm); font-size:11px; color:var(--ink); margin-bottom:6px; opacity:.8; font-variant-numeric:tabular-nums; }
  .narrativecard .nv-cl-driv { font-family:var(--fm); font-size:11.5px; color:var(--steel); line-height:1.4; }
  .narrativecard .nv-split { display:grid; grid-template-columns:1fr 1fr; gap:18px; border-top:1px solid var(--line); padding-top:14px; }
  .narrativecard .nv-h { font-family:var(--fb); font-size:10.5px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:8px; }
  .narrativecard .nv-line { display:flex; align-items:baseline; gap:8px; padding:6px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); font-size:11.5px; }
  .narrativecard .nv-line:last-child { border-bottom:none; }
  .narrativecard .nv-tk { font-family:var(--fm); font-weight:600; color:var(--ink); min-width:70px; }
  .narrativecard .nv-with { font-family:var(--fm); color:var(--steel); font-size:10.5px; }
  .narrativecard .nv-why { font-family:var(--fm); color:var(--ink); opacity:.85; line-height:1.4; flex:1; }
  @media (max-width:980px) { .narrativecard .nv-split { grid-template-columns:1fr; } }
  /* Sprint 9 - Conversations recentes */
  .conversationscard .cv-row { padding:10px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .conversationscard .cv-row:last-child { border-bottom:none; }
  .conversationscard .cv-meta { display:flex; align-items:center; gap:8px; margin-bottom:5px; font-family:var(--fb); font-size:9.5px; letter-spacing:.14em; text-transform:uppercase; }
  .conversationscard .cv-role { font-weight:600; padding:2px 6px; border-radius:var(--r1); }
  .conversationscard .cv-role.user { background:color-mix(in srgb,var(--id) 14%,transparent); color:var(--id); }
  .conversationscard .cv-role.assistant { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--ink); }
  .conversationscard .cv-surf { color:var(--steel); }
  .conversationscard .cv-date { margin-left:auto; color:var(--steel); font-variant-numeric:tabular-nums; }
  .conversationscard .cv-content { font-family:var(--fm); font-size:12px; line-height:1.45; color:var(--ink); opacity:.85; }
  .conversationscard .cv-user .cv-content { color:var(--ink); opacity:.95; }
  /* Sprint 9.d - Soft signals panel */
  .chatsigcard .cs-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:14px; margin-top:14px; }
  .chatsigcard .cs-group { background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); padding:12px 14px; }
  .chatsigcard .cs-kind { font-family:var(--fb); font-size:9.5px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:10px; }
  .chatsigcard .cs-row { padding:8px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .chatsigcard .cs-row:last-child { border-bottom:none; }
  .chatsigcard .cs-meta { display:flex; align-items:baseline; gap:8px; margin-bottom:4px; }
  .chatsigcard .cs-target { font-family:var(--fm); font-weight:600; font-size:11.5px; color:var(--ink); }
  .chatsigcard .cs-val { font-family:var(--fm); font-size:10.5px; font-variant-numeric:tabular-nums; padding:1px 6px; border-radius:var(--r1); margin-left:auto; }
  .chatsigcard .cs-val.neg { background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); }
  .chatsigcard .cs-val.pos { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .chatsigcard .cs-val.neu { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--steel); }
  .chatsigcard .cs-quote { font-family:var(--fm); font-size:11.5px; font-style:italic; color:var(--ink); opacity:.85; line-height:1.4; margin-bottom:3px; }
  .chatsigcard .cs-note { font-family:var(--fm); font-size:10.5px; color:var(--steel); line-height:1.4; }
  /* Layer 2 - Conceptions du bot */
  .conceptionscard .bc-row { padding:14px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .conceptionscard .bc-row:last-child { border-bottom:none; }
  .conceptionscard .bc-head { display:flex; align-items:baseline; gap:10px; margin-bottom:7px; flex-wrap:wrap; }
  .conceptionscard .bc-target { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); }
  .conceptionscard .bc-kind { font-family:var(--fb); font-size:9.5px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); }
  .conceptionscard .bc-conv { font-family:var(--fm); font-size:10.5px; font-variant-numeric:tabular-nums; padding:1px 6px; border-radius:var(--r1); font-weight:600; }
  .conceptionscard .bc-conv.high { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .conceptionscard .bc-conv.mid { background:color-mix(in srgb,#c89b00 14%,transparent); color:#c89b00; }
  .conceptionscard .bc-conv.low { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--steel); }
  .conceptionscard .bc-val { font-family:var(--fm); font-size:10.5px; font-variant-numeric:tabular-nums; padding:1px 6px; border-radius:var(--r1); }
  .conceptionscard .bc-val.neg { background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); }
  .conceptionscard .bc-val.pos { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .conceptionscard .bc-val.neu { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--steel); }
  .conceptionscard .bc-n { font-family:var(--fm); font-size:10px; color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .conceptionscard .bc-text { font-family:var(--fm); font-size:12.5px; line-height:1.55; color:var(--ink); opacity:.88; }
  /* Layer 3 - Preferences calibrees */
  .preferencescard .pr-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:14px; margin-top:14px; }
  .preferencescard .pr-group { background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); padding:12px 14px; }
  .preferencescard .pr-h { display:flex; align-items:baseline; gap:8px; margin-bottom:10px; }
  .preferencescard .pr-kind { font-family:var(--fb); font-size:10px; letter-spacing:.16em; text-transform:uppercase; color:var(--ink); font-weight:600; }
  .preferencescard .pr-meta { font-family:var(--fm); font-size:10px; color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .preferencescard .pr-row { display:flex; align-items:baseline; gap:10px; padding:5px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 3%,transparent); font-size:11.5px; }
  .preferencescard .pr-row:last-child { border-bottom:none; }
  .preferencescard .pr-key { font-family:var(--fm); font-weight:500; color:var(--ink); min-width:60px; }
  .preferencescard .pr-mid { font-family:var(--fm); font-size:10px; color:var(--steel); font-variant-numeric:tabular-nums; }
  .preferencescard .pr-num { margin-left:auto; font-variant-numeric:tabular-nums; }
  .preferencescard .pr-num.pos { color:var(--acc); }
  .preferencescard .pr-num.neg { color:var(--bear); }
  .preferencescard .pr-num.neu { color:var(--steel); }
  .preferencescard .pr-win { font-family:var(--fm); font-size:10.5px; color:var(--steel); min-width:50px; text-align:right; }
  /* Sprint 12 - Ticker axes */
  .axescard .ax-group { background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); padding:14px 16px; margin-top:14px; }
  .axescard .ax-h { display:flex; align-items:baseline; gap:10px; margin-bottom:10px; padding-bottom:8px; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .axescard .ax-macro { font-family:var(--fm); font-weight:600; font-size:12.5px; color:var(--ink); }
  .axescard .ax-n { font-family:var(--fm); font-size:10.5px; color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .axescard .ax-row { display:grid; grid-template-columns:78px 1fr; gap:14px; padding:8px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .axescard .ax-row:last-child { border-bottom:none; }
  .axescard .ax-tk { font-family:var(--fm); font-weight:600; font-size:12px; color:var(--ink); }
  .axescard .ax-fields { display:flex; flex-direction:column; gap:3px; }
  .axescard .ax-f { font-family:var(--fm); font-size:11px; color:var(--ink); opacity:.82; line-height:1.4; }
  .axescard .ax-l { display:inline-block; font-family:var(--fb); font-size:9px; letter-spacing:.14em; text-transform:uppercase; color:var(--steel); width:50px; }
  /* Sprint 13 - Factor exposures + Stress + Trajectory */
  .factorscard .fe-row { padding:12px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .factorscard .fe-row:last-child { border-bottom:none; }
  .factorscard .fe-head { display:flex; align-items:baseline; gap:10px; margin-bottom:5px; }
  .factorscard .fe-name { font-family:var(--fm); font-weight:500; font-size:13px; color:var(--ink); flex:1; }
  .factorscard .fe-pct { font-family:var(--fm); font-size:14px; font-weight:600; font-variant-numeric:tabular-nums; }
  .factorscard .fe-pct.high { color:var(--bear); }
  .factorscard .fe-pct.mid { color:#c89b00; }
  .factorscard .fe-pct.low { color:var(--acc); }
  .factorscard .fe-eur { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; min-width:75px; text-align:right; }
  .factorscard .fe-bar { height:5px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r1); overflow:hidden; margin:4px 0 6px; }
  .factorscard .fe-fill { height:100%; border-radius:var(--r1); }
  .factorscard .fe-fill.high { background:var(--bear); }
  .factorscard .fe-fill.mid { background:#c89b00; }
  .factorscard .fe-fill.low { background:var(--acc); }
  .factorscard .fe-tks { font-family:var(--fm); font-size:10.5px; color:var(--steel); font-variant-numeric:tabular-nums; }
  .stresscard .st-row { display:flex; align-items:baseline; gap:14px; padding:10px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .stresscard .st-row:last-child { border-bottom:none; }
  .stresscard .st-name { font-family:var(--fm); font-size:12px; color:var(--ink); flex:1; }
  .stresscard .st-impact { display:flex; align-items:baseline; gap:10px; }
  .stresscard .st-pct { font-family:var(--fm); font-size:13px; font-weight:600; font-variant-numeric:tabular-nums; min-width:60px; text-align:right; }
  .stresscard .st-pct.pos { color:var(--acc); }
  .stresscard .st-pct.danger { color:var(--bear); }
  .stresscard .st-pct.warn { color:#c89b00; }
  .stresscard .st-pct.neu { color:var(--steel); }
  .stresscard .st-eur { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; min-width:90px; text-align:right; }
  .stresscard .st-n { font-family:var(--fm); font-size:10px; color:var(--steel); min-width:40px; text-align:right; font-variant-numeric:tabular-nums; }
  .trajcard .tr-hero { font-family:var(--fm); font-size:18px; font-weight:500; color:var(--ink); padding:14px 0 16px; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); margin-bottom:8px; display:flex; align-items:baseline; gap:8px; }
  .trajcard .tr-row { display:flex; align-items:baseline; gap:10px; padding:7px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 3%,transparent); font-size:11.5px; }
  .trajcard .tr-row:last-child { border-bottom:none; }
  .trajcard .tr-key { font-family:var(--fm); color:var(--ink); flex:1; }
  .trajcard .tr-from, .trajcard .tr-to { font-variant-numeric:tabular-nums; color:var(--ink); opacity:.85; min-width:48px; text-align:right; }
  .trajcard .tr-arr { color:var(--steel); font-size:11px; }
  .trajcard .tr-delta { font-variant-numeric:tabular-nums; min-width:64px; text-align:right; font-weight:500; }
  .trajcard .tr-delta.pos { color:var(--acc); }
  .trajcard .tr-delta.neg { color:var(--bear); }
  .trajcard .tr-delta.neu { color:var(--steel); }
  /* Sprint 14 - SPOF + Mauboussin + Valo */
  .spofcard .sp-row { padding:12px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .spofcard .sp-row:last-child { border-bottom:none; }
  .spofcard .sp-head { display:flex; align-items:baseline; gap:10px; margin-bottom:5px; }
  .spofcard .sp-node { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); flex:1; }
  .spofcard .sp-pct { font-family:var(--fm); font-size:14px; font-weight:600; font-variant-numeric:tabular-nums; }
  .spofcard .sp-pct.high { color:var(--bear); }
  .spofcard .sp-pct.mid { color:#c89b00; }
  .spofcard .sp-pct.low { color:var(--acc); }
  .spofcard .sp-eur { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; min-width:80px; text-align:right; }
  .spofcard .sp-n { font-family:var(--fm); font-size:10.5px; color:var(--steel); font-variant-numeric:tabular-nums; min-width:38px; text-align:right; }
  .spofcard .sp-bar { height:5px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r1); overflow:hidden; margin:4px 0 6px; }
  .spofcard .sp-fill { height:100%; border-radius:var(--r1); }
  .spofcard .sp-fill.high { background:var(--bear); }
  .spofcard .sp-fill.mid { background:#c89b00; }
  .spofcard .sp-fill.low { background:var(--acc); }
  .spofcard .sp-deps { font-family:var(--fm); font-size:10.5px; color:var(--steel); font-variant-numeric:tabular-nums; }
  .mauboussincard .ms-row { display:grid; grid-template-columns:70px 50px 65px 75px 75px 65px; align-items:center; gap:10px; padding:7px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 3%,transparent); font-size:11.5px; }
  .mauboussincard .ms-row:last-child { border-bottom:none; }
  .mauboussincard .ms-tk { font-family:var(--fm); font-weight:600; color:var(--ink); }
  .mauboussincard .ms-conv { font-family:var(--fm); color:var(--steel); }
  .mauboussincard .ms-fade { font-family:var(--fm); padding:1px 5px; border-radius:var(--r1); font-size:10.5px; text-align:center; }
  .mauboussincard .ms-fade.low { background:color-mix(in srgb,var(--acc) 12%,transparent); color:var(--acc); }
  .mauboussincard .ms-fade.mid { background:color-mix(in srgb,#c89b00 12%,transparent); color:#c89b00; }
  .mauboussincard .ms-fade.high { background:color-mix(in srgb,var(--bear) 12%,transparent); color:var(--bear); }
  .mauboussincard .ms-target, .mauboussincard .ms-actual { font-family:var(--fm); color:var(--ink); opacity:.85; text-align:right; font-variant-numeric:tabular-nums; }
  .mauboussincard .ms-gap { font-family:var(--fm); font-weight:600; text-align:right; font-variant-numeric:tabular-nums; }
  .mauboussincard .ms-gap.pos { color:var(--acc); }
  .mauboussincard .ms-gap.neg { color:var(--bear); }
  .mauboussincard .ms-gap.neu { color:var(--steel); }
  .valocard .vb-row { padding:12px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .valocard .vb-row:last-child { border-bottom:none; }
  .valocard .vb-head { display:flex; align-items:baseline; gap:10px; margin-bottom:6px; }
  .valocard .vb-tk { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); }
  .valocard .vb-pe { font-family:var(--fm); font-size:11.5px; color:var(--bear); font-variant-numeric:tabular-nums; margin-left:auto; }
  .valocard .vb-priced { font-family:var(--fm); font-size:12px; color:var(--ink); opacity:.9; line-height:1.45; margin-bottom:4px; font-style:italic; }
  .valocard .vb-rat { font-family:var(--fm); font-size:11px; color:var(--steel); line-height:1.4; }
  @media (max-width:980px) { .mauboussincard .ms-row { grid-template-columns:60px 40px 1fr 65px; } .mauboussincard .ms-target, .mauboussincard .ms-actual { display:none; } }
  /* Sprint 15 - Kill-criteria */
  .killcard .kc-row { padding:12px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .killcard .kc-row:last-child { border-bottom:none; }
  .killcard .kc-row.triggered { border-left:3px solid var(--bear); padding-left:12px; margin-left:-12px; }
  .killcard .kc-row.at_risk { border-left:3px solid #c89b00; padding-left:12px; margin-left:-12px; }
  .killcard .kc-head { display:flex; align-items:baseline; gap:10px; margin-bottom:5px; }
  .killcard .kc-tk { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); }
  .killcard .kc-status { font-family:var(--fb); font-size:9.5px; letter-spacing:.15em; text-transform:uppercase; font-weight:600; padding:2px 7px; border-radius:var(--r1); }
  .killcard .kc-status.triggered { background:color-mix(in srgb,var(--bear) 16%,transparent); color:var(--bear); }
  .killcard .kc-status.at_risk { background:color-mix(in srgb,#c89b00 16%,transparent); color:#c89b00; }
  .killcard .kc-conf { font-family:var(--fm); font-size:10.5px; color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .killcard .kc-reason { font-family:var(--fm); font-size:12px; color:var(--ink); opacity:.88; line-height:1.5; margin-bottom:4px; }
  .killcard .kc-ev { font-family:var(--fm); font-size:10.5px; color:var(--steel); font-variant-numeric:tabular-nums; }
  /* Sprint 16 - Wrapper PEA/CTO + FX + Benchmark */
  .wrappercard .wr-alloc { display:flex; gap:18px; margin:14px 0 18px; padding-bottom:14px; border-bottom:1px solid var(--line); }
  .wrappercard .wr-row { flex:1; padding:12px 14px; background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); display:flex; flex-direction:column; gap:4px; }
  .wrappercard .wr-key { font-family:var(--fb); font-size:10px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); font-weight:600; }
  .wrappercard .wr-pct { font-family:var(--fm); font-size:22px; font-weight:500; color:var(--ink); font-variant-numeric:tabular-nums; }
  .wrappercard .wr-eur { font-family:var(--fm); font-size:11px; color:var(--steel); font-variant-numeric:tabular-nums; }
  .wrappercard .wr-section { margin-top:14px; }
  .wrappercard .wr-sh { font-family:var(--fb); font-size:10px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin-bottom:8px; }
  .wrappercard .wr-mis { display:flex; align-items:baseline; gap:10px; padding:6px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 3%,transparent); font-size:11.5px; }
  .wrappercard .wr-mis:last-child { border-bottom:none; }
  .wrappercard .wr-mis-tk { font-family:var(--fm); font-weight:600; color:var(--ink); min-width:80px; }
  .wrappercard .wr-mis-pct { font-family:var(--fm); color:var(--ink); margin-left:auto; font-variant-numeric:tabular-nums; min-width:55px; text-align:right; }
  .wrappercard .wr-mis-pct.neg { color:var(--bear); }
  .wrappercard .wr-mis-eur { font-family:var(--fm); color:var(--steel); font-variant-numeric:tabular-nums; min-width:80px; text-align:right; }
  .fxcard .fx-row { padding:12px 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .fxcard .fx-row:last-child { border-bottom:none; }
  .fxcard .fx-head { display:flex; align-items:baseline; gap:10px; margin-bottom:5px; }
  .fxcard .fx-cur { font-family:var(--fm); font-weight:600; font-size:13px; color:var(--ink); }
  .fxcard .fx-pct { font-family:var(--fm); font-size:14px; font-weight:600; font-variant-numeric:tabular-nums; }
  .fxcard .fx-pct.high { color:var(--bear); }
  .fxcard .fx-pct.mid { color:#c89b00; }
  .fxcard .fx-pct.low { color:var(--acc); }
  .fxcard .fx-eur { font-family:var(--fm); font-size:11px; color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .fxcard .fx-n { font-family:var(--fm); font-size:10px; color:var(--steel); min-width:32px; text-align:right; font-variant-numeric:tabular-nums; }
  .fxcard .fx-bar { height:5px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r1); overflow:hidden; margin:4px 0 6px; }
  .fxcard .fx-fill { height:100%; border-radius:var(--r1); }
  .fxcard .fx-fill.high { background:var(--bear); }
  .fxcard .fx-fill.mid { background:#c89b00; }
  .fxcard .fx-fill.low { background:var(--acc); }
  .fxcard .fx-tks { font-family:var(--fm); font-size:10.5px; color:var(--steel); font-variant-numeric:tabular-nums; }
  .benchcard .bm-grid { display:grid; grid-template-columns:repeat(3, 1fr); gap:18px; margin:14px 0; }
  .benchcard .bm-cell { padding:14px 18px; background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); }
  .benchcard .bm-h { font-family:var(--fb); font-size:10px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); font-weight:600; margin-bottom:6px; }
  .benchcard .bm-v { font-family:var(--fm); font-size:24px; font-weight:500; color:var(--ink); font-variant-numeric:tabular-nums; }
  .benchcard .bm-v.pos { color:var(--acc); }
  .benchcard .bm-v.neg { color:var(--bear); }
  .benchcard .bm-v.neu { color:var(--steel); }
  .benchcard .bm-foot { font-family:var(--fm); font-size:12px; color:var(--steel); margin-top:10px; padding-top:10px; border-top:1px solid var(--line); }
  .benchcard .bm-warn { font-family:var(--fm); font-size:11.5px; color:#c89b00; background:color-mix(in srgb,#c89b00 8%,transparent); padding:8px 12px; border-radius:var(--r2); margin:12px 0 0; }
  /* Sprint 7 - Chat surface */
  .chatcard .chat-log { max-height:340px; overflow-y:auto; padding:12px 0; margin-bottom:14px; display:flex; flex-direction:column; gap:10px; }
  .chatcard .chat-log:empty { display:none; }
  .chatcard .chat-msg { font-family:var(--fm); font-size:13px; line-height:1.5; padding:10px 14px; border-radius:var(--r2); max-width:88%; }
  .chatcard .chat-user { align-self:flex-end; background:color-mix(in srgb,var(--id) 14%,transparent); color:var(--ink); }
  .chatcard .chat-assistant { align-self:flex-start; background:color-mix(in srgb,var(--ink) 5%,transparent); color:var(--ink); }
  .chatcard .chat-form { display:flex; gap:10px; align-items:flex-start; }
  .chatcard .chat-input { flex:1; font-family:var(--fm); font-size:13px; padding:10px 12px; border:1px solid var(--line2); background:var(--panel); color:var(--ink); border-radius:var(--r2); resize:vertical; min-height:54px; }
  .chatcard .chat-input:focus { outline:none; border-color:var(--id); }
  .chatcard .chat-send { font-family:var(--fb); font-size:11.5px; letter-spacing:.15em; text-transform:uppercase; padding:0 22px; height:54px; border-radius:var(--r2); border:1px solid var(--id); background:var(--id); color:var(--bg); cursor:pointer; transition:.15s; }
  .chatcard .chat-send:hover:not(:disabled) { opacity:.85; }
  .chatcard .chat-send:disabled { opacity:.5; cursor:default; }
  .chatcard .chat-foot { font-family:var(--fm); font-size:10.5px; color:var(--steel); margin-top:10px; }
  .modetgl { display:flex; align-items:center; justify-content:center; width:44px; height:44px; border-radius:var(--r3); border:1px solid var(--line); background:transparent; color:var(--steel); cursor:pointer; transition:.15s; margin:16px 0 4px; }
  .modetgl svg { width:20px; height:20px; }
  .modetgl:hover { color:var(--id); border-color:var(--id); }
  .hero, .pfcard { box-shadow:var(--elev); }
  .card, .kpi, .gauge, .plan { box-shadow:var(--elev); }
  .loupe-card { box-shadow:0 30px 90px -20px #000; }
  .nitem.on { box-shadow:inset 0 0 20px -10px color-mix(in srgb,var(--id) 55%,transparent); }
  .nitem.on svg { filter:drop-shadow(0 0 6px color-mix(in srgb,var(--id) 70%,transparent)); }
  .tape { box-shadow:none; }
  .row[data-tk]:hover, .dt tbody tr:hover td, .th-row:hover, .sbrow:hover { background:color-mix(in srgb,var(--ink) 3.5%,transparent); }
  .brk { margin-bottom:18px; }
  .brk-h { display:flex; justify-content:space-between; align-items:baseline; margin:0 2px 10px; flex-wrap:wrap; gap:8px; }
  .brk-n { font-family:var(--fm); font-weight:500; font-size:16px; letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .brk-note { font-family:var(--fm); font-size:11px; color:var(--steel); margin-left:8px; }
  .brk-tot { font-family:var(--fm); font-size:13px; color:var(--ink); } .brk-tot span { color:var(--steel); font-size:11.5px; }
  .brk-body { display:flex; gap:24px; align-items:flex-start; flex-wrap:wrap; }
  .brk-viz { flex:0 0 320px; max-width:320px; }
  .brk-tbl { flex:1; min-width:300px; }
  .brk-bars { display:flex; flex-direction:column; gap:2px; }
  .brk-row { display:grid; grid-template-columns:minmax(110px,1.3fr) minmax(60px,2.5fr) 42px 56px; align-items:center; gap:12px; padding:8px 4px; border-radius:var(--r1); transition:background .15s; }
  .brk-row:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); }
  .brk-row-name { display:flex; align-items:center; gap:8px; min-width:0; }
  .brk-row-dot { width:8px; height:8px; border-radius:50%; flex:0 0 auto; }
  .brk-row-label { font-family:var(--fb); font-weight:500; font-size:12px; color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .brk-row-bar { height:4px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:2px; overflow:hidden; }
  .brk-row-fill { height:100%; border-radius:2px; transition:width .4s cubic-bezier(.2,.8,.2,1); }
  .brk-row-pct { font-family:var(--fm); font-weight:500; font-size:12px; color:var(--ink); text-align:right; font-variant-numeric:tabular-nums; }
  .brk-row-val { font-family:var(--fm); font-weight:400; font-size:11px; color:var(--steel); text-align:right; font-variant-numeric:tabular-nums; }
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
    var ana = a ? ('<div class="lp-sec">Derni&egrave;re analyse &middot; '+a.date+(a.type?' &middot; '+a.type:'')+'</div>'+sc+(a.regime?'<div class="lp-meta">R&eacute;gime '+a.regime+(a.narr&&a.narr.length?' &middot; '+a.narr.join(', '):'')+'</div>':'')+(a.excerpt?'<div class="lp-ex">'+a.excerpt+'&hellip;</div>':'')) : '<div class="lp-sec">Analyse</div><div class="lp-empty">Aucune analyse stock&eacute;e pour ce titre.</div>';
    document.getElementById('loupe-body').innerHTML =
      '<div class="lp-h"><span class="lp-tk">'+tk+'</span><span class="lp-nm">'+(d.name||'')+'</span></div>'
      +'<div class="lp-meta">'+badge+' &middot; '+(d.sector||'&mdash;')+' &middot; '+(d.country||'&mdash;')+'</div>'
      +((st==='held')?('<div class="lp-grid">'
      +'<div class="lp-stat"><div class="lp-sl">Poids</div><div class="lp-sv">'+d.weight_pct+'%</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">Investi</div><div class="lp-sv">'+d.weight_eur+'&euro;</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">P&amp;L</div><div class="lp-sv">'+_pct(d.pnl,true)+'</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">Marge stop</div><div class="lp-sv">'+_pct(d.down)+'</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">Vers cible</div><div class="lp-sv">'+_pct(d.up)+'</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">Asym&eacute;trie</div><div class="lp-sv">'+(d.ratio==null?'&mdash;':d.ratio+'x')+'</div></div>'
      +'</div>'+(d.perf?('<div class="lp-sec" style="margin-top:16px">Momentum r&eacute;cent</div><div class="lp-mom">'+mom('Jour',d.perf.d)+mom('Semaine',d.perf.w)+mom('Mois',d.perf.m)+'</div>'):'')):'<div class="lp-empty" style="padding:10px 0 2px">Pas de position ouverte sur ce titre.</div>')+ana;
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
    function rw(l,v,c){return '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:.5px solid var(--line)"><span style="color:var(--steel)">'+l+'</span><span class="mono" style="color:'+(c||'var(--ink)')+'">'+v+'</span></div>';}
    function overview(){
      for(var k in groups){groups[k].classList.remove('on');groups[k].classList.remove('dim');}
      var top=sorted[0],tp=Math.round(top.tw/total*100),ov=tp>=30;
      PANEL.innerHTML='<div style="font-family:var(--fb);font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--steel);margin-bottom:10px">Vue d&rsquo;ensemble</div>'
        +rw('Plus gros secteur',top.name+' &middot; '+tp+'%',ov?'var(--bear)':'var(--acc)')
        +rw('Lignes total',DATA.reduce(function(a,s){return a+s.t.length;},0)+'')
        +'<div style="margin-top:12px;font-size:12px;color:'+(ov?'var(--warn)':'var(--steel)')+'">'+(ov?('&#9888; '+top.name+' au-dessus du plafond 30%'):'sous le plafond 30%')+'</div>'
        +'<div style="margin-top:14px;font-size:11px;color:var(--steel)">clique un secteur pour voir ses lignes</div>';
    }
    function showSector(name){
      var s=null;DATA.forEach(function(d){if(d.name===name)s=d;});if(!s)return;
      for(var k in groups){if(k===name){groups[k].classList.add('on');groups[k].classList.remove('dim');}else{groups[k].classList.remove('on');groups[k].classList.add('dim');}}
      var rows=s.t.slice().sort(function(a,b){return b.w-a.w;}).map(function(x){var pc=x.pnl==null?'var(--steel)':(x.pnl>=0?'var(--acc)':'var(--bear)');return '<div class="sbrow" data-tk="'+x.tk+'"><span class="mono">'+x.tk+'</span><span style="display:flex;gap:12px;align-items:center"><span class="mono" style="width:48px;text-align:right;color:'+pc+'">'+pv(x.pnl)+'</span><span class="mono" style="color:var(--steel);font-size:11px">stop '+(x.down==null?'&mdash;':x.down+'%')+'</span></span></div>';}).join('');
      PANEL.innerHTML='<div class="sb-back" style="cursor:pointer;color:var(--steel);font-size:11px;margin-bottom:8px">&larr; vue d&rsquo;ensemble</div><div style="display:flex;align-items:center;gap:8px;margin-bottom:10px"><span style="width:10px;height:10px;border-radius:2px;background:'+s.col+'"></span><span style="font-family:var(--fd);font-weight:500;font-size:14px">'+s.name+'</span><span class="mono" style="color:var(--steel);font-size:12px">'+Math.round(s.tw/total*100)+'% &middot; '+s.t.length+' lignes</span></div>'+rows+'<div style="margin-top:10px;font-size:11px;color:var(--steel)">clique un titre pour sa fiche</div>';
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
    box.innerHTML='<div class="qs-card"><input id="qs-input" type="text" placeholder="Rechercher un titre ou un nom..." autocomplete="off"><div id="qs-res"></div></div>';
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
            exc = str(content)[:280].strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
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


def _broker_value(p: dict, pnl: dict) -> float:
    return p["weight"] * (1 + pnl.get(p["ticker"], 0) / 100.0)


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


def _broker_one(label: str, note: str, ps: list, grand: float, names: dict, pnl: dict, sectors: dict) -> str:
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
        rows += (
            f'<tr data-tk="{tk}" data-v="{v:.2f}" data-w="{w:.2f}" data-p="{pc if pc is not None else -9999}"><td class="tk">{tk}<span class="nm">{nm}</span></td>'
            f'<td class="num mono">{vstr}&nbsp;&euro;</td><td class="num">{w:.1f}%</td>'
            f'<td class="num {pcls}">{pstr}</td></tr>'
        )
    if not ps:
        rows = '<tr><td class="empty" colspan="4" style="padding:18px 0">aucune ligne</td></tr>'
    tot_str = f"{tot:,.0f}".replace(",", "&#8239;")
    donut = _sector_donut(_sector_mix(ps, pnl, sectors)) if ps else ""
    return (
        f'<div class="brk"><div class="brk-h"><div><span class="brk-n">{label}</span>'
        f'<span class="brk-note">{note}</span></div>'
        f'<div class="brk-tot">{tot_str}&nbsp;&euro; <span>&middot; {len(ps)} lignes &middot; {share:.0f}% du total</span></div></div>'
        f'<div class="brk-body">{donut}<div class="brk-tbl"><div class="card pad" style="padding:4px 18px"><table class="dt"><thead><tr><th>Ligne</th>'
        f'<th class="num">Valeur</th><th class="num">Poids</th><th class="num">P&amp;L</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div></div></div></div>"
    )


def _broker_tables(positions: list[dict], names: dict, pnl: dict, sectors: dict) -> str:
    grand = sum(_broker_value(p, pnl) for p in positions) or 1
    tr = [p for p in positions if _broker(p["ticker"]) == "tr"]
    eu = [p for p in positions if _broker(p["ticker"]) == "bourso"]
    head = (
        '<div class="colhead" style="margin-top:6px"><span class="t">Comptes</span>'
        '<span class="a">par courtier &middot; tri&eacute; par valeur</span></div>'
    )
    return (
        head
        + _broker_one("Trade Republic", "hors Europe", tr, grand, names, pnl, sectors)
        + _broker_one("Boursorama", "PEA &middot; Europe", eu, grand, names, pnl, sectors)
    )


_MODE_BTN = """<button class="modetgl" title="Mode jour / nuit" onclick="document.body.classList.toggle('midnight');try{localStorage.setItem('hmdl-theme',document.body.classList.contains('midnight')?'midnight':'parchment')}catch(e){}"><svg class="ico-sun" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg><svg class="ico-moon" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button>"""
_THEME_INIT = "<script>try{var t=localStorage.getItem('hmdl-theme');if(t==='midnight')document.body.classList.add('midnight');}catch(e){}</script>"


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


def render() -> Path:
    asym_mod._get_current_price = _cached_price_eur
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
                "w": round(p["weight"] * (1 + pnl.get(p["ticker"], 0) / 100.0)),
                "pnl": round(pnl[p["ticker"]], 1) if p["ticker"] in pnl else None,
                "down": round(sb_down[p["ticker"]], 1) if sb_down.get(p["ticker"]) is not None else None,
            }
        )
    sb_ordered = sorted(sb_secs.items(), key=lambda kv: (kv[0] == "Sans th&egrave;se", -sum(x["w"] for x in kv[1])))
    sb_data = [{"name": nm, "col": SECTOR_COLORS.get(nm, "#6B7686"), "t": rows} for nm, rows in sb_ordered]

    _ris, near, heat, watch = _rows_risque(computed)
    gain, lose = _movers(pnl)
    day_up, day_dn = _day_movers(daily)
    stamp = datetime.now().strftime("%d.%m.%Y &middot; %H:%M")
    today = datetime.now().strftime("%Y-%m-%d")
    erows = ""
    for rdate, rlab in sorted(REVIEWS):
        rpast = rdate < today
        rdd = f"{rdate[8:10]}.{rdate[5:7]}"
        rop = ' style="opacity:.45"' if rpast else ""
        rtag = " &middot; pass&eacute;e" if rpast else ""
        erows += f'<div class="line"{rop}><span>{rlab}{rtag}</span><span class="mono">{rdd}</span></div>'
    erows = erows or '<div class="empty" style="padding:14px 0">aucune &eacute;ch&eacute;ance</div>'

    wbase = sum(p["weight"] for p in positions if p["ticker"] in pnl) or 1
    port_pnl = sum(p["weight"] * pnl[p["ticker"]] for p in positions if p["ticker"] in pnl) / wbase
    gain_eur = sum(p["weight"] for p in positions if pnl.get(p["ticker"], 0) >= 0 and p["ticker"] in pnl)
    n_gain = sum(1 for p in positions if pnl.get(p["ticker"], 0) >= 0 and p["ticker"] in pnl)
    n_pnl = sum(1 for p in positions if p["ticker"] in pnl) or 1
    gpct = gain_eur / wbase * 100
    _pfcost = sum(p["weight"] for p in positions)
    pf_value = sum(p["weight"] * (1 + pnl.get(p["ticker"], 0) / 100.0) for p in positions)
    pf_pnl_eur = pf_value - _pfcost
    vcls = "pos" if pf_pnl_eur >= 0 else "neg"
    pf_val_str = f"{pf_value:,.0f}".replace(",", "&#8239;")
    pf_cost_str = f"{_pfcost:,.0f}".replace(",", "&#8239;")
    pf_pe = f"{pf_pnl_eur:+,.0f}".replace(",", "&#8239;")
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
    over_cap_tk = _sizing_overcap(
        positions, _conv_tk, _CFG.get("concentration", {}).get("line_cap_by_conviction", {}), pnl
    )

    disc_hero = (
        '<div class="hero posture"><div class="hl">Cockpit &mdash; lecture m&eacute;canique, non prescriptive</div><div class="plan-row">'
        + _pi(
            len(over_cap_tk),
            over_cap_tk,
            "au-dessus du cap &middot; all&eacute;ger sans sortir",
            "danger" if over_cap_tk else "calm",
        )
        + _pi(len(near_tgt_tk), near_tgt_tk, "candidat(s) prise de profit", "warn" if near_tgt_tk else "calm")
        + _pi(len(near_stop_tk), near_stop_tk, "marge(s) faible(s)", "danger" if near_stop_tk else "calm")
        + "</div></div>"
    )

    tape_items = ""
    for tk, p in sorted(pnl.items(), key=lambda x: -x[1]):
        cls = "pos" if p >= 0 else "neg"
        tape_items += f'<span class="ti"><b>{tk}</b> <span class="{cls}">{"+" if p >= 0 else ""}{p:.1f}%</span></span>'
    tape = f'<div class="tape"><div class="track2">{tape_items}{tape_items}</div></div>'
    tape8k = _tape_8k()

    journal_html = _journal()
    journal_block = (
        (
            '<div class="colhead" style="margin-top:22px"><span class="t">Derni&egrave;res d&eacute;cisions</span><span class="a">journal Telegram</span></div>'
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

    def _axisrow(tk: str) -> str:
        a = _axis[tk]
        return (
            f'<div class="row" data-tk="{tk}"><div class="rt"><span class="tk">{tk}</span></div>'
            f'<div class="axis"><div class="axis-mark" style="left:{a["frac"]:.1f}%"></div></div>'
            f'<div class="th-ends"><span class="th-stop">stop &minus;{a["dn"]:.0f}%</span>'
            f'<span class="th-tgt">cible +{a["up"]:.0f}%</span></div></div>'
        )

    gain = "".join(_axisrow(tk) for tk in _cibles) or '<div class="empty" style="padding:18px 0">&mdash;</div>'
    lose = "".join(_axisrow(tk) for tk in _stops) or '<div class="empty" style="padding:18px 0">&mdash;</div>'
    cockpit_html = (
        '<div class="card pad" style="margin-bottom:18px">'
        '<div class="colhead">'
        '<span class="t">Cockpit discipline</span>'
        '<span class="a">lecture en continu &middot; rouge = &agrave; traiter</span>'
        "</div>" + _cockpit() + "</div>"
    )
    grade_html = _grade_panel()
    copilot_html = _copilot_panel()
    chat_html = _chat_panel()
    narrative_html = _narrative_panel()
    conversations_html = _conversations_panel()
    chat_signals_html = _chat_signals_panel()
    conceptions_html = _conceptions_panel()
    preferences_html = _preferences_panel()
    axes_html = _ticker_axes_panel()
    factor_html = _factor_exposures_panel()
    stress_html = _stress_tests_panel()
    trajectory_html = _trajectory_panel()
    spof_html = _spof_panel()
    mauboussin_html = _mauboussin_sizing_panel()
    valo_html = _valo_above_bull_panel()
    kill_html = _kill_criteria_panel()
    wrapper_html = _wrapper_panel()
    fx_html = _fx_exposure_panel()
    bench_html = _benchmark_panel()
    vigie = (
        f'<section data-page="vigie" class="active"><div class="phead"><h2>Vue d\'ensemble</h2>'
        f'<div class="sub">Posture de discipline &middot; sur quoi agir aujourd&rsquo;hui</div></div>'
        f'<div class="hrow star">'
        f'<div class="pfcard"><div class="hl">Valeur du portefeuille</div>'
        f'<div class="v">{pf_val_str}&nbsp;&euro;</div>'
        f'<div class="d {vcls}">{pf_pe}&euro; ({"+" if port_pnl >= 0 else ""}{port_pnl:.1f}%)</div>'
        f'<div class="distline"><div class="g" style="width:{gpct:.0f}%"></div><div class="r" style="width:{100 - gpct:.0f}%"></div></div>'
        f'<div class="distcap"><span class="cg">en gain {gpct:.0f}% &middot; {n_gain} lignes</span><span class="cr">en perte {100 - gpct:.0f}% &middot; {n_pnl - n_gain} lignes</span></div>'
        f'<div class="sub2">{pf_cost_str}&euro; investi</div></div>{disc_hero}</div>'
        f"{grade_html}"
        f"{narrative_html}"
        f"{chat_html}"
        f"{conversations_html}"
        f"{chat_signals_html}"
        f"{conceptions_html}"
        f"{preferences_html}"
        f"{kill_html}"
        f"{trajectory_html}"
        f"{factor_html}"
        f"{fx_html}"
        f"{bench_html}"
        f"{wrapper_html}"
        f"{spof_html}"
        f"{stress_html}"
        f"{mauboussin_html}"
        f"{valo_html}"
        f"{axes_html}"
        f"{copilot_html}"
        f"{cockpit_html}"
        f'<div class="cols"><div class="col"><div class="colhead"><span class="t">Plus proches de la cible</span><span class="a">la th&egrave;se se r&eacute;alise</span></div>'
        f'<div class="card pad">{gain}</div></div><div class="col"><div class="colhead"><span class="t">Marges les plus faibles</span><span class="a">avant invalidation du stop</span></div>'
        f'<div class="card pad">{lose}</div></div></div>'
        f'<div class="cols"><div class="col"><div class="colhead"><span class="t">Hausses du jour</span><span class="a">vs cl&ocirc;ture veille</span></div>'
        f'<div class="card pad">{day_up}</div></div><div class="col"><div class="colhead"><span class="t">Baisses du jour</span><span class="a">vs cl&ocirc;ture veille</span></div>'
        f'<div class="card pad">{day_dn}</div></div></div>'
        f'<div class="colhead" style="margin-top:22px"><span class="t">&Eacute;ch&eacute;ances &agrave; venir</span></div>'
        f'<div class="card pad">{erows}</div>'
        f"{journal_block}</section>"
    )
    watch_zone_tk = [
        r["ticker"]
        for r in sorted(computed, key=lambda r: r.get("downside_pct", 999.0))
        if r.get("downside_pct") is not None and 10 <= r["downside_pct"] < 20
    ]
    pos_plan = (
        '<div class="plan"><div class="plan-h">Aujourd&rsquo;hui sur les positions</div><div class="plan-row">'
        + _pi(len(near_stop_tk), near_stop_tk, "au stop (&lt;10%)", "danger" if near_stop_tk else "calm")
        + _pi(len(watch_zone_tk), watch_zone_tk, "sous surveillance (10-20%)", "warn" if watch_zone_tk else "calm")
        + _pi(len(near_tgt_tk), near_tgt_tk, "proche d&rsquo;un palier", "warn" if near_tgt_tk else "calm")
        + "</div></div>"
    )
    broker_html = _broker_tables(positions, names, pnl, sectors)
    positions_pg = (
        f'<section data-page="positions"><div class="phead"><h2>Positions</h2>'
        f'<div class="sub">Marge &agrave; la hausse vers la cible &middot; &agrave; la baisse vers le stop</div></div>'
        f"{pos_plan}{broker_html}</section>"
    )

    # --- Bandeau d'ecart de discipline (sticky, haut de page) ---
    # v1: axe concentration (cluster hors plafond, source unique _cluster_health) + axe stop (near).
    # axe prise-profit -> ajoute apres ADR target_partial.
    _dev = []
    for _c in _cluster_health(positions, pnl):
        if _c["breached"]:
            _ov = f"{_c['over_eur']:,.0f}".replace(",", "&#8239;")
            _dev.append(f"all&eacute;ger {_c['name']} &middot; +{_ov}&#8239;&euro;")
    if near:
        _dev.append(f"{near} ligne(s) &lt; 10% du stop")
    _dn = len(_dev)
    _dcls, _dverdict = ("bear", "&Agrave; CALIBRER") if _dn else ("acc", "AU CALME")
    _ddetail = " &nbsp;&middot;&nbsp; ".join(_dev) if _dev else "tout sous les r&egrave;gles"
    _dband = (
        f'<div class="dband {_dcls}" onclick="document.querySelector(&#39;[data-nav=concentration]&#39;).click()">'
        f'<span class="dd"></span><span class="dv">{_dverdict}</span>'
        f'<span class="dx">{_ddetail}</span>'
        f'<span class="dn">{_dn} &agrave; traiter</span><span class="dc">&rsaquo;</span></div>'
    )
    elan, near_t = _elan_watch(computed)
    body = (
        f'<aside class="sidebar"><div class="logo">{_LOGO}<span class="wm">PRESAGE<small>intelligence &middot; signal &middot; advantage</small></span></div>'
        f'{_NAV}{_MODE_BTN}<div class="foot">{_rail_foot(near, heat)}<span class="dot" title="en veille &middot; maj {stamp}"></span></div></aside>{_THEME_INIT}{_SORT_JS}{_CSORT_JS}{_DONUT_JS}'
        f'<div class="wrap">{tape}{tape8k}<main class="main">{_dband}'
        + vigie
        + positions_pg
        + _theses(names, sectors, positions, pnl)
        + _concentration(positions, planned, sectors, names, pnl, daily)
        + _signaux()
        + _urgence(watch, near, positions, pnl, elan, near_t)
        + "</main></div>"
        + _LOUPE_HTML
    )

    html = (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta http-equiv="refresh" content="300">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><script>try{if(sessionStorage.getItem("h_seen"))document.documentElement.classList.add("noanim");sessionStorage.setItem("h_seen","1");}catch(e){}</script><title>PRESAGE</title><link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg%20viewBox%3D%220%200%2064%2064%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%3E%3Crect%20width%3D%2264%22%20height%3D%2264%22%20rx%3D%2214%22%20fill%3D%22%230c0c0e%22%2F%3E%3Cg%20transform%3D%22translate%288.00%2C19.57%29%20scale%280.13079%29%22%20fill%3D%22%23ECEFF4%22%3E%3Cg%20transform%3D%22translate%280.000000%2C190.000000%29%20scale%280.100000%2C-0.100000%29%22%20%20stroke%3D%22none%22%3E%20%3Cpath%20d%3D%22M1335%201890%20c-11%20-4%20-200%20-189%20-419%20-409%20l-399%20-401%20251%200%20250%200%20254%20260%20253%20260%2071%200%2071%200%2058%20-62%20c32%20-35%20168%20-174%20301%20-309%20l242%20-246%2069%20-7%20c37%20-4%20148%20-11%20246%20-16%2098%20-4%20181%20-11%20184%20-14%204%20-3%20-45%20-6%20-108%20-6%20-63%200%20-175%20-5%20-249%20-10%20l-135%20-11%20-72%20-72%20c-40%20-39%20-73%20-76%20-73%20-82%200%20-6%2051%20-61%20114%20-124%20l113%20-113%20184%20187%20184%20186%20330%209%20c182%205%20394%209%20473%2010%20l142%200%200%2030%200%2030%20-127%201%20c-71%201%20-284%204%20-474%207%20l-346%207%20-87%2082%20c-47%2045%20-126%20129%20-175%20186%20-131%20153%20-581%20617%20-609%20628%20-29%2011%20-490%2011%20-517%20-1z%22%2F%3E%20%3Cpath%20d%3D%22M2308%201888%20c-9%20-7%20-26%20-33%20-37%20-58%20-12%20-25%20-44%20-68%20-72%20-97%20l-51%20-52%20105%20-108%20105%20-107%2064%2067%2063%2067%2072%200%2071%200%20253%20-260%20252%20-260%20244%200%20c238%200%20244%200%20231%2019%20-23%2032%20-760%20775%20-782%20788%20-30%2018%20-496%2018%20-518%201z%22%2F%3E%20%3Cpath%20d%3D%22M1693%201259%20c-54%20-61%20-109%20-127%20-123%20-145%20-14%20-19%20-51%20-54%20-83%20-78%20l-58%20-43%20-487%20-7%20c-268%20-3%20-589%20-9%20-715%20-13%20-207%20-5%20-227%20-7%20-227%20-23%200%20-16%2024%20-18%20298%20-24%20163%20-4%20488%20-11%20721%20-17%20l424%20-10%2061%20-44%20c89%20-63%20148%20-125%20236%20-250%2053%20-75%20150%20-184%20305%20-345%20125%20-129%20237%20-240%20249%20-247%2015%20-9%2095%20-12%20276%20-13%20l254%200%20411%20410%20410%20410%20-245%200%20-245%200%20-255%20-255%20-255%20-255%20-81%200%20-80%200%20-244%20253%20c-309%20320%20-340%20349%20-388%20353%20-20%201%20-91%208%20-157%2013%20-66%206%20-176%2011%20-245%2012%20-149%202%20-118%2016%2039%2018%2056%200%20169%206%20250%2012%20l146%2011%2073%2071%20c39%2040%2071%2075%2070%2079%20-5%2013%20-221%20238%20-229%20238%20-4%200%20-52%20-50%20-106%20-111z%22%2F%3E%20%3Cpath%20d%3D%22M715%20618%20c110%20-112%20290%20-295%20402%20-408%20l202%20-205%20161%20-3%20c182%20-4%20206%203%20285%2077%2052%2049%20126%2093%20193%20115%20l54%2018%20-112%20112%20-111%20111%20-58%20-62%20-57%20-63%20-81%200%20-80%200%20-176%20178%20c-96%2097%20-208%20212%20-247%20255%20l-72%2077%20-251%200%20-251%200%20199%20-202z%22%2F%3E%20%3C%2Fg%3E%3C%2Fg%3E%3C%2Fsvg%3E">'
        ""
        '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Geist:wght@100;200;300;400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">'
        "<style>"
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
        + _APP_JS
        + "</script>"
        + "<script>(function(){var b=null;function c(){fetch(location.pathname,{method:'HEAD',cache:'no-store'}).then(function(r){var m=r.headers.get('Last-Modified');if(m){if(b===null)b=m;else if(m!==b)location.reload();}}).catch(function(){});}setInterval(c,60000);})();</script>"
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
