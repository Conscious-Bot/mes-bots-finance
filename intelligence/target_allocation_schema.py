"""Pydantic schema pour config/target_allocation.yaml (Phase 1.5 absorption_roadmap).

Pattern : workflow YAML declaratif (docs/templates/workflow_yaml_pattern.md).
Doctrine : L17 LESSONS (declarative YAML, live state en DB).

Strict mode :
- `model_config = {'extra': 'forbid'}` catche les drift (champ invente)
- Field bornes : amounts > 0, pct in [0, 100], tier alphanum simple
- Literal verdicts pour phantoms

Loader : `shared/book.py::_load_target` (transition JSON -> YAML).

Pour ajouter une position : edit le YAML, re-run tests. Le test
`test_target_allocation_yaml_schema.py` revalidate au CI.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PhantomVerdict = Literal[
    "exit_planned",
    "open_question",
    "likely_keep_image_omission",
    "archived",
]


class TargetAllocationMeta(BaseModel):
    """_meta block obligatoire (workflow YAML pattern L17)."""

    model_config = {"extra": "forbid"}

    schema_version: int = Field(ge=1, le=99)
    declared_at: date
    last_modified: date
    next_review_due: date
    source_capture: str = Field(min_length=1, max_length=200)
    total_capital_eur: int = Field(ge=1000, le=10_000_000)
    positions_count: int = Field(ge=1, le=200)
    doctrine_refs: list[str] = Field(min_length=1)
    schema_module: str = Field(min_length=1)
    themes_count: dict[str, int] = Field(min_length=1)

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


class TargetPosition(BaseModel):
    """Une ligne cible de l'allocation 70k."""

    model_config = {"extra": "forbid"}

    ticker: str = Field(min_length=1, max_length=30)
    wrapper: Literal["PEA", "CTO"]
    nom: str = Field(min_length=1, max_length=80)
    theme: str = Field(min_length=1, max_length=40)
    tier: str = Field(min_length=1, max_length=8)
    etoile: bool
    amount_eur: int = Field(ge=1, le=100_000)
    pct: float = Field(ge=0.0, le=100.0)
    note: str | None = Field(default=None, max_length=200)


class Phantom(BaseModel):
    """Position en DB hors cible, verdict reconciliation."""

    model_config = {"extra": "forbid"}

    verdict: PhantomVerdict
    rationale: str = Field(min_length=10, max_length=300)


class TargetAllocationConfig(BaseModel):
    """Top-level container du fichier YAML."""

    model_config = {"extra": "forbid"}

    meta: TargetAllocationMeta = Field(alias="_meta")
    positions: list[TargetPosition] = Field(min_length=1, max_length=100)
    phantoms_in_db_not_in_target: dict[str, Phantom] = Field(default_factory=dict)

    @field_validator("positions")
    @classmethod
    def _unique_tickers(cls, v: list[TargetPosition]) -> list[TargetPosition]:
        """Pas de doublon ticker dans la cible (catche bug user-edit)."""
        seen = set()
        for pos in v:
            if pos.ticker in seen:
                raise ValueError(f"ticker {pos.ticker!r} doublon dans positions")
            seen.add(pos.ticker)
        return v
