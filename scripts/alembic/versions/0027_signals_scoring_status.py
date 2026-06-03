"""#93 Composant A2 -- signals.scoring_status pour marquer pending_llm.

Quand un consumer LLM (signal_scorer_v2, materiality_v2) attrape un
LLMUnavailableError (credit_exhausted ou rate_limited), il marque le
signal `scoring_status='pending_llm'` au lieu de retourner None
silencieusement. Le drain job futur (post-1A) peut re-traiter ces
items quand l'API revient.

Etats canoniques :
- 'pending'   : pas encore scored (defaut a l'insertion)
- 'scored'    : LLM a reussi
- 'pending_llm' : LLM indisponible (credit/quota), a retenter
- 'failed'    : echec non-recuperable (parse, contenu invalide)

Pre-existant : score column INTEGER null pour non-scored. Cette colonne
status ajoute la SEMANTIQUE du non-score : pas-encore vs LLM-indispo vs
echec-definitif. Critique pour respect doctrine "jamais silencieux"
(#93 spec user 03/06).

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "signals",
        sa.Column(
            "scoring_status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
    )
    # Backfill existing rows : si score IS NOT NULL alors 'scored', sinon 'pending'.
    # Sans backfill, les anciens signaux scoreraient comme 'pending' par defaut et
    # se feraient re-scorer par les futurs drain jobs. Backfill = etat coherent.
    op.execute(
        "UPDATE signals SET scoring_status = 'scored' WHERE score IS NOT NULL"
    )
    op.create_index(
        "idx_signals_scoring_status",
        "signals",
        ["scoring_status"],
    )


def downgrade():
    op.drop_index("idx_signals_scoring_status", table_name="signals")
    op.drop_column("signals", "scoring_status")
