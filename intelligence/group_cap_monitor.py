"""group_cap monitor (#149) -- detection transition dormant/over par GROUPE.

4e monitor canonique cf docs/templates/monitor_pattern.md (apres
kill_criteria_monitor + over_cap_monitor + stale_target_monitor).
Pattern fige : 3x plus rapide que le 2e, 5x plus rapide que le 1er.

Mission :
    Flagger quand l'exposition agregee d'un GROUPE de tickers (e.g. memory
    makers Hynix + Micron) depasse le cap declare. C'est l'analogue
    over_cap_monitor mais au niveau GROUPE, pas position individuelle.

Premier groupe live : memory = {000660.KS, MU} cap 6% (decision Olivier
13/06 post Hynix repose Regime A : "Cap groupe memoire 6% reste le vrai
garde-fou de taille, overlay book-level hors these").

Status enum :
    dormant : group_pct <= cap_pct (sous le cap, OK)
    over    : group_pct > cap_pct (au-dessus du cap, action recommandee)

Transition ACTIONABLE (notify) : dormant_to_over.
Transition OBSERVABLE (audit seulement) : over_to_dormant, no_change.

PAS de wire bias_events (signal pur de gouvernance taille groupe, pas
anti-biais comportemental individual).

Etat DECOUPLE du cycle bias_events (cf L4) : prev_status lu depuis
group_cap_alerts (journal dedie), pas depuis bias_events ou autre source.
Garantit pas de re-fire spurieux.
"""
from __future__ import annotations

import logging
from typing import Any

from intelligence.bias_events import MissingDataError

log = logging.getLogger(__name__)

# Configuration des groupes : key -> (tickers, cap_pct).
# Decision Olivier 13/06 post Hynix repose Regime A : cap memory 6%.
# Pure DRAM/HBM makers (000660.KS Hynix + MU Micron). Exclude wafer
# (4063.T Shin-Etsu) et test (6857.T Advantest) qui servent aussi logique.
GROUPS: dict[str, tuple[set[str], float]] = {
    "memory": ({"000660.KS", "MU"}, 6.0),
}


def _prev_status_for_group(group_key: str) -> str:
    """Lit derniere row du journal group_cap_alerts. 'dormant' par defaut si
    jamais evalue. DECOUPLE du cycle bias_events.resolved (cf L4)."""
    from shared import storage as _storage

    row = _storage.get_latest_group_cap_per_group(group_key)
    if not row:
        return "dormant"
    return row["status"] or "dormant"


def _classify_transition(prev: str, new: str) -> str:
    """Construit le label canonique de transition prev->new."""
    if prev == new:
        return "no_change"
    return f"{prev}_to_{new}"


def classify_group(
    group_key: str, tickers: set, cap_pct: float, book_lines: list,
) -> dict[str, Any] | None:
    """Source de verite UNIQUE pour la classification group_cap.

    Distingue STRICTEMENT non-classifiable legitime vs donnee manquante :
    - Returns None si AUCUN ticker du groupe n'est dans le book (groupe
      vide = non-classifiable legitime, pas de signal).
    - Raise MissingDataError si book vide global OU si une ligne du groupe
      a weight_market_eur None/<=0 (cascade book cassee).

    Args:
        group_key : identifiant du groupe (e.g. "memory").
        tickers : set des tickers du groupe.
        cap_pct : seuil cap en % du book.
        book_lines : list de BookLine canonique.

    Returns:
        dict {group_key, tickers, status, group_pct, cap_pct, group_eur, book_eur}
        OR None si groupe non-classifiable legitime (aucune position).

    Raises:
        MissingDataError : book vide OU exposure invalide.
    """
    held = [ln for ln in book_lines if (ln.qty or 0) > 0]
    if not held:
        raise MissingDataError(
            f"group_cap.classify_group {group_key} : book vide (0 positions held)"
        )

    # Cure 16/06 Lane 2 #4 : migration ln.weight_market_eur -> book.value_eur.
    # Avant : ln.weight_market_eur = qty x _cached_price_eur(tk) (DB cron-cached,
    # peut etre stale, anti-pattern monitor depend du cache dashboard).
    # Apres : recompute via book.value_eur Datum canonique (asof + degraded
    # honnetes, pas de coupling au cron). Fallback ln.weight_market_eur si
    # value_eur fail-closed (rare, mais preserve continuite du monitor).
    from shared import book as _bk
    _value_map: dict[str, float] = {}
    _degraded = 0
    for ln in held:
        qty = float(ln.qty or 0)
        if qty <= 0:
            continue
        v = _bk.value_eur(ln.ticker, qty)
        if v is not None and v.value is not None and hasattr(v.value, "amount"):
            _value_map[ln.ticker] = float(v.value.amount)
            if getattr(v, "degraded", False):
                _degraded += 1
        else:
            _value_map[ln.ticker] = float(ln.weight_market_eur or 0)
    if _degraded > 0:
        import logging as _lg
        _lg.getLogger(__name__).warning(
            "group_cap.classify_group %s : %d/%d positions value_eur DEGRADED",
            group_key, _degraded, len(_value_map),
        )

    book_eur = sum(_value_map.values())
    if book_eur <= 0:
        raise MissingDataError(
            f"group_cap.classify_group {group_key} : book_eur={book_eur} (<=0)"
        )

    group_lines = [ln for ln in held if ln.ticker in tickers]
    if not group_lines:
        # Groupe entierement absent du book (e.g. tous vendus). Non-classifiable
        # legitime : aucun signal a emettre, pas une cassure de cascade.
        return None

    group_eur = sum(_value_map.get(ln.ticker, 0.0) for ln in group_lines)
    group_pct = group_eur / book_eur * 100

    status = "over" if group_pct > cap_pct else "dormant"

    return {
        "group_key": group_key,
        "tickers": sorted(ln.ticker for ln in group_lines),
        "status": status,
        "group_pct": float(group_pct),
        "cap_pct": float(cap_pct),
        "group_eur": float(group_eur),
        "book_eur": float(book_eur),
    }


def check_all_group_cap_transitions() -> dict[str, Any]:
    """Pour chaque groupe configure, classify + transition + notify si actionable.

    Returns:
        dict {checked, dormant, over, transitions, notified, errors}
    """
    from shared import book as _bk, notify as _notify, storage as _storage

    stats: dict[str, Any] = {
        "checked": 0, "dormant": 0, "over": 0,
        "transitions": 0, "notified": 0, "errors": 0,
    }

    try:
        book_lines = _bk.get_held_lines()
    except Exception as e:
        log.warning(f"group_cap_monitor: get_held_lines failed: {e}")
        return stats

    for group_key, (tickers, cap_pct) in GROUPS.items():
        try:
            stats["checked"] += 1
            try:
                cls = classify_group(group_key, tickers, cap_pct, book_lines)
            except MissingDataError as md:
                log.warning(f"group_cap_monitor: {group_key} missing data: {md}")
                stats["errors"] += 1
                continue
            if cls is None:
                continue  # non-classifiable légitime (groupe absent)

            new_status = cls["status"]
            stats[new_status] += 1
            prev_status = _prev_status_for_group(group_key)
            transition = _classify_transition(prev_status, new_status)

            notified_flag = False
            # Transition actionable : dormant -> over
            if transition == "dormant_to_over":
                stats["transitions"] += 1
                try:
                    msg = (
                        f"📊 GROUP CAP -- {group_key.upper()}\n"
                        f"exposition {cls['group_pct']:.1f}% > cap {cls['cap_pct']:.1f}%\n"
                        f"group EUR {cls['group_eur']:.0f} / book EUR {cls['book_eur']:.0f}\n"
                        f"tickers : {', '.join(cls['tickers'])}\n"
                        f"Action : trim 1+ position du groupe pour revenir sous cap"
                    )
                    _notify.send_text(msg, parse_mode=None)
                    notified_flag = True
                    stats["notified"] += 1
                except Exception as e:
                    log.warning(f"group_cap notify {group_key} failed: {e}")
            elif transition != "no_change":
                # over_to_dormant : observable, pas notify
                stats["transitions"] += 1

            # Audit row à CHAQUE évaluation
            _storage.insert_group_cap_alert(
                group_key=group_key, tickers=cls["tickers"],
                status=new_status, group_pct=cls["group_pct"],
                cap_pct=cls["cap_pct"], group_eur=cls["group_eur"],
                book_eur=cls["book_eur"], notified=notified_flag,
                transition=transition,
            )
        except Exception as e:
            log.warning(f"group_cap_monitor: {group_key} failed: {e}")
            stats["errors"] += 1
            continue

    return stats
