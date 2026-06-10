"""Pydantic schema pour config/portfolio_rules.yaml.

Pattern : workflow YAML declaratif (docs/templates/workflow_yaml_pattern.md).
Doctrine L17 LESSONS : declarative ICI (sizing/invalidation/regime), live state
en DB / live data (weight_pct actuel, spot, P&L) vit ailleurs.

Convention regime :
- A = core (full_condition = aucune, gauge degradee sans target_full)
- B = conteste (full_condition = expression textuelle, target_full prix natif
                  vit dans theses.target_full, la gauge l'affiche)

Convention sizing :
- target_weight_pct : poids cible voulu (% du book)
- partial_cap_pct   : seuil au-dessus duquel trim recommande
  - Doit etre >= target_weight_pct quand present (validator)
  - None autorise pour les positions tres petites (Regime B starter)

Convention consensus_ref :
- pt / median : PT analystes (semi-stable, asof date capture)
- PAS de spot-delta : derivable live, jamais fige (L23)

Champs LIVE STATE retires du schema (vivent ailleurs) :
- current_weight_pct -> BookView (qty x prix x fx)
- consensus_delta_pct -> calcul live (current_price - pt)/pt
- alert -> futur monitor #134 (alerte sur cap depasse / invalidation matched)

Loader : `shared/portfolio_rules.py::load_portfolio_rules`.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Regime = Literal["A", "B"]
ConsensusCurrency = Literal["USD", "EUR", "JPY", "KRW", "GBP", "CHF", "CAD"]


class PortfolioRulesMeta(BaseModel):
    """_meta block obligatoire (workflow YAML pattern L17)."""

    model_config = {"extra": "forbid"}

    schema_version: int = Field(ge=1, le=99)
    declared_at: date
    last_modified: date
    next_review_due: date
    doctrine_refs: list[str] = Field(min_length=1)
    schema_module: str = Field(min_length=1)
    description: str = Field(min_length=1, max_length=500)
    source: str | None = Field(default=None, max_length=200)

    @field_validator("last_modified")
    @classmethod
    def _modified_ge_declared(cls, v, info):
        declared = info.data.get("declared_at")
        if declared and v < declared:
            raise ValueError(
                f"last_modified ({v}) doit etre >= declared_at ({declared})"
            )
        return v

    @field_validator("next_review_due")
    @classmethod
    def _review_after_modified(cls, v, info):
        modified = info.data.get("last_modified")
        if modified and v < modified:
            raise ValueError(
                f"next_review_due ({v}) doit etre >= last_modified ({modified})"
            )
        return v


class ConsensusRef(BaseModel):
    """Ancre externe analystes (PT consensus + median + currency, capture datee).

    Pas de spot-delta ici : derivable live, L23 valeur derivable jamais figee.

    Currency OBLIGATOIRE (pas optionnel). Le money-invariant est exact (cf
    L28) : un PT 1690 sans devise est une bombe a retardement. Les PT
    Bigdata/FMP viennent typiquement de la couverture ADR US (USD) meme sur
    des tickers cotes localement (ASML.AS, STMPA.PA, etc.). Sans le tag, le
    spot-delta calcule (spot - pt)/pt melange EUR et USD = signe inverse
    silencieux (le +176056% du money-invariant). Le consumer (card, monitor)
    est responsable de la conversion via fx.
    """

    model_config = {"extra": "forbid"}

    pt: float = Field(gt=0.0)
    median: float = Field(gt=0.0)
    currency: ConsensusCurrency
    asof: date
    note: str | None = Field(default=None, max_length=200)


class ClusterCaps(BaseModel):
    """Caps de concentration cluster (% book)."""

    model_config = {"extra": "forbid"}

    ai_compute_max_pct: float = Field(gt=0.0, le=100.0)


class Position(BaseModel):
    """Regle sizing/invalidation pour une position tenue OU pseudo-ticker (CASH).

    Champs declaratifs uniquement. Le poids actuel vient de BookView,
    pas d'ici. Doctrine L17.

    Cas special : regime=None autorise UNIQUEMENT pour CASH (pas une position
    au sens these, n'a ni invalidation ni full_condition).
    """

    model_config = {"extra": "forbid"}

    target_weight_pct: float = Field(gt=0.0, le=100.0)
    partial_cap_pct: float | None = Field(default=None, gt=0.0, le=100.0)
    regime: Regime | None = None  # None autorise pour CASH uniquement
    invalidation: str | None = Field(default=None, max_length=300)
    full_condition: str | None = Field(default=None, max_length=300)
    consensus_ref: ConsensusRef | None = None
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _cap_above_target(self):
        if self.partial_cap_pct is not None:
            if self.partial_cap_pct < self.target_weight_pct:
                raise ValueError(
                    f"partial_cap_pct ({self.partial_cap_pct}) doit etre >= "
                    f"target_weight_pct ({self.target_weight_pct})"
                )
        return self

    @model_validator(mode="after")
    def _full_condition_only_regime_b(self):
        if self.full_condition is not None and self.regime != "B":
            raise ValueError(
                f"full_condition uniquement autorise pour regime B "
                f"(positions conteste avec full_prix dans theses), "
                f"pas regime {self.regime}"
            )
        return self

    @model_validator(mode="after")
    def _invalidation_required_when_regime_set(self):
        # regime A ou B doit avoir une invalidation (sinon declaratif vide).
        # regime=None (CASH) peut omettre.
        if self.regime in ("A", "B") and not self.invalidation:
            raise ValueError(
                f"invalidation obligatoire pour regime {self.regime} "
                f"(declaratif sans critere d'invalidation = vide)"
            )
        return self


class PortfolioRulesConfig(BaseModel):
    """Top-level container du fichier config/portfolio_rules.yaml."""

    model_config = {"extra": "forbid"}

    meta: PortfolioRulesMeta = Field(alias="_meta")
    cluster_caps: ClusterCaps
    positions: dict[str, Position] = Field(min_length=1)
    # Cap sum-of-weights : > 105% = bump aveugle non catche par les validators
    # per-position. Garde-fou portefeuille-level.
    max_total_weight_pct: float = Field(default=105.0, gt=0.0, le=200.0)

    @field_validator("positions")
    @classmethod
    def _ticker_keys_non_empty(cls, v: dict[str, Position]) -> dict[str, Position]:
        for tk in v:
            if not tk or not tk.strip():
                raise ValueError(f"ticker key vide ou whitespace : {tk!r}")
        return v

    @model_validator(mode="after")
    def _sum_of_weights_within_cap(self):
        total = sum(p.target_weight_pct for p in self.positions.values())
        if total > self.max_total_weight_pct:
            raise ValueError(
                f"Sum target_weight_pct ({total:.1f}%) depasse cap "
                f"({self.max_total_weight_pct}%). Garde-fou portefeuille : "
                f"un bump aveugle (+3% general) ferait sauter la somme sans "
                f"validation per-position. Ajuste les targets ou bump le cap "
                f"explicitement (decision documentee)."
            )
        return self
