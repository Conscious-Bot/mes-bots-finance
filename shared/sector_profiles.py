"""SOCLE substrat : sector_profiles canoniques (agnosticité au book).

Cf SPEC_SECTOR_TAXONOMY.md. Pour tout ticker entrant, après classification
(ticker_classifier), hériter d'un PROFIL canonique qui dit au moteur
COMMENT LIRE ce ticker -- deliverable_kpis sectoriels, crowding_proxies,
cyclicality, criticality, invalidation_template.

L'invariant central : pas de profil sans evidence_tier. Tier S exclusif
(audit_metadata.holdings_validated obligatoire). Shrinkage au mérite B->A->S,
jamais d'emblée. Fail-closed : ticker non-classable -> UNCLASSIFIED + flag,
pas de profil fabriqué.

Usage :
    from shared.sector_profiles import get_profile, profile_for_ticker

    # Direct par sous-secteur
    profile = get_profile("semiconductors.equipment")
    # profile.deliverable_kpis = ["bookings_yoy", ...]
    # profile.evidence_tier = "S"

    # Par ticker (via classification)
    profile, tier = profile_for_ticker("ASML.AS")
    # Si classifié semis.equipment -> profile complet tier=S
    # Si non-classable -> profile GENERIC_UNCLASSIFIED tier=B
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PROFILES_PATH = _REPO_ROOT / "config" / "sector_profiles.yaml"


# === Sub-models =============================================================


class HoldingValidated(BaseModel):
    """Une entrée d'audit pour holdings_validated (tier=S obligatoire)."""

    model_config = {"extra": "forbid", "frozen": True}

    ticker: str = Field(min_length=1)
    validated_at: str = Field(min_length=1, description="ISO date du validation event")


class AuditMetadata(BaseModel):
    """Provenance / audit du profil. holdings_validated obligatoire pour tier=S."""

    model_config = {"extra": "forbid", "frozen": True}

    holdings_validated: list[HoldingValidated] = Field(default_factory=list)
    notes: str = ""


# === SectorProfile ==========================================================


class SectorProfile(BaseModel):
    """Profil canonique d'un sous-secteur. Hérité par tout ticker de ce sous-secteur.

    Frozen + extra='forbid' : anti-tampering downstream. L'étage compose,
    ne mute pas.
    """

    model_config = {"extra": "forbid", "frozen": True}

    name: str = Field(min_length=1, description="Identifier canonique (e.g. semiconductors.equipment)")
    cyclicality: Literal["defensive", "moderate", "cyclical", "deep_cyclical"]
    criticality: Literal["commodity", "moat", "chokepoint"]
    macro_factor: str = Field(min_length=1, description="Cf classifier macro_factor enum")
    deliverable_kpis: list[str] = Field(default_factory=list,
                                         description="KPIs sectoriels pour 'realite livrable' (divergence micro)")
    crowding_proxies: list[str] = Field(default_factory=list, description="ETFs qui crowdent le secteur")
    invalidation_template: list[str] = Field(default_factory=list, description="Kill-criteria type du secteur")
    cycle_role: Literal[
        "early_cyclical", "mid_cyclical", "late_cyclical", "early", "mid", "late",
        "defensive", "unknown"
    ] = "unknown"
    evidence_tier: Literal["S", "A", "B"]
    audit_metadata: AuditMetadata = Field(default_factory=AuditMetadata)

    @model_validator(mode="after")
    def _tier_s_requires_holdings_validated(self) -> SectorProfile:
        """Tier S exclusif : nécessite holdings_validated non-vide.

        Doctrine : on n'affirme pas tier=S d'emblée. S = expertise PROUVÉE
        sur holdings actifs. Sinon tier=A (prior littérature) ou B (générique).
        """
        if self.evidence_tier == "S" and not self.audit_metadata.holdings_validated:
            raise ValueError(
                f"Sector profile '{self.name}' has evidence_tier=S but audit_metadata.holdings_validated is empty. "
                "Tier S nécessite holdings actifs validés (anti-affirmation, cf SPEC §7 invariant 7)."
            )
        return self

    @model_validator(mode="after")
    def _deliverable_kpis_required_for_held_sectors(self) -> SectorProfile:
        """Un sous-secteur avec holdings_validated DOIT avoir des deliverable_kpis.

        Sinon le moteur micro ne peut pas lire les noms de ce secteur -> flag.
        Cf SPEC §7 invariant 4.
        """
        if self.audit_metadata.holdings_validated and not self.deliverable_kpis:
            raise ValueError(
                f"Sector profile '{self.name}' has holdings_validated but deliverable_kpis is empty. "
                "Un sous-secteur tenu DOIT avoir des KPIs sectoriels mesurables (cf SPEC §7 invariant 4)."
            )
        return self


# === Registry ===============================================================


class ProfileRegistry(BaseModel):
    """Le registre complet, parsé depuis config/sector_profiles.yaml."""

    model_config = {"extra": "forbid", "frozen": True}

    vocabulary_version: str
    schema_version: str
    profiles: dict[str, SectorProfile]


@lru_cache(maxsize=1)
def load_profiles(path: str | None = None) -> ProfileRegistry:
    """Charge le registre depuis YAML, valide via Pydantic.

    LRU-cache : un seul appel par process. Appeler load_profiles.cache_clear()
    pour reload (tests qui mutent le fichier).
    """
    p = Path(path) if path else _PROFILES_PATH
    if not p.exists():
        raise FileNotFoundError(f"sector_profiles.yaml introuvable a {p}")
    with p.open() as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"sector_profiles.yaml malforme : root doit etre dict, got {type(raw)}")
    vocab_version = raw.pop("vocabulary_version", None) or "unknown"
    schema_version = raw.pop("schema_version", None) or "unknown"
    profiles: dict[str, SectorProfile] = {}
    for name, body in raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"Profile '{name}' body must be dict, got {type(body)}")
        try:
            payload = dict(body)
            payload["name"] = name
            profiles[name] = SectorProfile.model_validate(payload)
        except Exception as e:
            raise ValueError(f"Profile '{name}' validation failed : {e}") from e
    return ProfileRegistry(
        vocabulary_version=vocab_version,
        schema_version=schema_version,
        profiles=profiles,
    )


# === Public API =============================================================


def get_profile(sub_sector: str) -> SectorProfile:
    """Retourne le profil canonique pour un sous-secteur.

    Raise KeyError si sub_sector non-déclaré (pas de fabrication panel-locale).
    Pour fail-closed sur ticker non-classable, utiliser profile_for_ticker().
    """
    reg = load_profiles()
    if sub_sector not in reg.profiles:
        raise KeyError(
            f"Sous-secteur inconnu '{sub_sector}'. Ajouter au registre config/sector_profiles.yaml "
            "(acte délibéré, comme une entrée GLOSSARY)."
        )
    return reg.profiles[sub_sector]


def profile_for_ticker(ticker: str) -> tuple[SectorProfile, bool]:
    """Retourne (profile, is_unclassified) pour un ticker.

    is_unclassified=True signale fail-closed : pas de classification confiante,
    profile retourné = GENERIC_UNCLASSIFIED (tier=B), caller doit afficher
    UNCLASSIFIED flag et ne pas faire de lecture confiante.

    Pipeline :
      1. Lit la classification existante (intelligence/ticker_classifier)
      2. Mappe macro_factor + value_chain_stage -> sub_sector canonique
      3. Retourne le profile correspondant OU GENERIC_UNCLASSIFIED

    V0 minimal : mapping hardcodé sur les profils tier-S existants.
    V1 (future) : table de mapping dans sectors.yaml.
    """
    sub_sector = _classify_ticker_to_subsector(ticker)
    if sub_sector is None:
        return get_profile("GENERIC_UNCLASSIFIED"), True
    try:
        return get_profile(sub_sector), False
    except KeyError:
        # Sous-secteur identifié mais profil pas encore declaré -> fallback
        log.warning(f"Ticker {ticker} -> sub_sector {sub_sector} mais profil absent. Fallback UNCLASSIFIED.")
        return get_profile("GENERIC_UNCLASSIFIED"), True


def _classify_ticker_to_subsector(ticker: str) -> str | None:
    """Mappe ticker -> sub_sector canonique via classifier existant + lookup.

    V0 : hardcoded sur les tickers semis tier-S validés. V1 sera une lookup
    table dans config/sectors.yaml (extension YAML existant).
    """
    # V0 mapping basique sur les sub_sectors tier-S
    # (en attendant l'extension de config/sectors.yaml en V1)
    EQUIPMENT = {"ASML.AS", "AMAT", "LRCX", "KLAC", "TER", "ALAB", "BESI.AS",
                 "6920.T",  # Lasertec (Japan, EUV inspection equipment)
                 "6857.T",  # Advantest (Japan, ATE test equipment)
                 "4063.T",  # Shin-Etsu Chemical (Japan, wafer/photoresist materials)
                 "ENTG",    # Entegris (materials/equipment hybrid)
                 "COHR",    # Coherent (lasers / EUV components)
                 }
    FOUNDRY = {"TSM"}
    MEMORY = {"MU", "WDC", "STX",
              "000660.KS",  # SK Hynix (Korea, DRAM/NAND/HBM)
              }
    FABLESS = {"AMD", "NVDA", "AVGO", "QCOM", "MRVL", "SNPS"}

    t = ticker.upper()
    if t in EQUIPMENT:
        return "semiconductors.equipment"
    if t in FOUNDRY:
        return "semiconductors.foundry"
    if t in MEMORY:
        return "semiconductors.memory"
    if t in FABLESS:
        return "semiconductors.fabless"
    return None  # UNCLASSIFIED


def all_profiles() -> dict[str, SectorProfile]:
    """Retourne tous les profils déclarés. Utile pour tests / audits."""
    return dict(load_profiles().profiles)
