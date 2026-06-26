"""Single source of truth for ticker categorization (layer, driver, geo, status).

Cure 26/06/2026 — supersède 5 sources qui divergeaient :
  A) shared/sector_taxonomy.py:TICKER_SECTOR  (mort en Phase 1)
  B) config.yaml:concentration.clusters.compute_ai  (dérivée en Phase 4 — kill_switch)
  C) config/sectors.yaml  (vue dérivée via sector_highlevel() en Phase 3)
  D) config.yaml:sectors_taxonomy + sectors:  (survit pour caps, usages dashboard morts)
  E) dashboard/render.py:_sectors/_sector_blocks/...  (mort en Phase 2)

Source unique = config/presage_taxonomy.yaml. Toute catégorisation dashboard/risk
passe par ce module. Validations strictes au premier accès (raise sur incohérence —
CONVENTIONS §6, jamais de défaut silencieux).
"""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any

import yaml

_YAML_PATH = Path(__file__).parent.parent / "config" / "presage_taxonomy.yaml"


class TaxonomyError(Exception):
    """Catégorisation incohérente ou ticker manquant. Jamais de défaut silencieux."""


def _layer_full(category: str, sub: str) -> str:
    return f"{category}/{sub}"


@functools.lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    if not _YAML_PATH.exists():
        raise TaxonomyError(f"YAML absent : {_YAML_PATH}")
    with open(_YAML_PATH, encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    layers_vocab = {
        _layer_full(cat, sub)
        for cat, subs in (data.get("layers") or {}).items()
        for sub in (subs or [])
    }
    drivers_vocab = set(data.get("drivers") or [])
    geos_vocab = set(data.get("geos") or [])
    statuses_vocab = set(data.get("statuses") or [])

    positions = data.get("positions") or {}
    if not positions:
        raise TaxonomyError("positions block empty in YAML")

    for slug, p in positions.items():
        tk = p.get("ticker")
        if not tk:
            raise TaxonomyError(f"position {slug} : missing ticker field")
        lp = p.get("layer_primary")
        layers = p.get("layer") or []
        if lp not in layers:
            raise TaxonomyError(
                f"position {slug} ({tk}) : layer_primary={lp!r} not in layer list {layers!r}"
            )
        for lr in layers:
            if lr not in layers_vocab:
                raise TaxonomyError(
                    f"position {slug} ({tk}) : layer {lr!r} not in vocabulary"
                )
        if p.get("driver") not in drivers_vocab:
            raise TaxonomyError(
                f"position {slug} ({tk}) : driver={p.get('driver')!r} not in vocab"
            )
        if p.get("geo") not in geos_vocab:
            raise TaxonomyError(
                f"position {slug} ({tk}) : geo={p.get('geo')!r} not in vocab"
            )
        if p.get("status") not in statuses_vocab:
            raise TaxonomyError(
                f"position {slug} ({tk}) : status={p.get('status')!r} not in vocab"
            )

    return data


@functools.lru_cache(maxsize=1)
def _by_ticker() -> dict[str, dict[str, Any]]:
    raw = _load_raw()
    out: dict[str, dict[str, Any]] = {}
    for slug, p in (raw.get("positions") or {}).items():
        tk = p["ticker"]
        if tk in out:
            raise TaxonomyError(f"duplicate ticker {tk!r} in mapping (slug {slug})")
        out[tk] = p
    return out


def get_taxonomy(ticker: str) -> dict[str, Any]:
    """Returns {ticker, name, layer, layer_primary, driver, geo, status}.

    Raises TaxonomyError if ticker absent (jamais de défaut silencieux).
    """
    idx = _by_ticker()
    if ticker not in idx:
        raise TaxonomyError(
            f"ticker {ticker!r} absent du mapping (config/presage_taxonomy.yaml). "
            f"Ajouter la position ou exclure du book."
        )
    return idx[ticker]


def by_driver(driver: str, status: str = "held") -> list[str]:
    return [tk for tk, p in _by_ticker().items() if p["driver"] == driver and p["status"] == status]


def by_geo(geo: str, status: str = "held") -> list[str]:
    return [tk for tk, p in _by_ticker().items() if p["geo"] == geo and p["status"] == status]


def by_layer_primary(layer_primary: str, status: str = "held") -> list[str]:
    return [tk for tk, p in _by_ticker().items() if p["layer_primary"] == layer_primary and p["status"] == status]


def held_tickers() -> list[str]:
    return [tk for tk, p in _by_ticker().items() if p["status"] == "held"]


def planned_tickers() -> list[str]:
    return [tk for tk, p in _by_ticker().items() if p["status"] == "planned"]


def coverage_holes(status: str = "held") -> list[str]:
    """Sous-couches du vocabulaire absentes de la liste `layer` du périmètre demandé.

    status='held'     → trous = sous-couches non couvertes par tes 26 held.
    status='planned'  → trous = sous-couches non couvertes par held ∪ planned (trous ouverts).
    """
    raw = _load_raw()
    vocab = {
        _layer_full(cat, sub)
        for cat, subs in (raw.get("layers") or {}).items()
        for sub in (subs or [])
    }
    if status == "held":
        scope = {"held"}
    elif status == "planned":
        scope = {"held", "planned"}
    else:
        scope = {status}
    covered = set()
    for _tk, p in _by_ticker().items():
        if p["status"] not in scope:
            continue
        for lr in p.get("layer") or []:
            covered.add(lr)
    return sorted(vocab - covered)


def sector_highlevel(ticker: str) -> str | None:
    """Bucket high-level Brier-side (semis / energy_commodities / defense_industrials_eu).

    Lit sector_highlevel_buckets du YAML (catégorie-mère → bucket).
    Retourne None si layer_primary mal formé ou catégorie absente du mapping bucket.
    """
    tax = get_taxonomy(ticker)
    lp = tax.get("layer_primary") or ""
    if "/" not in lp:
        return None
    category = lp.split("/", 1)[0]
    buckets = _load_raw().get("sector_highlevel_buckets") or {}
    return buckets.get(category)


def same_sector_tickers(ticker: str, status: str = "held") -> list[str]:
    """Tickers in the same high-level sector bucket (Brier-side), excluding the input.

    Used by adversarial co-pilot for "adjacent signals" lookup. Maps to
    `sector_highlevel(ticker)` — broad bucket (semis / energy_commodities /
    defense_industrials_eu) — which best matches the legacy TICKER_SECTOR
    grouping ("AI Compute" → multiple semis sub-layers were grouped together).
    Returns [] if ticker has no bucket.
    """
    bucket = sector_highlevel(ticker)
    if not bucket:
        return []
    return [
        tk
        for tk, p in _by_ticker().items()
        if tk != ticker
        and p["status"] == status
        and sector_highlevel(tk) == bucket
    ]


def clean_sector(sid: str | None) -> str:
    """Format a sector_id (snake_case with optional trailing year) into a display label.

    'ai_compute_2026' → 'AI Compute' ; 'mag7' → 'MAG 7' ; None → 'Sans thesis'.
    Migrée depuis shared/sector_taxonomy.py:clean_sector lors de la cure
    5 sources → 1 (Phase 1, 26/06/2026). Pure formatting, ne dépend d'aucune
    table — sert au rendu de tout label catégoriel hérité.
    """
    if not sid:
        return "Sans thesis"
    s = re.sub(r"_20\d\d$", "", sid).replace("_", " ").title()
    return (
        s.replace(" Ai", " AI")
        .replace("Ai ", "AI ")
        .replace("Hpq", "HPQ")
        .replace("Eu ", "EU ")
        .replace("Mag7", "MAG 7")
    )


def validate_against_db(*, raise_on_missing: bool = True) -> dict[str, list[str]]:
    """Cross-check : every DB held ticker (qty>0) ∈ mapping.

    Returns {"missing_in_mapping": [...], "in_db_not_held_in_map": [...]}.
    raise_on_missing=True (default) → TaxonomyError si DB held - mapping ≠ ∅.
    """
    from shared import storage

    with storage.db() as cx:
        db_held = {
            row[0] for row in cx.execute(
                "SELECT ticker FROM positions WHERE qty > 0"
            ).fetchall()
        }
    mapping_held = set(held_tickers())
    mapping_all = set(_by_ticker().keys())
    missing = sorted(db_held - mapping_all)
    in_db_not_held_in_map = sorted(db_held - mapping_held)
    result = {"missing_in_mapping": missing, "in_db_not_held_in_map": in_db_not_held_in_map}
    if raise_on_missing and missing:
        raise TaxonomyError(
            f"DB held tickers absent du mapping : {missing}. "
            f"Ajouter au YAML ou exclure du book."
        )
    return result
