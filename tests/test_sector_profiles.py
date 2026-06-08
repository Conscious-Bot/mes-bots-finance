"""Tests verrouillants SOCLE substrat : sector_profiles canoniques.

7 invariants critiques (cf SPEC_SECTOR_TAXONOMY.md §7) :
  1. Structure complète MAIS chaque profil porte son evidence_tier obligatoire
  2. Aucun profil fabriqué : tier A/B marqué, jamais présenté comme S
  3. Fail-closed : ticker non-classable -> UNCLASSIFIED + profile générique
  4. deliverable_kpis présents pour tout sous-secteur tenu
  5. cyclicality dans enum strict (pas littéral arbitraire)
  6. Shrinkage actif : tier S nécessite holdings_validated non-vide (validator)
  7. Tier S exclusif : audit_metadata.holdings_validated documenté avec dates

+ Walking-skeleton : ASML.AS traverse profile_for_ticker -> profil semis
  tier-S validé -> deliverable_kpis exhaustifs.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.sector_profiles import (
    SectorProfile,
    all_profiles,
    get_profile,
    load_profiles,
    profile_for_ticker,
)

# === Test 1 : Chaque profil a son evidence_tier (validator Pydantic) =====


def test_all_profiles_have_evidence_tier() -> None:
    """Aucun profil sans tier. Validator Pydantic Literal["S", "A", "B"]."""
    for name, p in all_profiles().items():
        assert p.evidence_tier in ("S", "A", "B"), (
            f"Profile '{name}' tier={p.evidence_tier!r} invalide"
        )


def test_profile_missing_tier_raises() -> None:
    """Construire un profile sans evidence_tier MUST raise."""
    with pytest.raises(ValidationError):
        SectorProfile.model_validate({
            "name": "test.subsector",
            "cyclicality": "moderate",
            "criticality": "moat",
            "macro_factor": "Other",
            # evidence_tier MISSING
        })


# === Test 2 : Tier S exclusif (audit_metadata.holdings_validated obligatoire) ==


def test_tier_s_without_holdings_validated_raises() -> None:
    """Affirmer tier=S sans holdings_validated MUST raise."""
    with pytest.raises(ValidationError, match="evidence_tier=S but audit_metadata"):
        SectorProfile.model_validate({
            "name": "fake.tierS",
            "cyclicality": "cyclical",
            "criticality": "moat",
            "macro_factor": "AI capex",
            "evidence_tier": "S",
            "deliverable_kpis": ["some_kpi"],
            # audit_metadata vide -> validator raise
        })


def test_all_tier_s_profiles_have_holdings_validated() -> None:
    """Tous les tier=S dans le yaml ont leur audit_metadata.holdings_validated."""
    for name, p in all_profiles().items():
        if p.evidence_tier == "S":
            assert p.audit_metadata.holdings_validated, (
                f"Profile tier-S '{name}' sans holdings_validated (impossible par validator)"
            )
            # Chaque entry doit avoir ticker + date
            for hv in p.audit_metadata.holdings_validated:
                assert hv.ticker
                assert hv.validated_at


# === Test 3 : Tier A/B marqué, pas présenté comme S =====================


def test_tier_a_profiles_have_empty_holdings_validated() -> None:
    """Tier A = prior littérature, holdings_validated vide attendu."""
    for name, p in all_profiles().items():
        if p.evidence_tier == "A":
            assert not p.audit_metadata.holdings_validated, (
                f"Profile tier-A '{name}' a des holdings_validated -- devrait être tier-S"
            )


def test_at_least_one_tier_s_profile_exists() -> None:
    """SPEC : au moins un profil tier-S validé (semis dans le SPEC fondateur)."""
    profiles = all_profiles()
    tier_s = [name for name, p in profiles.items() if p.evidence_tier == "S"]
    assert len(tier_s) >= 1, f"Aucun profil tier-S declaré, attendu au moins semis : {list(profiles.keys())}"
    # Semis equipment doit être tier S (SPEC §2 exemple canonique)
    assert "semiconductors.equipment" in tier_s, (
        "semiconductors.equipment doit être tier-S (cf SPEC §2 cas canonique)"
    )


# === Test 4 : deliverable_kpis présents pour sous-secteurs tenus (tier S) ===


def test_tier_s_profiles_have_deliverable_kpis() -> None:
    """Tout profil tier-S a deliverable_kpis (validator Pydantic l'exige)."""
    for name, p in all_profiles().items():
        if p.evidence_tier == "S":
            assert p.deliverable_kpis, (
                f"Profile tier-S '{name}' n'a pas de deliverable_kpis -- moteur micro ne peut pas lire"
            )
            assert len(p.deliverable_kpis) >= 3, (
                f"Profile tier-S '{name}' a {len(p.deliverable_kpis)} KPIs, attendu >=3 pour vraie mesurabilité"
            )


def test_holdings_validated_requires_deliverable_kpis() -> None:
    """holdings_validated non-vide -> deliverable_kpis obligatoires (validator)."""
    with pytest.raises(ValidationError, match="deliverable_kpis is empty"):
        SectorProfile.model_validate({
            "name": "fake.held_no_kpis",
            "cyclicality": "cyclical",
            "criticality": "moat",
            "macro_factor": "AI capex",
            "evidence_tier": "S",
            "deliverable_kpis": [],  # vide alors qu'on a des holdings
            "audit_metadata": {
                "holdings_validated": [{"ticker": "FAKE", "validated_at": "2026-01-01"}],
            },
        })


# === Test 5 : cyclicality enum strict ===================================


def test_cyclicality_must_be_valid_enum() -> None:
    """Cyclicality dans {defensive, moderate, cyclical, deep_cyclical} uniquement."""
    with pytest.raises(ValidationError):
        SectorProfile.model_validate({
            "name": "test.invalid_cycle",
            "cyclicality": "super_cyclical_random",  # not in Literal enum
            "criticality": "moat",
            "macro_factor": "Other",
            "evidence_tier": "B",
        })


def test_all_profiles_cyclicality_in_enum() -> None:
    """Tous les profils existants ont cyclicality dans l'enum (defensive vs corruption)."""
    valid = {"defensive", "moderate", "cyclical", "deep_cyclical"}
    for name, p in all_profiles().items():
        assert p.cyclicality in valid, f"Profile '{name}' cyclicality={p.cyclicality} hors enum"


# === Test 6 : criticality enum + UNCLASSIFIED fallback ================


def test_criticality_must_be_valid_enum() -> None:
    with pytest.raises(ValidationError):
        SectorProfile.model_validate({
            "name": "test.invalid_crit",
            "cyclicality": "moderate",
            "criticality": "super_chokepoint_invented",  # invalid
            "macro_factor": "Other",
            "evidence_tier": "B",
        })


def test_unclassified_profile_exists() -> None:
    """Le profil fallback GENERIC_UNCLASSIFIED doit exister pour fail-closed."""
    profiles = all_profiles()
    assert "GENERIC_UNCLASSIFIED" in profiles, (
        "Profile GENERIC_UNCLASSIFIED manquant -- requis pour fail-closed sur tickers non-classables"
    )
    unc = profiles["GENERIC_UNCLASSIFIED"]
    assert unc.evidence_tier == "B"
    assert not unc.deliverable_kpis, "UNCLASSIFIED ne doit PAS avoir de KPIs (signal moteur=no_read)"


# === Test 7 : Profile registry frozen (anti-tampering) ================


def test_profile_is_frozen() -> None:
    p = get_profile("semiconductors.equipment")
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        p.evidence_tier = "B"  # type: ignore[misc]


def test_get_profile_unknown_raises_keyerror() -> None:
    """get_profile('TOTALLY.MADE_UP') doit raise KeyError."""
    with pytest.raises(KeyError, match="Sous-secteur inconnu"):
        get_profile("totally.made_up_subsector")


# === Walking-skeleton : ASML.AS traverse profile_for_ticker ============


def test_walking_skeleton_asml_to_semis_equipment_tier_s() -> None:
    """LE walking-skeleton : ASML.AS (holding tier-S) traverse le pipeline complet.

    Discipline L24 : pas seulement mocks. Un VRAI ticker holding traverse
    profile_for_ticker -> profil semis.equipment tier-S -> deliverable_kpis
    exhaustifs (bookings_yoy, book_to_bill, utilization, asp_trend, etc.).
    """
    profile, is_unclassified = profile_for_ticker("ASML.AS")
    assert is_unclassified is False, "ASML.AS classified -- doit avoir profil défini"
    assert profile.name == "semiconductors.equipment"
    assert profile.evidence_tier == "S"
    assert profile.cyclicality == "deep_cyclical"
    assert profile.criticality == "chokepoint"
    assert profile.macro_factor == "AI capex"
    # Deliverable KPIs : sectoriels (pas génériques)
    assert "bookings_yoy" in profile.deliverable_kpis
    assert "asp_trend" in profile.deliverable_kpis
    assert "utilization" in profile.deliverable_kpis
    # Crowding proxies : SMH/SOXX (ETFs canoniques semis)
    assert "SMH" in profile.crowding_proxies
    assert "SOXX" in profile.crowding_proxies
    # audit_metadata documenté
    assert profile.audit_metadata.holdings_validated
    tickers_validated = {hv.ticker for hv in profile.audit_metadata.holdings_validated}
    assert "ASML.AS" in tickers_validated


def test_walking_skeleton_tsm_to_foundry_tier_s() -> None:
    """TSM (foundry holding) -> tier-S foundry profile."""
    profile, is_unc = profile_for_ticker("TSM")
    assert is_unc is False
    assert profile.name == "semiconductors.foundry"
    assert profile.evidence_tier == "S"
    assert "leading_edge_mix_pct" in profile.deliverable_kpis


def test_walking_skeleton_mu_to_memory_tier_s() -> None:
    """MU (memory holding) -> tier-S memory profile."""
    profile, is_unc = profile_for_ticker("MU")
    assert is_unc is False
    assert profile.name == "semiconductors.memory"
    assert profile.evidence_tier == "S"
    assert profile.cyclicality == "deep_cyclical"
    assert "hbm_mix_pct" in profile.deliverable_kpis


def test_walking_skeleton_amd_nvda_to_fabless_tier_s() -> None:
    """AMD et NVDA (fabless holdings) -> tier-S fabless profile."""
    for ticker in ["AMD", "NVDA"]:
        profile, is_unc = profile_for_ticker(ticker)
        assert is_unc is False, f"{ticker} doit être classified"
        assert profile.name == "semiconductors.fabless"
        assert profile.evidence_tier == "S"


def test_unclassified_ticker_fail_closed() -> None:
    """Ticker non-classable -> profile UNCLASSIFIED + is_unclassified=True.

    Fail-closed : le système dit qu'il NE SAIT PAS lire ce stock, pas un
    profil fabriqué.
    """
    profile, is_unc = profile_for_ticker("RANDOM_NON_HELD_TICKER_XYZ")
    assert is_unc is True, "Ticker non-mappé -> UNCLASSIFIED"
    assert profile.name == "GENERIC_UNCLASSIFIED"
    assert profile.evidence_tier == "B"
    assert not profile.deliverable_kpis, "UNCLASSIFIED ne donne PAS de KPIs"


def test_tier_a_profile_exists_for_unheld_sector() -> None:
    """Au moins un profil tier-A (secteur connu mais pas tenu) doit exister."""
    profiles = all_profiles()
    tier_a = [name for name, p in profiles.items() if p.evidence_tier == "A"]
    assert len(tier_a) >= 1, "Au moins un profil tier-A attendu (banks/energy/healthcare/...)"


# === Sanity : registry version + loader ================================


def test_registry_has_version() -> None:
    reg = load_profiles()
    assert reg.vocabulary_version
    assert reg.schema_version


def test_all_profiles_have_name_matching_key() -> None:
    """Le name du profil == sa clé dans le registry."""
    for key, p in all_profiles().items():
        assert p.name == key, f"Mismatch key={key} vs profile.name={p.name}"
