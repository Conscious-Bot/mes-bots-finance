"""Tests Phase 1.5 absorption_roadmap — verrouille schema YAML target_allocation.

Verrouille pattern docs/templates/workflow_yaml_pattern.md + L17 LESSONS :
- _meta block obligatoire avec 9 cles requises
- schema_version >= 1
- positions valides Pydantic strict (extra='forbid')
- amounts > 0, pct in [0, 100]
- tickers uniques
- phantoms verdicts dans Literal authorise
- chronologie declared_at <= last_modified <= next_review_due

Si un de ces tests regresse, le YAML est en train de driftter et perd son
contrat. Catche egalement les ajouts d'edit-user qui inventeraient un champ
hors schema (ex `convction` typo).
"""

from __future__ import annotations

from datetime import date

import pytest
import yaml

from intelligence.target_allocation_schema import (
    TargetAllocationConfig,
    TargetAllocationMeta,
    TargetPosition,
)


def _load_yaml_raw() -> dict:
    """Lit le YAML brut sans validation Pydantic."""
    from pathlib import Path
    p = Path(__file__).parent.parent / "config" / "target_allocation.yaml"
    return yaml.safe_load(p.read_text())


def test_yaml_loads_and_validates_strict():
    """Le YAML actuel passe la validation Pydantic stricte (extra=forbid)."""
    raw = _load_yaml_raw()
    cfg = TargetAllocationConfig.model_validate(raw)
    assert cfg.meta.schema_version >= 1
    assert len(cfg.positions) == cfg.meta.positions_count


def test_meta_block_present_and_complete():
    """`_meta` doit contenir les 9 cles canoniques."""
    raw = _load_yaml_raw()
    meta = raw.get("_meta")
    assert meta is not None, "_meta block absent (violation L17)"
    required = {
        "schema_version",
        "declared_at",
        "last_modified",
        "next_review_due",
        "source_capture",
        "total_capital_eur",
        "positions_count",
        "doctrine_refs",
        "schema_module",
        "themes_count",
    }
    missing = required - set(meta.keys())
    assert not missing, f"Cles _meta manquantes : {missing}"


def test_sum_amounts_matches_total_capital():
    """Sum(amount_eur) == _meta.total_capital_eur. Catche edit user incomplet."""
    raw = _load_yaml_raw()
    total_meta = raw["_meta"]["total_capital_eur"]
    sum_positions = sum(p["amount_eur"] for p in raw["positions"])
    assert sum_positions == total_meta, (
        f"Somme positions ({sum_positions}) != _meta.total_capital_eur ({total_meta}). "
        f"Edit user incomplet."
    )


def test_positions_count_matches_meta():
    """len(positions) == _meta.positions_count."""
    raw = _load_yaml_raw()
    assert len(raw["positions"]) == raw["_meta"]["positions_count"]


def test_no_duplicate_tickers():
    """Validator Pydantic catche doublon. Test explicite ici pour clarte."""
    raw = _load_yaml_raw()
    tickers = [p["ticker"] for p in raw["positions"]]
    duplicates = {t for t in tickers if tickers.count(t) > 1}
    assert not duplicates, f"Tickers doublons dans positions : {duplicates}"


def test_chronology_meta_dates_coherent():
    """declared_at <= last_modified <= next_review_due."""
    raw = _load_yaml_raw()
    meta = raw["_meta"]
    declared = meta["declared_at"]
    modified = meta["last_modified"]
    review = meta["next_review_due"]
    assert declared <= modified, (
        f"declared_at ({declared}) > last_modified ({modified})"
    )
    assert modified <= review, (
        f"last_modified ({modified}) > next_review_due ({review})"
    )


def test_extra_field_rejected_in_position():
    """Si user invente un champ `convction` (typo) dans une position, Pydantic catche."""
    bad = {
        "ticker": "NVDA",
        "wrapper": "CTO",
        "nom": "Nvidia",
        "theme": "Compute & semis",
        "tier": "T1",
        "etoile": False,
        "amount_eur": 1000,
        "pct": 1.4,
        "convction": 5,  # typo : champ pas dans schema
    }
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TargetPosition.model_validate(bad)


def test_amount_eur_must_be_positive():
    bad = {
        "ticker": "NVDA",
        "wrapper": "CTO",
        "nom": "Nvidia",
        "theme": "Compute & semis",
        "tier": "T1",
        "etoile": False,
        "amount_eur": 0,
        "pct": 0.0,
    }
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TargetPosition.model_validate(bad)


def test_pct_within_bounds():
    bad = {
        "ticker": "NVDA",
        "wrapper": "CTO",
        "nom": "Nvidia",
        "theme": "Compute & semis",
        "tier": "T1",
        "etoile": False,
        "amount_eur": 1000,
        "pct": 110.0,  # > 100
    }
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TargetPosition.model_validate(bad)


def test_phantom_verdict_literal_enforced():
    """Verdicts hors Literal -> ValidationError."""
    raw = _load_yaml_raw()
    cfg = TargetAllocationConfig.model_validate(raw)
    allowed = {"exit_planned", "open_question", "likely_keep_image_omission", "archived"}
    for ticker, phantom in cfg.phantoms_in_db_not_in_target.items():
        assert phantom.verdict in allowed, (
            f"{ticker} verdict {phantom.verdict!r} hors Literal authorise"
        )


def test_meta_chronology_validators_field_level():
    """Validator field-level Pydantic catche dates incoherentes."""
    from pydantic import ValidationError
    base = {
        "schema_version": 1,
        "declared_at": date(2026, 5, 29),
        "last_modified": date(2026, 5, 28),  # avant declared = BAD
        "next_review_due": date(2026, 9, 30),
        "source_capture": "x",
        "total_capital_eur": 70180,
        "positions_count": 33,
        "doctrine_refs": ["L17"],
        "schema_module": "intelligence.target_allocation_schema",
        "themes_count": {"a": 1},
    }
    with pytest.raises(ValidationError):
        TargetAllocationMeta.model_validate(base)


def test_book_loader_uses_yaml():
    """shared.book._load_target lit le YAML en priorite (Phase 1.5 migration)."""
    from shared.book import _load_target, clear_cache
    clear_cache()
    t = _load_target()
    assert "positions" in t
    assert "_meta" in t
    assert t["_meta"]["total_capital_eur"] == 70180
    assert len(t["positions"]) == 33
