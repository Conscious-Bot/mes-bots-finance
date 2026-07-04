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
from datetime import date
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


def operate_state(book_eur: float | None = None, today: date | None = None) -> dict:
    """État de la transition BUILD -> OPERATE (étape 3 Path B, cure 04/07).

    Ferme le seuil ORAL (>=65k en memory) : la règle est désormais déclarative
    (config/portfolio_rules.yaml:operate_transition). rule=first_of → OPERATE
    dès que capital OU date est atteint (pas d'excuse « phase construction »
    infinie — antipattern gravé en memory 26/06).

    Args:
        book_eur : book courant (positions only, market value). None → calculé
            via shared.book.get_held_lines (import paresseux, fail-safe None).
        today : date de référence (défaut = aujourd'hui UTC).

    Returns dict : {available, phase ('BUILD'|'OPERATE'), book_eur,
        target_book_eur, target_date, days_to_date, book_gap_eur,
        met_by ('capital'|'date'|None), rule}. available=False si le bloc absent.
    """
    cfg = load_portfolio_rules()
    ot = (cfg or {}).get("operate_transition") if cfg else None
    if not ot:
        return {"available": False, "phase": "BUILD"}

    from datetime import UTC, datetime

    if today is None:
        today = datetime.now(UTC).date()
    if book_eur is None:
        try:
            from shared.book import get_held_lines

            book_eur = sum(ln.weight_market_eur for ln in get_held_lines())
        except Exception as e:
            log.warning(f"operate_state: book value indisponible ({e})")
            book_eur = None

    target_book = float(ot["book_eur"])
    tgt_date = ot["date"]
    if isinstance(tgt_date, str):
        tgt_date = date.fromisoformat(tgt_date)
    rule = ot.get("rule", "first_of")

    cap_met = book_eur is not None and book_eur >= target_book
    date_met = today >= tgt_date
    operate = (cap_met and date_met) if rule == "all_of" else (cap_met or date_met)
    met_by = ("capital" if cap_met else "date") if operate else None

    return {
        "available": True,
        "phase": "OPERATE" if operate else "BUILD",
        "book_eur": round(book_eur, 0) if book_eur is not None else None,
        "target_book_eur": target_book,
        "target_date": tgt_date.isoformat(),
        "days_to_date": (tgt_date - today).days,
        "book_gap_eur": round(target_book - book_eur, 0) if book_eur is not None else None,
        "met_by": met_by,
        "rule": rule,
    }


def clear_cache() -> None:
    """Reset cache module-level (pour tests)."""
    global _CACHE
    _CACHE = None
