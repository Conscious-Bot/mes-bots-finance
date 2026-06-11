"""Cure P0-2 audit (3) 12/06/2026 — triggers append-only per-classe.

Source unique : shared/append_only_registry.py (APPEND_ONLY_TABLES).
Enforcement : tests/test_append_only_enforced.py (méta-test scan triggers vs registre).

Classification per-table (verify-before-assert sur chaque par grep `UPDATE table_name`) :

IMMUTABLE (strict write-once, no_delete + no_update) :
- prediction_integrity_log    : tamper-evident chain. Manquant = mensonge central.
- thesis_erosion_log          : tamper-evident chain. Idem.
- prediction_audit_log        : audit log pure observation.
- thesis_erosion_classifications : audit log pure observation.
- position_events             : event sourcing. Toute correction = nouvelle event.

NO_DELETE (rétention mutable, no_delete uniquement) :
- signals      : UPDATÉ légitimement (scoring_status, materiality, feedback learning)
- bias_events  : UPDATÉ légitimement (résolution lock-in, backfill obs +60/+90j arch B3)

🔴 Cure rejette le blanket no_update du brief initial audit (3) — il aurait cassé
prod sur signals.scoring_status (storage.py × 5 sites, materiality_v2.py × 3,
learning.py:27) ET bias_events (résolution + backfill arch B3). Catch Olivier
30 secondes de grep → mensonge silencieux évité.

Tables intégrité (prediction_integrity_log, thesis_erosion_log) en PREMIER dans
la séquence CREATE : si la migration crash au milieu pour une raison, au moins
la promesse tamper-evident centrale du système est restaurée.

Downgrade : DROP TRIGGER tous les 7. Aucune perte de données (les triggers
n'écrivent rien, ils RAISE seulement).
"""
from __future__ import annotations

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


# IF NOT EXISTS idempotent : SQLite ne supporte pas DDL transactionnel, donc si
# la migration crash au milieu, les triggers déjà créés persistent. Le re-run
# doit pouvoir les retrouver sans casser. Aucun risque de divergence parce que
# le message RAISE est byte-identique entre l'ancien et le nouveau (cure unique).
_NO_DELETE_TEMPLATE = """
CREATE TRIGGER IF NOT EXISTS {table}_no_delete
BEFORE DELETE ON {table}
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, '{table} is append-only (cure P0-2 audit (3) 2026-06-12 / registre shared/append_only_registry.py). DELETE interdit. Pour corriger : INSERT une ligne audit séparée.');
END
"""

_NO_UPDATE_TEMPLATE = """
CREATE TRIGGER IF NOT EXISTS {table}_no_update
BEFORE UPDATE ON {table}
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, '{table} is strict write-once / immutable (cure P0-2 audit (3) 2026-06-12 / registre shared/append_only_registry.py). UPDATE interdit. Pour corriger : INSERT une nouvelle ligne (event sourcing) ou nouvelle observation (audit log).');
END
"""


# Source unique en MIGRATION (hardcodée, pas import shared/) :
# Alembic migrations ne doivent PAS dépendre du code applicatif (les migrations
# doivent rester applicables même si le code change). On duplique le registre
# ici avec un comment explicite cf shared/append_only_registry.py.
_IMMUTABLE_TABLES = (
    # Tables intégrité d'abord — promesse tamper-evident centrale du système.
    "prediction_integrity_log",
    "thesis_erosion_log",
    # Puis audit logs et event sourcing.
    "prediction_audit_log",
    "thesis_erosion_classifications",
    "position_events",
)

_NO_DELETE_ONLY_TABLES = (
    "signals",
    "bias_events",
)


def upgrade() -> None:
    # 1. Tables intégrité d'abord (immutable strict)
    for table in _IMMUTABLE_TABLES:
        op.execute(_NO_DELETE_TEMPLATE.format(table=table))
        op.execute(_NO_UPDATE_TEMPLATE.format(table=table))
    # 2. Tables no_delete-mutable (no_update INTERDIT — casserait scoring/résolution)
    for table in _NO_DELETE_ONLY_TABLES:
        op.execute(_NO_DELETE_TEMPLATE.format(table=table))


def downgrade() -> None:
    # Aucune perte de données (les triggers n'écrivent rien, ils RAISE).
    for table in _IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
    for table in _NO_DELETE_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
