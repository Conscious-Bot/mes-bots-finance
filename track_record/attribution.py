"""B : attribution causale 2x2 process × outcome (le saut qualitatif).

Spec red-team 07/06 nuit DECISION_QUALITY_ENGINE B.

Question superieure : pas "la ligne a-t-elle surperforme ?" mais "a-t-elle
surperforme pour la RAISON ecrite a l'entree ?". La calibration sur outcomes
seule est aveugle au quadrant raison-fausse/outcome-juste = chance deguisee
en talent = mode d'echec central.

Quadrants :
                outcome bon              outcome mauvais
raison juste    SKILL (size ca)          SOUND_PROCESS (ne pas desapprendre)
raison fausse   LUCK (le quadrant qui    LEARNING (vrai apprentissage)
                ruine)

+ UNATTRIBUTABLE quand residu domine -- L15 fail-closed (pas de story forcee
quand on n'explique pas le mouvement).

Mecanisation de "raison juste" :
1. Driver-hit test : le KPI nomme dans epic_driver a-t-il bouge dans la
   direction et la magnitude predites ? (objectif car KPI mesurable, force par A)
2. Decomposition du return : excess_return ≈ Δfondamental + Δmultiple + residu.
   Le canal nomme (price_channel) domine-t-il la decompo ?
3. Kill-criteria respectes : booleen depuis le journal de monitoring existant.

Doctrine :
- L15 : residu_dominance >= 0.5 -> UNATTRIBUTABLE, jamais story fabriquee
- L16 : entry est l'enregistrement A0 PIT, jamais revise
- Anti-double-instrumentation L4 : kill_criteria_respected lit le journal de
  monitoring existant, pas re-implemente ici
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Quadrant(StrEnum):
    """5 quadrants attribution. UNATTRIBUTABLE est le 5e fail-closed L15."""
    SKILL = "right_reason_right_outcome"
    LUCK = "wrong_reason_right_outcome"   # le quadrant qui ruine
    SOUND_PROCESS = "right_reason_wrong_outcome"
    LEARNING = "wrong_reason_wrong_outcome"
    UNATTRIBUTABLE = "unattributable"


# === Input contracts ======================================================


@dataclass(frozen=True, slots=True)
class EpicDriver:
    """Driver structure decla A0. Force par schema Pydantic upstream.

    - kpi : nom canonique du KPI mesurable (ex 'gross_margin_bps', 'eps_growth_pct')
    - direction : 'up' | 'down'
    - magnitude : seuil predit (ex +150 bps, +30%)
    - price_channel : 'fundamental' | 'multiple' (par quel canal ca doit toucher
      le prix)
    """
    kpi: str
    direction: str  # 'up' | 'down'
    magnitude: float
    price_channel: str  # 'fundamental' | 'multiple'


@dataclass(frozen=True, slots=True)
class EntryView:
    """Sous-vue immuable de l'entree A0 PIT (issue de thesis_integrity_log).

    Seuls les champs pertinents pour attribution. Le reste reste dans la chain
    pour audit complet.
    """
    thesis_id: int
    ticker: str
    conviction: int
    epic_driver: EpicDriver
    benchmark_ticker: str
    entry_ts: str


@dataclass(frozen=True, slots=True)
class ReturnDecomposition:
    """Decomposition causale du excess return.

    excess_return ≈ fundamental + multiple + residual.
    - fundamental : ΔEPS * P/E_entry (effet realise vs predit)
    - multiple : (P/E_exit - P/E_entry) * EPS_realized (re-rating)
    - residual : ce qui reste inexplique par les 2 canaux

    Si residual domine (>= 0.5 * sum(abs(v))), UNATTRIBUTABLE : L15 fail-closed.
    """
    fundamental: float
    multiple: float
    residual: float


@dataclass(frozen=True, slots=True)
class RealizedView:
    """Etat realise a horizon. Source : decompose_return helper (TBD C wire) +
    monitoring journal pour kill_criteria_respected.

    - kpi_move_dir : 'up' | 'down' direction observee du KPI
    - kpi_move : magnitude observee (signe positif si up, negatif si down)
    - return_decomposition : decompo {fundamental, multiple, residual}
    - kill_criteria_respected : depuis le journal monitoring (kill_criteria_monitor)
    - excess_return : total - benchmark sur horizon
    - outperf_threshold : seuil pour outcome 'good' (ex 0.0 = neutre)
    """
    kpi_move_dir: str
    kpi_move: float
    return_decomposition: ReturnDecomposition
    kill_criteria_respected: bool
    excess_return: float
    outperf_threshold: float = 0.0


# === Core attribution =====================================================


def attribute_decision(
    entry: EntryView,
    realized: RealizedView,
) -> dict:
    """Adjuge un (entry, realized) en 1 des 5 quadrants attribution.

    Args:
        entry : A0 PIT enregistre (driver structure + benchmark fige)
        realized : etat observe a horizon (decompo return + kpi observation +
          kill_criteria respect)

    Returns:
        dict :
        - 'quadrant' : Quadrant enum
        - 'driver_hit' : bool (KPI a-t-il bouge dir+magnitude predite)
        - 'attributed_channel' : 'fundamental' | 'multiple' | 'residual'
        - 'decomp' : dict decomposition return
        - 'unattributable_reason' : str si UNATTRIBUTABLE, sinon None

    Doctrine L15 : si residu domine, UNATTRIBUTABLE (refus de fabriquer cause).
    """
    decomp = {
        "fundamental": realized.return_decomposition.fundamental,
        "multiple": realized.return_decomposition.multiple,
        "residual": realized.return_decomposition.residual,
    }
    abs_total = sum(abs(v) for v in decomp.values())

    # L15 : residu domine -> UNATTRIBUTABLE
    if abs_total > 0 and abs(decomp["residual"]) >= 0.5 * abs_total:
        return {
            "quadrant": Quadrant.UNATTRIBUTABLE,
            "driver_hit": False,
            "attributed_channel": "residual",
            "decomp": decomp,
            "unattributable_reason": (
                f"residual ({decomp['residual']:+.3f}) >= 50% of "
                f"|decomp| sum ({abs_total:.3f}) -- mouvement non explique par "
                "fundamental+multiple, ne pas fabriquer de cause"
            ),
        }

    # Driver hit test : direction + magnitude
    driver_hit = (
        realized.kpi_move_dir == entry.epic_driver.direction
        and abs(realized.kpi_move) >= entry.epic_driver.magnitude
    )

    # Channel dominant (parmi fundamental + multiple, residual deja exclu)
    non_residual = {k: v for k, v in decomp.items() if k != "residual"}
    dominant = max(non_residual, key=lambda k: abs(non_residual[k]))

    # Reason right : driver_hit ET channel matche price_channel declare ET
    # kill_criteria respectes (process complet)
    reason_right = (
        driver_hit
        and dominant == entry.epic_driver.price_channel
        and realized.kill_criteria_respected
    )

    outcome_good = realized.excess_return >= realized.outperf_threshold

    # 2x2 mapping
    quadrant_map = {
        (True, True): Quadrant.SKILL,
        (True, False): Quadrant.SOUND_PROCESS,
        (False, True): Quadrant.LUCK,
        (False, False): Quadrant.LEARNING,
    }
    q = quadrant_map[(reason_right, outcome_good)]

    return {
        "quadrant": q,
        "driver_hit": driver_hit,
        "attributed_channel": dominant,
        "decomp": decomp,
        "unattributable_reason": None,
        "reason_right": reason_right,
        "outcome_good": outcome_good,
    }


# === Aggregation utilities ================================================


def luck_share(attributions: list[dict]) -> float | None:
    """Part des outcomes bons qui tombent en LUCK.

    Ton vrai taux d'illusion de skill. C'est le verdict cle agrege.

    Returns:
        float in [0, 1] ou None si N_good == 0 (gating L15)
    """
    goods = [a for a in attributions if a["quadrant"] in (Quadrant.SKILL, Quadrant.LUCK)]
    if not goods:
        return None
    luck = sum(1 for a in goods if a["quadrant"] == Quadrant.LUCK)
    return luck / len(goods)


def quadrant_counts(attributions: list[dict]) -> dict[str, int]:
    """Count per quadrant. Surface dashboard read-only."""
    counts = {q.value: 0 for q in Quadrant}
    for a in attributions:
        q = a["quadrant"]
        key = q.value if isinstance(q, Quadrant) else str(q)
        counts[key] = counts.get(key, 0) + 1
    return counts
