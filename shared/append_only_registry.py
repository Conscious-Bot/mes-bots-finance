"""Cure P0-2 audit (3) 12/06/2026 — registre déclaratif des tables append-only.

L'agent audit (3) a posé le diagnostic exact (« classe L25 que test_schema_drift
ne couvre pas »), mais sa cure ne couvrait que l'instance (7 triggers manuels).
La 8e table append-only ajoutée le mois prochain rouvrirait le gap silencieusement.

Cure de CLASSE (Cherny n°1 — feedback loop de vérification) :
- Ce module est la SOURCE UNIQUE de vérité « cette table est append-only et sa
  classe est X ».
- Le meta-test `test_append_only_enforced` énumère ce registre et assert que
  chaque table a le trigger correspondant à sa classe.
- → Doctrine et enforcement ne peuvent plus diverger. Une future table
  append-only sans trigger fera rougir le meta-test au CI.

DEUX SÉMANTIQUES DISTINCTES (red-team Olivier 12/06 sur l'agent audit) :

1. `'immutable'` (strict write-once) :
   Rows jamais modifiées NI supprimées. Triggers requis : no_delete + no_update.
   Candidates : tables d'historique pur (audit logs, observation logs).

2. `'no_delete'` (rétention mutable) :
   Rows jamais supprimées, MAIS mutables (status updates, materiality scoring,
   résolution backfill, etc.). Trigger requis : no_delete uniquement.
   ATTENTION : un trigger no_update sur ces tables casserait la prod en silence.
   Exemple historique : signals.scoring_status (storage.py, materiality_v2.py),
   bias_events.position_event_id (résolution + backfill obs +60/+90j arch B3).

Classification = verify-before-assert : chaque entrée doit avoir été grep-confirmée
(`grep "UPDATE table_name"` source vs trigger souhaité). Drift = bug.

Priorité tables intégrité : leur trigger manquant rend la tamper-evidence FAUSSE.
Une chaîne commit-reveal mutable n'est PAS tamper-evident, elle prétend l'être.
C'est la promesse centrale du système.
"""
from __future__ import annotations

from typing import Literal

AppendOnlyClass = Literal["immutable", "no_delete"]


APPEND_ONLY_TABLES: dict[str, AppendOnlyClass] = {
    # ========================================================================
    # IMMUTABLE — strict write-once, no_delete + no_update
    # ========================================================================
    # Tamper-evident chains : trigger manquant = tamper-evidence FAUSSE.
    # PRIORITÉ ABSOLUE pour cette cure.
    "prediction_integrity_log": "immutable",
    "thesis_erosion_log": "immutable",
    # Audit logs : observation pure, jamais modifiée post-écriture.
    "prediction_audit_log": "immutable",
    "thesis_erosion_classifications": "immutable",
    # Event sourcing : history positions (open/close/trim/add), jamais UPDATE
    # (toute correction = nouvelle event).
    "position_events": "immutable",
    # Journaux de monitors (L4) + live-state cron (L17) : pur observation
    # append-only, chaque évaluation = nouvelle ligne, jamais UPDATE/DELETE
    # (grep-confirmé 12/06 audit (2) : zéro UPDATE/DELETE app sur ces 6).
    # DELETE ré-armerait le compteur de transition → re-fire spurieux, exactement
    # ce que L4 interdit. macro_regime_alerts + risk_signal_evaluations sont les
    # exemples-canon de live-state append-only de LESSONS.md.
    "over_cap_alerts": "immutable",
    "kill_criteria_alerts": "immutable",
    "stress_gate_alerts": "immutable",
    "macro_regime_alerts": "immutable",
    "stale_target_alerts": "immutable",
    "risk_signal_evaluations": "immutable",

    # ========================================================================
    # NO_DELETE — rétention historique mais rows MUTABLES
    # ========================================================================
    # signals : scoring_status évolue (pending_llm → scored → expired),
    # materiality_v2 update score post-scrutin, learning.py update status sur
    # LLMUnavailableError. Trigger no_update CASSERAIT la prod en silence.
    "signals": "no_delete",
    # bias_events : résolution post-pose (lock_in_detector.py:264 hook
    # positions.add_sell), backfill observations +60/+90j (arch B3). Pareil :
    # trigger no_update casserait la résolution lock-in.
    "bias_events": "no_delete",
}


# ========================================================================
# DÉJÀ PROTÉGÉES (pour info / méta-test peut les vérifier en bonus) :
# ========================================================================
# - transactions : trigger transactions_writeonce (migration 0046)
# - thesis_predictions : 3 triggers (pose_writeonce, resolve_writeonce,
#   no_delete) via migrations 0052/0053/0054 — chantier alpha
# - predictions : no_delete + resolve_writeonce (migration 0058, audit 12/06 P1.1).
#   Track-record Brier/outcome write-once à la résolution (storage.py:1113 résout
#   en 1 UPDATE atomique). Le BEFORE UPDATE OF rendrait le méta-test test 2
#   incompatible avec la classe 'no_delete' → régime propre, hors dict.
# Ces tables ne sont PAS dans APPEND_ONLY_TABLES parce qu'elles ont leur
# propre régime (write-once-per-column, plus fin que immutable).
