"""Track record PRESAGE-managed — rendement honnête depuis l'inception.

Corrige les deux biais du métrique naïf `portfolio_snapshots.pnl_pct` :

1. **Survivorship** — `pnl_pct = value/cost-1` ne mesure que le latent sur les
   lots ENCORE ouverts. Le P&L réalisé (positions fermées + trims partiels)
   disparaît. Un fonds doit créditer le réalisé.
2. **Contribution-conflation** — le dénominateur bouge à chaque ajout/trim ;
   un apport de capital gonfle la NAV sans être de la performance.

Choix méthodologique (acté 2026-07-03) : on mesure la période **PRESAGE-managed
seulement** (depuis `INCEPTION`), pas l'historique Trade Republic pré-inception
(2021-2026) qui est du cost-basis/contexte, pas de la performance du système.

La courbe managed EST déjà `portfolio_snapshots` (forward-capturée, zéro
look-ahead). On la corrige en neutralisant les flux de capital de la période :

    perf_eur = (NAV_t - NAV_0) - apport_net_capital

et on donne le rendement money-weighted (XIRR) qui neutralise correctement le
timing des flux.

Read-only strict. Aucun write, aucun coût LLM. Fail-closed : None si pas de
snapshot à l'inception (jamais un chiffre fabriqué — cf L15).

`ADJUST` (side de réconciliation broker) est EXCLU des flux : ce n'est ni un
apport ni un retrait de capital, juste un recalage de qty que la vue positions
nette à zéro. L'inclure casserait la reconstruction (cf audit C, cas GEV).
"""

from __future__ import annotations

from datetime import date

from shared import storage

INCEPTION = "2026-05-23"  # 1er portfolio_snapshot forward = prise en main système
_EXCLUDE_TICKER_PREFIXES = ("SMOKE", "SMK")
_EXCLUDE_TICKERS = frozenset({"TEST"})


def _is_real_ticker(tk: str) -> bool:
    return tk not in _EXCLUDE_TICKERS and not tk.startswith(_EXCLUDE_TICKER_PREFIXES)


def _xirr(cashflows: list[tuple[str, float]]) -> float | None:
    """Money-weighted return annualisé par bisection. cashflows = [(iso_date, eur)].

    Convention : sorties de cash négatives (achat, NAV initiale), entrées positives
    (vente, NAV terminale). None si pas de changement de signe (XIRR indéfini).
    """
    if len(cashflows) < 2:
        return None
    signs = {1 if a > 0 else -1 for _, a in cashflows if a}
    if len(signs) < 2:
        return None

    def _d(s: str) -> date:
        y, m, dd = (int(x) for x in s.split("-"))
        return date(y, m, dd)

    d0 = min(_d(d) for d, _ in cashflows)
    pts = [(((_d(d) - d0).days) / 365.0, a) for d, a in cashflows]

    def npv(r: float) -> float:
        return sum(a / (1.0 + r) ** t for t, a in pts)

    lo, hi = -0.999, 100.0
    if npv(lo) * npv(hi) > 0:  # pas de racine dans l'intervalle
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
    return mid


def compute_managed_return(
    nav0: float, navt: float, flows: list[tuple[str, float]], inception: str, terminal_date: str
) -> dict:
    """Pur : NAV initiale/terminale + flux signés (BUY négatif, SELL positif) → métriques.

    flows = liste de (iso_date, eur_signé) des trades de la période, hors ADJUST.
    """
    net_contrib = -sum(a for _, a in flows)  # BUY négatif → apport net positif
    perf_eur = (navt - nav0) - net_contrib
    perf_pct = perf_eur / nav0 * 100 if nav0 else None
    days = (
        date(*(int(x) for x in terminal_date.split("-")))
        - date(*(int(x) for x in inception.split("-")))
    ).days
    ann_pct = None
    if perf_pct is not None and days > 0:
        ann_pct = ((1 + perf_eur / nav0) ** (365.0 / days) - 1) * 100
    xirr_series = [(inception, -nav0), *flows, (terminal_date, navt)]
    xirr = _xirr(xirr_series)
    return {
        "inception": inception,
        "terminal_date": terminal_date,
        "days": days,
        "nav0_eur": round(nav0, 2),
        "navt_eur": round(navt, 2),
        "nav_change_eur": round(navt - nav0, 2),
        "net_contrib_eur": round(net_contrib, 2),
        "perf_eur": round(perf_eur, 2),
        "perf_pct": round(perf_pct, 2) if perf_pct is not None else None,
        "perf_pct_annualized": round(ann_pct, 1) if ann_pct is not None else None,
        "xirr_pct": round(xirr * 100, 1) if xirr is not None else None,
        "n_flows": len(flows),
        "low_n_warning": days < 90,  # <90j = variance-dominé, annualisation trompeuse
    }


def managed_track_record(inception: str = INCEPTION) -> dict | None:
    """Rendement PRESAGE-managed réel depuis l'inception. None si pas de snapshot."""
    with storage.db_ro() as cx:
        snaps = cx.execute(
            "SELECT snapshot_date, total_value_eur FROM portfolio_snapshots "
            "WHERE total_value_eur IS NOT NULL AND snapshot_date >= ? "
            "ORDER BY snapshot_date",
            (inception,),
        ).fetchall()
        if len(snaps) < 2:
            return None
        nav0 = float(snaps[0]["total_value_eur"])
        navt = float(snaps[-1]["total_value_eur"])
        terminal_date = snaps[-1]["snapshot_date"]
        rows = cx.execute(
            "SELECT ticker, side, qty, price_native, fees_native, fx_at_trade, "
            "substr(trade_date,1,10) d FROM transactions "
            "WHERE substr(trade_date,1,10) >= ? AND side IN ('BUY','SELL') "
            "ORDER BY trade_date",
            (inception,),
        ).fetchall()
    flows: list[tuple[str, float]] = []
    for r in rows:
        if not _is_real_ticker(r["ticker"]):
            continue
        fx = r["fx_at_trade"] or 1.0
        gross = (r["qty"] or 0) * (r["price_native"] or 0) * fx
        fee = (r["fees_native"] or 0) * fx
        amt = -(gross + fee) if r["side"] == "BUY" else (gross - fee)
        flows.append((r["d"], amt))
    return compute_managed_return(nav0, navt, flows, inception, terminal_date)


if __name__ == "__main__":
    tr = managed_track_record()
    if tr is None:
        print("track_record: pas de snapshot à l'inception (fail-closed)")
    else:
        print(
            f"PRESAGE-managed {tr['inception']} → {tr['terminal_date']} ({tr['days']}j)\n"
            f"  NAV {tr['nav0_eur']:,.0f} → {tr['navt_eur']:,.0f} € "
            f"(Δ {tr['nav_change_eur']:+,.0f}, apport net {tr['net_contrib_eur']:+,.0f})\n"
            f"  PERF RÉELLE (flux-neutralisée) : {tr['perf_eur']:+,.0f} € = {tr['perf_pct']:+.2f}%"
            f"  |  XIRR ≈ {tr['xirr_pct']:+.0f}%/an"
            + ("  [N<90j : variance-dominé]" if tr["low_n_warning"] else "")
        )
