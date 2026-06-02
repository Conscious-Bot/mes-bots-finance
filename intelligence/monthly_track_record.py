"""Monthly track record orchestrator : recal + snapshot + audit (#89).

Job mensuel (1er du mois) qui :
  1. compute_public_track_record + timeseries (snapshot etat current)
  2. recalibrate_source_credibility (apply learning rule)
  3. export JSON dated dans data/track_record/snapshots/
  4. log dans cron_log
  5. retourne summary structure (pour Telegram digest)

Coupe la duplication entre :
- la page publique (snapshot mensuel publishable)
- le cron credibility recal
- le decision_log narratif mensuel

Pattern : 1 entry point `run_monthly_track_record_job()`. Idempotent
sur le mois courant (skip si snapshot deja present pour ce mois).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _snapshots_dir() -> Path:
    """data/track_record/snapshots/ -- cree si manquant."""
    d = Path(__file__).resolve().parent.parent / "data" / "track_record" / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _snapshot_path_for_month(year_month: str) -> Path:
    """data/track_record/snapshots/YYYY-MM.json"""
    return _snapshots_dir() / f"{year_month}.json"


def run_monthly_track_record_job(
    cx: sqlite3.Connection,
    rolling_days: int = 180,
    recal_dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Job mensuel canonique.

    Args:
        cx: connexion sqlite3
        rolling_days: fenetre rolling pour aggregator + timeseries
        recal_dry_run: si True, compute le recal mais n'applique pas
        force: si True, ecrase le snapshot existant du mois courant

    Returns:
        dict {
            year_month, snapshot_path,
            aggregator_summary : posture_global,
            recal_summary : {n_sources_processed, n_applied, applied},
            timeseries_keys : [...],
            skipped (bool),
        }
    """
    year_month = datetime.now(UTC).strftime("%Y-%m")
    snapshot_path = _snapshot_path_for_month(year_month)

    if snapshot_path.exists() and not force:
        log.info(f"monthly_track_record SKIP {year_month} (snapshot existe)")
        return {
            "year_month": year_month,
            "snapshot_path": str(snapshot_path),
            "skipped": True,
            "reason": "snapshot_already_exists",
        }

    # Imports locaux (defensive)
    from intelligence.calibration_audit import recalibrate_source_credibility
    from intelligence.track_record_aggregator import compute_public_track_record
    from intelligence.track_record_timeseries import compute_all_timeseries

    # 1. Aggregator snapshot
    aggregator = compute_public_track_record(cx, rolling_days=rolling_days)

    # 2. Timeseries (charts data)
    timeseries = compute_all_timeseries(cx, total_days=rolling_days)

    # 3. Recal credibility
    recal = recalibrate_source_credibility(cx, days=rolling_days, dry_run=recal_dry_run)
    n_applied = sum(1 for r in recal if r.get("applied"))

    # 4. Export JSON
    snapshot = {
        "year_month": year_month,
        "generated_at": datetime.now(UTC).isoformat(),
        "rolling_days": rolling_days,
        "aggregator": aggregator,
        "timeseries": timeseries,
        "recal": {
            "dry_run": recal_dry_run,
            "n_processed": len(recal),
            "n_applied": n_applied,
            "details": recal,
        },
    }
    snapshot_path.write_text(
        json.dumps(snapshot, sort_keys=True, default=str, indent=2),
        encoding="utf-8",
    )
    log.info(f"monthly_track_record EXPORTED {snapshot_path}")

    # Re-render la page publique avec donnees fraiches.
    public_html_path: str | None = None
    try:
        from scripts.render_public_track import main as render_public_main
        rendered = render_public_main()
        public_html_path = str(rendered)
        log.info(f"monthly_track_record PUBLIC_RENDERED {public_html_path}")
    except Exception as exc:
        log.warning(f"monthly_track_record PUBLIC_RENDER_FAILED {exc}")

    return {
        "year_month": year_month,
        "snapshot_path": str(snapshot_path),
        "public_html_path": public_html_path,
        "aggregator_summary": {
            "posture_global": aggregator.get("posture_global"),
            "n_resolved_predictions": aggregator.get("predictions", {}).get("n_resolved"),
            "bias_total_delta_eur": aggregator.get("bias_total_delta_signed_eur"),
            "n_active_theses": aggregator.get("theses", {}).get("n_active"),
        },
        "recal_summary": {
            "n_sources_processed": len(recal),
            "n_applied": n_applied,
            "applied": [r for r in recal if r.get("applied")],
        },
        "timeseries_keys": list(timeseries.keys()),
        "skipped": False,
    }


def load_snapshot(year_month: str) -> dict[str, Any] | None:
    """Lit un snapshot dated. Returns None si pas trouve."""
    p = _snapshot_path_for_month(year_month)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def list_snapshots() -> list[str]:
    """Liste les YYYY-MM snapshots presents, trie chrono."""
    d = _snapshots_dir()
    return sorted(p.stem for p in d.glob("*.json"))
