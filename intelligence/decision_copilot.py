"""Decision-time adversarial co-pilot.

Triggered at /position_buy or /position_sell, BEFORE the action is committed.
Assembles fresh context (current thesis + signals since creation + past similar
decisions + currently-triggered biases + asymmetry math) and asks Claude to
find the SHARPEST argument AGAINST the intended action — with mandatory citation
to specific evidence in the user's DB (decision_id, signal_id, pre_mortem_failure_mode).

Quality bar :
- Real arguments grounded in specific evidence, never generic platitudes.
- If no specific contrary evidence exists, output PROCEED with explicit
  acknowledgment ("aucune contre-evidence specifique trouvee").
- Citation of evidence IDs is mandatory in specific_arguments.

This is the orchestrator. The underlying components (pre_mortem, bias_tagger,
materiality scoring) are already in place. This module composes them.
"""

import json
import logging
from datetime import UTC, datetime

log = logging.getLogger(__name__)

# === Prompt structure ==========================================================

PROMPT = """Tu es un co-pilote adversarial pour un investisseur autonome qui s'apprete a
agir sur sa position. Ton ROLE : ecrire un brief court comme un collegue senior
qui le coince 30 secondes avant le geste. Pas une checklist. Pas une analyse de
texte. Un message direct, mache, en francais, qui pointe ce qui est ANORMAL
dans les donnees fournies. Si rien n'est anormal, tu le dis honnetement.

DATE D'ANCRAGE : TODAY = {today_iso}. Raisonne uniquement sur les donnees
ci-dessous. N'INVENTE PAS d'evenements absents (post-election, Q3 2024, etc.) —
si ta connaissance est plus ancienne, defere aux donnees fournies.

ACTION ENVISAGEE :
- Ticker : {ticker}
- Type : {decision_type}
- Raisonnement de l'utilisateur : "{reasoning}"
- Confiance pre-decision (1-5) : {confidence}

ETAT COURANT :
- Prix actuel : ${current_price}
- Entry : ${entry_price}
- Stop : ${stop_price} ({downside_pct}% downside)
- Target full : ${target_full} ({upside_pct}% upside)
- Asymetrie (upside/downside) : {asymmetry_ratio}
- Progression vers cible : {target_progress_pct}%
- Conviction these (1-5) : {thesis_conviction}
- Horizon : {horizon}
- Derniere revue : {last_reviewed} ({days_since_review} jours)

DRIVERS DE LA THESE :
{key_drivers}

TRIGGERS D'INVALIDATION (sorties definies) :
{invalidation_triggers}

PRE-MORTEM (5 modes d'echec a la creation de la these, il y a {thesis_age_days} jours) :
{pre_mortem_summary}

SIGNAUX RECENTS (30j, materialite ≥ 4/8, direct sur le ticker + adjacent meme secteur) :
{recent_signals_block}

DECISIONS PASSEES SIMILAIRES (meme type ou meme ticker, resolues) :
{past_similar_decisions_block}

BIAIS HISTORIQUEMENT IDENTIFIES CHEZ L'UTILISATEUR :
{bias_patterns_block}

═══════════════ REGLES DE SORTIE ═══════════════

INTERDIT (= platitude qui s'applique a n'importe quel titre) :
- "Reconsidere ton timing"
- "Attention aux biais"
- "Diversifie ton portefeuille"
- "Pense au risque"
- "Tiens ton plan"
- "Reste discipline"
- Toute phrase qui marche aussi bien pour AAPL, NVDA, ASML, ou un random ticker.

AUTO-VERIFICATION AVANT D'ECRIRE :
Pose-toi : "Mon argument citerait-il un fait specifique de TSM/NVDA/ce ticker
en particulier ? Ou pourrait-il s'appliquer a n'importe quoi ?"
Si c'est generique → reecris avec une citation concrete (signal_295, decision_42,
pm_failure_3, ou un nombre tire des donnees).
Si tu n'as RIEN de specifique a citer, sortie verdict=PROCEED et brief='Rien
de specifique ne s'oppose dans les donnees fournies. Action OK.'

FORMAT DE SORTIE — JSON strict, aucun markdown, aucun preambule :
{{
  "verdict" : "PROCEED" | "PRESSURE" | "STRONG_OPPOSE",
  "pressure_score" : <entier 0-100>,
  "biases_active" : ["nom_de_bias_1", ...] (uniquement parmi ceux listes ci-dessus),
  "ancrage" : "L'observation unique la plus importante. Une phrase. Doit citer un signal_id ou un nombre. Pas d'opinion sans citation.",
  "brief" : "Le message au format collegue senior. 3 a 5 phrases en francais. Direct, sec, sans politesse de remplissage. Specifique au ticker. Cite au moins un signal_id ou un nombre concret de la DB. Si verdict=PROCEED, dis pourquoi rien ne s'oppose."
}}

CALIBRATION :
- pressure_score < 30 → verdict=PROCEED (rien de specifique a opposer)
- 30-70 → verdict=PRESSURE (un ou deux points specifiques qui meritent reflexion)
- > 70 → verdict=STRONG_OPPOSE (evidence specifique multi-source contre l'action)

EXEMPLE DE QUALITE A ATTEINDRE (style brief) :
✅ "Tu veux trim TSM a 3% de progression vers cible alors que ton asymetrie reste
2.19 (upside 57.4 vs downside 26.2). Signal 282 du 27/05 mat 6/8 mentionne
'TSMC risks being a bottleneck on AI progress' — c'est bullish ton these
'AI exposure asymetrique', pas bearish. T'es a J+2 de la derniere revue these.
Qu'est-ce qui a vraiment change en 2 jours ?"

❌ MAUVAIS (platitude) : "Attention a ne pas vendre tes winners trop tot. Reflechis
bien avant d'agir. Considere les biais cognitifs comme le loss aversion."
"""


# === Context assembly =========================================================


def _format_signals(signals: list[dict]) -> str:
    if not signals:
        return "  (no signals on this ticker or sector in last 30 days above materiality threshold)"
    out = []
    for s in signals[:10]:
        cred = s.get("source_credibility")
        cred_str = f"{cred:.2f}" if isinstance(cred, int | float) else "?"
        mat = s.get("materiality", 0)
        scope = s.get("scope", "direct")
        out.append(
            f"  - signal_{s['id']} [{scope}] | {s['timestamp'][:10]} | source_credibility {cred_str} | "
            f"materiality {mat}/8 | sentiment {s.get('sentiment') or 'neutral'}\n"
            f"    \"{(s.get('title') or s.get('summary') or '')[:160]}\""
        )
    return "\n".join(out)


def _format_past_decisions(decisions: list[dict]) -> str:
    if not decisions:
        return "  (no past decisions of same type on similar patterns found)"
    out = []
    for d in decisions[:5]:
        outcome = "RESOLVED" if d.get("resolved_30d_at") else "PENDING"
        ret = d.get("return_30d_pct")
        ret_str = f"return_30d {ret:+.1f}%" if ret is not None else "no return yet"
        tags = d.get("bias_tags") or "[]"
        out.append(
            f"  - decision_{d['id']} | {d['created_at'][:10]} | {d['decision_type']} {d['ticker']} | "
            f"{outcome} | {ret_str} | biases tagged: {tags}\n"
            f"    reasoning: \"{(d.get('reasoning') or '')[:140]}\""
        )
    return "\n".join(out)


def _format_pre_mortem_summary(pm_json: str | None) -> str:
    if not pm_json:
        return "  (no pre-mortem on file — thesis predates auto-generation)"
    try:
        pm = json.loads(pm_json)
    except Exception:
        return "  (pre-mortem JSON malformed, skipping)"
    lines = []
    for i, fm in enumerate(pm.get("failure_modes", [])[:5], 1):
        p = fm.get("probability", 0)
        p_str = f"{p:.0%}" if isinstance(p, int | float) else str(p)
        sc = (fm.get("scenario") or "")[:140]
        lines.append(f"  - pm_failure_{i} (P={p_str}) : {sc}")
    if pm.get("asymmetry_warning"):
        lines.append(f"  - pm_asymmetry_warning : {pm['asymmetry_warning'][:200]}")
    return "\n".join(lines) or "  (pre-mortem empty)"


def _format_bias_patterns(patterns: list[dict]) -> str:
    if not patterns:
        return "  (no bias patterns currently matching this decision)"
    out = []
    for p in patterns[:4]:
        out.append(
            f"  - bias_{p['name']} (n={p.get('n_samples', '?')} historical samples, "
            f"avg_outcome {p.get('avg_outcome', 0):+.1f}%) : {p.get('description', '')[:200]}"
        )
    return "\n".join(out)


def assemble_context(intent: dict, thesis: dict, recent_signals: list, past_decisions: list, bias_patterns: list) -> dict:
    """Assemble the structured context dict for the prompt."""
    now = datetime.now(UTC)
    today_iso = now.date().isoformat()

    entry = thesis.get("entry_price") or 0
    stop = thesis.get("stop_price") or 0
    tgt_full = thesis.get("target_full") or 0
    current = intent.get("current_price") or thesis.get("last_price") or 0

    downside = ((current - stop) / current * 100) if current and stop else 0
    upside = ((tgt_full - current) / current * 100) if current and tgt_full else 0
    asym = (upside / downside) if downside > 0 else None
    progress = ((current - entry) / (tgt_full - entry) * 100) if (tgt_full and entry and tgt_full != entry) else 0

    opened = thesis.get("opened_at", "")
    thesis_age = 0
    if opened:
        try:
            opened_dt = datetime.fromisoformat(opened.replace("Z", "+00:00")) if opened else None
            if opened_dt:
                thesis_age = (now - opened_dt).days
        except Exception:
            thesis_age = 0

    last_rev = thesis.get("last_reviewed") or opened
    days_since_review = 0
    if last_rev:
        try:
            lr_dt = datetime.fromisoformat(last_rev.replace("Z", "+00:00")) if last_rev else None
            if lr_dt:
                days_since_review = (now - lr_dt).days
        except Exception:
            days_since_review = 0

    drivers = thesis.get("key_drivers") or "[]"
    if isinstance(drivers, str):
        try:
            drivers_list = json.loads(drivers)
        except Exception:
            drivers_list = [drivers]
    else:
        drivers_list = drivers
    drivers_str = "\n".join(f"  - {d}" for d in (drivers_list or [])) or "  (none recorded)"

    invalidation = thesis.get("invalidation_triggers") or "[]"
    if isinstance(invalidation, str):
        try:
            inv_list = json.loads(invalidation)
        except Exception:
            inv_list = [invalidation]
    else:
        inv_list = invalidation
    inv_str = "\n".join(f"  - {i}" for i in (inv_list or [])) or "  (none recorded)"

    return {
        "today_iso": today_iso,
        "ticker": thesis.get("ticker", "?"),
        "decision_type": intent.get("decision_type", "?"),
        "reasoning": (intent.get("reasoning") or "")[:400],
        "confidence": intent.get("confidence_pre", "?"),
        "current_price": f"{current:.2f}" if current else "?",
        "entry_price": f"{entry:.2f}" if entry else "?",
        "stop_price": f"{stop:.2f}" if stop else "?",
        "target_full": f"{tgt_full:.2f}" if tgt_full else "?",
        "downside_pct": f"{downside:.1f}" if current else "?",
        "upside_pct": f"{upside:.1f}" if current else "?",
        "asymmetry_ratio": f"{asym:.2f}" if asym else "?",
        "target_progress_pct": f"{progress:.0f}" if progress else "0",
        "thesis_conviction": thesis.get("conviction", "?"),
        "horizon": thesis.get("horizon", "?"),
        "last_reviewed": (last_rev or "?")[:10],
        "days_since_review": days_since_review,
        "thesis_age_days": thesis_age,
        "key_drivers": drivers_str,
        "invalidation_triggers": inv_str,
        "pre_mortem_summary": _format_pre_mortem_summary(thesis.get("pre_mortem")),
        "recent_signals_block": _format_signals(recent_signals),
        "past_similar_decisions_block": _format_past_decisions(past_decisions),
        "bias_patterns_block": _format_bias_patterns(bias_patterns),
    }


def run_copilot(intent: dict, thesis: dict, recent_signals: list, past_decisions: list, bias_patterns: list) -> dict | None:
    """Execute the co-pilot pressure test. Returns dict or None on failure."""
    from shared import llm

    ctx = assemble_context(intent, thesis, recent_signals, past_decisions, bias_patterns)
    prompt = PROMPT.format(**ctx)

    try:
        result = llm.call_json(prompt, tier="synthesize", max_tokens=1400)
        if not isinstance(result, dict):
            log.warning(f"copilot: unexpected response type {type(result)}")
            return None
        # Light validation
        if "verdict" not in result or "pressure_score" not in result:
            log.warning(f"copilot: malformed response keys {list(result.keys())}")
            return None
        return result
    except Exception as e:
        log.warning(f"copilot failed for {thesis.get('ticker')}: {e}")
        return None


def run_pre_trade_copilot(ticker: str, decision_type: str, reasoning: str, price: float) -> tuple[dict | None, int | None]:
    """High-level helper invoked from Telegram /position_buy, /position_sell, /override.

    Assembles context from live DB, runs the copilot, logs the intervention.
    Returns (copilot_response_dict, intervention_id) — both may be None if
    copilot fails. The trade SHOULD proceed regardless (copilot is advisory).
    """
    from shared import storage

    try:
        thesis = storage.get_thesis_by_ticker(ticker, status="active") or {}
        if not thesis:
            log.info(f"copilot: no active thesis on {ticker}, skipping pressure test")
            return None, None

        recent_signals = _fetch_signals_for_ticker(ticker)
        past_decisions = _fetch_past_decisions(ticker, decision_type)
        bias_patterns = _fetch_bias_patterns()

        intent = {
            "decision_type": decision_type,
            "reasoning": reasoning,
            "confidence_pre": thesis.get("conviction", 3),
            "current_price": price,
        }
        response = run_copilot(intent, thesis, recent_signals, past_decisions, bias_patterns)
        intervention_id = storage.log_copilot_intervention(
            ticker=ticker,
            decision_type=decision_type,
            intent_reasoning=reasoning,
            intent_price=price,
            intent_qty=None,
            thesis_id=thesis.get("id"),
            response=response,
            llm_meta={},  # llm_call already telemetered via llm_calls table
        )
        return response, intervention_id
    except Exception as e:
        log.warning(f"run_pre_trade_copilot failed for {ticker} {decision_type}: {e}")
        return None, None


def _fetch_signals_for_ticker(ticker: str) -> list:
    """Pull direct + adjacent (same sector) signals last 30d, materiality ≥ 4/8."""
    from dashboard.render import TICKER_SECTOR
    from shared.storage import db

    sector = TICKER_SECTOR.get(ticker)
    out = []
    try:
        with db() as conn:
            direct = conn.execute(
                "SELECT s.id, s.timestamp, s.title, s.summary, s.sentiment, s.score, "
                "src.credibility AS source_credibility "
                "FROM signals s LEFT JOIN sources src ON src.id=s.source_id "
                "WHERE s.timestamp > datetime('now','-30 day') "
                "AND (s.entities LIKE ? OR s.title LIKE ? OR s.content LIKE ?) "
                "AND s.score >= 4 ORDER BY s.timestamp DESC LIMIT 12",
                (f"%{ticker}%", f"%{ticker}%", f"%{ticker}%"),
            ).fetchall()
            adjacent = []
            if sector:
                same_sec = [tk for tk, sec in TICKER_SECTOR.items() if sec == sector and tk != ticker]
                if same_sec:
                    ph = " OR ".join(["s.entities LIKE ?" for _ in same_sec])
                    params = [f"%{tk}%" for tk in same_sec]
                    adjacent = conn.execute(
                        "SELECT s.id, s.timestamp, s.title, s.summary, s.sentiment, s.score, "
                        "src.credibility AS source_credibility "
                        f"FROM signals s LEFT JOIN sources src ON src.id=s.source_id "
                        f"WHERE s.timestamp > datetime('now','-30 day') AND ({ph}) "
                        f"AND s.score >= 4 ORDER BY s.timestamp DESC LIMIT 8",
                        params,
                    ).fetchall()
            cols = ["id", "timestamp", "title", "summary", "sentiment", "score", "source_credibility"]
            for r in direct:
                d = dict(zip(cols, r, strict=False))
                d["materiality"] = d["score"]
                d["scope"] = "direct"
                out.append(d)
            for r in adjacent:
                d = dict(zip(cols, r, strict=False))
                d["materiality"] = d["score"]
                d["scope"] = f"adjacent (sector: {sector})"
                out.append(d)
    except Exception as e:
        log.warning(f"_fetch_signals_for_ticker {ticker} failed: {e}")
    return out[:10]


def _fetch_past_decisions(ticker: str, decision_type: str) -> list:
    from shared.storage import db

    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT id, created_at, ticker, decision_type, direction, reasoning, "
                "resolved_30d_at, return_30d_pct, bias_tags, thesis_relative_30d "
                "FROM decisions WHERE (ticker=? OR decision_type=?) "
                "AND resolved_30d_at IS NOT NULL ORDER BY created_at DESC LIMIT 10",
                (ticker, decision_type),
            ).fetchall()
            cols = [
                "id",
                "created_at",
                "ticker",
                "decision_type",
                "direction",
                "reasoning",
                "resolved_30d_at",
                "return_30d_pct",
                "bias_tags",
                "thesis_relative_30d",
            ]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        log.warning(f"_fetch_past_decisions {ticker} failed: {e}")
        return []


def _fetch_bias_patterns() -> list:
    from shared.storage import db

    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT name, description, n_samples, avg_outcome, success_rate "
                "FROM patterns WHERE is_active=1 AND n_samples >= 3 "
                "ORDER BY n_samples DESC LIMIT 5"
            ).fetchall()
            cols = ["name", "description", "n_samples", "avg_outcome", "success_rate"]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        log.warning(f"_fetch_bias_patterns failed: {e}")
        return []


def format_brief_for_telegram(response: dict | None) -> str:
    """Format the co-pilot response as a Telegram-friendly text block."""
    if not response:
        return ""
    verdict = response.get("verdict", "PROCEED")
    score = response.get("pressure_score", 0)
    brief = response.get("brief", "").strip()
    ancrage = response.get("ancrage", "").strip()
    biases = response.get("biases_active") or []

    # Verdict emoji header
    icon = {"PROCEED": "✓", "PRESSURE": "⚠", "STRONG_OPPOSE": "✕"}.get(verdict, "?")
    parts = [f"\n— Co-pilot {icon} {verdict} (pression {score}/100) —"]
    if ancrage:
        parts.append(f"⚓ {ancrage}")
    if brief:
        parts.append(brief)
    if biases:
        parts.append(f"biais flagges : {', '.join(biases)}")
    return "\n".join(parts)
