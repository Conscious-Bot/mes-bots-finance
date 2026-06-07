"""Axe 4 (b) QUALITY_BAR : tests ballast_compute live.

M1 doctrine : valeur derivable JAMAIS stockee figee. YAML porte
declaratif (tickers + target) ; live deriv ici.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from intelligence.ballast_compute import compute_ballast_strict


def _fake_cfg(tickers=None, target=20.0, declared=None):
    return {
        "risks": [{
            "ballast_strict_tickers": tickers or ["MP", "SAF.PA", "HO.PA", "CCJ"],
            "target": {
                "target_ballast_strict_pct": target,
                "current_ballast_strict_pct": declared,
            },
        }],
    }


def _positions(d: dict[str, float]) -> list[dict]:
    return [{"ticker": tk, "weight": w} for tk, w in d.items()]


def test_empty_positions_breach() -> None:
    with patch("shared.risk_watch.load_risk_watch", return_value=_fake_cfg()):
        out = compute_ballast_strict([])
    assert out["current_pct"] == 0.0
    assert out["gap_pp"] == -20.0
    assert out["severity"] == "breach"
    assert out["tickers_held"] == []
    assert out["tickers_missing"] == sorted({"MP", "SAF.PA", "HO.PA", "CCJ"})


def test_full_ballast_ok() -> None:
    # 20% du book = ballast strict pile cible -> ok, gap 0
    positions = _positions({
        "MP": 5000, "SAF.PA": 5000, "HO.PA": 5000, "CCJ": 5000,  # 20k = 20%
        "ASML.AS": 80000,
    })
    with patch("shared.risk_watch.load_risk_watch", return_value=_fake_cfg()):
        out = compute_ballast_strict(positions)
    assert out["current_pct"] == 20.0
    assert out["gap_pp"] == 0.0
    assert out["severity"] == "ok"
    assert out["tickers_missing"] == []


def test_warn_threshold_minus_5pp() -> None:
    # 15% ballast = gap -5pp = warn
    positions = _positions({
        "MP": 3750, "SAF.PA": 3750, "HO.PA": 3750, "CCJ": 3750,  # 15k = 15%
        "ASML.AS": 85000,
    })
    with patch("shared.risk_watch.load_risk_watch", return_value=_fake_cfg()):
        out = compute_ballast_strict(positions)
    assert out["current_pct"] == 15.0
    assert out["gap_pp"] == -5.0
    assert out["severity"] == "warn"


def test_breach_threshold_minus_10pp() -> None:
    # 10% ballast = gap -10pp = breach
    positions = _positions({
        "MP": 2500, "SAF.PA": 2500, "HO.PA": 2500, "CCJ": 2500,  # 10k = 10%
        "ASML.AS": 90000,
    })
    with patch("shared.risk_watch.load_risk_watch", return_value=_fake_cfg()):
        out = compute_ballast_strict(positions)
    assert out["current_pct"] == 10.0
    assert out["gap_pp"] == -10.0
    assert out["severity"] == "breach"


def test_missing_ticker_structural_gap() -> None:
    # Si user n'a jamais ouvert MP, le tracker doit le surfacer
    positions = _positions({
        "SAF.PA": 5000, "HO.PA": 5000, "CCJ": 5000,  # 15k, MP absent
        "ASML.AS": 85000,
    })
    with patch("shared.risk_watch.load_risk_watch", return_value=_fake_cfg()):
        out = compute_ballast_strict(positions)
    assert "MP" in out["tickers_missing"]
    assert "MP" not in out["tickers_held"]
    assert out["current_pct"] == 15.0


def test_declared_vs_live_divergence_surfaced() -> None:
    # YAML declare 14% mais live calcule 10% -> les 2 sont retournes
    # (live = source verite, declared = metadata historique)
    positions = _positions({
        "MP": 2500, "SAF.PA": 2500, "HO.PA": 2500, "CCJ": 2500,  # 10%
        "ASML.AS": 90000,
    })
    with patch(
        "shared.risk_watch.load_risk_watch",
        return_value=_fake_cfg(declared=14.0),
    ):
        out = compute_ballast_strict(positions)
    assert out["current_pct"] == 10.0
    assert out["declared_pct"] == 14.0
    # gap_pp calcule sur live, pas declared
    assert out["gap_pp"] == -10.0


def test_config_absent_returns_none() -> None:
    with patch("shared.risk_watch.load_risk_watch", return_value=None):
        out = compute_ballast_strict([{"ticker": "X", "weight": 100}])
    assert out is None


@pytest.mark.parametrize("gap_pp,expected", [
    (-3.0, "ok"),       # boundary inclusive
    (-3.1, "warn"),
    (-7.0, "warn"),     # boundary inclusive
    (-7.1, "breach"),
    (5.0, "ok"),        # surpondere
])
def test_severity_boundaries(gap_pp: float, expected: str) -> None:
    target = 20.0
    current = target + gap_pp
    # Construit positions correspondantes
    ballast_weight = current
    other_weight = 100 - current
    positions = [
        {"ticker": "MP", "weight": ballast_weight},
        {"ticker": "ASML.AS", "weight": other_weight},
    ]
    with patch(
        "shared.risk_watch.load_risk_watch",
        return_value=_fake_cfg(tickers=["MP"]),
    ):
        out = compute_ballast_strict(positions)
    assert out["severity"] == expected
