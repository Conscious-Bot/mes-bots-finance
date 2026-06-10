"""Loader config/portfolio_rules.yaml.

Doctrine L17 LESSONS :
- DECLARATIF (ici, YAML) : target_weight_pct, partial_cap_pct, regime,
  invalidation, consensus_ref, full_condition.
- LIVE STATE (ailleurs) :
    - poids actuel -> BookView (qty x prix x fx)
    - spot-delta consensus -> calcul live (current_price - pt)/pt
    - alertes cap depasse / invalidation matched -> futur monitor #134

Le loader :
1. Lit le YAML
2. Valide via Pydantic PortfolioRulesConfig (extra=forbid catche drift)
3. Cache module-level (reset via clear_cache pour tests)

API publique :
- `load_portfolio_rules()` -> dict valide ou None
- `get_position_rule(ticker)` -> dict de la regle pour ce ticker ou None
- `get_cluster_caps()` -> dict des caps cluster
- `clear_cache()` -> reset cache (tests)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_YAML_PATH = _REPO_ROOT / "config" / "portfolio_rules.yaml"
_CACHE: dict | None = None


def load_portfolio_rules() -> dict | None:
    """Charge le YAML declaratif + valide via Pydantic.

    Returns:
        Dict avec keys _meta, cluster_caps, positions ; None si fichier absent
        ou invalide.
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    if not _YAML_PATH.exists():
        log.warning(f"portfolio_rules.yaml absent : {_YAML_PATH}")
        return None

    try:
        import yaml

        from intelligence.portfolio_rules_schema import PortfolioRulesConfig

        raw = yaml.safe_load(_YAML_PATH.read_text())
        cfg = PortfolioRulesConfig.model_validate(raw)
        _CACHE = cfg.model_dump(by_alias=True, mode="json")
        return _CACHE
    except Exception as e:
        log.warning(f"portfolio_rules.yaml invalide : {e}")
        return None


def get_position_rule(ticker: str) -> dict[str, Any] | None:
    """Retourne la regle declarative pour un ticker, None si non declare."""
    cfg = load_portfolio_rules()
    if cfg is None:
        return None
    return cfg.get("positions", {}).get(ticker)


def get_cluster_caps() -> dict[str, float] | None:
    """Retourne les caps de concentration cluster declares."""
    cfg = load_portfolio_rules()
    if cfg is None:
        return None
    return cfg.get("cluster_caps")


def clear_cache() -> None:
    """Reset cache module-level (pour tests)."""
    global _CACHE
    _CACHE = None
