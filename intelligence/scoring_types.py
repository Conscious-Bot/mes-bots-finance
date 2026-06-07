"""Structured Pydantic contracts pour les scorers (Phase 1.3 absorption_roadmap).

Source pattern : TradingAgents `agents/utils/structured.py` (LLM output ->
Pydantic validation -> fail-closed on invalid).

Doctrine L15 LESSONS : si un dict de scoring ne valide pas le contrat,
le scorer doit retourner None (skip propre). JAMAIS de coercion silencieuse
qui fabriquerait un score "presque valide" mais incoherent avec le ledger.

API :
- `ScoringDecision` : output contract de `signal_scorer_v2`
- `validate_scoring_dict(d) -> dict | None` : helper qui encapsule la
  try/except ValidationError. Retourne le dict normalise ou None.

Backward compat :
- Le scorer continue de retourner un dict (via `.model_dump()`), pas un
  ScoringDecision instance. Les callers (learning.py, scoring_orchestrator)
  travaillent sur dict comme avant.
- Le modele sert de GATE finale + de contrat documentaire.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

log = logging.getLogger(__name__)

EvidenceStrength = Literal["none", "weak", "moderate", "strong"]
Direction = Literal["bullish", "bearish", "watch"]


class ScoringDecision(BaseModel):
    """Contrat structure de la sortie de signal_scorer_v2.

    Champs alignes 1:1 sur le dict legacy. Aucun champ supprime, ajoute
    ou renomme -- la migration Phase 1.3 est purement additive (validation
    en plus du dict legacy).

    Invariants verrouilles par Pydantic :
    - `probability` et `base_rate` dans [0, 1] (Field constraints, NON
      silent-clamp -- ValidationError si hors bornes)
    - `evidence_strength` Literal {none, weak, moderate, strong} (typo catch)
    - `direction` Literal {bullish, bearish, watch} (typo catch)
    - `horizon_days` dans [1, 365] (signal long-terme reste raisonnable)
    - Strings limitees en longueur (evite ledger pollue avec reasoning de
      10k chars qui tue les rapports)

    Mode strict : `model_config = {'extra': 'forbid'}` pour catcher les
    champs inattendus (drift LLM qui inventerait un champ comme
    `confidence_level` qui passerait silencieusement).
    """

    model_config = {"extra": "forbid", "frozen": True}

    version: str = Field(min_length=1, max_length=16)
    ticker: str = Field(min_length=1, max_length=12)
    horizon_days: int = Field(ge=1, le=365)
    base_rate: float = Field(ge=0.0, le=1.0)
    evidence_strength: EvidenceStrength
    evidence_summary: str = Field(default="", max_length=500)
    anti_anchoring_reason: str = Field(default="", max_length=300)
    probability: float = Field(ge=0.0, le=1.0)
    direction: Direction
    reasoning: str = Field(default="", max_length=500)

    @field_validator("evidence_summary", "anti_anchoring_reason", "reasoning")
    @classmethod
    def _trim_strings(cls, v: str) -> str:
        """Trim whitespace mais conserve le contenu. NPE-safe sur None upstream."""
        return (v or "").strip()

    @field_validator("ticker")
    @classmethod
    def _ticker_uppercase(cls, v: str) -> str:
        """Canonical ticker shape : uppercase, alphanum + dots/dashes uniquement.
        Cas reels : NVDA, MSFT, BRK.B, 4063.T (TSE japonaise), 005930.KS (KRX)."""
        v = v.strip().upper()
        if not v:
            raise ValueError("ticker vide apres strip")
        if not all(c.isalnum() or c in ".-" for c in v):
            raise ValueError(
                f"ticker {v!r} contient des caracteres invalides "
                f"(autorise: alphanum + . + -)"
            )
        return v


def validate_scoring_dict(d: dict[str, Any]) -> dict[str, Any] | None:
    """Valide un dict de scoring contre ScoringDecision.

    Retourne :
    - Le dict normalise (via `.model_dump()`) si valide
    - None si ValidationError (L15 fail-closed -- caller skip propre)

    Logue un `warning` structure sur ValidationError pour audit trail.
    Pas de retry, pas de coercion -- doctrine L15.

    Pourquoi un helper plutot que l'appel direct dans le scorer : permet
    aux tests d'auditer la validation isolement (test_scoring_decision.py)
    sans avoir a mocker l'integralite de la pipeline LLM.
    """
    try:
        decision = ScoringDecision(**d)
        return decision.model_dump()
    except ValidationError as e:
        log.warning(
            "ScoringDecision validation failed (L15 fail-closed return None) : "
            f"errors={e.errors()} input_keys={list(d.keys())}"
        )
        return None
