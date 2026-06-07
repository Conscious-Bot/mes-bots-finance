"""Axe 4 (b) QUALITY_BAR : ballast cible + verification live.

Spec : "ligne ballast definie (cash / decorrele / hedge de queue) +
factor_exposures exige le ballast et flag quand < cible".

Pattern M1 doctrine : la valeur ballast_strict_pct est DERIVABLE depuis les
positions actuelles + la liste ballast_strict_tickers. Ne JAMAIS stocker
fige (le YAML risk_watch declare un current_ballast_strict_pct = pollution
M1, garde comme metadata historique uniquement).

Source de verite :
- ballast_strict_tickers : declaratif risk_watch.yaml (decision user)
- target_ballast_strict_pct : declaratif risk_watch.yaml
- current_ballast_strict_pct : DERIVE LIVE ici (pas lu du YAML)
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def compute_ballast_strict(positions: list[dict]) -> dict | None:
    """Calcule live le pct ballast strict actuel + gap vs cible.

    Args:
        positions: list dicts avec keys 'ticker' + 'weight' (EUR market value).

    Returns:
        dict {
          'tickers_configured': set,    # liste declaree YAML
          'tickers_held': list,         # parmi configured, ceux effectivement detenus
          'tickers_missing': list,      # configured mais pas detenus (gap structurel)
          'current_pct': float,         # pct live ballast strict / total book
          'target_pct': float,          # cible declaree YAML
          'gap_pp': float,              # current - target (negatif = sous-pondere)
          'severity': str,              # 'ok' / 'warn' / 'breach'
          'declared_pct': float | None, # ce que le YAML disait (pollution M1)
        } ou None si config absente.
    """
    try:
        from shared.risk_watch import load_risk_watch
        cfg = load_risk_watch()
    except Exception as e:
        log.warning(f"compute_ballast_strict load failed: {e}")
        return None
    if not cfg or not cfg.get("risks"):
        return None

    # Risk #1 surchauffe_tech_ai porte la def ballast. Architecture multi-risk
    # ballast a faire si user veut un jour ballast par risque, pas pour 1er geste.
    risk0 = cfg["risks"][0]
    ballast_tickers = set(risk0.get("ballast_strict_tickers") or [])
    target = risk0.get("target") or {}
    target_pct = float(target.get("target_ballast_strict_pct") or 0.0)
    declared_pct = target.get("current_ballast_strict_pct")
    declared_pct = float(declared_pct) if declared_pct is not None else None

    if not positions:
        return {
            "tickers_configured": ballast_tickers,
            "tickers_held": [],
            "tickers_missing": sorted(ballast_tickers),
            "current_pct": 0.0,
            "target_pct": target_pct,
            "gap_pp": -target_pct,
            "severity": "breach",
            "declared_pct": declared_pct,
        }

    total_weight = sum(float(p.get("weight", 0)) for p in positions) or 1.0
    held_set = {p["ticker"] for p in positions if p.get("ticker")}
    tickers_held = sorted(ballast_tickers & held_set)
    tickers_missing = sorted(ballast_tickers - held_set)

    ballast_weight = sum(
        float(p.get("weight", 0)) for p in positions
        if p.get("ticker") in ballast_tickers
    )
    current_pct = ballast_weight / total_weight * 100
    gap_pp = current_pct - target_pct

    # Severite : gap > -3pp = ok ; > -7pp = warn ; <= -7pp = breach
    if gap_pp >= -3.0:
        severity = "ok"
    elif gap_pp >= -7.0:
        severity = "warn"
    else:
        severity = "breach"

    return {
        "tickers_configured": ballast_tickers,
        "tickers_held": tickers_held,
        "tickers_missing": tickers_missing,
        "current_pct": round(current_pct, 1),
        "target_pct": target_pct,
        "gap_pp": round(gap_pp, 1),
        "severity": severity,
        "declared_pct": declared_pct,
    }
