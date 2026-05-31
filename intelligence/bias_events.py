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
from datetime import UTC, datetime, timedelta
from typing import Any

log = logging.getLogger(__name__)


class MissingDataError(Exception):
    """Levee par resolve_one_bias_event si prix EUR au horizon indisponible
    (delisted, suspended, data gap > 7j, ou FX rate absent). Le caller marque
    status='missing_data' au lieu de default silencieux. Charte invariant :
    on crashe ou on marque explicit, jamais 0."""


def classify_net_delta(
    bias: str,
    discipline_expected_delta: float,
    position_events_in_window: list[dict],
    initial_qty: float,
    noise_tolerance_pct: float = 0.05,
) -> tuple[str, float, float, float]:
    """v2.c.1 -- classification pure de l'action user vs discipline sur un
    window [created_at, resolve_at]. Aligne ADR 010 Addendum v2.c : ancrage
    sur reco discrete + classification sur le DELTA NET. Partial/reversal
    geres par construction (pas de code special).

    SEUIL NOISE (user 01/06) : la reponse disciplinee depend du type de reco
    (inaction pour hold, cible pour rightsize, mouvement plein pour exit).
    `resisted` = avoir matche CETTE reponse, pas juste "bouge dans le bon sens".
    Le piege classique est hold (discipline = ne rien faire) : sans seuil
    explicite, un trade de bruit (e.g., 1 share) basculerait a tort en
    acted_on_bias. On pose donc : si |delta_vs_discipline| <= tolerance
    (default 5% de initial_qty) -> resisted.

    Le label part de la direction/ecart-a-la-cible. La magnitude part
    SEPAREMENT vers delta_signed (cf resolve_one_bias_event). "Partiel" =
    label + magnitude, pas une 3eme categorie.

    Args:
        bias: 'lock_in' | 'fomo_greed' | 'other'
        discipline_expected_delta: changement net shares que la discipline
            recommandait (negatif = trim/exit, 0 = hold, positif = add).
        position_events_in_window: list d'events avec key 'qty_delta'
            (signed : positif=buy, negatif=sell/trim).
        initial_qty: position au created_at (= shares avant la window).
        noise_tolerance_pct: tolerance relative pour considerer le delta
            "match" la discipline (= resisted). 0.05 = 5% de initial_qty.

    Returns:
        (action, shares_taken, shares_avoided, shares_delta_net_actual)
        - action : 'acted_on_bias' OU 'resisted'
        - shares_taken : qty user a resolve_at (= initial + actual_delta)
        - shares_avoided : qty discipline aurait eu (= initial + expected_delta)
        - shares_delta_net_actual : sum signe des qty_delta (audit)
    """
    actual_delta = sum(e.get("qty_delta", 0.0) for e in position_events_in_window)
    shares_taken = initial_qty + actual_delta
    shares_avoided = initial_qty + discipline_expected_delta
    delta_vs_discipline = actual_delta - discipline_expected_delta

    # Noise tolerance : si delta_vs_discipline tient dans la zone d'inertie
    # (default 5% de initial_qty), on classe resisted = matche la discipline.
    # Couvre le piege "hold + 1 trade bruit" + "rightsize approxime" +
    # "exit a 95% mais pas 100%". Le label depend de l'ecart-a-la-cible.
    threshold = abs(initial_qty) * noise_tolerance_pct
    if abs(delta_vs_discipline) <= threshold:
        return "resisted", shares_taken, shares_avoided, actual_delta

    if bias == "lock_in":
        action = "acted_on_bias" if delta_vs_discipline < 0 else "resisted"
    elif bias == "fomo_greed":
        action = "acted_on_bias" if delta_vs_discipline > 0 else "resisted"
    else:  # 'other' : conservatif
        action = "acted_on_bias"

    return action, shares_taken, shares_avoided, actual_delta


def open_candidate(
    *,  # kwargs only -- evite l'ambiguite des positionnels (ordre arguments)
    ticker: str,
    bias: str,
    discipline_said: dict[str, Any],
    horizon_days: int,
    anchor_price_eur: float,
    initial_qty: float,
    discipline_expected_delta: float,
    thesis_id: int | None = None,
    prediction_id: int | None = None,
    source: str = "auto_detected",
    note: str | None = None,
) -> int:
    """v2.c.2 -- ouvre un candidat bias_event au moment ou la regle emet une
    reco counter-bias. Aligne ADR 010 Addendum v2.c §"Un candidat par
    recommandation".

    SUPERSEDE RULE (user 01/06) : void TOUS les candidats open meme
    (ticker, bias) avant INSERT -- pas en supposer exactement un. Si un bug
    / race / retry historique a cree plusieurs opens, ils sont tous voides.
    Apres l'appel : aucun orphelin open meme (ticker, bias) ne reste, sauf
    le nouveau qu'on vient d'INSERT.

    Action PROVISOIRE : 'acted_on_bias' a l'INSERT (l'addendum dit que
    action est determinee a la resolution via classify_net_delta). Le
    placeholder a un sens semantique : "le biais n'a pas encore ete
    resiste". resolve_one_bias_event (v2.c.3) UPDATE-ra action='resisted'
    si la classification dit que la discipline a tenu.

    decision_json capture captured_at_event=true (cf invariant ADR §3
    falsifiabilite : discipline_said capture a l'instant t, pas reconstruit
    a la resolution).

    Args:
        ticker: UPPERCASE (e.g., 'NVDA')
        bias: 'lock_in' | 'fomo_greed' | 'other'
        discipline_said: dict avec au minimum 'action' ('hold' | 'rightsize'
            | 'trim' | 'exit') et 'ref' (ID de la regle qui a emis).
        horizon_days: figé sur la thèse (cf ADR §4), jamais ad-hoc.
        anchor_price_eur: prix EUR au moment de l'emission (FX-coherent
            sera utilise par resolve aussi).
        initial_qty: shares au moment de l'emission.
        discipline_expected_delta: changement net shares recommande
            (negatif=trim/exit, 0=hold, positif=add).
        thesis_id / prediction_id: liens optionnels (FK).
        source: 'auto_detected' (default) | 'telegram_tap' | 'manual'.
        note: texte libre optionnel.

    Returns:
        id du nouveau bias_event (lastrowid).
    """
    from shared.storage import DB_PATH

    now_iso = datetime.now(UTC).isoformat()
    resolve_at_iso = (datetime.now(UTC) + timedelta(days=horizon_days)).isoformat()
    decision_json_str = json.dumps(
        {"captured_at_event": True, "discipline_said": discipline_said},
        sort_keys=True,
    )
    counterfactual_json_str = json.dumps(
        {
            "anchor_price_eur": anchor_price_eur,
            "counterfactual_method": "cash_idle",
            "discipline_expected_delta": discipline_expected_delta,
            "horizon_days": horizon_days,
            "initial_qty": initial_qty,
            "path_avoided": "discipline",
            "path_taken": "user",
        },
        sort_keys=True,
    )

    conn = sqlite3.connect(DB_PATH)
    try:
        # SUPERSEDE : void TOUS les open candidats meme (ticker, bias) -- pas
        # en supposer 1. Couvre race/bug/retry historiques qui ont accumule.
        conn.execute(
            "UPDATE bias_events SET status='void' "
            "WHERE status='open' AND ticker=? AND bias=?",
            (ticker, bias),
        )
        cursor = conn.execute(
            "INSERT INTO bias_events "
            "(created_at, ticker, bias, action, decision_json, "
            " counterfactual_json, status, source, thesis_id, prediction_id, "
            " note, horizon_days, resolve_at) "
            "VALUES (?, ?, ?, 'acted_on_bias', ?, ?, 'open', ?, ?, ?, ?, ?, ?)",
            (
                now_iso, ticker, bias,
                decision_json_str, counterfactual_json_str,
                source, thesis_id, prediction_id, note,
                horizon_days, resolve_at_iso,
            ),
        )
        new_id = cursor.lastrowid
        conn.commit()
        if new_id is None:
            raise RuntimeError("open_candidate : lastrowid None apres INSERT")
        return new_id
    finally:
        conn.close()


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

    # Aligne ADR 010 : counterfactual_method = "cash_idle" (v1) vs "redeployment" (v2 differe).
    counterfactual_method = cf.get("counterfactual_method", "cash_idle")
    return {
        "delta_signed_eur": round(delta_signed_eur, 2),
        "value_taken_eur": round(value_taken_eur, 2),
        "value_avoided_eur": round(value_avoided_eur, 2),
        "measured_at": datetime.now(UTC).isoformat(),
        "price_at_horizon_eur": round(price_at_horizon_eur, 4),
        "summary": (
            f"{ticker} : "
            f"{'taken>avoided' if shares_delta > 0 else 'taken<avoided'} "
            f"({shares_taken}-{shares_avoided}={shares_delta}), "
            f"price {anchor_price_eur:.2f} -> {price_at_horizon_eur:.2f} EUR, "
            f"method={counterfactual_method}, delta {delta_signed_eur:+.2f} EUR"
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
