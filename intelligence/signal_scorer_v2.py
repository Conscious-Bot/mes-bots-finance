"""SIGNAL_SCORER_V2 — Directional probability via base-rate-first elicitation.

Bug fondateur (audit 30/05/2026) : 40 predictions batch 10/06 toutes dans proba
[0.608-0.658] (1 seul bucket) et 67% outcomes neutral. Cause : `estimate_probability`
formule (V1) borne [0.50, 0.72] + sources cred=0.50 figees + filter score>=6.
Resultat : forecaster qui sort une constante deguisee, evite la falsifiabilite.

V2 attaque la racine : elicitation directionnelle LLM forcee a expliciter :
  1. BASE RATE -- taux de base sur l'horizon, sans regarder le signal
  2. AJUSTEMENT -- evidence specifique + magnitude de la deviation
  3. ANTI-ANCRAGE -- pourquoi ni 0.50 ni 0.90 ?

Interdictions encodees dans le prompt :
- Pas de prob dans [0.55-0.70] "parce que ca semble probable"
- Si pas d'evidence specifique justifiable -> prob = base rate
- Si pas de direction falsifiable -> direction="watch" (sort du ledger)

Output : prob + direction + audit fields (base_rate, evidence, anti_anchor reason).

V1 (estimate_probability) reste accessible pour A/B versioning. V2 ne remplace
pas V1 tant que validation echantillon n'a pas montre spread >= 3 buckets.
"""

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

# Versioning : V1 = formula estimate_probability, V2 = LLM elicitation base-rate-first
SCORER_VERSION = "v2.0"


def score_directional_probability(
    title: str,
    summary: str | None,
    ticker: str,
    horizon_days: int,
    content: str | None = None,
    entities: list[str] | None = None,
    source_name: str | None = None,
) -> dict[str, Any] | None:
    # ARCHITECTURE NOTE: source_name n'est PAS injectee dans le prompt.
    # Bug observe 30/05 sur echelle synthetique : le LLM utilisait la source
    # pour downgrade l'evidence ("synthetic_test = pas fiable -> watch"). La
    # fiabilite source doit etre une couche APRES le scoring, pas pendant.
    # Le scorer repond "si ce signal est vrai, qu'est-ce que ca implique" --
    # pondertion crediblite source = job de credibility.py.
    _ = source_name  # explicite : on l'accepte pour compat API mais on n'l'utilise pas
    """Single Sonnet call. Returns dict or None on failure.

    Returns:
        {
            "version": "v2.0",
            "ticker": str,
            "horizon_days": int,
            "base_rate": float in [0.0, 1.0],         # step 1
            "evidence_strength": "none|weak|moderate|strong",
            "evidence_summary": str,                   # step 2
            "anti_anchoring_reason": str,              # step 3 (one sentence)
            "probability": float in [0.0, 1.0],
            "direction": "bullish|bearish|watch",     # watch = no ledger entry
            "reasoning": str,                          # full short reasoning
        }
    """
    from shared import llm

    title_s = (title or "")[:300]
    summary_s = (summary or "")[:600]
    content_s = (content or "")[:1200]
    entities_str = ", ".join(entities) if entities else "none extracted"

    prompt = (
        "You are a CALIBRATED directional forecaster for a personal finance system.\n"
        "Your output is logged to a Brier-scored ledger; over-confident or anchored\n"
        "probabilities ruin calibration. Follow the 3 EXPLICIT steps below.\n\n"
        "ASSUME THE SIGNAL CONTENT IS FACTUALLY TRUE for the purpose of scoring.\n"
        "Source-credibility weighting is applied in a SEPARATE LAYER downstream --\n"
        "do not downgrade evidence_strength because the source feels unfamiliar.\n"
        "Your job: 'IF this signal is true, what does it imply for the directional move?'\n\n"
        f"TARGET TICKER: {ticker}\n"
        f"HORIZON: {horizon_days} days from now\n"
        f"SIGNAL TITLE: {title_s}\n"
        f"SUMMARY: {summary_s}\n"
        f"CONTENT EXCERPT: {content_s}\n"
        f"ENTITIES MENTIONED: {entities_str}\n\n"
        "STEP 1 — BASE RATE (no signal):\n"
        "  State the base rate of a directional move (>5%) for this ticker over\n"
        "  this horizon, ignoring the signal entirely. For most liquid equities\n"
        "  over 30d this is near 0.50 (slightly above if bullish drift accepted).\n"
        "  DO NOT default to 0.6 'pour le confort'.\n\n"
        "STEP 2 — ADJUSTMENT (evidence-driven):\n"
        "  List the specific evidence in this signal that justifies deviating\n"
        "  from base rate, and by how much. Be explicit on strength:\n"
        "    - 'none'     : no specific actionable evidence -> stay AT base rate\n"
        "    - 'weak'     : vague narrative / opinion -> deviation 0-3 points max\n"
        "    - 'moderate' : concrete data point / catalyst -> deviation 5-15 points\n"
        "    - 'strong'   : specific verifiable + magnitude -> deviation 15-30 points\n\n"
        "STEP 3 — ANTI-ANCHORING (one sentence):\n"
        "  Justify in one sentence why your probability is NEITHER ~0.50 NOR ~0.90.\n"
        "  If you cannot justify the deviation from base rate with substance,\n"
        "  the probability MUST equal the base rate.\n\n"
        "FORBIDDEN PATTERNS:\n"
        "  - probability in [0.55, 0.70] 'because it seems probable' -- use base rate instead\n"
        "  - vague 'this might support the stock' without specific magnitude\n"
        "  - asserting 'strong' evidence without naming a specific verifiable fact\n\n"
        "FALLBACK:\n"
        "  If no evidence supports a FALSIFIABLE directional call within the horizon,\n"
        "  set direction='watch'. Watch entries do NOT enter the scored ledger.\n"
        "  Better silence than a fake call.\n\n"
        "Output ONLY this JSON structure, no preamble:\n"
        "{\n"
        '  "base_rate": <float 0-1>,\n'
        '  "evidence_strength": "<none|weak|moderate|strong>",\n'
        '  "evidence_summary": "<1-2 sentences listing specific evidence + estimated deviation>",\n'
        '  "anti_anchoring_reason": "<one sentence: why not ~0.5 and why not ~0.9>",\n'
        '  "probability": <float 0-1>,\n'
        '  "direction": "<bullish|bearish|watch>",\n'
        '  "reasoning": "<short overall>"\n'
        "}"
    )

    try:
        result = llm.call(prompt, tier="enrich", max_tokens=500)
        if not result:
            return None
        text = result.strip()
        if text.startswith("```"):
            text = text.split("```")[1] if "```" in text else text
            if text.startswith("json"):
                text = text[4:]
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0:
            log.warning(f"signal_scorer_v2: no JSON in: {text[:200]}")
            return None
        data = json.loads(text[start : end + 1])

        # Validate
        base_rate = float(data.get("base_rate", 0.5))
        prob = float(data.get("probability", base_rate))
        ev_str = (data.get("evidence_strength") or "none").strip().lower()
        direction = (data.get("direction") or "watch").strip().lower()

        if not (0.0 <= base_rate <= 1.0) or not (0.0 <= prob <= 1.0):
            log.warning(f"signal_scorer_v2: prob out of [0,1] for {ticker}")
            return None
        if ev_str not in ("none", "weak", "moderate", "strong"):
            ev_str = "none"
        if direction not in ("bullish", "bearish", "watch"):
            direction = "watch"

        # Server-side enforcement of "no evidence -> prob = base_rate".
        # Le LLM peut tricher ; on impose la regle a la sortie.
        if ev_str == "none" and abs(prob - base_rate) > 0.01:
            log.info(
                f"signal_scorer_v2 [{ticker}]: ev=none but prob={prob:.3f} != "
                f"base={base_rate:.3f} -- enforcing prob=base_rate"
            )
            prob = base_rate

        # Server-side enforcement of the [0.55, 0.70] dead zone : si on tombe
        # dedans SANS evidence strong, on force vers base rate. C'est la zone
        # "ca semble probable" qui pollue la calibration.
        if 0.55 <= prob <= 0.70 and ev_str in ("none", "weak"):
            log.info(
                f"signal_scorer_v2 [{ticker}]: prob={prob:.3f} in dead zone with "
                f"ev={ev_str} -- snap to base_rate={base_rate:.3f}"
            )
            prob = base_rate

        return {
            "version": SCORER_VERSION,
            "ticker": ticker,
            "horizon_days": horizon_days,
            "base_rate": round(base_rate, 3),
            "evidence_strength": ev_str,
            "evidence_summary": (data.get("evidence_summary") or "")[:500],
            "anti_anchoring_reason": (data.get("anti_anchoring_reason") or "")[:300],
            "probability": round(prob, 3),
            "direction": direction,
            "reasoning": (data.get("reasoning") or "")[:500],
        }
    except json.JSONDecodeError as e:
        log.warning(f"signal_scorer_v2 JSON decode failed for {ticker}: {e}")
        return None
    except Exception as e:
        log.warning(f"signal_scorer_v2 failed for {ticker}: {e}")
        return None
