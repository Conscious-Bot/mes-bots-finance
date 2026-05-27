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
    "TSM": "Ta&iuml;wan", "TSEM": "Isra&euml;l", "ASML": "Pays-Bas", "NVO": "Danemark", "ARM": "Royaume-Uni",
    "IFNNY": "Allemagne", "BABA": "Chine", "TCEHY": "Chine", "PDD": "Chine", "STM": "France",
}
SUFFIX = {
    ".KS": "Cor&eacute;e", ".T": "Japon", ".TW": "Ta&iuml;wan", ".PA": "France", ".AS": "Pays-Bas",
    ".L": "Royaume-Uni", ".HK": "Chine", ".DE": "Allemagne", ".MI": "Italie", ".ST": "Su&egrave;de",
    ".AX": "Australie", ".TO": "Canada", ".SS": "Chine", ".SZ": "Chine", ".SW": "Suisse",
}


_PX_CACHE: dict[str, tuple[float, float]] = {}
_PX_TTL = 1800.0  # 30 min: throttle yfinance (partage IP/lib avec price_monitor, evite le ban)


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


SECTOR_COLORS = {
    "Foundry & logique": "#4C8DFF",
    "Équipement semi": "#22C9D6",
    "Mémoire": "#6E7BF2",
    "Matériaux semi": "#2DD4A0",
    "EDA": "#4ADE80",
    "Connectivité & optique": "#C084FC",
    "Hyperscalers": "#38BDF8",
    "Power & électrification": "#F5B544",
    "Défense": "#F0654B",
    "Énergie & matières premières": "#E0894B",
    "Auto / robotique": "#EC6A9C",
}
TICKER_SECTOR = {
    "AMZN": "MAG 7", "ENTG": "AI Compute", "MP": "Matériaux rares",
    "MU": "AI Compute", "6857.T": "AI Compute", "VRT": "Data Center",
    "CCJ": "Énergie", "LNG": "Énergie", "TSLA": "Robotique",
}
SECTOR_ALIAS = {"EU Defense": "Defense"}


def _clean_sector(sid: str | None) -> str:
    if not sid:
        return "Sans th&egrave;se"
    s = re.sub(r"_20\d\d$", "", sid).replace("_", " ").title()
    return s.replace(" Ai", " AI").replace("Ai ", "AI ").replace("Hpq", "HPQ").replace("Eu ", "EU ").replace("Mag7", "MAG 7")


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
        out.append({"ticker": tk, "weight": float(teur or 0), "pct": float(tpct or 0), "sector": label, "planned": True})
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
        bar = "prismatic" if hit else ("up" if pnl >= 0 else "danger")
        flag = " &#127919;" if hit else ""
        d = i * 0.035
        rows.append(
            f'<div class="row" data-tk="{tk}" style="animation-delay:{d:.2f}s"><div class="rt">'
            f'<span class="tk">{tk}{flag}</span><span class="tag {cls}">{sign}{pnl:.1f}%</span></div>'
            f'<div class="track"><div class="fill {bar}" style="--w:{pc:.0f}%;animation-delay:{d + 0.08:.2f}s"></div></div>'
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
    watch = rows or '<div class="empty" style="padding:18px 0">aucun winner &agrave; &ge;75% &mdash; laisse courir</div>'
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
            f'<div class="track"><div class="fill {cls}" style="--w:{buf:.0f}%;animation-delay:{d + 0.08:.2f}s"></div></div>'
            f'<div class="rs"><span>marge avant le stop</span></div></div>'
        )
        if is_near:
            near_rows.append(f'<div class="line"><span>{tk}</span><span class="mono">{down:.0f}% de marge</span></div>')
    watch = "".join(near_rows) or '<div class="empty" style="padding:18px 0">aucune position sous 10% &mdash; au calme</div>'
    return "".join(rows), near, heat, watch


def _mover_blk(rows) -> str:
    return "".join(
        f'<div class="line"><span class="mono">{tk}</span>'
        f'<span class="mono {"pos" if p >= 0 else "neg"}">{"+" if p >= 0 else ""}{p:.1f}%</span></div>'
        for tk, p in rows
    ) or '<div class="empty" style="padding:14px 0">&mdash;</div>'


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
        out.append({"name": _clean_sector(cn), "pct": cp, "cap": ccap, "over_eur": cv - ccap / 100 * total, "breached": cp >= ccap})
    return out


def _concentration(positions: list[dict], planned: list[dict], sectors: dict, names: dict, pnl: dict, daily: dict) -> str:
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
    cause = " &middot; ".join(cbits) or "tout sous tes plafonds"
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
        _otxt = (f"d&eacute;passement +{_c['over_eur']:,.0f}&#8239;&euro; &rarr; trimmer" if _c["over_eur"] > 0 else "sous le plafond").replace(",", "&#8239;")
        _crows.append(
            f'<div class="pi {_ccls}"><span class="pn">{_c["pct"]:.0f}%</span>'
            f'<span class="pl">{_c["name"]} &middot; plafond {_c["cap"]:.0f}%</span>'
            f'<span class="pt">{_otxt}</span></div>'
        )
    cluster_card = ('<div class="plan"><div class="plan-h">Cluster corr&eacute;l&eacute; (gouverneur)</div><div class="plan-row">' + "".join(_crows) + "</div></div>") if _crows else ""
    verdict_card = (
        '<div class="plan"><div class="plan-h">Verdict concentration</div>'
        '<div class="plan-row" style="grid-template-columns:minmax(160px,1fr) 2fr">'
        + f'<div class="pi {vcls}"><span class="pn">{verdict}</span><span class="pl">posture concentration</span><span class="pt">{cause}</span></div>'
        + f'<div class="pi"><span class="pl">{over_cap} ligne(s) au-dessus du plafond {POS_CAP:.0f}%</span>'
        + f'<span class="pt" style="font-size:12.5px;color:var(--ink);margin-top:4px;line-height:1.5">{over_nm or "aucune"}</span></div>'
        + '</div></div>'
    )
    return (
        f'<section data-page="concentration"><div class="phead"><h2>Concentration</h2>'
        f'<div class="sub">Trois axes de concentration &mdash; par ligne, par secteur, par g&eacute;ographie</div></div>'
        f'{verdict_card}'
        f'{cluster_card}'
        f'<div class="kpis" style="grid-template-columns:repeat(3,1fr)">'
        f'<div class="kpi"><span class="kl">Plus grosse ligne</span><span class="kv {top_cls}">{top_pct:.0f}%</span><span class="kd">{line_msg}</span></div>'
        f'<div class="kpi"><span class="kl">Th&egrave;se dominante</span><span class="kv {these_cls}">{dom_these_pct:.0f}%</span><span class="kd">{these_msg}</span></div>'
        f'<div class="kpi"><span class="kl">Capital investi</span><span class="kv">{cap}&nbsp;&euro;</span><span class="kd">{len(positions)} lignes</span></div></div>'
        f'<div class="card pad"><div class="sbwrap"><svg id="sb-svg" viewBox="0 0 320 320" aria-label="Concentration"></svg><div id="sb-panel"></div></div></div>'
        f'<div class="card pad" style="margin-top:18px"><div class="colhead"><span class="t">Par secteur</span></div>{_sector_blocks(positions, planned, sectors, pnl, names, daily)}</div>'
        f'<div class="card pad" style="margin-top:18px"><div class="colhead"><span class="t">Par pays</span><span class="a">si&egrave;ge social &middot; pas la supply-chain r&eacute;elle (Ta&iuml;wan sous-estim&eacute;)</span></div>{_geo_bars(positions)}</div>'
        f'</section>'
    )


def _render_bucket(name: str, rows: list, total: float, pnl: dict, names: dict, daily: dict, fx: float, sub: bool = False) -> tuple[str, float]:
    rows = sorted(rows, key=lambda r: -r["w"])
    sw = sum(r["w"] for r in rows)
    spct = sw / total * 100
    wbase = sum(r["w"] for r in rows if not r["prev"] and pnl.get(r["tk"]) is not None)
    wpl = sum(r["w"] * pnl[r["tk"]] for r in rows if not r["prev"] and pnl.get(r["tk"]) is not None)
    spl = (wpl / wbase) if wbase else None
    plmeta = ""
    if spl is not None:
        plmeta = f' &middot; <span class="sec-pl {"pos" if spl >= 0 else "neg"}">{"+" if spl >= 0 else ""}{spl:.1f}%</span>'
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
        plc = '<span class="num">&mdash;</span>' if pl is None else f'<span class="num {"pos" if pl >= 0 else "neg"}">{"+" if pl >= 0 else ""}{pl:.1f}%</span>'
        dvc = '<span class="num">&mdash;</span>' if dv is None else f'<span class="num {"pos" if dv >= 0 else "neg"}">{"+" if dv >= 0 else ""}{dv:.1f}%</span>'
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


def _sector_blocks(positions: list[dict], planned: list[dict], sectors: dict, pnl: dict, names: dict, daily: dict) -> str:
    real_t = sum(p["weight"] for p in positions)
    plan_t = sum(p["weight"] for p in planned)
    total = (real_t + plan_t) or 1
    fx = FX_USD
    _cl = _compute_ai_set()
    fine: dict = {}
    for p in positions:
        fine.setdefault(sectors.get(p["ticker"], "Autre"), []).append({"tk": p["ticker"], "w": p["weight"], "prev": False})
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
        c_pm = "" if c_spl is None else f' &middot; <span class="sec-pl {"pos" if c_spl >= 0 else "neg"}">{"+" if c_spl >= 0 else ""}{c_spl:.1f}%</span>'
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
        f'D&eacute;tenu {real_t:.0f}&euro; &middot; pr&eacute;vu {plan_t:.0f}&euro; &middot; '
        f'total {total:.0f}&euro; (${total / fx:.0f}) &middot; {len(order) + (1 if compute_sub else 0)} groupes'
    )
    return (
        f'<div class="sub" style="margin-bottom:10px">{sub}</div>'
        f'<div class="sec-cols"><span></span><span class="num">&euro;</span><span class="num">$</span>'
        f'<span class="num">%</span><span class="num">Jour</span><span class="num">P&amp;L</span></div>'
        f'{blocks}'
    )


def _geo_bars(positions: list[dict]) -> str:
    total = sum(p["weight"] for p in positions) or 1
    cw: dict[str, float] = {}
    for p in positions:
        c = _country(p["ticker"])
        cw[c] = cw.get(c, 0.0) + p["weight"]
    bars = ""
    for country, w in sorted(cw.items(), key=lambda x: -x[1]):
        pct = w / total * 100
        bars += (
            f'<div class="row"><div class="rt"><span class="tk">{country}</span>'
            f'<span class="tag acc2">{pct:.0f}%</span></div>'
            f'<div class="track"><div class="fill acc2" style="--w:{max(2.0, min(100.0, pct)):.0f}%"></div></div>'
            f'<div class="rs"><span>exposition</span><span class="mono">{w:.0f}&euro;</span></div></div>'
        )
    return bars


def _signaux() -> str:
    try:
        s24 = _q("SELECT COUNT(*) FROM signals WHERE timestamp > datetime('now','-1 day')")[0][0]
        s30 = _q("SELECT COUNT(*) FROM signals WHERE timestamp > datetime('now','-30 day')")[0][0]
        n8k = _q("SELECT COUNT(*) FROM filings_8k_log WHERE filed_at > datetime('now','-60 day')")[0][0]
    except Exception as e:
        return f'<section data-page="signaux"><div class="phead"><h2>Signaux</h2></div>{_err(e)}</section>'

    sevcls = {"HIGH": "danger", "MEDIUM": "warn", "MED": "warn", "LOW": "calm"}
    sev_order = ("CASE UPPER(COALESCE(severity,'')) WHEN 'HIGH' THEN 0 "
                 "WHEN 'MEDIUM' THEN 1 WHEN 'MED' THEN 1 WHEN 'LOW' THEN 2 ELSE 3 END")
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
        eightk = rows8k or '<div class="empty" style="padding:18px 0">aucun 8-K sur 60j</div>'
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
        insiders = rowsib or '<div class="empty" style="padding:18px 0">aucun cluster d\'achats group&eacute;s d&eacute;tect&eacute;</div>'
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
                f'<div class="track"><div class="fill {col}" style="--w:{max(2.0, min(100.0, cv * 100)):.0f}%"></div></div>'
                f'<div class="rs"><span>cr&eacute;dibilit&eacute;</span><span class="mono">{int(n)} signaux</span></div></div>'
            )
    except Exception as e:
        src_rows, nsrc = _err(e), 0

    kpis = (
        f'<div class="kpis" style="grid-template-columns:repeat(3,1fr)">'
        f'<div class="kpi"><span class="kl">Signaux 24h</span><span class="kv">{s24}</span><span class="kd">Gmail + EDGAR</span></div>'
        f'<div class="kpi"><span class="kl">Signaux 30j</span><span class="kv">{s30}</span><span class="kd">fen&ecirc;tre roulante</span></div>'
        f'<div class="kpi"><span class="kl">8-K 60j</span><span class="kv">{n8k}</span><span class="kd">d&eacute;p&ocirc;ts EDGAR</span></div></div>'
    )
    cols = (
        f'<div class="cols">'
        f'<div class="col"><div class="colhead"><span class="t">8-K r&eacute;cents</span><span class="a">{tally_str}</span></div><div class="card">{eightk}</div></div>'
        f'<div class="col"><div class="colhead"><span class="t">Cr&eacute;dibilit&eacute; des sources</span><span class="a">{nsrc} sources &middot; recal 1er du mois</span></div><div class="card">{src_rows}</div></div>'
        f'</div>'
    )
    insider_strip = (
        f'<div class="colhead" style="margin-top:24px"><span class="t">Achats d\'initi&eacute;s group&eacute;s</span><span class="a">60j &middot; Form 4 EDGAR</span></div>'
        f'<div class="card pad">{insiders}</div>'
    )
    return (
        f'<section data-page="signaux"><div class="phead"><h2>Signaux</h2>'
        f'<div class="sub">D&eacute;p&ocirc;ts 8-K par s&eacute;v&eacute;rit&eacute; &middot; cr&eacute;dibilit&eacute; des sources &middot; achats d\'initi&eacute;s</div></div>'
        f'{kpis}{cols}{insider_strip}</section>'
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


def _macro_dot(ind: str, v: float) -> str:
    "Couleur du point macro selon le niveau reel (decouplee de la phase). Inconnu -> mute."
    band = _MACRO_BANDS.get(ind)
    if band is None:
        return "mute"
    warn, danger, hi_bad = band
    if hi_bad:
        return "danger" if v >= danger else ("warn" if v >= warn else "calm")
    return "danger" if v <= danger else ("warn" if v <= warn else "calm")


def _urgence(watch: str, near: int, positions: list[dict], pnl: dict, elan: str = "", near_t: int = 0) -> str:
    debt_map = {
        "TYX": (1, "Taux US 30 ans (%)", 4, False),
        "Gold": (1, "Or ($/oz)", 0, True),
        "USDJPY": (1, "USD/JPY", 2, False),
        "VIX": (1, "VIX", 2, False),
        "HY_OAS": (1, "Spread HY (bp)", 2, False),
        "DXY": (1, "Dollar (DXY)", 2, False),
        "BTC": (1, "Bitcoin ($)", 0, True),
        "MOVE": (2, "Vol. obligataire (MOVE)", 2, False),
        "KRE": (2, "Banques r&eacute;gionales ($)", 2, False),
        "T10Y2Y": (2, "Pente 10a-2a (%)", 4, False),
        "BankReserves": (2, "R&eacute;serves bancaires Fed ($M)", 0, True),
        "CopperGold": (2, "Ratio cuivre/or", 4, False),
        "CoreCPI": (3, "Inflation core (%)", 4, False),
        "CPI": (3, "Inflation core (%)", 4, False),
        "FedBalanceSheet": (3, "Bilan Fed ($M)", 0, True),
        "FedBS": (3, "Bilan Fed ($M)", 0, True),
        "MfgIP": (3, "Production industrielle (%)", 4, False),
    }
    tnames = {1: "March&eacute; & liquidit&eacute;", 2: "Stress bancaire", 3: "Macro lente", 9: "Autres"}
    try:
        sig = _q("SELECT indicator_name, value, phase, timestamp FROM debt_signals WHERE id IN (SELECT MAX(id) FROM debt_signals GROUP BY indicator_name) ORDER BY timestamp DESC")
    except Exception:
        sig = []
    import datetime as _dt
    _today = _dt.date.today()
    _STALE = {1: 3, 2: 10, 3: 40, 9: 10}  # tolerance jours: daily / hebdo / mensuel
    tiers: dict[int, str] = {}
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
        tiers[tier] = tiers.get(tier, "") + (
            f'<div class="drow"><span class="ddot {dot}"></span><span class="dname">{label}</span>'
            f'<span class="dval {vcls}">{num}</span><span class="dp">P{ph}</span>{stale}</div>'
        )
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
            _conc.append(f"trim {_c['name']} &middot; +{_ov}&#8239;&euro;")
    _dev_cls, _dev_lab = ("danger", "&Agrave; TRAITER") if _conc else ("calm", "AU CALME")
    _dev_txt = " &nbsp;&middot;&nbsp; ".join(_conc) if _conc else "concentration sous tes plafonds"
    feu = (
        '<div class="plan"><div class="plan-h">&Agrave; arbitrer aujourd&rsquo;hui</div><div class="plan-row">'
        + f'<div class="pi {_dev_cls}"><span class="pn">{_dev_lab}</span><span class="pl">&eacute;cart de discipline</span><span class="pt">{_dev_txt}</span></div>'
        + f'<div class="pi calm"><span class="pn">{near_t}</span><span class="pl">winner(s) &ge;75% cible</span><span class="pt">laisse courir &middot; ex&eacute;cute ton plan</span></div>'
        + f'<div class="pi {"danger" if near else "calm"}"><span class="pn">{near}</span><span class="pl">ligne(s) &lt; 10% du stop</span><span class="pt">{"&agrave; surveiller" if near else "au calme"}</span></div>'
        + '</div>'
        + '<div style="margin-top:16px;padding-top:13px;border-top:1px solid var(--line);display:flex;gap:30px;flex-wrap:wrap;font-size:11.5px;color:var(--steel)">'
        + f'<span>{size_txt} &middot; sizing <b style="color:var(--ink)">&times;{_sfac:.1f}</b></span>'
        + '</div></div>'
    )
    _phase_col = {1: "acc", 2: "warn", 3: "warn", 4: "bear"}.get(cphase, "bear")
    gauge = (
        '<div class="gauge"><div class="ghead">'
        '<span class="gl">Sant&eacute; macro &middot; cr&eacute;dit / or / taux 30a / inflation / VIX</span>'
        + f'<span class="gv" style="color:var(--{_phase_col})">{clabel}<span style="font-size:12px;color:var(--steel);font-weight:500"> &middot; phase {cphase}/4 &middot; indice {score:.0f}</span></span></div>'
        + f'<div class="gtrack"><div class="gmark" style="left:{(cphase - 0.5) * 25:.0f}%"></div></div>'
        '<div class="glab"><span>stable</span><span>stress</span><span>alerte</span><span>crise</span></div></div>'
    )
    return (
        f'<section data-page="urgence"><div class="phead"><h2>Urgence</h2>'
        f'<div class="sub">&Eacute;lan vers les cibles &middot; marge avant les stops &middot; stress macro (/debt_status, en direct)</div></div>'
        f'{feu}{gauge}'
        f'<div class="cols">'
        f'<div><div class="ph3">Course vers la cible</div><div class="card pad">{elan}</div></div>'
        f'<div><div class="ph3">Positions proches du stop</div><div class="card pad">{watch}</div></div>'
        f'<div><div class="ph3">Moniteur de stress macro &mdash; {clabel}</div>'
        f'<div class="card pad"><div class="dlist"><style>.ddot.mute{{background:var(--steel);box-shadow:none;opacity:.6}}</style>{blocks}</div></div></div></div></section>'
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
        f'<div class="rfoot" title="Portefeuille {posture} &middot; surchauffe {heat:.0f}&deg; &middot; {near} proche(s) du stop">'
        f'<span class="statedot {tone}"></span>'
        f'<span class="rfm">{heat:.0f}&deg;</span>'
        f'<span class="rfm">{near}&#9888;</span>'
        f'{macro}</div>'
    )


def _pi(n: int, tks: list, lab: str, cls: str) -> str:
    nm = " &middot; ".join(tks[:3]) + ("&hellip;" if len(tks) > 3 else "")
    return f'<div class="pi {cls}"><span class="pn">{n}</span><span class="pl">{lab}</span><span class="pt">{nm or "&mdash;"}</span></div>'


def _journal() -> str:
    try:
        rows = _q("SELECT created_at, ticker, decision_type, reasoning FROM decisions ORDER BY created_at DESC LIMIT 6")
    except Exception:
        return ""
    if not rows:
        return ""
    tmap = {"entry": "Entr&eacute;e", "scale_in": "Renforcement", "partial_exit": "All&egrave;gement", "full_exit": "Sortie", "override": "Override", "no_action_flag": "Non-action"}
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


_LOGO = (
    '<svg width="46" height="36" viewBox="0 0 56 44" fill="none" xmlns="http://www.w3.org/2000/svg">'
    '<defs><linearGradient id="hlg" x1="0" y1="44" x2="56" y2="0">'
    '<stop offset="0" stop-color="#9A7B2E"/><stop offset=".45" stop-color="var(--id)"/><stop offset="1" stop-color="#F6DD9A"/>'
    '</linearGradient></defs>'
    '<g stroke="url(#hlg)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" fill="none">'
    '<ellipse cx="8" cy="31" rx="3" ry="4.4"/>'
    '<path d="M8.5 26.8 C13 19 21.5 17 28 19.2"/>'
    '<path d="M11 35 C16 38 23 37 28.5 31.5"/>'
    '<path d="M19 30 V25 M23 31 V20 M27 31 V15 M31 30 V18"/>'
    '<path d="M37 10 V34 M37 10 l5.5 4.5 -5.5 4.5"/>'
    '</g></svg>'
)

_TH_CSS = """
<style>
  .th-gap { margin-bottom:18px; }
  .th-hist { display:flex; flex-direction:column; gap:6px; padding:2px 0; }
  .th-hbar { display:flex; align-items:center; gap:11px; font-family:var(--fm); font-size:11.5px; }
  .th-hlab { width:24px; color:var(--steel); }
  .th-htrack { flex:1; height:13px; background:color-mix(in srgb,var(--ink) 4%,transparent); border-radius:7px; overflow:hidden; }
  .th-hfill { height:100%; border-radius:7px; background:linear-gradient(90deg,var(--acc),var(--acc2)); }
  .th-hn { width:22px; text-align:right; color:var(--ink); font-weight:600; }
  .th-grp { font-family:var(--fb); font-size:10.5px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin:34px 2px 13px; display:flex; align-items:center; gap:10px; }
  .th-grp::after { content:""; flex:1; height:1px; background:var(--line); }
  .th-row { display:grid; grid-template-columns:160px 46px 1fr; gap:12px; align-items:center; padding:13px 15px; border:1px solid var(--line); border-radius:12px; margin-bottom:0; background:color-mix(in srgb,var(--ink) 1.2%,transparent); cursor:pointer; transition:.15s; }
  .th-row:hover { border-color:var(--line2); background:color-mix(in srgb,var(--ink) 3.5%,transparent); }
  .th-id { display:flex; align-items:center; gap:9px; flex-wrap:wrap; }
  .th-conv { font-family:var(--fm); font-weight:700; font-size:11px; padding:2px 7px; border-radius:6px; }
  .th-conv.c5 { color:#0E1622; background:var(--id); }
  .th-conv.c4 { color:#0E1622; background:var(--acc); }
  .th-conv.c3 { color:#0E1622; background:var(--acc2); }
  .th-conv.c2 { color:var(--steel); border:1px solid var(--line2); }
  .th-conv.c1 { color:var(--steel); border:1px solid var(--line); opacity:.65; }
  .th-tk { font-weight:600; font-size:14px; }
  .th-w { font-family:var(--fm); font-size:12px; font-weight:600; color:var(--ink); text-align:right; align-self:center; }
  .th-dir { font-family:var(--fb); font-size:9.5px; color:var(--steel); text-transform:uppercase; letter-spacing:.12em; }
  .th-bar { display:flex; flex-direction:column; gap:6px; grid-column:1/-1; margin-top:8px; }
  .th-track { position:relative; height:10px; border-radius:5px; background:rgba(128,128,128,.10); }
  .th-sz { position:relative; height:5px; border-radius:3px; background:rgba(128,128,128,.14); }
  .th-szf { position:absolute; left:0; top:0; bottom:0; border-radius:3px; }
  .th-szc { position:absolute; top:-2px; bottom:-2px; left:76.9%; width:1.5px; border-radius:1px; background:rgba(128,128,128,.5); }
  .th-adj { font-family:var(--fm); font-size:10.5px; letter-spacing:.02em; line-height:1.3; }
  .th-adj.trim { color:var(--warn); }
  .th-adj.add { color:var(--acc2); }
  .th-adj.ok { color:var(--steel); }
  .th-szcol { display:flex; flex-direction:column; gap:5px; }
  .th-zone-loss { position:absolute; left:0; top:0; bottom:0; background:rgba(255,107,107,.13); }
  .th-zone-profit { position:absolute; right:0; top:0; bottom:0; background:rgba(55,224,160,.13); }
  .th-entry { position:absolute; top:0; bottom:0; border-left:1px dashed var(--steel); opacity:.7; transform:translateX(-1px); }
  .th-cur { position:absolute; top:50%; width:10px; height:10px; border-radius:50%; background:var(--ink); transform:translate(-50%,-50%); }
  .th-fill { position:absolute; top:0; bottom:0; border-radius:4px; }
  .th-ends { display:flex; justify-content:space-between; align-items:baseline; font-family:var(--fm); font-size:10.5px; }
  .th-stop { color:var(--bear); }
  .th-tgt { color:var(--acc); font-weight:600; }
  .th-na { font-family:var(--fm); font-size:11px; color:var(--steel); }
  .th-cat { font-family:var(--fm); font-size:10px; letter-spacing:.03em; color:var(--steel); background:rgba(124,137,166,.10); border:1px solid var(--line); border-radius:6px; padding:2px 8px; margin-left:2px; white-space:nowrap; }
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
    n_missing = n_fav = n_near = n_profit = 0
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
            if ratio is not None and ratio >= 2:
                n_fav += 1
            if d_stop < 10:
                n_near += 1
            if pnl_e is not None and pnl_e >= 0:
                n_profit += 1
        ths.append({
            "tk": tk, "conv": conv, "dir": (direction or "long"), "nm": names.get(tk, tk),
            "d_stop": d_stop, "d_tgt": d_tgt, "ratio": ratio, "frac": frac,
            "entry_frac": entry_frac, "pnl_e": pnl_e, "has_bar": has_bar,
            "cat": sectors.get(tk, ""), "tpart": tpart,
        })
    n = len(ths)
    med = sorted(t["conv"] for t in ths)[n // 2]
    c5_pct = dist[5] / n * 100
    infl = c5_pct > 20
    maxc = max(dist.values()) or 1

    hist = '<div class="th-hist">'
    for c in (5, 4, 3, 2, 1):
        hist += (
            f'<div class="th-hbar"><span class="th-hlab">c{c}</span>'
            f'<div class="th-htrack"><div class="th-hfill" style="width:{dist[c] / maxc * 100:.0f}%"></div></div>'
            f'<span class="th-hn">{dist[c]}</span></div>'
        )
    hist += '</div>'
    infl_msg = (
        f'&#9888; inflation de conviction : c5 = {c5_pct:.0f}% (seuil 20%)' if infl
        else f'c5 = {c5_pct:.0f}% &middot; pas d&rsquo;inflation (seuil 20%)'
    )

    hero = (
        '<div class="hero"><div><div class="hl">Th&egrave;ses actives</div>'
        f'<div class="big" style="color:var(--id)">{n}</div>'
        f'<div class="hsub">m&eacute;diane c{med} &middot; {n_fav} &agrave; asym&eacute;trie favorable &middot; {n_near} proche(s) du stop</div></div>'
        '<div style="flex:1;min-width:250px"><div class="hl">Distribution conviction</div>'
        f'{hist}<div class="hsub" style="margin-top:7px">{infl_msg}</div></div></div>'
    )

    pcls = "acc" if n_profit * 2 >= n else "negc"
    ncls = "negc" if n_near else "acc"
    kpis = (
        '<div class="kpis" style="grid-template-columns:repeat(3,1fr)">'
        f'<div class="kpi"><span class="kl">Asym&eacute;trie favorable</span><span class="kv acc">{n_fav}</span><span class="kd">ratio cible:stop &ge; 2</span></div>'
        f'<div class="kpi"><span class="kl">En profit</span><span class="kv {pcls}">{n_profit}/{n}</span><span class="kd">prix au-dessus de l&rsquo;entr&eacute;e</span></div>'
        f'<div class="kpi"><span class="kl">Proches du stop</span><span class="kv {ncls}">{n_near}</span><span class="kd">moins de 10% de marge</span></div></div>'
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
        groups += f'<div class="th-grp">{_TIER_LABEL.get(c, "Conviction " + str(c))} &middot; {len(grp)}</div><div class="th-grid">'
        for t in grp:
            if t["has_bar"]:
                curc = "var(--ink)"
                if t["entry_frac"] is not None:
                    ef = t["entry_frac"]
                    fc = t["frac"]
                    _fcol = "oklch(0.72 0.16 150)" if fc >= ef else "oklch(0.62 0.18 25)"
                    curc = "oklch(0.52 0.16 150)" if fc >= ef else "oklch(0.50 0.18 25)"
                    zones = (
                        f'<div class="th-fill" style="left:{min(ef, fc):.1f}%;width:{abs(fc - ef):.1f}%;background:{_fcol}"></div>'
                        f'<div class="th-entry" style="left:{ef:.1f}%;top:-1px;bottom:-1px;width:1px;background:rgba(128,128,128,.5)"></div>'
                    )
                else:
                    zones = ""
                bar = (
                    '<div class="th-bar"><div class="th-track">'
                    f'{zones}<div class="th-cur" style="left:{t["frac"]:.1f}%;background:{curc}"></div></div>'
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
                    _amsg = "Winner en profit, upside restant. Ton biais te pousse &agrave; s&eacute;curiser trop t&ocirc;t &mdash; laisse courir vers ta cible."
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
                _fill = min(wv / (_cappct * 1.3) * 100, 100)
                sizebar = f'<div class="th-sz"><div class="th-szf" style="width:{_fill:.0f}%;background:oklch({_lt:.2f} 0.22 {_hue:.0f})"></div><div class="th-szc"></div></div>'
                _d = wv - _tgt
                _de = f"{abs(_d) / 100 * vtot:,.0f}".replace(",", "&#8239;")
                if _d > 0.4:
                    _tail = f" &middot; &gt; cap {_cappct:.0f}%" if wv > _cappct else ""
                    adj = f'<div class="th-adj trim">all&eacute;ger &minus;{_de}&nbsp;&euro; &rarr; cible taille {_tgt:.1f}%{_tail}</div>'
                elif _d < -0.4:
                    adj = f'<div class="th-adj add">renforcer +{_de}&nbsp;&euro; &rarr; cible taille {_tgt:.1f}%</div>'
                else:
                    adj = f'<div class="th-adj ok">&check; cible taille {_tgt:.1f}%</div>'
            else:
                wtxt = f'{wv:.1f}%'
            groups += (
                f'<div class="th-row" data-tk="{t["tk"]}">'
                f'<div class="th-id"><span class="th-conv c{t["conv"]}">c{t["conv"]}</span>'
                f'<span class="th-tk">{t["nm"]}</span>{cat_html}</div>'
                f'<div class="th-w">{wtxt}</div><div class="th-szcol">{sizebar}{adj}</div>{bar}{anchor}</div>'
            )
        groups += '</div>'

    return (
        '<section data-page="theses"><div class="phead"><h2>Th&egrave;ses</h2>'
        '<div class="sub">Asym&eacute;trie cible / stop par conviction &mdash; la discipline rendue visible</div></div>'
        f'{_TH_CSS}{hero}{kpis}{gap}{groups}</section>'
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
  :root { --bg:#0A0E16; --panel:#121826; --line:#1E2738; --line2:#2C3550; --ink:#E8ECF4; --steel:#8A93A8;
    --acc:#34D9A0; --acc2:#2DD4BF; --id:#3D8BFF; --bear:#FF6B6B; --warn:#F5B544; --gold:#C9A86A;
    --fd:"Satoshi","Inter Tight",sans-serif; --fb:"Satoshi","Inter Tight",sans-serif; --fm:"IBM Plex Mono",monospace; --fo:"Satoshi",sans-serif;
    --bg2:#070A11; --panel2:#1A2234; --ink2:#C2C9D6; --steel2:#5C6678;
    --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:20px; --s6:28px; --r1:8px; --r2:12px; --r3:16px; --elev:0 18px 48px -28px rgba(0,0,0,.85);
    --glass:rgba(28,28,33,.5); --glass2:rgba(20,20,24,.6); --tape:rgba(14,14,17,.6); --barbg:#26262C;
    --glow:0 0 26px -7px color-mix(in srgb,var(--id) 66%,transparent); --glow2:0 0 36px -18px color-mix(in srgb,var(--id) 52%,transparent); }
  body.frost { --bg:#FAFCFF; --panel:#FFFFFF; --line:#D2DBE8; --line2:#C2CDDD; --ink:#15171E; --steel:#647088;
    --acc:#0E9F6E; --acc2:#0D9488; --id:#3D8BFF; --bear:#E5484D; --warn:#C2750A;
    --bg2:#FFFFFF; --panel2:#F1F3F6; --ink2:#3A3F4A; --steel2:#9AA1AD;
    --elev:0 14px 36px -24px rgba(30,55,105,.22);
    --glass:rgba(255,255,255,.92); --glass2:rgba(241,243,246,.7); --tape:rgba(246,247,249,.85); --barbg:#E7EAEF; --glow:0 0 30px -9px color-mix(in srgb,var(--id) 85%,transparent); --glow2:0 0 38px -15px color-mix(in srgb,var(--id) 70%,transparent); }
  body.frost::after { display:none; }
  * { box-sizing:border-box; }
  .dband { position:sticky; top:10px; z-index:45; display:flex; align-items:center; gap:13px; padding:11px 17px; margin:0 0 22px; border:1px solid var(--line2); border-radius:13px; background:color-mix(in srgb,var(--panel) 85%,transparent); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); cursor:pointer; transition:border-color .15s,background .15s; }
  .dband:hover { background:color-mix(in srgb,var(--panel) 95%,transparent); }
  .dband .dd { width:9px; height:9px; border-radius:50%; flex:none; }
  .dband.bear .dd { background:var(--bear); box-shadow:0 0 10px var(--bear); }
  .dband.acc .dd { background:var(--acc); box-shadow:0 0 9px var(--acc); }
  .dband .dv { font-family:var(--fd); font-weight:800; font-size:12.5px; letter-spacing:.05em; flex:none; }
  .dband.bear .dv { color:var(--bear); }
  .dband.acc .dv { color:var(--acc); }
  .dband .dx { font-family:var(--fm); font-size:12px; color:var(--steel); flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .dband .dn { font-family:var(--fm); font-size:12px; color:var(--ink); font-weight:600; flex:none; }
  .dband .dc { font-size:18px; line-height:1; color:var(--steel); flex:none; transition:transform .15s,color .15s; }
  .dband:hover .dc { color:var(--ink); transform:translateX(3px); }
  .sec-super { border:1px solid var(--line2); border-radius:14px; padding:4px 8px 8px; margin-bottom:16px; background:color-mix(in srgb,var(--ink) 2%,transparent); }
  .sec-superh { display:flex; align-items:baseline; justify-content:space-between; gap:12px; padding:13px 12px 10px; flex-wrap:wrap; }
  .sec-supername { font-family:var(--fd); font-weight:800; font-size:20px; letter-spacing:-.02em; color:var(--ink); }
  .sec-subwrap { display:flex; flex-direction:column; gap:4px; }
  .sec-super .sec-grp.sub { margin:0; border-left:2px solid var(--line); border-radius:0 10px 10px 0; }
  .sec-super .sec-grp.sub .sec-name { font-family:var(--fd); font-weight:600; font-size:13.5px; color:var(--steel); letter-spacing:0; }
  body { font-family:var(--fb); color:var(--ink); margin:0; display:flex; min-height:100vh; background:radial-gradient(1100px 680px at 82% -10%,rgba(61,139,255,.05),transparent 60%),radial-gradient(820px 560px at 6% 112%,rgba(61,139,255,.028),transparent 56%),var(--bg); background-attachment:fixed; -webkit-font-smoothing:antialiased; transition:background .3s ease,color .3s ease; }
  body::before { content:""; position:fixed; inset:0; z-index:-1; pointer-events:none; opacity:.85; transition:background .3s ease-out;
    background:radial-gradient(46% 40% at var(--mx,78%) var(--my,8%),rgba(61,139,255,.13),transparent 58%); }
  body::after { content:""; position:fixed; inset:0; z-index:-1; pointer-events:none; opacity:1;
    background-image:radial-gradient(1.4px 1.4px at 22% 24%,rgba(255,255,255,.9),transparent),radial-gradient(1.6px 1.6px at 68% 58%,rgba(200,225,255,.8),transparent),radial-gradient(1.3px 1.3px at 46% 82%,rgba(255,255,255,.7),transparent),radial-gradient(1.5px 1.5px at 86% 28%,rgba(255,255,255,.8),transparent),radial-gradient(1.3px 1.3px at 12% 70%,rgba(210,230,255,.7),transparent),radial-gradient(1.2px 1.2px at 34% 44%,rgba(255,255,255,.6),transparent),radial-gradient(1.4px 1.4px at 78% 80%,rgba(255,255,255,.65),transparent),radial-gradient(1.2px 1.2px at 58% 16%,rgba(220,235,255,.6),transparent);
    background-size:300px 300px,360px 360px,240px 240px,320px 320px,400px 400px,280px 280px,420px 420px,340px 340px; }
  .sidebar { width:78px; flex-shrink:0; background:transparent; border-right:1px solid var(--line); padding:20px 0; display:flex; flex-direction:column; align-items:center; }
  .logo { display:flex; align-items:center; justify-content:center; margin-bottom:22px; padding:0; }
  .logo svg { width:38px; height:auto; filter:drop-shadow(0 0 8px rgba(61,139,255,.4)); }
  .logo .wm { display:none; }
  .nav { display:flex; flex-direction:column; gap:4px; align-items:center; width:100%; }
  .nitem { position:relative; display:flex; align-items:center; justify-content:center; width:48px; height:48px; border-radius:12px; cursor:pointer; color:var(--steel); border-left:2px solid transparent; transition:.15s; }
  .nitem svg { width:26px; height:26px; }
  .nitem:hover { background:color-mix(in srgb,var(--ink) 4%,transparent); color:var(--ink); }
  .nitem.on { background:color-mix(in srgb,var(--id) 13%,transparent); color:var(--ink); border-left-color:var(--id); box-shadow:inset 0 0 22px -10px color-mix(in srgb,var(--id) 55%,transparent); }
  .nlab { position:absolute; left:56px; top:50%; transform:translateY(-50%); white-space:nowrap; background:var(--panel); border:1px solid var(--line2); border-radius:9px; padding:7px 12px; font-family:var(--fb); font-size:12.5px; font-weight:500; color:var(--ink); opacity:0; pointer-events:none; transition:opacity .14s ease; z-index:80; box-shadow:0 10px 26px -12px #000; }
  .nitem:hover .nlab { opacity:1; }
  .foot { margin-top:auto; padding:12px 0 2px; display:flex; flex-direction:column; align-items:center; gap:7px; }
  .rfoot { display:flex; flex-direction:column; align-items:center; gap:6px; }
  .rfm { font-family:var(--fm); font-size:10.5px; color:var(--steel); }
  .rfmacro { width:8px; height:8px; border-radius:2px; }
  .dot { width:7px; height:7px; border-radius:50%; background:var(--acc); box-shadow:0 0 9px var(--acc); }
  .wrap { flex:1; display:flex; flex-direction:column; min-width:0; }
  .tape { overflow:hidden; white-space:nowrap; padding:11px 0; }
  .tape .track2 { display:inline-block; animation:scroll 50s linear infinite; }
  .tape .ti { font-family:var(--fm); font-size:11.5px; margin:0 30px; letter-spacing:.02em; } .tape .ti b { color:var(--ink); } .tape .ti .pos { color:var(--acc); } .tape .ti .neg { color:var(--bear); }
  @keyframes scroll { from{transform:translateX(0);} to{transform:translateX(-50%);} }
  .tape8k { background:var(--tape); padding:7px 0; } .tape8k .ti .warn { color:var(--warn); } .tape8k .track2 { animation-duration:64s; }
  .statedot { width:8px; height:8px; border-radius:50%; animation:pulse 2.6s ease-in-out infinite; }
  .statedot.calm { background:var(--acc); color:var(--acc); } .statedot.warn { background:var(--warn); color:var(--warn); } .statedot.alert { background:var(--bear); color:var(--bear); }
  .main { padding:30px 52px 54px; max-width:1340px; }
  .phead { margin-bottom:18px; } .phead h2 { font-family:var(--fd); font-weight:800; font-size:26px; margin:0 0 4px; letter-spacing:-.03em; } .phead .sub { font-size:12px; color:var(--steel); }
  [data-page] { display:none; } [data-page].active { display:block; animation:fadein .42s ease; } @keyframes fadein { from { opacity:0; transform:translateY(5px); } to { opacity:1; transform:none; } }
  .hero { background:linear-gradient(135deg,rgba(61,139,255,.05),transparent 62%),var(--panel); border:1px solid var(--line2); border-radius:18px; padding:28px 34px; margin-bottom:26px; display:flex; align-items:center; gap:28px; flex-wrap:wrap; backdrop-filter:blur(9px); }
  .hero .big { font-family:var(--fd); font-weight:800; font-size:46px; line-height:.95; letter-spacing:-.04em; animation:glowpulse 4.6s ease-in-out infinite; }
  .hero .big.pos { color:var(--acc); text-shadow:0 0 34px rgba(55,224,160,.5); } .hero .big.neg { color:var(--bear); text-shadow:0 0 34px rgba(255,107,107,.45); }
  @keyframes glowpulse { 0%,100% { opacity:.93; } 50% { opacity:1; } }
  .hero .hl { font-family:var(--fb); font-size:9.5px; letter-spacing:.2em; text-transform:uppercase; color:var(--steel); margin-bottom:8px; }
  .hero .hsub { font-size:12.5px; color:var(--steel); margin-top:6px; }
  .distbar { flex:1; min-width:240px; } .distline { display:flex; height:8px; border-radius:4px; overflow:hidden; }
  .distline .g { background:oklch(0.72 0.16 150); } .distline .r { background:oklch(0.62 0.18 25); }
  .kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:18px; margin-bottom:26px; }
  .kpi { background:var(--glass); border:1px solid var(--line); border-radius:14px; padding:13px 16px; box-shadow:0 12px 36px -22px #000, inset 0 1px 0 rgba(255,255,255,.07), inset 0 0 0 1px color-mix(in srgb,var(--id) 5%,transparent); backdrop-filter:blur(9px); }
  .kl { display:block; font-family:var(--fb); font-size:9px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:7px; }
  .kv { font-family:var(--fd); font-weight:800; font-size:26px; letter-spacing:-.035em; line-height:1; }
  .kv.acc { color:var(--acc); } .kv.negc { color:var(--bear); } .kv.warn { color:var(--warn); } .kv.hot { color:#FB923C; } .kv.danger { color:var(--bear); } .kv.calm { color:var(--acc); }
  .kd { display:block; font-size:10px; color:var(--steel); margin-top:6px; }
  .cols { display:grid; grid-template-columns:1fr 1fr; gap:30px; align-items:start; }
  .colhead { display:flex; align-items:baseline; gap:9px; margin-bottom:12px; padding-left:2px; } .colhead .t { font-family:var(--fd); font-weight:700; font-size:15px; } .colhead .a { font-family:var(--fm); font-size:11.5px; color:var(--steel); }
  .sec-cols { display:grid; grid-template-columns:1fr 92px 96px 58px 72px 78px; gap:10px; padding:2px 16px 9px; font-family:var(--fb); font-size:9.5px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); border-bottom:1px solid var(--line); margin-bottom:12px; }
  .sec-cols .num { text-align:right; }
  .sec-grp { margin-bottom:22px; }
  .sec-h { display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin:0 4px 9px; }
  .sec-name { font-family:var(--fd); font-weight:700; font-size:17.5px; color:var(--ink); display:flex; align-items:center; gap:9px; }
  .sec-name::before { content:""; width:6px; height:6px; border-radius:2px; background:var(--id); box-shadow:var(--glow2); }
  .sec-meta { font-family:var(--fm); font-size:11.5px; color:var(--steel); white-space:nowrap; }
  .sec-pl.pos { color:var(--acc); } .sec-pl.neg { color:var(--bear); }
  .sec-rows { display:flex; flex-direction:column; gap:1px; }
  .sec-row { display:grid; grid-template-columns:1fr 92px 96px 58px 72px 78px; gap:10px; align-items:center; padding:7px 16px; border-radius:9px; font-family:var(--fm); font-size:12.5px; cursor:pointer; transition:background .12s; }
  .sec-row:hover { background:color-mix(in srgb,var(--ink) 4%,transparent); }
  .sec-row .num { text-align:right; color:var(--ink); font-variant-numeric:tabular-nums; }
  .sec-row .num.pos, .sec-pl.pos { color:var(--acc); } .sec-row .num.neg { color:var(--bear); }
  .sec-tk { font-weight:600; color:var(--ink); }
  .sec-nm { color:var(--steel); font-family:var(--fb); font-size:11px; margin-left:9px; font-weight:400; }
  /*CHER*/
  .card, .kpi { transition:transform .16s ease, box-shadow .16s ease; }
  .card:hover, .kpi:hover { transform:translateY(-2px); box-shadow:0 18px 44px -22px #000, var(--glow2), inset 0 1px 0 rgba(255,255,255,.09); }
  .tape .ti::after { content:"·"; margin-left:30px; color:var(--steel); opacity:.4; }
  /*METAL2*/
  .card, .kpi, .hero, .pfcard { border-top:1px solid color-mix(in srgb,var(--ink) 16%,var(--line)); }
  .th-grid { display:grid; grid-template-columns:1fr 1fr; gap:13px; margin-bottom:6px; }
  .th-anchor { grid-column:1/-1; margin-top:8px; padding:8px 11px; border-radius:8px; font-family:var(--fb); font-size:11.5px; line-height:1.5; color:var(--ink); border-left:2px solid var(--id); }
  .th-anchor.acc { border-left-color:var(--acc); background:color-mix(in srgb,var(--acc) 7%,transparent); }
  .th-anchor.warn { border-left-color:var(--warn); background:color-mix(in srgb,var(--warn) 9%,transparent); }
  /*THEME-ICO*/
  .modetgl .ico-moon { display:none; } body.frost .modetgl .ico-sun { display:none; } body.frost .modetgl .ico-moon { display:inline-block; }
  /*DVAL-STATE*/
  .dval.calm { color:var(--acc); } .dval.warn { color:#E0A33A; } .dval.danger { color:#EF4444; } .dval.mute { color:var(--steel); }
  .card { background:var(--glass); border:1px solid var(--line); border-radius:14px; padding:7px 24px; box-shadow:0 12px 36px -24px #000, inset 0 1px 0 rgba(255,255,255,.07), inset 0 0 0 1px color-mix(in srgb,var(--id) 5%,transparent); backdrop-filter:blur(9px); } .card.pad { padding:14px 18px; }
  .line { display:flex; justify-content:space-between; padding:9px 0; border-bottom:1px solid var(--line); font-size:13px; } .line:last-child { border-bottom:none; }
  .mono { font-family:var(--fm); font-weight:600; color:var(--ink); } .mono.pos { color:var(--acc); } .mono.neg { color:var(--bear); }
  .gauge { background:var(--glass); border:1px solid var(--line); border-radius:14px; padding:16px 20px; margin-bottom:15px; backdrop-filter:blur(9px); }
  .ghead { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:11px; } .ghead .gl { font-family:var(--fb); font-size:9.5px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); } .ghead .gv { font-family:var(--fd); font-weight:800; font-size:20px; }
  .gtrack { position:relative; height:6px; border-radius:3px; background:linear-gradient(90deg in oklch,oklch(0.80 0.15 150),oklch(0.80 0.16 90) 52%,oklch(0.63 0.18 25)); }
  .gmark { position:absolute; top:-3px; width:2px; height:12px; border-radius:1px; background:var(--ink); transform:translateX(-50%); }
  .glab { margin-top:9px; font-size:10px; color:var(--steel); display:flex; justify-content:space-between; font-family:var(--fm); letter-spacing:.08em; }
  .row { padding:9px 0; border-bottom:1px solid var(--line); opacity:0; animation:fade .45s ease forwards; } .row:last-child { border-bottom:none; }
  .row[data-tk] { cursor:pointer; } .row[data-tk]:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); }
  .rt { display:flex; justify-content:space-between; align-items:center; margin-bottom:9px; } .tk { font-family:var(--fm); font-weight:600; font-size:13px; }
  .tag { font-family:var(--fm); font-weight:600; font-size:11px; padding:3px 9px; border-radius:6px; }
  .tag.up { color:var(--acc); background:rgba(55,224,160,.12); } .tag.acc2 { color:var(--acc2); background:rgba(61,139,255,.12); }
  .tag.down,.tag.danger { color:var(--bear); background:rgba(255,107,107,.13); } .tag.warn { color:var(--warn); background:rgba(255,176,32,.14); } .tag.calm { color:var(--steel); background:rgba(124,137,166,.12); }
  .track { height:10px; background:var(--barbg); border-radius:5px; overflow:hidden; }
  .fill { height:100%; border-radius:4px; width:0; animation:grow .8s cubic-bezier(.2,.8,.2,1) forwards; }
  .fill.up { background:linear-gradient(90deg,#7CF0C4,var(--acc)); box-shadow:0 0 10px rgba(55,224,160,.35); }
  .fill.prismatic { background:linear-gradient(100deg,#FFE24A,#37E0A0,#00E0FF,#8A6CFF); box-shadow:0 0 12px rgba(55,224,160,.5); }
  .fill.danger { background:linear-gradient(90deg,#FF9A9A,var(--bear)); } .fill.warn { background:linear-gradient(90deg,#FFD27A,var(--warn)); } .fill.calm { background:#2A4439; } .fill.acc2 { background:linear-gradient(90deg,#8FF0FF,var(--acc2)); }
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
  .drow { display:grid; grid-template-columns:14px 1fr auto auto auto; align-items:center; gap:10px; padding:7px 0; font-size:13px; }
  .ddot { width:8px; height:8px; border-radius:50%; }
  .ddot.calm { background:#37E0A0; box-shadow:0 0 7px rgba(55,224,160,.6); } .ddot.warn { background:#FACC15; box-shadow:0 0 7px rgba(250,204,21,.6); }
  .ddot.hot { background:#FB923C; box-shadow:0 0 7px rgba(251,146,60,.6); } .ddot.danger { background:#EF4444; box-shadow:0 0 7px rgba(239,68,68,.6); }
  .dname { color:var(--ink); } .dval { font-family:var(--fm); text-align:right; color:var(--ink); } .dp { font-family:var(--fm); font-size:10px; color:var(--steel); }
  .stale { font-family:var(--fb); font-size:9px; color:var(--steel); opacity:.7; text-transform:uppercase; letter-spacing:.08em; }
  @keyframes grow { to { width:var(--w); } } @keyframes fade { to { opacity:1; } }
  .noanim [data-page].active, .noanim .row, .noanim .fill { animation:none !important; }
  .noanim .row { opacity:1 !important; } .noanim .fill { width:var(--w) !important; }
  @keyframes pulse { 0%,100% { opacity:1; box-shadow:0 0 10px currentColor; } 50% { opacity:.4; box-shadow:0 0 3px currentColor; } }
  .plan { background:var(--glass2); border:1px solid var(--line); border-radius:14px; padding:15px 20px; margin-bottom:18px; backdrop-filter:blur(9px); }
  .plan-h { font-family:var(--fb); font-size:9.5px; letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:13px; }
  .plan-row { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
  .pi { display:flex; flex-direction:column; gap:4px; padding-left:13px; border-left:2px solid var(--line2); border-radius:0; }
  .pi.danger { border-left-color:var(--bear); } .pi.warn { border-left-color:var(--warn); } .pi.calm { border-left-color:var(--acc); }
  .pn { font-family:var(--fd); font-weight:800; font-size:23px; line-height:1; }
  .pi.danger .pn { color:var(--bear); } .pi.warn .pn { color:var(--warn); } .pi.calm .pn { color:var(--acc); }
  .pl { font-size:11.5px; color:var(--ink); } .pt { font-family:var(--fm); font-size:10.5px; color:var(--steel); }
  .dt tbody tr:not(.prev) { cursor:pointer; }
  .loupe { position:fixed; inset:0; z-index:60; display:none; align-items:center; justify-content:center; background:rgba(6,10,18,.72); backdrop-filter:blur(6px); padding:34px; }
  .loupe.open { display:flex; }
  .loupe-card { position:relative; width:min(560px,100%); max-height:86vh; overflow:auto; background:var(--panel); border:1px solid var(--line2); border-radius:18px; padding:28px 30px; box-shadow:0 30px 90px -20px #000; }
  .loupe-x { position:absolute; top:14px; right:18px; background:none; border:none; color:var(--steel); font-size:26px; line-height:1; cursor:pointer; }
  .loupe-x:hover { color:var(--ink); }
  .lp-h { display:flex; align-items:baseline; gap:11px; }
  .lp-tk { font-family:var(--fo); font-weight:700; font-size:24px; letter-spacing:.04em; color:var(--id); }
  .lp-nm { font-size:13px; color:var(--steel); }
  .lp-meta { font-family:var(--fm); font-size:11px; color:var(--steel); margin:6px 0 18px; }
  .lp-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
  .lp-mom { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
  .lp-stat { background:var(--glass2); border:1px solid var(--line); border-radius:10px; padding:11px 13px; }
  .lp-sl { font-family:var(--fb); font-size:8.5px; letter-spacing:.14em; text-transform:uppercase; color:var(--steel); }
  .lp-sv { font-family:var(--fd); font-weight:800; font-size:18px; margin-top:5px; }
  .lp-sec { font-family:var(--fb); font-size:10px; letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin:20px 0 10px; border-top:1px solid var(--line); padding-top:14px; }
  .lp-score { display:flex; align-items:center; gap:10px; margin:8px 0; font-size:12px; }
  .lp-score .ln { width:92px; color:var(--steel); }
  .lp-score .bar { flex:1; height:6px; background:var(--barbg); border-radius:3px; overflow:hidden; }
  .lp-score .bf { display:block; height:100%; background:linear-gradient(90deg,#00E0FF,#37E0A0); }
  .lp-score .vv { font-family:var(--fm); width:32px; text-align:right; }
  .lp-ex { font-size:12.5px; color:var(--ink); line-height:1.6; opacity:.82; }
  .lp-empty { font-size:12px; color:var(--steel); padding:6px 0; }
  .tkc { cursor:pointer; transition:color .12s; } .tkc:hover { color:var(--id); }
  .lp-badge { display:inline-block; font-family:var(--fb); font-size:10px; letter-spacing:.1em; text-transform:uppercase; padding:2px 8px; border-radius:6px; border:1px solid currentColor; }
  .lp-badge.held { color:var(--acc); } .lp-badge.watch { color:var(--warn); } .lp-badge.univ { color:var(--acc2); } .lp-badge.out { color:var(--steel); }
  .sbwrap { display:flex; gap:20px; flex-wrap:wrap; align-items:center; }
  #sb-svg { width:320px; height:320px; flex:0 0 auto; }
  #sb-svg path { cursor:pointer; transition:opacity .15s; stroke:var(--panel); } #sb-svg path:hover { opacity:.85; }
  #sb-svg .sb-ct { fill:var(--ink); } #sb-svg .sb-c2 { fill:var(--steel); }
  #sb-panel { flex:1; min-width:230px; font-size:13px; }
  .sbrow { display:flex; justify-content:space-between; align-items:center; padding:7px 0; border-bottom:.5px solid var(--line); cursor:pointer; } .sbrow:last-child { border-bottom:none; } .sbrow:hover { background:color-mix(in srgb,var(--ink) 2.5%,transparent); }
  .qs { position:fixed; inset:0; z-index:70; display:none; align-items:flex-start; justify-content:center; background:rgba(6,10,18,.72); backdrop-filter:blur(6px); padding:12vh 20px 20px; }
  .qs.open { display:flex; }
  .qs-card { width:min(560px,100%); background:var(--panel); border:1px solid var(--line2); border-radius:16px; box-shadow:0 30px 90px -20px #000; overflow:hidden; }
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
  .pfcard { background:linear-gradient(135deg,rgba(61,139,255,.04),transparent 60%),var(--panel); border:1px solid var(--line2); border-radius:18px; padding:20px 24px; backdrop-filter:blur(9px); display:flex; flex-direction:column; }
  .pfcard .v { font-family:var(--fd); font-weight:800; font-size:30px; letter-spacing:-.03em; line-height:1; margin:8px 0 5px; color:var(--ink); }
  .pfcard .d { font-family:var(--fm); font-size:14px; font-weight:600; } .pfcard .d.pos { color:var(--acc); } .pfcard .d.neg { color:var(--bear); }
  .pfcard .distline { margin:15px 0 0; }
  .pfcard .sub2 { font-size:11.5px; color:var(--steel); margin-top:auto; padding-top:13px; } .pfcard .sub2 b { color:var(--ink); font-weight:600; }
  @media (max-width:980px) { .hrow { grid-template-columns:1fr; } }
  .modetgl { display:flex; align-items:center; justify-content:center; width:44px; height:44px; border-radius:12px; border:1px solid var(--line); background:transparent; color:var(--steel); cursor:pointer; transition:.15s; margin:16px 0 4px; }
  .modetgl svg { width:20px; height:20px; }
  .modetgl:hover { color:var(--id); border-color:var(--id); }
  body.frost::before { opacity:.4; }
  .hero, .pfcard { box-shadow:var(--elev),var(--glow); }
  .card, .kpi, .gauge, .plan { box-shadow:var(--elev),var(--glow2); }
  .loupe-card { box-shadow:0 30px 90px -20px #000,var(--glow); }
  .nitem.on { box-shadow:inset 0 0 20px -10px color-mix(in srgb,var(--id) 55%,transparent),var(--glow); }
  .nitem.on svg { filter:drop-shadow(0 0 6px color-mix(in srgb,var(--id) 70%,transparent)); }
  .tape { box-shadow:none; }
  .row[data-tk]:hover, .dt tbody tr:hover td, .th-row:hover, .sbrow:hover { box-shadow:var(--glow2); }
  .brk { margin-bottom:18px; }
  .brk-h { display:flex; justify-content:space-between; align-items:baseline; margin:0 2px 10px; flex-wrap:wrap; gap:8px; }
  .brk-n { font-family:var(--fd); font-weight:700; font-size:16px; }
  .brk-note { font-family:var(--fm); font-size:11px; color:var(--steel); margin-left:8px; }
  .brk-tot { font-family:var(--fm); font-size:13px; color:var(--ink); } .brk-tot span { color:var(--steel); font-size:11.5px; }
  .brk-body { display:flex; gap:24px; align-items:flex-start; flex-wrap:wrap; }
  .brk-viz { flex:0 0 172px; }
  .brk-tbl { flex:1; min-width:340px; }
  .brk-dwrap { position:relative; width:148px; height:148px; margin:2px auto 0; }
  .brk-donut { display:block; width:148px; height:148px; }
  .brk-seg { transition:opacity .15s; }
  .brk-donut:hover .brk-seg { opacity:.32; }
  .brk-donut .brk-seg:hover { opacity:1; }
  .brk-tip { position:absolute; inset:0; display:none; flex-direction:column; align-items:center; justify-content:center; text-align:center; pointer-events:none; gap:2px; }
  .brk-tip.on { display:flex; }
  .brk-tl { font-size:10.5px; letter-spacing:.04em; text-transform:uppercase; color:var(--steel); }
  .brk-tv { font-family:var(--fm); font-size:15px; color:var(--ink); }
  .brk-tp { font-family:var(--fm); font-size:11.5px; color:var(--steel); }
  .brk-leg { margin-top:14px; display:flex; flex-direction:column; gap:6px; }
  .brk-lg { display:flex; align-items:center; gap:8px; font-size:11.5px; line-height:1.35; }
  .brk-sw { width:9px; height:9px; border-radius:2px; flex:0 0 auto; }
  .brk-ln { flex:1; color:var(--ink); }
  .brk-lp { font-family:var(--fm); color:var(--steel); }
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
  let _raf=null;
  document.addEventListener('mousemove',function(e){
    if(_raf)return;
    _raf=requestAnimationFrame(function(){ _raf=null;
      document.body.style.setProperty('--mx',(e.clientX/window.innerWidth*100).toFixed(1)+'%');
      document.body.style.setProperty('--my',(e.clientY/window.innerHeight*100).toFixed(1)+'%');
    });
  });
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
    var SVG=document.getElementById('sb-svg'),PANEL=document.getElementById('sb-panel');
    if(!SVG||!PANEL||!window.SB_DATA)return;
    var DATA=window.SB_DATA,CX=160,CY=160,RI1=56,RO1=94,RI2=100,RO2=142,PAD=0.018,NS='http://www.w3.org/2000/svg';
    var total=0;DATA.forEach(function(s){s.tw=s.t.reduce(function(a,x){return a+(x.w||0);},0);total+=s.tw;});
    if(total<=0)return;
    function hx(h){h=h.replace('#','');return [parseInt(h.substr(0,2),16),parseInt(h.substr(2,2),16),parseInt(h.substr(4,2),16)];}
    function mix(a,b,t){var A=hx(a),B=hx(b);return 'rgb('+Math.round(A[0]+(B[0]-A[0])*t)+','+Math.round(A[1]+(B[1]-A[1])*t)+','+Math.round(A[2]+(B[2]-A[2])*t)+')';}
    function heat(p){if(p==null)return '#2A4439';var t=Math.min(1,Math.abs(p)/35);return p>=0?mix('#1C4A3A','#37E0A0',t):mix('#4A2222','#FF6B6B',t);}
    function pol(r,a){return [CX+r*Math.cos(a),CY+r*Math.sin(a)];}
    function arc(ri,ro,a0,a1){var lg=(a1-a0)>Math.PI?1:0,A=pol(ri,a0),B=pol(ro,a0),C=pol(ro,a1),D=pol(ri,a1);return 'M'+A[0]+' '+A[1]+'L'+B[0]+' '+B[1]+'A'+ro+' '+ro+' 0 '+lg+' 1 '+C[0]+' '+C[1]+'L'+D[0]+' '+D[1]+'A'+ri+' '+ri+' 0 '+lg+' 0 '+A[0]+' '+A[1]+'Z';}
    function mkp(tag,at){var e=document.createElementNS(NS,tag);for(var k in at)e.setAttribute(k,at[k]);return e;}
    var groups={},cur=-Math.PI/2;
    DATA.forEach(function(s){
      var ang=s.tw/total*2*Math.PI,a0=cur+PAD/2,a1=cur+ang-PAD/2,mid=(a0+a1)/2;
      var g=mkp('g',{'data-sec':s.name});g.style.cursor='pointer';g.style.transition='transform .18s ease,opacity .18s ease';
      g.dataset.mx=Math.cos(mid);g.dataset.my=Math.sin(mid);
      g.appendChild(mkp('path',{d:arc(RI1,RO1,a0,a1),fill:s.col,'fill-opacity':'0.85',stroke:'#0E1622','stroke-width':'1.5','data-sec':s.name}));
      var sub=cur;
      s.t.forEach(function(x){var ta=x.w/total*2*Math.PI,b0=sub+PAD/2,b1=sub+ta-PAD/2;if(b1<=b0){b0=sub;b1=sub+ta;}g.appendChild(mkp('path',{d:arc(RI2,RO2,b0,b1),fill:s.col,'fill-opacity':'0.5',stroke:'#0E1622','stroke-width':'1.5','data-tk':x.tk,'data-sec':s.name}));sub+=ta;});
      groups[s.name]=g;SVG.appendChild(g);cur+=ang;
    });
    var ct=mkp('text',{x:CX,y:CY-3,'text-anchor':'middle','class':'sb-ct','font-size':'19','font-weight':'600'});ct.textContent=Math.round(total/1000)+'k'+String.fromCharCode(8364);SVG.appendChild(ct);
    var c2=mkp('text',{x:CX,y:CY+15,'text-anchor':'middle','class':'sb-c2','font-size':'11','font-family':'monospace'});c2.textContent=DATA.length+' secteurs';SVG.appendChild(c2);
    function pv(p){return p==null?'&mdash;':((p>=0?'+':'')+p+'%');}
    function rw(l,v,c){return '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:.5px solid var(--line)"><span style="color:var(--steel)">'+l+'</span><span class="mono" style="color:'+(c||'var(--ink)')+'">'+v+'</span></div>';}
    function overview(){
      for(var k in groups){groups[k].style.transform='';groups[k].style.opacity='1';}
      var top=DATA.slice().sort(function(a,b){return b.tw-a.tw;})[0],tp=Math.round(top.tw/total*100),ov=tp>=30;
      PANEL.innerHTML='<div style="font-family:var(--fb);font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--steel);margin-bottom:10px">Vue d&rsquo;ensemble</div>'
        +rw('Plus gros secteur',top.name+' &middot; '+tp+'%',ov?'var(--bear)':'var(--acc)')
        +rw('Secteurs',DATA.length+'')+rw('Lignes',DATA.reduce(function(a,s){return a+s.t.length;},0)+'')
        +'<div style="margin-top:12px;font-size:12px;color:'+(ov?'var(--warn)':'var(--steel)')+'">'+(ov?('&#9888; '+top.name+' au-dessus du plafond 30%'):'sous le plafond 30%')+'</div>'
        +'<div style="margin-top:14px;font-size:11px;color:var(--steel)">clique un secteur pour le morceler</div>';
    }
    function showSector(name){
      var s=null;DATA.forEach(function(d){if(d.name===name)s=d;});if(!s)return;
      for(var k in groups){var g=groups[k];if(k===name){g.style.transform='translate('+(g.dataset.mx*12)+'px,'+(g.dataset.my*12)+'px)';g.style.opacity='1';}else{g.style.transform='';g.style.opacity='0.22';}}
      var rows=s.t.slice().sort(function(a,b){return b.w-a.w;}).map(function(x){var pc=x.pnl==null?'var(--steel)':(x.pnl>=0?'var(--acc)':'var(--bear)');return '<div class="sbrow" data-tk="'+x.tk+'"><span class="mono">'+x.tk+'</span><span style="display:flex;gap:12px;align-items:center"><span class="mono" style="width:48px;text-align:right;color:'+pc+'">'+pv(x.pnl)+'</span><span class="mono" style="color:var(--steel);font-size:11px">stop '+(x.down==null?'&mdash;':x.down+'%')+'</span></span></div>';}).join('');
      PANEL.innerHTML='<div class="sb-back" style="cursor:pointer;color:var(--steel);font-size:11px;margin-bottom:8px">&larr; vue d&rsquo;ensemble</div><div style="display:flex;align-items:center;gap:8px;margin-bottom:10px"><span style="width:10px;height:10px;border-radius:2px;background:'+s.col+'"></span><span style="font-family:var(--fd);font-weight:700;font-size:14px">'+s.name+'</span><span class="mono" style="color:var(--steel);font-size:12px">'+Math.round(s.tw/total*100)+'% &middot; '+s.t.length+' lignes</span></div>'+rows+'<div style="margin-top:10px;font-size:11px;color:var(--steel)">clique un titre pour sa fiche</div>';
    }
    SVG.addEventListener('click',function(e){var t=e.target;if(t.dataset&&t.dataset.tk)return;if(t.dataset&&t.dataset.sec)showSector(t.dataset.sec);});
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
            ana[tk] = {"date": str(ts)[:10], "type": str(typ), "excerpt": exc,
                       "scores": scores, "regime": str(regime), "narr": narr}
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
            "weight_eur": None, "weight_pct": None, "pnl": None,
            "down": None, "up": None, "ratio": None,
            "analysis": ana.get(tk),
        }
    return out


_LOUPE_HTML = (
    '<div id="loupe" class="loupe"><div class="loupe-card">'
    '<button class="loupe-x" onclick="closeLoupe()" aria-label="Fermer">&times;</button>'
    '<div id="loupe-body"></div></div></div>'
)


_EU_SUFFIX = (".PA", ".AS", ".DE", ".MI", ".ST", ".BR", ".MC", ".SW", ".VI", ".HE", ".CO", ".OL", ".LS", ".L", ".F", ".PL", ".WA", ".AT")


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
    total = sum(v for _, v in segs) or 1
    circ = 376.99
    arcs = []
    leg = []
    acc = 0.0
    for label, v in segs:
        col = SECTOR_COLORS.get(label, "#6B7686")
        pct = v / total * 100
        seg = v / total * circ
        off = acc / total * circ
        acc += v
        vstr = f'{v:,.0f}'.replace(',', '&#8239;')
        arcs.append(
            f'<circle class="brk-seg" cx="74" cy="74" r="60" fill="none" stroke="{col}" stroke-width="28" stroke-dasharray="{seg:.2f} {circ - seg:.2f}" stroke-dashoffset="{-off:.2f}" transform="rotate(-90 74 74)" data-label="{label}" data-val="{vstr}&nbsp;&euro;" data-pct="{pct:.0f}%"></circle>'
        )
        leg.append(
            f'<div class="brk-lg"><span class="brk-sw" style="background:{col}"></span><span class="brk-ln">{label}</span><span class="brk-lp">{pct:.0f}%</span></div>'
        )
    return (
        f'<div class="brk-viz"><div class="brk-dwrap"><svg class="brk-donut" viewBox="0 0 148 148">{"".join(arcs)}</svg><div class="brk-tip"></div></div><div class="brk-leg">{"".join(leg)}</div></div>'
    )


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
        pstr = "&mdash;" if pc is None else f'{"+" if pc >= 0 else ""}{pc:.1f}%'
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
        f'<tbody>{rows}</tbody></table></div></div></div></div>'
    )


def _broker_tables(positions: list[dict], names: dict, pnl: dict, sectors: dict) -> str:
    grand = sum(_broker_value(p, pnl) for p in positions) or 1
    tr = [p for p in positions if _broker(p["ticker"]) == "tr"]
    eu = [p for p in positions if _broker(p["ticker"]) == "bourso"]
    head = (
        '<div class="colhead" style="margin-top:6px"><span class="t">Comptes</span>'
        '<span class="a">par courtier &middot; tri&eacute; par valeur</span></div>'
    )
    return head + _broker_one("Trade Republic", "hors Europe", tr, grand, names, pnl, sectors) + _broker_one("Boursorama", "PEA &middot; Europe", eu, grand, names, pnl, sectors)


_MODE_BTN = """<button class="modetgl" title="Mode clair / sombre" onclick="document.body.classList.toggle('frost');try{localStorage.setItem('hmdl-theme',document.body.classList.contains('frost')?'frost':'carbon')}catch(e){}"><svg class="ico-sun" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg><svg class="ico-moon" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button>"""
_THEME_INIT = "<script>try{var t=localStorage.getItem('hmdl-theme');if(t==='frost')document.body.classList.add('frost');}catch(e){}</script>"


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


_DONUT_JS = """<script>
document.addEventListener('DOMContentLoaded',function(){
  document.querySelectorAll('.brk-viz').forEach(function(viz){
    var tip=viz.querySelector('.brk-tip'); if(!tip)return;
    viz.querySelectorAll('.brk-seg').forEach(function(s){
      s.addEventListener('mouseenter',function(){
        tip.innerHTML='<span class="brk-tl">'+s.dataset.label
          +'</span><span class="brk-tv">'+s.dataset.val
          +'</span><span class="brk-tp">'+s.dataset.pct+'</span>';
        tip.classList.add('on');
      });
      s.addEventListener('mouseleave',function(){tip.classList.remove('on');});
    });
  });
});
</script>"""

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
        sb_secs.setdefault(sectors.get(p["ticker"], "Sans th&egrave;se"), []).append({
            "tk": p["ticker"], "w": round(p["weight"] * (1 + pnl.get(p["ticker"], 0) / 100.0)),
            "pnl": round(pnl[p["ticker"]], 1) if p["ticker"] in pnl else None,
            "down": round(sb_down[p["ticker"]], 1) if sb_down.get(p["ticker"]) is not None else None,
        })
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
    near_stop_tk = [r["ticker"] for r in sorted(computed, key=lambda r: r.get("downside_pct", 999.0)) if r.get("downside_pct") is not None and r["downside_pct"] < 10]
    near_tgt_tk = [r["ticker"] for r in sorted(computed, key=lambda r: r.get("upside_pct", 999.0)) if r.get("upside_pct") is not None and r["upside_pct"] < 12]

    disc_hero = (
        '<div class="hero posture"><div class="hl">&Agrave; surveiller &mdash; m&eacute;canique, non prescriptif</div><div class="plan-row">'
        + _pi(len(near_tgt_tk), near_tgt_tk, "candidat(s) prise de profit", "warn" if near_tgt_tk else "calm")
        + _pi(len(near_stop_tk), near_stop_tk, "proche(s) du stop", "danger" if near_stop_tk else "calm")
        + '</div></div>'
    )

    tape_items = ""
    for tk, p in sorted(pnl.items(), key=lambda x: -x[1]):
        cls = "pos" if p >= 0 else "neg"
        tape_items += f'<span class="ti"><b>{tk}</b> <span class="{cls}">{"+" if p >= 0 else ""}{p:.1f}%</span></span>'
    tape = f'<div class="tape"><div class="track2">{tape_items}{tape_items}</div></div>'
    tape8k = _tape_8k()

    journal_html = _journal()
    journal_block = (
        '<div class="colhead" style="margin-top:22px"><span class="t">Derni&egrave;res d&eacute;cisions</span><span class="a">journal Telegram</span></div>'
        f'<div class="card pad">{journal_html}</div>'
    ) if journal_html else ""
    _up = {r["ticker"]: r.get("upside_pct") for r in computed}
    _dn = {r["ticker"]: r.get("downside_pct") for r in computed}
    _cibles = sorted((tk for tk in _up if _up[tk] is not None), key=lambda tk: _up[tk])[:6]
    _stops = sorted((tk for tk in _dn if _dn[tk] is not None), key=lambda tk: _dn[tk])[:6]
    gain = "".join(
        f'<div class="line"><span class="mono">{tk}</span><span class="mono"><b>+{_up[tk]:.0f}%</b> &rarr; cible</span></div>'
        for tk in _cibles
    ) or '<div class="empty" style="padding:18px 0">aucune ligne pr&egrave;s de sa cible</div>'
    lose = "".join(
        f'<div class="line"><span class="mono">{tk}</span><span class="mono"><b>{_dn[tk]:.0f}%</b> de marge</span></div>'
        for tk in _stops
    ) or '<div class="empty" style="padding:18px 0">toutes loin de leur stop</div>'
    vigie = (
        f'<section data-page="vigie" class="active"><div class="phead"><h2>Vue d\'ensemble</h2>'
        f'<div class="sub">Posture de discipline &middot; ce sur quoi agir aujourd&rsquo;hui</div></div>'
        f'<div class="hrow">'
        f'<div class="pfcard"><div class="hl">Valeur du portefeuille</div>'
        f'<div class="v">{pf_val_str}&nbsp;&euro;</div>'
        f'<div class="d {vcls}">{pf_pe}&euro; ({"+" if port_pnl >= 0 else ""}{port_pnl:.1f}%)</div>'
        f'<div class="distline"><div class="g" style="width:{gpct:.0f}%"></div><div class="r" style="width:{100 - gpct:.0f}%"></div></div>'
        f'<div class="sub2"><b>{n_gain}/{n_pnl}</b> en gain &middot; {gpct:.0f}% du capital &middot; {pf_cost_str}&euro; investi</div></div>{disc_hero}</div>'
        f'<div class="cols"><div class="col"><div class="colhead"><span class="t">Plus proches de la cible</span><span class="a">ta th&egrave;se se r&eacute;alise</span></div>'
        f'<div class="card pad">{gain}</div></div><div class="col"><div class="colhead"><span class="t">Plus proches du stop</span><span class="a">marge avant invalidation</span></div>'
        f'<div class="card pad">{lose}</div></div></div>'
        f'<div class="cols"><div class="col"><div class="colhead"><span class="t">Hausses du jour</span><span class="a">vs cl&ocirc;ture veille</span></div>'
        f'<div class="card pad">{day_up}</div></div><div class="col"><div class="colhead"><span class="t">Baisses du jour</span><span class="a">vs cl&ocirc;ture veille</span></div>'
        f'<div class="card pad">{day_dn}</div></div></div>'
        f'<div class="colhead" style="margin-top:22px"><span class="t">&Eacute;ch&eacute;ances &agrave; venir</span></div>'
        f'<div class="card pad">{erows}</div>'
        f'{journal_block}</section>'
    )
    watch_zone_tk = [r["ticker"] for r in sorted(computed, key=lambda r: r.get("downside_pct", 999.0)) if r.get("downside_pct") is not None and 10 <= r["downside_pct"] < 20]
    pos_plan = (
        '<div class="plan"><div class="plan-h">Aujourd&rsquo;hui sur les positions</div><div class="plan-row">'
        + _pi(len(near_stop_tk), near_stop_tk, "au stop (&lt;10%)", "danger" if near_stop_tk else "calm")
        + _pi(len(watch_zone_tk), watch_zone_tk, "sous surveillance (10-20%)", "warn" if watch_zone_tk else "calm")
        + _pi(len(near_tgt_tk), near_tgt_tk, "proche d&rsquo;un palier", "warn" if near_tgt_tk else "calm")
        + '</div></div>'
    )
    broker_html = _broker_tables(positions, names, pnl, sectors)
    positions_pg = (
        f'<section data-page="positions"><div class="phead"><h2>Positions</h2>'
        f'<div class="sub">Marge &agrave; la hausse vers la cible &middot; &agrave; la baisse vers le stop</div></div>'
        f'{pos_plan}{broker_html}</section>'
    )

    # --- Bandeau d'ecart de discipline (sticky, haut de page) ---
    # v1: axe concentration (cluster hors plafond, source unique _cluster_health) + axe stop (near).
    # axe prise-profit -> ajoute apres ADR target_partial.
    _dev = []
    for _c in _cluster_health(positions, pnl):
        if _c["breached"]:
            _ov = f"{_c['over_eur']:,.0f}".replace(",", "&#8239;")
            _dev.append(f"trim {_c['name']} &middot; +{_ov}&#8239;&euro;")
    if near:
        _dev.append(f"{near} ligne(s) &lt; 10% du stop")
    _dn = len(_dev)
    _dcls, _dverdict = ("bear", "&Agrave; TRAITER") if _dn else ("acc", "AU CALME")
    _ddetail = " &nbsp;&middot;&nbsp; ".join(_dev) if _dev else "tout sous tes r&egrave;gles"
    _dband = (
        f'<div class="dband {_dcls}" onclick="document.querySelector(&#39;[data-nav=concentration]&#39;).click()">'
        f'<span class="dd"></span><span class="dv">{_dverdict}</span>'
        f'<span class="dx">{_ddetail}</span>'
        f'<span class="dn">{_dn} &agrave; traiter</span><span class="dc">&rsaquo;</span></div>'
    )
    elan, near_t = _elan_watch(computed)
    body = (
        f'<aside class="sidebar"><div class="logo">{_LOGO}<span class="wm">HEIMDALL<small>sentinelle</small></span></div>'
        f'{_NAV}{_MODE_BTN}<div class="foot">{_rail_foot(near, heat)}<span class="dot" title="en veille &middot; maj {stamp}"></span></div></aside>{_THEME_INIT}{_SORT_JS}{_CSORT_JS}{_DONUT_JS}'
        f'<div class="wrap">{tape}{tape8k}<main class="main">{_dband}'
        + vigie + positions_pg + _theses(names, sectors, positions, pnl) + _concentration(positions, planned, sectors, names, pnl, daily)
        + _signaux() + _urgence(watch, near, positions, pnl, elan, near_t)
        + "</main></div>" + _LOUPE_HTML
    )

    html = (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta http-equiv="refresh" content="300">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><script>try{if(sessionStorage.getItem("h_seen"))document.documentElement.classList.add("noanim");sessionStorage.setItem("h_seen","1");}catch(e){}</script><title>Heimdall</title>'
        ''
        '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Sans+Runic&display=swap" rel="stylesheet">'
        '<link href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,900&display=swap" rel="stylesheet">'
        "<style>" + _CSS + "</style></head><body>"
        + body
        + "<script>window.TK=" + json.dumps(loupe_data) + ";window.SB_DATA=" + json.dumps(sb_data) + ";</script>"
        + ''
        + "<script>" + _APP_JS + "</script>"
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
