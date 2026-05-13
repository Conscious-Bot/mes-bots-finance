"""Phase Digestion 3b — Cross-source corroboration multiplier on materiality scores.

When N≥2 distinct sources cluster on the same topic (via echo_cluster_id from A3),
boost the materiality score:
- 1 source → 1.0 (no boost, lone signal)
- 2 sources → 1.3
- 3 sources → 1.5
- 4+ sources → 1.7

Counter to behavioral biais "vu une fois sur Twitter → trade".
Refreshed by cron after echo_clusters_job runs (every 1h).
"""

import logging

log = logging.getLogger(__name__)


def compute_corroboration_multiplier(n_distinct_sources: int) -> float:
    """Return multiplier 1.0-1.7 based on source corroboration."""
    if n_distinct_sources >= 4:
        return 1.7
    if n_distinct_sources >= 3:
        return 1.5
    if n_distinct_sources >= 2:
        return 1.3
    return 1.0


def recompute_boosts_for_clustered_signals() -> int:
    """Cron job: recompute materiality_boost for all clustered signals.
    Returns count of signals updated.
    """
    import sqlite3

    from shared import storage

    updated = 0
    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Get all signals with an echo_cluster_id
        rows = conn.execute(
            "SELECT id, echo_cluster_id, COALESCE(materiality_boost, 1.0) AS current_boost "
            "FROM signals WHERE echo_cluster_id IS NOT NULL"
        ).fetchall()
        for r in rows:
            cid = r["echo_cluster_id"]
            n = storage.get_signals_in_cluster_with_sources(cid)
            new_boost = compute_corroboration_multiplier(n)
            if abs((r["current_boost"] or 1.0) - new_boost) > 0.001:
                storage.update_materiality_boost(r["id"], new_boost)
                updated += 1
    finally:
        conn.close()
    log.info(f"materiality_boost: {updated} signals updated")
    return updated
