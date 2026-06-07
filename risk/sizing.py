"""Position sizing. UNE seule formule. PAS de cascade.

STATUS: FEATURE READY, NOT YET WIRED INTO RUNTIME (as of 13 May 2026).

Designed for /size_recommend handler + decision pipeline. Integration deferred
to post-observation. See TODO.md.

Reference: tennis-bot AUDIT.md (Quarter Kelly + hard cap).
Test: tests/test_sizing.py
"""

from shared.sizing_caps import cap_for_conviction


def position_size(
    edge_pct: float, variance_estimate: float, capital: float,
    regime_factor: float = 1.0, conviction: int | None = None,
) -> float:
    """Quarter Kelly + cap dur. UNE modulation régime. 3 étapes max.

    conviction (optional) : si fourni, cap fin = line_cap_by_conviction[conv].
    Si None : cap absolu = c5 sommet bride (defense conservative).
    Cf shared.sizing_caps doctrine.
    """
    if edge_pct <= 0 or variance_estimate <= 0:
        return 0.0
    max_pct = cap_for_conviction(conviction)
    raw_kelly = edge_pct / variance_estimate
    sized = capital * raw_kelly * 0.25 * regime_factor
    capped = min(sized, capital * max_pct)
    return float(max(0.0, capped))
