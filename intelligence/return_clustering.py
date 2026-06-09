"""Sprint 17 — Data-defined clusters par correlation rendements reels.

Per la critique : "Laisser les donnees definir les clusters. Plutot que des
etiquettes de theme posees a la main (qui ont mal classe Safran et AMD),
clusteriser par correlation de rendements reels. Ca aurait montre qu'ASML/
TSMC/Synopsys bougent ensemble quel que soit leur label 'edge', et donne
une mesure de decorrelation objective."

Approche :
  1. Fetch 120 derniers jours de prix daily via yfinance (batch)
  2. Compute log-returns -> correlation matrix
  3. Identifier high-corr pairs (>0.7) — les vraies redondances mesurees
  4. Identifier clusters par seuil de correlation (hierarchical scipy)
  5. Comparer aux macro_factor declarations (Sprint 12) -> hidden concentration

Output : dashboard panel des paires correlees + warnings quand
macro_factor declarations divergent de la realite des correlations.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from shared import storage

log = logging.getLogger(__name__)


def fetch_price_history(tickers: list[str], days: int = 120) -> pd.DataFrame:
    """Fetch daily Close prices for tickers via shared.prices gateway.

    SOCLE S1c (#111) : migré de yf.download() direct vers
    prices.ensure_price_history() + read price_history table. Le gateway
    canonique gère le throttle anti-ban yfinance + cache DB partagé.
    """
    from datetime import UTC, datetime, timedelta
    from shared.prices import ensure_price_history

    if not tickers:
        return pd.DataFrame()
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    closes: dict = {}
    for tk in tickers:
        try:
            df = ensure_price_history(tk, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            if df is not None and not df.empty:
                # ensure_price_history retourne DataFrame avec colonnes incluant price_native
                if "price_native" in df.columns:
                    closes[tk] = df.set_index("asof")["price_native"] if "asof" in df.columns else df["price_native"]
                elif "Close" in df.columns:
                    closes[tk] = df["Close"]
        except Exception as e:
            log.warning(f"price fetch {tk} failed via gateway: {e}")
    if not closes:
        return pd.DataFrame()
    return pd.DataFrame(closes).dropna(how="all")


def compute_correlation(prices: pd.DataFrame, min_observations: int = 30) -> pd.DataFrame:
    """Log-returns -> Pearson correlation. NaN if not enough observations."""
    if prices.empty:
        return pd.DataFrame()
    log_ret = np.log(prices / prices.shift(1)).dropna(how="all")
    valid = log_ret.dropna(axis=1, thresh=min_observations)
    return valid.corr(method="pearson")


def find_high_corr_pairs(corr: pd.DataFrame, threshold: float = 0.7) -> list[dict]:
    """Identify ticker pairs with correlation >= threshold (excluding diagonal)."""
    if corr.empty:
        return []
    pairs = []
    tks = list(corr.columns)
    for i, a in enumerate(tks):
        for b in tks[i + 1:]:
            r = corr.at[a, b]
            if pd.isna(r):
                continue
            if r >= threshold:
                pairs.append({
                    "ticker_a": a,
                    "ticker_b": b,
                    "correlation": round(float(r), 2),
                })
    pairs.sort(key=lambda p: -p["correlation"])
    return pairs


def cluster_by_correlation(corr: pd.DataFrame, distance_threshold: float = 0.4) -> dict:
    """Hierarchical clustering. distance = 1 - correlation. Returns {ticker: cluster_id}."""
    if corr.empty or corr.shape[0] < 2:
        return {}
    tks = list(corr.columns)
    dist_matrix = 1 - corr.values
    # Ensure symmetry + zero diagonal
    np.fill_diagonal(dist_matrix, 0)
    # squareform requires the matrix to be symmetric
    try:
        condensed = squareform(dist_matrix, checks=False)
        Z = linkage(condensed, method="average")
        labels = fcluster(Z, t=distance_threshold, criterion="distance")
    except Exception as e:
        log.warning(f"clustering failed: {e}")
        return {}
    return dict(zip(tks, [int(x) for x in labels], strict=False))


def compare_with_macro_factor(clusters: dict, axes_map: dict) -> list[dict]:
    """For each data-defined cluster, list macro_factor declarations of members.

    Reveals hidden concentration : if data-cluster groups tickers from DIFFERENT
    macro_factors -> the macro_factor declarations may be wrong OR there's
    correlation despite different drivers (common factor exposure).
    """
    by_cluster: dict = {}
    for tk, cid in clusters.items():
        a = axes_map.get(tk) or {}
        by_cluster.setdefault(cid, []).append({
            "ticker": tk,
            "macro_factor": a.get("macro_factor", "Unclassified"),
        })
    out = []
    for cid, members in by_cluster.items():
        if len(members) < 2:
            continue
        factors = {m["macro_factor"] for m in members}
        out.append({
            "cluster_id": cid,
            "n_members": len(members),
            "members": members,
            "unique_factors": sorted(factors),
            "n_unique_factors": len(factors),
            "mixed": len(factors) > 1,  # hidden concentration if mixed
        })
    out.sort(key=lambda c: -c["n_members"])
    return out


def run_analysis(days: int = 120, corr_threshold: float = 0.7, cluster_distance: float = 0.4) -> dict:
    """End-to-end : fetch + correlate + cluster + compare to macro_factor declarations."""
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT DISTINCT ticker FROM positions WHERE qty > 0 AND status='open'"
        ).fetchall()
    tickers = [r[0] for r in rows]
    if not tickers:
        return {"error": "no_positions"}

    prices = fetch_price_history(tickers, days=days)
    if prices.empty:
        return {"error": "no_prices_fetched", "tickers_attempted": len(tickers)}

    corr = compute_correlation(prices)
    pairs = find_high_corr_pairs(corr, threshold=corr_threshold)
    clusters = cluster_by_correlation(corr, distance_threshold=cluster_distance)
    axes_map = {a["ticker"]: a for a in storage.get_all_latest_ticker_axes()}
    cluster_analysis = compare_with_macro_factor(clusters, axes_map)

    return {
        "days": days,
        "n_tickers_attempted": len(tickers),
        "n_tickers_with_data": len(corr.columns) if not corr.empty else 0,
        "corr_threshold": corr_threshold,
        "high_corr_pairs": pairs,
        "n_pairs": len(pairs),
        "clusters": cluster_analysis,
        "n_clusters": len(cluster_analysis),
        "n_mixed_clusters": sum(1 for c in cluster_analysis if c["mixed"]),
    }
