"""Sprint 13 — Factor exposures + stress tests + trajectory.

Per la critique : "Un vrai modele de risque, pas juste un bucket. Le 'cluster
cap' est une version naive. La version rigoureuse : decomposer le book en
facteurs reels — capex-IA, cycle memoire, EUR/USD, dépense défense, terres
rares/Chine — et montrer les expositions par facteur. Puis des stress tests :
capex-IA −30%, retournement du cycle memoire, EUR/USD +10%, restriction
chinoise sur les terres rares → drawdown estime."

Source : ticker_axes.macro_factor (Sprint 12). Pas d'opinion, juste sommer
les poids par facteur + appliquer des scenarios deterministes.

Trajectoire (1a) : on a deja portfolio_grades snapshots. Ce module ajoute :
  - format_grade_trajectory(n_days) -> grade + drift par dim
  - compute_price_vs_trade_drift() -> distingue derive prix vs derive trade
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from shared import storage

log = logging.getLogger(__name__)


# ─────────────────────────── Factor exposures ────────────────────────────────


# F1 add 29/05 — Les 3 facteurs IA bougent ensemble en stress (cf scenario
# "AI capex -30%" qui spillover Memory cycle -18% + AI inference -25%). Decouper
# en 3 paris minimise pile le risque cluster. On expose un AGREGAT composite
# qui dit la verite "77% en pari IA elargi" en plus des 3 sous-buckets.
_AI_BROAD_FACTORS = {"AI capex", "Memory cycle", "AI inference/compute demand"}


def compute_factor_exposures() -> dict:
    """Sum book market value per macro_factor.

    MIGRATED 29/05 round 2 vers shared.book : on lit directement les
    BookLine canoniques (qui ont deja le macro_factor JOINT). Plus de
    lookup separe ticker_axes. Effet : F9 visible -- on peut afficher
    le theme (taxonomie thesis user) a cote de chaque ticker pour rendre
    explicite la double classification (theme vs macro_factor).

    Returns {factor: {eur, pct_of_book, tickers: [...], themes_overlay: {tk: theme}, n_positions}}.
    Composite "AI broad (capex + memory + inference)" ajoute en plus.
    """
    from shared import book

    held = book.get_held_lines()
    if not held:
        return {}

    # Cure 16/06 Lane 2 #5 : migration ln.weight_market_eur -> book.value_eur.
    # Coherent avec over_cap_monitor (Lane 2 #3, deja migre) + group_cap_monitor
    # (Lane 2 #4, migre cette session). Fallback ln.weight_market_eur si Datum
    # fail-closed. Log degraded count pour visibilite.
    _value_map: dict[str, float] = {}
    _degraded = 0
    for ln in held:
        qty = float(ln.qty or 0)
        if qty <= 0:
            _value_map[ln.ticker] = 0.0
            continue
        v = book.value_eur(ln.ticker, qty)
        if v is not None and v.value is not None and hasattr(v.value, "amount"):
            _value_map[ln.ticker] = float(v.value.amount)
            if getattr(v, "degraded", False):
                _degraded += 1
        else:
            _value_map[ln.ticker] = float(ln.weight_market_eur or 0)
    if _degraded > 0:
        import logging as _lg
        _lg.getLogger(__name__).warning(
            "compute_factor_exposures: %d/%d positions value_eur DEGRADED",
            _degraded, len(_value_map),
        )

    total = sum(_value_map.values()) or 1

    factors: dict = {}
    for ln in held:
        f = ln.macro_factor or "Unclassified"
        factors.setdefault(f, {
            "eur": 0.0,
            "tickers": [],
            "themes_overlay": {},  # F9 fix : visible cross-class
            "n_positions": 0,
        })
        factors[f]["eur"] += _value_map.get(ln.ticker, 0.0)
        factors[f]["tickers"].append(ln.ticker)
        if ln.theme:
            factors[f]["themes_overlay"][ln.ticker] = ln.theme
        factors[f]["n_positions"] += 1
    # Composite AI broad
    ai_eur = 0.0
    ai_tickers: list = []
    for k in _AI_BROAD_FACTORS:
        d = factors.get(k)
        if d:
            ai_eur += d["eur"]
            ai_tickers.extend(d["tickers"])
    if ai_tickers:
        factors["AI broad (capex + memory + inference)"] = {
            "eur": ai_eur,
            "tickers": ai_tickers,
            "n_positions": len(ai_tickers),
            "is_composite": True,
            "composes": sorted(_AI_BROAD_FACTORS),
        }
    for d in factors.values():
        d["pct_of_book"] = round(d["eur"] / total * 100, 1)
        d["eur"] = round(d["eur"], 0)
    return factors


# ─────────────────────────── Stress tests ────────────────────────────────────


_STRESS_SCENARIOS = {
    "AI capex -30%": {
        "AI capex": -30.0,
        "AI inference/compute demand": -25.0,
        "Memory cycle": -18.0,  # spillover
    },
    "Memory cycle reversal -40%": {
        "Memory cycle": -40.0,
        "AI capex": -8.0,  # mild spillover
    },
    "Defense rearmament freeze -15%": {
        "Defense rearmament": -15.0,
    },
    "China rare earth restriction +20% upside": {
        "Rare earths / materials": 20.0,
    },
    "EUR/USD +10% (negative for unhedged USD exposure)": {
        # All USD-denominated tickers take a -10% (proxy : applies to all
        # non-european tickers held in euros, treated as a global haircut
        # since we don't track currency per position)
        "_FX_USD_PENALTY": -10.0,
    },
    # F2 add 29/05 — 23% du book en JPY (Shin-Etsu, MHI, Advantest, Lasertec)
    # n'avait aucun scenario FX. BoJ intervention zone = USDJPY > 160 => yen rally
    # = haircut sur les .T en EUR. Symetrique au scenario USD.
    "JPY +10% (yen rally squeeze JP tickers)": {
        "_FX_JPY_PENALTY": -10.0,
    },
    "Energy crisis +25%": {
        "Energy commodities": 25.0,
    },
    "Rates spike +200bps": {
        "Rates / financials": 12.0,
        "AI capex": -10.0,
        "Healthcare innovation": -15.0,
        "Consumer cyclical": -12.0,
    },
}


def _is_usd_ticker(tk: str) -> bool:
    """Crude proxy : EU tickers end with .AS .PA .DE .L .MI ; JP with .T ; KR with .KS."""
    if tk.endswith((".AS", ".PA", ".DE", ".L", ".MI", ".SW")):
        return False
    # Asian markets (.T .HK .KS) ; otherwise default US
    return not tk.endswith((".T", ".HK", ".KS"))


def _is_jpy_ticker(tk: str) -> bool:
    """Tickers cotes en JPY (.T = Tokyo Stock Exchange)."""
    return tk.endswith(".T")


def run_stress_test(scenario_name: str) -> dict:
    """Apply one scenario : sum impact per position weighted by macro_factor exposure.

    Returns {scenario, total_drawdown_pct, total_drawdown_eur, by_position: [...]}.
    """
    # Migration Lane 2 #8 : shared.book direct.
    from shared import book as _bk

    held = list(_bk.get_held_lines())
    if not held:
        return {"scenario": scenario_name, "error": "empty_book"}
    scenario = _STRESS_SCENARIOS.get(scenario_name)
    if not scenario:
        return {"scenario": scenario_name, "error": "unknown_scenario"}
    axes = {a["ticker"]: a for a in storage.get_all_latest_ticker_axes()}
    # Weight depuis seam canonique book.value_eur
    weights = {}
    _degraded_count = 0
    for ln in held:
        qty = float(ln.qty or 0)
        if qty <= 0:
            continue
        v = _bk.value_eur(ln.ticker, qty)
        if v is not None and v.value is not None and hasattr(v.value, "amount"):
            weights[ln.ticker] = float(v.value.amount)
            # Cure 16/06 audit P0 Cat-D : log degraded inputs pour stress scenarios.
            # Scenario sur input stale -> resultat utile mais a flagger downstream.
            if getattr(v, "degraded", False):
                _degraded_count += 1
        else:
            weights[ln.ticker] = ln.weight_market_eur or 0
    if _degraded_count > 0:
        import logging as _lg
        _lg.getLogger(__name__).warning(
            "factor_exposures.run_stress: %d/%d positions value_eur DEGRADED -- scenario %s sur inputs stales",
            _degraded_count, len(weights), scenario_name,
        )
    total = sum(weights.values()) or 1

    by_position: list = []
    total_impact_eur = 0.0
    for tk, w in weights.items():
        a = axes.get(tk)
        impact_pct = 0.0
        # Macro factor impact
        if a:
            mf = a["macro_factor"]
            if mf in scenario:
                impact_pct += scenario[mf]
        # FX overlay for USD scenarios
        if "_FX_USD_PENALTY" in scenario and _is_usd_ticker(tk):
            impact_pct += scenario["_FX_USD_PENALTY"]
        # FX overlay for JPY scenarios (29/05 add)
        if "_FX_JPY_PENALTY" in scenario and _is_jpy_ticker(tk):
            impact_pct += scenario["_FX_JPY_PENALTY"]
        impact_eur = w * impact_pct / 100
        total_impact_eur += impact_eur
        if abs(impact_pct) > 0.5:
            by_position.append({
                "ticker": tk,
                "weight_eur": round(w, 0),
                "impact_pct": round(impact_pct, 1),
                "impact_eur": round(impact_eur, 0),
            })
    by_position.sort(key=lambda x: x["impact_eur"])
    total_drawdown_pct = total_impact_eur / total * 100
    return {
        "scenario": scenario_name,
        "total_drawdown_pct": round(total_drawdown_pct, 1),
        "total_drawdown_eur": round(total_impact_eur, 0),
        "by_position": by_position[:10],  # top 10 most impacted
        "n_positions_affected": len(by_position),
    }


def run_all_stress_tests() -> list[dict]:
    return [run_stress_test(name) for name in _STRESS_SCENARIOS]


# ─────────────────────────── Trajectory + drift ──────────────────────────────


def format_grade_trajectory(n_days: int = 30) -> dict:
    """Get all grade snapshots within window + compute drift on each dim."""
    since = (datetime.now(UTC) - timedelta(days=n_days)).date().isoformat()
    try:
        with storage.db() as cx:
            storage._ensure_grade_table(cx)
            rows = cx.execute(
                "SELECT id, snapshot_date, overall_score, overall_grade, dimensions_json "
                "FROM portfolio_grades WHERE snapshot_date >= ? "
                "ORDER BY snapshot_date ASC",
                (since,),
            ).fetchall()
    except Exception as e:
        log.warning(f"format_grade_trajectory failed: {e}")
        return {}
    snaps = []
    for r in rows:
        try:
            dims = json.loads(r[4] or "{}")
        except Exception:
            dims = {}
        snaps.append({
            "id": r[0],
            "date": r[1],
            "score": r[2],
            "grade": r[3],
            "dims": dims,
        })
    drift: dict = {}
    if len(snaps) >= 2:
        first = snaps[0]
        last = snaps[-1]
        drift["score"] = {
            "first": first["score"],
            "last": last["score"],
            "delta": last["score"] - first["score"],
            "first_date": first["date"],
            "last_date": last["date"],
        }
        for dk in (last["dims"].keys() if last["dims"] else []):
            f_val = (first["dims"].get(dk) or {}).get("current_pct", 0)
            l_val = (last["dims"].get(dk) or {}).get("current_pct", 0)
            drift[dk] = {
                "first": round(f_val, 1),
                "last": round(l_val, 1),
                "delta": round(l_val - f_val, 1),
            }
    return {"snapshots": snaps, "drift": drift}


def compute_price_vs_trade_drift(n_days: int = 30) -> dict:
    """Decompose cluster_cap drift into : price-driven vs trade-driven.

    Cluster-cap may breach simply because TSMC rallied. Trade-driven drift
    requires a position_event in the window.
    """
    since = (datetime.now(UTC) - timedelta(days=n_days)).isoformat()
    try:
        with storage.db() as cx:
            ev_rows = cx.execute(
                "SELECT ticker, event_type, qty_delta, price "
                "FROM position_events WHERE created_at >= ? "
                "ORDER BY created_at ASC",
                (since,),
            ).fetchall()
    except Exception:
        ev_rows = []
    trades_by_tk: dict = {}
    for tk, etype, qd, px in ev_rows:
        trades_by_tk.setdefault(tk, []).append({
            "type": etype, "qty_delta": qd, "price": px,
        })
    # Sum trade-driven delta : qty_delta * (current_price - trade_price)
    # Migration Lane 2 #8 : shared direct.
    from shared import book as _bk
    from shared.prices import get_current_price_in_eur

    total_drift_eur = 0.0
    price_drift_eur = 0.0
    trade_drift_eur = 0.0
    for ln in _bk.get_held_lines():
        tk = ln.ticker
        qty = float(ln.qty or 0)
        if qty <= 0:
            continue
        cur = get_current_price_in_eur(tk) or 0
        if not cur:
            continue
        # cost basis = qty * avg_cost_eur (canonique)
        cost_basis = qty * float(ln.avg_cost_eur or 0)
        current_value = qty * cur
        total_drift = current_value - cost_basis
        # Trade-driven : qty added in window * (current - avg_buy_in_window)
        ev = trades_by_tk.get(tk) or []
        if ev:
            for x in ev:
                qd = x.get("qty_delta") or 0
                px = x.get("price") or 0
                if qd > 0:
                    trade_drift_eur += qd * (cur - px)
        # Rest is price drift
        position_price_drift = total_drift - (sum((x.get("qty_delta") or 0) * (cur - (x.get("price") or 0))
                                              for x in ev if (x.get("qty_delta") or 0) > 0))
        price_drift_eur += position_price_drift
        total_drift_eur += total_drift
    return {
        "n_days": n_days,
        "total_drift_eur": round(total_drift_eur, 0),
        "price_drift_eur": round(price_drift_eur, 0),
        "trade_drift_eur": round(trade_drift_eur, 0),
        "n_positions_with_trades": sum(1 for v in trades_by_tk.values() if v),
    }
