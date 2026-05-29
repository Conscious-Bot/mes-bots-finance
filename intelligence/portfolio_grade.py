"""Sprint 5 — Portfolio Quality Grade (deterministic part).

Compute a single overall_grade (A+/A/A-/B+/.../D) + 0-100 score with
breakdown across 6 dimensions, all computable from existing DB state :

  1. Quality T1+T1★      (poids 30) — c5 active recent + ★ track-record
  2. T2 redondant         (poids 20) — proxy sector-based (LLM-augmented Sprint 6)
  3. Decorrelation ★      (poids 15) — proxy lone-wolf sectors (LLM-augmented Sprint 6)
  4. Sizing conviction    (poids 15) — caps c5=8% c4=6% c3=4.5% c2=3% c1=2%
  5. Cluster cap          (poids 10) — max cluster correle <= 35%
  6. Thesis health        (poids 10) — % theses reviewed within 30d

Snapshots ecrits quotidiennement dans portfolio_grades (Sprint 5). Trend 7j
calcule par comparaison avec snapshot d'il y a 7 jours.

Quality bar : tout cite evidence (counts, n, %). Aucune affirmation sans
calcul deterministe. Pas de LLM dans cette version — c'est tout math sur
positions + theses + thesis_relative + cluster_health.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

log = logging.getLogger(__name__)


def _parse_dt_aware(s: str | None) -> datetime | None:
    """Parse a DB timestamp string into a UTC-aware datetime, tolerant to formats."""
    if not s:
        return None
    try:
        # Try ISO with timezone
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except Exception:
        pass
    try:
        # Fallback : "YYYY-MM-DD HH:MM:SS" naive → assume UTC
        return datetime.fromisoformat(s).replace(tzinfo=UTC)
    except Exception:
        return None


# Conviction caps from config (mirrored to avoid yaml import cost — keep in sync)
CONVICTION_CAPS_PCT = {5: 8.0, 4: 6.0, 3: 4.5, 2: 3.0, 1: 2.0}

# Dimension weights (sum = 100)
DIMENSION_WEIGHTS = {
    "quality_T1_plus": 25,      # was 30
    "T2_redondant": 15,         # was 20
    "decorrelation_star": 12,   # was 15
    "sizing_conviction": 13,    # was 15
    "cluster_cap": 15,          # was 10 — concentration matters more
    "thesis_health": 10,
    "cycle_valo_exposure": 10,  # Sprint 18 — nouvelle dim Fragilite reelle
}

# Letter grade bands
GRADE_BANDS = [
    (90, "A+"), (85, "A"), (80, "A-"),
    (75, "B+"), (70, "B"), (65, "B-"),
    (60, "C+"), (55, "C"), (50, "C-"),
    (0, "D"),
]


def score_to_grade(score: int) -> str:
    for threshold, letter in GRADE_BANDS:
        if score >= threshold:
            return letter
    return "D"


def _fetch_state(months_brier_window: int = 6) -> dict:
    """Read positions + theses + cluster health + prediction history."""
    from shared.storage import db

    state: dict = {}
    with db() as cx:
        # Positions with current value (qty * avg_cost is the cost basis; for live value we'd need prices)
        pos_rows = cx.execute(
            "SELECT ticker, qty, avg_cost FROM positions WHERE qty > 0 AND status='open'"
        ).fetchall()
        positions = [{"ticker": r[0], "qty": r[1] or 0, "avg_cost": r[2] or 0,
                      "weight": (r[1] or 0) * (r[2] or 0)} for r in pos_rows]
        state["positions"] = positions
        state["total_capital_eur"] = sum(p["weight"] for p in positions)
        # Theses (active only)
        thesis_rows = cx.execute(
            "SELECT id, ticker, conviction, opened_at, last_reviewed, last_revisit_at "
            "FROM theses WHERE status='active'"
        ).fetchall()
        theses = [dict(zip(["id", "ticker", "conviction", "opened_at", "last_reviewed", "last_revisit_at"], r, strict=False))
                  for r in thesis_rows]
        state["theses_active"] = theses
        # Predictions resolved (last N months) for ★ track-record by sector
        bw_start = (datetime.now(UTC) - timedelta(days=months_brier_window * 30)).isoformat()
        pred_rows = cx.execute(
            "SELECT ticker, brier_score FROM predictions "
            "WHERE resolved_at IS NOT NULL AND resolved_at >= ? AND brier_score IS NOT NULL",
            (bw_start,),
        ).fetchall()
        state["predictions_resolved"] = [{"ticker": r[0], "brier": r[1]} for r in pred_rows]
    return state


_CLUSTER_MAP_CACHE: dict[str, str] | None = None


def _ticker_sector(ticker: str) -> str | None:
    """Resolve ticker → sector via (a) cluster membership in config.yaml, (b) TICKER_SECTOR fallback."""
    global _CLUSTER_MAP_CACHE
    if _CLUSTER_MAP_CACHE is None:
        _CLUSTER_MAP_CACHE = {}
        try:
            from pathlib import Path

            import yaml

            cfg = yaml.safe_load(Path("config.yaml").read_text())
            clusters = (cfg.get("concentration") or {}).get("clusters") or {}
            for cname, members in clusters.items():
                for tk in (members or []):
                    _CLUSTER_MAP_CACHE[tk] = cname
        except Exception as e:
            log.warning(f"cluster map load failed: {e}")
    if ticker in _CLUSTER_MAP_CACHE:
        return _CLUSTER_MAP_CACHE[ticker]
    try:
        from dashboard.render import TICKER_SECTOR

        return TICKER_SECTOR.get(ticker)
    except Exception:
        return None


def _compute_quality_T1_plus(state: dict) -> dict:
    """Solidite haute = poids canonique tagge Incontournable dans
    canonical_perimeter.json. Source unique de verite = la table de reference
    user (29 lignes, taggee a la main).

    T1★ (bonus track-record) = Incontournable ET sector Brier moyen <=0.4
    avec n>=3 (la qualite "intrinseque" est confirmee par les resolutions).

    Refonte 29/05/2026 : avant, on exigeait c5 these mature >=30j + review
    <=30j, ce qui renvoyait 0% sur un book jeune (J+14) PLEIN d'Incontournables
    (ASML, TSMC, Synopsys, KLA, Advantest, BESI, Suez, Cameco, GOOGL...). Le
    bug datait de J1 : on confondait "qualite intrinseque du ticker" et
    "track-record empirique sur la these". Maintenant on separe : la solidite
    est lue dans la table user, le ★ est l'overlay Brier."""
    positions = state["positions"]
    total = state["total_capital_eur"] or 1
    solidite = _solidite_by_ticker()

    # Sector-level Brier overlay (preserve original ★ semantics)
    sector_brier: dict[str, list[float]] = {}
    for p in state["predictions_resolved"]:
        sec = _ticker_sector(p["ticker"])
        if sec:
            sector_brier.setdefault(sec, []).append(p["brier"])
    sector_star: dict[str, bool] = {}
    for sec, briers in sector_brier.items():
        if len(briers) >= 3 and (sum(briers) / len(briers)) <= 0.4:
            sector_star[sec] = True

    incontournable_eur = 0.0
    star_eur = 0.0
    inc_names: list[str] = []
    star_names: list[str] = []
    for p in positions:
        if solidite.get(p["ticker"]) != "Incontournable":
            continue
        incontournable_eur += p["weight"]
        inc_names.append(p["ticker"])
        sec = _ticker_sector(p["ticker"])
        if sec and sector_star.get(sec):
            star_eur += p["weight"]
            star_names.append(p["ticker"])

    current_pct = incontournable_eur / total * 100 if total else 0
    target_pct = 65.0
    score = min(100, current_pct / target_pct * 100) if target_pct else 0
    n_inc = len(inc_names)
    n_star = len(star_names)
    # Marker "data_insufficient" disparait : la solidite canonique est connue
    # ex-ante (taggee a la main), donc toujours calculable.
    status = "at_or_above_target" if current_pct >= target_pct else "below_target"
    return {
        "current_pct": round(current_pct, 1),
        "target_pct": target_pct,
        "score": round(score, 1),
        "weight": DIMENSION_WEIGHTS["quality_T1_plus"],
        "status": status,
        "evidence": (
            f"Incontournable n={n_inc} ({incontournable_eur:.0f}€) "
            f"dont ★ track-record n={n_star} ({star_eur:.0f}€) sur total {total:.0f}€. "
            f"Top: {', '.join(inc_names[:6])}"
        ),
        "source": "canonical_perimeter_solidite",
    }


def _load_llm_narrative_snapshot() -> dict | None:
    """DEPRECATED Sprint 19 — la critique a montre que le narrative LLM
    creait des faux flags (AMD~TSM, SAF~HO, GOOGL~AMZN, STMPA dans AI silicon).
    Source unique = ticker_axes. Cette fonction retourne None pour forcer
    le path axes-strict + interdire le retour aux faux flags.
    """
    return None


def _load_ticker_axes_map() -> dict[str, dict]:
    """Sprint 12 : load ticker -> axes map (driver/stage/moat/macro)."""
    try:
        from shared import storage

        axes = storage.get_all_latest_ticker_axes()
        return {a["ticker"]: a for a in axes}
    except Exception:
        return {}


_CANONICAL_PERIMETER_CACHE: dict | None = None


def _load_canonical_perimeter() -> dict:
    """Source unique de la solidite-tier (table de reference user).
    canonical_perimeter.json position.solidite in {Incontournable, Solide,
    Incertain, Fragile}. Cf. fix 29/05/2026 du bug Solidite haute=0%."""
    global _CANONICAL_PERIMETER_CACHE
    if _CANONICAL_PERIMETER_CACHE is not None:
        return _CANONICAL_PERIMETER_CACHE
    try:
        import json
        from pathlib import Path

        path = Path(__file__).parent.parent / "scripts" / "canonical_perimeter.json"
        with open(path) as f:
            _CANONICAL_PERIMETER_CACHE = json.load(f)
    except Exception:
        _CANONICAL_PERIMETER_CACHE = {"positions": []}
    return _CANONICAL_PERIMETER_CACHE


def _solidite_by_ticker() -> dict[str, str]:
    cp = _load_canonical_perimeter()
    return {p["ticker"]: (p.get("solidite") or "") for p in cp.get("positions", [])}


def _compute_T2_redundant(state: dict) -> dict:
    """T2 = positions redondantes au sens STRICT (driver + stage coincident).

    Sprint 12 (refactor critique) : si ticker_axes dispo, redondance ⟺
    paire (demand_driver, value_chain_stage) identique. Sinon Sprint 6 LLM
    narrative snapshot. Sinon Sprint 5 proxy sectors.
    """
    positions = state["positions"]
    pos_by_tk = {p["ticker"]: p for p in positions}
    total = state["total_capital_eur"] or 1
    # Sprint 12 — Axes-based redundancy (strict definition).
    # Fix : on matche sur (macro_factor, value_chain_stage) — macro_factor est
    # la version controlled-vocab du driver (sinon les wordings LLM
    # verbatim divergent : MU "Memory cycle HBM/DRAM AI compute" vs SK
    # Hynix "AI accelerator HBM3E ramp NVDA exclusive" ne matchent pas en
    # raw mais sont evidently same).
    axes_map = _load_ticker_axes_map()
    if axes_map and len([p for p in positions if p["ticker"] in axes_map]) >= len(positions) * 0.7:
        groups: dict[tuple, list[dict]] = {}
        for p in positions:
            a = axes_map.get(p["ticker"])
            if not a:
                continue
            key = (a["macro_factor"], a["value_chain_stage"])
            groups.setdefault(key, []).append(p)
        redundant_eur = 0.0
        details = []
        for (macro, stage), ps in groups.items():
            if len(ps) < 2:
                continue
            sorted_ps = sorted(ps, key=lambda p: -p["weight"])
            extras = sorted_ps[1:]
            for x in extras:
                redundant_eur += x["weight"]
            details.append(
                f"{macro[:18]} | {stage[:35]} → {sorted_ps[0]['ticker']} keep, "
                f"{', '.join(x['ticker'] for x in extras)} redundant"
            )
        current_pct = redundant_eur / total * 100 if total else 0
        target_pct = 20.0
        score = min(100, target_pct / max(current_pct, 0.1) * 100) if current_pct > target_pct else 100
        return {
            "current_pct": round(current_pct, 1),
            "target_pct": target_pct,
            "score": round(score, 1),
            "weight": DIMENSION_WEIGHTS["T2_redondant"],
            "status": "above_target" if current_pct > target_pct else "at_or_below_target",
            "evidence": "Axes-based (macro+stage match) : " + (" ; ".join(details[:3]) or "aucune paire stricte"),
            "source": "sprint12_axes_macro_stage",
        }
    snap = _load_llm_narrative_snapshot()
    if snap and snap.get("clusters"):
        # LLM mode
        redundant_eur = 0.0
        redundant_detail = []
        # 1. From narrative_clusters : 4th+ position in same cluster = redundant (we keep 3 anchor names)
        for cl in snap["clusters"]:
            tks = cl.get("tickers") or []
            cl_positions = sorted(
                [pos_by_tk[t] for t in tks if t in pos_by_tk],
                key=lambda p: -p["weight"],
            )
            if len(cl_positions) > 3:
                for extra in cl_positions[3:]:
                    redundant_eur += extra["weight"]
                redundant_detail.append(f"{cl.get('name', 'cluster')} (n={len(cl_positions)})")
        # 2. From explicit redundant_positions list (any redundant explicitly flagged)
        # Critique fix : integrity check — un ticker ne peut pas etre a la fois
        # edge ET redundant (cas Safran dans la review). On prefere edge.
        edge_tickers = {(e.get("ticker") or "").upper() for e in snap.get("edges", {}).get("edge_positions") or []}
        for rp in snap.get("edges", {}).get("redundant_positions") or []:
            tk = rp.get("ticker")
            if not tk or tk.upper() in edge_tickers:
                continue  # skip conflict
            p = pos_by_tk.get(tk)
            if p and not any(tk in str(d) for d in redundant_detail):
                redundant_eur += p["weight"]
                redundant_detail.append(f"{tk}~{rp.get('redundant_with', '?')}")
        current_pct = redundant_eur / total * 100 if total else 0
        target_pct = 20.0
        score = min(100, target_pct / max(current_pct, 0.1) * 100) if current_pct > target_pct else 100
        return {
            "current_pct": round(current_pct, 1),
            "target_pct": target_pct,
            "score": round(score, 1),
            "weight": DIMENSION_WEIGHTS["T2_redondant"],
            "status": "above_target" if current_pct > target_pct else "at_or_below_target",
            "evidence": "LLM narrative : " + (", ".join(redundant_detail[:4]) or "aucune redondance"),
            "source": f"llm_snapshot_{snap.get('snapshot_date', '?')}",
        }
    # Fallback Sprint 5
    sec_groups: dict[str, list[dict]] = {}
    for p in positions:
        sec = _ticker_sector(p["ticker"]) or "Other"
        sec_groups.setdefault(sec, []).append(p)
    redundant_eur = 0.0
    redundant_secs = []
    for sec, ps in sec_groups.items():
        if len(ps) > 3:
            sorted_ps = sorted(ps, key=lambda p: -p["weight"])
            for extra in sorted_ps[3:]:
                redundant_eur += extra["weight"]
            redundant_secs.append(f"{sec} (n={len(ps)})")
    current_pct = redundant_eur / total * 100 if total else 0
    target_pct = 20.0
    score = min(100, target_pct / max(current_pct, 0.1) * 100) if current_pct > target_pct else 100
    return {
        "current_pct": round(current_pct, 1),
        "target_pct": target_pct,
        "score": round(score, 1),
        "weight": DIMENSION_WEIGHTS["T2_redondant"],
        "status": "above_target" if current_pct > target_pct else "at_or_below_target",
        "evidence": f"Proxy secteurs >3 positions : {', '.join(redundant_secs) or 'aucun'}",
        "source": "sprint5_proxy_sectors",
    }


_BALLAST_MACROS_STRICT = {
    "Defense rearmament",
    "Energy commodities",
    "Rare earths / materials",
    "Industrial reshoring",
}


def _compute_decorrelation_star(state: dict) -> dict:
    """Sprint 12 refactor (29/05/2026) : DECORRELATION = ballast macro STRICT.

    Avant : 'macro_factor unique parmi c>=4' -> flattait TSLA (Consumer
    cyclical) et 000660.KS (Memory cycle = HBM = AI capex adjacent) comme
    ballast. Or Tesla est du beta tech qui tombe AVEC la tech, et HBM
    surchauffe avec le capex IA. Faux reconfort exactement sur le risque
    qui inquiete (surchauffe tech).

    Definition stricte : ballast = positions dont le macro_factor est
    REELLEMENT non-correle a la tech IA. Whitelist explicite :
      - Defense rearmament
      - Energy commodities
      - Rare earths / materials
      - Industrial reshoring (Mitsubishi 7011.T = defense + indus)

    Pas de filtre conviction : un ballast est un ballast meme en c3 (la
    protection ne demande pas une these de chokepoint).
    """
    positions = state["positions"]
    pos_by_tk = {p["ticker"]: p for p in positions}
    theses_by_ticker = {t["ticker"]: t for t in state["theses_active"]}
    total = state["total_capital_eur"] or 1
    axes_map = _load_ticker_axes_map()
    if axes_map and len([p for p in positions if p["ticker"] in axes_map]) >= len(positions) * 0.7:
        star_eur = 0.0
        names = []
        macro_count: dict[str, int] = {}
        for p in positions:
            a = axes_map.get(p["ticker"])
            if not a:
                continue
            mf = a["macro_factor"]
            macro_count[mf] = macro_count.get(mf, 0) + 1
            if mf in _BALLAST_MACROS_STRICT:
                star_eur += p["weight"]
                names.append(f"{p['ticker']}({mf[:14]})")
        current_pct = star_eur / total * 100 if total else 0
        target_pct = 15.0
        score = min(100, current_pct / target_pct * 100) if target_pct else 0
        dominant = max(macro_count.items(), key=lambda kv: kv[1]) if macro_count else ("?", 0)
        return {
            "current_pct": round(current_pct, 1),
            "target_pct": target_pct,
            "score": round(score, 1),
            "weight": DIMENSION_WEIGHTS["decorrelation_star"],
            "status": "at_or_above_target" if current_pct >= target_pct else "below_target",
            "evidence": (
                f"Ballast strict (defense/energie/terres rares/reshoring) : "
                f"{', '.join(names[:6]) or 'aucun'} ({star_eur:.0f}€). "
                f"Dominant book: {dominant[0]} (n={dominant[1]})"
            ),
            "source": "sprint12_ballast_strict_whitelist",
        }
    snap = _load_llm_narrative_snapshot()
    if snap and snap.get("edges"):
        edges = snap["edges"].get("edge_positions") or []
        star_eur = 0.0
        names = []
        for ep in edges:
            tk = ep.get("ticker")
            p = pos_by_tk.get(tk)
            t = theses_by_ticker.get(tk)
            conv = (t or {}).get("conviction") or 0
            if p and conv >= 4:  # Edge ET conviction >=4
                star_eur += p["weight"]
                names.append(tk)
        current_pct = star_eur / total * 100 if total else 0
        target_pct = 15.0
        score = min(100, current_pct / target_pct * 100) if target_pct else 0
        return {
            "current_pct": round(current_pct, 1),
            "target_pct": target_pct,
            "score": round(score, 1),
            "weight": DIMENSION_WEIGHTS["decorrelation_star"],
            "status": "at_or_above_target" if current_pct >= target_pct else "below_target",
            "evidence": f"LLM edge c>=4 : {', '.join(names[:5]) or 'aucun'} ({star_eur:.0f}€)",
            "source": f"llm_snapshot_{snap.get('snapshot_date', '?')}",
        }
    # Fallback Sprint 5
    sec_counts: dict[str, int] = {}
    for p in positions:
        sec = _ticker_sector(p["ticker"]) or "Other"
        sec_counts[sec] = sec_counts.get(sec, 0) + 1
    star_eur = 0.0
    n_star = 0
    for p in positions:
        sec = _ticker_sector(p["ticker"])
        t = theses_by_ticker.get(p["ticker"])
        conv = (t or {}).get("conviction") or 0
        if sec and sec_counts.get(sec, 0) == 1 and conv >= 4:
            star_eur += p["weight"]
            n_star += 1
    current_pct = star_eur / total * 100 if total else 0
    target_pct = 15.0
    score = min(100, current_pct / target_pct * 100) if target_pct else 0
    return {
        "current_pct": round(current_pct, 1),
        "target_pct": target_pct,
        "score": round(score, 1),
        "weight": DIMENSION_WEIGHTS["decorrelation_star"],
        "status": "at_or_above_target" if current_pct >= target_pct else "below_target",
        "evidence": f"Proxy lone-wolf c>=4 : n={n_star} ({star_eur:.0f}€)",
        "source": "sprint5_proxy_lonewolf",
    }


def _compute_sizing_conviction(state: dict) -> dict:
    """100% deterministe : chaque ligne <= cap conviction.
    Score = (capital en compliance) / total."""
    positions = state["positions"]
    theses_by_ticker = {t["ticker"]: t for t in state["theses_active"]}
    total = state["total_capital_eur"] or 1
    compliant_eur = 0.0
    violations = []
    for p in positions:
        t = theses_by_ticker.get(p["ticker"])
        conv = (t or {}).get("conviction") or 3
        cap_pct = CONVICTION_CAPS_PCT.get(conv, 3.0)
        weight_pct = p["weight"] / total * 100 if total else 0
        if weight_pct <= cap_pct + 0.2:  # tiny tolerance 0.2%
            compliant_eur += p["weight"]
        else:
            violations.append(f"{p['ticker']} c{conv} {weight_pct:.1f}% > {cap_pct:.1f}%")
    current_pct = compliant_eur / total * 100 if total else 0
    target_pct = 90.0
    score = min(100, current_pct / target_pct * 100) if target_pct else 0
    return {
        "current_pct": round(current_pct, 1),
        "target_pct": target_pct,
        "score": round(score, 1),
        "weight": DIMENSION_WEIGHTS["sizing_conviction"],
        "status": "at_or_above_target" if current_pct >= target_pct else "below_target",
        "evidence": f"{len(violations)} violations : {', '.join(violations[:3])}" if violations else "tout sous les caps",
    }


def _load_user_strategy() -> dict:
    """Sprint 19 : lit user_strategy depuis config.yaml. Permet user-driven targets."""
    try:
        from pathlib import Path

        import yaml

        cfg = yaml.safe_load(Path("config.yaml").read_text())
        return cfg.get("user_strategy") or {}
    except Exception:
        return {}


def _compute_cluster_cap(state: dict) -> dict:
    """Sprint 19 : cible cluster_cap = user_strategy.target_cluster_cap_pct
    si declaree (default 35%). Pour un concentrator_thematic, cible 75%.
    """
    user_strat = _load_user_strategy()
    target_pct = float(user_strat.get("target_cluster_cap_pct", 35))
    try:
        from dashboard.render import _cluster_health, _pnl_cost_map

        pnl = _pnl_cost_map(state["positions"])
        clusters = _cluster_health(state["positions"], pnl)
        max_pct = max((c["pct"] for c in clusters), default=0)
        max_name = next((c["name"] for c in clusters if c["pct"] == max_pct), "?")
    except Exception as e:
        log.warning(f"_compute_cluster_cap failed: {e}")
        return {
            "current_pct": 0.0,
            "target_pct": target_pct,
            "score": 100,
            "weight": DIMENSION_WEIGHTS["cluster_cap"],
            "status": "unknown",
            "evidence": "cluster_health fetch failed",
        }
    score = 100 if max_pct <= target_pct else max(0, 100 - (max_pct - target_pct) * 5)
    archetype = user_strat.get("archetype", "default")
    suffix = f" (cible {target_pct:.0f}% car archetype={archetype})" if archetype != "default" else ""
    return {
        "current_pct": round(max_pct, 1),
        "target_pct": target_pct,
        "score": round(score, 1),
        "weight": DIMENSION_WEIGHTS["cluster_cap"],
        "status": "at_or_below_target" if max_pct <= target_pct else "above_target",
        "evidence": f"Plus gros cluster : {max_name} a {max_pct:.1f}%{suffix}",
        "source": "sprint19_user_strategy" if user_strat else "default",
    }


def _compute_cycle_valo_exposure(state: dict) -> dict:
    """Sprint 18 — Vraie Fragilite forward (per critique #2).

    Sante fondamentaux est une chose, exposition cycle/valo en est une autre.
    Un nom peut etre 'sain' (marges OK, no debt) ET 'au pic de cycle'
    (Micron/SK Hynix 72-74% margins = peak) OU 'valo > bull case' (AMD 92x).
    Source : ticker_meta.fade_rate_score (cycle position) + valo_above_bull_case.

    fragile_eur = sum positions ou (fade >= 60 OR valo_above_bull_case).
    Target: <=20% du book.
    """
    from shared import storage

    positions = state["positions"]
    total = state["total_capital_eur"] or 1
    meta = {m["ticker"]: m for m in storage.get_all_latest_ticker_meta()}
    fragile_eur = 0.0
    flagged = []
    for p in positions:
        m = meta.get(p["ticker"])
        if not m:
            continue
        fade = m.get("fade_rate_score") or 0
        valo_tight = m.get("valo_above_bull_case") or False
        if fade >= 60 or valo_tight:
            fragile_eur += p["weight"]
            tag = "fade" if fade >= 60 else ""
            if valo_tight:
                tag = (tag + "+valo>bull") if tag else "valo>bull"
            flagged.append(f"{p['ticker']}({tag})")
    current_pct = fragile_eur / total * 100 if total else 0
    target_pct = 20.0
    # inverse score : moins = mieux
    score = min(100, target_pct / max(current_pct, 0.1) * 100) if current_pct > target_pct else 100
    return {
        "current_pct": round(current_pct, 1),
        "target_pct": target_pct,
        "score": round(score, 1),
        "weight": 20,  # poids dans Fragilite (avec sante 30%)
        "status": "above_target" if current_pct > target_pct else "at_or_below_target",
        "evidence": f"Cycle/valo expose : {', '.join(flagged[:6]) or 'aucun'}",
        "source": "sprint18_ticker_meta",
    }


def _compute_thesis_health(state: dict) -> dict:
    """Sante = fondamentaux verifies, pas juste 'reviewee recemment'.

    Per critique #3 review : 'STM et Lasertec ont des fondamentaux faibles/en
    erosion — ils devraient etre « sous surveillance », pas « sains ».'

    Nouvelle definition Sprint 19 : une these est "saine" si :
      - reviewee dans les 30j (current)
      - ET aucun signal d'erosion fondamentaux (fade<70 si ticker_meta dispo)
      - ET pas flag valo > bull case

    Retourne % "sain". "Sous surveillance" = (fade>=70 OR valo>bull) regardless review.
    """
    from shared import storage

    theses = state["theses_active"]
    if not theses:
        return {
            "current_pct": 0,
            "target_pct": 80,
            "score": 0,
            "weight": DIMENSION_WEIGHTS["thesis_health"],
            "status": "no_data",
            "evidence": "aucune these active",
        }
    meta = {m["ticker"]: m for m in storage.get_all_latest_ticker_meta()}
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    n_sain = 0
    sous_surveillance: list[str] = []
    for t in theses:
        last_rev = t.get("last_reviewed") or t.get("last_revisit_at") or t.get("opened_at") or ""
        last_rev_dt = _parse_dt_aware(last_rev)
        reviewed_recent = last_rev_dt and last_rev_dt >= cutoff
        m = meta.get(t["ticker"])
        eroding = m and (m.get("fade_rate_score", 0) >= 70 or m.get("valo_above_bull_case", False))
        if reviewed_recent and not eroding:
            n_sain += 1
        elif eroding:
            tag = "fade" if m.get("fade_rate_score", 0) >= 70 else ""
            if m.get("valo_above_bull_case"):
                tag = (tag + "+valo>bull") if tag else "valo>bull"
            sous_surveillance.append(f"{t['ticker']}({tag})")
    current_pct = n_sain / len(theses) * 100
    target_pct = 80.0
    score = min(100, current_pct / target_pct * 100) if target_pct else 0
    surveillance_str = f" ; sous surveillance : {', '.join(sous_surveillance[:5])}" if sous_surveillance else ""
    return {
        "current_pct": round(current_pct, 1),
        "target_pct": target_pct,
        "score": round(score, 1),
        "weight": DIMENSION_WEIGHTS["thesis_health"],
        "status": "at_or_above_target" if current_pct >= target_pct else "below_target",
        "evidence": f"{n_sain}/{len(theses)} sains{surveillance_str}",
        "source": "sprint19_fundamentals_verified",
    }


def compute_grade() -> dict:
    """Compute full portfolio grade snapshot. Returns dict ready to insert."""
    state = _fetch_state()
    dims = {
        "quality_T1_plus": _compute_quality_T1_plus(state),
        "T2_redondant": _compute_T2_redundant(state),
        "decorrelation_star": _compute_decorrelation_star(state),
        "sizing_conviction": _compute_sizing_conviction(state),
        "cluster_cap": _compute_cluster_cap(state),
        "thesis_health": _compute_thesis_health(state),
        "cycle_valo_exposure": _compute_cycle_valo_exposure(state),
    }
    valid_dims = {k: d for k, d in dims.items() if d.get("status") != "data_insufficient"}
    valid_weight = sum(d["weight"] for d in valid_dims.values()) or 1
    overall = sum(d["score"] * d["weight"] / valid_weight for d in valid_dims.values())
    overall_int = round(overall)

    # Sprint 18/19 — HARD GATES, mais respect user_strategy.
    # Un concentrator_thematic (user declare la concentration delibere) doit
    # pouvoir afficher A- meme avec 70% Pari principal si c'est sa target.
    # Le gate ne kicke que si cc_current >> target user.
    gates_applied = []
    cc = dims.get("cluster_cap", {})
    cc_current = cc.get("current_pct", 0)
    cc_target = cc.get("target_pct", 35)
    if cc_current > cc_target * 2:
        cap = 65
        if overall_int > cap:
            gates_applied.append(
                f"Pari principal {cc_current:.0f}% > 2x cible {cc_target:.0f}% -> note cap a {cap}"
            )
            overall_int = cap
    elif cc_current > cc_target * 1.5:
        cap = 78
        if overall_int > cap:
            gates_applied.append(
                f"Pari principal {cc_current:.0f}% > 1.5x cible {cc_target:.0f}% -> note cap a {cap}"
            )
            overall_int = cap

    # Gate Calibrage (sizing_conviction) — plafond + plancher
    # Per le co-analyste : "on reprend les planchers Autres paris / Calibrage
    # pour finir la spec des gates". Le plafond cluster_cap > 2x cible est en
    # place, on ajoute les planchers cote dims minimum.
    sc = dims.get("sizing_conviction", {})
    sc_score = sc.get("score", 100)
    if sc_score < 50:
        cap = 60  # C+ max si Calibrage tres mauvais
        if overall_int > cap:
            gates_applied.append(f"Calibrage tres bas (score {sc_score:.0f}) -> note cap a {cap}")
            overall_int = cap
    elif sc_score < 70:
        cap = 75
        if overall_int > cap:
            gates_applied.append(f"Calibrage sous-cible (score {sc_score:.0f}) -> note cap a {cap}")
            overall_int = cap

    # Plancher Autres paris (decorrelation_star) : si <50% de la cible, le book
    # est tellement monolithique qu'aucune diversification n'amortit.
    de = dims.get("decorrelation_star", {})
    de_current = de.get("current_pct", 0)
    de_target = de.get("target_pct", 15)
    if de_current < de_target * 0.3:  # <4.5%, quasi rien de decorrele
        cap = 60
        if overall_int > cap:
            gates_applied.append(f"Autres paris quasi-nuls ({de_current:.1f}% < 0.3x cible) -> note cap a {cap}")
            overall_int = cap
    elif de_current < de_target * 0.6:  # <9%, decorrelation faible
        cap = 72
        if overall_int > cap:
            gates_applied.append(f"Autres paris faibles ({de_current:.1f}% < 0.6x cible) -> note cap a {cap}")
            overall_int = cap

    # Plancher Solidite haute : si <50% de la cible (et data disponible)
    qp = dims.get("quality_T1_plus", {})
    if qp.get("status") != "data_insufficient":
        qp_current = qp.get("current_pct", 0)
        qp_target = qp.get("target_pct", 65)
        if qp_current < qp_target * 0.4:  # <26% du book en Incontournable/Solide
            cap = 65
            if overall_int > cap:
                gates_applied.append(f"Solidite haute basse ({qp_current:.0f}% < 0.4x cible) -> note cap a {cap}")
                overall_int = cap

    # Plancher Cycle/valo : si tres expose, l'avenir est fragile peu importe la sante actuelle
    cv = dims.get("cycle_valo_exposure", {})
    cv_current = cv.get("current_pct", 0)
    cv_target = cv.get("target_pct", 20)
    if cv_current > cv_target * 2.5:  # >50% du book a fade>=60 ou valo>bull
        cap = 65
        if overall_int > cap:
            gates_applied.append(f"Cycle/valo expose extreme ({cv_current:.0f}% > 2.5x cible) -> note cap a {cap}")
            overall_int = cap

    grade = score_to_grade(overall_int)
    return {
        "snapshot_date": datetime.now(UTC).date().isoformat(),
        "overall_score": overall_int,
        "overall_grade": grade,
        "dimensions": dims,
        "total_capital_eur": state["total_capital_eur"],
        "n_positions": len(state["positions"]),
        "n_theses_active": len(state["theses_active"]),
        "n_dims_data_insufficient": sum(1 for d in dims.values() if d.get("status") == "data_insufficient"),
        "gates_applied": gates_applied,
        "computation_version": "sprint18_gates_fragility",
    }


def format_grade_for_dashboard(grade: dict) -> dict:
    """Format the grade dict into a structure ready for dashboard rendering."""
    return {
        "grade": grade.get("overall_grade", "?"),
        "score": grade.get("overall_score", 0),
        "snapshot_date": grade.get("snapshot_date", ""),
        "dimensions": grade.get("dimensions", {}),
        "total_capital_eur": grade.get("total_capital_eur", 0),
        "n_positions": grade.get("n_positions", 0),
    }


def _grade_from_state(state: dict) -> dict:
    """Reusable : same 7 dims + gates as compute_grade (utilise par simulate_grade)."""
    dims = {
        "quality_T1_plus": _compute_quality_T1_plus(state),
        "T2_redondant": _compute_T2_redundant(state),
        "decorrelation_star": _compute_decorrelation_star(state),
        "sizing_conviction": _compute_sizing_conviction(state),
        "cluster_cap": _compute_cluster_cap(state),
        "thesis_health": _compute_thesis_health(state),
        "cycle_valo_exposure": _compute_cycle_valo_exposure(state),
    }
    valid_dims = {k: d for k, d in dims.items() if d.get("status") != "data_insufficient"}
    valid_weight = sum(d["weight"] for d in valid_dims.values()) or 1
    overall = sum(d["score"] * d["weight"] / valid_weight for d in valid_dims.values())
    overall_int = round(overall)
    # Memes gates que compute_grade pour que la sim soit coherente
    cc = dims.get("cluster_cap", {})
    cc_current = cc.get("current_pct", 0)
    cc_target = cc.get("target_pct", 35)  # user_strategy honored via _compute_cluster_cap
    if cc_current > cc_target * 2:
        overall_int = min(overall_int, 65)
    elif cc_current > cc_target * 1.5:
        overall_int = min(overall_int, 78)
    sc_score = dims.get("sizing_conviction", {}).get("score", 100)
    if sc_score < 50:
        overall_int = min(overall_int, 60)
    elif sc_score < 70:
        overall_int = min(overall_int, 75)
    de = dims.get("decorrelation_star", {})
    de_current = de.get("current_pct", 0)
    de_target = de.get("target_pct", 15)
    if de_current < de_target * 0.3:
        overall_int = min(overall_int, 60)
    elif de_current < de_target * 0.6:
        overall_int = min(overall_int, 72)
    qp = dims.get("quality_T1_plus", {})
    if qp.get("status") != "data_insufficient" and qp.get("current_pct", 0) < qp.get("target_pct", 65) * 0.4:
        overall_int = min(overall_int, 65)
    cv = dims.get("cycle_valo_exposure", {})
    if cv.get("current_pct", 0) > cv.get("target_pct", 20) * 2.5:
        overall_int = min(overall_int, 65)
    return {
        "overall_score": overall_int,
        "overall_grade": score_to_grade(overall_int),
        "dimensions": dims,
        "total_capital_eur": state["total_capital_eur"],
        "n_positions": len(state["positions"]),
        "n_theses_active": len(state["theses_active"]),
        "n_dims_data_insufficient": sum(1 for d in dims.values() if d.get("status") == "data_insufficient"),
    }


def simulate_grade(action: dict) -> dict:
    """Sprint 6 — Recompute the grade with a hypothetical action applied.

    action = {
        "type": "buy" | "sell" | "scale_in" | "scale_out",
        "ticker": str,
        "qty": float,
        "price_eur": float (optional, defaults to avg_cost on sell)
    }

    Returns {
        "before": {grade, score, dims},
        "after":  {grade, score, dims},
        "delta_score": int,
        "delta_letter": "B+ -> A-",
        "diagnosis": list[str],  # human-readable list of what shifted
    }

    Conservative simulation : we only update the 'positions' weight/qty
    snapshot. Theses are unchanged (a new buy is assumed under the existing
    conviction if a these exists ; otherwise conviction defaults to 3).
    """
    from copy import deepcopy

    state_before = _fetch_state()
    before = _grade_from_state(state_before)

    state_after = deepcopy(state_before)
    tk = action["ticker"]
    act_type = action.get("type", "buy")
    qty = float(action.get("qty") or 0)
    price = float(action.get("price_eur") or 0)

    pos_map = {p["ticker"]: p for p in state_after["positions"]}
    if act_type in ("buy", "scale_in"):
        # Find avg_cost basis
        if tk in pos_map:
            p = pos_map[tk]
            old_qty = p["qty"]
            old_w = p["weight"]
            new_qty = old_qty + qty
            new_w = old_w + qty * price
            p["qty"] = new_qty
            p["weight"] = new_w
            p["avg_cost"] = new_w / new_qty if new_qty else 0
        else:
            state_after["positions"].append({
                "ticker": tk, "qty": qty, "avg_cost": price, "weight": qty * price,
            })
    elif act_type in ("sell", "scale_out", "full_exit") and tk in pos_map:
        p = pos_map[tk]
        if act_type == "full_exit" or qty >= p["qty"]:
            state_after["positions"] = [pp for pp in state_after["positions"] if pp["ticker"] != tk]
        else:
            p["qty"] = p["qty"] - qty
            p["weight"] = p["qty"] * p["avg_cost"]
    state_after["total_capital_eur"] = sum(p["weight"] for p in state_after["positions"])

    after = _grade_from_state(state_after)
    delta = after["overall_score"] - before["overall_score"]

    # Diagnosis : which dims moved >= 5 pts
    diag = []
    for dk, d_after in after["dimensions"].items():
        d_before = before["dimensions"].get(dk) or {}
        d_diff = d_after.get("score", 0) - d_before.get("score", 0)
        if abs(d_diff) >= 5:
            arrow = "+" if d_diff > 0 else ""
            diag.append(f"{dk} : {d_before.get('current_pct', 0):.1f}% -> {d_after.get('current_pct', 0):.1f}% ({arrow}{d_diff:.0f} pts)")

    return {
        "before": before,
        "after": after,
        "delta_score": delta,
        "delta_letter": f"{before['overall_grade']} -> {after['overall_grade']}",
        "diagnosis": diag,
        "action": action,
    }


def compute_trend_7d() -> str:
    """Compare today's score vs 7d ago. Returns 'improving' | 'stable' | 'deteriorating'."""
    from shared import storage

    latest = storage.get_latest_portfolio_grade()
    week_ago = storage.get_portfolio_grade_n_days_ago(7)
    if not latest or not week_ago:
        return "no_history"
    delta = latest.get("overall_score", 0) - week_ago.get("overall_score", 0)
    if delta >= 3:
        return "improving"
    if delta <= -3:
        return "deteriorating"
    return "stable"


def serialize_for_db(grade: dict) -> str:
    return json.dumps(grade.get("dimensions", {}), ensure_ascii=False)
