"""Source UNIQUE du cap par ligne. Kill style.position_max_pct legacy.

Doctrine : un seul knob de cap par ligne -> concentration.line_cap_by_conviction.
Avant ce module : 2 verites concurrentes (style.position_max_pct uniforme +
line_cap_by_conviction graduee) -> les enforcers (risk/sizing, risk/risk_engine,
positions handler, render POS_CAP) appliquaient le cap uniforme et laissaient
une c3 monter a 8% alors que la doctrine la cape a 3.8%.

Ce module ferme TODO #73 partie "router tous enforcers vers cap fin unique".
La partie "remplacer pente par hit-rates empiriques post N>=30 J+90" reste
ouverte (TODO #73 sub-task transitoire -> mesure).

Usage :
    from shared.sizing_caps import cap_for_conviction
    cap = cap_for_conviction(conviction)  # fraction (0.06 pour c5)
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Fallback minimal si config indisponible (tests, bootstrap).
# = c5 ancre courante (sommet bride sub-Kelly N<100). Documente dans config.yaml.
_FALLBACK_CAP_C5 = 0.06


def cap_for_conviction(conviction: int | None) -> float:
    """Cap absolu par ligne en fonction de la conviction.

    Source de verite : config.concentration.line_cap_by_conviction (YAML).
    Pente transitoire compressee sub-Kelly tant que N<100. Sera remplacee
    par hit-rates empiriques mesures post N>=30 J+90 (TODO #73).

    Args:
        conviction: int 1-5, ou None.

    Returns:
        cap en fraction du capital (ex 0.06 = 6%).

    Si conviction unknown/missing/out-of-range :
        Retour cap c5 (sommet bride = plafond ABSOLU). Defense conservative :
        on ne sait pas la conviction -> on est strict.
    """
    try:
        from shared import config
        caps = config.load().get("concentration", {}).get(
            "line_cap_by_conviction"
        ) or {}
    except Exception as e:
        log.warning(f"cap_for_conviction config load failed: {e}")
        return _FALLBACK_CAP_C5

    # Pydantic load YAML preserve int keys, mais config.load passe par
    # yaml.safe_load qui peut renvoyer int OU str. Supporte les 2.
    if conviction is None:
        return float(caps.get(5, caps.get("5", _FALLBACK_CAP_C5)))
    key_int = int(conviction)
    if key_int in caps:
        return float(caps[key_int])
    if str(key_int) in caps:
        return float(caps[str(key_int)])
    return float(caps.get(5, caps.get("5", _FALLBACK_CAP_C5)))


def absolute_max_cap() -> float:
    """Plafond ABSOLU (= cap c5 = sommet bride). Pour displays / threshold
    uniformes ou la conviction n'est pas disponible (ex : dashboard global
    cap marker)."""
    return cap_for_conviction(5)


def target_edge_pct(
    entry: float | None,
    stop: float | None,
    current: float | None,
    ruin_budget_pct: float,
    direction: str = "long",
) -> float | None:
    """Levier #4 sizing asymetrie-first : taille honnete bride par budget-ruine
    par nom plutot que par conviction seule. Doctrine sub-Kelly N<100.

    Formule : target_edge_pct = ruin_budget_pct / |downside_pct|
    ou downside_pct = (current - stop) / current * 100 (long)
                    = (stop - current) / current * 100 (short)

    Si downside large -> target-edge plus restrictif que cap conviction.
    Si downside etroit -> target-edge plus large que cap conviction (mais
    le cap conviction prime in fine, voir consumer derive_card_steer).

    Returns:
        target_edge_pct : taille max en % du book honnete vs budget-ruine.
        None si :
        - stop is None (structural -- downside non-borne par prix, target-edge n/a)
        - downside <= 0 (deja stop-breached ou price > stop equivalent)
        - inputs manquants
    """
    if not entry or not stop or not current:
        return None
    if direction == "long":
        downside = (current - stop) / current * 100
    else:
        downside = (stop - current) / current * 100
    if downside <= 0:
        return None
    abs_downside = abs(downside)
    if abs_downside < 0.01:
        return None  # degenere
    return ruin_budget_pct / abs_downside * 100  # both in %
