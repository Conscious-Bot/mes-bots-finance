"""Cure audit 12/06/2026 (2) — protège predictions + 6 journaux append-only.

Audit 2026-06-12 P1.1/P1.2 : la table `predictions` (track-record Brier) n'avait
AUCUN trigger, et 6 journaux de monitors (L4) / live-state cron (L17) non plus.
Source registre : shared/append_only_registry.py (gardé en sync par le méta-test
test_append_only_enforced).

`predictions` — régime propre (comme thesis_predictions / transactions) :
  - no_delete : le track-record probabiliste ne se supprime pas.
  - resolve_writeonce : resolved_at/final_price/return_pct/outcome/credibility_delta
    /brier_score write-once à la résolution (NULL→valeur OK, RÉ-écriture RAISE).
    storage.py:1113 résout en UN seul UPDATE atomique → compatible (même contrat
    que thesis_predictions §2.2 : un writer qui splitterait en 2 UPDATE post
    resolved_at se ferait mordre, c'est voulu).
  HORS APPEND_ONLY_TABLES : le méta-test test 2 flaggerait le BEFORE UPDATE comme
  incompatible avec la classe 'no_delete'. predictions a un régime write-once-
  per-column plus fin, documenté dans le registre § DÉJÀ PROTÉGÉES.

6 journaux `immutable` (pur observation, grep-confirmé 12/06 zéro UPDATE/DELETE
app dans tout le repo) : over_cap_alerts, kill_criteria_alerts, stress_gate_alerts,
macro_regime_alerts, stale_target_alerts, risk_signal_evaluations. Inscrites au
registre → le méta-test les couvre automatiquement (no_delete + no_update).

IF NOT EXISTS idempotent (SQLite : pas de DDL transactionnel, un crash au milieu
laisse les triggers déjà créés ; le re-run doit les retrouver sans casser).
Downgrade : DROP. Aucune perte de données (les triggers RAISE, n'écrivent rien).

Revision ID: 0058
Revises: 0057
"""
from __future__ import annotations

from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


_NO_DELETE_TEMPLATE = """
CREATE TRIGGER IF NOT EXISTS {table}_no_delete
BEFORE DELETE ON {table}
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, '{table} is append-only (cure audit 2026-06-12 / registre shared/append_only_registry.py). DELETE interdit. Pour corriger : INSERT une ligne audit séparée.');
END
"""

_NO_UPDATE_TEMPLATE = """
CREATE TRIGGER IF NOT EXISTS {table}_no_update
BEFORE UPDATE ON {table}
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, '{table} is strict write-once / immutable (cure audit 2026-06-12 / registre shared/append_only_registry.py). UPDATE interdit. Pour corriger : INSERT une nouvelle observation.');
END
"""

# Hardcodé en migration (pas d'import shared/ : les migrations restent applicables
# même si le code app change). Source de vérité = shared/append_only_registry.py,
# tenue en sync par le méta-test test_append_only_enforced.
_IMMUTABLE_TABLES = (
    "over_cap_alerts",
    "kill_criteria_alerts",
    "stress_gate_alerts",
    "macro_regime_alerts",
    "stale_target_alerts",
    "risk_signal_evaluations",
)


def upgrade() -> None:
    # 1. predictions — régime propre write-once à la résolution (tamper-evidence
    #    de la table de track-record Brier elle-même).
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS predictions_no_delete
        BEFORE DELETE ON predictions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'predictions append-only : DELETE interdit. Le track-record Brier exige l''immutabilité historique (audit 2026-06-12 P1.1).');
        END
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS predictions_resolve_writeonce
        BEFORE UPDATE OF
            resolved_at, final_price, return_pct, outcome,
            credibility_delta, brier_score
        ON predictions
        FOR EACH ROW
        WHEN OLD.resolved_at IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'predictions resolve columns are write-once : déjà résolu, pas de réécriture du Brier/outcome (audit 2026-06-12 P1.1). Pour corriger : INSERT une ligne audit séparée.');
        END
    """)

    # 2. 6 journaux immutable (no_delete + no_update strict)
    for table in _IMMUTABLE_TABLES:
        op.execute(_NO_DELETE_TEMPLATE.format(table=table))
        op.execute(_NO_UPDATE_TEMPLATE.format(table=table))


def downgrade() -> None:
    for table in _IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
    op.execute("DROP TRIGGER IF EXISTS predictions_resolve_writeonce")
    op.execute("DROP TRIGGER IF EXISTS predictions_no_delete")
