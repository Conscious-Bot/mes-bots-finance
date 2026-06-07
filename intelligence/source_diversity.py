"""Axe 2 QUALITY_BAR : diversite des sources, N_effective.

Spec garde-fou : "deux sources qui s'accordent toujours ne comptent pas pour
deux. Ce n'est pas une lecture du marche, c'est une lecture d'une cohorte
narrative."

Heuristique 1er geste : N_effective = nombre de FAMILLES distinctes representees
parmi les signaux. Pas le nombre de sources brut.

Famille canonique (defini par migration 0038) :
- primary_filing       : EDGAR 8-K/10-Q/10-K (orthogonal structurel)
- insider              : Form 4, insider clusters (orthogonal comportemental)
- narrative_newsletter : substacks, beehiiv (cohorte narrative)
- broker_research      : Goldman/Morgan/Jefferies
- social               : reddit, twitter, WSB
- chat                 : user manual taps Telegram
- manual               : ajouts manuels user
- other                : fallback

L21 invariant : pas de wire scoring action ici. Le but du 1er geste est
de RENDRE VISIBLE la monoculture, pas encore de la corriger (gating par
calibration N<100).
"""

from __future__ import annotations

import logging

from shared import storage

log = logging.getLogger(__name__)

CANONICAL_FAMILIES = (
    "primary_filing", "insider", "narrative_newsletter", "broker_research",
    "social", "chat", "manual", "other",
)

ORTHOGONAL_FAMILIES = frozenset({
    "primary_filing", "insider", "broker_research",
})


def effective_n_signals(signals: list[dict]) -> dict:
    """Calcule N_raw et N_effective sur une liste de signaux.

    Args:
        signals: list[dict], chaque dict doit avoir au minimum 'source_id' ou
            'source_family' (resolu via DB si besoin).

    Returns:
        {
          'n_raw': int,                # nombre de signaux brut
          'n_effective': int,          # nombre de familles distinctes
          'n_orthogonal': int,         # familles orthogonales presentes
          'by_family': {family: int},  # repartition
          'is_monoculture': bool,      # True si 1 famille narrative_newsletter unique
        }
    """
    if not signals:
        return {
            "n_raw": 0, "n_effective": 0, "n_orthogonal": 0,
            "by_family": {}, "is_monoculture": False,
        }

    family_map = _resolve_family_for_signals(signals)
    by_family: dict[str, int] = {}
    for sig in signals:
        sid = sig.get("source_id")
        family = sig.get("source_family") or family_map.get(sid) or "other"
        by_family[family] = by_family.get(family, 0) + 1

    n_raw = len(signals)
    n_effective = len(by_family)
    n_orthogonal = sum(
        1 for f in by_family if f in ORTHOGONAL_FAMILIES
    )
    # Monoculture : tous les signaux dans narrative_newsletter, aucun orthogonal
    is_monoculture = (
        len(by_family) == 1
        and "narrative_newsletter" in by_family
        and by_family["narrative_newsletter"] >= 2
    )

    return {
        "n_raw": n_raw,
        "n_effective": n_effective,
        "n_orthogonal": n_orthogonal,
        "by_family": by_family,
        "is_monoculture": is_monoculture,
    }


def _resolve_family_for_signals(signals: list[dict]) -> dict[int, str]:
    """Resolve source_id -> family map via DB. Cached per call (small N)."""
    source_ids = {sig.get("source_id") for sig in signals if sig.get("source_id")}
    if not source_ids:
        return {}
    try:
        with storage.db() as cx:
            placeholders = ",".join("?" * len(source_ids))
            rows = cx.execute(
                f"SELECT id, family FROM sources WHERE id IN ({placeholders})",
                tuple(source_ids),
            ).fetchall()
            return {int(r[0]): r[1] for r in rows}
    except Exception as e:
        log.warning(f"_resolve_family_for_signals failed: {e}")
        return {}


def book_source_composition() -> dict:
    """Distribution globale des sources par famille pour dashboard chip.

    Returns:
        {
          'total': int,
          'by_family': {family: int},
          'orthogonal_pct': float,  # % sources orthogonales (primary/insider/broker)
          'narrative_pct': float,   # % narrative_newsletter
        }
    """
    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT family, COUNT(*) FROM sources GROUP BY family"
            ).fetchall()
            by_family = {r[0]: int(r[1]) for r in rows}
    except Exception as e:
        log.warning(f"book_source_composition failed: {e}")
        return {"total": 0, "by_family": {}, "orthogonal_pct": 0.0, "narrative_pct": 0.0}

    total = sum(by_family.values()) or 1
    n_ortho = sum(c for f, c in by_family.items() if f in ORTHOGONAL_FAMILIES)
    n_narr = by_family.get("narrative_newsletter", 0)
    return {
        "total": total,
        "by_family": by_family,
        "orthogonal_pct": round(n_ortho / total * 100, 1),
        "narrative_pct": round(n_narr / total * 100, 1),
    }
