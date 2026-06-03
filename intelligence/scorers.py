"""#94 Scorer Protocol -- linchpin de l'architecture resilience.

Spec user 03/06 (resilience_architecture_spine) :
    Spine : Opus -> Haiku (80% cap) -> [rule+BGE quand LLM down] -> templates
    Linchpin : Scorer Protocol dans intelligence/scorers.py
              (LLMScorer + RuleScorer)
    Orchestrateur thin route entre les deux selon llm_status.

Cette phase 1 etablit le Protocol + LLMScorer adapter. Pas de changement
de comportement -- pure refactor. signal_scorer_v2.score_directional_probability
reste l'implementation backend ; LLMScorer est juste son wrapper signature-stable.

Phase 2 (a venir) : RuleScorer deterministe (BGE analogs + base rates) avec
methodology_version='rule_v1_fallback'.

Phase 3 (a venir) : orchestrator route LLMScorer <-> RuleScorer selon
shared.llm.get_llm_status().status.

Phase 4 (a venir) : restitution.py honest-marker contract pour surfaces UI
quand LLM down (degraded_restitution_contract).

ADR 014 :
- LLMScorer tag methodology_version='v2' (canonical post-J-day)
- RuleScorer tag 'rule_v1_fallback' (plancher LLM down) ou 'rule_v1_shadow'
  (paired challenger pour #96). Tous deux EXCLUS du canonical/substance
  filters (cf shared.storage).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

# ─── Input contract ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ScorerInput:
    """Donnees minimales que tout Scorer recoit pour scorer un (signal, ticker).

    Champs alignes sur la signature historique de score_directional_probability
    (signal_scorer_v2) pour migration zero-friction. Les nouveaux scorers
    (rule, ensemble) recoivent le meme input -- pas de fork de signature.

    title : titre signal (ex: '8-K NVDA Q1 beat').
    summary : resume optionnel (None si pas disponible).
    ticker : ticker cible canonique (NVDA, MSFT, etc -- pas le suffix .DE).
    horizon_days : horizon resolution en jours (28 default V1, variable post-V2).
    content : excerpt long texte si dispo (1200 chars max post-truncate).
    entities : liste tickers extraits par NLP (peut etre None).
    source_name : nom source ('EDGAR_8K', 'StockEdge', etc). NOT used in
                  scoring proper (couche credibilite separee). Conserve pour
                  audit trail.
    """

    title: str
    ticker: str
    horizon_days: int
    summary: str | None = None
    content: str | None = None
    entities: list[str] | None = None
    source_name: str | None = None


# ─── Scorer Protocol ──────────────────────────────────────────────────────


class Scorer(Protocol):
    """Contrat structurel d'un scorer de signal directionnel.

    Tout scorer (LLM, rule, ensemble, future llm_v3) implemente :
    - methodology_version : str -- tag stocke dans predictions.methodology_version
      au moment de l'insert. ADR 014 hazard B (#98) : ce tag est REQUIRED a
      l'insert, jamais default. Le Scorer le porte donc en attribut.
    - score(inp) -> dict | None : retourne la structure standard ou None si
      scoring n'aboutit pas (signal incoherent, evidence none, etc).

    Le dict retourne est aligne sur le contrat historique v2 :
      {
        "version": str,                            # synonyme methodology_version
        "ticker": str,
        "horizon_days": int,
        "base_rate": float in [0, 1],
        "evidence_strength": "none|weak|moderate|strong",
        "evidence_summary": str,
        "anti_anchoring_reason": str,
        "probability": float in [0, 1],
        "direction": "bullish|bearish|watch",
        "reasoning": str,
      }

    Le caller (orchestrator) lit `direction` pour decider register vs skip,
    `probability` pour passer en probability_override, et le dict integral pour
    persister en scoring_trace_json (audit trail #70/#74).

    Exceptions :
    - LLMUnavailableError : remonte telle quelle (NEVER swallow). Le caller
      doit l'attraper pour marquer scoring_status='pending_llm' OU routing
      vers le scorer fallback (orchestrator phase 3).
    - Toute autre exception : le scorer doit retourner None silencieusement
      (log warning OK, pas crash). Le caller skip ce signal.
    """

    methodology_version: str

    def score(self, inp: ScorerInput) -> dict[str, Any] | None:
        ...


# ─── LLMScorer adapter ───────────────────────────────────────────────────


class LLMScorer:
    """Adapter sur intelligence.signal_scorer_v2.score_directional_probability.

    Aucun changement de comportement vs l'appel direct. Sert de point de
    polymorphisme pour l'orchestrator (phase 3) : Orchestrator detient un
    `Scorer`, peut etre LLMScorer en sante / RuleScorer en degradation.

    methodology_version = 'v2' (correspond a SCORER_VERSION du module backend).
    """

    methodology_version: str = "v2"

    def score(self, inp: ScorerInput) -> dict[str, Any] | None:
        """Delegue a score_directional_probability avec la meme signature.

        Si la fonction backend raise LLMUnavailableError, ca remonte : le
        contrat #93 (chokepoint detection) est preserve.
        """
        # Import local pour eviter cycle (signal_scorer_v2 importe shared.llm
        # qui est wired pour le status mecanique).
        from intelligence.signal_scorer_v2 import score_directional_probability

        return score_directional_probability(
            title=inp.title,
            summary=inp.summary,
            ticker=inp.ticker,
            horizon_days=inp.horizon_days,
            content=inp.content,
            entities=inp.entities,
            source_name=inp.source_name,
        )
