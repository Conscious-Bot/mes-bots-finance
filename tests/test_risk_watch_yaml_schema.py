"""Tests Phase 1.5 stage 2 — verrouille schema YAML risk_watch + helpers.

4 axes verifies :
1. YAML loads + valide via Pydantic strict
2. Loader shared.risk_watch retourne dict compatible legacy
3. Storage helpers insert + latest_per_pair fonctionnent
4. Live state hydration merge correctement YAML + DB
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from intelligence.risk_watch_schema import (
    Risk,
    RiskWatchConfig,
    SurveillanceSignal,
)


def _load_yaml_raw() -> dict:
    p = Path(__file__).parent.parent / "config" / "risk_watch.yaml"
    return yaml.safe_load(p.read_text())


# --- Schema validation ----------------------------------------------------


def test_yaml_loads_and_validates_strict():
    """Le YAML passe la validation Pydantic stricte."""
    raw = _load_yaml_raw()
    cfg = RiskWatchConfig.model_validate(raw)
    assert cfg.meta.schema_version >= 1
    assert len(cfg.risks) >= 1


def test_meta_block_present_and_complete():
    """_meta block 7 cles canoniques."""
    raw = _load_yaml_raw()
    meta = raw.get("_meta")
    assert meta is not None
    required = {
        "schema_version", "declared_at", "last_modified", "next_review_due",
        "doctrine_refs", "schema_module", "description",
    }
    missing = required - set(meta.keys())
    assert not missing, f"Cles _meta manquantes : {missing}"


def test_no_live_state_in_declarative_yaml():
    """Le YAML declaratif NE doit PAS contenir current_status, last_eval_*.

    Doctrine L17 : ces champs sont en DB (table risk_signal_evaluations),
    pas dans le YAML user-edited."""
    raw = _load_yaml_raw()
    forbidden_keys = {
        "current_status", "last_evaluated_at", "last_eval_reason",
        "last_eval_confidence", "last_eval_evidence_ids",
    }
    for risk in raw["risks"]:
        for sig in risk["surveillance_signals"]:
            leaked = forbidden_keys & set(sig.keys())
            assert not leaked, (
                f"Signal {sig.get('id')!r} contient des champs LIVE STATE "
                f"interdits dans le YAML declaratif : {leaked}. Violation L17."
            )


def test_chronology_meta_dates_coherent():
    """declared_at <= last_modified <= next_review_due."""
    raw = _load_yaml_raw()
    meta = raw["_meta"]
    assert meta["declared_at"] <= meta["last_modified"]
    assert meta["last_modified"] <= meta["next_review_due"]


def test_signal_id_unique_per_risk():
    """Validator catche signal_id doublon dans 1 risque."""
    from pydantic import ValidationError
    sig = SurveillanceSignal(
        id="x", label="x", weight="major", trigger="x",
    )
    risk_data = {
        "id": "test_risk", "rank": 1, "name": "Test", "severity": "high",
        "declared_at": date(2026, 1, 1),
        "exposure": {"cluster": "X", "pct_book": 50.0, "factor": "Y"},
        "drawdown_estimates": {
            "mild_derating_minus30": -10, "capex_pause_minus40": -20,
            "thesis_break_minus50": -30,
        },
        "ballast_strict_pct": 10.0, "ballast_strict_tickers": ["X"],
        "scenarios": ["s1"],
        "surveillance_signals": [sig.model_dump(), sig.model_dump()],
        "mitigation_plan": [],
        "target": {
            "current_ballast_strict_pct": 10.0, "target_ballast_strict_pct": 20.0,
            "current_estimated_drawdown_stress": -30.0,
            "target_estimated_drawdown_stress": -25.0,
        },
    }
    with pytest.raises(ValidationError, match="doublon"):
        Risk.model_validate(risk_data)


def test_extra_field_rejected_on_signal():
    """User invente un champ -> Pydantic catche."""
    from pydantic import ValidationError
    bad = {
        "id": "x", "label": "x", "weight": "major", "trigger": "x",
        "confidance": 80,  # typo "confidance"
    }
    with pytest.raises(ValidationError):
        SurveillanceSignal.model_validate(bad)


# --- Loader + cache --------------------------------------------------------


def test_load_risk_watch_returns_dict():
    """Loader retourne dict avec _meta + risks (compat ancien format)."""
    from shared.risk_watch import clear_cache, load_risk_watch
    clear_cache()
    cfg = load_risk_watch()
    assert cfg is not None
    assert "_meta" in cfg
    assert "risks" in cfg


def test_get_declarative_signal_helper():
    """get_declarative_signal retourne le signal par (risk_id, signal_id)."""
    from shared.risk_watch import clear_cache, get_declarative_signal
    clear_cache()
    sig = get_declarative_signal("surchauffe_tech_ai", "capex_hyperscaler")
    assert sig is not None
    assert sig["weight"] == "major"
    assert sig["label"].startswith("Hyperscaler")


def test_get_declarative_signal_unknown_returns_none():
    from shared.risk_watch import get_declarative_signal
    assert get_declarative_signal("nope", "nope") is None


# --- Storage helpers + live state hydration -------------------------------


def test_insert_and_get_latest_risk_signal_evaluation(migrated_db):
    """Insert puis latest doit retourner le dernier."""
    from shared.storage import (
        get_latest_risk_signal_evaluation,
        insert_risk_signal_evaluation,
    )
    rid = insert_risk_signal_evaluation(
        risk_id="r1", signal_id="s1", status="at_risk",
        reason="test", confidence=70,
        evidence_ids_json=json.dumps([1, 2, 3]),
        transition="changed",
    )
    assert rid is not None
    latest = get_latest_risk_signal_evaluation("r1", "s1")
    assert latest is not None
    assert latest["status"] == "at_risk"
    assert latest["confidence"] == 70


def test_get_all_latest_returns_one_per_pair(migrated_db):
    """Plusieurs evaluations -> latest seulement (1 par paire)."""
    from shared.storage import (
        get_all_latest_risk_signal_evaluations,
        insert_risk_signal_evaluation,
    )
    insert_risk_signal_evaluation("r1", "s1", "monitoring", "first", 50,
                                  json.dumps([]), "no_change")
    insert_risk_signal_evaluation("r1", "s1", "at_risk", "escalated", 75,
                                  json.dumps([42]), "changed")
    insert_risk_signal_evaluation("r2", "s2", "triggered", "second risk", 90,
                                  json.dumps([1]), "changed")
    all_latest = get_all_latest_risk_signal_evaluations()
    assert all_latest[("r1", "s1")]["status"] == "at_risk"
    assert all_latest[("r2", "s2")]["status"] == "triggered"
    assert len(all_latest) == 2


def test_insert_invalid_status_returns_none(migrated_db):
    """Status hors enum {monitoring, at_risk, triggered, resolved} -> None."""
    from shared.storage import insert_risk_signal_evaluation
    rid = insert_risk_signal_evaluation("r", "s", "invalid_status")
    assert rid is None


def test_load_with_live_state_defaults_to_monitoring(migrated_db):
    """Signal sans evaluation DB -> current_status='monitoring' par defaut."""
    from shared.risk_watch import clear_cache, load_risk_watch_with_live_state
    clear_cache()
    cfg = load_risk_watch_with_live_state()
    assert cfg is not None
    # Sur fixture DB neuve (migrated_db), aucun evaluations -> tous monitoring
    for risk in cfg["risks"]:
        for sig in risk["surveillance_signals"]:
            assert sig["current_status"] == "monitoring"
            assert sig["last_evaluated_at"] is None
            assert sig["last_eval_confidence"] is None


def test_load_with_live_state_overrides_with_db(migrated_db):
    """Insert eval en DB -> hydration retourne ce status."""
    from shared.risk_watch import clear_cache, load_risk_watch_with_live_state
    from shared.storage import insert_risk_signal_evaluation
    insert_risk_signal_evaluation(
        risk_id="surchauffe_tech_ai", signal_id="capex_hyperscaler",
        status="triggered", reason="db override test", confidence=88,
        evidence_ids_json=json.dumps([100, 200]),
    )
    clear_cache()
    cfg = load_risk_watch_with_live_state()
    sigs = cfg["risks"][0]["surveillance_signals"]
    capex_sig = next(s for s in sigs if s["id"] == "capex_hyperscaler")
    assert capex_sig["current_status"] == "triggered"
    assert capex_sig["last_eval_confidence"] == 88
    assert capex_sig["last_eval_evidence_ids"] == [100, 200]
