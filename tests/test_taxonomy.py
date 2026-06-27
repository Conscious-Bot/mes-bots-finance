"""Tests Phase 0 — loader shared/taxonomy.py (source unique catégorisation)."""
from __future__ import annotations

import pytest

from shared import taxonomy


def test_parse_ok():
    raw = taxonomy._load_raw()
    assert "layers" in raw
    assert "positions" in raw
    assert "drivers" in raw
    assert "geos" in raw
    assert "statuses" in raw


def test_held_planned_sorti_counts():
    assert len(taxonomy.held_tickers()) == 26
    assert len(taxonomy.planned_tickers()) == 7


def test_get_taxonomy_known():
    t = taxonomy.get_taxonomy("TSM")
    assert t["driver"] == "ai_capex"
    assert t["geo"] == "taiwan"
    assert t["status"] == "held"
    assert t["layer_primary"] == "manufacturing/foundry_leading"


def test_get_taxonomy_unknown_raises():
    with pytest.raises(taxonomy.TaxonomyError, match="absent du mapping"):
        taxonomy.get_taxonomy("UNKNOWN_TICKER_X9")


def test_layer_primary_in_layer_invariant():
    for tk in taxonomy._by_ticker():
        t = taxonomy.get_taxonomy(tk)
        assert t["layer_primary"] in t["layer"], (
            f"{tk}: layer_primary {t['layer_primary']} hors de {t['layer']}"
        )


def test_ai_capex_held_19():
    ai = taxonomy.by_driver("ai_capex", status="held")
    assert len(ai) == 19, f"ai_capex held = {len(ai)} (attendu 19)"
    for tk in ("TSM", "AMZN", "GOOGL", "GEV", "SU.PA", "AVGO", "ASML.AS"):
        assert tk in ai, f"{tk} doit être dans ai_capex held"
    for tk in ("CCJ", "HO.PA", "MP", "SPCX", "6324.T", "LNG", "SAF.PA"):
        assert tk not in ai, f"{tk} ne doit PAS être dans ai_capex held"


def test_decorrelators_7():
    decorr = {
        tk
        for d in ("resources_energy", "sovereignty", "commodities", "space", "robotics")
        for tk in taxonomy.by_driver(d, status="held")
    }
    assert decorr == {"LNG", "CCJ", "HO.PA", "SAF.PA", "MP", "SPCX", "6324.T"}


def test_geo_japan_5_held():
    j = taxonomy.by_geo("japan", status="held")
    assert set(j) == {"6857.T", "6920.T", "4063.T", "7011.T", "6324.T"}


def test_compute_hyperscaler_subcategory():
    hyper = taxonomy.by_layer_primary("compute/hyperscaler", status="held")
    assert set(hyper) == {"AMZN", "GOOGL"}


def test_coverage_holes_held():
    holes = taxonomy.coverage_holes(status="held")
    for sub in (
        "assembly/molding_equip",
        "assembly/substrate",
        "assembly/substrate_film",
        "capital_equipment/deposition_etch",
        "design/ip_cores",
        "energy/power_semis",
        "materials/multimetal",
    ):
        assert sub in holes, f"{sub} doit être un trou en held"


def test_coverage_holes_planned_only_molding_open():
    holes = taxonomy.coverage_holes(status="planned")
    assert "assembly/molding_equip" in holes, "Towa absent partout → trou ouvert"
    for sub in (
        "assembly/substrate",
        "assembly/substrate_film",
        "capital_equipment/deposition_etch",
        "design/ip_cores",
        "energy/power_semis",
        "materials/multimetal",
    ):
        assert sub not in holes, f"{sub} couvert en planned, ne doit plus être trou"


def test_sector_highlevel():
    # by_category résolution (default)
    assert taxonomy.sector_highlevel("TSM") == "semis"
    assert taxonomy.sector_highlevel("CCJ") == "energy_commodities"
    assert taxonomy.sector_highlevel("LNG") == "energy_commodities"
    assert taxonomy.sector_highlevel("HO.PA") == "defense_industrials_eu"
    assert taxonomy.sector_highlevel("SAF.PA") == "defense_industrials_eu"
    assert taxonomy.sector_highlevel("GEV") == "defense_industrials_eu"
    # Override historique Phase 3 (préservation Brier) : compute/hyperscaler → tech_mega
    assert taxonomy.sector_highlevel("AMZN") == "tech_mega"
    assert taxonomy.sector_highlevel("GOOGL") == "tech_mega"
    # Override historique : MP materials/rare_earths → energy_commodities (pas semis)
    assert taxonomy.sector_highlevel("MP") == "energy_commodities"
    # Tickers hors-mapping mais portés par overrides (historique Brier)
    assert taxonomy.sector_highlevel("NVDA") == "semis"
    assert taxonomy.sector_highlevel("AMD") == "semis"
    assert taxonomy.sector_highlevel("TSLA") == "auto_ev"


def test_sector_highlevel_info_rich():
    """Info riche Phase 3 : label + index + cycle_phase + cycle_note."""
    info = taxonomy.sector_highlevel_info("TSM")
    assert info["id"] == "semis"
    assert info["index"] == "SOXX"
    assert info["cycle_phase"] == "late"
    info = taxonomy.sector_highlevel_info("AMZN")
    assert info["id"] == "tech_mega"
    assert info["index"] == "XLK"
    info = taxonomy.sector_highlevel_info("TSLA")
    assert info["id"] == "auto_ev"
    assert info["cycle_phase"] == "contraction"


def test_cycle_phase_for():
    assert taxonomy.cycle_phase_for("TSM") == "late"
    assert taxonomy.cycle_phase_for("CCJ") == "early"
    assert taxonomy.cycle_phase_for("SAF.PA") == "mid"
    assert taxonomy.cycle_phase_for("TSLA") == "contraction"
    assert taxonomy.cycle_phase_for("UNKNOWN_X9") == "unknown"


def test_sectors_facade_compat():
    """shared/sectors.py façade lit la même source — préservation API + historique."""
    from shared import sectors as _sec
    # API compat : sector_for_ticker retourne TypedDict avec les bons champs
    info = _sec.sector_for_ticker("AMZN")
    assert info is not None
    assert info["id"] == "tech_mega"
    assert info["cycle_phase"] == "late"
    # Cycle phase passthrough
    assert _sec.cycle_phase_for_ticker("CCJ") == "early"
    assert _sec.cycle_phase_for_ticker("UNKNOWN_X9") == "unknown"


def test_validate_against_db_no_missing():
    r = taxonomy.validate_against_db(raise_on_missing=False)
    assert r["missing_in_mapping"] == [], (
        f"DB held absents du mapping : {r['missing_in_mapping']}"
    )
    assert r["in_db_not_held_in_map"] == [], (
        f"DB held mais pas marqués held dans mapping : {r['in_db_not_held_in_map']}"
    )


def test_planned_tickers_7():
    p = set(taxonomy.planned_tickers())
    assert p == {"IFX.DE", "PRY.MI", "ARM", "2802.T", "4062.T", "NDA.DE", "8035.T"}


def test_clean_sector_preserves_legacy_output():
    """Refonte 27/06 token-based : output identique à la cascade .replace."""
    assert taxonomy.clean_sector("ai_compute_2026") == "AI Compute"
    assert taxonomy.clean_sector("mag7") == "MAG 7"
    assert taxonomy.clean_sector("hpq") == "HPQ"
    assert taxonomy.clean_sector("hbm") == "HBM"
    assert taxonomy.clean_sector("eda") == "EDA"
    assert taxonomy.clean_sector("lng") == "LNG"
    assert taxonomy.clean_sector("asic") == "ASIC"
    assert taxonomy.clean_sector("cowos") == "CoWoS"
    assert taxonomy.clean_sector("idm_analog") == "IDM Analog"
    assert taxonomy.clean_sector("ip_cores") == "IP Cores"
    assert taxonomy.clean_sector(None) == "Sans thesis"
    assert taxonomy.clean_sector("") == "Sans thesis"


def test_clean_sector_no_substring_collision():
    """Refonte 27/06 doit régler le bug "Fx" → "FX" frappant des sous-chaînes innocentes.

    Le token-based ne touche que les mots entiers (split sur ' '), pas les substrings.
    """
    # Mot innocent contenant 'ai' en sous-chaîne ne doit pas être frappé.
    assert taxonomy.clean_sector("captain") == "Captain"
    assert taxonomy.clean_sector("mosaic") == "Mosaic"
    assert taxonomy.clean_sector("airline") == "Airline"
    # Pas de collision Fx (l'ancien .replace("Fx","FX") aurait frappé Fxd→FXd)
    assert taxonomy.clean_sector("fixed") == "Fixed"
    # Mais l'acronyme entier doit toujours marcher
    assert taxonomy.clean_sector("ai") == "AI"


def test_invariants_already_validated_at_load():
    """_load_raw() raise si layer_primary∉layer ou couche hors vocab. Si on arrive ici, OK."""
    taxonomy._load_raw()  # ne raise pas = invariants OK
