"""Carte-decision #1 etape 3 : derive_card_steer + 5 regles fail-closed transverses.

Compose CardInputs (etape 2) + derive_steer (couche 2) en SteerVerdict unifie.

5 etats SteerVerdict (mutuellement exclusifs) :
- HOLD       : exit hold + size no_action (these tient, taille OK)
- TRIM_TO_X  : reduce size (over-cap, eroding, trim_aggressive...) -- thes tient
- ADD_TO_X   : add size (under-cap + thes intact + asym OK) -- DESACTIVE par defaut
- EXIT       : exit immediat (invalidation_hit) -- prioritaire sur tout
- REVIEW     : 1 des 5 regles fail-closed declenchee -> ne steer PAS dans le noir

5 regles fail-closed transverses (red-team user (c) "steer sur stale -> mauvais
des mondes : faux avec assurance") :
1. prix stale rouge SLA (>4h) -> REVIEW + bandeau "PRIX STALE"
2. these non-revue > 90j -> REVIEW + bandeau "THESE NON-REVUE Xj+"
3. erosion_verdict == REVIEW_DUE_DEGRADED -> REVIEW + bandeau "VERDICT LLM REFUSE"
4. cours absent (book_line.last_price_native None pour position ouverte) -> REVIEW
5. structural sans structural_justification -> REVIEW (Catch 1 amplifie)

Output structure : SteerOutput frozen avec verdict + dominant_reason + bandeau
+ exit_action + size_action + target_qty_delta_pct (si TRIM/ADD).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from intelligence.card_inputs import CardInputs
from intelligence.position_steer import derive_steer


class SteerVerdict(StrEnum):
    """5 etats canoniques mutuellement exclusifs."""
    HOLD = "HOLD"
    TRIM_TO_X = "TRIM_TO_X"
    ADD_TO_X = "ADD_TO_X"
    EXIT = "EXIT"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class SteerOutput:
    """Sortie composee de derive_card_steer.

    verdict : enum 5-state.
    dominant_reason : 1-liner raison dominante (utilise dans display).
    bandeau : liste raisons fail-closed declenchees (vide si verdict != REVIEW).
    exit_action : action ExitPolicy sous-jacente (couche 2), None si REVIEW.
    size_action : action SizeAction sous-jacente (couche 2), None si REVIEW.
    target_qty_delta_pct : delta qty pour TRIM/ADD (-X% pour trim, 0 sinon).
    cap_pct : cap conviction utilise (pour display).
    """
    verdict: SteerVerdict
    dominant_reason: str
    bandeau: list[str] = field(default_factory=list)
    exit_action: str | None = None
    size_action: str | None = None
    target_qty_delta_pct: float = 0.0
    cap_pct: float | None = None


def _check_fail_closed(inputs: CardInputs) -> list[str]:
    """Applique les 5 regles fail-closed transverses. Retourne liste raisons."""
    bandeau: list[str] = []

    # Regle 1 : prix stale rouge
    if inputs.price_asof_severity == "rouge":
        bandeau.append("PRIX STALE (>4h SLA)")

    # Regle 2 : these non-revue > 90j
    age = inputs.thesis_review_age_days
    if age is not None and age > 90:
        bandeau.append(f"THESE NON-REVUE {age}j+")

    # Regle 3 : erosion LLM refuse
    if inputs.erosion_verdict == "REVIEW_DUE_DEGRADED":
        bandeau.append("VERDICT LLM REFUSE (L15 fail-closed)")

    # Regle 4 : cours absent
    bl = inputs.book_line
    if bl is not None and getattr(bl, "qty", 0):
        qty = getattr(bl, "qty", 0) or 0
        native = getattr(bl, "last_price_native", None)
        if qty > 0 and native is None:
            bandeau.append("COURS ABSENT (last_price_native None)")

    # Regle 5 : structural sans justification (Catch 1 amplifie)
    if inputs.position_type == "structural" and not inputs.structural_justification:
        bandeau.append("STRUCTURAL SANS JUSTIFICATION (Catch 1)")

    return bandeau


def _map_to_verdict(
    exit_action: str, size_action: str, allow_add_steer: bool,
) -> SteerVerdict:
    """Reduction (ExitPolicy.action x SizeAction.action) -> SteerVerdict.

    Priorites (top-down) :
    1. EXIT > tout (invalidation hit)
    2. REVIEW si exit_policy review/review_due_degraded
    3. TRIM si size action rightsize/urgent (Catch 2 : SIZE prime sur HOLD-exit)
    4. TRIM si exit action trim_aggressive ou tighten_stop (couche 2)
    5. ADD si size under-cap-room ET allow_add_steer (defaut OFF)
    6. HOLD sinon
    """
    if exit_action == "exit_now":
        return SteerVerdict.EXIT
    if exit_action in ("review", "review_due_degraded"):
        return SteerVerdict.REVIEW
    if size_action in ("rightsize", "urgent_rightsize"):
        return SteerVerdict.TRIM_TO_X
    if exit_action in ("trim_aggressive", "tighten_stop"):
        return SteerVerdict.TRIM_TO_X
    # ADD desactive par defaut (anti-FOMO red-team user (a))
    if size_action == "under_room" and allow_add_steer:
        return SteerVerdict.ADD_TO_X
    return SteerVerdict.HOLD


def derive_card_steer(inputs: CardInputs) -> SteerOutput:
    """Compose CardInputs -> SteerVerdict unifie. Fail-closed transverse en tete.

    Returns SteerOutput frozen.
    """
    # Etape 1 : fail-closed transverse PRIORITAIRE (rouge sur tout)
    bandeau = _check_fail_closed(inputs)
    if bandeau:
        return SteerOutput(
            verdict=SteerVerdict.REVIEW,
            dominant_reason=bandeau[0],  # raison principale = 1er fail
            bandeau=bandeau,
            exit_action=None,
            size_action=None,
            cap_pct=inputs.cap_for_conviction_pct,
        )

    # Etape 2 : INVALIDATION_HIT prioritaire (verdict erosion contracte)
    if inputs.erosion_verdict == "INVALIDATION_HIT":
        return SteerOutput(
            verdict=SteerVerdict.EXIT,
            dominant_reason="invalidation_trigger declenche -- exit immediat",
            bandeau=[],
            exit_action="exit_now",
            size_action="exit_all",
            cap_pct=inputs.cap_for_conviction_pct,
        )

    # Etape 3 : compose via derive_steer (couche 2) -- 2 axes orthogonaux Catch 2
    try:
        steer = derive_steer(
            position_type=inputs.position_type,
            erosion_verdict=inputs.erosion_verdict,
            current_weight_pct=inputs.weight_pct,
            conviction=inputs.conviction_current,
        )
    except ValueError as e:
        # Type ou verdict invalide -> REVIEW
        return SteerOutput(
            verdict=SteerVerdict.REVIEW,
            dominant_reason=f"derive_steer invalide : {e}",
            bandeau=[],
            cap_pct=inputs.cap_for_conviction_pct,
        )

    # Etape 4 : map a SteerVerdict
    ep_action = steer.exit_policy.action
    sa_action = steer.size_action.action
    verdict = _map_to_verdict(ep_action, sa_action, inputs.allow_add_steer)

    # Etape 5 : raison dominante (1-liner) -- compose les 2 axes quand actifs.
    # Amelioration 08/06 : avant ce fix, TRIM + over-cap masquait l'erosion
    # eventuelle ("over-cap X%" sans mentionner that the thesis is also eroding).
    # User pouvait lire "trim pour over-cap" et manquer "+ these erode aussi".
    # Fix : si EROSION detectee EN PLUS de over-cap, mentionner les 2 axes.
    is_erosion = inputs.erosion_verdict == "EROSION_DETECTED"
    is_over_cap = sa_action in ("rightsize", "urgent_rightsize")

    if verdict == SteerVerdict.EXIT:
        dom = steer.exit_policy.reason
    elif verdict == SteerVerdict.TRIM_TO_X:
        # Composition selon axes actifs
        if is_over_cap and is_erosion:
            # Les DEUX axes parlent : on doit mentionner les 2 sinon user manque info
            dom = (
                f"over-cap {inputs.weight_pct:.1f}% vs cap {steer.size_action.cap_pct:.1f}% "
                f"(trim {steer.size_action.target_qty_delta_pct:+.1f}%) "
                f"+ erosion driver detectee (these en cours de revision)"
            )
        elif is_over_cap:
            dom = (
                f"over-cap : {inputs.weight_pct:.1f}% vs cap {steer.size_action.cap_pct:.1f}% "
                f"(trim qty {steer.size_action.target_qty_delta_pct:+.1f}%)"
            )
        else:
            dom = steer.exit_policy.reason
    elif verdict == SteerVerdict.HOLD:
        dom = "these tient + taille OK"
    elif verdict == SteerVerdict.ADD_TO_X:
        dom = "under-cap + these intact + asym favorable"
    else:  # REVIEW
        # Si erosion verdict en jeu pour structural (mapping -> review), surface
        if inputs.position_type == "structural" and is_erosion:
            dom = (
                "structural + erosion driver detectee -- revue manuelle "
                "(structural protege exit sur prix, mais drivers contestes)"
            )
        else:
            dom = steer.exit_policy.reason

    return SteerOutput(
        verdict=verdict,
        dominant_reason=dom,
        bandeau=[],
        exit_action=ep_action,
        size_action=sa_action,
        target_qty_delta_pct=steer.size_action.target_qty_delta_pct,
        cap_pct=steer.size_action.cap_pct,
    )
