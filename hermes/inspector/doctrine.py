"""Doctrine-aware exclusions pour eviter les faux positifs.

Le moteur de detection 'mort' est statistique/syntaxique. Il flague des
patterns qui PEUVENT etre intentionnels :
- Code en grace-period de depreciation (CONVENTIONS §15, garder 1 mois min)
- Versions archive (v0/v1) intentionnellement conservees (CONVENTIONS §13)
- Shadow variants en eval (KNOWN-GAP)
- Tickers / handlers dormants-par-design

Cette table est consultee AVANT de promouvoir un candidat en 'DEAD haute
confiance'. Si match -> degrade en 'WATCH' avec citation de la regle.

Source de verite : docs/CONVENTIONS.md + CLAUDE.md memory.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class DoctrineRule:
    name: str
    pattern: str        # regex ou substring qui matche le candidat
    reason: str         # citation textuelle de la regle
    grace_until: date | None = None  # date apres laquelle la rule expire


# ============================================================
# Exclusions canoniques (sourcees docs + memory durables)
# ============================================================

EXCLUSIONS: tuple[DoctrineRule, ...] = (
    # CONVENTIONS §13 versioning : archives v0/v1 gardes pour comparaison
    DoctrineRule(
        name="archive_v0_v1",
        pattern=r"methodology_version.*v[01]|_v0\b|_v1\b",
        reason="CONVENTIONS §13 : v0/v1 archives intentionnellement conservees "
               "pour comparaison cohort. Ne pas supprimer.",
    ),
    # CONVENTIONS §15 grace-period depreciation : 1 mois min
    DoctrineRule(
        name="grace_period_recent_deprecation",
        pattern=r"DEPRECATED|deprecated|# TODO.*remove",
        reason="CONVENTIONS §15 grace-period : 1 mois min apres marker "
               "DEPRECATED avant suppression effective.",
    ),
    # KNOWN-GAP : dette technique CONNUE et acceptee
    DoctrineRule(
        name="known_gap_accepted",
        pattern=r"# KNOWN-GAP:",
        reason="KNOWN-GAP marker = dette consciente acceptee. Pas de "
               "suppression sans review explicite du marker.",
    ),
    # Tests : `_unused` prefix volontaire (ruff RUF059 convention)
    DoctrineRule(
        name="underscore_dummy",
        pattern=r"^_[a-z]",
        reason="Variable prefix _ = dummy/unused convention (ruff RUF059). "
               "Volontaire.",
    ),
    # Shadow scorer v2 vs v1 (KPI #2 et ADR 014)
    DoctrineRule(
        name="shadow_scorer_eval",
        pattern=r"shadow|signal_scorer_v[12]",
        reason="Shadow scoring intentionnel pendant migration ADR 014. Ne "
               "pas supprimer tant que v2 < 5 resolved 28d.",
    ),
)


def is_excluded(candidate_name: str, candidate_text: str = "") -> tuple[bool, str | None]:
    """Verifie si le candidat match une exclusion doctrine.

    Args:
        candidate_name: nom du symbole/fichier candidate
        candidate_text: texte alentour (commentaires, def, etc.)

    Returns:
        (is_excluded, reason_or_none).
    """
    import re
    today = date.today()
    combined = f"{candidate_name}\n{candidate_text}"
    for rule in EXCLUSIONS:
        if rule.grace_until and today > rule.grace_until:
            continue  # grace period expired, no longer exempt
        if re.search(rule.pattern, combined):
            return True, f"{rule.name} :: {rule.reason}"
    return False, None


def grace_period_days_remaining(deprecation_date: date) -> int:
    """CONVENTIONS §15 : combien de jours reste-t-il avant la fin de la grace
    period de depreciation (1 mois standard)."""
    end = deprecation_date + timedelta(days=30)
    return max(0, (end - date.today()).days)
