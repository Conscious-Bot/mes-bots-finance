"""Tetlock 'what's priced in' instrument.

Tier 3 #10 wiring (26/06/2026), central des 2 red-teams :

> « Tetlock dit que la première question à poser sur n'importe quelle thèse =
>   "qu'est-ce qui est déjà dans le prix ?". PRESAGE n'a aucun mécanisme pour ça.
>   SK Hynix +89% sur cost, consensus mean +3.7%, forward PE 6.74 → tu as
>   raison ET le marché aussi → où est l'edge ? »

Pour chaque position tenue, compare :
- cur vs analyst consensus target_mean → upside attendu (consensus)
- cur vs target_high → upside maximum (le plus optimiste)
- cur vs target_low → downside potentiel (le plus pessimiste)
- recommendation_mean (1=Strong Buy, 5=Strong Sell) → consensus crowded-ness

Classification per ticker :
- priced_for_perfection : cur >= target_high (analyst le + optimiste battu)
  → ZÉRO upside dans le consensus, pari sur révision haussière collective
- at_consensus : cur entre 95% et 105% de target_mean
  → totalement priced, edge dépend d'execution > consensus
- asymmetric : cur < 95% de target_mean
  → upside dans le consensus, edge classique
- crowded_buy : recommendation_mean < 1.5 (everyone strong buy)
  → consensus saturé, alpha = écart vs consensus

Surface :
- aggregate counts par catégorie
- top 3 priced_for_perfection (les plus à risque de mean-reversion)
- top 3 asymmetric (les meilleurs setups si thèse tient)

Data source : shared.prices.get_analyst_consensus (yfinance, cached).
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def _classify(cur: float, consensus: dict) -> dict[str, Any]:
    """Classification per ticker — un dict avec statut + metrics.

    Returns :
        {
            'category': 'priced_for_perfection' | 'at_consensus' | 'asymmetric' | 'crowded_buy' | 'unrated',
            'upside_to_mean_pct': float | None,
            'upside_to_high_pct': float | None,
            'downside_to_low_pct': float | None,
            'recommendation_mean': float | None,
        }
    """
    tm = consensus.get("target_mean")
    th = consensus.get("target_high")
    tl = consensus.get("target_low")
    rm = consensus.get("recommendation_mean")

    out = {
        "category": "unrated",
        "upside_to_mean_pct": None,
        "upside_to_high_pct": None,
        "downside_to_low_pct": None,
        "recommendation_mean": rm,
        "n_analysts": consensus.get("n_analysts"),
        "currency": consensus.get("currency"),
        "target_mean": tm,
        "target_high": th,
        "target_low": tl,
        "cur": cur,
    }

    if not tm or tm <= 0 or cur <= 0:
        return out

    upside_mean = (tm - cur) / cur * 100
    out["upside_to_mean_pct"] = upside_mean
    if th and th > 0:
        out["upside_to_high_pct"] = (th - cur) / cur * 100
    if tl and tl > 0:
        out["downside_to_low_pct"] = (tl - cur) / cur * 100

    # Classification primaire sur upside_mean
    if th and th > 0 and cur >= th:
        out["category"] = "priced_for_perfection"
    elif -5 <= upside_mean <= 5:
        out["category"] = "at_consensus"
    elif upside_mean > 5:
        out["category"] = "asymmetric"
    else:  # upside_mean < -5 = cur > consensus mean significantly
        out["category"] = "above_consensus"  # entre at_consensus et priced_for_perfection

    # Tag crowded_buy si recommendation_mean très bas (consensus saturé)
    # NB : c'est un AND avec la catégorie principale
    out["crowded_buy"] = rm is not None and rm < 1.5
    return out


def compute_priced_in() -> dict[str, Any]:
    """Compute Tetlock 'what's priced in' aggregate pour TOUTES les positions tenues.

    Returns :
        {
            'ok': bool,
            'n_total': int,
            'n_rated': int,                              # consensus dispo
            'n_priced_for_perfection': int,
            'n_above_consensus': int,
            'n_at_consensus': int,
            'n_asymmetric': int,
            'n_crowded_buy': int,
            'per_ticker': {ticker: classify_dict},
            'top_priced_for_perfection': list[ticker],
            'top_asymmetric': list[ticker],
            'reason': str,
        }
    """
    from shared import prices, storage

    out: dict[str, Any] = {
        "ok": False,
        "n_total": 0,
        "n_rated": 0,
        "n_priced_for_perfection": 0,
        "n_above_consensus": 0,
        "n_at_consensus": 0,
        "n_asymmetric": 0,
        "n_crowded_buy": 0,
        "per_ticker": {},
        "top_priced_for_perfection": [],
        "top_asymmetric": [],
        "reason": "",
    }

    try:
        with storage.db() as conn:
            rows = conn.execute(
                "SELECT ticker, last_price_native, last_price_currency "
                "FROM positions WHERE qty > 0 AND last_price_native > 0"
            ).fetchall()
    except Exception as e:
        out["reason"] = f"db err: {e}"
        return out

    out["n_total"] = len(rows)
    if not rows:
        out["reason"] = "no positions"
        return out

    per_ticker = {}
    rated_with_upside = []  # list of (ticker, upside_to_mean_pct, classification)

    for ticker, cur_native, _ccy in rows:
        cur = float(cur_native or 0)
        try:
            consensus = prices.get_analyst_consensus(ticker)
        except Exception as e:
            log.debug("consensus fail %s : %s", ticker, e)
            consensus = None
        if not consensus or not consensus.get("target_mean"):
            per_ticker[ticker] = {"category": "unrated", "cur": cur}
            continue
        cls = _classify(cur, consensus)
        per_ticker[ticker] = cls
        out["n_rated"] += 1
        cat = cls["category"]
        if cat == "priced_for_perfection":
            out["n_priced_for_perfection"] += 1
        elif cat == "above_consensus":
            out["n_above_consensus"] += 1
        elif cat == "at_consensus":
            out["n_at_consensus"] += 1
        elif cat == "asymmetric":
            out["n_asymmetric"] += 1
        if cls.get("crowded_buy"):
            out["n_crowded_buy"] += 1
        if cls.get("upside_to_mean_pct") is not None:
            rated_with_upside.append((ticker, cls["upside_to_mean_pct"], cls))

    out["per_ticker"] = per_ticker

    # Top 3 priced_for_perfection = ceux qui dépassent le plus target_high
    pfp = [(tk, cls) for tk, _u, cls in rated_with_upside if cls["category"] == "priced_for_perfection"]
    pfp.sort(key=lambda x: x[1].get("upside_to_high_pct") or 0)  # plus négatif = plus dépassé
    out["top_priced_for_perfection"] = [tk for tk, _ in pfp[:3]]

    # Top 3 asymmetric = ceux avec le + d'upside vers mean
    asym = [(tk, cls) for tk, _u, cls in rated_with_upside if cls["category"] == "asymmetric"]
    asym.sort(key=lambda x: -(x[1].get("upside_to_mean_pct") or 0))
    out["top_asymmetric"] = [tk for tk, _ in asym[:3]]

    out["ok"] = out["n_rated"] > 0
    out["reason"] = (
        f"{out['n_rated']}/{out['n_total']} positions rated · "
        f"perfection={out['n_priced_for_perfection']} "
        f"above={out['n_above_consensus']} at={out['n_at_consensus']} "
        f"asym={out['n_asymmetric']} crowded_buy={out['n_crowded_buy']}"
    )
    return out
