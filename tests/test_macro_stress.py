"""Tests macro_stress — chaîne donnée→signal→courbe→état. Véracité par assertion.

Couvre les garde-fous non-négociables (advisor 27/06) :
- donnée cassée (hors plausible) → EXCLUE, jamais lue comme calme (fail-closed L15)
- donnée stale → exclue
- pente (75%) écrase le niveau (25%) dans la famille taux
- l'état DÉRIVE du score (un seul chemin)
- seuil non-linéaire = accélération de régime
- snapshot réel 27/06 (oracles calmes) → PAS broken (le BROKEN était un artefact)
"""
from __future__ import annotations

import pytest

from intelligence import macro_stress as ms

# Snapshot des lectures réelles 27/06 (value, age_jours). Déterministe.
SNAP = {
    "HY_OAS": (278.0, 0.1), "MOVE": (66.79, 0.1), "T10Y2Y": (0.27, 5.1),
    "TYX": (4.86, 0.1), "BankReserves": (3033444.0, 5.1), "FedBalance_yoy": (0.66, 12.1),
    "KRE": (71.72, 5.1), "CopperGold": (0.0015, 5.1),  # VALIDE (0.00 à l'écran = artefact .2f)
    "CoreCPI": (2.82, 12.1), "MfgIP_yoy": (1.47, 12.1), "VIX": (18.41, 0.1),
    "BTC_drawdown180": (-34.91, 0.1), "Gold": (4078.7, 0.1),
    "USDJPY": (161.73, 0.1), "DXY": (101.43, 0.1),
}


def test_spec_invariants_pass():
    m = ms.load_model()  # raise si Σ weights != 100 ou Σ intra != 100
    assert sum(f["weight"] for f in m["families"].values()) == 100


def test_normalize_normal_direction():
    assert ms.normalize(300, 300, 800) == 0.0
    assert ms.normalize(800, 300, 800) == 1.0
    assert ms.normalize(550, 300, 800) == pytest.approx(0.5)
    assert ms.normalize(1500, 300, 800) == 1.0  # clamp


def test_normalize_inverted_direction_slope():
    # pente : floor 0.5 (sain) > ceiling -0.5 (inversion) => bas = stress
    assert ms.normalize(0.5, 0.5, -0.5) == 0.0       # raide = calme
    assert ms.normalize(-0.5, 0.5, -0.5) == 1.0      # inversée = stress max
    assert ms.normalize(0.0, 0.5, -0.5) == pytest.approx(0.5)
    assert ms.normalize(0.27, 0.5, -0.5) == pytest.approx(0.23)  # actuel = calme


def test_broken_data_flags_never_calm():
    """Exhaustif : 0-impossible / NaN / négatif-physique / stale → chacun EXCLU,
    jamais une contribution calme. La règle d'or fail-closed."""
    cases = {
        "CopperGold": (0.0, 1.0),       # ratio nul → < plausible_min
        "VIX": (-5.0, 1.0),             # VIX négatif = physiquement impossible
        "HY_OAS": (float("nan"), 1.0),  # NaN
        "MOVE": (66.0, 99.0),           # stale (>4j)
    }
    for src, reading in cases.items():
        snap = dict(SNAP)
        snap[src] = reading
        r = ms.compute_stress(snap)
        assert src in {e["source"] for e in r["excluded"]}, f"{src} {reading} non exclu"


def test_all_invalid_family_is_unknown_not_zero():
    """Une famille dont TOUT est cassé → signal None (UNKNOWN), JAMAIS 0 (faux calme)."""
    snap = dict(SNAP)
    snap["CopperGold"] = (0.0, 1.0)   # cassé
    snap["KRE"] = (71.0, 99.0)        # stale
    r = ms.compute_stress(snap)
    bp = next(f for f in r["families"] if f["family"] == "banks_plumbing")
    assert bp["signal"] is None  # UNKNOWN, pas une contribution nulle silencieuse


def test_valid_copper_is_scored():
    """Inverse : copper VALIDE (0.0015) est bien scoré (pas exclu à tort)."""
    r = ms.compute_stress(SNAP)
    assert "CopperGold" not in {e["source"] for e in r["excluded"]}
    bp = next(f for f in r["families"] if f["family"] == "banks_plumbing")
    assert bp["valid"] == 2


@pytest.mark.live_data  # lit storage.DB_PATH (debt_signals) — absent/vide en CI
def test_mapping_sources_are_real_debt_signals():
    """Chaque source spec DOIT être un vrai champ debt_signals — sinon le modèle
    calcule une courbe cohérente sur la MAUVAISE donnée (pire cas, rien ne crie)."""
    from shared import storage
    with storage.db() as cx:
        real = {r[0] for r in cx.execute(
            "SELECT DISTINCT indicator_name FROM debt_signals").fetchall()}
    if not real:
        pytest.skip("debt_signals vide (CI/DB fraîche) : rien à mapper")
    for fname, f in ms.load_model()["families"].items():
        for iname, ind in f["indicators"].items():
            src = ind.get("source")
            if src is None:
                continue
            assert src in real, f"{fname}/{iname}: source '{src}' absente de debt_signals"


def test_stale_data_excluded():
    snap = dict(SNAP)
    snap["VIX"] = (18.0, 99.0)  # vieux de 99j > tol 4j
    r = ms.compute_stress(snap)
    assert any(e["source"] == "VIX" and "stale" in e["reason"] for e in r["excluded"])


def test_slope_dominates_level_in_rates():
    """Pente calme + niveau élevé → signal famille proche de la pente (75%)."""
    snap = dict(SNAP)
    snap["T10Y2Y"] = (0.27, 1.0)   # pente calme -> ~0.23
    snap["TYX"] = (5.5, 1.0)       # niveau élevé -> ~0.80
    r = ms.compute_stress(snap)
    rates = next(f for f in r["families"] if f["family"] == "rates")
    # 0.75*0.23 + 0.25*0.80 = 0.37  -> dominé par la pente, loin de 0.80
    assert rates["signal"] < 0.45, f"niveau noie l'oracle : {rates['signal']}"


def test_state_derives_from_score():
    bands = ms.load_model()["bands"]
    assert ms._state_from_score(10, bands) == "STABLE"
    assert ms._state_from_score(40, bands) == "STRESSED"
    assert ms._state_from_score(65, bands) == "FRAGILE"
    assert ms._state_from_score(85, bands) == "BROKEN"
    # frontière : 30 -> stressed (pas stable)
    assert ms._state_from_score(30, bands) == "STRESSED"


def test_nonlinear_threshold_accelerates():
    """HY au-delà de 500bp accélère (régime), > contribution linéaire."""
    ind = ms.load_model()["families"]["credit"]["indicators"]["hy_spread"]
    # base linéaire à 650bp
    base = ms.normalize(650, ind["stress_floor"], ind["stress_ceiling"])
    sig = ms._apply_nonlinear(base, ind)
    assert sig > base  # accéléré
    # sous le seuil : linéaire intact
    base2 = ms.normalize(400, ind["stress_floor"], ind["stress_ceiling"])
    assert ms._apply_nonlinear(base2, ind) == pytest.approx(base2)


def test_snapshot_real_is_not_broken():
    """Le smoking gun : avec les oracles calmes (courbe +0.27, crédit 278bp),
    la courbe DÉRIVE en STRESS, PAS broken. Le V3 disait BROKEN = artefact."""
    r = ms.compute_stress(SNAP)
    assert r["score"] is not None
    assert r["score"] < 55, f"score {r['score']} : devrait être stress, pas fragile/broken"
    assert r["state"] in ("STABLE", "STRESSED"), r["state"]


def test_no_score_when_all_invalid():
    """Fail-closed total : si tout est cassé, score=None/NO-DATA, pas un faux calme."""
    broken = dict.fromkeys(SNAP, (None, None))
    r = ms.compute_stress(broken)
    assert r["score"] is None
    assert r["state"] == "NO-DATA"
