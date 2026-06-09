"""Layer 3 — bot_preferences : ce qui MARCHE deterministically pour CE user.

Pendant agrege a Layer 2 (bot_conceptions per ticker) : ici on agrege au
niveau PATTERN ie sizing, conviction, horizon, sector, bias.

Calibration est l'inverse de l'opinion : on NE DEMANDE PAS au modele ce
qu'il pense — on regarde ce qui s'est passe (return_30d_pct des decisions
resolved, outcome_label des copilot interventions resolved).

Pour eviter la confirmation bias note dans le review utilisateur (l'outil
recyclait les notes user comme analyse), Layer 3 SEPARE :
  - metrique deterministe : le calcul brut (samples, win rate, mean return)
  - insight LLM (provenance=llm_augmented) : 2-4 phrases d'interpretation
  - confidence : derivee du sample size (Wilson-like, conservative)

Kinds :
  - conviction_calibration : c5 outperforme-t-il c3 ? gap moyen + p
  - sizing_outcome         : grosses positions vs petites — return moyen
  - horizon_outcome        : short / med / long horizons — return moyen
  - sector_outcome         : par cluster — return moyen + Brier
  - bias_outcome           : decisions avec bias_tag X — return moyen
  - archetype_consistency  : drift de l'archetype risky/balanced sur le temps
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime

from shared import storage

log = logging.getLogger(__name__)


# ─────────────────────────── Utility ─────────────────────────────────────────


def _confidence_from_n(n: int) -> int:
    """Conservative confidence calibration from sample size."""
    if n < 3:
        return 10
    if n < 10:
        return 30
    if n < 30:
        return 55
    if n < 100:
        return 75
    return 90


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _winrate(xs: list[float], thresh: float = 0.0) -> float:
    if not xs:
        return 0.0
    return sum(1 for x in xs if x > thresh) / len(xs) * 100


# ─────────────────────────── Extractors ──────────────────────────────────────


def _extract_conviction_calibration() -> dict:
    """Do high-conviction decisions actually outperform? Deterministic.

    Group decisions by confidence_pre (1-5), compute mean return_30d_pct +
    winrate. No opinion, just raw counts.
    """
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT confidence_pre, return_30d_pct FROM decisions "
            "WHERE return_30d_pct IS NOT NULL"
        ).fetchall()
    bucket: dict = {}
    for conv, ret in rows:
        if conv is None or ret is None:
            continue
        bucket.setdefault(int(conv), []).append(float(ret))
    out: dict = {}
    for c, vals in sorted(bucket.items()):
        out[f"c{c}"] = {
            "n": len(vals),
            "mean_return_30d_pct": round(_mean(vals), 2),
            "winrate_pct": round(_winrate(vals), 1),
            "min": round(min(vals), 2),
            "max": round(max(vals), 2),
        }
    n_total = sum(out[k]["n"] for k in out)
    return {"buckets": out, "n_samples": n_total}


def _extract_sector_outcome() -> dict:
    """Group decisions by cluster membership (config.yaml clusters).

    For each cluster : sample size, mean return, winrate. Deterministic.
    """
    from pathlib import Path

    import yaml

    cfg = yaml.safe_load(Path("config.yaml").read_text())
    clusters = (cfg.get("concentration") or {}).get("clusters") or {}
    ticker_to_cluster = {}
    for cname, members in clusters.items():
        for tk in (members or []):
            ticker_to_cluster[tk] = cname

    with storage.db() as cx:
        rows = cx.execute(
            "SELECT ticker, return_30d_pct FROM decisions "
            "WHERE return_30d_pct IS NOT NULL"
        ).fetchall()
    bucket: dict = {}
    for tk, ret in rows:
        sec = ticker_to_cluster.get(tk, "Other")
        bucket.setdefault(sec, []).append(float(ret))
    out: dict = {}
    for sec, vals in bucket.items():
        out[sec] = {
            "n": len(vals),
            "mean_return_30d_pct": round(_mean(vals), 2),
            "winrate_pct": round(_winrate(vals), 1),
        }
    return {"clusters": out, "n_samples": sum(out[k]["n"] for k in out)}


def _extract_bias_outcome() -> dict:
    """Decisions tagged with each bias : did they underperform on average?

    Source : decisions.bias_tags (JSON array of tag names).
    """
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT bias_tags, return_30d_pct FROM decisions "
            "WHERE return_30d_pct IS NOT NULL AND bias_tags IS NOT NULL"
        ).fetchall()
    bucket: dict = {}
    for tags_json, ret in rows:
        try:
            tags = json.loads(tags_json) if isinstance(tags_json, str) else (tags_json or [])
        except Exception:
            tags = []
        if not isinstance(tags, list):
            continue
        for t in tags:
            bucket.setdefault(str(t), []).append(float(ret))
    out: dict = {}
    for tag, vals in bucket.items():
        out[tag] = {
            "n": len(vals),
            "mean_return_30d_pct": round(_mean(vals), 2),
            "winrate_pct": round(_winrate(vals), 1),
        }
    return {"biases": out, "n_samples": sum(out[k]["n"] for k in out)}


def _extract_sizing_outcome() -> dict:
    """Group decisions by sizing bucket (size_pct of capital).

    Uses size implied by position deltas. Deterministic — no opinion.
    """
    # Post-0049 : positions.avg_cost = NULL. PMP rolling via BookLine.
    from shared import book as _bk
    lines_by_tk = {ln.ticker: ln for ln in _bk.get_held_lines()}
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT d.id, d.ticker, d.return_30d_pct "
            "FROM decisions d "
            "WHERE d.return_30d_pct IS NOT NULL"
        ).fetchall()
    bucket: dict = {"small_<3%": [], "mid_3-6%": [], "large_>6%": []}
    for _, ticker, ret in rows:
        ln = lines_by_tk.get(ticker)
        if ret is None or not ln or not ln.qty or not ln.avg_cost_eur:
            continue
        # approximate weight ; needs capital reference but we use proportional buckets
        wcost = float(ln.qty) * float(ln.avg_cost_eur)
        # Heuristic bucketing on absolute eur (proxy)
        if wcost < 1500:
            bucket["small_<3%"].append(float(ret))
        elif wcost < 3000:
            bucket["mid_3-6%"].append(float(ret))
        else:
            bucket["large_>6%"].append(float(ret))
    out: dict = {}
    for k, vals in bucket.items():
        out[k] = {
            "n": len(vals),
            "mean_return_30d_pct": round(_mean(vals), 2),
            "winrate_pct": round(_winrate(vals), 1),
        }
    return {"sizing": out, "n_samples": sum(out[k]["n"] for k in out)}


def _extract_archetype_consistency() -> dict:
    """Track drift of risk_archetype across user_profile snapshots."""
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT id, refreshed_at, profile_json FROM user_profile "
            "ORDER BY id DESC LIMIT 12"
        ).fetchall()
    timeline = []
    for pid, dt, pj in rows:
        try:
            p = json.loads(pj or "{}")
        except Exception:
            p = {}
        arch = p.get("risk_archetype")
        label = arch.get("label") if isinstance(arch, dict) else (arch if isinstance(arch, str) else "?")
        score = arch.get("score") if isinstance(arch, dict) else None
        timeline.append({"profile_id": pid, "at": (dt or "")[:10], "label": label, "score": score})
    return {"timeline": timeline, "n_samples": len(timeline)}


def _extract_copilot_outcome() -> dict:
    """Copilot interventions resolved : did pressure flag predict bad outcomes?"""
    out: dict = {"PROCEED": [], "PRESSURE": [], "STRONG_OPPOSE": []}
    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT verdict, return_30d_pct, outcome_label "
                "FROM bot_copilot_interventions WHERE resolved_30d_at IS NOT NULL"
            ).fetchall()
    except Exception:
        rows = []
    for ver, ret, label in rows:
        if ver in out and ret is not None:
            out[ver].append({"ret": float(ret), "label": label})
    summary: dict = {}
    n_total = 0
    for ver, items in out.items():
        rets = [it["ret"] for it in items]
        good = sum(1 for it in items if it.get("label", "").endswith("good"))
        summary[ver] = {
            "n": len(items),
            "mean_return_30d_pct": round(_mean(rets), 2),
            "winrate_pct": round(_winrate(rets), 1),
            "outcome_good_pct": round(good / len(items) * 100, 1) if items else 0,
        }
        n_total += len(items)
    return {"verdicts": summary, "n_samples": n_total}


# ─────────────────────────── Orchestration ───────────────────────────────────


_EXTRACTORS = {
    "conviction_calibration": _extract_conviction_calibration,
    "sector_outcome": _extract_sector_outcome,
    "bias_outcome": _extract_bias_outcome,
    "sizing_outcome": _extract_sizing_outcome,
    "archetype_consistency": _extract_archetype_consistency,
    "copilot_outcome": _extract_copilot_outcome,
}


def synthesize_one(kind: str) -> tuple[dict | None, int | None]:
    """Run one extractor + persist. Returns (metric_dict, pref_id)."""
    fn = _EXTRACTORS.get(kind)
    if not fn:
        return None, None
    try:
        metric = fn()
    except Exception as e:
        log.warning(f"extractor {kind} failed: {e}")
        return None, None
    n = metric.get("n_samples") or 0
    conf = _confidence_from_n(n)
    snapshot_date = datetime.now(UTC).date().isoformat()
    pid = storage.insert_bot_preference(
        kind=kind,
        snapshot_date=snapshot_date,
        metric_json=json.dumps(metric, ensure_ascii=False),
        insight_text=None,  # llm_augmented version can fill this later
        confidence=conf,
        n_samples=n,
        provenance="deterministic",
    )
    log.info(f"preference {kind} n={n} confidence={conf} id={pid}")
    return metric, pid


def synthesize_all() -> dict:
    """Run all extractors, persist each. Returns summary."""
    from typing import Any
    out: dict[str, Any] = {"ok": 0, "skip": 0, "fail": 0, "details": {}}
    for kind in _EXTRACTORS:
        try:
            metric, pid = synthesize_one(kind)
            if pid:
                out["ok"] += 1
            else:
                out["skip"] += 1
            out["details"][kind] = {"id": pid, "n": (metric or {}).get("n_samples", 0)}
        except Exception as e:
            log.warning(f"synthesize_one {kind} crashed: {e}")
            out["fail"] += 1
        time.sleep(0.05)
    return out


def format_preferences_for_copilot() -> str:
    """Render latest preferences as a block injectable in copilot prompt."""
    prefs = storage.get_latest_preferences()
    if not prefs:
        return "  (pas encore de preferences calibrees)"
    lines = []
    for p in prefs:
        kind = p.get("kind", "?")
        n = p.get("n_samples") or 0
        conf = p.get("confidence") or 0
        date = (p.get("snapshot_date") or "")[:10]
        lines.append(f"  [{kind}] n={n} conf={conf} ({date})")
        # Brief deterministic summary inline
        try:
            metric = json.loads(p.get("metric_json") or "{}")
        except Exception:
            metric = {}
        if kind == "conviction_calibration":
            for c, v in (metric.get("buckets") or {}).items():
                lines.append(
                    f"    {c}: n={v['n']} mean={v['mean_return_30d_pct']:+.1f}% "
                    f"win={v['winrate_pct']:.0f}%"
                )
        elif kind == "sector_outcome":
            for sec, v in (metric.get("clusters") or {}).items():
                if v["n"] >= 2:
                    lines.append(
                        f"    {sec[:20]}: n={v['n']} mean={v['mean_return_30d_pct']:+.1f}% "
                        f"win={v['winrate_pct']:.0f}%"
                    )
        elif kind == "bias_outcome":
            for b, v in (metric.get("biases") or {}).items():
                if v["n"] >= 1:
                    lines.append(
                        f"    bias_{b}: n={v['n']} mean={v['mean_return_30d_pct']:+.1f}%"
                    )
        elif kind == "copilot_outcome":
            for ver, v in (metric.get("verdicts") or {}).items():
                if v["n"] >= 1:
                    lines.append(
                        f"    {ver}: n={v['n']} mean={v['mean_return_30d_pct']:+.1f}% "
                        f"good={v['outcome_good_pct']:.0f}%"
                    )
        elif kind == "archetype_consistency":
            tl = metric.get("timeline") or []
            for t in tl[:3]:
                lines.append(f"    {t['at']}: {t['label']} score={t.get('score','?')}")
    return "\n".join(lines)
