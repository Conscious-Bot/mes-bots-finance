"""Phase Digestion 3c — Structured materiality scoring (Sonnet enrich).

Décompose le score monolithique 0-10 en rubric explicite:
- impact_magnitude (1-5): À quel point l'event affecte les prix/business si vrai?
- reversibility (1-5): Est-ce permanent (1) ou facile à inverser (5)?
- time_to_realization: urgent (<7d) / medium (7-90d) / slow (>90d) / na

Composite = (impact*0.5 + reversibility_inv*0.3 + time_factor*0.2) scaled to 0-10.
Stockage: signals.impact_magnitude, reversibility, time_to_realization, materiality_breakdown (JSON).

Justification cognitive: au lieu de "score=7 sans savoir pourquoi", tu vois
"impact=4 reversibility=2 (durable) time=urgent (FOMC -3j)" → décision lucide.
"""

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

TIME_FACTORS = {"urgent": 5.0, "medium": 3.0, "slow": 1.0, "na": 2.0}


def score_materiality_structured(
    title: str,
    summary: str | None = None,
    content: str | None = None,
    entities: list[str] | None = None,
    source_credibility: float | None = None,
) -> dict[str, Any] | None:
    """Single Sonnet call. Returns dict with rubric components or None on failure."""
    from shared import llm

    title = (title or "")[:300]
    summary = (summary or "")[:600] if summary else ""
    content_snippet = (content or "")[:1200] if content else ""
    entities_str = ", ".join(entities) if entities else "none extracted"
    cred = source_credibility if source_credibility is not None else 0.5

    prompt = (
        "You are a materiality scoring engine for a personal finance intelligence system.\n"
        "Score the materiality of this signal using a 3-axis rubric. Output STRICT JSON only.\n\n"
        f"SIGNAL TITLE: {title}\n"
        f"SUMMARY: {summary}\n"
        f"CONTENT EXCERPT: {content_snippet}\n"
        f"ENTITIES MENTIONED: {entities_str}\n"
        f"SOURCE CREDIBILITY: {cred:.2f} (0-1, higher=more credible)\n\n"
        "RUBRIC:\n"
        "1. impact_magnitude (1-5): If this signal is true, how much does it shift prices/business?\n"
        "   1 = trivial/cosmetic; 2 = minor; 3 = notable; 4 = material; 5 = paradigm-shifting\n"
        "2. reversibility (1-5): How permanent is the change?\n"
        "   1 = irreversible (bankruptcy, ban); 2 = hard to undo; 3 = moderate; 4 = easy to reverse; 5 = transient noise\n"
        "3. time_to_realization (string): When does the impact manifest?\n"
        "   'urgent' (<7 days) | 'medium' (7-90 days) | 'slow' (>90 days) | 'na' (timing unclear)\n\n"
        "REASONING (1-2 sentences max): Why these scores?\n\n"
        "Output ONLY this JSON structure, no preamble:\n"
        '{"impact_magnitude": <int 1-5>, "reversibility": <int 1-5>, '
        '"time_to_realization": "<string>", "reasoning": "<short>"}'
    )
    try:
        result = llm.call(prompt, tier="enrich", max_tokens=200)
        if not result:
            return None
        # Extract JSON from response
        text = result.strip()
        if text.startswith("```"):
            text = text.split("```")[1] if "```" in text else text
            if text.startswith("json"):
                text = text[4:]
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0:
            log.warning(f"materiality_v2: no JSON found in: {text[:200]}")
            return None
        data = json.loads(text[start : end + 1])
        # Validate
        imp = float(data.get("impact_magnitude", 0))
        rev = float(data.get("reversibility", 0))
        time = (data.get("time_to_realization") or "na").strip().lower()
        if time not in TIME_FACTORS:
            time = "na"
        if not (1 <= imp <= 5) or not (1 <= rev <= 5):
            return None
        return {
            "impact_magnitude": imp,
            "reversibility": rev,
            "time_to_realization": time,
            "reasoning": data.get("reasoning", "")[:300],
        }
    except llm.LLMUnavailableError:
        # #93 Composant A : LLM upstream indisponible (credit / 429). JAMAIS de
        # default silencieux. On laisse remonter l'exception : le caller
        # (recompute_materiality_for_recent_signals) la catch + marque
        # scoring_status='pending_llm' sur le signal pour retry.
        raise
    except json.JSONDecodeError as e:
        log.warning(f"materiality_v2 JSON decode failed: {e}")
        return None
    except Exception as e:
        log.warning(f"materiality_v2 failed: {e}")
        return None


def compute_composite_score(breakdown: dict[str, Any]) -> float | None:
    """Composite score 0-10 from breakdown. Reversibility inverted (lower=more permanent=higher impact)."""
    if not breakdown:
        return None
    imp = breakdown.get("impact_magnitude", 0)
    rev = breakdown.get("reversibility", 0)
    time_factor = TIME_FACTORS.get(breakdown.get("time_to_realization", "na"), 2.0)
    # Reversibility inverse: 1 (irreversible) → 5, 5 (transient) → 1
    rev_inv = 6 - rev
    composite = float(imp) * 0.5 + float(rev_inv) * 0.3 + float(time_factor) * 0.2  # range 1-5
    return float(round(composite * 2.0, 2))  # scale to 0-10


def persist_breakdown(signal_id: int, breakdown: dict[str, Any]) -> None:
    """Persist rubric to signals table."""
    import sqlite3

    from shared import storage

    conn = sqlite3.connect(storage._DB_PATH)
    try:
        conn.execute(
            "UPDATE signals SET impact_magnitude=?, reversibility=?, time_to_realization=?, "
            "materiality_breakdown=? WHERE id=?",
            (
                breakdown["impact_magnitude"],
                breakdown["reversibility"],
                breakdown["time_to_realization"],
                json.dumps(breakdown),
                int(signal_id),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _mark_pending_llm(signal_id: int) -> None:
    """#93 Composant A2 : marque scoring_status='pending_llm' pour retry quand API up."""
    import sqlite3

    from shared import storage

    conn = sqlite3.connect(storage._DB_PATH)
    try:
        conn.execute(
            "UPDATE signals SET scoring_status='pending_llm' WHERE id=?",
            (int(signal_id),),
        )
        conn.commit()
    finally:
        conn.close()


def score_pending_signals_v2(limit: int = 20) -> tuple[int, int, int]:
    """Cron: score signals where impact_magnitude IS NULL. Returns counts.

    #93 (03/06) : sur LLMUnavailableError, marque scoring_status='pending_llm'
    + break la boucle (inutile de bruler les autres signaux quand l'API dit
    non). JAMAIS de drop silencieux.

    Source unique de verite pour "pas encore score" = `impact_magnitude IS NULL`.
    Le scoring_status est informatif (telemetrie / drain manuel), il ne gate PAS
    la requete : sinon un crash LLM tague tout pending_llm et plus rien ne tire
    quand l'API revient (bug constate 05/06 : 70 signaux stuck apres 2-3j off).
    """
    import sqlite3

    from shared import llm, storage

    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT s.id, s.title, s.summary, s.content, s.entities, "
            "       COALESCE(src.credibility, 0.5) AS cred "
            "FROM signals s LEFT JOIN sources src ON s.source_id = src.id "
            "WHERE s.impact_magnitude IS NULL "
            "ORDER BY s.timestamp DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    finally:
        conn.close()
    scored = 0
    failed = 0
    pending_llm = 0
    for r in rows:
        entities = []
        try:
            if r["entities"]:
                entities = json.loads(r["entities"])
        except Exception as e:
            log.debug(f"Materiality entities parse failed (non-blocking): {e}")
        try:
            breakdown = score_materiality_structured(r["title"], r["summary"], r["content"], entities, r["cred"])
        except llm.LLMUnavailableError as e:
            _mark_pending_llm(r["id"])
            pending_llm += 1
            log.error(
                f"materiality_v2 LLM unavailable ({e.reason}) -- signal {r['id']} "
                f"marque pending_llm. Stop boucle, reprise quand API up."
            )
            # Marque les restants comme pending_llm aussi (inutile de tenter)
            for remaining in rows[rows.index(r) + 1 :]:
                _mark_pending_llm(remaining["id"])
                pending_llm += 1
            break
        if breakdown:
            persist_breakdown(r["id"], breakdown)
            # Ligne deja a 'scored' via persist_breakdown via update si on l'ajoute la,
            # mais on garde le marquage explicite ici pour clarte.
            conn = sqlite3.connect(storage._DB_PATH)
            try:
                conn.execute("UPDATE signals SET scoring_status='scored' WHERE id=?", (int(r["id"]),))
                conn.commit()
            finally:
                conn.close()
            scored += 1
        else:
            failed += 1
    log.info(
        f"materiality_v2: {scored} scored, {failed} failed, "
        f"{pending_llm} pending_llm of {len(rows)}"
    )
    return scored, failed, len(rows)
