"""positions.wrapper — Sprint 16 : PEA / CTO / autre wrapper fiscal.

Per la critique : "Placement PEA vs CTO : flagger un nom eligible PEA loge
inutilement au CTO. Recolte de moins-values : Vertiv est dans le rouge ->
moins-value mobilisable au CTO."

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("positions", sa.Column("wrapper", sa.Text(), nullable=True, server_default="CTO"))


def downgrade():
    op.drop_column("positions", "wrapper")
