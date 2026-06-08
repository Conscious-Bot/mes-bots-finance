"""SOCLE substrat sémantique : vocabulaire d'alerte canonique.

Cf SPEC_ALERT_VOCABULARY.md. L'équivalent sémantique du Datum : un registre
declaratif de "mots d'alerte" canoniques dont TOUS les panels composent --
au lieu d'inventer leur propre langue.

L'invariant central : 4 classes orthogonales, et la règle d'attention encode
la doctrine d'alarme dans la STRUCTURE du vocabulaire :

    L'attention provient UNIQUEMENT de {EVENT} ∪ {FLAG actif} ∪ {STEER act-class}.
    Un STATE n'attire JAMAIS l'attention -- gravé dans le validator Pydantic.

Les états DÉCRIVENT (calme, defaut) ; les deltas/conditions/conclusions ALARMENT
(gagné). C'est la doctrine delta-pas-état, structurelle, pas une discipline
répétée par panel.

Usage :
    from shared.alert_vocabulary import get_word, render_token, attention_earning

    word = get_word("EROSION_DETECTED")
    if attention_earning(word):  # True (EVENT)
        rt = render_token(word)
        # rt.color = "warning", rt.icon = "trending-down", rt.weight = "high"
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_VOCAB_PATH = _REPO_ROOT / "config" / "alert_vocabulary.yaml"


# === Sub-models ============================================================


class CalibrationContract(BaseModel):
    """Contrat de calibration d'un EVENT : comment il gagne le droit de tirer.

    Frozen : un EVENT déclaré ne peut pas voir son contrat muté en runtime.
    """

    model_config = {"extra": "forbid", "frozen": True}

    trigger: str = Field(min_length=1, description="Condition logique qui tire l'event")
    delta_based: bool = Field(description="EVENT = delta toujours True. Verrouille par validator.")
    outcome_validated: str = Field(min_length=1, description="Comment l'event prouve sa pertinence (Brier, PR-AUC, etc.)")
    min_n_for_threshold: int = Field(default=10, ge=1, description="N min pour ajuster le seuil au mérite")

    @field_validator("delta_based")
    @classmethod
    def _delta_must_be_true_for_events(cls, v: bool) -> bool:
        if not v:
            raise ValueError("EVENT calibration_contract.delta_based MUST be True (cf doctrine delta-pas-etat)")
        return v


class RenderSpec(BaseModel):
    """Visuel canonique d'un mot. Hérité par TOUS les panels qui le rendent.

    Tokens sémantiques (pas de hex literal) : color est dans
    {neutral, info, warning, danger, critical, calm}. Le mapping token -> hex/CSS
    vit dans le thème, pas ici.
    """

    model_config = {"extra": "forbid", "frozen": True}

    color: Literal["calm", "neutral", "info", "warning", "danger", "critical"]
    icon: str = Field(min_length=1)
    weight: Literal["low", "medium", "high"]


# === AlertWord (discriminated union sur class) ==============================


class _BaseWord(BaseModel):
    """Champs communs. Ne pas instancier directement -- utiliser StateWord/SteerWord/etc."""

    model_config = {"extra": "forbid", "frozen": True}

    earns_attention: bool
    meaning: str = Field(min_length=1)
    render: RenderSpec
    action_hint: str = ""  # vide OK pour STATE
    calibration_contract: CalibrationContract | None = None


class StateWord(_BaseWord):
    """STATE : décrit OÙ une chose est. earns_attention=False TOUJOURS (validator)."""

    @field_validator("earns_attention")
    @classmethod
    def _state_never_attention(cls, v: bool) -> bool:
        # CRITIQUE doctrine : un STATE n'attire JAMAIS l'attention.
        # Gravé dans la structure du vocabulaire, pas dans la discipline.
        if v is True:
            raise ValueError(
                "STATE.earns_attention MUST be False (cf doctrine : STATE n'attire jamais l'oeil)."
            )
        return v


class SteerWord(_BaseWord):
    """STEER : conclusion sur quoi faire. act-class earns_attention=True, calm-class False.

    On ne valide pas earns_attention contre une enum d'act/calm names :
    l'auteur du yaml l'indique selon l'intention sémantique.
    """


class FlagWord(_BaseWord):
    """FLAG : condition qui contraint la lecture. earns_attention=True quand actif."""


class EventWord(_BaseWord):
    """EVENT : delta. earns_attention=True TOUJOURS + calibration_contract OBLIGATOIRE.

    Un EVENT sans contrat = un delta non-calibré = du bruit, refusé.
    """

    @model_validator(mode="after")
    def _event_requires_contract_and_attention(self) -> EventWord:
        if self.calibration_contract is None:
            raise ValueError(
                f"EVENT requires calibration_contract (cf doctrine : un delta non-calibre n'est pas un mot, c'est du bruit). "
                f"Meaning='{self.meaning[:60]}'"
            )
        if self.earns_attention is False:
            raise ValueError(
                f"EVENT must have earns_attention=True (alarme legitime par nature). "
                f"Meaning='{self.meaning[:60]}'"
            )
        return self


AlertWord = StateWord | SteerWord | FlagWord | EventWord


# === Registry ===============================================================


class VocabularyRegistry(BaseModel):
    """Le registre complet, parse depuis config/alert_vocabulary.yaml.

    Frozen + extra='forbid' : anti-tampering downstream.
    """

    model_config = {"extra": "forbid", "frozen": True}

    vocabulary_version: str
    schema_version: str
    words: dict[str, AlertWord]


def _build_word(name: str, raw: dict) -> AlertWord:
    """Construit le bon sous-type d'AlertWord depuis le dict yaml.

    On extrait `class` (mot Python reserve) et dispatch manuellement vers
    le bon sous-type Pydantic -- pas besoin de discriminator interne.
    """
    cls = raw.get("class")
    if cls not in ("state", "steer", "flag", "event"):
        raise ValueError(f"Word '{name}' has invalid class={cls!r} (must be state/steer/flag/event)")
    payload = {k: v for k, v in raw.items() if k != "class"}
    cls_map = {"state": StateWord, "steer": SteerWord, "flag": FlagWord, "event": EventWord}
    return cls_map[cls].model_validate(payload)


@lru_cache(maxsize=1)
def load_vocabulary(path: str | None = None) -> VocabularyRegistry:
    """Charge le registre depuis YAML, valide via Pydantic.

    LRU-cache : un seul appel par process. Si vraiment besoin de reload
    (tests qui mutent fichier), appeler load_vocabulary.cache_clear() avant.
    """
    p = Path(path) if path else _VOCAB_PATH
    if not p.exists():
        raise FileNotFoundError(f"alert_vocabulary.yaml introuvable a {p}")
    with p.open() as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"alert_vocabulary.yaml malforme : root doit etre dict, got {type(raw)}")
    vocab_version = raw.pop("vocabulary_version", None) or "unknown"
    schema_version = raw.pop("schema_version", None) or "unknown"
    words: dict[str, AlertWord] = {}
    for name, body in raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"Word '{name}' body must be dict, got {type(body)}")
        try:
            words[name] = _build_word(name, body)
        except Exception as e:
            raise ValueError(f"Word '{name}' validation failed : {e}") from e
    return VocabularyRegistry(
        vocabulary_version=vocab_version,
        schema_version=schema_version,
        words=words,
    )


# === Public API =============================================================


def get_word(name: str) -> AlertWord:
    """Retourne le AlertWord canonique. Raise KeyError si non-declare.

    Aucun panel ne doit avoir un mot d'alerte hors registre. Si name absent
    -> ValueError loud (le mot doit etre declare delibérément, comme une
    entree GLOSSARY).
    """
    reg = load_vocabulary()
    if name not in reg.words:
        raise KeyError(
            f"Mot inconnu '{name}'. Ajouter au registre config/alert_vocabulary.yaml "
            "(acte délibéré, pas improvisation panel)."
        )
    return reg.words[name]


def attention_earning(word: AlertWord) -> bool:
    """La règle structurelle : l'oeil n'accroche que sur les act-class.

    Equivalent : word.earns_attention -- mais on l'exprime via cette fonction
    pour rendre la règle EXPLICITE dans les sites consommateurs (lit la regle,
    pas un champ).
    """
    return word.earns_attention


def render_token(word: AlertWord) -> RenderSpec:
    """Retourne le render canonique. Tous les panels appellent ceci pour le visuel.

    Le panel ne décide JAMAIS la couleur/icone -- il consomme le token canonique.
    C'est ce qui garantit qu'EROSION_DETECTED s'affiche pareil partout.
    """
    return word.render


def attention_earning_ratio(panel_words: list[str]) -> float:
    """Compteur : ratio des mots attention-earning actifs / total dans un panel.

    Sert le test global "crying-wolf detector" : >20% sur un panel donné
    = défaut calme cassé, build rouge (cf SPEC §4 + PLAN_REFONTE_ALERTES).

    Args:
        panel_words : liste des mots ACTIFS rendus par le panel à l'instant t.

    Returns:
        ratio float dans [0, 1]. None-empty list assumes valid words (raise sinon).
    """
    if not panel_words:
        return 0.0
    n_attention = sum(1 for w in panel_words if attention_earning(get_word(w)))
    return n_attention / len(panel_words)


def all_words() -> dict[str, AlertWord]:
    """Retourne tous les mots déclarés. Utile pour tests / audits."""
    return dict(load_vocabulary().words)
