"""Position-card #1 couche 2 : derive_steer = ExitPolicy + SizeAction separes.

Spec user red-team 07/06 Catch 2 :
"position_type gouverne COMMENT tu sors (stop-prix vs invalidation
structurelle). Le cap gouverne ta TAILLE. Ce sont deux axes. Un chokepoint
structurel peut etre sur-dimensionne et necessiter un rightsize sans exit.
Le steer honnete dit les deux : 'HOLD la these (structurelle, intacte) ET
rightsize -X% (11% vs 6% = 2x over)'. Ne laisse pas le type exempter la taille."

Architecture :
- ExitPolicy gouvernee par (position_type x erosion_verdict) -- matrice 3x5
- SizeAction gouvernee par (weight_pct vs cap_pct) -- independant
- Steer = ExitPolicy + SizeAction (jamais l'un n'exempte l'autre)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.sizing_caps import cap_for_conviction

# Position types canoniques (3 mutuellement exclusifs, axe EXIT seul)
_VALID_TYPES = frozenset({"structural", "priced", "tactical"})

# Verdicts erosion (5 + None pour "jamais compute")
_VALID_VERDICTS = frozenset({
    "INTACT", "EROSION_DETECTED", "INVALIDATION_HIT",
    "STALE_UNUPDATED", "REVIEW_DUE_DEGRADED",
})

# Seuil "urgent" pour rightsize : over_cap >= 1pp * URGENT_MULT.
# 1.5x = entre cap et 1.5x cap = rightsize normal ; > 1.5x = urgent.
_URGENT_OVER_CAP_RATIO = 1.5


@dataclass(frozen=True)
class ExitPolicy:
    """Politique d'exit gouvernee par (position_type x erosion_verdict).

    action : enum
      - hold                        : these tient, pas d'action sortie
      - exit_on_invalidation_only   : structural specifique -- exit que sur
                                      condition structurelle, jamais sur prix
      - exit_now                    : invalidation declenchee -> exit immediat
      - tighten_stop                : priced erosion -- resserre le stop existant
      - trim_aggressive             : tactical erosion -- trim partiel rapide
      - review                      : verdict ambigu -- revision manuelle requise
      - review_due_degraded         : L15 fail-closed -- verdict refuse, revue
    """

    action: str
    reason: str
    forbidden: list[str] = field(default_factory=list)
    allowed: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SizeAction:
    """Action de sizing gouvernee par (weight_pct vs cap_pct).

    INDEPENDANTE du type : un structural over-cap reste over-cap.
    target_qty_delta_pct : negatif si trim, 0 si no_action.
    """

    action: str  # "no_action" | "rightsize" | "urgent_rightsize"
    current_weight_pct: float
    cap_pct: float
    over_cap_pp: float
    target_qty_delta_pct: float
    reason: str


@dataclass(frozen=True)
class Steer:
    exit_policy: ExitPolicy
    size_action: SizeAction

    def display(self) -> str:
        """Combinaison lisible des deux axes (jamais fusionnee en un seul mot)."""
        ep = self.exit_policy
        sa = self.size_action
        return (
            f"EXIT : {ep.action.upper()} -- {ep.reason}\n"
            f"SIZE : {sa.action.upper()} ({sa.current_weight_pct:.1f}% vs "
            f"cap {sa.cap_pct:.1f}%, over {sa.over_cap_pp:+.1f}pp) -- {sa.reason}"
        )


# ─── Matrice EXIT POLICY (type x verdict) ────────────────────────────────


def _exit_policy_structural(verdict: str | None) -> ExitPolicy:
    """Structural : exit SEULEMENT sur invalidation-trigger. Jamais sur prix."""
    forbidden = ["full_exit_on_price_drop", "trim_on_volatility"]
    allowed = ["exit_on_invalidation_trigger", "rightsize_for_cap"]
    if verdict == "INTACT" or verdict is None:
        return ExitPolicy(
            action="hold",
            reason="these structurelle intacte, exit reserve invalidation-trigger",
            forbidden=forbidden, allowed=allowed,
        )
    if verdict == "EROSION_DETECTED":
        return ExitPolicy(
            action="review",
            reason="erosion driver detectee -- re-justifie ou alleg via cap",
            forbidden=forbidden, allowed=allowed,
        )
    if verdict == "INVALIDATION_HIT":
        return ExitPolicy(
            action="exit_now",
            reason="invalidation structurelle declenchee -- exit conditioned",
            forbidden=[], allowed=["exit_full"],
        )
    if verdict == "STALE_UNUPDATED":
        return ExitPolicy(
            action="review",
            reason="aucune evidence depuis >45j -- angle mort, revue manuelle",
            forbidden=forbidden, allowed=allowed,
        )
    # REVIEW_DUE_DEGRADED
    return ExitPolicy(
        action="review_due_degraded",
        reason="L15 fail-closed -- LLM degrade, verdict refuse",
        forbidden=forbidden, allowed=allowed,
    )


def _exit_policy_priced(verdict: str | None) -> ExitPolicy:
    """Priced : discipline stop/target normale, downside borne par prix."""
    forbidden = ["ignore_existing_stop"]
    allowed = ["normal_stop_target", "tighten_stop_on_erosion", "rightsize_for_cap"]
    if verdict == "INTACT" or verdict is None:
        return ExitPolicy(
            action="hold",
            reason="these priced intacte, discipline stop existante",
            forbidden=forbidden, allowed=allowed,
        )
    if verdict == "EROSION_DETECTED":
        return ExitPolicy(
            action="tighten_stop",
            reason="erosion driver detectee -- resserre stop pour limiter downside",
            forbidden=forbidden, allowed=allowed,
        )
    if verdict == "INVALIDATION_HIT":
        return ExitPolicy(
            action="exit_now",
            reason="invalidation declenchee -- exit immediat",
            forbidden=[], allowed=["exit_full"],
        )
    if verdict == "STALE_UNUPDATED":
        return ExitPolicy(
            action="review",
            reason="aucune evidence depuis >45j -- angle mort, revue",
            forbidden=forbidden, allowed=allowed,
        )
    return ExitPolicy(
        action="review_due_degraded",
        reason="L15 fail-closed -- LLM degrade, verdict refuse",
        forbidden=forbidden, allowed=allowed,
    )


def _exit_policy_tactical(verdict: str | None) -> ExitPolicy:
    """Tactical : borne par catalyseur/temps, stop serre, trim agressif."""
    forbidden = ["hold_through_catalyst_miss"]
    allowed = ["tight_stop", "aggressive_trim_on_erosion", "rightsize_for_cap"]
    if verdict == "INTACT" or verdict is None:
        return ExitPolicy(
            action="hold",
            reason="these tactique intacte, stop serre existant",
            forbidden=forbidden, allowed=allowed,
        )
    if verdict == "EROSION_DETECTED":
        return ExitPolicy(
            action="trim_aggressive",
            reason="erosion sur tactique -- trim partiel rapide",
            forbidden=forbidden, allowed=allowed,
        )
    if verdict == "INVALIDATION_HIT":
        return ExitPolicy(
            action="exit_now",
            reason="invalidation declenchee -- exit immediat",
            forbidden=[], allowed=["exit_full"],
        )
    if verdict == "STALE_UNUPDATED":
        return ExitPolicy(
            action="review",
            reason="aucune evidence depuis >45j -- catalyseur passe sans trace ?",
            forbidden=forbidden, allowed=allowed,
        )
    return ExitPolicy(
        action="review_due_degraded",
        reason="L15 fail-closed -- LLM degrade, verdict refuse",
        forbidden=forbidden, allowed=allowed,
    )


def _derive_exit_policy(position_type: str, verdict: str | None) -> ExitPolicy:
    """Aiguillage exit policy par type. Verdict None -> traitement INTACT."""
    if position_type not in _VALID_TYPES:
        raise ValueError(
            f"position_type invalide : {position_type!r}. "
            f"Attendu : {sorted(_VALID_TYPES)}",
        )
    if verdict is not None and verdict not in _VALID_VERDICTS:
        raise ValueError(
            f"verdict invalide : {verdict!r}. Attendu : {sorted(_VALID_VERDICTS)} ou None",
        )
    if position_type == "structural":
        return _exit_policy_structural(verdict)
    if position_type == "priced":
        return _exit_policy_priced(verdict)
    return _exit_policy_tactical(verdict)


# ─── SizeAction INDEPENDANT (weight vs cap) ───────────────────────────────


def _derive_size_action(
    current_weight_pct: float, conviction: int | None,
) -> SizeAction:
    """Sizing gouverne par cap_for_conviction. INDEPENDANT du type d'exit.

    - weight <= cap : no_action
    - cap < weight <= URGENT_RATIO x cap : rightsize (compute trim %)
    - weight > URGENT_RATIO x cap : urgent_rightsize (priorite haute)
    """
    cap_pct = cap_for_conviction(conviction) * 100  # cap en %
    over_cap_pp = current_weight_pct - cap_pct

    if over_cap_pp <= 0:
        # Sous le cap. Pas d'action sizing.
        return SizeAction(
            action="no_action",
            current_weight_pct=round(current_weight_pct, 2),
            cap_pct=round(cap_pct, 2),
            over_cap_pp=round(over_cap_pp, 2),
            target_qty_delta_pct=0.0,
            reason=f"weight {current_weight_pct:.1f}% sous cap {cap_pct:.1f}%",
        )

    # Over-cap. Compute trim necessaire pour ramener a cap.
    # target_qty_delta_pct = -(over_cap_pp / current_weight_pct) -- ramene a cap.
    trim_pct = -(over_cap_pp / current_weight_pct) * 100
    is_urgent = current_weight_pct > _URGENT_OVER_CAP_RATIO * cap_pct
    action = "urgent_rightsize" if is_urgent else "rightsize"
    ratio = current_weight_pct / cap_pct if cap_pct > 0 else float("inf")

    return SizeAction(
        action=action,
        current_weight_pct=round(current_weight_pct, 2),
        cap_pct=round(cap_pct, 2),
        over_cap_pp=round(over_cap_pp, 2),
        target_qty_delta_pct=round(trim_pct, 1),
        reason=(
            f"weight {current_weight_pct:.1f}% vs cap {cap_pct:.1f}% "
            f"= {ratio:.2f}x cap (edge non-prouve N<100, M3 sub-Kelly)"
        ),
    )


# ─── API publique ────────────────────────────────────────────────────────


def derive_steer(
    position_type: str,
    erosion_verdict: str | None,
    current_weight_pct: float,
    conviction: int | None,
) -> Steer:
    """Compose ExitPolicy + SizeAction. Les deux axes JAMAIS fusionnes.

    Args:
        position_type: 'structural' | 'priced' | 'tactical'.
        erosion_verdict: l'un des _VALID_VERDICTS, ou None si jamais compute.
        current_weight_pct: weight de la position en % du book (0-100).
        conviction: 1-5 ou None (defense conservative -> cap c5).

    Returns:
        Steer (frozen) avec exit_policy + size_action.

    Raises:
        ValueError si type ou verdict invalide.
    """
    exit_policy = _derive_exit_policy(position_type, erosion_verdict)
    size_action = _derive_size_action(current_weight_pct, conviction)
    return Steer(exit_policy=exit_policy, size_action=size_action)
