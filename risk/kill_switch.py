"""Kill-condition disjoncteur for the AI-compute cluster.

Implémente la BRANCHE PRIX P1 de la doctrine
[[Kill-condition — disjoncteur de la grappe AI-compute]] (vault PRESAGE, 26/06).

Sur un franchissement frais de seuil → un message Telegram dédié par trigger,
qui force une réponse structurée (exécuter ou override falsifiable+daté).
L'inaction silencieuse devient impossible à trois endroits :
- push non sollicité (tu ne peux pas ne pas voir)
- réponse structurée (tu ne peux pas accuser réception sans trancher)
- falsification datée (tu ne peux pas te défausser sans t'engager)

Exports principaux :
- snapshot_cluster_value()   daily cron : record cluster aggregate EUR value
- check_and_fire()           cron : detect crossings, fire TG, manage episode
- escalate_unresolved()      daily cron : re-push unresolved + re-prompt due overrides
- validate_override(text)    enforce falsifiable+dated override
- cmd_kill_exec / cmd_kill_override / cmd_kill_resolve   Telegram handlers

Doctrine : vault PRESAGE > "Kill-condition — disjoncteur de la grappe AI-compute" V3.
Choix figés (26/06) : reduce=-25%, stop=-35%, fenêtre 90j glissant, override_failure_policy=re_arm.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime
from typing import Any

from shared import config, notify, prices, storage

logger = logging.getLogger(__name__)


def _cfg() -> dict[str, Any]:
    """Lire le bloc kill_switch de config.yaml (re-lu à chaque appel pour hot-reload)."""
    return config.get().get("kill_switch", {})


STAGE_LABELS: dict[int, str] = {
    1: "VIGILANCE — gel (zéro ajout)",
    2: "DÉ-RISQUE — trim partiel mécanique vers le plancher-cap",
    3: "THÈSE CASSÉE — sortie au plancher/ballast",
}
STAGE_ACTION: dict[int, str] = {
    1: "geler la grappe (aucun nouvel ajout) + écrire la réévaluation datée",
    2: "exécuter le trim partiel — lignes plus-corrélées / plus-basse-conviction d'abord",
    3: "sortir la grappe vers l'allocation plancher",
}

_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _today() -> date:
    return datetime.now(UTC).date()


# ───────────────────────────────────────────────────────── cluster value


def _cluster_membership() -> set[str]:
    """Récupère la liste des tickers de la grappe AI-compute.

    Priorité (27/06/2026 — Phase 4 unification 5 sources → 1) :
    1. cluster_source: 'taxonomy_ai_capex_held' → dérivation depuis le mapping
       unique (presage_taxonomy.yaml driver=ai_capex sur held). Avant retour,
       assertion held-scopée vs config.yaml cluster_compute_ai (fail-closed).
    2. cluster_source: 'compute_ai_cluster' → lecture directe de
       concentration.clusters.compute_ai (chemin legacy avant Phase 4).
    3. cluster_tickers explicite → fallback statique.
    4. cluster_narrative → lookup via theses (deprecated).

    Raise ConfigurationError si rien défini.
    Raise TaxonomyError si source='taxonomy_ai_capex_held' ET divergence vs B.
    """
    cfg = _cfg()
    source = cfg.get("cluster_source")
    if source == "taxonomy_ai_capex_held":
        # Phase 4 — source canonique unique. Assertion held-scopée AVANT retour
        # garantit que B (config.yaml) et mapping s'accordent sur le détenu.
        from shared import taxonomy

        taxonomy.assert_held_cluster_consistency()  # raise sinon
        return {tk.upper() for tk in taxonomy.by_driver("ai_capex", "held")}
    if source == "compute_ai_cluster":
        full = config.get()
        canon = (full.get("concentration", {}).get("clusters", {}).get("compute_ai") or [])
        if canon:
            return {str(t).upper() for t in canon}
    tickers = cfg.get("cluster_tickers")
    if tickers:
        return {str(t).upper() for t in tickers}
    narrative = cfg.get("cluster_narrative")
    if narrative:
        with storage.db() as conn:
            rows = conn.execute(
                "SELECT DISTINCT ticker FROM theses WHERE status='active' "
                "AND notes LIKE ?",
                (f"%narrative={narrative}%",),
            ).fetchall()
            return {str(r[0]).upper() for r in rows}
    raise config.ConfigurationError(
        "kill_switch: ni cluster_source ni cluster_tickers ni cluster_narrative défini"
    )


def compute_cluster_value_eur() -> float:
    """Aggregate live EUR value de la grappe AI-compute.

    Réutilise le cache prix (_PX_TTL) → zéro charge yfinance additionnelle.
    Tickers absents de price cache sont log.warning et exclus du calcul.
    """
    cluster = _cluster_membership()
    total = 0.0
    missing: list[str] = []
    for pos in storage.get_open_positions():
        ticker = str(pos.get("ticker", "")).upper()
        if ticker not in cluster:
            continue
        px = prices.get_current_price_in_eur(ticker)
        if px is None:
            missing.append(ticker)
            continue
        try:
            qty = float(pos.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        total += px * qty
    if missing:
        logger.warning("kill_switch: prix EUR manquant pour %s, exclus du calcul grappe", missing)
    return total


def snapshot_cluster_value() -> None:
    """Daily cron : record un snapshot daily de la valeur agrégée EUR."""
    value = compute_cluster_value_eur()
    storage.record_cluster_snapshot(_today().isoformat(), value)
    logger.info("kill_switch: snapshot grappe %.0f EUR", value)


# ───────────────────────────────────────────────────── drawdown / stage


def compute_drawdown() -> tuple[float, float, float] | None:
    """Return (current_value, peak_value, drawdown_pct≤0) ou None si pas de data.

    Early on (history < window) : peak ≈ current → drawdown ~0 → pas de false trigger.
    Forward-only by construction.
    """
    window = int(_cfg().get("peak_window_days", 90))
    latest = storage.get_latest_cluster_snapshot()
    if latest is None:
        return None
    peak = storage.get_cluster_peak(window)
    if peak is None or peak <= 0:
        return None
    cur = float(latest["value_eur"])
    return cur, peak, (cur - peak) / peak


def stage_for_drawdown(dd_pct: float) -> int:
    """0=normal, 1=vigilance (reduce), 2=derisque (stop), 3=hard (si activé)."""
    cfg = _cfg()
    reduce_pct = float(cfg.get("drawdown_reduce_pct", 0.25))
    stop_pct = float(cfg.get("drawdown_stop_pct", 0.35))
    hard = cfg.get("drawdown_hard_pct")
    loss = -dd_pct
    if hard is not None and loss >= float(hard):
        return 3
    if loss >= stop_pct:
        return 2
    if loss >= reduce_pct:
        return 1
    return 0


# ───────────────────────────────────────────────────────── fire / episode


def check_and_fire() -> None:
    """Cron : fire UN message TG dédié par escalation fraîche de stage.

    Anti-spam via épisode (state store JSON). Un trigger = un message =
    une résolution traçable.
    """
    if not _cfg().get("enabled", False):
        return
    dd = compute_drawdown()
    if dd is None:
        return
    cur, peak, dd_pct = dd
    stage = stage_for_drawdown(dd_pct)
    ep = storage.get_kill_episode_state()

    if stage == 0:
        if ep["open"]:
            storage.set_kill_episode_state(
                {"open": False, "worst_stage": 0, "episode_id": ep["episode_id"]}
            )
            logger.info("kill_switch: grappe rétablie (dd %.1f%%), épisode clos", dd_pct * 100)
        return

    if not ep["open"]:
        ep = {"open": True, "worst_stage": 0, "episode_id": int(ep["episode_id"]) + 1}

    if stage > ep["worst_stage"]:
        tid = storage.insert_kill_trigger(
            trigger_type="p1_drawdown",
            episode_id=ep["episode_id"],
            stage=stage,
            level_measured=round(dd_pct, 4),
            prescribed_action=STAGE_ACTION[stage],
            status="unresolved",
            created_at=_now_iso(),
        )
        _push_trigger(tid, stage, dd_pct, cur, peak, escalation=False)
        ep["worst_stage"] = stage
        logger.info("kill_switch: trigger #%d stage %d (dd %.1f%%)", tid, stage, dd_pct * 100)

    storage.set_kill_episode_state(ep)


def _push_trigger(
    tid: int, stage: int, dd_pct: float, cur: float, peak: float, *, escalation: bool
) -> None:
    """Push TG dédié au franchissement (ou reminder si escalation=True)."""
    prefix = "🔴 *RAPPEL — KILL-CONDITION*" if escalation else "🔴 *KILL-CONDITION*"
    msg = (
        f"{prefix} — grappe AI-compute\n\n"
        f"Drawdown *{dd_pct * 100:.1f}%* depuis le pic 90j "
        f"({cur:,.0f}€ vs pic {peak:,.0f}€)\n"
        f"Palier *Stage {stage}* — {STAGE_LABELS[stage]}\n\n"
        f"Action prescrite : {STAGE_ACTION[stage]}\n\n"
        f"Deux issues — pas d'accusé de réception vide :\n"
        f"• exécuter → `/kill_exec {tid}`\n"
        f"• tenir quand même → `/kill_override {tid} <raison + condition de falsification + date AAAA-MM-JJ>`\n\n"
        f"_Override sans condition datée = refusé._"
    )
    try:
        notify.send_text(msg, parse_mode="Markdown")
    except Exception as e:
        logger.warning("kill_switch: TG send failed for trigger %d: %s", tid, e)


def escalate_unresolved() -> None:
    """Daily cron : re-push unresolved triggers + re-prompt due overrides."""
    if not _cfg().get("enabled", False):
        return
    dd = compute_drawdown()
    cur, peak, dd_pct = dd if dd else (0.0, 0.0, 0.0)

    for t in storage.get_kill_triggers_by_status("unresolved"):
        level = dd_pct if dd else float(t["level_measured"])
        _push_trigger(t["id"], t["stage"], level, cur, peak, escalation=True)

    today = _today()
    for t in storage.get_kill_triggers_by_status("override_active"):
        due = t.get("override_falsification_date")
        if due and date.fromisoformat(due) <= today:
            _prompt_override_due(t)


def _prompt_override_due(t: dict[str, Any]) -> None:
    """À l'échéance d'un override : demande check + bascule statut → override_due."""
    msg = (
        f"🟠 *OVERRIDE À ÉCHÉANCE* — trigger #{t['id']}\n\n"
        f"Ta raison de tenir : {t.get('override_text', '')}\n"
        f"Falsification datée au {t.get('override_falsification_date')}.\n\n"
        f"S'est-elle réalisée ?\n"
        f"• oui, j'avais tort → `/kill_resolve {t['id']} wrong`\n"
        f"• non, la thèse tient → `/kill_resolve {t['id']} holds`"
    )
    try:
        notify.send_text(msg, parse_mode="Markdown")
    except Exception as e:
        logger.warning("kill_switch: TG override expiry send failed for #%d: %s", t["id"], e)
    storage.update_kill_trigger(t["id"], status="override_due")


# ──────────────────────────────────────────────────── override validation


def validate_override(text: str) -> tuple[bool, str | None, str]:
    """Enforce falsifiable + dated override.

    Returns (ok, falsification_date_iso, reason).
    Règles :
    - text strip().length >= override_min_chars (config)
    - contient une date ISO YYYY-MM-DD
    - date dans le futur strict (> today UTC)
    """
    cfg = _cfg()
    min_chars = int(cfg.get("override_min_chars", 40))
    text = text.strip()
    if len(text) < min_chars:
        return False, None, (
            f"Override trop court ({len(text)}<{min_chars}). Écris la thèse précise + "
            f"la condition observable qui te donnerait tort + une date AAAA-MM-JJ."
        )
    m = _ISO_DATE_RE.search(text)
    if not m:
        return False, None, (
            "Refusé : aucune date de falsification (AAAA-MM-JJ). Sans date, ce n'est pas "
            "une prédiction falsifiable — c'est une dérobade."
        )
    try:
        fdate = date.fromisoformat(m.group(1))
    except ValueError:
        return False, None, "Date invalide (AAAA-MM-JJ)."
    if fdate <= _today():
        return False, None, "La date de falsification doit être dans le futur."
    return True, fdate.isoformat(), "ok"


# ────────────────────────────────────────────────── Telegram handlers
# python-telegram-bot v21 async API. ARG001 (update, ctx) ignored by repo convention.


async def cmd_kill_exec(update, ctx):
    """`/kill_exec <trigger_id>` — confirme exécution. Chemin par défaut, sans friction."""
    if not ctx.args:
        await update.message.reply_text("Usage : /kill_exec <trigger_id>")
        return
    try:
        tid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("trigger_id invalide.")
        return
    t = storage.get_kill_trigger(tid)
    if t is None:
        await update.message.reply_text(f"Trigger #{tid} introuvable.")
        return
    storage.update_kill_trigger(tid, status="executed", resolved_at=_now_iso())
    await update.message.reply_text(
        f"✅ Trigger #{tid} marqué *exécuté* (Stage {t['stage']}). "
        f"Exécute le trim chez ton courtier — le statut est loggé.",
        parse_mode="Markdown",
    )


async def cmd_kill_override(update, ctx):
    """`/kill_override <trigger_id> <texte>` — override falsifiable+daté ou refus."""
    if len(ctx.args) < 2:
        await update.message.reply_text(
            "Usage : /kill_override <trigger_id> <raison + condition falsifiable + date AAAA-MM-JJ>"
        )
        return
    try:
        tid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("trigger_id invalide.")
        return
    t = storage.get_kill_trigger(tid)
    if t is None:
        await update.message.reply_text(f"Trigger #{tid} introuvable.")
        return
    text = " ".join(ctx.args[1:])
    ok, fdate, reason = validate_override(text)
    if not ok:
        # statut reste 'unresolved' → re-push demain via escalate_unresolved
        await update.message.reply_text(f"❌ {reason}")
        return
    storage.update_kill_trigger(
        tid,
        status="override_active",
        override_text=text,
        override_falsification_date=fdate,
        resolved_at=_now_iso(),
    )
    await update.message.reply_text(
        f"📝 Override enregistré sur #{tid}. Falsification au *{fdate}* — "
        f"le bot te redemandera à cette date.",
        parse_mode="Markdown",
    )


async def cmd_kill_resolve(update, ctx):
    """`/kill_resolve <trigger_id> wrong|holds` — résolution override à échéance."""
    if len(ctx.args) < 2 or ctx.args[1] not in ("wrong", "holds"):
        await update.message.reply_text("Usage : /kill_resolve <trigger_id> wrong|holds")
        return
    try:
        tid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("trigger_id invalide.")
        return
    t = storage.get_kill_trigger(tid)
    if t is None:
        await update.message.reply_text(f"Trigger #{tid} introuvable.")
        return
    if ctx.args[1] == "holds":
        storage.update_kill_trigger(tid, status="override_correct", resolved_at=_now_iso())
        await update.message.reply_text(
            f"✅ #{tid} : override tenu. Loggé comme prédiction correcte "
            f"(preuve datée que l'instinct était juste *cette fois*)."
        )
        return
    # wrong → failed override → applique override_failure_policy
    storage.update_kill_trigger(tid, status="override_failed", resolved_at=_now_iso())
    await _apply_failure_policy(update, t, _cfg().get("override_failure_policy", "re_arm"))


async def _apply_failure_policy(update, t: dict[str, Any], policy: str) -> None:
    """Politique override-échoué : notify (a) | re_arm (b, défaut) | auto_execute (c)."""
    tid = t["id"]
    base = (
        f"⚠️ #{tid} : override *échoué* — ta condition de falsification s'est réalisée. "
        f"Preuve datée que l'instinct de tenir t'a trahi (biais #2/#3)."
    )
    if policy == "notify":  # (a)
        await update.message.reply_text(
            base + "\nLibre à toi de re-décider.", parse_mode="Markdown"
        )
    elif policy == "re_arm":  # (b) défaut O. 26/06
        new_id = storage.insert_kill_trigger(
            trigger_type=t["trigger_type"],
            episode_id=t.get("episode_id", 0),
            stage=t["stage"],
            level_measured=t["level_measured"],
            prescribed_action=t["prescribed_action"],
            status="unresolved",
            created_at=_now_iso(),
        )
        await update.message.reply_text(
            base
            + f"\nTrigger ré-armé (#{new_id}) : tu re-affrontes l'action. "
            + f"`/kill_exec {new_id}` ou nouvel override.",
            parse_mode="Markdown",
        )
    elif policy == "auto_execute":  # (c)
        storage.update_kill_trigger(tid, status="auto_execute_prescribed")
        await update.message.reply_text(
            base
            + "\nPlus de troisième chance : exécution prescrite, pas de nouvel override. "
            + f"`/kill_exec {tid}` pour confirmer.",
            parse_mode="Markdown",
        )
    else:
        raise config.ConfigurationError(f"override_failure_policy inconnu: {policy}")
