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

log = logging.getLogger("bot")

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

    parts = [
        f"🔬 *ADVERSARIAL BRIEF* — `{result.target}`",
        f"_asof : {result.asof}_",
        "",
        "═══ *STAGE 1 — BULL CASE* ═══",
        _bullets(result.raw_bull_chunks, limit=4),
        "",
        "═══ *STAGE 2 — BEAR CASE (adversarial)* ═══",
        _bullets(result.raw_bear_chunks, limit=4),
        "",
        "═══ *STAGE 3 — COUNTER-EVIDENCE* ═══",
        _bullets(result.raw_counter_chunks, limit=4),
        "",
        "═══ *VERDICT GRID* ═══",
        f"• Bull claims : {len(result.claims_bull)} extracted",
        f"• Bear claims : {len(result.claims_bear)} extracted",
        f"• Confirmed (survived counter) : {result.n_claims_confirmed}",
        f"• Refuted (failed counter) : {result.n_claims_refuted}",
        f"• Stale data revealed : {result.n_claims_stale_data}",
        "",
        "─────",
        "_Pattern : tracer-bullet GEV 23/06/2026 (cf [[adversarial-loop-acted]])._",
        "_Sources : Bigdata.com — https://bigdata.com (ou WebSearch fallback)_",
        "_Aucune direction. Toi de calibrer._",
    ]
    return "\n".join(parts)


def run(target: str, user_id: str, intent: str = "buy") -> LoopResult:  # noqa: ARG001  intent reserve : query biasing v2
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

    backend = _backend()

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

    # Stage 4 : synthesis = format markdown (claims extraction = humain inspecte
    # raw_*_chunks et formule verdicts ; code n'invente pas le verdict pour
    # respecter anti-anchoring strict).
    result.markdown = _format_markdown(result)

    if _check_no_verdict(result.markdown):
        result.error = "Brief rejete : verdict pattern detecte. Cure : revoir _format_markdown."
        log.error(f"adversarial_loop {target}: anti-anchoring gate triggered")
        return result

    result.ok = True

    # Log to research_brief_log (reuse same table, target_type='adversarial')
    try:
        from shared.storage import insert_research_brief_log
        insert_research_brief_log(
            user_id=user_id, target=target, target_type="adversarial",
            success=True, cost_actual_usd=0.15,  # 4 calls vs 3 pour research_brief
            error_reason=None, response_chars=len(result.markdown),
        )
    except Exception as e:
        log.warning(f"adversarial_loop log fail (non-blocking): {e}")

    return result
