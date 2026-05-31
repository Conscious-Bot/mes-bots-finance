"""Quarantaine cohorte v0 (batch 12/05 horizon=30 hardcode, target 10/06).

Audit ground-truth 31/05 a revele : 40 predictions creees le 12/05/2026
07:09:33-07:09:40 ont target_date=2026-06-10 et horizon_days=30 hardcode --
methodo pre-V2 scorer canonique + pre-horizon-diversification par signal_type
(shippe arc 30/05). Cohorte methodo-contaminee : si non-exclue, polluera la
calibration map credible apres resolution batch 10/06.

Tag explicite methodology_version='v0' permet aux consumers de calibration
de filter ces 40 lignes. Defaut 'v1' pour le reste (V2 scorer + horizon
diversifie). Toute prediction future = v1 par defaut (a faire evoluer v2,
v3, etc. quand la methodo change a nouveau).

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-31
"""

from alembic import op


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    # Ajout colonne methodology_version, defaut v1 (= V2-scorer + horizon-divers).
    op.execute(
        "ALTER TABLE predictions ADD COLUMN methodology_version TEXT NOT NULL DEFAULT 'v1'"
    )
    # Tag explicit la cohorte v0 (40 predictions creees 12/05 07:09:33-40).
    # Critere robuste : window created_at + target_date + horizon, triple-check
    # pour eviter de tagger une prediction recente qui se serait glissee.
    op.execute(
        """
        UPDATE predictions
        SET methodology_version = 'v0'
        WHERE created_at BETWEEN '2026-05-12 07:09:00' AND '2026-05-12 07:10:00'
          AND target_date = '2026-06-10'
          AND horizon_days = 30
        """
    )


def downgrade():
    # SQLite 3.35+ supporte DROP COLUMN (verifie : 3.50.4 en prod 31/05).
    op.execute("ALTER TABLE predictions DROP COLUMN methodology_version")
