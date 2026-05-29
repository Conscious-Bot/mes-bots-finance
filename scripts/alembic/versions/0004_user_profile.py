"""user_profile — auto-derived self-portrait of the investor

Layer 0 of the personality stack. Refresh hebdo (Opus). Append-only history.
Each row = one snapshot of how the bot sees the user, at a given moment.

Used by :
- decision_copilot.assemble_context (calibrates pressure-test to user's patterns)
- chat surface (knows the user's language, biases, edge)
- portfolio_grade (some rules use user's track record on similar sectors)

Quality bar : every trait must cite specific evidence_ids (decisions, predictions,
theses). No generic personality blurbs. confidence_score reflects sample size :
restraint at start (low n), sharp at maturity (high n).

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_profile",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("refreshed_at", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        # The profile itself — structured JSON, see schema in intelligence/user_profile.py
        sa.Column("profile_json", sa.Text(), nullable=False),
        # Confidence in the profile (function of sample sizes)
        sa.Column("confidence_score", sa.Integer(), nullable=True),  # 0-100
        # Source counts at time of synthesis — auditable
        sa.Column("n_decisions_used", sa.Integer(), nullable=True),
        sa.Column("n_theses_used", sa.Integer(), nullable=True),
        sa.Column("n_predictions_resolved_used", sa.Integer(), nullable=True),
        sa.Column("n_signals_window", sa.Integer(), nullable=True),
        # Time window analyzed
        sa.Column("data_window_start", sa.Text(), nullable=True),
        sa.Column("data_window_end", sa.Text(), nullable=True),
        # LLM telemetry
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("idx_user_profile_refreshed", "user_profile", ["refreshed_at"])


def downgrade():
    op.drop_index("idx_user_profile_refreshed", "user_profile")
    op.drop_table("user_profile")
