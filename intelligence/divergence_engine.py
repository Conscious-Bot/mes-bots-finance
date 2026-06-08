"""Moteur PARTAGÉ divergence-reflexivite (cornerstone C6).

PROJECTION-AGNOSTIC : compute_divergence(scale, resolved_inputs, cfg) -- ne
nomme JAMAIS HY_OAS, SMH, BTC. Consomme seulement ResolvedInput. Les noms
des indicateurs entrent par macro_inputs.py / micro_inputs.py.

Primitive (SPEC_CORNERSTONE §1) :
- D = sum_pondéré(z_score_signed) sur croyance_pricée + realite_livrable
  (les sign-theory pointent tous vers "divergence positive" -- on agrege)
- Phi = sum_pondéré(z_score_signed) sur phase_reflexive
  (positif = auto-renforcant, négatif = auto-défaisant)
- F = |D| * (1 + max(0, Phi))  (late + renforcant amplifie ; late+defaisant aussi)

Fail-closed L15 strict :
- n_fresh < min_fresh_inputs_<scale> -> degraded=True, D/Phi/F=None
- Aucun nombre fabrique sur evidence insuffisante.

V0 (sans calibration C7) :
- p_outcome=None : la calibration probabiliste vient en C7 (isotonic sur outcome)
- band = crude (1/sqrt(n)) -- placeholder jusqu'a conformal C7
- weight = prior_tier YAML (S=0.40, A=0.25, B=0.10) -- skill-weight gagne post-track-record
"""

from __future__ import annotations

import logging
import math
from typing import Literal

from intelligence.divergence_schema import DivergenceReading, ResolvedInput

log = logging.getLogger(__name__)

# Bucket constants (cf YAML inputs.macro/micro.<bucket>)
_BUCKETS_DIVERGENCE = {"croyance_pricee", "realite_livrable"}
_BUCKET_PHASE = "phase_reflexive"


def _weighted_mean(values_weights: list[tuple[float, float]]) -> float | None:
    """Compute sum(v*w) / sum(w). Returns None if empty or sum_w == 0."""
    if not values_weights:
        return None
    sum_vw = sum(v * w for v, w in values_weights)
    sum_w = sum(w for _, w in values_weights)
    if sum_w == 0:
        return None
    return sum_vw / sum_w


def compute_divergence(
    scale: Literal["macro", "micro"],
    resolved_inputs: list[ResolvedInput],
    cfg: dict,
) -> DivergenceReading:
    """Primitive D/Phi/F. Pure et agnostique de la projection.

    Args:
        scale: 'macro' (cycle / crisis gauge) ou 'micro' (consensus per ticker).
        resolved_inputs: list[ResolvedInput] -- deja resolus par macro_inputs/
            micro_inputs (z-score signé, freshness, weight, etc.).
        cfg: dict parse de config/divergence.yaml (yaml.safe_load).

    Returns:
        DivergenceReading frozen avec D/Phi/F ou degraded=True.
    """
    methodology_version = cfg.get("methodology_versions", {}).get(scale, f"divergence_{scale}_v0")
    fail_closed_cfg = cfg.get("fail_closed", {})

    # 1. Filter fresh inputs
    fresh = [i for i in resolved_inputs if i.fresh]
    min_fresh = fail_closed_cfg.get(f"min_fresh_inputs_{scale}", 2)

    if len(fresh) < min_fresh:
        return DivergenceReading(
            scale=scale,
            D=None, phase=None, fragility=None,
            p_outcome=None, band_lo=None, band_hi=None,
            drivers=[],
            confidence=None,
            effective_asof=None,
            n_inputs_fresh=len(fresh),
            n_inputs_total=len(resolved_inputs),
            degraded=True,
            degraded_reason=f"fail_closed: n_fresh={len(fresh)} < min_fresh={min_fresh} (L15)",
            methodology_version=methodology_version,
        )

    # 2. Bucket aggregation
    # Tous les z_score_signed pointent vers "divergence positive" (theorie figee).
    # On agrege globalement croyance_pricee + realite_livrable comme la divergence,
    # et phase_reflexive separement comme la phase.
    divergence_pairs = [
        (i.z_score_signed, i.weight)
        for i in fresh if i.bucket in _BUCKETS_DIVERGENCE
    ]
    phase_pairs = [
        (i.z_score_signed, i.weight)
        for i in fresh if i.bucket == _BUCKET_PHASE
    ]

    D = _weighted_mean(divergence_pairs)
    phi = _weighted_mean(phase_pairs)

    # Si aucun input dans buckets divergence -> degraded
    if D is None:
        return DivergenceReading(
            scale=scale,
            D=None, phase=None, fragility=None,
            n_inputs_fresh=len(fresh), n_inputs_total=len(resolved_inputs),
            degraded=True,
            degraded_reason="fail_closed: aucun fresh input dans croyance_pricee/realite_livrable",
            methodology_version=methodology_version,
        )

    # phi = 0 si phase_pairs vide (pas de phase signal -> on suppose neutre)
    if phi is None:
        phi = 0.0

    # 3. Fragilite : amplification par phase positive (late + renforcant)
    # F = |D| * (1 + max(0, phi))
    # Late+renforcant (phi>0) amplifie ; phase neutre/defaisante (phi<=0) -> F = |D|
    F = abs(D) * (1.0 + max(0.0, phi))

    # 4. Band V0 : crude 1/sqrt(n) -- conformal vient en C7
    band_width = 1.0 / math.sqrt(len(fresh))
    band_lo = F - band_width
    band_hi = F + band_width

    # 5. Confidence V0 : 1 - band_width (normalise simple)
    confidence = max(0.0, min(1.0, 1.0 - band_width))

    # 6. Effective as-of : le plus vieux contributeur (M1 honnete)
    effective_asof = min(i.asof for i in fresh)

    # 7. Drivers : pour display (pas pour logique). PROJECTION-AGNOSTIC : on
    # passe juste les champs ResolvedInput pertinents.
    drivers = [
        {
            "name": i.name,
            "bucket": i.bucket,
            "tier": i.tier,
            "z_signed": round(i.z_score_signed, 3),
            "weight": round(i.weight, 3),
            "asof": i.asof,
            "source": i.source,
            "raw_value": i.raw_value,
            "percentile": i.percentile,
            "delta": i.delta,
        }
        for i in fresh
    ]

    return DivergenceReading(
        scale=scale,
        D=round(D, 4),
        phase=round(phi, 4),
        fragility=round(F, 4),
        p_outcome=None,  # V0 : calibration C7 a venir
        band_lo=round(band_lo, 4),
        band_hi=round(band_hi, 4),
        drivers=drivers,
        confidence=round(confidence, 4),
        effective_asof=effective_asof,
        n_inputs_fresh=len(fresh),
        n_inputs_total=len(resolved_inputs),
        degraded=False,
        degraded_reason=None,
        methodology_version=methodology_version,
    )
