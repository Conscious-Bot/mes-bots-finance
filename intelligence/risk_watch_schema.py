"""Pydantic schema pour config/risk_watch.yaml (Phase 1.5 stage 2).

Pattern : workflow YAML declaratif (docs/templates/workflow_yaml_pattern.md).
Doctrine L17 LESSONS : declarative ICI, live state en DB
(table `risk_signal_evaluations` via shared/storage.py helpers).

Champs LIVE STATE retires du schema (vs ancien JSON) :
- current_status -> shared.storage.get_latest_risk_signal_evaluation()
- last_evaluated_at -> idem
- last_eval_reason -> idem
- last_eval_confidence -> idem
- last_eval_evidence_ids -> idem (JSON serialized)

Strict mode :
- `model_config = {'extra': 'forbid'}` catche drift LLM/user qui inventerait
  un champ (ex 'severity_score' typo).
- Field bornes : rank > 0, ballast_strict_pct in [0, 100], etc.
- Literal {severity}, Literal {mitigation status}, etc.

Loader : `shared/risk_watch.py::load_risk_watch`.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Severity = Literal["critical", "high", "medium", "low"]
SignalWeight = Literal["leading", "major", "amplifier", "minor"]
MitigationStatus = Literal[
    "not_started", "started", "in_progress", "completed", "pending"
]


class RiskWatchMeta(BaseModel):
    """_meta block obligatoire (workflow YAML pattern L17)."""

    model_config = {"extra": "forbid"}

    schema_version: int = Field(ge=1, le=99)
    declared_at: date
    last_modified: date
    next_review_due: date
    doctrine_refs: list[str] = Field(min_length=1)
    schema_module: str = Field(min_length=1)
    description: str = Field(min_length=1, max_length=500)

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


class Exposure(BaseModel):
    """Exposition du book au risque."""

    model_config = {"extra": "forbid"}

    cluster: str = Field(min_length=1, max_length=60)
    pct_book: float = Field(ge=0.0, le=100.0)
    factor: str = Field(min_length=1, max_length=60)


class DrawdownEstimates(BaseModel):
    """Estimations drawdown sous differents scenarios."""

    model_config = {"extra": "forbid"}

    mild_derating_minus30: float = Field(le=0.0)
    capex_pause_minus40: float = Field(le=0.0)
    thesis_break_minus50: float = Field(le=0.0)


class SurveillanceSignal(BaseModel):
    """Signal a surveiller pour le risque. CHAMPS LIVE STATE retires."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=200)
    weight: SignalWeight
    trigger: str = Field(min_length=1, max_length=500)
    # Champs optionnels (selon le type de signal) :
    tickers_to_watch: list[str] | None = None
    threshold: str | None = Field(default=None, max_length=200)
    data_source: str | None = Field(default=None, max_length=200)


class MitigationItem(BaseModel):
    """Item du plan de mitigation."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=200)
    action: str = Field(min_length=1, max_length=500)
    status: MitigationStatus
    progress_pct: int = Field(ge=0, le=100)
    notes: str | None = Field(default=None, max_length=300)


class RiskTarget(BaseModel):
    """Target metrics pour le risque (current vs target)."""

    model_config = {"extra": "forbid"}

    current_ballast_strict_pct: float = Field(ge=0.0, le=100.0)
    target_ballast_strict_pct: float = Field(ge=0.0, le=100.0)
    current_estimated_drawdown_stress: float = Field(le=0.0)
    target_estimated_drawdown_stress: float = Field(le=0.0)
    note: str | None = Field(default=None, max_length=300)


class ArbitrageHistoryItem(BaseModel):
    """Item historique des arbitrages user sur ce risque."""

    model_config = {"extra": "forbid"}

    date: date
    decision: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=500)


class Risk(BaseModel):
    """Un risque declare par l'user (declaratif).

    Pas de current_status / last_eval_* ici - ces champs vivent dans la table
    DB `risk_signal_evaluations`. Render.py merge declaratif + live state."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=60)
    rank: int = Field(ge=1, le=99)
    name: str = Field(min_length=1, max_length=120)
    severity: Severity
    declared_at: date
    exposure: Exposure
    drawdown_estimates: DrawdownEstimates
    ballast_strict_pct: float = Field(ge=0.0, le=100.0)
    ballast_strict_tickers: list[str] = Field(min_length=1)
    scenarios: list[str] = Field(min_length=1)
    surveillance_signals: list[SurveillanceSignal] = Field(min_length=1)
    mitigation_plan: list[MitigationItem]
    target: RiskTarget
    user_arbitrage_history: list[ArbitrageHistoryItem] = Field(default_factory=list)

    @field_validator("surveillance_signals")
    @classmethod
    def _unique_signal_ids(
        cls, v: list[SurveillanceSignal]
    ) -> list[SurveillanceSignal]:
        seen = set()
        for s in v:
            if s.id in seen:
                raise ValueError(f"surveillance_signal id {s.id!r} doublon")
            seen.add(s.id)
        return v


class RiskWatchConfig(BaseModel):
    """Top-level container du fichier YAML."""

    model_config = {"extra": "forbid"}

    meta: RiskWatchMeta = Field(alias="_meta")
    risks: list[Risk] = Field(min_length=1, max_length=20)

    @field_validator("risks")
    @classmethod
    def _unique_risk_ids(cls, v: list[Risk]) -> list[Risk]:
        seen = set()
        for r in v:
            if r.id in seen:
                raise ValueError(f"risk id {r.id!r} doublon")
            seen.add(r.id)
        return v
