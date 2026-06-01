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


def wire_bias_trigger(recommendations: list[dict]) -> dict[str, int]:
    """v2.c.5 -- branchement observation-only : pour chaque reco emise
    au point user-facing (brief / risk_check / tiers), ouvre 1 candidat
    bias_event -- SANS le piege #1 (sur-declenchement).

    Cle d'identite reco = (ticker, bias, discipline_said.action,
    discipline_said.ref). Le prix, la qty courante, l'ecart cible peuvent
    deriver d'un cycle a l'autre (recompute internes) ; ils ne changent
    PAS l'identite de la reco -- ce sont des parametres. Sans cette regle,
    chaque cycle prix voiderait/reouvrirait, remettant created_at a zero
    en boucle : la fenetre n'accumulerait jamais et rien ne resoudrait.

    Comportement par reco :
    - aucun open meme (ticker, bias)            -> open_candidate (new)
    - open meme (ticker, bias) + MEME action+ref -> NO-OP (kept, created_at preserve)
    - open meme (ticker, bias) + action/ref DIFFERENT -> open_candidate
      (supersede automatique via c.2 : void ancien + INSERT)

    FAIL-SAFE (user 01/06) : chaque ouverture est wrapee try/except. Un
    bug dans une reco ne casse JAMAIS la boucle ni le caller. Le brief/
    risk/tiers user-facing survit toujours. Stats retournees pour
    observation.

    Args:
        recommendations: list de dicts avec champs requis :
            - ticker (str UPPERCASE)
            - bias ('lock_in' | 'fomo_greed' | 'other')
            - discipline_said (dict avec 'action' + 'ref')
            - horizon_days (int)
            - anchor_price_eur (float)
            - initial_qty (float)
            - discipline_expected_delta (float)
          + optionnels : thesis_id, prediction_id, source, note.

    Returns:
        dict {opened, kept, superseded, errors} -- diagnostic, jamais raise.
    """
    from shared.storage import DB_PATH

    stats = {"opened": 0, "kept": 0, "superseded": 0, "errors": 0}
    if not recommendations:
        return stats

    for reco in recommendations:
        try:
            ticker = reco["ticker"]
            bias = reco["bias"]
            discipline_said = reco["discipline_said"]
            new_action = discipline_said.get("action")
            new_ref = discipline_said.get("ref")

            conn = sqlite3.connect(DB_PATH)
            try:
                row = conn.execute(
                    "SELECT id, decision_json FROM bias_events "
                    "WHERE status='open' AND ticker=? AND bias=? "
                    "ORDER BY id DESC LIMIT 1",
                    (ticker, bias),
                ).fetchone()
            finally:
                conn.close()

            if row is not None:
                try:
                    existing_decision = json.loads(row[1])
                    existing_said = existing_decision.get("discipline_said", {})
                    existing_action = existing_said.get("action")
                    existing_ref = existing_said.get("ref")
                except (json.JSONDecodeError, TypeError, KeyError):
                    existing_action = existing_ref = None

                if existing_action == new_action and existing_ref == new_ref:
                    # MEME reco -> NO-OP. created_at de l'ancien preserve,
                    # la fenetre court depuis l'emission initiale.
                    stats["kept"] += 1
                    continue
                # Reco materiellement differente -> supersede via c.2
                # (open_candidate void TOUS les open meme ticker+bias).
                open_candidate(
                    ticker=ticker, bias=bias,
                    discipline_said=discipline_said,
                    horizon_days=reco["horizon_days"],
                    anchor_price_eur=reco["anchor_price_eur"],
                    initial_qty=reco["initial_qty"],
                    discipline_expected_delta=reco["discipline_expected_delta"],
                    thesis_id=reco.get("thesis_id"),
                    prediction_id=reco.get("prediction_id"),
                    source=reco.get("source", "auto_detected"),
                    note=reco.get("note"),
                )
                stats["superseded"] += 1
            else:
                # Aucun open existant -> nouvelle ouverture
                open_candidate(
                    ticker=ticker, bias=bias,
                    discipline_said=discipline_said,
                    horizon_days=reco["horizon_days"],
                    anchor_price_eur=reco["anchor_price_eur"],
                    initial_qty=reco["initial_qty"],
                    discipline_expected_delta=reco["discipline_expected_delta"],
                    thesis_id=reco.get("thesis_id"),
                    prediction_id=reco.get("prediction_id"),
                    source=reco.get("source", "auto_detected"),
                    note=reco.get("note"),
                )
                stats["opened"] += 1
        except Exception as e:
            # FAIL-SAFE strict : aucune exception ne traverse vers le caller.
            log.warning(
                "wire_bias_trigger: ouverture echouee pour %s : %s",
                reco.get("ticker", "?"), e,
            )
            stats["errors"] += 1
            continue

    return stats


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


_TRADE_TYPES = ("buy", "sell")  # SEULS types qui changent les shares.


def _qty_delta_from_event(pos_event: dict[str, Any]) -> float:
    """Signe le qty selon event_type. buy -> +qty, sell -> -qty.
    Tout type hors _TRADE_TYPES (dividend, split, adjustment, metadata)
    -> 0.0 (ignore du delta net). Aligne user guidance v2.c.3 prep #2.
    """
    et = (pos_event.get("event_type") or "").lower()
    if et not in _TRADE_TYPES:
        return 0.0
    qty = float(pos_event.get("qty", 0.0))
    return qty if et == "buy" else -qty


def _query_position_events_in_window(
    ticker: str, created_at_iso: str, resolve_at_iso: str,
) -> list[dict[str, Any]]:
    """Query position_events strictement filtree pour le window
    (created_at, resolve_at]. Borne exclusive a created_at (event au moment
    de l'open est deja dans initial_qty), inclusive a resolve_at (last
    moment avant resolution). Tie-break par id si timestamps egaux.
    Filtre type IN ('buy', 'sell') AU NIVEAU SQL (exclus div/split/etc).
    """
    from shared.storage import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, ticker, event_type, qty, timestamp "
            "FROM position_events "
            "WHERE ticker = ? "
            "  AND event_type IN ('buy', 'sell') "
            "  AND timestamp > ? AND timestamp <= ? "
            "ORDER BY timestamp ASC, id ASC",
            (ticker.upper(), created_at_iso, resolve_at_iso),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def resolve_one_bias_event(
    event: dict[str, Any],
    position_events_in_window: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    """Calcule resolution_json + action classifiee pour UN event.
    Single-path post v2.c.3 : shares_taken/avoided SOURCES DE position_events
    via classify_net_delta. plus de shares_taken/avoided dans counterfactual_json.

    Value-equivalence preservee (user guide regle #1) : la valorisation EUR
    FX-coherente de v2.b ne bouge pas. Seule la source des shares change
    (table position_events au lieu du JSON).

    Args:
        event: dict avec keys ticker, counterfactual_json, decision_json,
               resolve_at, bias, created_at
        position_events_in_window: list de position_events filtres + dans
            le window, deja injecte par le caller (resolve_due_bias_events
            ou test). Permet unit test pure sans DB query.

    Returns:
        (resolution_json_dict, classified_action)
        - classified_action : 'acted_on_bias' OU 'resisted', a appliquer
          via UPDATE bias_events.action = ? avant marquage resolved.

    Raises:
        MissingDataError: si price_at_horizon_eur indisponible (delisted/FX gap)
        ValueError: si counterfactual_json mal forme (champs requis manquants)

    PIEGE FENETRE VIDE (user guide #1) : 0 trade dans le window N'EST PAS
    une erreur. C'est un signal valide -- classify_net_delta retourne
    actual_delta=0 et le label depend de discipline_expected_delta :
    - discipline=hold (expected=0) + 0 trade -> resisted (a tenu)
    - discipline=exit (expected=-initial) + 0 trade -> acted_on_bias
      (echec a sortir). NE PAS confondre avec MissingDataError (prix manquant).
    """
    from shared.prices import get_close_on_in_eur

    ticker = event.get("ticker")
    cf_raw = event.get("counterfactual_json")
    resolve_at = event.get("resolve_at")
    bias = event.get("bias", "other")
    if not cf_raw or not resolve_at:
        raise ValueError(
            f"event id={event.get('id')} : counterfactual_json ou resolve_at "
            f"manquant -- impossible de resoudre."
        )
    cf = json.loads(cf_raw)
    anchor_price_eur = cf.get("anchor_price_eur")
    initial_qty = cf.get("initial_qty")
    discipline_expected_delta = cf.get("discipline_expected_delta")
    if anchor_price_eur is None or initial_qty is None or discipline_expected_delta is None:
        raise ValueError(
            f"event id={event.get('id')} : counterfactual_json incomplet "
            f"(anchor_price_eur, initial_qty, discipline_expected_delta requis "
            f"-- shape v2.c attendu)."
        )

    horizon_date = resolve_at[:10]
    if ticker is None:
        raise MissingDataError(
            f"event id={event.get('id')} : ticker NULL (event portefeuille) "
            f"non-supporte en v2.c. Reserve a iteration future."
        )
    price_at_horizon_eur = get_close_on_in_eur(ticker, horizon_date)
    if price_at_horizon_eur is None:
        raise MissingDataError(
            f"event id={event.get('id')} ticker={ticker} : price_at_horizon_eur "
            f"None au {horizon_date} (delisted / FX gap / suspended)."
        )

    # Classifie via position_events injecte (peut etre [] = fenetre vide).
    # _qty_delta_from_event ignore les types non-trade (dividend, split, etc).
    enriched_events = [
        {"qty_delta": _qty_delta_from_event(e)} for e in position_events_in_window
    ]
    classified_action, shares_taken, shares_avoided, actual_delta = classify_net_delta(
        bias=bias,
        discipline_expected_delta=float(discipline_expected_delta),
        position_events_in_window=enriched_events,
        initial_qty=float(initial_qty),
    )

    # Formule canonique inchangee (value-equivalence v2.b)
    shares_delta = shares_taken - shares_avoided
    delta_signed_eur = shares_delta * (price_at_horizon_eur - anchor_price_eur)
    cash_oisif_eur = max(0.0, (shares_avoided - shares_taken) * anchor_price_eur)
    value_taken_eur = shares_taken * price_at_horizon_eur + cash_oisif_eur
    value_avoided_eur = shares_avoided * price_at_horizon_eur

    counterfactual_method = cf.get("counterfactual_method", "cash_idle")
    resolution = {
        "delta_signed_eur": round(delta_signed_eur, 2),
        "value_taken_eur": round(value_taken_eur, 2),
        "value_avoided_eur": round(value_avoided_eur, 2),
        "measured_at": datetime.now(UTC).isoformat(),
        "price_at_horizon_eur": round(price_at_horizon_eur, 4),
        "classified_action": classified_action,
        "n_trades_in_window": len(position_events_in_window),
        "actual_delta_net": actual_delta,
        "summary": (
            f"{ticker} {bias} : classified={classified_action} "
            f"({len(position_events_in_window)} trades, net {actual_delta:+.2f}), "
            f"taken={shares_taken} vs avoided={shares_avoided}, "
            f"price {anchor_price_eur:.2f} -> {price_at_horizon_eur:.2f} EUR, "
            f"method={counterfactual_method}, delta {delta_signed_eur:+.2f} EUR"
        ),
    }
    return resolution, classified_action


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
                # v2.c.3 : query position_events au lieu de lire JSON.
                # Window strict (created_at, resolve_at], filtre buy/sell.
                pos_events = _query_position_events_in_window(
                    ticker=event["ticker"],
                    created_at_iso=event["created_at"],
                    resolve_at_iso=event["resolve_at"],
                ) if event.get("ticker") else []
                resolution_json, classified_action = resolve_one_bias_event(
                    event, pos_events,
                )
                # UPDATE action si classification dit resisted (provisoire
                # acted_on_bias a l'open via open_candidate).
                conn.execute(
                    "UPDATE bias_events SET action=?, resolution_json=?, "
                    "status='resolved' WHERE id=?",
                    (classified_action, json.dumps(resolution_json, sort_keys=True), eid),
                )
                n_resolved += 1
                details.append({
                    "id": eid, "status": "resolved",
                    "classified_action": classified_action,
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


# Pile 2.1 v2.c.6 -- Backfill cron weekly enrichit observations[] sur les
# bias_events resolved (architecture B3 user 01/06 Q3). Sememantique :
# - resolution_json.delta_signed_eur = scoring CANONIQUE immutable (a +30j)
# - resolution_json.observations[] = log d'enrichissement APPEND-ONLY
#   (jamais mutation, jamais delete -- compatible PIT bitemporal ADR 001)
# - Chaque entree observations[] = {horizon_days, price_native, price_eur,
#   delta_eur, fetched_at}
#
# Run weekly Sunday apres le cron KPI (~22:45). Fetch yfinance cache _PX_TTL.
# Idempotent : skip si observation pour ce horizon deja presente.

_BACKFILL_HORIZONS_DAYS = (60, 90)


def backfill_resolved_observations(
    horizons: tuple[int, ...] = _BACKFILL_HORIZONS_DAYS,
    limit: int = 200,
) -> dict[str, Any]:
    """Pour chaque bias_event status='resolved' suffisamment ancien (resolve_at
    + horizon <= now), append observation prix EUR pour les horizons longs
    manquants. Append-only dans resolution_json.observations[].

    Architecture B3 (user 01/06 Q3) : pas de mutation du scoring canonical,
    juste enrichissement async. Resilient au crash (skip si deja present).

    Args:
        horizons: horizons longs a backfiller (default 60, 90 jours).
        limit: max bias_events scannes par run (eviter LIMITless si journal
            grossit).

    Returns:
        dict {scanned, enriched, skipped, errors, missing_data}.
    """
    from shared.prices import get_close_on, get_close_on_in_eur
    from shared.storage import DB_PATH

    stats = {"scanned": 0, "enriched": 0, "skipped": 0, "errors": 0, "missing_data": 0}
    max_horizon = max(horizons)

    cx = sqlite3.connect(DB_PATH)
    cx.row_factory = sqlite3.Row
    try:
        # bias_events resolved dont anchor + max_horizon est passe -> on peut
        # backfiller tous les horizons demandes.
        rows = cx.execute(
            "SELECT id, ticker, created_at, resolve_at, counterfactual_json, "
            "       resolution_json "
            "FROM bias_events "
            "WHERE status='resolved' "
            "  AND resolution_json IS NOT NULL "
            "  AND datetime(created_at, ?) <= datetime('now') "
            "ORDER BY id ASC "
            "LIMIT ?",
            (f"+{max_horizon} days", limit),
        ).fetchall()
    finally:
        cx.close()

    for r in rows:
        stats["scanned"] += 1
        try:
            cf = json.loads(r["counterfactual_json"] or "{}")
            res = json.loads(r["resolution_json"] or "{}")
        except json.JSONDecodeError:
            stats["errors"] += 1
            continue

        anchor_eur = cf.get("anchor_price_eur")
        if not anchor_eur or anchor_eur <= 0:
            stats["errors"] += 1
            continue

        # Date d'ancrage = created_at (heure d'ouverture du candidat = vente
        # pour lock_in, ou transition pour kca/over_cap)
        try:
            created = datetime.fromisoformat(
                str(r["created_at"]).replace("Z", "+00:00")
            )
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
        except ValueError:
            stats["errors"] += 1
            continue

        observations = list(res.get("observations") or [])
        existing_horizons = {o.get("horizon_days") for o in observations}

        any_added = False
        for h in horizons:
            if h in existing_horizons:
                continue  # deja backfille
            target_date = (created + timedelta(days=h)).strftime("%Y-%m-%d")
            price_eur = get_close_on_in_eur(r["ticker"], target_date)
            if price_eur is None:
                stats["missing_data"] += 1
                continue
            try:
                price_native = get_close_on(r["ticker"], target_date)
            except Exception:
                price_native = None
            delta_eur = (price_eur - anchor_eur) * cf.get("initial_qty", 0)
            observations.append({
                "horizon_days": h,
                "price_native": price_native,
                "price_eur": round(price_eur, 6),
                "delta_eur": round(delta_eur, 4),
                "fetched_at": datetime.now(UTC).isoformat(),
            })
            any_added = True

        if not any_added:
            stats["skipped"] += 1
            continue

        # Persist : append observations[], jamais mutation des champs
        # canoniques.
        res["observations"] = observations
        cx_upd = sqlite3.connect(DB_PATH)
        try:
            cx_upd.execute(
                "UPDATE bias_events SET resolution_json=? WHERE id=?",
                (json.dumps(res, sort_keys=True), r["id"]),
            )
            cx_upd.commit()
            stats["enriched"] += 1
        finally:
            cx_upd.close()

    return stats
