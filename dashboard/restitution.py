"""#94 Phase 4 -- Degraded restitution contract.

Spec user 03/06 (degraded_restitution_contract, grave) :

    "Invisible where nothing changed. Honest marker where reasoning missing.
     NEVER fake synthesis. The form that imitates reasoning without
     reasoning = the only thing banned."

3 etats de restitution pour toute surface UI/Telegram :

- COMPUTED : data brutes (positions, prix, Brier, count predictions). Toujours
  visible, jamais affecte par LLM down. Source = code python + DB.

- RETRIEVED : data en cache (analyses anciennes, contrefactuels resolus). Visible
  avec marker d'age si applicable. Source = DB persistence.

- SYNTHESIZED : raisonnement LLM frais (chat reply, narrative analysis,
  why_matters). REMPLACE par marker structure quand LLM down. JAMAIS faux
  raisonnement. Source = appel LLM live.

Le ban absolu : remplir un slot SYNTHESIZED par de la prose qui IMITE le
raisonnement sans l'avoir produit. Exemples interdits :
  - "Le copilot reviendra apres recharge des credits..."     (faux espoir prose)
  - "Le bot pense que NVDA reste solide..."                  (fausse pensee)
  - "Patientez quelques minutes que le service revienne..."  (faux statut)

Le marker accepte :
  ⦿ <object> indisponible (LLM · <reason>)

Symbol ⦿ + label sec + provenance technique. Aucun verbe d'opinion, aucune
phrase complete, aucun futur prometteur. Sec, professionnel, honnete.

ADR 014 hazard A compliance : quand une prediction est produite par
RuleScorer (rule_v1_fallback / rule_v1_shadow), on surface CETTE provenance
explicitement -- "déterministe, hors headline canonique" -- pour eviter
qu'un visiteur cite la proba comme s'il s'agissait d'un score LLM.
"""

from __future__ import annotations

# ─── Marker prefix + canonical helpers ────────────────────────────────────

# Symbol canonique pour les markers degrade. Choisi neutre (ni warning ni
# error) -- signale juste "presence d'un slot avec etat particulier".
LLM_UNAVAILABLE_MARKER_PREFIX = "⦿"


def format_llm_unavailable_marker(
    reason: str | None,
    surface: str = "synthèse",
) -> str:
    """Format le marker canonique pour un slot SYNTHESIZED en panne LLM.

    Pattern strict : "⦿ <surface> indisponible (LLM · <reason>)"
    - Pas de phrase complete prose-like
    - Pas de promesse futur ("reviendra", "patientez")
    - Pas d'opinion fabriquee ("pense que")
    - Provenance technique entre parentheses pour debug + transparence

    Args:
        reason : credit_exhausted / rate_limited / cost_cap_hard / None.
                 None devient "?" pour rester honnete sur l'inconnu.
        surface : nom du slot affecte ("synthèse" defaut, "why_matters",
                  "narrative", "chat_reply", "telegram_brief"). Permet de
                  preciser ce qui manque sans inventer ce qu'il aurait dit.

    Returns:
        str de format "⦿ synthèse indisponible (LLM · credit_exhausted)"
    """
    reason_s = reason if reason else "?"
    return f"{LLM_UNAVAILABLE_MARKER_PREFIX} {surface} indisponible (LLM · {reason_s})"


def format_rule_fallback_provenance(methodology_version: str) -> str:
    """Marker provenance pour une prediction produite par RuleScorer.

    Affiche dans les surfaces per-prediction (chat, dashboard ticker drawer,
    audit trail) quand une prediction porte un tag rule_v1_*. Le marker
    explicite que c'est un score determinist, PAS un score LLM.

    Crucial pour eviter que le visiteur cite une proba shadow/fallback comme
    s'il s'agissait du headline canonique LLM. ADR 014 disambiguation rule.

    Returns:
        str de format "⦿ rule_v1_fallback (déterministe, hors headline canonique)"
        ou "" si methodology_version n'est pas rule-family (pas de marker
        a poser pour v1/v2/etc -- ils sont canoniques par defaut).
    """
    if methodology_version not in ("rule_v1_fallback", "rule_v1_shadow"):
        return ""
    return (
        f"{LLM_UNAVAILABLE_MARKER_PREFIX} {methodology_version} "
        "(déterministe, hors headline canonique)"
    )


def is_synthesized_marker(text: str) -> bool:
    """True si un texte est un marker SYNTHESIZED-down (vs vraie synthese).

    Sert aux surfaces qui distinguent "voici l'analyse LLM" vs "voici un
    marker degrade" pour styling differencie (CSS class, telegram icon).

    Detection robuste : commence par le prefix canonique.
    """
    return text.lstrip().startswith(LLM_UNAVAILABLE_MARKER_PREFIX)
