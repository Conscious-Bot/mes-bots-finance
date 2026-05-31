"""Pile 2.1 v1 mecanique -- skeleton resolve_due_bias_events.

User spec 31/05 close (2 critiques substantielles, cf
docs/specs/user_bias_detector_schema.md). v1 = mecanique seulement :
table + cron skeleton no-op. La logique contrefactuel (redeployment du
cash, EUR FX-coherent aux 2 dates, capture symetrique auto-detection)
arrive en v2 -- fenetre fraiche obligatoire (user warning explicite :
"plus haut risque de bug ET integrite-critique a la fois").

Status enum strict :
- open               : evenement cree, en attente de resolution
- resolved           : resolution_json rempli, delta_signed calcule
- void               : marquage manuel rare (erreur capture, doublon)
- thesis_invalidated : these fermee avant resolve_at -> referentiel parti
- reentered          : user a re-pris la position -> contrefactuel casse
- missing_data       : prix au resolve indisponible -- JAMAIS default silencieux

Le cron crashe ou marque missing_data, ne ment jamais.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

log = logging.getLogger(__name__)


def get_due_bias_events(limit: int = 50) -> list[dict]:
    """Open events dont resolve_at est passe. Pattern clone get_due_predictions."""
    from shared.storage import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM bias_events "
            "WHERE status='open' AND datetime(resolve_at) <= datetime('now') "
            "ORDER BY resolve_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def resolve_due_bias_events(limit: int = 50) -> dict[str, Any]:
    """Cron entry-point. v1 skeleton : decouvre les rows open, logge
    l'intention de resoudre mais ne calcule pas (contrefactuel pas
    implemente en v1 mecanique).

    v2 (fenetre fraiche) : implementer le calcul contrefactuel avec :
    - EUR via get_current_price_in_eur (FX-coherent aux 2 dates)
    - cash_redeployment depuis counterfactual_json
    - delta_signed = value_taken - value_avoided
    - status -> resolved si OK, missing_data si MissingDataError, etc.
    """
    due = get_due_bias_events(limit=limit)
    if not due:
        return {"resolved": 0, "deferred": 0, "details": []}
    log.info(
        f"bias_events : {len(due)} open events dus mais resolution v2 pas "
        f"implementee. Skipping (v1 mecanique = no-op safe)."
    )
    return {
        "resolved": 0,
        "deferred": len(due),
        "details": [
            {"id": e["id"], "bias": e["bias"], "action": e["action"],
             "ticker": e.get("ticker"), "skipped_reason": "v2_contrefactuel_pending"}
            for e in due
        ],
    }
