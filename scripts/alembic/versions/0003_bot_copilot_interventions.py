"""bot_copilot_interventions — capture every adversarial co-pilot pre-trade brief

Each /position_buy, /position_sell, /override triggers a co-pilot call.
The full LLM response + intent + resolution outcome (filled at J+30) is logged
here. This is the substrate for :
- Future preference layer (which biases the bot consistently flags)
- Calibration metrics (does the bot's verdict correlate with actual outcomes ?)
- Chat surface RAG (what did the bot say about this ticker recently ?)

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bot_copilot_interventions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # Intent (what the user is about to do, captured pre-trade)
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("decision_type", sa.Text(), nullable=False),
        sa.Column("intent_reasoning", sa.Text(), nullable=True),
        sa.Column("intent_price", sa.Float(), nullable=True),
        sa.Column("intent_qty", sa.Float(), nullable=True),
        sa.Column("thesis_id", sa.Integer(), nullable=True),
        # Back-link to actual decision row (filled post-trade execution)
        sa.Column("decision_id", sa.Integer(), nullable=True),
        # Co-pilot response (machine-readable header)
        sa.Column("verdict", sa.Text(), nullable=True),  # PROCEED | PRESSURE | STRONG_OPPOSE
        sa.Column("pressure_score", sa.Integer(), nullable=True),
        sa.Column("ancrage", sa.Text(), nullable=True),
        sa.Column("brief", sa.Text(), nullable=True),
        sa.Column("biases_active_json", sa.Text(), nullable=True),
        sa.Column("full_response_json", sa.Text(), nullable=True),
        # LLM telemetry
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        # Resolution layer (filled at J+30 by a future resolve job)
        sa.Column("resolved_30d_at", sa.Text(), nullable=True),
        sa.Column("return_30d_pct", sa.Float(), nullable=True),
        sa.Column("outcome_label", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["thesis_id"], ["theses.id"]),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"]),
    )
    op.create_index("idx_copilot_ticker", "bot_copilot_interventions", ["ticker"])
    op.create_index("idx_copilot_decision", "bot_copilot_interventions", ["decision_id"])
    op.create_index("idx_copilot_created", "bot_copilot_interventions", ["created_at"])
    op.create_index("idx_copilot_unresolved", "bot_copilot_interventions", ["resolved_30d_at"])


def downgrade():
    op.drop_index("idx_copilot_unresolved", "bot_copilot_interventions")
    op.drop_index("idx_copilot_created", "bot_copilot_interventions")
    op.drop_index("idx_copilot_decision", "bot_copilot_interventions")
    op.drop_index("idx_copilot_ticker", "bot_copilot_interventions")
    op.drop_table("bot_copilot_interventions")
