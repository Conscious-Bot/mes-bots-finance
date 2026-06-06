"""Phase B — Tie-to-book : macro regime x book composition -> warnings actionables.

Doctrine : "discipline mecanisee, pas alpha predictif" (cf
[[business-path-6-acted]]). On ne predit pas. On constate :
1. Regime macro courant (Phase A classify_regime)
2. Composition book courante (positions x sectors.yaml via shared.sectors)
3. Si certaines confluences declenchent une regle -> warning actionnable

Pas de signal "buy X". Que des "trim X" / "raise stops" / "rightsize".

Doctrine secondaire (cf [[portfolio_construction_phase]]) : book en phase
construction (43k -> 70k cible) -> warnings parlent de "rightsize" /
"raise stops", pas de "trim hardcore" / "exit". Tone consciencieux.

06/06 v2 : refactor sur shared.sectors (source unique sectors.yaml).
"""

from __future__ import annotations

import logging
from typing import TypedDict

from shared import sectors as _sec
from shared.calibration import get_rule_threshold as _rt

log = logging.getLogger(__name__)

# 06/06 architecture : thresholds canoniques desormais loaded depuis
# config/calibration.yaml via shared.calibration.
_R1_SEMIS_MIN = _rt("R1_semis_share_min") or 45.0
_R2_USDJPY_GATE = _rt("R2_usdjpy_gate") or 155.0
_R2_USDJPY_HIGH = _rt("R2_usdjpy_high_sev") or 160.0
_R2_JP_MIN = _rt("R2_jp_share_min") or 10.0
_R3_GROWTH_MIN = _rt("R3_growth_tech_min") or 65.0
_R4_AUTO_MIN = _rt("R4_auto_ev_min") or 3.0
_R5_VIX_MAX = _rt("R5_vix_complacent_max") or 12.0


class Warning(TypedDict):
    severity: str  # 'high' | 'med' | 'low'
    rule_id: str
    action: str
    rationale: str
    tickers: list[str]


def compute_book_warnings(
    regime: str,
    positions: list[dict],
    indicator_values: dict[str, float | None],
) -> list[Warning]:
    """Apply rules. Returns sorted by severity (high first), max 4."""
    by_sector = _sec.book_composition_by_sector(positions)
    if not by_sector:
        return []

    semis_share = by_sector.get("semis", {}).get("share_pct", 0.0)
    tech_mega_share = by_sector.get("tech_mega", {}).get("share_pct", 0.0)
    auto_ev_share = by_sector.get("auto_ev", {}).get("share_pct", 0.0)
    energy_share = by_sector.get("energy_commodities", {}).get("share_pct", 0.0)
    semis_tickers = by_sector.get("semis", {}).get("tickers", [])
    tech_tickers = by_sector.get("tech_mega", {}).get("tickers", [])

    jp_tickers = _sec.jp_tickers(positions)
    jp_exposure_eur = sum(
        sum(pos.get("qty", 0) * pos.get("avg_cost", 0) for pos in positions if pos.get("ticker") == tk)
        for tk in jp_tickers
    )
    total_eur = sum(b["exposure_eur"] for b in by_sector.values())
    jp_share = (jp_exposure_eur / total_eur * 100.0) if total_eur > 0 else 0.0

    usdjpy = indicator_values.get("USDJPY")
    tyx = indicator_values.get("TYX")
    vix = indicator_values.get("VIX")

    warnings: list[Warning] = []

    # R1 : FRAGILE/STRESS + semis dominant -> repricing risk concentre.
    if regime in ("FRAGILE", "STRESS", "LATE_CYCLE") and semis_share > _R1_SEMIS_MIN:
        sev = "high" if regime == "STRESS" else "med"
        tyx_phrase = f"Taux 30Y à {tyx:.1f}% (>4.2 = repricing actif). " if tyx and tyx > 4.2 else ""
        warnings.append(Warning(
            severity=sev,
            rule_id="R1_semis_concentration",
            action=f"Resserre tes stops sur le cluster semis ({semis_share:.0f}% du book)",
            rationale=(
                f"Marché en {regime}. {tyx_phrase}"
                f"Les multiples growth craquent en premier sur repricing brutal, "
                f"et ton book est concentré à {semis_share:.0f}% sur les semis."
            ),
            tickers=semis_tickers[:5],
        ))

    # R2 : USDJPY > gate (calib) + JP exposure > min (calib) -> carry unwind risk.
    if usdjpy is not None and usdjpy > _R2_USDJPY_GATE and jp_share > _R2_JP_MIN and jp_tickers:
        sev = "high" if usdjpy > _R2_USDJPY_HIGH else "med"
        warnings.append(Warning(
            severity=sev,
            rule_id="R2_carry_unwind_jp",
            action=f"Hedge ou réduis tes positions japonaises ({jp_share:.0f}% du book)",
            rationale=(
                f"USDJPY à {usdjpy:.1f}. BoJ/MoF ont déjà dépensé > 73 Mds$ pour défendre 160 "
                f"en avril-mai 2026, l'intervention est confirmée. Si l'unwind carry démarre, "
                f"yen monte vite et tech JP vendus en cascade. Tu as {len(jp_tickers)} positions JP."
            ),
            tickers=jp_tickers[:5],
        ))

    # R3 : LATE_CYCLE/FRAGILE + growth-tech combined elevee -> diversifier hors growth.
    growth_tech = semis_share + tech_mega_share
    if regime in ("LATE_CYCLE", "FRAGILE") and growth_tech > _R3_GROWTH_MIN:
        warnings.append(Warning(
            severity="med",
            rule_id="R3_growth_tech_dominance",
            action=f"Diversifie hors du growth-tech ({growth_tech:.0f}% combiné)",
            rationale=(
                f"Tu cumules {semis_share:.0f}% semis + {tech_mega_share:.0f}% mega-cap = "
                f"{growth_tech:.0f}% du book exposé au même facteur taux. "
                f"L'energie ({energy_share:.0f}%) et les industriels EU décorrèlent."
            ),
            tickers=tech_tickers[:5],
        ))

    # R4 : STRESS + auto_ev exposure -> margins compression accelerent.
    if regime == "STRESS" and auto_ev_share > _R4_AUTO_MIN:
        warnings.append(Warning(
            severity="med",
            rule_id="R4_auto_ev_stress",
            action="Allège le cluster auto/EV",
            rationale=(
                "Marché en STRESS et le cycle auto est en contraction. "
                "Marges sous pression + sentiment fragile = baisse rapide possible."
            ),
            tickers=by_sector.get("auto_ev", {}).get("tickers", [])[:5],
        ))

    # R5 : COMPLACENT + zero stress flags -> consider tactical hedge.
    if regime == "COMPLACENT" and vix is not None and vix < _R5_VIX_MAX:
        warnings.append(Warning(
            severity="low",
            rule_id="R5_complacent_hedge",
            action="Considère un hedge tactique (puts SPY / call spread VIX)",
            rationale=(
                f"VIX à {vix:.1f} = ultra-bas, spreads serrés. "
                f"Le coût d'un hedge est minimal historiquement, et le risque de "
                f"correction asymétrique se construit."
            ),
            tickers=[],
        ))

    sev_order = {"high": 0, "med": 1, "low": 2}
    warnings.sort(key=lambda w: sev_order.get(w["severity"], 9))
    return warnings[:4]
