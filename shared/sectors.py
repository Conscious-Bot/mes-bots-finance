"""Source canonique unique pour config/sectors.yaml.

Consolide 2 implementations precedentes :
- intelligence/macro_book_warnings.py (_load_sectors + _book_composition)
- bot/handlers/review.py (_load_sector_config + _find_sector_for_ticker)

Tout panel/handler qui a besoin du mapping ticker->secteur+cycle_phase
doit importer d'ici. Une seule source de verite, un seul cache, une
seule semantique (cf [[organize tout proprement]] memory 06/06).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypedDict

log = logging.getLogger(__name__)

_SECTORS_YAML = Path(__file__).resolve().parent.parent / "config" / "sectors.yaml"
_CACHE: dict | None = None


class SectorInfo(TypedDict):
    """Forme retournee par sector_for_ticker."""
    id: str
    label: str
    index: str
    cycle_phase: str  # 'early' | 'mid' | 'late' | 'contraction'
    cycle_note: str


def load_sectors() -> dict:
    """Lazy load + cache. Re-load au redemarrage process suffisant
    (config evolue trimestriellement)."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        import yaml
        with open(_SECTORS_YAML) as f:
            _CACHE = yaml.safe_load(f) or {}
    except Exception as e:
        log.warning(f"sectors.yaml load failed: {e}")
        _CACHE = {}
    return _CACHE


def sector_for_ticker(ticker: str) -> SectorInfo | None:
    """Lookup ticker -> {id, label, index, cycle_phase, cycle_note}.

    None si ticker absent du mapping. Source canonique = sectors.yaml.
    """
    cfg = load_sectors()
    for sect_id, sect in cfg.get("sectors", {}).items():
        if ticker in sect.get("tickers", []):
            return SectorInfo(
                id=sect_id,
                label=sect.get("label", sect_id),
                index=sect.get("index", ""),
                cycle_phase=sect.get("cycle_phase", "unknown"),
                cycle_note=sect.get("cycle_note", ""),
            )
    return None


def cycle_phase_for_ticker(ticker: str) -> str:
    """Cycle phase courante du secteur d'un ticker. 'unknown' si non-catalogue."""
    s = sector_for_ticker(ticker)
    return s["cycle_phase"] if s else "unknown"


def book_composition_by_sector(positions: list[dict]) -> dict[str, dict]:
    """Decompose un book par sector_id. Returns:
        {
          sector_id: {
            exposure_eur: float,
            share_pct: float,
            tickers: [str],
            cycle_phase: str,
            label: str
          }
        }

    Tickers absents de sectors.yaml -> bucket 'uncat' (surface explicite
    plutot que masquer dans 'other').
    """
    cfg = load_sectors()
    sectors = cfg.get("sectors", {})
    ticker_to_sector: dict[str, str] = {}
    for sid, sdef in sectors.items():
        for tk in sdef.get("tickers", []):
            ticker_to_sector[tk] = sid

    total_eur = 0.0
    by_sector: dict[str, dict] = {}
    for pos in positions:
        tk = pos.get("ticker")
        qty = float(pos.get("qty") or 0)
        avg = float(pos.get("avg_cost") or 0)
        if qty <= 0 or avg <= 0:
            continue
        exposure = qty * avg
        sid = ticker_to_sector.get(tk, "uncat")
        sdef = sectors.get(sid, {})
        bucket = by_sector.setdefault(sid, {
            "exposure_eur": 0.0,
            "tickers": [],
            "cycle_phase": sdef.get("cycle_phase", "unknown"),
            "label": sdef.get("label", sid),
        })
        bucket["exposure_eur"] += exposure
        bucket["tickers"].append(tk)
        total_eur += exposure

    for _sid, b in by_sector.items():
        b["share_pct"] = (b["exposure_eur"] / total_eur * 100.0) if total_eur > 0 else 0.0
    return by_sector


def jp_tickers(positions: list[dict]) -> list[str]:
    """Tickers .T (Tokyo) parmi positions tenues (qty > 0)."""
    return [
        p["ticker"] for p in positions
        if p.get("ticker", "").endswith(".T") and float(p.get("qty") or 0) > 0
    ]


def reset_cache() -> None:
    """Force re-load au prochain appel. Pour tests + edge case manuel."""
    global _CACHE
    _CACHE = None
