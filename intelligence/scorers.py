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
    (signal_scorer_v2) + ajouts pour RuleScorer (phase 2). LLMScorer ignore les
    champs rule-specifiques (signal_score / signal_type / impact_magnitude /
    sentiment) ; RuleScorer ignore les champs LLM-specifiques (content riche).

    LLM-relevant fields :
      title : titre signal (ex: '8-K NVDA Q1 beat').
      summary : resume optionnel (None si pas disponible).
      content : excerpt long texte si dispo (1200 chars max post-truncate).
      entities : liste tickers extraits par NLP (peut etre None).

    Universal fields :
      ticker : ticker cible canonique (NVDA, MSFT, etc -- pas le suffix .DE).
      horizon_days : horizon resolution en jours (28 default V1, variable post-V2).
      source_name : nom source. NOT used in scoring proper (couche credibilite
                    separee). Conserve pour audit trail.

    Rule-relevant fields (None pour LLM-only flow) :
      signal_score : int [0,10] -- score d'evidence du signal (post-pipeline).
      signal_type : str -- categorie ('earnings_beat', 'guidance_up', 'insider_buy', etc).
                    Sert de cle de lookup base_rates empiriques.
      impact_magnitude : float [0,1] -- magnitude impact estimee (pipeline upstream).
      sentiment : 'bullish' / 'bearish' / 'watch' / None -- direction sentiment
                  derive du pipeline upstream (NLP classifier ou tag manuel).
                  RuleScorer ne peut pas la re-deriver ; doit etre fournie.
    """

    title: str
    ticker: str
    horizon_days: int
    summary: str | None = None
    content: str | None = None
    entities: list[str] | None = None
    source_name: str | None = None
    # Rule-specific (None pour LLM path)
    signal_score: int | None = None
    signal_type: str | None = None
    impact_magnitude: float | None = None
    sentiment: str | None = None


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


# ─── RuleScorer (Phase 2 -- plancher determinist) ────────────────────────


# Type alias pour le base-rate fetcher : (signal_type, direction, horizon_days)
# -> dict {rate, n, ci_lo, ci_hi, as_of} ou None. Mockable en test.
_BaseRateFetcher = Any  # Callable[[str, str, int], dict | None]


def _default_base_rate_fetcher(
    signal_type: str, direction: str, horizon_days: int
) -> dict[str, Any] | None:
    """Default backend : intelligence.base_rates.get_empirical_base_rate.

    Retourne None si bucket vide (n < MIN_N_PER_BUCKET) -- RuleScorer
    fallback sur prior 0.55.
    """
    from intelligence import base_rates

    return base_rates.get_empirical_base_rate(
        signal_type=signal_type,
        direction=direction,
        horizon_days=horizon_days,
    )


# Constantes calibration RuleScorer. Plage volontairement plus etroite que
# V2 (LLM = [0.50, 0.95]) pour honnetete : un determinist ne peut pas
# atteindre les memes extremes que le LLM en contexte limite.
_RULE_PROB_MIN = 0.55  # sous ce seuil -> watch (semantique : pas confiant)
_RULE_PROB_MAX = 0.85  # plafond honnete pour un determinist sans contexte texte
_RULE_PRIOR_NO_BASE_RATE = 0.55  # fallback si bucket base_rate vide
# Bumps additionnels (signal-score-based + impact-based). Total maxi ~+0.12
# au-dessus du base_rate pour eviter les valeurs hallucinees-extremes.
_BUMP_SCORE_PER_POINT = 0.03   # par point au-dessus de 7
_BUMP_IMPACT_MAX = 0.05         # impact_magnitude in [0,1] mappe [0, 0.05]


class RuleScorer:
    """Scorer determinist -- plancher quand LLM down (#94 phase 2).

    Strategie : base_rate empirique (intelligence.base_rates) + bumps
    deterministes (signal_score, impact_magnitude). Pas d'embedding text,
    pas de LLM, pas de randomness. Reproductible bit-pour-bit.

    Plage probabilite : [0.55, 0.85]. Volontairement plus etroite que V2 LLM
    pour honnetete : sans elicitation textuelle, on ne peut pas s'engager
    au-dessus de 0.85 ni en-dessous de 0.55 (entre les deux = watch).

    Echec gracieux : si signal_score manque, ou sentiment manque, ou
    evidence trop faible -> return dict avec direction='watch' (PAS None,
    pour que le caller log la skip avec provenance).

    methodology_version : 'rule_v1_fallback' par defaut. Parametrable a
    l'init pour le mode champion-challenger paired (#96) -> 'rule_v1_shadow'.

    Tag canonique : ADR 014 hazard A exclut shadow + fallback du headline
    canonique ET du substance accounting (filters partages).

    base_rate_fetcher : injectable pour test. Default = intelligence.base_rates.
    """

    def __init__(
        self,
        methodology_version: str = "rule_v1_fallback",
        base_rate_fetcher: _BaseRateFetcher | None = None,
    ):
        # Garde : on n'accepte que les deux tags rule-family connus (defense
        # vs typo qui contournerait les filtres canonical/substance).
        if methodology_version not in ("rule_v1_fallback", "rule_v1_shadow"):
            raise ValueError(
                f"RuleScorer methodology_version must be 'rule_v1_fallback' or "
                f"'rule_v1_shadow', got: {methodology_version!r}. "
                "ADR 014 § Substance tier : autres tags polluent le ledger."
            )
        self.methodology_version = methodology_version
        self._fetch_base_rate = base_rate_fetcher or _default_base_rate_fetcher

    @staticmethod
    def _evidence_strength(score: int | None) -> str:
        """Mapping score -> evidence_strength label, aligne sur la grille V2.

        Pas de LLM ici : pure heuristique sur le score d'evidence du pipeline.
        """
        if score is None:
            return "none"
        if score >= 8:
            return "strong"
        if score >= 7:
            return "moderate"
        if score >= 6:
            return "weak"
        return "none"

    @staticmethod
    def _watch_dict(inp: ScorerInput, base_rate: float, reason: str) -> dict[str, Any]:
        """Construct un dict 'watch' complet (jamais None, pour audit trail)."""
        return {
            "version": "rule_v1",
            "ticker": inp.ticker,
            "horizon_days": inp.horizon_days,
            "base_rate": round(base_rate, 3),
            "evidence_strength": RuleScorer._evidence_strength(inp.signal_score),
            "evidence_summary": "",
            "anti_anchoring_reason": reason,
            "probability": round(base_rate, 3),
            "direction": "watch",
            "reasoning": f"RuleScorer (determinist) -> watch. {reason}",
        }

    def score(self, inp: ScorerInput) -> dict[str, Any] | None:
        """Compute proba determinist + direction.

        Retourne TOUJOURS un dict (jamais None) -- direction='watch' encode
        le skip. Le caller log le watch via scoring_trace_json (audit trail).

        Etapes :
        1. base_rate = empirical(signal_type, direction, horizon) ou prior 0.55
        2. evidence_strength = mapping(signal_score)
        3. Si none/weak -> watch (mirror enforcement V2)
        4. Sinon : p = clamp(base_rate + bumps, MIN, MAX)
        5. Si p < MIN -> watch (semantic coherence : P(call correct) < 0.55
           = on ne devrait pas faire le call)
        """
        ev_str = self._evidence_strength(inp.signal_score)
        sentiment = (inp.sentiment or "").lower()
        direction = sentiment if sentiment in ("bullish", "bearish") else "watch"

        # Fetch base_rate (peut etre None si bucket vide -> prior).
        base_rate = _RULE_PRIOR_NO_BASE_RATE
        if inp.signal_type and direction in ("bullish", "bearish"):
            br = self._fetch_base_rate(inp.signal_type, direction, inp.horizon_days)
            if br is not None:
                rate_val = br.get("rate") if isinstance(br, dict) else None
                if isinstance(rate_val, int | float) and 0 <= rate_val <= 1:
                    base_rate = float(rate_val)

        # Enforcement #1 : pas de direction (sentiment watch / None) -> watch.
        if direction == "watch":
            return self._watch_dict(inp, base_rate, "sentiment != bullish/bearish")

        # Enforcement #2 (mirror V2) : evidence none/weak -> watch (non-falsifiable).
        if ev_str in ("none", "weak"):
            return self._watch_dict(inp, base_rate, f"evidence_strength={ev_str}")

        # Compute bumps (determinist).
        score_bump = max(0.0, ((inp.signal_score or 0) - 7) * _BUMP_SCORE_PER_POINT)
        impact_bump = (inp.impact_magnitude or 0.0) * _BUMP_IMPACT_MAX
        prob_raw = base_rate + score_bump + impact_bump
        prob = max(_RULE_PROB_MIN, min(_RULE_PROB_MAX, prob_raw))

        # Enforcement #3 (mirror V2) : prob < 0.55 -> watch (semantic incoherence).
        if prob < _RULE_PROB_MIN:
            return self._watch_dict(inp, base_rate, f"prob_raw={prob_raw:.3f} below MIN")

        return {
            "version": "rule_v1",
            "ticker": inp.ticker,
            "horizon_days": inp.horizon_days,
            "base_rate": round(base_rate, 3),
            "evidence_strength": ev_str,
            "evidence_summary": (
                f"signal_score={inp.signal_score} signal_type={inp.signal_type} "
                f"impact_magnitude={inp.impact_magnitude}"
            ),
            "anti_anchoring_reason": (
                f"Determinist : base_rate {base_rate:.3f} + score_bump "
                f"{score_bump:.3f} + impact_bump {impact_bump:.3f} = {prob_raw:.3f} "
                f"clamped to [{_RULE_PROB_MIN}, {_RULE_PROB_MAX}]."
            ),
            "probability": round(prob, 3),
            "direction": direction,
            "reasoning": (
                f"RuleScorer ({self.methodology_version}) : "
                f"{direction} @ p={prob:.3f} sur {inp.ticker} h={inp.horizon_days}j. "
                f"Pas de LLM context. Plage [{_RULE_PROB_MIN}, {_RULE_PROB_MAX}]."
            ),
        }
