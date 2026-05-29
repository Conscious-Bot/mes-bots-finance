"""chat_extracted_signals — signaux soft extraits passivement des conversations.

Chaque message chat est passe au crible (Haiku tier=extract, cheap) pour
detecter : concern, conviction_drift, topic_interest, sentiment, heuristic.
Ce ne sont PAS des decisions formelles — c'est le murmure que le user
laisse echapper en conversation, et qu'on veut digester dans le profil.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_extracted_signals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("chat_message_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),  # concern | conviction_drift | topic_interest | sentiment | heuristic | conviction_endorsement
        sa.Column("ticker", sa.Text(), nullable=True),
        sa.Column("sector", sa.Text(), nullable=True),
        sa.Column("theme", sa.Text(), nullable=True),
        sa.Column("valence", sa.Float(), nullable=True),  # -1 (negatif/doute) to +1 (positif/conviction)
        sa.Column("confidence", sa.Float(), nullable=True),  # extraction confidence 0-1
        sa.Column("evidence_quote", sa.Text(), nullable=True),  # citation exacte du message
        sa.Column("note", sa.Text(), nullable=True),  # interpretation 1 phrase
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
    )
    op.create_index("idx_ces_ticker", "chat_extracted_signals", ["ticker"])
    op.create_index("idx_ces_kind", "chat_extracted_signals", ["kind"])
    op.create_index("idx_ces_created", "chat_extracted_signals", ["created_at"])


def downgrade():
    op.drop_index("idx_ces_created", "chat_extracted_signals")
    op.drop_index("idx_ces_kind", "chat_extracted_signals")
    op.drop_index("idx_ces_ticker", "chat_extracted_signals")
    op.drop_table("chat_extracted_signals")
