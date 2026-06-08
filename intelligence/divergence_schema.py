"""Schemas Pydantic pour le moteur PARTAGÉ divergence-reflexivite (cornerstone C6).

Contrats input/output figés. L'engine compute_divergence() consomme
ResolvedInput[] et retourne DivergenceReading. L'engine est PROJECTION-AGNOSTIC :
il ne nomme jamais HY_OAS, SMH, BTC -- il ne voit que ResolvedInput.

Hérite : SPEC_CORNERSTONE §7 (architecture code) + QUALITY_BAR (M1 triple).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ResolvedInput(BaseModel):
    """Un input lu, signé-théorie, z-scoré, freshness-checké.

    Construit par macro_inputs.py / micro_inputs.py PUIS passé a l'engine.
    L'engine ne le construit jamais -- il consomme seulement.
    """

    model_config = {"extra": "forbid", "frozen": True}

    name: str = Field(min_length=1, description="Identifier (HY_OAS, T10Y2Y, etc.) -- pour audit drivers, JAMAIS pour logique engine")
    bucket: Literal["croyance_pricee", "realite_livrable", "phase_reflexive"]
    tier: Literal["S", "A", "B"]
    sign_theory: Literal["positive", "negative", "neutral"]
    z_score_signed: float = Field(description="z-score deja multiplie par sign-theory : >0 = vers divergence haute, <0 = vers divergence basse")
    weight: float = Field(ge=0.0, le=1.0, description="poids normalise (prior_tier en V0, gagné post-calibration)")
    asof: str = Field(description="ISO timestamp de l'observation, M1 triple")
    source: str = Field(min_length=1, description="provenance (FRED:BAMLH0A0HYM2, yfinance:SMH, etc.)")
    fresh: bool = Field(description="True si asof - now < max_age_days du YAML ; sinon stale")
    raw_value: float | None = Field(default=None, description="valeur brute (pour audit/display, pas pour calcul)")
    percentile: float | None = Field(default=None, ge=0.0, le=100.0, description="percentile vs historique pour display")
    delta: float | None = Field(default=None, description="delta vs T-1 (trajectoire pour display)")


class DivergenceReading(BaseModel):
    """Output canonique de compute_divergence(scale, inputs).

    p_outcome=None tant que la calibration C7 n'a pas tourne (V0 = pas de
    probabilite calibree, juste D/Phi/F bruts).
    """

    model_config = {"extra": "forbid", "frozen": True}

    scale: Literal["macro", "micro"]

    # Primitives D/Phi/F (None si fail-closed)
    D: float | None = Field(description="Divergence : magnitude signed (>0 = croyance > realite)")
    phase: float | None = Field(description="Phi : phase reflexive (>0 = auto-renforcant, <0 = auto-defaisant)")
    fragility: float | None = Field(description="F = |D| * (1 + max(0, phase)) ; max si late+renforcant")

    # Probabilite calibree (None tant que C7 calibration pas faite OU fail-closed)
    p_outcome: float | None = Field(default=None, ge=0.0, le=1.0)
    band_lo: float | None = Field(default=None)
    band_hi: float | None = Field(default=None)

    # Drivers pour display (pas pour logique)
    drivers: list[dict] = Field(default_factory=list)

    # Confidence + meta
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    effective_asof: str | None = Field(default=None, description="as-of de l'input le plus vieux (M1 honnete)")
    n_inputs_fresh: int = Field(default=0, ge=0)
    n_inputs_total: int = Field(default=0, ge=0)

    # Fail-closed
    degraded: bool = Field(default=False)
    degraded_reason: str | None = Field(default=None)

    # Methodology version (pour self-scoring funnel)
    methodology_version: str = Field(min_length=1)
