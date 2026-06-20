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
    # ============================================================
    # Decouvertes 20/06/2026 (audit session) : patterns FP recurrents.
    # ============================================================
    # LIVING_GRAPH canonical seeds : helper qui register_concept comme
    # source canonique d'un concept, intentionnel (fork detection L29).
    # Cas verifies : book.value_eur, ledger_pmp.compute_pmp_realized,
    # portfolio_analytics._pnl_cost_map (republie byte-identique). Le
    # check_l7 lens widened le contexte +15 lignes + markers intentional_re.
    DoctrineRule(
        name="living_graph_canonical_seed",
        pattern=r"LIVING[ _]GRAPH|source canonique|tracer.bullet|fork[ _-]detection",
        reason="LIVING_GRAPH canonical seed / fork detection : register_concept "
               "intentionnel comme source unique d'un concept (book.value_eur, "
               "ledger_pmp.pmp_eur, etc.). L29 mecanisme, pas violation L7.",
    ),
    # ADR 014 Archive-report rule : queries qui INTENTIONNELLEMENT filtrent
    # 'methodology_version = v0/v1' pour panneaux archive (Methode Brier
    # rolling display, recalib_map fit sur archive abondante). Le commentaire
    # 'NE filtre PAS via canonical' ou 'Archive-report rule' marque l'intent.
    DoctrineRule(
        name="adr014_archive_report_intentional",
        pattern=r"Archive.report rule|NE filtre PAS|archive-v[01] explicite",
        reason="ADR 014 §Archive-report rule : panneaux archive explicit (Brier "
               "v1 Methode, recalib_map sur archive abondante) NE doivent PAS "
               "filtrer canonical_predictions_filter. Intentionnel par doctrine.",
    ),
    # Storage layer accessors : by-id lookups individuels (SELECT * FROM
    # predictions WHERE id=?) ne sont pas des aggregations KPI. Filter
    # canonical inutile (le filter est appliquee au consumer s'il aggreque).
    DoctrineRule(
        name="storage_accessor_by_id",
        pattern=r"FROM predictions WHERE id\s*=\s*\?|FROM predictions p WHERE p\.id",
        reason="Storage accessor by-id : SELECT individuel par id, pas une "
               "aggregation KPI. canonical_predictions_filter inutile car le "
               "consumer applique le filter en aval s'il aggreque les results.",
    ),
    # Top-level consumer functions (render, main, orchestrateurs) : ne sont
    # pas des helpers stateless. register_concept legitime au CONSUMER per
    # memory feedback_helper_register_no_side_effect.
    DoctrineRule(
        name="consumer_orchestrator_register",
        pattern=r"compute.once.project|point unique|battement unique",
        reason="Consumer orchestrator (render()/main()) : register_concept "
               "legitime au point de consommation production, pas dans helper "
               "stateless. Per memory feedback_helper_register_no_side_effect.",
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
