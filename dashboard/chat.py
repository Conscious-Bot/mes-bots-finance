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


SYSTEM_PROMPT = (
    "Tu es l'assistant adversarial co-pilot d'un investisseur particulier serieux. "
    "Tu connais son historique reel, son profil, sa note PF actuelle, ses interventions "
    "passees et ses theses actives. Tu reponds EN FRANCAIS, ton direct et sec (pas de "
    "politesse de remplissage). Tu cites toujours du concret de la DB (ticker exact, "
    "score precis, ancrage). Tu ne donnes JAMAIS de generalite (\"diversifie\", "
    "\"reste discipline\", \"reconsidere\") : si tu n'as rien de specifique, dis-le. "
    "Tu peux pousser un point de vue (red-team), mais cite tes sources."
)


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
    thesis_archs = prof.get("thesis_archetypes") or []
    out.append(f"  Archetype risque : {arch}")
    if thesis_archs:
        out.append(f"  Archetypes these : {', '.join(thesis_archs)}")
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

    return (
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
        f"{_format_interventions(interventions)}\n"
    )


def chat(user_message: str) -> dict:
    """Send a message; return {reply, latency_ms, error}.

    Single-shot for now (no multi-turn history). Context (positions/grade/etc)
    is refreshed every call. Multi-turn will need llm.call extension.
    """
    from time import time as _now

    from shared import llm

    if not user_message or not user_message.strip():
        return {"reply": "(message vide)", "error": "empty"}

    context = assemble_context()
    prefix = f"Contexte DB :\n\n{context}\n\n"
    full_prompt = prefix + f"Question : {user_message.strip()}"

    t0 = _now()
    try:
        # Multi-turn : we don't pass history through llm.call (single-shot)
        # because shared/llm.py is single-message ; multi-turn would need extension.
        # For now : single-shot with full context each time. Caching the context
        # block via cache_invariant when long enough.
        reply = llm.call(
            full_prompt,
            tier="synthesize",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            cache_invariant=context if len(context) > 4000 else None,
        )
        return {
            "reply": reply,
            "latency_ms": int((_now() - t0) * 1000),
            "error": None,
        }
    except Exception as e:
        log.error(f"chat failed: {e}")
        return {"reply": f"Erreur : {type(e).__name__}: {e}", "error": str(e)}
