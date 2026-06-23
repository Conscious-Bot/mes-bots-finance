"""adversarial_research_loop — 4-stage bull/bear/counter/synth loop pour pre-trade research.

Extension de research_brief.py (passive info gather) vers active TENSION RESOLUTION :
au lieu de 3 queries paralleles (facts/consensus/news), 4 stages structurelles
qui se nourrissent l'une l'autre pour catch :
- Stale consensus data (target mean obsolete post-earnings)
- Hidden risks not in headline numbers
- Bull/bear claims that DON'T survive counter-search

Origine : tracer-bullet manuel session 23/06 sur GEV. Le single-pass yfinance
disait target mean $1,211 (+7% upside). Le loop a revele consensus REVU
post-Q1 a $1,216-$1,424 (+30% to +60%), wind tariff $350M FACTORED dans
guidance (pas surprise), Q1 orders +71% +$163B backlog. Materiellement
different output -> codification justifiee.

Architecture :
    run(target, user_id, intent='buy')
        -> stage_1_bull(target) -> claims_bull[]
        -> stage_2_bear(target) -> claims_bear[]
        -> stage_3_counter(target, claims_bull + claims_bear) -> verdicts[]
        -> stage_4_synthesize(bull, bear, verdicts) -> structured_brief
        -> anti-anchoring gate (reuse research_brief)
        -> log to research_brief_log (extended schema)

ANTI-ANCHORING preserve : aucun "achete/vends/recommande/probabilite que",
juste claim grid avec verdict refute/confirme/unverified + evidence + sources.
Decision reste 100% utilisateur (cf [[barrier-held-without-human-2026-06-13]]).

Backends : reuses research_brief._backend() (Bigdata si key, stub sinon).
Future : WebSearch fallback quand Bigdata indispo (requires Anthropic SDK
external_search tool ou Claude Code session).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

# Reuse research_brief infrastructure pour ne pas dupliquer (DRY + cohesion).
from intelligence.research_brief import _backend, _check_no_verdict
from shared import llm

log = logging.getLogger("bot")


class _WebSearchBackend:
    """Backend fallback : Anthropic SDK `web_search` tool quand Bigdata indispo.

    Use case typique : BIGDATA_API_KEY expired/missing. Le model Claude (via
    shared.llm.call) recoit un toolset incluant web_search et synthese les
    resultats en chunks-like structure pour rester compatible avec le pattern
    des autres backends.

    Cost : ~$0.03-0.10 par search (Sonnet input + web_search tool fee).
    Strictement plus cher que Bigdata mais autonomous (pas de subscription).
    """

    def search(self, query_text: str, n_chunks: int = 10) -> list[dict]:
        """Run web search via Anthropic SDK + parse response into chunks format.

        Returns list of dicts {headline, date, source, text} compatible avec
        _BigdataBackend.search() shape pour drop-in remplacement.
        """
        try:
            from anthropic import Anthropic

            from shared.env import env
            client = Anthropic(api_key=env.anthropic_api_key)
            # web_search beta tool, available since 2025-Q2
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",  # cheapest tier, search dominates cost
                max_tokens=2000,
                tools=[{"type": "web_search_20250305", "name": "web_search",
                        "max_uses": min(5, max(2, n_chunks // 3))}],
                messages=[{
                    "role": "user",
                    "content": (
                        f"Search the web for: {query_text}\n\n"
                        f"Return findings as JSON ONLY (no markdown), schema:\n"
                        '{"chunks":[{"headline":"...","date":"YYYY-MM-DD",'
                        '"source":"domain.com","text":"key passage"}]}\n\n'
                        f"Aim for {min(n_chunks, 8)} distinct chunks. Each chunk must "
                        "describe what the source said factually — no recommendations, no "
                        "predictions ('le titre va monter'), no 'buy/sell' verbs."
                    ),
                }],
            )
            # Parse JSON from response (Claude may wrap in markdown fences)
            import json
            text_parts = [
                b.text for b in resp.content
                if getattr(b, "type", None) == "text" and getattr(b, "text", None)
            ]
            raw = "".join(text_parts).strip()
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            try:
                data = json.loads(raw)
                return list(data.get("chunks", []))[:n_chunks]
            except json.JSONDecodeError:
                log.warning("web_search backend: response not JSON, return single chunk")
                return [{"headline": "Web search results",
                         "date": datetime.now(UTC).date().isoformat(),
                         "source": "anthropic_web_search",
                         "text": raw[:1000]}]
        except Exception as e:
            log.warning(f"web_search backend err: {e}")
            return []


def _resolved_backend():
    """Resolve backend with fallback chain : Bigdata > WebSearch > Stub.

    Bigdata if BIGDATA_API_KEY set (live). WebSearch if ANTHROPIC_API_KEY (always
    available in production). Stub last resort si rien.

    Le caller adversarial_research_loop.run() prefere ce resolver vs
    research_brief._backend (qui s'arrete a Bigdata/Stub).
    """
    import os
    if os.environ.get("BIGDATA_API_KEY"):
        try:
            return _backend()  # Bigdata via research_brief
        except Exception as e:
            log.warning(f"Bigdata init fail, fallback web_search: {e}")
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _WebSearchBackend()
    return _backend()  # research_brief._backend returns _StubBackend


ClaimStance = Literal["bull", "bear"]
ClaimVerdict = Literal["confirmed", "refuted", "unverified", "stale_data_revealed"]


@dataclass
class Claim:
    """Une affirmation extraite d'un stage, avec verdict post-counter-search."""
    stance: ClaimStance
    text: str                          # claim verbatim
    evidence_initial: str = ""         # source qui supporte la claim
    verdict: ClaimVerdict = "unverified"
    counter_evidence: str = ""         # source qui refute/confirme apres stage 3
    confidence: int = 50               # 0-100, post-verdict


@dataclass
class LoopResult:
    target: str
    asof: str
    claims_bull: list[Claim] = field(default_factory=list)
    claims_bear: list[Claim] = field(default_factory=list)
    raw_bull_chunks: list[dict] = field(default_factory=list)
    raw_bear_chunks: list[dict] = field(default_factory=list)
    raw_counter_chunks: list[dict] = field(default_factory=list)
    markdown: str = ""
    ok: bool = False
    error: str | None = None
    n_claims_confirmed: int = 0
    n_claims_refuted: int = 0
    n_claims_stale_data: int = 0


def _stage_1_bull(target: str, backend, max_chunks: int = 15) -> list[dict]:
    """Stage 1 : search for the STRONGEST bull case data points.

    Returns raw search chunks. Claim extraction done in synthesis stage
    pour respecter anti-anchoring (Claude humain inspecte chunks et formule
    claims, le code ne fabrique pas de verdict).
    """
    query = (
        f"{target} bull case investment thesis growth catalysts "
        f"recent quarter beat raised guidance backlog orders revenue"
    )
    return backend.search(query, n_chunks=max_chunks)


def _stage_2_bear(target: str, backend, max_chunks: int = 15) -> list[dict]:
    """Stage 2 : adversarial — search for STRONGEST bear case risks.

    Symetrique du stage 1 mais oriente downside : valuation concerns,
    execution risks, hidden tariffs, segment losses, bankruptcy signals,
    short interest, regulatory headwinds.
    """
    query = (
        f"{target} bear case risks valuation concerns earnings miss "
        f"wind loss tariff exposure execution downside short interest"
    )
    return backend.search(query, n_chunks=max_chunks)


def _stage_3_counter(target: str,
                     bull_chunks: list[dict],  # noqa: ARG001  reserve : claim extraction v2
                     bear_chunks: list[dict],  # noqa: ARG001  reserve : claim extraction v2
                     backend, max_chunks: int = 10) -> list[dict]:
    """Stage 3 : counter-evidence search.

    Specifically pulls disconfirming evidence on the STRONGEST claims from
    bull and bear. Le focus = tester :
    - Bull claims : sont-ils supportes par latest data, ou stales pre-earnings ?
    - Bear claims : sont-ils deja factored dans guidance, ou vrais surprises ?
    - Cross-validation : si bull dit X et bear dit Y, lequel survit ?

    En pratique : query "post Q1 2026 analyst price target revision update"
    pour catch stale data + "guidance management commentary risk factored"
    pour catch bounded risks.
    """
    query = (
        f"{target} post earnings analyst price target revision update "
        f"guidance management commentary risks factored mitigation"
    )
    return backend.search(query, n_chunks=max_chunks)


_EXTRACT_SYSTEM = (
    "Tu extrais des CLAIMS factuelles de chunks de research. STRICT : "
    "tu decris ce que les sources DISENT, jamais ce que l'utilisateur DOIT faire. "
    "Aucun 'achete/vends/recommande/probabilite que'. Juste verbatim des assertions "
    "factuelles avec leur source. Reponse JSON uniquement."
)


def _stage_4_extract_claims(chunks: list[dict], stance: ClaimStance,
                            max_claims: int = 5) -> list[Claim]:
    """Stage 4 : LLM extract claims structurees from raw chunks.

    Input : raw chunks from stage 1 (bull) or stage 2 (bear).
    Output : list of Claim avec text + evidence_initial. Verdict reste
    'unverified' jusqu'au stage 5.

    Cost : 1 LLM call (extract tier = Haiku, cheap). Skip si chunks vide
    OU si premier chunk = stub placeholder (Bigdata indispo).
    """
    if not chunks:
        return []
    # Skip si stub backend (placeholder unique)
    if len(chunks) == 1 and "not configured" in (chunks[0].get("text", "")):
        return []
    # Compose chunks text for LLM
    chunk_text = "\n\n".join(
        f"[{c.get('date', '?')}] {c.get('headline', '?')}\n{c.get('text', '')[:500]}\n(source: {c.get('source', '?')})"
        for c in chunks[:10]
    )
    prompt = (
        f"Voici {len(chunks[:10])} chunks de research orientes case {stance.upper()} "
        f"sur un ticker financier.\n\n{chunk_text}\n\n"
        f"Extract jusqu'a {max_claims} claims factuelles distinctes. Format JSON :\n"
        '{"claims": [{"text": "...", "evidence_initial": "headline + date"}]}\n\n'
        "STRICT : chaque claim doit etre une assertion factuelle (chiffre, fait, "
        "evenement). Pas de 'le titre va monter'. Pas de 'analystes recommandent'. "
        "Juste 'Q1 orders +71% YoY' ou 'Wind segment EBITDA loss $(382)M'."
    )
    try:
        resp = llm.call_json(prompt, tier="extract", max_tokens=1200,
                             system=_EXTRACT_SYSTEM)
        out = []
        for item in (resp.get("claims") or [])[:max_claims]:
            text = (item.get("text") or "").strip()
            if not text:
                continue
            out.append(Claim(
                stance=stance,
                text=text,
                evidence_initial=(item.get("evidence_initial") or "")[:200],
            ))
        return out
    except Exception as e:
        log.warning(f"adversarial_loop stage_4_extract_claims {stance}: {e}")
        return []


def _stage_5_judge_verdicts(bull_claims: list[Claim], bear_claims: list[Claim],
                            counter_chunks: list[dict]) -> tuple[list[Claim], dict[str, int]]:
    """Stage 5 : LLM judge each claim vs counter-evidence chunks.

    Input : claims (bull + bear) + counter-evidence chunks.
    Output : claims updated avec verdict + counter_evidence + confidence,
             plus stats dict {confirmed, refuted, stale_data, unverified}.

    Skip si pas de chunks counter OU si claims vides. Cost : 1 LLM call.
    """
    stats = {"confirmed": 0, "refuted": 0, "stale_data": 0, "unverified": 0}
    all_claims = list(bull_claims) + list(bear_claims)
    if not all_claims:
        return all_claims, stats
    if not counter_chunks or (len(counter_chunks) == 1
                              and "not configured" in (counter_chunks[0].get("text", ""))):
        # Pas de counter data exploitable -> tout reste unverified
        for _c in all_claims:
            stats["unverified"] += 1
        return all_claims, stats

    counter_text = "\n\n".join(
        f"[{c.get('date', '?')}] {c.get('headline', '?')}\n{c.get('text', '')[:500]}"
        for c in counter_chunks[:10]
    )
    claims_text = "\n".join(
        f"{i+1}. [{c.stance}] {c.text}" for i, c in enumerate(all_claims)
    )
    prompt = (
        f"Voici {len(all_claims)} claims a juger contre des chunks counter-evidence :\n\n"
        f"CLAIMS :\n{claims_text}\n\n"
        f"COUNTER-EVIDENCE CHUNKS :\n{counter_text}\n\n"
        "Pour chaque claim, retourne un verdict :\n"
        "- 'confirmed' : counter-evidence supporte la claim\n"
        "- 'refuted' : counter-evidence contredit explicitement\n"
        "- 'stale_data_revealed' : counter-evidence montre data plus recente qui change l'angle\n"
        "- 'unverified' : counter-evidence ni supporte ni refute\n\n"
        'Format JSON : {"verdicts": [{"id": 1, "verdict": "confirmed|refuted|stale_data_revealed|unverified", '
        '"counter_evidence": "headline + raison breve", "confidence": 0-100}]}'
    )
    try:
        resp = llm.call_json(prompt, tier="enrich", max_tokens=1500,
                             system=_EXTRACT_SYSTEM)
        verdicts_by_id = {v.get("id"): v for v in (resp.get("verdicts") or [])}
        for i, claim in enumerate(all_claims, start=1):
            v = verdicts_by_id.get(i)
            if not v:
                stats["unverified"] += 1
                continue
            verdict = (v.get("verdict") or "unverified").lower()
            if verdict not in ("confirmed", "refuted", "stale_data_revealed", "unverified"):
                verdict = "unverified"
            claim.verdict = verdict  # type: ignore[assignment]
            claim.counter_evidence = (v.get("counter_evidence") or "")[:200]
            try:
                claim.confidence = max(0, min(100, int(v.get("confidence", 50))))
            except (ValueError, TypeError):
                claim.confidence = 50
            # Stats key normalize
            key = "stale_data" if verdict == "stale_data_revealed" else verdict
            stats[key] = stats.get(key, 0) + 1
    except Exception as e:
        log.warning(f"adversarial_loop stage_5_judge_verdicts: {e}")
        for _c in all_claims:
            stats["unverified"] += 1
    return all_claims, stats


def _format_markdown(result: LoopResult) -> str:
    """Format adversarial brief per spec :
    - Header avec target + asof
    - Bull case top-3 chunks
    - Bear case top-3 chunks
    - Counter-evidence top-3 chunks
    - Verdict grid : confirmed/refuted/stale_data count
    - Sources

    ANTI-ANCHORING : aucun "tu devrais", aucun ranking direction. Juste
    claim grid + counter-evidence pour decision humaine.
    """
    _VERDICT_EMOJI = {
        "confirmed": "✅",
        "refuted": "❌",
        "stale_data_revealed": "🔄",
        "unverified": "❓",
    }

    def _bullets(chunks: list[dict], limit: int = 3) -> str:
        if not chunks:
            return "_(aucun resultat)_"
        out = []
        for c in chunks[:limit]:
            date = c.get("date", "?")
            head = (c.get("headline") or "?")[:120]
            src = c.get("source", "?")
            out.append(f"• [{date}] {head} — {src}")
        return "\n".join(out)

    def _claims_block(claims: list[Claim]) -> str:
        if not claims:
            return "_(aucun claim extracted — stub backend ou chunks vides)_"
        out = []
        for c in claims:
            emoji = _VERDICT_EMOJI.get(c.verdict, "❓")
            line = f"{emoji} {c.text} _(conf {c.confidence}%)_"
            if c.counter_evidence:
                line += f"\n    └─ counter: {c.counter_evidence[:100]}"
            out.append(line)
        return "\n".join(out)

    parts = [
        f"🔬 *ADVERSARIAL BRIEF* — `{result.target}`",
        f"_asof : {result.asof}_",
        "",
        "═══ *BULL CLAIMS* ═══",
        _claims_block(result.claims_bull),
        "",
        "═══ *BEAR CLAIMS* ═══",
        _claims_block(result.claims_bear),
        "",
        "═══ *RAW SOURCES (Stage 1-3 chunks)* ═══",
        f"_Bull stage : {len(result.raw_bull_chunks)} chunks_",
        _bullets(result.raw_bull_chunks, limit=3),
        "",
        f"_Bear stage : {len(result.raw_bear_chunks)} chunks_",
        _bullets(result.raw_bear_chunks, limit=3),
        "",
        f"_Counter stage : {len(result.raw_counter_chunks)} chunks_",
        _bullets(result.raw_counter_chunks, limit=3),
        "",
        "═══ *VERDICT GRID* ═══",
        f"✅ Confirmed : {result.n_claims_confirmed}  |  "
        f"❌ Refuted : {result.n_claims_refuted}  |  "
        f"🔄 Stale data : {result.n_claims_stale_data}  |  "
        f"❓ Unverified : {len(result.claims_bull) + len(result.claims_bear) - result.n_claims_confirmed - result.n_claims_refuted - result.n_claims_stale_data}",
        "",
        "─────",
        "_Pattern : tracer-bullet GEV 23/06/2026._",
        "_Sources : Bigdata.com (si key) ou WebSearch fallback._",
        "_Aucune direction. Toi de calibrer._",
    ]
    return "\n".join(parts)


def run(target: str, user_id: str, intent: str = "buy") -> LoopResult:
    """Execute the 4-stage adversarial loop.

    Args:
        target: ticker (AAPL) ou theme (AI data center power)
        user_id: pour rate-limit + audit (reuse research_brief_log schema)
        intent: 'buy' | 'sell' | 'trim' | 'review' — biaise les queries

    Returns:
        LoopResult avec markdown + raw chunks + verdict grid.
    """
    target = (target or "").strip()
    asof = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    result = LoopResult(target=target, asof=asof)

    if not target or len(target) > 100:
        result.error = "Cible invalide. Format : ticker (AAPL) ou theme court."
        return result

    backend = _resolved_backend()

    try:
        result.raw_bull_chunks = _stage_1_bull(target, backend)
        result.raw_bear_chunks = _stage_2_bear(target, backend)
        result.raw_counter_chunks = _stage_3_counter(
            target, result.raw_bull_chunks, result.raw_bear_chunks, backend,
        )
    except Exception as e:
        result.error = f"Backend search failed: {e}"
        log.warning(f"adversarial_loop {target}: {e}")
        return result

    # Stage 4 : LLM extract claims structurees from raw chunks (skip si stub).
    try:
        result.claims_bull = _stage_4_extract_claims(result.raw_bull_chunks, "bull")
        result.claims_bear = _stage_4_extract_claims(result.raw_bear_chunks, "bear")
    except Exception as e:
        log.warning(f"adversarial_loop stage_4: {e}")

    # Stage 5 : LLM judge each claim vs counter-evidence. Mutates claims in-place.
    try:
        _all_claims, stats = _stage_5_judge_verdicts(
            result.claims_bull, result.claims_bear, result.raw_counter_chunks,
        )
        # Re-split into bull/bear (mutating refs maintained)
        result.n_claims_confirmed = stats.get("confirmed", 0)
        result.n_claims_refuted = stats.get("refuted", 0)
        result.n_claims_stale_data = stats.get("stale_data", 0)
    except Exception as e:
        log.warning(f"adversarial_loop stage_5: {e}")

    # Format markdown
    result.markdown = _format_markdown(result)

    if _check_no_verdict(result.markdown):
        result.error = "Brief rejete : verdict pattern detecte. Cure : revoir _format_markdown."
        log.error(f"adversarial_loop {target}: anti-anchoring gate triggered")
        return result

    result.ok = True

    # Log to research_brief_log (reuse same table, target_type 'ticker' ou 'theme'
    # selon shape — schema CHECK rejette autres valeurs).
    # TODO v2 : add brief_type column to distinguish 'research' vs 'adversarial'.
    try:
        from shared.storage import insert_research_brief_log
        _tt = "ticker" if (target.isupper() and len(target) <= 6) else "theme"
        insert_research_brief_log(
            user_id=user_id, target=target, target_type=_tt,
            success=True, cost_actual_usd=0.15,  # 4 calls vs 3 pour research_brief
            error_reason=f"adversarial_loop_intent={intent}",  # piggyback intent ici
            response_chars=len(result.markdown),
        )
    except Exception as e:
        log.warning(f"adversarial_loop log fail (non-blocking): {e}")

    return result
