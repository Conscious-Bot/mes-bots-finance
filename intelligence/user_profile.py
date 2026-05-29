"""Sprint 2 — Auto-derived self-portrait of the investor.

Synthese hebdo Opus. Lit tout l'historique structure (decisions, theses,
predictions resolved, bias_tags accumules, copilot interventions resolved,
sizing/concentration). Synthetise un JSON structure ou CHAQUE trait est
cite avec evidence_ids et n_samples. Ecrit dans user_profile (append-only).

Le profile est injecte dans decision_copilot.assemble_context pour calibrer
chaque pressure-test au style, biais, edge sectoriel du user.

Quality bar (meme que copilot) :
- Chaque trait cite des decision_ids / prediction_ids / n / Brier
- confidence_score derive du sample size (restraint au debut, pointu plus tard)
- Si data trop maigre sur une dimension : explicite ("uncertainty : pas assez
  de decisions sell pour caracteriser ton timing")
- INTERDIT : platitudes "tu es prudent", "tu as l'air aggressive" sans evidence
"""

import json
import logging
from datetime import UTC, datetime, timedelta

log = logging.getLogger(__name__)


PROMPT = """Tu es un analyste comportemental. Tu observes UN investisseur via
ses inputs structures (decisions, theses, predictions resolved, biais
tags, copilot interventions, sizing actuel) et tu construis un
AUTO-PORTRAIT factuel qui pourra etre INJECTE dans tous les futurs
calls du co-pilot pour calibrer la reponse au style de cet investisseur.

DATE D'ANCRAGE : TODAY = {today_iso}. Raisonne uniquement sur les donnees
ci-dessous. N'invente pas des traits non-supportes par les donnees.

═══════════════ DONNEES BRUTES ═══════════════

PORTFOLIO ACTUEL ({n_positions} positions, capital deploye {capital_eur}€) :
{portfolio_summary}

REPARTITION CONVICTION (theses actives, n={n_theses_active}) :
{conviction_distribution}

THESES ACTIVES TOP 10 PAR CONVICTION :
{theses_summary}

DECISIONS HISTORIQUES (n={n_decisions} total, dont {n_decisions_resolved} resolved a J+30) :
{decisions_summary}

PREDICTIONS RESOLVED (n={n_predictions_resolved}, Brier global {brier_avg}) :
{predictions_summary}

BIAS TAGS ACCUMULES (count par bias type) :
{bias_tags_summary}

COPILOT INTERVENTIONS RESOLVED (n={n_copilot_resolved}, outcome distribution) :
{copilot_history_summary}

DERNIER PORTFOLIO SNAPSHOT (concentration metrics) :
{concentration_metrics}

═══════════════ REGLES DE SORTIE ═══════════════

Tu vas produire un JSON. Pour chaque trait, tu DOIS citer le sample size
et au moins UN evidence_id (decision_42, prediction_67, ou un n=X).

INTERDIT (= platitudes generiques) :
- "Tu es un investisseur prudent" sans citation
- "Tu fais preuve de discipline" sans evidence_id ni n
- "Tes choix montrent une certaine maturite" — vide, no citation
- Toute affirmation qui marcherait pour n'importe quel user.

AUTO-VERIFICATION AVANT D'ECRIRE :
Pose-toi : "Mon trait cite un nombre, un decision_id, ou un n=X ?"
Si NON → reformule ou retire le trait. Mieux vaut moins de traits mais
tous cites que beaucoup de filler.

Si une dimension a moins de 3 samples → mets-la dans "uncertainty"
plutot que d'inventer un trait.

CONFIDENCE_SCORE (0-100) = pondere par sample sizes :
- < 10 decisions resolved → max 30
- 10-30 decisions resolved → 30-60
- > 30 decisions resolved → 60-90
- > 100 + ≥6 mois historique → 90+

═══════════════ HIERARCHIE DE POIDS DES INPUTS ═══════════════

Les inputs ont des poids differents dans ta synthese :
1. INPUTS DIRECTS de l'user (reasonings tapes dans decisions/theses) → POIDS MAX
   C'est ce qu'il PENSE explicitement. Verifie-le contre les outcomes.
2. THESES creees par l'user → poids fort
   Reflete ce qu'il valide/bet on, ses convictions actives.
3. NEWSLETTERS / SOURCES (signaux materialise) → poids moyen
   Reflete ce qu'il choisit d'ingerer, pas forcement ce qu'il decide.
4. POSITIONS actuelles → poids moyen-bas
   Peut inclure des legacy holdings qui ne reflete plus son thinking actuel.
5. PREDICTIONS resolved + Brier → poids correctif
   La realite du track-record corrige les declaration de surface.

Quand 2 signaux divergent (e.g. reasoning bullish mais Brier defavorable),
note explicitement la dissonance dans uncertainty[].

═══════════════ ARCHETYPES A CLASSIFIER ═══════════════

A. RISK ARCHETYPE (continuum, base sur sizing + asymetries + conviction
   distribution + concentration tolerance) :
   - "safe" : c1-c3 dominants, sizing sous cap, exits frequents pour
     securiser, asymetries faibles
   - "balanced" : mix c3-c4, sizing au cap, exits disciplines
   - "risky" : c5 dominants, concentration tolerance haute, asymetries
     hautes, hold-through volatility
   Output : {{"label": "balanced", "score": 0-100 (0=ultra safe, 100=ultra risky), "evidence": "..."}}

B. THESIS ARCHETYPE (liste des themes detectes via key_drivers + sectors
   + narratives) :
   - "modern_tech_ai" : AI compute, semis, cloud, growth tech
   - "classic_industrial" : energy, materials, utilities, infrastructure
   - "dividend_income" : high yield, REITs, defensive payers
   - "old_school_value" : deep value, contrarian, cyclical bottoms
   - "crypto" : digital assets, tokens
   - "macro_thematic" : top-down bets (rates, currencies, geo)
   - "sector_specific:<nom>" : si concentre sur 1 secteur particulier
   Output : array of {{"label": "modern_tech_ai", "n_theses": X, "weight_pct": X.X, "evidence_thesis_ids": [...]}}

═══════════════ FORMAT DE SORTIE ═══════════════

JSON strict, aucun markdown, aucun preambule :
{{
  "confidence_score": <0-100>,
  "summary_oneliner": "1 phrase qui resume la persona en termes specifiques, citant un n. Pas de generique.",
  "risk_archetype": {{
    "label": "safe" | "balanced" | "risky",
    "score": <0-100>,
    "evidence": "Citation de sizing patterns, asymetries observees, etc."
  }},
  "thesis_archetypes": [
    {{"label": "modern_tech_ai", "n_theses": X, "weight_pct": X.X, "evidence_thesis_ids": [...]}}
  ],
  "style": {{
    "trait": "Description specifique (citer pattern + n)",
    "evidence_ids": ["decision_X", "decision_Y", ...]
  }},
  "sizing_patterns": {{
    "trait": "Comment l'user dimensionne ses positions (citer ratios + n)",
    "evidence_ids": [...]
  }},
  "sector_preferences": {{
    "leans_bullish_on": [
      {{"sector_or_theme": "...", "n_theses": X, "avg_brier_or_outcome": "...", "evidence_ids": [...]}}
    ],
    "avoids": [
      {{"sector_or_theme": "...", "n_theses": 0, "rationale_from_data": "..."}}
    ]
  }},
  "bias_signature": {{
    "recurring_biases": [
      {{"name": "loss_aversion", "n_occurrences": X, "avg_outcome": "...", "evidence_ids": [...]}}
    ],
    "absent_biases": ["fomo si jamais observe", ...]
  }},
  "language_patterns": "Tu ecris court / long, jargon pro / vulgarise, etc. — base sur reasonings observed. Cite n=X reasoning observed.",
  "dialogue_tone_recommendation": "Pour les futurs co-pilot briefs adresses a cet user, le ton optimal est X (e.g. direct sec, jargon technique pro, asymetrie pas risk/reward). Base sur language_patterns + archetypes.",
  "track_record_summary": {{
    "brier_avg": <float>,
    "hit_rate_pct": <float>,
    "best_sector_or_theme": "...",
    "worst_sector_or_theme": "..."
  }},
  "uncertainty": [
    "Dimension X : pas assez de samples (n=Y) pour caracteriser",
    "Dissonance entre input direct et outcome : ...",
    ...
  ]
}}
"""


def _format_portfolio(positions: list) -> str:
    if not positions:
        return "  (aucune position)"
    out = []
    for p in positions[:15]:
        out.append(f"  - {p.get('ticker', '?')} qty {p.get('qty', 0):.2f} @ avg {p.get('avg_cost', 0):.2f}")
    if len(positions) > 15:
        out.append(f"  ... +{len(positions) - 15} autres positions")
    return "\n".join(out)


def _format_conviction_distribution(theses: list) -> str:
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for t in theses:
        c = t.get("conviction") or 0
        if 1 <= c <= 5:
            dist[c] += 1
    return "  " + " · ".join(f"c{k}={v}" for k, v in dist.items() if v > 0) or "  (aucune)"


def _format_theses(theses: list) -> str:
    if not theses:
        return "  (aucune)"
    out = []
    for t in theses[:10]:
        drivers = t.get("key_drivers") or ""
        if isinstance(drivers, str):
            try:
                drivers_list = json.loads(drivers)
            except Exception:
                drivers_list = [drivers]
        else:
            drivers_list = drivers
        drivers_short = "; ".join(str(d)[:60] for d in (drivers_list or [])[:2])
        out.append(
            f"  - thesis_{t['id']} {t['ticker']} c{t.get('conviction', '?')} {t.get('direction', 'long')} | "
            f"opened {(t.get('opened_at') or '')[:10]} | drivers: {drivers_short or '(none)'}"
        )
    return "\n".join(out)


def _format_decisions(decisions: list) -> str:
    if not decisions:
        return "  (aucune decision en DB)"
    out = []
    for d in decisions[:20]:
        ret = d.get("return_30d_pct")
        ret_str = f"return_30d {ret:+.1f}%" if ret is not None else "pending"
        biases = d.get("bias_tags") or "[]"
        out.append(
            f"  - decision_{d['id']} {(d.get('created_at') or '')[:10]} | {d.get('decision_type', '?')} "
            f"{d.get('ticker', '?')} c{d.get('confidence_pre', '?')} | {ret_str} | biases: {biases}\n"
            f"    reasoning: \"{(d.get('reasoning') or '')[:120]}\""
        )
    return "\n".join(out)


def _format_predictions(preds: list) -> str:
    if not preds:
        return "  (aucune prediction resolved)"
    out = []
    for p in preds[:15]:
        out.append(
            f"  - prediction_{p['id']} {p.get('ticker', '?')} {p.get('direction', '?')} | "
            f"resolved {(p.get('resolved_at') or '')[:10]} | "
            f"outcome {p.get('outcome', '?')} | return {p.get('return_pct', 0):.1f}% | "
            f"Brier {p.get('brier_score', 0):.2f}"
        )
    return "\n".join(out)


def _format_bias_tags(decisions: list) -> str:
    counts: dict = {}
    for d in decisions:
        tags = d.get("bias_tags") or "[]"
        try:
            tag_list = json.loads(tags) if isinstance(tags, str) else tags
            for t in tag_list:
                counts[t] = counts.get(t, 0) + 1
        except Exception:
            continue
    if not counts:
        return "  (aucun bias tag accumule)"
    sorted_counts = sorted(counts.items(), key=lambda kv: -kv[1])
    return "\n".join(f"  - {name}: {n} occurrences" for name, n in sorted_counts)


def _format_copilot_history(interventions: list) -> str:
    if not interventions:
        return "  (aucune intervention copilot resolved)"
    verdict_counts: dict = {}
    outcome_counts: dict = {}
    for i in interventions:
        v = i.get("verdict") or "UNKNOWN"
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
        o = i.get("outcome_label") or "pending"
        outcome_counts[o] = outcome_counts.get(o, 0) + 1
    lines = ["  Verdicts distribution :"]
    for v, n in sorted(verdict_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"    {v}: {n}")
    lines.append("  Outcome labels :")
    for o, n in sorted(outcome_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"    {o}: {n}")
    return "\n".join(lines)


def _format_concentration(snapshot: dict | None) -> str:
    if not snapshot:
        return "  (pas de snapshot recent)"
    return (
        f"  total value {snapshot.get('total_value_eur', 0):.0f}€ | "
        f"n_positions {snapshot.get('n_positions', '?')} | "
        f"pnl {snapshot.get('pnl_pct', 0):+.1f}% | "
        f"drawdown {snapshot.get('drawdown_pct', 0):.1f}%"
    )


def assemble_synthesis_context(months_window: int = 6) -> tuple[dict, dict]:
    """Lit tout l'historique structure pour la synthese profile.
    Returns (formatted_context_dict_for_prompt, source_counts_dict)."""
    from shared.storage import db

    now = datetime.now(UTC)
    window_start = (now - timedelta(days=months_window * 30)).isoformat()
    window_end = now.isoformat()

    counts = {"window_start": window_start, "window_end": window_end}

    with db() as conn:
        # Positions
        positions = [dict(zip(["ticker", "qty", "avg_cost"], r, strict=False))
                     for r in conn.execute(
                         "SELECT ticker, qty, avg_cost FROM positions WHERE qty > 0 AND status='open' ORDER BY qty * avg_cost DESC"
                     ).fetchall()]
        # Theses
        theses_rows = conn.execute(
            "SELECT id, ticker, conviction, direction, opened_at, key_drivers, status "
            "FROM theses WHERE status='active' ORDER BY conviction DESC LIMIT 30"
        ).fetchall()
        theses = [dict(zip(["id", "ticker", "conviction", "direction", "opened_at", "key_drivers", "status"], r, strict=False)) for r in theses_rows]
        counts["n_theses"] = len(theses)
        # Decisions
        decision_rows = conn.execute(
            "SELECT id, created_at, ticker, decision_type, confidence_pre, reasoning, "
            "resolved_30d_at, return_30d_pct, bias_tags "
            "FROM decisions WHERE created_at >= ? ORDER BY created_at DESC LIMIT 50",
            (window_start,),
        ).fetchall()
        decisions = [dict(zip(["id", "created_at", "ticker", "decision_type", "confidence_pre",
                              "reasoning", "resolved_30d_at", "return_30d_pct", "bias_tags"], r, strict=False)) for r in decision_rows]
        counts["n_decisions"] = len(decisions)
        counts["n_decisions_resolved"] = len([d for d in decisions if d.get("resolved_30d_at")])
        # Predictions resolved
        pred_rows = conn.execute(
            "SELECT id, ticker, direction, resolved_at, outcome, return_pct, brier_score "
            "FROM predictions WHERE resolved_at IS NOT NULL AND created_at >= ? "
            "ORDER BY resolved_at DESC LIMIT 50",
            (window_start,),
        ).fetchall()
        preds = [dict(zip(["id", "ticker", "direction", "resolved_at", "outcome", "return_pct", "brier_score"], r, strict=False)) for r in pred_rows]
        counts["n_predictions_resolved"] = len(preds)
        brier_avg = sum(p.get("brier_score") or 0 for p in preds) / len(preds) if preds else 0
        # Copilot interventions resolved (table may not exist yet pre-deploy)
        copilots: list = []
        try:
            copilot_rows = conn.execute(
                "SELECT id, verdict, pressure_score, outcome_label "
                "FROM bot_copilot_interventions WHERE resolved_30d_at IS NOT NULL "
                "ORDER BY resolved_30d_at DESC LIMIT 50"
            ).fetchall()
            copilots = [dict(zip(["id", "verdict", "pressure_score", "outcome_label"], r, strict=False)) for r in copilot_rows]
        except Exception as ce:
            log.info(f"bot_copilot_interventions not yet available: {ce}")
        counts["n_copilot_resolved"] = len(copilots)
        # Latest portfolio snapshot
        snap_row = conn.execute(
            "SELECT total_value_eur, n_positions, pnl_pct, drawdown_pct, snapshot_date "
            "FROM portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
        ).fetchone()
        snapshot = dict(zip(["total_value_eur", "n_positions", "pnl_pct", "drawdown_pct", "snapshot_date"], snap_row, strict=False)) if snap_row else None
        # Signals window count (informational)
        sig_count = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE timestamp >= ?", (window_start,)
        ).fetchone()[0]
        counts["n_signals_window"] = sig_count

    # Capital deploye (sum qty*avg_cost)
    capital_eur = sum((p.get("qty") or 0) * (p.get("avg_cost") or 0) for p in positions)
    counts["n_positions"] = len(positions)
    counts["capital_eur"] = capital_eur

    ctx = {
        "today_iso": now.date().isoformat(),
        "n_positions": len(positions),
        "capital_eur": f"{capital_eur:,.0f}".replace(",", " "),
        "portfolio_summary": _format_portfolio(positions),
        "n_theses_active": counts["n_theses"],
        "conviction_distribution": _format_conviction_distribution(theses),
        "theses_summary": _format_theses(theses),
        "n_decisions": counts["n_decisions"],
        "n_decisions_resolved": counts["n_decisions_resolved"],
        "decisions_summary": _format_decisions(decisions),
        "n_predictions_resolved": counts["n_predictions_resolved"],
        "brier_avg": f"{brier_avg:.3f}",
        "predictions_summary": _format_predictions(preds),
        "bias_tags_summary": _format_bias_tags(decisions),
        "n_copilot_resolved": counts["n_copilot_resolved"],
        "copilot_history_summary": _format_copilot_history(copilots),
        "concentration_metrics": _format_concentration(snapshot),
    }
    return ctx, counts


def run_synthesis(months_window: int = 6) -> tuple[dict | None, int | None]:
    """Run the synthesis LLM call and write to user_profile. Returns (profile_dict, profile_id)."""
    from shared import llm, storage

    ctx, counts = assemble_synthesis_context(months_window=months_window)
    prompt = PROMPT.format(**ctx)
    try:
        result = llm.call_json(prompt, tier="synthesize", max_tokens=2500)
        if not isinstance(result, dict):
            log.warning(f"user_profile synthesis: unexpected response type {type(result)}")
            return None, None
        # Store
        profile_json = json.dumps(result, ensure_ascii=False)
        source_counts = {
            "confidence_score": result.get("confidence_score"),
            "n_decisions": counts.get("n_decisions"),
            "n_theses": counts.get("n_theses"),
            "n_predictions_resolved": counts.get("n_predictions_resolved"),
            "n_signals_window": counts.get("n_signals_window"),
            "window_start": counts.get("window_start"),
            "window_end": counts.get("window_end"),
            "notes": f"synthesis window {months_window} months",
        }
        profile_id = storage.insert_user_profile(profile_json, source_counts, llm_meta={})
        return result, profile_id
    except Exception as e:
        log.warning(f"user_profile synthesis failed: {e}")
        return None, None


def format_profile_for_copilot_context(profile_json: str | None) -> str:
    """Format the latest profile_json into a section ready to inject in copilot prompt.
    Surface archetypes + dialogue_tone_recommendation pour calibrer le ton du brief."""
    if not profile_json:
        return "  (aucun user_profile encore synthese — bot ne connait pas encore l'utilisateur en detail)"
    try:
        p = json.loads(profile_json)
    except Exception:
        return "  (user_profile malformed, skipping)"
    lines = []
    if p.get("summary_oneliner"):
        lines.append(f"  Summary : {p['summary_oneliner']}")
    if p.get("confidence_score") is not None:
        lines.append(f"  Confidence in profile : {p['confidence_score']}/100 (low = restraint, high = pointu)")
    # Archetype risk
    ra = p.get("risk_archetype") or {}
    if ra.get("label"):
        lines.append(f"  Risk archetype : {ra.get('label')} (score {ra.get('score', '?')}/100)")
    # Archetype theses
    ta = p.get("thesis_archetypes") or []
    if ta:
        archs = [f"{a.get('label')} ({a.get('weight_pct', 0):.0f}%)" for a in ta[:4]]
        lines.append(f"  Thesis archetypes : {', '.join(archs)}")
    if p.get("style", {}).get("trait"):
        lines.append(f"  Style : {p['style']['trait']}")
    if p.get("sizing_patterns", {}).get("trait"):
        lines.append(f"  Sizing : {p['sizing_patterns']['trait']}")
    leans = p.get("sector_preferences", {}).get("leans_bullish_on") or []
    if leans:
        lines.append(f"  Lean bullish : {', '.join(s.get('sector_or_theme', '?') for s in leans[:3])}")
    avoids = p.get("sector_preferences", {}).get("avoids") or []
    if avoids:
        lines.append(f"  Evite : {', '.join(s.get('sector_or_theme', '?') for s in avoids[:3])}")
    biases = p.get("bias_signature", {}).get("recurring_biases") or []
    if biases:
        bias_parts = [f"{b.get('name')} (n={b.get('n_occurrences')})" for b in biases[:3]]
        lines.append(f"  Biais recurrents : {', '.join(bias_parts)}")
    if p.get("language_patterns"):
        lines.append(f"  Langage : {p['language_patterns'][:160]}")
    # Tone calibration explicite pour les futurs briefs
    if p.get("dialogue_tone_recommendation"):
        lines.append(f"  >> TON A ADOPTER dans ce brief : {p['dialogue_tone_recommendation']}")
    return "\n".join(lines) or "  (profile vide)"
