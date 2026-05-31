"""Sprint 7 — Chat surface : RAG sur user_profile + grade + interventions + theses.

Le user pose une question dans le panel chat du dashboard → cet module
assemble le contexte RAG complet (profil + note PF + interventions + theses
+ positions) et appelle Opus.

Pas de RAG vectoriel — le bot est petit (~40 theses), on injecte tout le
contexte structure. C'est ce qui rend le bot tailormade : il connait son
historique reel, pas un retrieval flou.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


# SYSTEM_PROMPT extrait vers shared/copilot_persona.py (31/05/2026) pour source de
# verite UNIQUE partagee avec futurs handlers Telegram. Voir [[copilot-persona-canonical]].
from shared.copilot_persona import SYSTEM_PROMPT


def _format_positions(positions: list[dict], pnl: dict) -> str:
    if not positions:
        return "  (aucune position ouverte)"
    out = []
    total = sum(p.get("weight", 0) for p in positions) or 1
    for p in sorted(positions, key=lambda x: -x.get("weight", 0))[:20]:
        tk = p.get("ticker", "?")
        w = p.get("weight", 0)
        wpct = w / total * 100
        plv = pnl.get(tk)
        plv_s = f"{plv:+.1f}%" if plv is not None else "?"
        out.append(f"  - {tk} : {wpct:.1f}% du book, P&L {plv_s}")
    return "\n".join(out)


def _format_theses(theses: list[dict]) -> str:
    if not theses:
        return "  (aucune these active)"
    out = []
    for t in sorted(theses, key=lambda x: -(x.get("conviction") or 0))[:20]:
        tk = t.get("ticker", "?")
        conv = t.get("conviction", "?")
        kd = (t.get("key_drivers") or "")[:180]
        out.append(f"  - {tk} c{conv} : {kd}")
    return "\n".join(out)


def _format_interventions(interventions: list[dict]) -> str:
    if not interventions:
        return "  (aucune intervention enregistree)"
    out = []
    for r in interventions[:15]:
        date = (r.get("created_at") or "")[:10]
        tk = r.get("ticker", "?")
        dtype = r.get("decision_type", "?")
        ver = r.get("verdict", "?")
        score = r.get("pressure_score") or 0
        anc = (r.get("ancrage") or "")[:160]
        outc = r.get("outcome_label") or ""
        ret = r.get("return_30d_pct")
        outc_s = ""
        if outc:
            outc_s = f" → {outc}"
            if ret is not None:
                outc_s += f" ({ret:+.1f}%)"
        out.append(f"  - {date} {tk} {dtype} : {ver} ({score}) — {anc}{outc_s}")
    return "\n".join(out)


def _format_grade(grade: dict | None) -> str:
    if not grade:
        return "  (pas de snapshot grade)"
    out = [
        f"  Note PF : {grade['overall_grade']} ({grade['overall_score']}/100) au {grade.get('snapshot_date', '?')}",
    ]
    dims = grade.get("dimensions") or {}
    if isinstance(dims, str):
        try:
            dims = json.loads(dims)
        except Exception:
            dims = {}
    for dk, d in (dims or {}).items():
        cur = d.get("current_pct", 0)
        tgt = d.get("target_pct", 0)
        ev = (d.get("evidence") or "")[:100]
        out.append(f"  - {dk} : {cur:.1f}% / cible {tgt}% — {ev}")
    return "\n".join(out)


def _format_profile(profile: dict | None) -> str:
    if not profile:
        return "  (profil non encore synthesise)"
    try:
        prof = json.loads(profile.get("profile_json", "{}")) if profile.get("profile_json") else {}
    except Exception:
        prof = {}
    if not prof:
        return "  (profil vide)"
    out = []
    arch = prof.get("risk_archetype") or "?"
    if isinstance(arch, dict):
        arch = f"{arch.get('label','?')} (score {arch.get('score','?')})"
    thesis_archs = prof.get("thesis_archetypes") or []
    arch_labels = []
    for a in thesis_archs:
        if isinstance(a, dict):
            arch_labels.append(f"{a.get('label','?')} ({a.get('weight_pct','?')}%)")
        elif isinstance(a, str):
            arch_labels.append(a)
    out.append(f"  Archetype risque : {arch}")
    if arch_labels:
        out.append(f"  Archetypes these : {', '.join(arch_labels)}")
    tone = prof.get("dialogue_tone_recommendation") or ""
    if tone:
        out.append(f"  Tone recommande : {tone[:200]}")
    bias = prof.get("bias_signature") or {}
    if bias:
        out.append(f"  Biais signature : {json.dumps(bias, ensure_ascii=False)[:300]}")
    return "\n".join(out)


def assemble_context() -> str:
    """Assemble all DB context blocks for the prompt."""
    from intelligence import portfolio_grade as _grade
    from shared import storage as _stg

    # User profile
    try:
        profile = _stg.get_latest_user_profile()
    except Exception:
        profile = None

    # Portfolio grade
    try:
        grade = _stg.get_latest_portfolio_grade()
        if grade and grade.get("dimensions_json"):
            grade["dimensions"] = json.loads(grade["dimensions_json"])
    except Exception:
        grade = None

    # Interventions
    try:
        interventions = _stg.get_recent_copilot_interventions(limit=15)
    except Exception:
        interventions = []

    # Positions + theses + pnl from dashboard.render (single source of truth)
    try:
        from dashboard.render import _pnl_cost_map, _positions

        positions = _positions()
        pnl = _pnl_cost_map(positions)
    except Exception as e:
        log.warning(f"chat context positions failed: {e}")
        positions = []
        pnl = {}

    try:
        from shared.storage import db

        with db() as cx:
            thesis_rows = cx.execute(
                "SELECT ticker, conviction, key_drivers FROM theses WHERE status='active'"
            ).fetchall()
        theses = [
            {"ticker": r[0], "conviction": r[1], "key_drivers": r[2]} for r in thesis_rows
        ]
    except Exception:
        theses = []

    # Trend
    try:
        trend = _grade.compute_trend_7d()
    except Exception:
        trend = "no_history"

    # Layer 2 — Bot conceptions (1 ligne par target, conviction>=30)
    conceptions_block = "  (pas encore de conceptions synthetisees)"
    try:
        from shared import storage as _stg

        concs = _stg.get_all_current_conceptions()
        lines = []
        for c in concs[:30]:
            if (c.get("conviction") or 0) < 30:
                continue
            val = c.get("valence")
            val_s = f"{val:+.1f}" if isinstance(val, int | float) else "·"
            lines.append(
                f"  [{c['kind']}] {c['target_key']:14s} conv={c['conviction']:>3d} val={val_s} : "
                f"{(c.get('conception_text') or '')[:240]}"
            )
        if lines:
            conceptions_block = "\n".join(lines)
    except Exception:
        pass

    # Topical recurrence : what the user obsesses about
    try:
        from intelligence import topical_recurrence as _tr

        recurrence_block = _tr.format_for_chat_context()
    except Exception:
        recurrence_block = "  (recurrence indispo)"

    # Pushes Telegram recents 24h (hook notify.py 31/05/2026)
    # Le copilot peut referencer "le brief de ce matin disait X" sans re-coller.
    try:
        with _stg.db() as cx:
            tg_rows = cx.execute(
                "SELECT created_at, content FROM chat_messages "
                "WHERE surface = 'telegram' "
                "AND created_at >= datetime('now', '-24 hours') "
                "ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
        if tg_rows:
            tg_lines = []
            for r in tg_rows:
                ts = (r["created_at"] or "")[:16]
                content = (r["content"] or "").strip()
                # Tronquer chaque push a 400 chars pour eviter context explosion
                if len(content) > 400:
                    content = content[:400] + "..."
                tg_lines.append(f"  [{ts}] {content}")
            telegram_pushes_block = "\n".join(tg_lines)
        else:
            telegram_pushes_block = "  (aucun push Telegram dans les 24h)"
    except Exception:
        telegram_pushes_block = "  (pushes Telegram indispo)"

    return (
        "═══ OBSESSIONS RECURRENTES (60j chat) ═══\n"
        f"{recurrence_block}\n\n"
        "═══ PROFIL UTILISATEUR (auto-derive) ═══\n"
        f"{_format_profile(profile)}\n\n"
        "═══ NOTE DU PORTEFEUILLE ═══\n"
        f"{_format_grade(grade)}\n"
        f"  Trend 7j : {trend}\n\n"
        "═══ POSITIONS ACTIVES ═══\n"
        f"{_format_positions(positions, pnl)}\n\n"
        "═══ THESES ACTIVES ═══\n"
        f"{_format_theses(theses)}\n\n"
        "═══ INTERVENTIONS COPILOT RECENTES ═══\n"
        f"{_format_interventions(interventions)}\n\n"
        "═══ PUSHES TELEGRAM 24H (briefs/alerts/digests recents) ═══\n"
        f"{telegram_pushes_block}\n\n"
        "═══ CONCEPTIONS BOT (Layer 2 — vue stable par target) ═══\n"
        f"{conceptions_block}\n"
    )


def chat(
    user_message: str,
    history: list[dict] | None = None,
    session_id: str | None = None,
    surface: str = "dashboard",
) -> dict:
    """Send a message ; return {reply, latency_ms, error, session_id}.

    history (optional) : [{role: 'user'|'assistant', content: str}, ...] — turns
    PRIOR to the current user_message. Context (positions/grade/etc) is
    refreshed every call and pushed in system so it doesn't bloat history.

    Side-effect : persiste user + assistant turn dans chat_messages (Sprint 9 —
    "tout les textes et conversation doivent etre consignees sauvegardees et
    utilisees pour le futur"). Logged via shared/storage helper.
    """
    from time import time as _now
    from uuid import uuid4

    from shared import llm, storage

    if not user_message or not user_message.strip():
        return {"reply": "(message vide)", "error": "empty"}

    if not session_id:
        session_id = uuid4().hex[:16]

    user_msg_id = storage.insert_chat_message(
        surface=surface,
        role="user",
        content=user_message.strip(),
        session_id=session_id,
    )

    # Sprint 9-19 — Intent detection : route NL vers primitives Telegram.
    # Sprint 19 : supporte les messages compound (plusieurs trades dans 1
    # message) + EUR amounts (convertis via prix courant).
    trade_summary = None
    try:
        from intelligence import chat_intent as _intent_mod

        parsed = _intent_mod.extract_intent(user_message)
        if parsed:
            confidence = parsed.get("confidence") or 0
            intents = parsed.get("intents") or []
            mutation_kinds = {"buy", "sell", "set_field", "close_thesis", "revisit_thesis", "override"}
            # Si AU MOINS UN intent est mutation, on applique le seuil mutation
            has_mutation = any((i or {}).get("kind") in mutation_kinds for i in intents)
            threshold = 0.7 if has_mutation else 0.5
            if intents and confidence >= threshold:
                exec_res = _intent_mod.execute_intents(intents, reasoning_fallback=user_message)
                trade_summary = exec_res.get("summary")
                log.info(
                    f"chat-driven {len(intents)} intents : "
                    f"ok={exec_res.get('n_executed')} fail={exec_res.get('n_failed')}"
                )
            elif intents and confidence >= 0.4 and parsed.get("clarification_needed"):
                trade_summary = (
                    "⚠️ Intent(s) detecte(s) mais incomplet : "
                    f"{parsed.get('clarification_needed')}"
                )
    except Exception as e:
        log.warning(f"intent extraction failed: {e}")

    # Sprint 9.d — Passive signal extraction : tout message lambda devient une
    # mine d'info (concerns/doubts/conviction shifts/topic interests/...).
    # Best-effort, non-bloquant. Tourne meme quand pas d'intent ferme.
    try:
        from intelligence import chat_intent as _ce

        _ce.extract_passive_signals(user_message, chat_message_id=user_msg_id)
    except Exception as e:
        log.warning(f"passive signal extraction failed: {e}")

    context = assemble_context()
    messages = []
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content[:6000]})
    messages.append({"role": "user", "content": user_message.strip()})

    system_with_ctx = f"{SYSTEM_PROMPT}\n\n=== CONTEXTE DB (rafraichi a chaque tour) ===\n{context}"

    t0 = _now()
    reply_text = ""
    err_msg = None
    try:
        if len(system_with_ctx) > 4000:
            reply_text = llm.call_multiturn(
                messages, tier="synthesize", max_tokens=4000,
                cache_invariant=system_with_ctx,
            )
        else:
            reply_text = llm.call_multiturn(
                messages, tier="synthesize", max_tokens=4000, system=system_with_ctx,
            )
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        log.error(f"chat failed: {err_msg}")
        reply_text = f"Erreur : {err_msg}"
    latency_ms = int((_now() - t0) * 1000)

    # If a trade was executed (or attempted), prepend it to the reply so the
    # user sees the action take effect IN the chat.
    if trade_summary:
        reply_text = f"{trade_summary}\n\n---\n\n{reply_text}"

    # Persist assistant turn (success or error)
    storage.insert_chat_message(
        surface=surface,
        role="assistant",
        content=reply_text,
        session_id=session_id,
        llm_meta={"latency_ms": latency_ms, "error": err_msg},
    )

    return {
        "reply": reply_text,
        "latency_ms": latency_ms,
        "session_id": session_id,
        "trade_executed": bool(trade_summary and trade_summary.startswith("✅")),
        "error": err_msg,
    }
