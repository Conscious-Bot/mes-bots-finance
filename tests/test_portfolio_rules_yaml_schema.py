"""Tests pour config/portfolio_rules.yaml + schema Pydantic + loader.

Verrouille :
1. YAML loads + valide via Pydantic strict (extra=forbid)
2. _meta block complet (7 cles canoniques L17)
3. Chronologie dates _meta (declared <= modified <= next_review)
4. Validator partial_cap_pct >= target_weight_pct (sinon nonsense sizing)
5. Validator full_condition uniquement regime B
6. Tous les tickers du YAML existent dans book_index (anti-typo)
7. Loader + helpers retournent les bonnes regles
8. Anti-doublon ticker (cle dict naturellement, mais teste la non-vacuite)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from intelligence.portfolio_rules_schema import (
    ConsensusRef,
    PortfolioRulesConfig,
    Position,
)


def _load_yaml_raw() -> dict:
    p = Path(__file__).parent.parent / "config" / "portfolio_rules.yaml"
    return yaml.safe_load(p.read_text())


# --- Schema validation ----------------------------------------------------


def test_yaml_loads_and_validates_strict():
    """Le YAML passe la validation Pydantic stricte."""
    raw = _load_yaml_raw()
    cfg = PortfolioRulesConfig.model_validate(raw)
    assert cfg.meta.schema_version >= 1
    assert len(cfg.positions) >= 1


def test_meta_block_present_and_complete():
    """_meta block contient les cles canoniques L17."""
    raw = _load_yaml_raw()
    meta = raw.get("_meta")
    assert meta is not None
    required = {
        "schema_version", "declared_at", "last_modified", "next_review_due",
        "doctrine_refs", "schema_module", "description",
    }
    missing = required - set(meta.keys())
    assert not missing, f"Cles _meta manquantes : {missing}"


def test_chronology_meta_dates_coherent():
    """declared_at <= last_modified <= next_review_due."""
    raw = _load_yaml_raw()
    meta = raw["_meta"]
    assert meta["declared_at"] <= meta["last_modified"]
    assert meta["last_modified"] <= meta["next_review_due"]


def test_partial_cap_gte_target_weight():
    """Validator catche un cap < target (sizing aberrant)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="partial_cap_pct"):
        Position.model_validate({
            "target_weight_pct": 5.0,
            "partial_cap_pct": 3.0,  # < target, invalide
            "regime": "A",
            "invalidation": "test",
        })


def test_full_condition_only_regime_b():
    """Validator catche full_condition sur regime A (nonsense)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="full_condition"):
        Position.model_validate({
            "target_weight_pct": 5.0,
            "regime": "A",
            "invalidation": "test",
            "full_condition": "exit if X",  # A interdit
        })


def test_partial_cap_none_allowed():
    """partial_cap_pct=None accepte (positions tres petites Regime B)."""
    p = Position.model_validate({
        "target_weight_pct": 1.5,
        "partial_cap_pct": None,
        "regime": "B",
        "invalidation": "test",
        "full_condition": "exit if X",
    })
    assert p.partial_cap_pct is None


def test_consensus_ref_dates_valid():
    """ConsensusRef valide PT > 0, median > 0, currency obligatoire, date valide."""
    ref = ConsensusRef.model_validate({
        "pt": 100.0,
        "median": 95.0,
        "currency": "USD",
        "asof": date(2026, 6, 10),
    })
    assert ref.pt == 100.0
    assert ref.currency == "USD"
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ConsensusRef.model_validate({
            "pt": -10.0,  # negatif interdit
            "median": 95.0,
            "currency": "USD",
            "asof": date(2026, 6, 10),
        })


def test_consensus_ref_currency_required():
    """Verrou money-invariant L28 : currency obligatoire sur ConsensusRef.

    Sans devise, un PT 1690 sur ASML.AS (cote EUR) vs spot EUR -> signe inverse
    silencieux du delta consensus (USD vs EUR melange = +176056% du money-invariant).
    """
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="currency"):
        ConsensusRef.model_validate({
            "pt": 1690.0,
            "median": 1730.0,
            "asof": date(2026, 6, 10),
            # currency manquant
        })


def test_consensus_ref_currency_invalid_rejected():
    """Devise hors enum (typo 'usd' minuscule, ou 'EURO') -> Pydantic catche."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ConsensusRef.model_validate({
            "pt": 1690.0,
            "median": 1730.0,
            "currency": "usd",  # minuscule = drift
            "asof": date(2026, 6, 10),
        })


def test_sum_of_target_weights_within_cap():
    """Garde-fou portefeuille : Sum target_weight_pct <= 105% (cap par defaut).

    Sans ce validator un bump aveugle (+3% general) ferait sauter la somme
    sans validation per-position.
    """
    from pydantic import ValidationError
    bad_raw = {
        "_meta": {
            "schema_version": 1,
            "declared_at": date(2026, 6, 10),
            "last_modified": date(2026, 6, 10),
            "next_review_due": date(2026, 9, 30),
            "doctrine_refs": ["test"],
            "schema_module": "intelligence.portfolio_rules_schema",
            "description": "test",
        },
        "cluster_caps": {"ai_compute_max_pct": 70},
        "positions": {
            # Σ = 110% > 105% cap
            "A": {"target_weight_pct": 50.0, "regime": "A", "invalidation": "x"},
            "B": {"target_weight_pct": 40.0, "regime": "A", "invalidation": "x"},
            "C": {"target_weight_pct": 20.0, "regime": "A", "invalidation": "x"},
        },
    }
    with pytest.raises(ValidationError, match="Sum target_weight_pct"):
        PortfolioRulesConfig.model_validate(bad_raw)


def test_extra_field_rejected_on_position():
    """User invente un champ -> Pydantic catche."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Position.model_validate({
            "target_weight_pct": 5.0,
            "regime": "A",
            "invalidation": "test",
            "alert_threshold": 0.05,  # champ non declare = drift
        })


# --- Coherence avec book_index --------------------------------------------


# Pseudo-tickers autorises (pas dans book_index par construction)
_PSEUDO_TICKERS = {"CASH"}


def test_all_tickers_exist_in_book_index():
    """Tous les tickers declares dans le YAML doivent matcher book_index,
    sauf pseudo-tickers (CASH).

    Anti-typo : si un ticker du YAML n'existe pas dans le book_index,
    c'est une regle pour une position qu'on ne tient pas (= bruit).
    """
    from shared.book import get_book_index

    raw = _load_yaml_raw()
    book_tickers = set(get_book_index().keys())
    yaml_tickers = set(raw["positions"].keys()) - _PSEUDO_TICKERS

    unknown = yaml_tickers - book_tickers
    assert not unknown, (
        f"Tickers du YAML absents du book_index (typo ou position non-tenue ?) : "
        f"{sorted(unknown)}"
    )


def test_cash_pseudo_ticker_regime_null():
    """CASH est le seul pseudo-ticker avec regime=None autorise."""
    raw = _load_yaml_raw()
    cash = raw["positions"].get("CASH")
    assert cash is not None
    assert cash["regime"] is None
    assert "invalidation" not in cash or cash.get("invalidation") is None


# --- Loader + helpers ------------------------------------------------------


def test_load_portfolio_rules_returns_dict():
    """Loader retourne dict avec _meta + positions."""
    from shared.portfolio_rules import clear_cache, load_portfolio_rules

    clear_cache()
    cfg = load_portfolio_rules()
    assert cfg is not None
    assert "_meta" in cfg
    assert "positions" in cfg
    assert "cluster_caps" in cfg


def test_get_position_rule_helper():
    """get_position_rule retourne la regle pour un ticker connu."""
    from shared.portfolio_rules import clear_cache, get_position_rule

    clear_cache()
    rule = get_position_rule("ASML.AS")
    assert rule is not None
    assert rule["target_weight_pct"] == 6.0
    assert rule["regime"] == "A"


def test_get_position_rule_unknown_returns_none():
    """Ticker absent -> None (pas d'erreur)."""
    from shared.portfolio_rules import get_position_rule

    assert get_position_rule("FAKE_TICKER_XYZ") is None


def test_get_cluster_caps_helper():
    """get_cluster_caps retourne les caps declares."""
    from shared.portfolio_rules import clear_cache, get_cluster_caps

    clear_cache()
    caps = get_cluster_caps()
    assert caps is not None
    assert caps["ai_compute_max_pct"] == 70


# --- Coherence regime B / full_condition ----------------------------------


def test_regime_b_positions_have_full_condition():
    """Toute position regime B doit avoir un full_condition explicite.

    Sinon le 'conteste' n'a pas de critere de sortie, donc pas conteste.
    """
    raw = _load_yaml_raw()
    for tk, rule in raw["positions"].items():
        if rule["regime"] == "B":
            assert rule.get("full_condition"), (
                f"Position {tk} regime B sans full_condition - "
                f"declaratif incomplet"
            )
