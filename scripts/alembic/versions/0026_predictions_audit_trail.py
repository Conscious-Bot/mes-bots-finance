"""#70 + #74 Audit trail full per prediction : scoring_trace + source_metadata.

Capture la chaine de provenance complete par prediction :
- scoring_trace_json : la sortie du scorer V2 (base_rate, evidence_strength,
  evidence_summary, anti_anchoring_reason, probability, direction, reasoning,
  version). Sans trace, impossible de defendre "pourquoi 0.73 ?" en audit.
- source_metadata_json : gmail_id, source_name, credibility_at_creation,
  title du signal. Permet de retracer la provenance externe meme si
  signals table evolue.

Append-only par construction (predictions n'a pas de UPDATE en prod) -- pas
de trigger necessaire ici.

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "predictions",
        sa.Column("scoring_trace_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "predictions",
        sa.Column("source_metadata_json", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("predictions", "source_metadata_json")
    op.drop_column("predictions", "scoring_trace_json")
