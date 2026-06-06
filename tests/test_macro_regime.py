"""Phase A — tests classify_regime + journal helpers.

7 tests dont test critique L4 (idempotence : meme input -> meme output,
sans side-effect).
"""

from intelligence.macro_regime import classify_regime


def _readings(**overrides):
    """Helper : 15 indicators, defaults safe (calm/RISK_ON default)."""
    base = {
        "VIX": {"indicator": "VIX", "value": 17.0, "dot": "calm"},
        "HY_OAS": {"indicator": "HY_OAS", "value": 300.0, "dot": "calm"},
        "USDJPY": {"indicator": "USDJPY", "value": 150.0, "dot": "calm"},
        "TYX": {"indicator": "TYX", "value": 3.8, "dot": "calm"},
        "DXY": {"indicator": "DXY", "value": 98.0, "dot": "calm"},
        "MOVE": {"indicator": "MOVE", "value": 80.0, "dot": "calm"},
        "T10Y2Y": {"indicator": "T10Y2Y", "value": 1.0, "dot": "calm"},
        "Gold": {"indicator": "Gold", "value": 3000.0, "dot": "calm"},
        "BTC_drawdown180": {"indicator": "BTC_drawdown180", "value": -10.0, "dot": "calm"},
        "BankReserves": {"indicator": "BankReserves", "value": 3_500_000.0, "dot": "calm"},
        "KRE": {"indicator": "KRE", "value": 70.0, "dot": "calm"},
        "CopperGold": {"indicator": "CopperGold", "value": 0.0015, "dot": "calm"},
        "CoreCPI": {"indicator": "CoreCPI", "value": 2.0, "dot": "calm"},
        "MfgIP_yoy": {"indicator": "MfgIP_yoy", "value": 1.5, "dot": "calm"},
        "FedBalance_yoy": {"indicator": "FedBalance_yoy", "value": 0.5, "dot": "calm"},
    }
    for k, v in overrides.items():
        base[k] = v
    return base


def test_classify_regime_risk_on_default():
    """Tout calm + VIX moderee -> RISK_ON (default healthy)."""
    out = classify_regime(_readings())
    assert out["regime"] == "RISK_ON"
    assert "default" in out["triggers"]


def test_classify_regime_complacent_ultra_low_vol():
    """VIX < 14 + HY < 250 + zero danger -> COMPLACENT (melt-up risk)."""
    r = _readings(
        VIX={"indicator": "VIX", "value": 12.0, "dot": "calm"},
        HY_OAS={"indicator": "HY_OAS", "value": 220.0, "dot": "calm"},
    )
    out = classify_regime(r)
    assert out["regime"] == "COMPLACENT"


def test_classify_regime_late_cycle_rates_dxy_vix_asleep():
    """Taux > 4.5 + DXY > 100 + VIX < 18 -> LATE_CYCLE."""
    r = _readings(
        TYX={"indicator": "TYX", "value": 4.8, "dot": "danger"},
        DXY={"indicator": "DXY", "value": 102.0, "dot": "warn"},
        VIX={"indicator": "VIX", "value": 16.0, "dot": "calm"},
    )
    out = classify_regime(r)
    assert out["regime"] == "LATE_CYCLE"


def test_classify_regime_fragile_multi_danger_vol_asleep():
    """3+ dangers + VIX < 22 -> FRAGILE (stress reel, marche pas reveille).

    Cas reel observable au 06/06 : TYX+USDJPY+BTC = 3 dangers, VIX 15.4
    -> doit retourner FRAGILE, pas RISK_ON ni STRESS.
    """
    r = _readings(
        TYX={"indicator": "TYX", "value": 4.98, "dot": "danger"},
        USDJPY={"indicator": "USDJPY", "value": 159.0, "dot": "danger"},
        BTC_drawdown180={"indicator": "BTC_drawdown180", "value": -35.0, "dot": "danger"},
        VIX={"indicator": "VIX", "value": 15.4, "dot": "calm"},
    )
    out = classify_regime(r)
    assert out["regime"] == "FRAGILE"
    assert out["danger_count"] == 3


def test_classify_regime_stress_vix_high():
    """VIX > 22 -> STRESS direct (regle prioritaire)."""
    r = _readings(VIX={"indicator": "VIX", "value": 28.0, "dot": "danger"})
    out = classify_regime(r)
    assert out["regime"] == "STRESS"


def test_classify_regime_stress_hy_oas_blowout():
    """HY_OAS > 400 -> STRESS (credit panic)."""
    r = _readings(HY_OAS={"indicator": "HY_OAS", "value": 450.0, "dot": "danger"})
    out = classify_regime(r)
    assert out["regime"] == "STRESS"


def test_classify_regime_l4_idempotent():
    """L4 CRITIQUE : appel deux fois avec meme input -> meme output, no side-effect.

    Le classifier est pur : aucune DB, aucun cache, aucune mutation. Une
    transition est une lecture, pas une fonction stateful.
    """
    r = _readings(
        TYX={"indicator": "TYX", "value": 4.98, "dot": "danger"},
        USDJPY={"indicator": "USDJPY", "value": 159.0, "dot": "danger"},
        BTC_drawdown180={"indicator": "BTC_drawdown180", "value": -35.0, "dot": "danger"},
    )
    out1 = classify_regime(r)
    out2 = classify_regime(r)
    assert out1 == out2
    assert out1["regime"] == out2["regime"]
    assert out1["triggers"] == out2["triggers"]


def test_classify_regime_missing_data_safe():
    """Tous indicateurs absents -> RISK_ON default (pas de crash).

    Mode degraded (cf design_mode_vacances doctrine) : data manquante
    ne doit pas planter le classifier, juste retourner default safe.
    """
    out = classify_regime({})
    assert out["regime"] == "RISK_ON"
    assert out["danger_count"] == 0
    assert out["warn_count"] == 0
    assert out["silent_count"] == 0


def test_classify_regime_six_warn_threshold_fragile():
    """6+ indicators warn/danger melanges -> FRAGILE.

    Test boundary : exactement 6 entre warn+danger force FRAGILE meme
    si pas 3 danger purs.
    """
    r = _readings(
        Gold={"indicator": "Gold", "value": 4500.0, "dot": "warn"},
        HY_OAS={"indicator": "HY_OAS", "value": 350.0, "dot": "warn"},
        T10Y2Y={"indicator": "T10Y2Y", "value": 0.3, "dot": "warn"},
        MOVE={"indicator": "MOVE", "value": 95.0, "dot": "warn"},
        DXY={"indicator": "DXY", "value": 103.0, "dot": "warn"},
        CoreCPI={"indicator": "CoreCPI", "value": 3.0, "dot": "warn"},
    )
    out = classify_regime(r)
    assert out["regime"] == "FRAGILE"
    assert out["warn_count"] == 6
