"""Sprint 16 — PEA / CTO wrapper + recolte de moins-values + FX exposure.

Per la critique : "Placement PEA vs CTO : flagger un nom eligible PEA loge
inutilement au CTO. Recolte de moins-values : Vertiv est dans le rouge ->
moins-value mobilisable au CTO."

Heuristique PEA eligibility (sans appel LLM) :
  - Tickers .PA (Paris), .AS (Amsterdam), .DE (Frankfurt), .MI (Milan),
    .L (London — UK pre/post-Brexit, accepte au PEA), .MC (Madrid),
    .BR (Brussels) = eligibles PEA
  - US/Asian (.T, .HK, .KS, no-suffix US) = NON eligibles PEA
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)


_PEA_ELIGIBLE_SUFFIXES = (".PA", ".AS", ".DE", ".MI", ".L", ".MC", ".BR", ".SW", ".LS", ".VI")


def _is_pea_eligible(ticker: str) -> bool:
    return bool(re.search(r"\.[A-Z]{1,4}$", ticker)) and any(
        ticker.endswith(s) for s in _PEA_ELIGIBLE_SUFFIXES
    )


def compute_wrapper_allocation() -> dict:
    """Sum book weight per wrapper (PEA / CTO / unknown).

    For each held ticker : reads positions.wrapper if set, else fallback
    to 'CTO' (default). Identifies tickers PEA-eligible currently in CTO
    (placement sous-optimal).
    """
    from dashboard.render import _positions

    positions = _positions()
    total = sum(p.get("weight", 0) for p in positions) or 1

    alloc: dict = {"PEA": 0.0, "CTO": 0.0, "unknown": 0.0}
    misallocated = []  # PEA-eligible in CTO
    for p in positions:
        wrapper = (p.get("wrapper") or "CTO").upper()
        alloc[wrapper if wrapper in alloc else "unknown"] += p["weight"]
        if wrapper == "CTO" and _is_pea_eligible(p["ticker"]):
            misallocated.append({
                "ticker": p["ticker"],
                "weight_eur": round(p["weight"], 0),
                "weight_pct": round(p["weight"] / total * 100, 1),
            })

    for k in alloc:
        alloc[k] = round(alloc[k], 0)
    return {
        "allocation_eur": alloc,
        "allocation_pct": {k: round(v / total * 100, 1) for k, v in alloc.items()},
        "total_eur": round(total, 0),
        "pea_misallocated_in_cto": misallocated,
        "n_pea_misallocated": len(misallocated),
    }


def compute_tax_loss_harvest_candidates(min_loss_pct: float = -5.0) -> list[dict]:
    """Liste les positions CTO en moins-value > seuil (mobilisable contre PV)."""
    from dashboard.render import _cached_price_eur, _positions

    positions = _positions()
    candidates = []
    for p in positions:
        wrapper = (p.get("wrapper") or "CTO").upper()
        if wrapper != "CTO":
            continue
        ac = p.get("avg_cost", 0) or 0
        w = p.get("weight", 0) or 0
        if not ac or not w:
            continue
        qty = w / ac  # derived from cost basis
        cur = _cached_price_eur(p["ticker"]) or 0
        if not cur:
            continue
        pnl_pct = (cur - ac) / ac * 100
        if pnl_pct >= min_loss_pct:
            continue
        moins_value_eur = (cur - ac) * qty
        candidates.append({
            "ticker": p["ticker"],
            "qty": qty,
            "avg_cost": ac,
            "current_price_eur": round(cur, 2),
            "pnl_pct": round(pnl_pct, 1),
            "moins_value_eur": round(moins_value_eur, 0),
        })
    candidates.sort(key=lambda x: x["moins_value_eur"])
    return candidates


# ─────────────────────────── FX exposure ─────────────────────────────────────


_TICKER_CURRENCY = {
    ".PA": "EUR", ".AS": "EUR", ".DE": "EUR", ".MI": "EUR", ".MC": "EUR",
    ".BR": "EUR", ".VI": "EUR", ".LS": "EUR",
    ".SW": "CHF",
    ".L": "GBP",
    ".T": "JPY", ".HK": "HKD",
    ".KS": "KRW", ".KQ": "KRW",
}


def _ticker_currency(tk: str) -> str:
    for suffix, cur in _TICKER_CURRENCY.items():
        if tk.endswith(suffix):
            return cur
    return "USD"  # default for non-suffix tickers


def compute_fx_exposure() -> dict:
    """Group book weight by currency. Useful for euro book holding USD/JPY/KRW.

    Retour par devise :
      - eur (float) : exposition totale en EUR
      - pct (float) : poids en % du book
      - n_positions (int) : nb tickers dans la devise
      - tickers (list[str]) : tickers (triés desc par poids EUR)
      - holdings (list[dict]) : {tk, eur, pct_of_cur} pour accordeon UI
    """
    from dashboard.render import _positions

    positions = _positions()
    total = sum(p.get("weight", 0) for p in positions) or 1
    by_cur: dict = {}
    for p in positions:
        cur = _ticker_currency(p["ticker"])
        by_cur.setdefault(cur, {"eur": 0.0, "holdings": []})
        by_cur[cur]["eur"] += p["weight"]
        by_cur[cur]["holdings"].append({"tk": p["ticker"], "eur": p["weight"]})
    for d in by_cur.values():
        d["pct"] = round(d["eur"] / total * 100, 1)
        d["holdings"].sort(key=lambda h: -h["eur"])
        for h in d["holdings"]:
            h["pct_of_cur"] = round(h["eur"] / d["eur"] * 100, 1) if d["eur"] else 0.0
            h["eur"] = round(h["eur"], 0)
        d["tickers"] = [h["tk"] for h in d["holdings"]]
        d["eur"] = round(d["eur"], 0)
        d["n_positions"] = len(d["holdings"])
    return dict(sorted(by_cur.items(), key=lambda kv: -kv[1]["pct"]))
