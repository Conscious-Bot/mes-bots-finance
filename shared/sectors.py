"""Façade canonique sectoriel — source dérivée du mapping unique (Phase 3, 26/06/2026).

Avant : façade qui lisait config/sectors.yaml directement.
Maintenant : façade qui lit shared/taxonomy.py (presage_taxonomy.yaml). L'API est
strictement identique (5 consumers downstream ne voient rien) — seule la SOURCE
bascule. Les buckets sont définis dans presage_taxonomy.yaml:sector_highlevel_buckets.

Tout panel/handler qui a besoin du mapping ticker → secteur + cycle_phase doit
importer d'ici. Une seule source de vérité (taxonomy), une seule sémantique
(préservation historique Brier garantie via overrides).
"""

from __future__ import annotations

import logging
from typing import TypedDict

log = logging.getLogger(__name__)


class SectorInfo(TypedDict):
    """Forme retournée par sector_for_ticker (compat exacte avec l'ancienne API)."""

    id: str
    label: str
    index: str
    cycle_phase: str  # 'early' | 'mid' | 'late' | 'contraction'
    cycle_note: str


def load_sectors() -> dict:
    """Compat layer : retourne un dict raw {sectors: {bid: {...}}} dérivé du mapping.

    L'ancienne API renvoyait le YAML chargé. On reconstruit la même forme depuis
    presage_taxonomy.yaml:sector_highlevel_buckets pour compat callers qui
    inspectent le dict raw (book_composition_by_sector ci-dessous).
    """
    from shared import taxonomy

    raw = taxonomy._load_raw()
    buckets = raw.get("sector_highlevel_buckets") or {}
    out_sectors = {}
    for bid, bdef in buckets.items():
        # Reconstruit la liste tickers du bucket : tickers explicites + ceux que
        # le mapping classe via by_category.
        explicit = list(bdef.get("tickers") or [])
        by_cat = set(bdef.get("by_category") or [])
        cat_tickers = []
        for tk, p in taxonomy._by_ticker().items():
            lp = p.get("layer_primary") or ""
            if "/" not in lp:
                continue
            category = lp.split("/", 1)[0]
            if category in by_cat and tk not in explicit:
                cat_tickers.append(tk)
        out_sectors[bid] = {
            "label": bdef.get("label", bid),
            "index": bdef.get("index", ""),
            "cycle_phase": bdef.get("cycle_phase", "unknown"),
            "cycle_note": bdef.get("cycle_note", ""),
            "tickers": explicit + cat_tickers,
        }
    return {"sectors": out_sectors}


def sector_for_ticker(ticker: str) -> SectorInfo | None:
    """Lookup ticker → {id, label, index, cycle_phase, cycle_note}.

    None si ticker absent du mapping ET hors overrides. Source canonique =
    presage_taxonomy.yaml via shared/taxonomy.py.
    """
    from shared import taxonomy

    info = taxonomy.sector_highlevel_info(ticker)
    if not info:
        return None
    return SectorInfo(
        id=info["id"],
        label=info["label"],
        index=info["index"],
        cycle_phase=info["cycle_phase"],
        cycle_note=info["cycle_note"],
    )


def cycle_phase_for_ticker(ticker: str) -> str:
    """Cycle phase courante du secteur d'un ticker. 'unknown' si non-catalogue."""
    from shared import taxonomy

    return taxonomy.cycle_phase_for(ticker)


def book_composition_by_sector(positions: list[dict]) -> dict[str, dict]:
    """Décompose un book par sector_id. Returns:
        {
          sector_id: {
            exposure_eur: float,
            share_pct: float,
            tickers: [str],
            cycle_phase: str,
            label: str
          }
        }

    Tickers hors-mapping → bucket 'uncat' (surface explicite plutôt que masquer
    dans 'other'). Source = shared/taxonomy.py (Phase 3, 26/06/2026).
    """
    total_eur = 0.0
    by_sector: dict[str, dict] = {}
    for pos in positions:
        tk = pos.get("ticker")
        if not tk:
            continue
        # Refonte 24/06 (cure coherence cluster%) : prefere weight (market value
        # EUR canonique cure #120) sur qty*avg_cost (cost basis). Le panneau macro
        # impact disait 57% (cost basis) vs cluster_cap grade 62.3% (market).
        # Sur winners +50-100% PnL, market value gonfle 5pp vs cost. Single-source
        # via weight = panneaux concordants. Fallback qty*avg pour callers legacy
        # (trade_context.py simulate post-trade qui ne passe pas weight).
        weight = pos.get("weight")
        if weight is not None and weight > 0:
            exposure = float(weight)
        else:
            qty = float(pos.get("qty") or 0)
            avg = float(pos.get("avg_cost") or 0)
            if qty <= 0 or avg <= 0:
                continue
            exposure = qty * avg
        info = sector_for_ticker(tk)
        sid = info["id"] if info else "uncat"
        bucket = by_sector.setdefault(
            sid,
            {
                "exposure_eur": 0.0,
                "tickers": [],
                "cycle_phase": info["cycle_phase"] if info else "unknown",
                "label": info["label"] if info else sid,
            },
        )
        bucket["exposure_eur"] += exposure
        bucket["tickers"].append(tk)
        total_eur += exposure

    for _sid, b in by_sector.items():
        b["share_pct"] = (b["exposure_eur"] / total_eur * 100.0) if total_eur > 0 else 0.0
    return by_sector


def jp_tickers(positions: list[dict]) -> list[str]:
    """Tickers .T (Tokyo) parmi positions tenues (qty > 0)."""
    return [
        p["ticker"]
        for p in positions
        if p.get("ticker", "").endswith(".T") and float(p.get("qty") or 0) > 0
    ]


def reset_cache() -> None:
    """No-op (taxonomy has its own lru_cache). Conservé pour compat callers tests."""
