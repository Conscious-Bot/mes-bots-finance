"""chat_messages — persist all chat conversations (dashboard + Telegram).

Why : le user veut que TOUS les echanges au copilot soient consignes,
sauvegardes, et reutilises pour le futur (synthese user_profile, retrieval
contextuel, audit). Append-only.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("surface", sa.Text(), nullable=False),  # 'dashboard' | 'telegram'
        sa.Column("role", sa.Text(), nullable=False),  # 'user' | 'assistant'
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("idx_chat_session", "chat_messages", ["session_id"])
    op.create_index("idx_chat_created", "chat_messages", ["created_at"])


def downgrade():
    op.drop_index("idx_chat_created", "chat_messages")
    op.drop_index("idx_chat_session", "chat_messages")
    op.drop_table("chat_messages")
