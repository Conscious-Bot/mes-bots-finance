"""Cure P2 audit (3) reste whitelist 12/06/2026 — TICKER_SECTOR + SECTOR_ALIAS
+ _clean_sector dans la bonne couche (shared/, pas dashboard/).

Mapping ticker → sector affiché. Pure data, pas de rendu HTML/CSS. Sa place
est ici, pas dans dashboard/render.py où il vivait jusqu'à présent.

Anti-pattern reconnu : `intelligence/decision_copilot.py:426` et
`intelligence/portfolio_grade.py:184` importaient `from dashboard.render import
TICKER_SECTOR` (couplage intelligence/ → dashboard/, ratchet legacy). Le
déplacement ici tue le couplage et permet de retirer 2 entrées du whitelist
`_INTELLIGENCE_LEGACY_WHITELIST` (cf tests/test_no_shared_dashboard_import.py).

Source canonique des PROFILS sectoriels (cyclicality, criticality, KPIs, etc.)
= `config/sector_profiles.yaml` (SPEC_SECTOR_TAXONOMY, task #98 livré). Ce
module-ci ne fait QUE le mapping ticker → label sector pour usage UI/scoring.
La taxonomie riche vit dans le YAML, l'étiquette simple vit ici.

Migration future possible : ce dict pourrait être remplacé par un YAML
`config/ticker_to_sector.yaml` (versionnable hors code). Pour l'instant on
garde Python dict (9 entrées seulement, scope minimal de la cure).
"""
from __future__ import annotations

import re


def clean_sector(sid: str | None) -> str:
    """Formatte un sector_id (snake_case avec année éventuelle) en label affichable.

    Exemples : 'ai_compute_2026' → 'AI Compute', 'mag7' → 'MAG 7', None → 'Sans thesis'.

    Pure logique de format. Vivait dans dashboard/render.py:3801 mais n'a rien
    à faire dans la couche présentation — c'est de la taxonomie sector pure,
    consommée par _cluster_health, _concentration, etc.
    """
    if not sid:
        return "Sans thesis"
    s = re.sub(r"_20\d\d$", "", sid).replace("_", " ").title()
    return (
        s.replace(" Ai", " AI")
        .replace("Ai ", "AI ")
        .replace("Hpq", "HPQ")
        .replace("Eu ", "EU ")
        .replace("Mag7", "MAG 7")
    )


# Alias historique (legacy callers utilisent l'underscore).
_clean_sector = clean_sector


# Mapping ticker → label sector affiché (pour positions UI + scoring sectoriel).
# Note : portfolio_grade.py:_ticker_sector teste d'abord la cluster membership
# via config.yaml § concentration.clusters, et fallback sur ce dict.
TICKER_SECTOR: dict[str, str] = {
    "AMZN": "MAG 7",
    "ENTG": "AI Compute",
    "MP": "Matériaux rares",
    "MU": "AI Compute",
    "6857.T": "AI Compute",
    "VRT": "Data Center",
    "CCJ": "Énergie",
    "LNG": "Énergie",
    "TSLA": "Robotique",
}

# Alias d'affichage : canonical → display.
SECTOR_ALIAS: dict[str, str] = {
    "EU Defense": "Defense",
}
