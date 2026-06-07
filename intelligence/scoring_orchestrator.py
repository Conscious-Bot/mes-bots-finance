"""#94 Phase 3 -- ScoringOrchestrator (route LLMScorer <-> RuleScorer).

Spec user 03/06 (resilience_architecture_spine) :
    Orchestrateur thin route entre LLMScorer (sante) et RuleScorer
    (degradation) selon shared.llm.get_llm_status().status. Le caller
    n'a pas a savoir lequel scorer a tire.

Cette phase 3 etablit le routing. Le caller (intelligence.learning ou
futur) substitue son appel signal_scorer_v2 direct par un appel
orchestrator.score(inp) -- on lit le tuple (data, methodology_version)
et on persiste avec le bon tag (ADR 014 hazard B compliance).

Phase 4 (a venir) : restitution.py applique le contrat honest-marker
sur les surfaces UI quand le tag retourne 'rule_v1_fallback' (mode degrade
visible mais factuel, jamais prose-qui-imite).

FLAG OFF par defaut : sans `RESILIENCE_FALLBACK_ENABLED=1`, l'orchestrator
appelle uniquement primary et laisse remonter LLMUnavailableError. Le code
existant (consumers de #93 A1/A2) reste fonctionnel sans modification.

FLAG ON : LLMUnavailableError -> route vers fallback. Le tag persistera
'rule_v1_fallback', deja exclu par canonical_predictions_filter() et
substance_predictions_filter() (ADR 014).
"""

from __future__ import annotations

import logging
from typing import Any

from intelligence.scorers import LLMScorer, RuleScorer, Scorer, ScorerInput
from shared.env import env

log = logging.getLogger(__name__)


# Env flag : par defaut OFF. User opt-in pour activer routing fallback.
# Doc d'usage : exporter RESILIENCE_FALLBACK_ENABLED=1 avant de lancer le bot
# (ou dans le launchd plist, ou dans .env). OFF en CI tant que la calibration
# rule_v1_fallback n'est pas validee.


def _flag_enabled_from_env() -> bool:
    # KNOWN-GAP : env.resilience_fallback_enabled est cache (lecture une fois
    # au boot). Tests qui togglent l'env var doivent appeler env.reset_cache().
    env.reset_cache()
    return env.resilience_fallback_enabled


class ScoringOrchestrator:
    """Thin router : appelle primary, fallback sur LLMUnavailableError si flag ON.

    Le caller invoque orchestrator.score(inp) au lieu de scorer.score(inp).
    Retour : tuple (data_dict, methodology_version_used). Le caller persiste
    avec methodology_version_used comme tag predictions.methodology_version.

    Si primary retourne None (JSON fail / watch / etc), pas de fallback :
    None signifie "scoring abouti mais pas de prediction" (skip propre).

    Si primary raise LLMUnavailableError ET fallback enabled : route vers
    fallback. Le tag retourne sera celui du fallback (e.g. 'rule_v1_fallback').

    Si primary raise LLMUnavailableError ET fallback OFF : remonte
    LLMUnavailableError telle quelle (compat #93 A1/A2 : consumer marque
    scoring_status='pending_llm').

    fallback_enabled : peut etre passe explicitement OU lu depuis env via
    factory `from_env()`. Le constructeur direct sert pour tests.
    """

    def __init__(
        self,
        primary: Scorer,
        fallback: Scorer | None = None,
        fallback_enabled: bool = False,
    ):
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled

    @classmethod
    def from_env(cls) -> ScoringOrchestrator:
        """Factory : LLMScorer + RuleScorer, flag lu depuis env.

        Default prod-ish : LLM en primary, Rule en fallback, flag depuis env
        (OFF par defaut tant que la calibration rule_v1_fallback n'est pas
        validee sur N predictions resolues).
        """
        return cls(
            primary=LLMScorer(),
            fallback=RuleScorer(),
            fallback_enabled=_flag_enabled_from_env(),
        )

    def score(self, inp: ScorerInput) -> tuple[dict[str, Any] | None, str]:
        """Route entre primary et fallback. Retourne (data, methodology_version).

        Si data is None : scoring abouti mais pas de prediction (watch fallout
        ou JSON parse fail). methodology_version reflete neanmoins le scorer
        qui a essaye en dernier (utile pour audit log).

        Si primary raise LLMUnavailableError :
          - flag ON + fallback present -> route fallback
          - flag OFF OU pas de fallback -> propage LLMUnavailableError
        """
        from shared.llm import LLMUnavailableError

        try:
            data = self.primary.score(inp)
            return data, self.primary.methodology_version
        except LLMUnavailableError as e:
            if not (self.fallback_enabled and self.fallback is not None):
                # FLAG OFF : compat #93 A1/A2 -- remonte tel quel
                raise
            # FLAG ON : route fallback. Log structure pour audit + telemetry.
            log.warning(
                f"ScoringOrchestrator : primary LLM unavailable ({e.reason}), "
                f"routing fallback {self.fallback.methodology_version} for {inp.ticker}"
            )
            data = self.fallback.score(inp)
            return data, self.fallback.methodology_version
