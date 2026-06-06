"""Phase B — Tie-to-book : macro regime x book composition -> warnings actionables.

Doctrine : "discipline mecanisee, pas alpha predictif" (cf
[[business-path-6-acted]]). On ne predit pas. On constate :
1. Regime macro courant (Phase A classify_regime)
2. Composition book courante (positions x sectors.yaml)
3. Si certaines confluences declenchent une regle -> warning actionnable

Pas de signal "buy X". Que des "trim X" / "raise stops" / "rightsize".

Doctrine secondaire (cf [[portfolio_construction_phase]]) : book en phase
construction (43k -> 70k cible) -> warnings parlent de "rightsize" /
"raise stops", pas de "trim hardcore" / "exit". Tone consciencieux.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypedDict

log = logging.getLogger(__name__)

_SECTORS_YAML = Path(__file__).resolve().parent.parent / "config" / "sectors.yaml"


class Warning(TypedDict):
    severity: str  # 'high' | 'med' | 'low'
    rule_id: str
    action: str
    rationale: str
    tickers: list[str]


def _load_sectors() -> dict:
    try:
        import yaml
        with open(_SECTORS_YAML) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        log.warning(f"sectors.yaml load failed: {e}")
        return {}


def _book_composition(positions: list[dict], sectors_cfg: dict) -> dict[str, dict]:
    """Returns {sector_id: {exposure_eur, share_pct, tickers: [...]}}.

    Tickers absents de sectors.yaml -> bucket 'uncat' (decision: surface
    explicite pour pousser a categoriser, pas masquer en 'other').
    """
    sectors = sectors_cfg.get("sectors", {})
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
        bucket = by_sector.setdefault(sid, {"exposure_eur": 0.0, "tickers": []})
        bucket["exposure_eur"] += exposure
        bucket["tickers"].append(tk)
        total_eur += exposure

    for sid, b in by_sector.items():
        b["share_pct"] = (b["exposure_eur"] / total_eur * 100.0) if total_eur > 0 else 0.0
    return by_sector


def _jp_tickers(by_sector: dict) -> list[str]:
    """Tickers .T (Tokyo) across all sectors."""
    out = []
    for _, b in by_sector.items():
        out.extend(t for t in b["tickers"] if t.endswith(".T"))
    return out


def compute_book_warnings(
    regime: str,
    positions: list[dict],
    indicator_values: dict[str, float | None],
) -> list[Warning]:
    """Apply rules. Returns sorted by severity (high first), max 4."""
    cfg = _load_sectors()
    if not cfg:
        return []
    by_sector = _book_composition(positions, cfg)
    if not by_sector:
        return []

    semis_share = by_sector.get("semis", {}).get("share_pct", 0.0)
    tech_mega_share = by_sector.get("tech_mega", {}).get("share_pct", 0.0)
    auto_ev_share = by_sector.get("auto_ev", {}).get("share_pct", 0.0)
    energy_share = by_sector.get("energy_commodities", {}).get("share_pct", 0.0)
    semis_tickers = by_sector.get("semis", {}).get("tickers", [])
    tech_tickers = by_sector.get("tech_mega", {}).get("tickers", [])

    jp_tickers = _jp_tickers(by_sector)
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
    if regime in ("FRAGILE", "STRESS", "LATE_CYCLE") and semis_share > 45.0:
        sev = "high" if regime == "STRESS" else "med"
        tyx_note = f"TYX {tyx:.2f} (>4.5 = repricing actif)" if tyx and tyx > 4.5 else ""
        warnings.append(Warning(
            severity=sev,
            rule_id="R1_semis_concentration",
            action=f"raise stops sur cluster semis ({semis_share:.0f}% du book)",
            rationale=(
                f"Regime {regime} : multiples growth sensibles aux taux. "
                f"{tyx_note}. Le book = {semis_share:.0f}% semis cyclical, premiers a craquer "
                f"en repricing brutal."
            ),
            tickers=semis_tickers[:5],
        ))

    # R2 : USDJPY proche/au-dessus 158 + JP exposure significative -> carry unwind.
    if usdjpy is not None and usdjpy > 158.0 and jp_share > 10.0 and jp_tickers:
        sev = "high" if usdjpy > 160.0 else "med"
        warnings.append(Warning(
            severity=sev,
            rule_id="R2_carry_unwind_jp",
            action=f"verifier hedge / size sur positions JP ({jp_share:.0f}% du book)",
            rationale=(
                f"USDJPY {usdjpy:.1f} > 158 = zone intervention BoJ. Carry unwind "
                f"-> sharp JPY appreciation -> JP-tech sell-off asymetrique. "
                f"Exposure JP: {jp_share:.0f}% sur {len(jp_tickers)} positions."
            ),
            tickers=jp_tickers[:5],
        ))

    # R3 : LATE_CYCLE/FRAGILE + growth-tech combined elevee -> diversifier hors growth.
    growth_tech = semis_share + tech_mega_share
    if regime in ("LATE_CYCLE", "FRAGILE") and growth_tech > 65.0:
        warnings.append(Warning(
            severity="med",
            rule_id="R3_growth_tech_dominance",
            action=f"diversifier hors growth-tech ({growth_tech:.0f}% combined)",
            rationale=(
                f"Regime {regime} + book = semis ({semis_share:.0f}%) + tech_mega "
                f"({tech_mega_share:.0f}%) = {growth_tech:.0f}% growth-sensitive. "
                f"Energy ({energy_share:.0f}%) + EU industrials apportent de la decorrelation."
            ),
            tickers=tech_tickers[:5],
        ))

    # R4 : STRESS + auto_ev exposure -> margins compression accelerent.
    if regime == "STRESS" and auto_ev_share > 3.0:
        warnings.append(Warning(
            severity="med",
            rule_id="R4_auto_ev_stress",
            action="rightsize cluster auto_ev",
            rationale=(
                f"Regime STRESS + auto/EV en contraction cycle = "
                f"compression marges + sentiment cassant."
            ),
            tickers=by_sector.get("auto_ev", {}).get("tickers", [])[:5],
        ))

    # R5 : COMPLACENT + zero stress flags -> consider tactical hedge.
    if regime == "COMPLACENT" and vix is not None and vix < 13.0:
        warnings.append(Warning(
            severity="low",
            rule_id="R5_complacent_hedge",
            action="considere hedge tactique (VIX call spread / SPY put)",
            rationale=(
                f"Regime COMPLACENT (VIX {vix:.1f} ultra-bas, spreads serres). "
                f"Cout hedge minimal historiquement; melt-up risk asymetrique."
            ),
            tickers=[],
        ))

    sev_order = {"high": 0, "med": 1, "low": 2}
    warnings.sort(key=lambda w: sev_order.get(w["severity"], 9))
    return warnings[:4]
