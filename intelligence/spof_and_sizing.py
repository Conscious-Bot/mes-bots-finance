"""Sprint 14 — SPOF graph upstream + Mauboussin implied sizing.

Branche ticker_meta (Sprint 14 classifier) sur les positions reelles pour
produire deux signaux deterministes :

1. SPOF — aggregate upstream nodes que >1 position partage. Concretise la
   critique "ta vraie concentration est en amont (TSMC fab pour AMD, AVGO,
   ALAB ; ASML pour EUV...)".

2. Mauboussin sizing — implied weight derivee du fade_rate, vs weight reel.
   Le sizing_conviction Sprint 5 etait un nombre magique (90%). Ici le
   target weight est rigoureux : weight derivee de (conviction, fade_rate).
"""

from __future__ import annotations

import json
import logging

from shared import storage

log = logging.getLogger(__name__)


# ─────────────────────────── SPOF graph ──────────────────────────────────────


def compute_spof_graph() -> dict:
    """For each upstream node mentioned by any position, sum the book weight
    that depends on it (weighted by share_of_revenue_or_capacity).

    Returns {node: {total_exposure_eur, pct_of_book, dependents: [...]}}
    sorted by pct_of_book desc.
    """
    from shared.portfolio_view_builder import _positions  # cure #120 étape 3 — couche shared/, plus de dashboard/
    from shared.position_view import get_all_positions_views

    # Cure #120 étape 5 single-source : on tire le seam UNE FOIS au call-site,
    # builder reçoit views explicite. Fallback intérieur supprimé pour empêcher
    # le drift double-source silencieux entre callers.
    positions = _positions(views=get_all_positions_views())
    if not positions:
        return {}
    total = sum(p.get("weight", 0) for p in positions) or 1
    meta = {m["ticker"]: m for m in storage.get_all_latest_ticker_meta()}

    nodes: dict = {}
    for p in positions:
        tk = p["ticker"]
        m = meta.get(tk)
        if not m:
            continue
        try:
            deps = json.loads(m.get("upstream_critical_deps_json") or "[]")
        except Exception:
            deps = []
        for dep in deps:
            if not isinstance(dep, dict):
                continue
            node = dep.get("node")
            share = float(dep.get("share_of_revenue_or_capacity") or 0)
            if not node or share <= 0:
                continue
            exposure_eur = p["weight"] * share
            nodes.setdefault(node, {"total_exposure_eur": 0.0, "dependents": []})
            nodes[node]["total_exposure_eur"] += exposure_eur
            nodes[node]["dependents"].append({
                "ticker": tk,
                "share": share,
                "exposure_eur": round(exposure_eur, 0),
            })
    # finalize : pct + sort
    for d in nodes.values():
        d["pct_of_book"] = round(d["total_exposure_eur"] / total * 100, 1)
        d["total_exposure_eur"] = round(d["total_exposure_eur"], 0)
        d["n_dependents"] = len(d["dependents"])
        d["dependents"].sort(key=lambda x: -x["exposure_eur"])
    return dict(sorted(nodes.items(), key=lambda kv: -kv[1]["pct_of_book"]))


# ─────────────────────────── Mauboussin implied sizing ───────────────────────


# Cap par conviction (sync avec config.yaml ; mirrored ici)
_BASE_CAP_BY_CONVICTION = {5: 8.0, 4: 6.0, 3: 4.5, 2: 3.0, 1: 2.0}


def _fade_factor(fade_rate_score: int | None) -> float:
    """Convert fade_rate_score (0=annuity, 100=immediate revert) into a
    multiplier on the base cap. Low fade -> 1.0 (use full cap). High fade
    -> 0.5 (halve the cap).
    """
    if fade_rate_score is None:
        return 1.0  # neutral if unknown
    # Linear : 0 -> 1.0, 50 -> 0.75, 100 -> 0.5
    f = 1.0 - (fade_rate_score / 100.0) * 0.5
    return max(0.5, min(1.0, f))


def compute_mauboussin_sizing() -> dict:
    """For each held position with conviction+fade_rate available, compute :
      - target_weight_pct = base_cap * fade_factor(fade_rate)
      - gap_pp = actual - target (positive = oversize vs implied, negative = undersize)

    Returns {ticker: {conviction, fade_rate, base_cap, target_pct, actual_pct, gap_pp, status}}.
    """
    from shared.portfolio_view_builder import _positions  # cure #120 étape 3 — couche shared/, plus de dashboard/
    from shared.position_view import get_all_positions_views

    # Cure #120 étape 5 single-source : on tire le seam UNE FOIS au call-site,
    # builder reçoit views explicite. Fallback intérieur supprimé pour empêcher
    # le drift double-source silencieux entre callers.
    positions = _positions(views=get_all_positions_views())
    total = sum(p.get("weight", 0) for p in positions) or 1
    meta = {m["ticker"]: m for m in storage.get_all_latest_ticker_meta()}

    # Conviction lookup
    with storage.db() as cx:
        thr = cx.execute(
            "SELECT ticker, conviction FROM theses WHERE status='active'"
        ).fetchall()
    convict_map = dict(thr)

    out: dict = {}
    for p in positions:
        tk = p["ticker"]
        conv = convict_map.get(tk)
        m = meta.get(tk)
        if conv is None or not m:
            continue
        fade = m.get("fade_rate_score")
        base_cap = _BASE_CAP_BY_CONVICTION.get(int(conv), 3.0)
        target_pct = base_cap * _fade_factor(fade)
        actual_pct = p["weight"] / total * 100
        gap_pp = actual_pct - target_pct
        status = (
            "above_implied" if gap_pp > 0.5
            else "below_implied" if gap_pp < -0.5
            else "at_implied"
        )
        out[tk] = {
            "conviction": conv,
            "fade_rate_score": fade,
            "base_cap_pct": round(base_cap, 1),
            "fade_factor": round(_fade_factor(fade), 2),
            "target_pct": round(target_pct, 1),
            "actual_pct": round(actual_pct, 1),
            "gap_pp": round(gap_pp, 1),
            "status": status,
        }
    return dict(sorted(out.items(), key=lambda kv: kv[1]["gap_pp"], reverse=True))


def list_above_bull_case() -> list[dict]:
    """Critique : 'flag quand expectations depassent meme le bull case (AMD ~92x)'."""
    meta = storage.get_all_latest_ticker_meta()
    out = []
    for m in meta:
        if m.get("valo_above_bull_case"):
            out.append({
                "ticker": m["ticker"],
                "what_priced_in": (m.get("valo_what_priced_in") or "")[:300],
                "pe_or_proxy": m.get("valo_pe_or_proxy"),
                "rationale": (m.get("rationale") or "")[:200],
            })
    return out
