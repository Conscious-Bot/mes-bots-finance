"""stale_target monitor (#134) -- detection transition alive/dying/dead.

3e monitor canonique cf docs/templates/monitor_pattern.md (apres
kill_criteria_monitor + over_cap_monitor). Le pattern figé doit être 3×
plus rapide à monter que le 2e -- juste compose les briques.

Mission :
    Un target posé avant rally peut être rattrapé (cost dépasse target)
    ou la marge target-vs-cost peut devenir minime. Le monitor surface
    le signal à l'instant T du franchissement, SANS auto-recompute le
    target (cf [[L30]] anti-piège "cible figée + cost roulant").

Status enum :
    alive  : (target - cost) / cost >= _SEUIL_EDGE_DYING  (marge OK)
    dying  : 0 <= (target - cost) / cost < _SEUIL_EDGE_DYING  (marge mince)
    dead   : cost >= target  (target rattrapé ou dépassé)

Cost = BookLine.avg_cost_eur (PMP roulant fee-inclusive, source canonique).
Target = thesis.target_full convertie en EUR (via FX si native ≠ EUR) OU
         thesis.target_full_value si l'entrée native a été figée a la pose.

Transitions ACTIONABLES (notify) :
    alive_to_dying : "marge target se compresse, action humaine recommandée"
    dying_to_dead  : "target rattrapé, repenser la thèse"

Transitions OBSERVABLES (audit row seulement, pas notify) :
    dying_to_alive : repli OK (prix retombé), pas urgent
    dead_to_dying  : target re-dépassé un peu, observation
    dead_to_alive  : retour franc, observation
    alive_to_dead  : skip d'état (rare, large mouvement), notify quand même
    no_change      : routine

PAS de wire bias_events (différence vs kca/over_cap). Signal pur de
gouvernance des niveaux, pas anti-biais comportemental.

État DÉCOUPLÉ du cycle bias_events (cf L4) : prev_status lu depuis
stale_target_alerts (journal incrémental dédié), pas depuis bias_events
ou autre source. Garantit pas de re-fire spurieux.
"""
from __future__ import annotations

import logging
from typing import Any

from intelligence.bias_events import MissingDataError

log = logging.getLogger(__name__)

# Seuil edge pour passer d'alive a dying : (target - cost) / cost < 5%
_SEUIL_EDGE_DYING = 0.05
# Seuil divergence consensus pour flagger dans la notif (signal pur, pas
# changement de status). Olivier > consensus * 1.3 (ou < consensus * 0.77)
# = divergence materielle a mentionner. Aligne avec scoring methodologique
# 12/06 ou |delta| > 30% etait pris comme "explicitement variant".
_SEUIL_CONSENSUS_DIVERGENCE = 0.30


def _prev_status_for_stale_target(thesis_id: int) -> str:
    """Lit derniere row du journal stale_target_alerts. 'alive' par defaut
    si jamais evalue (cf doctrine : commencer la vie en bonne sante).
    DECOUPLE du cycle bias_events.resolved (cf L4)."""
    from shared import storage as _storage

    row = _storage.get_latest_stale_target_per_thesis(thesis_id)
    if not row:
        return "alive"
    return row["status"] or "alive"


def _classify_transition(prev: str, new: str) -> str:
    """Construit le label canonique de transition prev->new."""
    if prev == new:
        return "no_change"
    return f"{prev}_to_{new}"


def classify_thesis(
    thesis: dict,
    avg_cost_eur: float | None,
    target_eur: float | None,
) -> dict[str, Any] | None:
    """Source de vérité UNIQUE pour la classification stale_target.

    Distingue STRICTEMENT non-classifiable légitime vs donnée manquante :
    - Returns None si la thèse est non-classifiable LÉGITIMEMENT :
      pas de target défini (e.g. structural sans prix-target). Pas
      d'erreur, pas de fire, juste skip.
    - Raise MissingDataError si la thèse a un target mais que avg_cost_eur
      est None (cost réellement absent malgré une position ouverte =
      cassure de la cascade book→ledger_pmp, alerte legitimate).

    Args:
        thesis : row de theses (ticker, target_full, target_full_value, ...).
        avg_cost_eur : BookLine.avg_cost_eur (PMP roulant). None si pas de
            position (e.g. thèse active sans qty -> non-classifiable).
        target_eur : target en EUR. None si pas défini ou si conversion
            FX a échoué (la conversion se fait en amont par le caller).

    Returns:
        dict {thesis_id, ticker, status, cost_eur, target_eur, edge_pct}
            où edge_pct = (target - cost) / cost * 100 (signed).
        OR None si non-classifiable légitime (pas de target défini).

    Raises:
        MissingDataError : thesis a un target mais avg_cost_eur None.
    """
    if target_eur is None or target_eur <= 0:
        return None  # non-classifiable légitime
    if avg_cost_eur is None:
        raise MissingDataError(
            f"stale_target.classify_thesis {thesis.get('ticker', '?')} : "
            f"target_eur={target_eur} mais avg_cost_eur=None (cascade book "
            f"ou ledger_pmp cassée)"
        )
    if avg_cost_eur <= 0:
        raise MissingDataError(
            f"stale_target.classify_thesis {thesis.get('ticker', '?')} : "
            f"avg_cost_eur={avg_cost_eur} (<=0)"
        )

    edge_ratio = (target_eur - avg_cost_eur) / avg_cost_eur
    if edge_ratio < 0:
        status = "dead"
    elif edge_ratio < _SEUIL_EDGE_DYING:
        status = "dying"
    else:
        status = "alive"

    return {
        "thesis_id": int(thesis["id"]),
        "ticker": (thesis.get("ticker") or "").upper(),
        "status": status,
        "cost_eur": float(avg_cost_eur),
        "target_eur": float(target_eur),
        "edge_pct": float(edge_ratio * 100),
    }


def _resolve_target_eur(thesis: dict, fx_rate: float | None = None) -> float | None:
    """Récupère target_full converti en EUR. Prefere target_full_value (native
    si figé à la pose) + thesis.target_full_currency. Fallback target_full
    qui était historiquement EUR-implicite avant migration M1.

    Returns None si pas de target ou conversion FX impossible.
    """
    # Priorité 1 : target_full_value en native + currency (M1)
    tv = thesis.get("target_full_value")
    tc = (thesis.get("target_full_currency") or "EUR").upper()
    if tv is not None and tv > 0:
        if tc == "EUR":
            return float(tv)
        if fx_rate is not None and fx_rate > 0:
            return float(tv) * fx_rate
        # FX manquant -> non-classifiable cette evaluation (skip silent OK)
        return None
    # Priorité 2 (fallback legacy) : target_full plain
    tf = thesis.get("target_full")
    if tf is not None and tf > 0:
        return float(tf)
    return None


def check_all_stale_target_transitions() -> dict[str, Any]:
    """Pour chaque thèse active avec target défini, classify + transition + notify.

    Returns:
        dict {checked, alive, dying, dead, transitions, notified, errors}
    """
    from shared import book as _bk, notify as _notify, prices as _prices, storage as _storage

    stats: dict[str, Any] = {
        "checked": 0, "alive": 0, "dying": 0, "dead": 0,
        "transitions": 0, "notified": 0, "errors": 0,
        "consensus_divergent": 0,  # info pure, pas un status
    }

    # Charge actives theses + book index
    try:
        theses = _storage.active_theses() or []
    except Exception as e:
        log.warning(f"stale_target_monitor: active_theses failed: {e}")
        return stats

    try:
        book_index = _bk.get_book_index()
    except Exception as e:
        log.warning(f"stale_target_monitor: get_book_index failed: {e}")
        return stats

    for t in theses:
        try:
            stats["checked"] += 1
            thesis_id = int(t["id"])
            ticker = (t.get("ticker") or "").upper()

            # avg_cost_eur via BookLine (cascade book -> ledger_pmp)
            bl = book_index.get(ticker)
            avg_cost_eur = float(bl.avg_cost_eur) if (bl and bl.avg_cost_eur) else None

            # target_eur via helper (priorité native+fx, fallback legacy)
            fx_rate = float(bl.fx_rate_to_eur) if (bl and bl.fx_rate_to_eur) else None
            target_eur = _resolve_target_eur(t, fx_rate)

            try:
                cls = classify_thesis(t, avg_cost_eur, target_eur)
            except MissingDataError as md:
                log.warning(f"stale_target_monitor: {ticker} missing data: {md}")
                stats["errors"] += 1
                continue
            if cls is None:
                continue  # non-classifiable légitime (no target)

            new_status = cls["status"]
            stats[new_status] += 1
            prev_status = _prev_status_for_stale_target(thesis_id)
            transition = _classify_transition(prev_status, new_status)

            # Cross-check consensus (yfinance .info live)
            consensus_target: float | None = None
            consensus_n: int | None = None
            consensus_delta_pct: float | None = None
            try:
                cons = _prices.get_analyst_consensus(ticker)
                if cons and cons.get("target_mean") and cons.get("n_analysts"):
                    # consensus.target_mean en native currency du listing
                    # target Olivier (t.target_full) aussi en native (doctrine
                    # currency_native_invariant). On compare native vs native.
                    target_olv_native = float(t.get("target_full") or 0)
                    if target_olv_native > 0:
                        consensus_target = float(cons["target_mean"])
                        consensus_n = int(cons["n_analysts"])
                        consensus_delta_pct = (
                            target_olv_native / consensus_target - 1
                        ) * 100
                        if abs(consensus_delta_pct) > _SEUIL_CONSENSUS_DIVERGENCE * 100:
                            stats["consensus_divergent"] += 1
            except Exception as e:
                log.warning(f"stale_target consensus {ticker} failed: {e}")

            notified_flag = False
            # Transitions actionables (notify Telegram)
            actionable = {
                "alive_to_dying", "dying_to_dead", "alive_to_dead",
            }
            if transition in actionable:
                stats["transitions"] += 1
                try:
                    emoji = "⚠" if new_status == "dying" else "🔴"
                    consensus_line = ""
                    if consensus_target is not None and consensus_delta_pct is not None:
                        cons_dir = "BULL" if consensus_delta_pct > 0 else "BEAR"
                        flag = (
                            "  ⚠ divergent"
                            if abs(consensus_delta_pct) > _SEUIL_CONSENSUS_DIVERGENCE * 100
                            else "  aligne"
                        )
                        consensus_line = (
                            f"consensus: {consensus_target:.2f} (N={consensus_n}) "
                            f"-> delta {consensus_delta_pct:+.0f}% {cons_dir}{flag}\n"
                        )
                    msg = (
                        f"{emoji} STALE TARGET -- {ticker}\n"
                        f"status : {prev_status} -> {new_status}\n"
                        f"cost {cls['cost_eur']:.2f} EUR vs target {cls['target_eur']:.2f} EUR\n"
                        f"edge {cls['edge_pct']:+.1f}%\n"
                        f"{consensus_line}"
                        f"Action : repose le target (L30 anti-piege : "
                        f"humain decide, pas auto-recompute)"
                    )
                    _notify.send_text(msg, parse_mode=None)  # cf #146 cure
                    notified_flag = True
                    stats["notified"] += 1
                except Exception as e:
                    log.warning(f"stale_target notify {ticker} failed: {e}")
            elif transition != "no_change":
                # Transitions observables (audit row seulement, pas notify)
                stats["transitions"] += 1

            # Audit row à CHAQUE évaluation
            _storage.insert_stale_target_alert(
                thesis_id=thesis_id, ticker=ticker, status=new_status,
                cost_eur=cls["cost_eur"], target_eur=cls["target_eur"],
                edge_pct=cls["edge_pct"], notified=notified_flag,
                transition=transition,
                consensus_target=consensus_target,
                consensus_n=consensus_n,
                consensus_delta_pct=consensus_delta_pct,
            )
        except Exception as e:
            log.warning(
                f"stale_target_monitor: {t.get('ticker', '?')} failed: {e}"
            )
            stats["errors"] += 1
            continue

    return stats
