"""v2.c.5 -- detection transition dormant -> over_cap. Miroir kill_criteria.

Architecture (user 01/06) : over_cap n'a aucune emission ponctuelle existante --
il vit en etat ambiant sur le dashboard. Pour que la mesure bias_events soit
JUSTE (captured_at_event fidele), la reco "trimme" doit etre dite a un
instant T. On cree donc une detection de transition (weight franchit le cap
vers le haut, dormant -> over) + notify Telegram, en miroir exact du flux
kill_criteria_monitor.

ETAT DECOUPLE DU CYCLE BIAS_EVENTS (user 01/06 critique post-1er design) :
prev_status est lu depuis over_cap_alerts (journal incremental dedie, migration
0024), PAS depuis bias_events.open. Sinon un candidat over_cap qui se resout
a +30j alors que la position est toujours over -> bias_events.open absent ->
re-fire spurieux au cycle suivant. "Resolu-mais-toujours-over" doit rester
distingue de "jamais franchi" : un evenement = un franchissement = une
prediction sur un contrefactuel (orthogonalite ADR 010). Si re-test roulant
voulu plus tard = ajout delibere, pas defaut par construction.

Sequence par position :
1. Compute weight current vs cap conviction (config.concentration.line_cap_by_conviction)
2. new_status = 'over' si weight_pct > cap_pct, sinon 'dormant'
3. prev_status lu depuis over_cap_alerts.last (status). None si jamais evalue
   -> dormant par defaut.
4. Transition dormant -> over : notify Telegram + wire_bias_trigger,
   audit row inserted avec transition='dormant_to_over' + notified=1 +
   bias_event_id.
5. over -> over : audit row inserted (transition='no_change'), no notify, no wire
6. over -> dormant : audit row inserted (transition='over_to_dormant'),
   no notify, no wire. L'open candidate (s'il en reste un dans la fenetre)
   continue de courir vers resolve_at.

Bias = fomo_greed (envie de garder le runner qui court = direction dominante
gardee, user 01/06 pragmatique v1). Le cas sur-trim (lock_in dans over_cap)
est traite plus tard quand on aura un meilleur signal.

Fail-safe par ticker : un bug sur 1 position n'arrete pas la boucle. La
notify et le wire sont eux-memes wrappees -- triple protection.
"""

from __future__ import annotations

import logging
from typing import Any

from intelligence.bias_events import MissingDataError

log = logging.getLogger(__name__)

_DEFAULT_HORIZON_DAYS = 30
_OVERCAP_REF = "rule:over_cap"


def _prev_status_for_overcap(ticker: str) -> str:
    """Lit over_cap_alerts.last row pour ce ticker. 'over' ou 'dormant'
    selon la derniere evaluation. 'dormant' par defaut si jamais evalue.
    DECOUPLE du cycle bias_events.resolved (user 01/06 critique)."""
    from shared import storage as _storage

    row = _storage.get_latest_oca_per_ticker(ticker)
    if not row:
        return "dormant"
    return row["status"] or "dormant"


def _weight_pct(lines: list[dict], ticker: str) -> float | None:
    """Weight courant en % du book total (EUR market value)."""
    vtot = sum(ln.get("weight") or 0 for ln in lines) or 0
    if vtot <= 0:
        return None
    ln = next((q for q in lines if q.get("ticker") == ticker), None)
    if not ln:
        return None
    return (ln.get("weight") or 0) / vtot * 100


def classify_position(
    ticker: str,
    lines: list[dict],
    convs: dict[str, int],
    caps: dict[int, float],
) -> dict[str, Any] | None:
    """Source de verite UNIQUE pour la classification over_cap par ligne.
    Anti-double-implementation (user 01/06) : evite que bloc baseline et
    monitor divergent silencieusement.

    Distingue STRICTEMENT non-classifiable legitime vs donnee manquante :
    - Retourne None si la ligne est non-classifiable LEGITIMEMENT :
      pas dans theses actives, ou conviction sans cap configure. Ces
      lignes ne firent JAMAIS -- signal d'observation pour le baseline.
    - Raise MissingDataError si la ligne EST classifiable mais qu'une
      donnee critique manque (qty None/<=0, current_price_eur None/<=0,
      total book nul, ligne disparue). Aligne §6 invariant : on crashe
      ou on marque explicit, JAMAIS de silent drop dans IGNORED.

    Returns:
        dict (classification reussie) :
            ticker, conviction, weight_pct, cap_pct, status ('over'|'dormant'),
            qty, anchor_eur, expected_delta (None si dormant, sinon negatif)
        OU None si non-classifiable LEGITIME.

    Raises:
        MissingDataError: donnee critique manquante pour une ligne qui
            DEVRAIT etre classifiable.
    """
    conv = convs.get(ticker)
    if conv is None or not isinstance(conv, int) or conv not in caps:
        return None  # non-classifiable legitime (no these / no cap)

    cap_pct = float(caps[conv]) * 100.0
    wpct = _weight_pct(lines, ticker)
    if wpct is None:
        raise MissingDataError(
            f"over_cap.classify_position {ticker} : weight_pct None "
            f"(total book nul ou ligne introuvable post-lookup)"
        )
    ln = next((q for q in lines if q.get("ticker") == ticker), None)
    if not ln:
        raise MissingDataError(
            f"over_cap.classify_position {ticker} : ligne disparue post-weight"
        )
    qty = float(ln.get("qty") or 0)
    anchor_eur = ln.get("current_price_eur")
    if qty <= 0:
        raise MissingDataError(
            f"over_cap.classify_position {ticker} : qty={qty} (<=0)"
        )
    if anchor_eur is None or anchor_eur <= 0:
        raise MissingDataError(
            f"over_cap.classify_position {ticker} : anchor_eur={anchor_eur} "
            f"(None ou <=0)"
        )
    status = "over" if wpct > cap_pct else "dormant"
    expected_delta = None
    if status == "over":
        excess_pct = (wpct - cap_pct) / wpct
        expected_delta = -qty * excess_pct
    return {
        "ticker": ticker, "conviction": conv,
        "weight_pct": wpct, "cap_pct": cap_pct,
        "status": status, "qty": qty,
        "anchor_eur": anchor_eur,
        "expected_delta": expected_delta,
    }


def check_all_overcap_transitions() -> dict[str, Any]:
    """Pour chaque ligne canonique tenue + conviction + cap configure,
    detecte transition dormant -> over_cap et emet la reco (notify + wire).

    Returns:
        dict {checked, over, transitions, notified, wired, errors}.
    """
    from shared import config as _cfg, notify as _notify, storage as _storage

    stats = {"checked": 0, "over": 0, "transitions": 0,
             "notified": 0, "wired": 0, "errors": 0}

    caps = _cfg.load().get("concentration", {}).get("line_cap_by_conviction", {})
    if not caps:
        log.warning("over_cap_monitor: no caps configured")
        return stats

    try:
        from shared import book as _bk
        lines = [
            {
                "ticker": ln.ticker,
                "weight": ln.weight_market_eur,
                "qty": float(ln.qty or 0),
                "current_price_eur": ln.current_price_eur,
            }
            for ln in _bk.get_held_lines()
        ]
    except Exception as e:
        log.warning(f"over_cap_monitor: get_held_lines failed: {e}")
        return stats
    if not lines:
        return stats

    convs: dict[str, int] = {}
    try:
        for t in _storage.active_theses():
            tk = t.get("ticker")
            c = t.get("conviction")
            if tk and isinstance(c, int):
                convs[tk] = c
    except Exception as e:
        log.warning(f"over_cap_monitor: active_theses failed: {e}")
        return stats

    for ln in lines:
        try:
            stats["checked"] += 1
            ticker = ln["ticker"]
            try:
                cls = classify_position(ticker, lines, convs, caps)
            except MissingDataError as md:
                # Donnee critique manquante -- jamais silent skip. Logge
                # explicit + compte en errors. La ligne ne va PAS en IGNORED.
                log.warning(f"over_cap_monitor: {ticker} missing data: {md}")
                stats["errors"] += 1
                continue
            if cls is None:
                continue  # non-classifiable LEGITIME (no these / no cap)
            new_status = cls["status"]
            wpct = cls["weight_pct"]
            cap_pct = cls["cap_pct"]
            conv = cls["conviction"]
            if new_status == "over":
                stats["over"] += 1
            prev_status = _prev_status_for_overcap(ticker)

            # Classification de la transition (vrai miroir kca.prev->new)
            if prev_status == new_status:
                transition = "no_change"
            elif prev_status == "dormant" and new_status == "over":
                transition = "dormant_to_over"
            elif prev_status == "over" and new_status == "dormant":
                transition = "over_to_dormant"
            else:
                transition = None  # shouldn't happen with 2 enums

            # Default : audit row sans notify/wire. La notify/wire
            # n'arrive QUE sur dormant_to_over (clause ci-dessous).
            notified_flag = False
            bias_event_id: int | None = None

            if transition == "dormant_to_over":
                stats["transitions"] += 1
                qty = cls["qty"]
                anchor_eur = cls["anchor_eur"]
                expected_delta = cls["expected_delta"]
                if not anchor_eur or qty <= 0 or expected_delta is None:
                    log.warning(
                        f"over_cap {ticker}: anchor_eur={anchor_eur} "
                        f"qty={qty}, skip wire (audit still logged)"
                    )
                else:

                    # Notify d'abord (l'instant T fidele = franchissement dit a l'user)
                    try:
                        _notify.send_text(
                            f"📈 OVER CAP — {ticker}\n"
                            f"poids {wpct:.1f}% > cap c{conv} {cap_pct:.1f}%\n"
                            f"discipline : trim ~{abs(expected_delta):.1f} shares "
                            f"(revenir sous cap)\n"
                            f"Action : /tiers ou /alleger {ticker}"
                        )
                        notified_flag = True
                        stats["notified"] += 1
                    except Exception as e:
                        log.warning(f"over_cap notify {ticker} failed: {e}")

                    # Wire ensuite. wire_bias_trigger ne devrait JAMAIS raise
                    # (fail-safe interne) mais on entoure par precaution.
                    try:
                        from intelligence.bias_events import wire_bias_trigger
                        r = wire_bias_trigger([{
                            "ticker": ticker, "bias": "fomo_greed",
                            "discipline_said": {
                                "action": "rightsize", "ref": _OVERCAP_REF,
                            },
                            "horizon_days": _DEFAULT_HORIZON_DAYS,
                            "anchor_price_eur": float(anchor_eur),
                            "initial_qty": qty,
                            "discipline_expected_delta": expected_delta,
                            "source": "auto_detected",
                        }])
                        stats["wired"] += r.get("opened", 0)
                        # Recupere l'id du candidat ouvert pour le lien audit
                        import sqlite3 as _sql

                        from shared.storage import DB_PATH
                        cx = _sql.connect(DB_PATH)
                        try:
                            row = cx.execute(
                                "SELECT id FROM bias_events "
                                "WHERE status='open' AND ticker=? "
                                "AND bias='fomo_greed' "
                                "ORDER BY id DESC LIMIT 1",
                                (ticker,),
                            ).fetchone()
                            if row:
                                bias_event_id = int(row[0])
                        finally:
                            cx.close()
                    except Exception as e:
                        log.error(
                            f"over_cap_monitor: wire_bias_trigger raised "
                            f"on {ticker}: {e}"
                        )

            # Audit row inserted CHAQUE evaluation (incl. no_change),
            # source de verite de prev_status au prochain cycle.
            _storage.insert_over_cap_alert(
                ticker=ticker, status=new_status,
                weight_pct=wpct, cap_pct=cap_pct, conviction=conv,
                notified=notified_flag, transition=transition,
                bias_event_id=bias_event_id,
            )
        except Exception as e:
            log.warning(
                f"over_cap_monitor: {ln.get('ticker','?')} failed: {e}"
            )
            stats["errors"] += 1
            continue

    return stats
