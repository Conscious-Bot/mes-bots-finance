"""Digues de concentration — ADR 015 §3 (défense en profondeur).

Ce module porte la Digue 1 (GEL comportemental) sur le **drawdown RÉALISÉ du book**
(equity vs HWM, fait objectif), JAMAIS `classify_regime`. Le bot ne trade pas :
gate + reco, exécution manuelle.

  - Digue 1 (gel_15, -15%) : gèle /position_buy (ajout/renfort refusé). Ne vend
    RIEN. Protocole de revue + cooldown avant déblocage (à implémenter — pour
    l'instant refus fail-closed avec message).
  - gel_25 (-25%) : vigilance renforcée, MÊME action (gel). Un seul gel gradué.
  - prorata_35 (-35% book) : gel maintenu + heads-up. NE déclenche PAS le prorata.

RÉCONCILIATION DES SIGNAUX (décision 04/07, point d'implémentation ouvert ADR §3) :
deux signaux, deux jobs. Le GEL (Digue 1, comportemental « arrête d'ajouter »)
utilise le DD BOOK (ici). Le PRORATA (Digue 2, frein de capital sur la
concentration) utilise le DD GRAPPE compute_ai (`risk/kill_switch.py`, cluster vs
pic 90j) — car un frein de concentration doit se déclencher sur la détresse de
concentration, pas sur une baisse book possiblement portée par le ballast. La
graduation vécue : book -15% stop-add → grappe -25% vigilance → grappe -35% prorata.
Le prorata est donc mono-déclencheur (kill_switch) ; ici prorata_35 (book) ne fait
que défèrer au kill_switch (à -35% book la grappe à 73% est quasi-sûrement en Stage 2).

Signal = portfolio_snapshots.drawdown_pct (déjà calculé vs HWM dans snapshot.py).
État actuel dormant tant que DD > -15% (conforme monitor_defaults : défaut dormant).

Pattern monitor canonique (docs/templates/monitor_pattern.md) adapté : objet =
LE book (portfolio-level, pas per-ticker), donc pas de wiring bias_events.
"""

from __future__ import annotations

import logging

from shared import storage

log = logging.getLogger(__name__)

# Seuils sur drawdown réalisé (négatif). ADR 015 §3.
GEL_15_PCT = -15.0
GEL_25_PCT = -25.0
PRORATA_35_PCT = -35.0

# Ordre de sévérité pour détecter escalade vs recovery.
_SEVERITY = {"normal": 0, "gel_15": 1, "gel_25": 2, "prorata_35": 3}


def classify_digue(drawdown_pct: float) -> str:
    """Source de vérité UNIQUE. drawdown_pct négatif = perte vs HWM.

    Pur, déterministe. Jamais None (tout drawdown est classifiable, même 0).
    """
    dd = float(drawdown_pct)
    if dd <= PRORATA_35_PCT:
        return "prorata_35"
    if dd <= GEL_25_PCT:
        return "gel_25"
    if dd <= GEL_15_PCT:
        return "gel_15"
    return "normal"


def is_frozen(status: str) -> bool:
    """Digue 1 : tout état gel_* ou prorata_* gèle les achats. normal = libre."""
    return status != "normal"


def is_prorata_armed(status: str) -> bool:
    """Digue 2 : prorata 20% armé uniquement à -35%."""
    return status == "prorata_35"


def _latest_drawdown() -> dict | None:
    """Lit le drawdown réalisé du dernier snapshot. None si aucun snapshot.

    Fail-OPEN par design : si le signal est indisponible, le caller (gate)
    NE gèle PAS (un trou de données ne doit pas bloquer le trading ni fabriquer
    un faux gel — cf L15 : ne pas inventer un état plus confiant que l'évidence).
    """
    try:
        with storage.db_ro() as cx:
            row = cx.execute(
                "SELECT snapshot_date, total_value_eur, hwm_value_eur, drawdown_pct "
                "FROM portfolio_snapshots "
                "WHERE drawdown_pct IS NOT NULL "
                "ORDER BY snapshot_date DESC LIMIT 1"
            ).fetchone()
    except Exception as e:
        log.warning("digue _latest_drawdown read failed: %s", e)
        return None
    if not row:
        return None
    return {
        "snapshot_date": row[0],
        "current_value_eur": float(row[1]) if row[1] is not None else None,
        "hwm_value_eur": float(row[2]) if row[2] is not None else None,
        "drawdown_pct": float(row[3]),
    }


def current_digue_state() -> dict:
    """État digue courant depuis le dernier snapshot. Fail-open si pas de signal.

    Returns {available, status, frozen, prorata_armed, drawdown_pct, ...}.
    available=False + status='normal' + frozen=False si signal indisponible.
    """
    dd = _latest_drawdown()
    if dd is None:
        return {
            "available": False,
            "status": "normal",
            "frozen": False,
            "prorata_armed": False,
            "drawdown_pct": None,
            "snapshot_date": None,
        }
    status = classify_digue(dd["drawdown_pct"])
    return {
        "available": True,
        "status": status,
        "frozen": is_frozen(status),
        "prorata_armed": is_prorata_armed(status),
        "drawdown_pct": dd["drawdown_pct"],
        "hwm_value_eur": dd["hwm_value_eur"],
        "current_value_eur": dd["current_value_eur"],
        "snapshot_date": dd["snapshot_date"],
    }


def _prev_status() -> str:
    """Dernière row du journal digue. Default 'normal' si jamais évalué."""
    row = storage.get_latest_digue_alert()
    return row["status"] if row else "normal"


def _transition(prev: str, new: str) -> str:
    """escalation (aggravation) / recovery (amélioration) / no_change."""
    p, n = _SEVERITY.get(prev, 0), _SEVERITY.get(new, 0)
    if n > p:
        return "escalation"
    if n < p:
        return "recovery"
    return "no_change"


_LABELS = {
    "gel_15": "🟠 DIGUE 1 — GEL (-15%)",
    "gel_25": "🔴 VIGILANCE RENFORCÉE (-25%)",
    "prorata_35": "⛔ DIGUE 2 — PRORATA 20% (-35%)",
    "normal": "✓ normal",
}


def check_digue_transition() -> dict:
    """Évalue l'état digue, journalise, notifie sur transition (escalade/recovery).

    Append une row à CHAQUE évaluation (no_change inclus). Notify seulement sur
    vraie transition. Returns stats dict.
    """
    stats = {"status": None, "transition": None, "notified": False, "drawdown_pct": None}
    state = current_digue_state()
    if not state["available"]:
        log.info("digue: signal indisponible (pas de snapshot) — skip")
        return stats

    new_status = state["status"]
    prev_status = _prev_status()
    transition = _transition(prev_status, new_status)
    stats["status"] = new_status
    stats["transition"] = transition
    stats["drawdown_pct"] = state["drawdown_pct"]

    notified = False
    if transition in ("escalation", "recovery"):
        try:
            from shared import notify

            arrow = "aggravation" if transition == "escalation" else "amélioration"
            body = (
                f"*Digue concentration ADR 015* — {arrow}\n"
                f"{_LABELS.get(prev_status, prev_status)} → "
                f"{_LABELS.get(new_status, new_status)}\n\n"
                f"Drawdown réalisé : {state['drawdown_pct']:+.1f}% "
                f"(book {state['current_value_eur']:,.0f} € vs HWM "
                f"{state['hwm_value_eur']:,.0f} €, {state['snapshot_date']})\n"
            )
            if is_frozen(new_status):
                body += "\n🚫 /position_buy GELÉ (ajout/renfort refusé). Ne vend rien."
            if is_prorata_armed(new_status):
                # Réconciliation des signaux (décision 04/07) : le PRORATA (Digue 2)
                # est un frein de CONCENTRATION → déclenché par le DD GRAPPE
                # (kill_switch, cluster compute_ai), PAS par le DD book. À -35% book
                # la grappe (73% du book) est quasi-certainement en Stage 2 aussi ;
                # la digue défère donc au kill_switch pour le prorata chiffré, elle
                # ne calcule pas un 2e prorata book-side. Ici : heads-up + gel maintenu.
                body += (
                    "\n⛔ Book DD -35%+ : gel maintenu. Le PRORATA 20% (Digue 2) se "
                    "déclenche sur le DD de la grappe compute_ai via le kill_switch — "
                    "plan chiffré exact dans /kill_exec quand Stage 2 grappe s'arme."
                )
            if new_status == "normal":
                body += "\n✓ Digues levées — /position_buy de nouveau autorisé."
            notify.send_text(body)
            notified = True
        except Exception as e:
            log.warning("digue notify failed: %s", e)

    storage.insert_digue_alert(
        status=new_status,
        drawdown_pct=state["drawdown_pct"],
        hwm_value_eur=state.get("hwm_value_eur"),
        current_value_eur=state.get("current_value_eur"),
        snapshot_date=state.get("snapshot_date"),
        notified=notified,
        transition=transition,
    )
    stats["notified"] = notified
    log.info("digue check: dd=%.1f%% status=%s transition=%s", state["drawdown_pct"], new_status, transition)
    return stats


if __name__ == "__main__":
    st = current_digue_state()
    print(f"digue state: {st}")
