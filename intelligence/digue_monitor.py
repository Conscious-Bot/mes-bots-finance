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

import contextlib
import logging
from datetime import UTC, date, datetime, timedelta

from shared import storage

log = logging.getLogger(__name__)

# Override Digue 1 (ADR 015 §3) : déblocage JAMAIS un simple clic. Requiert le
# cooldown incompressible écoulé ET une justification substantielle (le protocole
# de revue écrit). Pattern emprunté au kill_switch override (min_chars + substance).
DIGUE_COOLDOWN_DAYS = 2  # le gel tient AU MOINS ce délai, incompressible
DIGUE_OVERRIDE_VALID_DAYS = 3  # une fois accordé, l'override lève le gel ce délai
DIGUE_OVERRIDE_MIN_CHARS = 40

# Seuils sur drawdown réalisé (négatif). ADR 015 §3.
GEL_15_PCT = -15.0
GEL_25_PCT = -25.0
PRORATA_35_PCT = -35.0

# Un snapshot plus vieux que ça n'est plus un signal : indisponible (fail-open,
# pas de gel sur donnée fossile). Le pipeline snapshot est daily — 7j = cassé.
# Volontairement plus long que kill_switch.snapshot_max_age_days=3 : le gel est
# comportemental et fail-open (ne vend rien, ne prescrit rien), le kill_switch
# PRESCRIT une vente → il exige une fraîcheur plus stricte.
DIGUE_STALE_AFTER_DAYS = 7

# Tolérance reader ALIGNÉE sur le writer (revue 04/07) : snapshot.aggregate écrit
# une row avec ≤2% du coût unpriced (1-2 petites lignes max). Un reader strict
# n_priced==n_positions rendrait ces rows quasi-exactes invisibles → staleness
# artificielle → digue aveugle en silence (corridor de désarmement). Gap >2 =
# row anormale (pré-gate ou pipeline cassé) → exclue.
DIGUE_MAX_UNPRICED_GAP = 2

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



# ── HWM CANONIQUE (rewire 04/08/2026 — ferme le fork L1 snapshot vs reconstruction) ──
# Ancre arbitrée dans config/policy.yaml (drawdown_ladder.HWM_ANCHOR) ; le HWM
# vivant = max(ancre, snapshots POSTÉRIEURS à l'ancre). Rolling max auto-entretenu
# par la table portfolio_snapshots existante — aucun nouvel état, aucun cache.
# Le champ hwm_value_eur des rows (rolling legacy, porte le 60 258 intraday)
# n'est PLUS consommé ici. KNOWN-GAP: le writer snapshot.aggregate continue de
# l'écrire pour compat append-only — lecteur et écrivain divergent sciemment,
# documenté, jusqu'à retrait du champ côté writer.

def _hwm_anchor() -> tuple[float, str] | None:
    """Lit l'ancre depuis policy.yaml. None si illisible (JAMAIS un défaut inventé)."""
    try:
        from pathlib import Path

        import yaml
        pol = Path(__file__).resolve().parent.parent / "config" / "policy.yaml"
        d = yaml.safe_load(pol.read_text(encoding="utf-8"))
        a = d["drawdown_ladder"]["HWM_ANCHOR"]
        return float(a["value_eur"]), str(a["date"])
    except Exception as e:  # ancre illisible → le caller retombe en legacy BRUYAMMENT
        log.error("digue: HWM_ANCHOR illisible dans policy.yaml (%s) — "
                  "fallback legacy hwm_value_eur, fork L1 ROUVERT", e)
        return None


def canonical_hwm() -> dict | None:
    """HWM canonique = max(ancre policy, snapshots complets POSTÉRIEURS à l'ancre).

    SOURCE UNIQUE (L1) du HWM — digest, dashboard et gates lisent CE résultat
    via _latest_drawdown/current_digue_state. Retour None si l'ancre est
    illisible (le caller décide du fallback, bruyamment).
    """
    anchor = _hwm_anchor()
    if anchor is None:
        return None
    anchor_val, anchor_date = anchor
    post_max = None
    try:
        with storage.db_ro() as cx:
            row = cx.execute(
                "SELECT MAX(total_value_eur) FROM portfolio_snapshots "
                "WHERE snapshot_date > ? AND (n_positions - n_priced) <= ?",
                (anchor_date, DIGUE_MAX_UNPRICED_GAP),
            ).fetchone()
        post_max = float(row[0]) if row and row[0] is not None else None
    except Exception as e:
        log.warning("digue: lecture post-anchor max échouée (%s) — ancre seule", e)
    if post_max is not None and post_max > anchor_val:
        return {"hwm_eur": post_max, "hwm_source": "post_anchor_snapshot"}
    return {"hwm_eur": anchor_val, "hwm_source": f"anchor_{anchor_date}"}


def _latest_drawdown() -> dict | None:
    """Lit le drawdown réalisé du dernier snapshot COMPLET et FRAIS. None sinon.

    Fail-OPEN par design : si le signal est indisponible, le caller (gate)
    NE gèle PAS (un trou de données ne doit pas bloquer le trading ni fabriquer
    un faux gel — cf L15 : ne pas inventer un état plus confiant que l'évidence).

    Deux gardes d'honnêteté (04/07/2026, classe « agrégat partiel ≠ total ») :
    - gap unpriced borné : une row franchement partielle (throttle yfinance,
      pipeline cassé) compare un total tronqué au HWM book-complet → drawdown
      fabriqué. On la saute. Les rows writer-tolérées (gap ≤ DIGUE_MAX_UNPRICED_GAP,
      biais ≤2% du coût par construction de MIN_COST_COVERAGE) restent consommées.
    - staleness : au-delà de DIGUE_STALE_AFTER_DAYS le signal est indisponible,
      pas « le dernier connu » — un gel/dégel ne se décide pas sur du fossile.
    """
    try:
        with storage.db_ro() as cx:
            row = cx.execute(
                "SELECT snapshot_date, total_value_eur, hwm_value_eur, drawdown_pct "
                "FROM portfolio_snapshots "
                "WHERE drawdown_pct IS NOT NULL "
                "  AND (n_positions - n_priced) <= ? "
                "ORDER BY snapshot_date DESC LIMIT 1",
                (DIGUE_MAX_UNPRICED_GAP,),
            ).fetchone()
    except Exception as e:
        log.warning("digue _latest_drawdown read failed: %s", e)
        return None
    if not row:
        return None
    try:
        age_days = (datetime.now(UTC).date() - date.fromisoformat(str(row[0]))).days
    except (TypeError, ValueError):
        age_days = None
    if age_days is None or age_days > DIGUE_STALE_AFTER_DAYS:
        log.warning(
            "digue: dernier snapshot complet %s trop vieux (%sj > %dj) — "
            "signal indisponible (fail-open)",
            row[0], age_days, DIGUE_STALE_AFTER_DAYS,
        )
        return None
    current = float(row[1]) if row[1] is not None else None
    # ── REWIRE 04/08 : DD recalculé contre le HWM CANONIQUE, pas le rolling
    # legacy de la row (qui fige le 60 258 intraday pour toujours).
    canon = canonical_hwm()
    if canon is not None and current is not None and canon["hwm_eur"] > 0:
        return {
            "snapshot_date": row[0],
            "current_value_eur": current,
            "hwm_value_eur": canon["hwm_eur"],
            "hwm_source": canon["hwm_source"],
            "drawdown_pct": (current / canon["hwm_eur"] - 1.0) * 100.0,
        }
    # Fallback legacy BRUYANT (ancre illisible) — jamais silencieux (L15).
    log.error("digue: HWM canonique indisponible — drawdown calculé sur le "
              "rolling LEGACY de la row (fork L1 actif)")
    return {
        "snapshot_date": row[0],
        "current_value_eur": current,
        "hwm_value_eur": float(row[2]) if row[2] is not None else None,
        "hwm_source": "legacy_snapshot_rolling",
        "drawdown_pct": float(row[3]),
    }


def current_digue_state() -> dict:
    """État digue courant depuis le dernier snapshot. Fail-open si pas de signal.

    Returns {available, status, frozen, prorata_armed, drawdown_pct, ...}.
    available=False + status='normal' + frozen=False si signal indisponible.

    EXCEPTION gel actif (revue 04/07) : le fail-open ne CRÉE pas de gel sur
    donnée absente — mais il ne DISSOUT pas non plus un gel déjà journalisé.
    La dernière évidence disait gel ; ré-autoriser les achats sur signal perdu
    serait aussi une décision prise sur donnée absente (L21), et casserait le
    « jamais un clic » (une panne de pipeline deviendrait moins chère que le
    protocole override). Déblocage d'un gel-hold = /digue_override normal
    (cooldown + protocole), ou retour du signal.
    """
    dd = _latest_drawdown()
    if dd is None:
        last = _prev_status()
        if is_frozen(last):
            return {
                "available": False,
                "status": last,
                "frozen": True,
                "prorata_armed": False,  # jamais d'armement prorata sur donnée absente
                "drawdown_pct": None,
                "snapshot_date": None,
                "signal_stale_hold": True,
            }
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


def _notify_blindness_once(state: dict) -> None:
    """Telegram UNE fois par épisode d'aveuglement (flag state), pas par run.

    L'aveuglement digue doit être VISIBLE (revue 04/07) : sans ça, un pipeline
    snapshot cassé désarme/suspend la digue pendant que tous les monitors sont
    verts. Flag posé seulement si le notify part (sinon retente au prochain run).
    """
    if storage.load_state().get("digue_stale_notified"):
        return
    if not state.get("signal_stale_hold") and storage.get_latest_digue_alert() is None:
        # Monitor jamais évalué (fresh install / DB neuve) : rien n'a été « perdu »,
        # pas d'alerte d'aveuglement pour un signal qui n'a jamais existé.
        return
    try:
        from shared import notify

        if state.get("signal_stale_hold"):
            body = (
                "⚠️ *Digue ADR 015 — signal AVEUGLE, gel MAINTENU*\n"
                f"Snapshots book partiels/stale ({DIGUE_STALE_AFTER_DAYS}j+). "
                f"Dernière évidence = {_LABELS.get(state['status'], state['status'])} "
                "→ le gel tient (pas de dégel sur donnée absente).\n"
                "Déblocage = `/digue_override` (cooldown + protocole) ou retour du signal.\n"
                "Cause probable : voir scheduler_runs (snapshot FAIL) / yfinance."
            )
        else:
            body = (
                "⚠️ *Digue ADR 015 — signal AVEUGLE (fail-open)*\n"
                f"Aucun snapshot book complet et frais ({DIGUE_STALE_AFTER_DAYS}j). "
                "La digue ne peut plus détecter un franchissement −15% tant que le "
                "pipeline snapshot ne repart pas (voir scheduler_runs)."
            )
        notify.send_text(body, parse_mode="Markdown")
    except Exception as e:
        log.warning("digue blindness notify failed: %s", e)
        return
    storage.update_state(digue_stale_notified=datetime.now(UTC).isoformat())


def _clear_blindness_flag(new_status: str) -> None:
    """Signal revenu : lève le flag + heads-up symétrique (si on avait alerté)."""
    if not storage.load_state().get("digue_stale_notified"):
        return
    storage.update_state(digue_stale_notified=None)
    with contextlib.suppress(Exception):
        from shared import notify

        notify.send_text(
            f"✓ Signal digue rétabli — état {_LABELS.get(new_status, new_status)}."
        )


def check_digue_transition() -> dict:
    """Évalue l'état digue, journalise, notifie sur transition (escalade/recovery).

    Append une row à CHAQUE évaluation (no_change inclus). Notify seulement sur
    vraie transition. Returns stats dict. Signal indisponible → pas de row
    (le schéma journal exige un drawdown réel), mais notify-once d'aveuglement.
    """
    stats = {"status": None, "transition": None, "notified": False, "drawdown_pct": None}
    state = current_digue_state()
    if not state["available"]:
        _notify_blindness_once(state)
        log.info(
            "digue: signal indisponible — skip (gel_hold=%s)",
            bool(state.get("signal_stale_hold")),
        )
        return stats
    _clear_blindness_flag(state["status"])

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

    # Épisode de gel (pour le cooldown incompressible de l'override) : stampe le
    # début à l'ENTRÉE dans le gel (normal→frozen), efface au retour normal (+ purge
    # l'override devenu sans objet).
    if prev_status == "normal" and is_frozen(new_status):
        storage.update_state(digue_gel_started_at=datetime.now(UTC).isoformat())
    elif new_status == "normal":
        storage.update_state(digue_gel_started_at=None, digue_override=None)

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


# ───────────────────────────────────────────── override Digue 1 (déblocage)


def _active_override() -> dict | None:
    """Override en cours et non expiré, ou None."""
    ov = storage.load_state().get("digue_override")
    if not ov:
        return None
    try:
        if datetime.fromisoformat(ov["expires_at"]) <= datetime.now(UTC):
            return None
    except Exception:
        return None
    return ov


def _gel_cooldown_remaining_days() -> int | None:
    """Jours de cooldown incompressible restants, ou None si pas de gel stampé."""
    started = storage.load_state().get("digue_gel_started_at")
    if not started:
        return None
    try:
        elapsed = (datetime.now(UTC) - datetime.fromisoformat(started)).days
    except Exception:
        return None
    return max(0, DIGUE_COOLDOWN_DAYS - elapsed)


def gate_allows_buy() -> tuple[bool, str]:
    """Décision du gate d'achat Digue 1. (allow, message). Fail-OPEN si signal absent.

    Bloque si gel actif SANS override valide. Un override exige cooldown écoulé +
    justification (cf grant_override) — jamais un simple clic.
    """
    st = current_digue_state()
    if not st["frozen"]:
        return True, ""
    if st.get("drawdown_pct") is not None:
        dd_txt = f"DD réalisé {st['drawdown_pct']:+.1f}% (état {st['status']})"
    else:
        dd_txt = (
            f"signal drawdown INDISPONIBLE (snapshot partiel/stale) — gel MAINTENU "
            f"sur dernière évidence ({st['status']})"
        )
    if _active_override() is not None:
        ov = _active_override()
        return True, (
            f"⚠ Achat sous OVERRIDE Digue 1 (expire {ov['expires_at'][:10]}). {dd_txt}."
        )
    rem = _gel_cooldown_remaining_days()
    if rem and rem > 0:
        cd = f" Cooldown incompressible : {rem}j restants avant tout déblocage."
    else:
        cd = " Cooldown écoulé — `/digue_override <protocole de revue ≥40 car.>` pour débloquer."
    return False, (
        f"🚫 Achat GELÉ — Digue 1 ADR 015. {dd_txt}. "
        f"Gèle ajout/renfort, ne vend rien.{cd}"
    )


def grant_override(text: str) -> tuple[bool, str]:
    """Accorde l'override Digue 1 si cooldown écoulé ET justification substantielle.

    Le texte DOIT être le protocole de revue écrit (thèses relues, sentinelles
    S4/S5, inflation de conviction, constat de régime) — pas un accusé de réception.
    """
    st = current_digue_state()
    if not st["frozen"]:
        return False, "Aucun gel actif — rien à outrepasser."
    text = (text or "").strip()
    if len(text) < DIGUE_OVERRIDE_MIN_CHARS:
        return False, (
            f"Justification trop courte ({len(text)}<{DIGUE_OVERRIDE_MIN_CHARS}). "
            "Écris le protocole de revue : thèses du cluster relues, état sentinelles "
            "S4/S5, métrique d'inflation de conviction, constat de régime."
        )
    rem = _gel_cooldown_remaining_days()
    if rem and rem > 0:
        return False, (
            f"Cooldown incompressible : {rem}j restants. Le gel doit tenir "
            f"{DIGUE_COOLDOWN_DAYS}j avant tout déblocage — pas un clic, même justifié."
        )
    now = datetime.now(UTC)
    ov = {
        "granted_at": now.isoformat(),
        "expires_at": (now + timedelta(days=DIGUE_OVERRIDE_VALID_DAYS)).isoformat(),
        "text": text,
    }
    storage.update_state(digue_override=ov)
    with contextlib.suppress(Exception):
        storage.log_event("digue_override_granted", {"dd_pct": st["drawdown_pct"], "text": text})
    return True, (
        f"Override Digue 1 accordé {DIGUE_OVERRIDE_VALID_DAYS}j (jusqu'au "
        f"{ov['expires_at'][:10]}). /position_buy ré-autorisé. Protocole loggé."
    )


async def cmd_digue_override(update, ctx):
    """`/digue_override <protocole de revue>` — lève le gel Digue 1 (cooldown + substance)."""
    text = " ".join(ctx.args) if getattr(ctx, "args", None) else ""
    ok, msg = grant_override(text)
    await update.message.reply_text(("✅ " if ok else "🚫 ") + msg)


if __name__ == "__main__":
    st = current_digue_state()
    print(f"digue state: {st}")
