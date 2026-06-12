"""Cure P2 audit (3) reste whitelist (12/06/2026) — degraded restitution
contract déplacé vers shared/llm_restitution.py.

Ce module est désormais un alias rétro-compat. Tous les callers (internes
au dashboard ou en intelligence/analyze.py) peuvent continuer à importer
`from dashboard.restitution import ...` mais le code réel vit dans
shared/llm_restitution.py (couche substrat, pas présentation).

Nouveaux callers : importer DIRECTEMENT depuis `shared.llm_restitution`.
Ce fichier sera supprimé quand tous les call-sites legacy auront migré.
"""
from shared.llm_restitution import (
    LLM_UNAVAILABLE_MARKER_PREFIX,
    format_llm_unavailable_marker,
    format_rule_fallback_provenance,
    is_synthesized_marker,
)

__all__ = [
    "LLM_UNAVAILABLE_MARKER_PREFIX",
    "format_llm_unavailable_marker",
    "format_rule_fallback_provenance",
    "is_synthesized_marker",
]
