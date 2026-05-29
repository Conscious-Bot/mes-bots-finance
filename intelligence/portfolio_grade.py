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
    "quality_T1_plus": 30,
    "T2_redondant": 20,
    "decorrelation_star": 15,
    "sizing_conviction": 15,
    "cluster_cap": 10,
    "thesis_health": 10,
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
    """T1 = c5 active opened ≥30j ago AND last_reviewed within 30j.
    T1★ = T1 AND avg Brier on same sector ≤ 0.4 with n_predictions ≥ 3."""
    positions = state["positions"]
    theses_by_ticker = {t["ticker"]: t for t in state["theses_active"]}
    total = state["total_capital_eur"] or 1
    now = datetime.now(UTC)
    cutoff_open = now - timedelta(days=30)
    cutoff_review = now - timedelta(days=30)

    # ★ : per-sector aggregated Brier (n>=3, avg<=0.4)
    sector_brier: dict[str, list[float]] = {}
    for p in state["predictions_resolved"]:
        sec = _ticker_sector(p["ticker"])
        if sec:
            sector_brier.setdefault(sec, []).append(p["brier"])
    sector_star: dict[str, bool] = {}
    for sec, briers in sector_brier.items():
        if len(briers) >= 3 and (sum(briers) / len(briers)) <= 0.4:
            sector_star[sec] = True

    t1_eur = 0.0
    t1_star_eur = 0.0
    n_t1 = n_t1_star = 0
    for p in positions:
        t = theses_by_ticker.get(p["ticker"])
        if not t or t.get("conviction") != 5:
            continue
        opened = t.get("opened_at") or ""
        last_rev = t.get("last_reviewed") or t.get("last_revisit_at") or opened
        opened_dt = _parse_dt_aware(opened)
        last_rev_dt = _parse_dt_aware(last_rev)
        if not opened_dt or opened_dt > cutoff_open:
            continue
        if not last_rev_dt or last_rev_dt < cutoff_review:
            continue
        # T1
        t1_eur += p["weight"]
        n_t1 += 1
        # T1★ ?
        sec = _ticker_sector(p["ticker"])
        if sec and sector_star.get(sec):
            t1_star_eur += p["weight"]
            n_t1_star += 1

    current_pct = (t1_eur + t1_star_eur) / total * 100 if total else 0
    target_pct = 65.0
    score = min(100, current_pct / target_pct * 100) if target_pct else 0
    return {
        "current_pct": round(current_pct, 1),
        "target_pct": target_pct,
        "score": round(score, 1),
        "weight": DIMENSION_WEIGHTS["quality_T1_plus"],
        "status": "at_or_above_target" if current_pct >= target_pct else "below_target",
        "evidence": f"T1 n={n_t1} ({t1_eur:.0f}€) + T1★ n={n_t1_star} ({t1_star_eur:.0f}€) sur total {total:.0f}€",
    }


def _compute_T2_redundant(state: dict) -> dict:
    """Proxy deterministe Sprint 5 : sectors avec >3 positions = redondance presumee.
    Sprint 6 LLM-augmented : detection narrative-level (sera plus precise)."""
    positions = state["positions"]
    total = state["total_capital_eur"] or 1
    sec_groups: dict[str, list[dict]] = {}
    for p in positions:
        sec = _ticker_sector(p["ticker"]) or "Other"
        sec_groups.setdefault(sec, []).append(p)
    redundant_eur = 0.0
    redundant_secs = []
    for sec, ps in sec_groups.items():
        if len(ps) > 3:
            # On compte tout au-dela de 3 (les 3 premiers sont OK, le reste = redondant)
            sorted_ps = sorted(ps, key=lambda p: -p["weight"])
            for extra in sorted_ps[3:]:
                redundant_eur += extra["weight"]
            redundant_secs.append(f"{sec} (n={len(ps)})")
    current_pct = redundant_eur / total * 100 if total else 0
    target_pct = 20.0  # max
    # Inverse score : moins on a, mieux c'est
    score = min(100, target_pct / max(current_pct, 0.1) * 100) if current_pct > target_pct else 100
    return {
        "current_pct": round(current_pct, 1),
        "target_pct": target_pct,
        "score": round(score, 1),
        "weight": DIMENSION_WEIGHTS["T2_redondant"],
        "status": "above_target" if current_pct > target_pct else "at_or_below_target",
        "evidence": f"Secteurs >3 positions : {', '.join(redundant_secs) or 'aucun'}",
        "note_for_sprint6": "Sprint 5 = proxy sector-based ; Sprint 6 = LLM narrative grouping plus precis",
    }


def _compute_decorrelation_star(state: dict) -> dict:
    """Proxy deterministe Sprint 5 : positions a conviction ≥4 dans des secteurs
    qui n'ont qu'1 position (= lone wolf). C'est la decorrelation par-defaut.
    Sprint 6 LLM-augmented : edge identification + narrative independence."""
    positions = state["positions"]
    theses_by_ticker = {t["ticker"]: t for t in state["theses_active"]}
    total = state["total_capital_eur"] or 1
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
        "evidence": f"n_lonewolf c≥4 = {n_star} ({star_eur:.0f}€ sur {total:.0f}€)",
        "note_for_sprint6": "Sprint 5 = proxy lone-wolf ; Sprint 6 = LLM edge identification",
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


def _compute_cluster_cap(state: dict) -> dict:
    """Reuse _cluster_health from dashboard.render — meme source que dashboard."""
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
            "target_pct": 35.0,
            "score": 100,
            "weight": DIMENSION_WEIGHTS["cluster_cap"],
            "status": "unknown",
            "evidence": "cluster_health fetch failed",
        }
    target_pct = 35.0
    # Score : 100 si <= target, decreasing au-dessus
    score = 100 if max_pct <= target_pct else max(0, 100 - (max_pct - target_pct) * 5)
    return {
        "current_pct": round(max_pct, 1),
        "target_pct": target_pct,
        "score": round(score, 1),
        "weight": DIMENSION_WEIGHTS["cluster_cap"],
        "status": "at_or_below_target" if max_pct <= target_pct else "above_target",
        "evidence": f"Plus gros cluster : {max_name} a {max_pct:.1f}%",
    }


def _compute_thesis_health(state: dict) -> dict:
    """Proxy deterministe Sprint 5 : % theses actives reviewed within 30j.
    Sprint 6 LLM-augmented : derive du Layer 2 conceptions."""
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
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    n_recent = 0
    for t in theses:
        last_rev = t.get("last_reviewed") or t.get("last_revisit_at") or t.get("opened_at") or ""
        last_rev_dt = _parse_dt_aware(last_rev)
        if last_rev_dt and last_rev_dt >= cutoff:
            n_recent += 1
    current_pct = n_recent / len(theses) * 100
    target_pct = 80.0
    score = min(100, current_pct / target_pct * 100) if target_pct else 0
    return {
        "current_pct": round(current_pct, 1),
        "target_pct": target_pct,
        "score": round(score, 1),
        "weight": DIMENSION_WEIGHTS["thesis_health"],
        "status": "at_or_above_target" if current_pct >= target_pct else "below_target",
        "evidence": f"{n_recent}/{len(theses)} theses reviewees < 30j",
        "note_for_sprint6": "Sprint 5 = proxy review-age ; Sprint 6 = Layer 2 conceptions signal flow",
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
    }
    overall = sum(d["score"] * d["weight"] / 100 for d in dims.values())
    overall_int = round(overall)
    grade = score_to_grade(overall_int)
    return {
        "snapshot_date": datetime.now(UTC).date().isoformat(),
        "overall_score": overall_int,
        "overall_grade": grade,
        "dimensions": dims,
        "total_capital_eur": state["total_capital_eur"],
        "n_positions": len(state["positions"]),
        "n_theses_active": len(state["theses_active"]),
        "computation_version": "sprint5_deterministic",
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
