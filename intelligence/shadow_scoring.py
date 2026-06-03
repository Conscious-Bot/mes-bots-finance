"""#96 -- Champion-Challenger Shadow Scoring (paired LLM + Rule).

Spec user 03/06 (Spec Champion-Challenger Shadow Scoring, variante b
"independent call") :
    Le shadow scorer est un appel INDEPENDANT, non un rescue. Le primary
    (LLMScorer 'v2') tire son raisonnement ; le shadow (RuleScorer
    'rule_v1_shadow') tire le sien en parallele. Les deux ecrivent des
    predictions distinctes avec methodology_version distincts. La meme
    resolution (price hits stop/target) sert aux deux.

Objectif : mesurer la valeur ajoutee du LLM vs un baseline determinist
gratuit. Delta = Brier(v2) - Brier(rule_v1_shadow) sur la meme distribution
de signaux. Si delta ~ 0 ou inverse, le LLM ne justifie pas son cout.
Comparer via storage.brier_by_methodology('v2') vs ('rule_v1_shadow').

ADR 014 hazard A : 'rule_v1_shadow' deja exclu de canonical + substance
filters. Les predictions shadow vivent dans leur propre famille, n'invade
ni le headline public ni le scorer feed (base_rates, outcome_context).

Distinction avec #94 ScoringOrchestrator :
- #94 ScoringOrchestrator : FALLBACK. LLM raise -> bascule rule (mutex).
  Objectif resilience : garder le bot fonctionnel quand LLM down.
- #96 PairedShadowOrchestrator : PAIRED. Les deux tirent toujours en
  parallele quand LLM up. Objectif mesure : isoler la contribution LLM
  vs baseline gratuit.

Si LLM est down, le paired shadow n'a pas de sens (pas de pair a comparer).
Le caller doit alors switcher vers #94 fallback orchestrator. Cette
distinction est documentee dans la disambiguation rule (ADR 014).

FLAG OFF par defaut : RESILIENCE_SHADOW_ENABLED=1 pour activer. Sans flag,
le shadow ne tire pas -- compat #93 + #94 stricte. OFF en CI tant que
le wire prod n'est pas valide.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from intelligence.scorers import LLMScorer, RuleScorer, Scorer, ScorerInput

log = logging.getLogger(__name__)

# Env flag. Default OFF. Reconnait '1', 'true', 'yes', 'on' (insensitive).
_ENV_FLAG = "RESILIENCE_SHADOW_ENABLED"


def _flag_enabled_from_env() -> bool:
    return os.environ.get(_ENV_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True, slots=True)
class ShadowPairedResult:
    """Resultat d'un appel pair LLM + Rule.

    primary_data : dict de la prediction LLM (v2) -- None si watch ou JSON fail.
    primary_tag : methodology_version du primary scorer (e.g. 'v2').
    shadow_data : dict de la prediction Rule -- None si flag OFF ou si shadow
                  a crash (jamais en pratique, RuleScorer ne raise pas).
    shadow_tag : methodology_version du shadow scorer (e.g. 'rule_v1_shadow')
                 ou None si shadow pas tire.

    Le caller decide quoi inserter en DB :
    - Si primary_data['direction'] in (bullish, bearish) -> register primary
      avec methodology_version=primary_tag
    - Si shadow_data is not None et shadow_data['direction'] != watch ->
      register shadow avec methodology_version=shadow_tag

    Les deux predictions partagent (signal_id, ticker, baseline_date,
    target_date). Le "pair" se reconstruit en SQL par jointure sur
    (signal_id, ticker), filtres par methodology_version.
    """

    primary_data: dict[str, Any] | None
    primary_tag: str
    shadow_data: dict[str, Any] | None
    shadow_tag: str | None


def should_register_prediction(data: dict[str, Any] | None) -> bool:
    """True si data porte une direction registrable (bullish/bearish, non-watch).

    Helper unique pour les deux paths (primary + shadow). Watch et None
    n'engendrent pas de prediction inseree -- ils sont audit-loggables
    mais hors ledger.
    """
    if data is None:
        return False
    return data.get("direction") in ("bullish", "bearish")


def is_paired(result: ShadowPairedResult) -> bool:
    """True si LES DEUX scorers ont produit une prediction registrable.

    Utile pour les calculs Brier delta : ne compare que les pairs (signal,
    ticker) ou v2 ET rule_v1_shadow ont tous deux ecrit une prediction.
    Les "orphelins" (un seul des deux a tire non-watch) sont mesures
    separement.
    """
    return (
        should_register_prediction(result.primary_data)
        and should_register_prediction(result.shadow_data)
    )


class PairedShadowOrchestrator:
    """Orchestrator qui tire primary + shadow en parallele (variante b indep).

    primary : LLMScorer ('v2' canonical) generalement.
    shadow : RuleScorer instancie avec 'rule_v1_shadow' tag.
    enabled : flag d'activation. Default OFF -- shadow ne tire pas.

    Contrat :
    - score(inp) -> ShadowPairedResult
    - LLMUnavailableError du primary REMONTE (pas de catch silencieux).
      Si le LLM est down, le pair n'a pas de sens (le caller doit basculer
      vers #94 fallback orchestrator).
    - Le shadow tire UNIQUEMENT si flag enabled ET primary a abouti sans
      lever LLMUnavailableError. Court-circuit si primary down.
    - Exceptions du shadow N'AFFECTENT JAMAIS le primary path :
      shadow_data=None + warning log, on retourne quand meme la primary
      result.
    """

    def __init__(
        self,
        primary: Scorer,
        shadow: Scorer,
        enabled: bool = False,
    ):
        # Defense : le shadow doit etre un rule-family tag (sinon il
        # contaminerait canonical/substance filters).
        shadow_tag = getattr(shadow, "methodology_version", None)
        if shadow_tag not in ("rule_v1_shadow", "rule_v1_fallback"):
            raise ValueError(
                f"PairedShadowOrchestrator : shadow.methodology_version doit etre "
                f"'rule_v1_shadow' ou 'rule_v1_fallback', got: {shadow_tag!r}. "
                "ADR 014 § Substance tier."
            )
        self.primary = primary
        self.shadow = shadow
        self.enabled = enabled

    @classmethod
    def from_env(cls) -> PairedShadowOrchestrator:
        """Factory : LLMScorer + RuleScorer('rule_v1_shadow') + flag env.

        Default prod-ish quand activation manuelle : shadow tire en pair
        avec primary, tag explicit 'rule_v1_shadow' (ledger segmente).
        """
        return cls(
            primary=LLMScorer(),
            shadow=RuleScorer(methodology_version="rule_v1_shadow"),
            enabled=_flag_enabled_from_env(),
        )

    def score(self, inp: ScorerInput) -> ShadowPairedResult:
        """Tire primary, puis shadow si flag enabled.

        Primary LLMUnavailableError remonte verbatim. Shadow ne court-circuite
        pas (n'est pas un rescue). Le caller doit alors basculer vers le
        ScoringOrchestrator de #94 si fallback voulu.

        Shadow exceptions sont avalees (log warning) -- jamais affecter le
        primary path. C'est le ban absolu : la mesure ne doit jamais
        degrader la prediction principale.
        """
        # Primary path : peut raise LLMUnavailableError. Pas de catch ici.
        primary_data = self.primary.score(inp)
        primary_tag = self.primary.methodology_version

        # Shadow path : court-circuite si flag OFF.
        shadow_data: dict[str, Any] | None = None
        shadow_tag: str | None = None
        if self.enabled:
            try:
                shadow_data = self.shadow.score(inp)
                shadow_tag = self.shadow.methodology_version
            except Exception as e:
                # Ban absolu : shadow ne doit JAMAIS affecter primary. Log
                # + None, on continue. (En pratique RuleScorer ne raise pas,
                # mais defense en profondeur.)
                log.warning(
                    f"PairedShadowOrchestrator : shadow scorer raised on "
                    f"{inp.ticker} -- {type(e).__name__}: {e}. "
                    "Primary result preserved."
                )

        return ShadowPairedResult(
            primary_data=primary_data,
            primary_tag=primary_tag,
            shadow_data=shadow_data,
            shadow_tag=shadow_tag,
        )
