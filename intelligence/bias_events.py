"""Pile 2.1 v2 contrefactuel -- resolve_due_bias_events.

User spec 31/05 close (2 critiques substantielles, cf
docs/specs/user_bias_detector_schema.md). v2 contrefactuel : EUR FX-coherent
aux 2 dates + cash_redeployment v1 flag (`cash_oisif`) + auto-detection
`resisted` (a venir v2.d) + lifecycle status transitions.

CONVENTION canonique :
- delta_signed_eur = (shares_taken - shares_avoided) * (price_at_horizon_eur - anchor_price_eur)
- POSITIF = bonne decision (peu importe action acted_on_bias ou resisted)

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

import json
import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)


class MissingDataError(Exception):
    """Levee par resolve_one_bias_event si prix EUR au horizon indisponible
    (delisted, suspended, data gap > 7j, ou FX rate absent). Le caller marque
    status='missing_data' au lieu de default silencieux. Charte invariant :
    on crashe ou on marque explicit, jamais 0."""


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


def resolve_one_bias_event(event: dict[str, Any]) -> dict[str, Any]:
    """Calcule resolution_json pour UN event. Convention :
    delta_signed_eur = (shares_taken - shares_avoided) * (price_horizon_eur - anchor_eur)

    Args:
        event: dict avec keys ticker, counterfactual_json (JSON string), resolve_at

    Returns:
        dict resolution_json prêt à insérer en DB (status='resolved' implicite côté caller)

    Raises:
        MissingDataError: si price_at_horizon_eur indisponible (delisted/FX gap)
        ValueError: si counterfactual_json mal formé (donnees obligatoires manquantes)
    """
    from shared.prices import get_close_on_in_eur

    ticker = event.get("ticker")
    cf_raw = event.get("counterfactual_json")
    resolve_at = event.get("resolve_at")
    if not cf_raw or not resolve_at:
        raise ValueError(
            f"event id={event.get('id')} : counterfactual_json ou resolve_at "
            f"manquant -- impossible de resoudre."
        )
    cf = json.loads(cf_raw)
    anchor_price_eur = cf.get("anchor_price_eur")
    shares_taken = cf.get("shares_taken")
    shares_avoided = cf.get("shares_avoided")
    if anchor_price_eur is None or shares_taken is None or shares_avoided is None:
        raise ValueError(
            f"event id={event.get('id')} : counterfactual_json incomplet "
            f"(anchor_price_eur, shares_taken, shares_avoided requis)."
        )

    # Resolve_at vient en ISO UTC. On extrait la date pour fetch close + FX a CETTE date.
    horizon_date = resolve_at[:10]  # 'YYYY-MM-DD'
    if ticker is None:
        # Event au niveau portefeuille (pas un ticker) -- v1 ne supporte pas.
        raise MissingDataError(
            f"event id={event.get('id')} : ticker NULL (event portefeuille) "
            f"non-support en v2.b. Reserve a v2.c+."
        )
    price_at_horizon_eur = get_close_on_in_eur(ticker, horizon_date)
    if price_at_horizon_eur is None:
        raise MissingDataError(
            f"event id={event.get('id')} ticker={ticker} : price_at_horizon_eur "
            f"None au {horizon_date} (delisted / FX gap / suspended)."
        )

    # Calcul canonical delta_signed
    shares_delta = shares_taken - shares_avoided
    delta_signed_eur = shares_delta * (price_at_horizon_eur - anchor_price_eur)

    # value_taken : ce que vaut la portion taken au horizon (incl. cash oisif v1)
    # cash_oisif_eur = max(0, (shares_avoided - shares_taken) * anchor_eur)
    # (positif seulement si user a degage du cash en prenant moins de shares)
    cash_oisif_eur = max(0.0, (shares_avoided - shares_taken) * anchor_price_eur)
    value_taken_eur = shares_taken * price_at_horizon_eur + cash_oisif_eur
    value_avoided_eur = shares_avoided * price_at_horizon_eur

    return {
        "delta_signed_eur": round(delta_signed_eur, 2),
        "value_taken_eur": round(value_taken_eur, 2),
        "value_avoided_eur": round(value_avoided_eur, 2),
        "measured_at": datetime.now(UTC).isoformat(),
        "price_at_horizon_eur": round(price_at_horizon_eur, 4),
        "anchor_price_eur_used": round(anchor_price_eur, 4),
        "cash_redeployment_assumption": "cash_oisif",  # v1 flag explicit
        "shares_delta_used": shares_delta,
        "summary": (
            f"{ticker} : {'taken>avoided' if shares_delta > 0 else 'taken<avoided'} "
            f"({shares_taken}-{shares_avoided}={shares_delta}), price {anchor_price_eur:.2f} -> "
            f"{price_at_horizon_eur:.2f} EUR, delta {delta_signed_eur:+.2f} EUR"
        ),
    }


def resolve_due_bias_events(limit: int = 50) -> dict[str, Any]:
    """Cron entry-point v2. Pour chaque event open du, tente resolve_one et
    update DB. Catch MissingDataError -> status='missing_data'. Catch
    ValueError -> status='void' (event malforme, audit user). Sinon -> resolved.
    """
    from shared.storage import DB_PATH

    due = get_due_bias_events(limit=limit)
    if not due:
        return {"resolved": 0, "missing": 0, "void": 0, "details": []}

    n_resolved = n_missing = n_void = 0
    details: list[dict] = []
    conn = sqlite3.connect(DB_PATH)
    try:
        for event in due:
            eid = event["id"]
            try:
                resolution_json = resolve_one_bias_event(event)
                conn.execute(
                    "UPDATE bias_events SET resolution_json=?, status='resolved' WHERE id=?",
                    (json.dumps(resolution_json, sort_keys=True), eid),
                )
                n_resolved += 1
                details.append({
                    "id": eid, "status": "resolved",
                    "delta_signed_eur": resolution_json["delta_signed_eur"],
                    "summary": resolution_json["summary"],
                })
            except MissingDataError as e:
                conn.execute(
                    "UPDATE bias_events SET status='missing_data' WHERE id=?", (eid,),
                )
                n_missing += 1
                details.append({"id": eid, "status": "missing_data", "reason": str(e)})
            except ValueError as e:
                conn.execute(
                    "UPDATE bias_events SET status='void' WHERE id=?", (eid,),
                )
                n_void += 1
                details.append({"id": eid, "status": "void", "reason": str(e)})
        conn.commit()
    finally:
        conn.close()

    log.info(
        f"bias_events resolve v2 : {n_resolved} resolved, {n_missing} missing_data, "
        f"{n_void} void (sur {len(due)} dus)."
    )
    return {
        "resolved": n_resolved, "missing": n_missing, "void": n_void,
        "details": details,
    }
