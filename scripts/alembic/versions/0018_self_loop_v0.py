"""Boucle-de-soi V0 : decision_counterfactual + counterfactual_resolution.

Directive user 29/05 round 3 :
> "Decision -> ancre contrefactuelle -> mesure a 30/90/180j -> biais quantifie
>  -> reinjecte dans le prochain prompt"

V0 minimal :
- horizon J+30 seulement (J+60/90/180 viennent V1)
- contrefactuel = "hold strict" (pas de rotation)
- tables append-only stricte (triggers UPDATE/DELETE)

decision_counterfactual : ancre figee AVANT execution de la decision.
  Capture price + qty + thesis_id au moment T. C'est la "branche jamais
  prise" qu'on va mesurer.

counterfactual_resolution : append-only par horizon. J+30 = 1 ligne.
  Quand V1 ajoutera J+60/90/180, ce sera 3 lignes de plus pour la meme
  decision_id. La trajectoire est preservee.

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    # === decision_counterfactual : ancre figee a T0 ===
    op.create_table(
        "decision_counterfactual",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.Integer(), nullable=False),  # FK decisions.id
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("decision_type", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.Text(), nullable=False,
                  server_default=sa.text("(datetime('now'))")),
        # Contrefactuel : v0 = "hold" seulement
        sa.Column("counterfactual_branch", sa.Text(), nullable=False,
                  server_default=sa.text("'hold'")),
        # Snapshot pre-execution
        sa.Column("anchor_price_native", sa.Float(), nullable=True),
        sa.Column("anchor_price_eur", sa.Float(), nullable=True),
        sa.Column("anchor_qty_before", sa.Float(), nullable=False),  # qty AVANT la decision
        sa.Column("anchor_currency", sa.Text(), nullable=True),
        sa.Column("anchor_thesis_id", sa.Integer(), nullable=True),
        sa.Column("anchor_conviction", sa.Integer(), nullable=True),  # snapshot de la conviction T0
        # Self-attribution (peut etre tagged a posteriori via copilot biases_active_json)
        sa.Column("bias_hypothesis_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("reasoning_at_decision", sa.Text(), nullable=True),
    )
    op.create_index("idx_dcf_ticker", "decision_counterfactual", ["ticker", "decided_at"])
    op.create_index("idx_dcf_decision", "decision_counterfactual", ["decision_id"])
    op.create_index("idx_dcf_type", "decision_counterfactual", ["decision_type"])

    # Append-only triggers
    op.execute("""
    CREATE TRIGGER dcf_no_update BEFORE UPDATE ON decision_counterfactual
    BEGIN SELECT RAISE(ABORT, 'decision_counterfactual append-only : pas d UPDATE'); END;
    """)
    op.execute("""
    CREATE TRIGGER dcf_no_delete BEFORE DELETE ON decision_counterfactual
    BEGIN SELECT RAISE(ABORT, 'decision_counterfactual append-only : pas de DELETE'); END;
    """)
    # decision_type valide
    op.execute("""
    CREATE TRIGGER dcf_decision_type_valid BEFORE INSERT ON decision_counterfactual
    FOR EACH ROW
    WHEN NEW.decision_type NOT IN ('entry', 'scale_in', 'partial_exit', 'full_exit', 'no_action_flag', 'override')
    BEGIN SELECT RAISE(ABORT, 'decision_type invalide pour decision_counterfactual'); END;
    """)
    # counterfactual_branch valide (v0 = hold uniquement, v1 ajoutera rotate / would_have_sold)
    op.execute("""
    CREATE TRIGGER dcf_branch_valid BEFORE INSERT ON decision_counterfactual
    FOR EACH ROW
    WHEN NEW.counterfactual_branch NOT IN ('hold', 'would_have_sold', 'rotate_to')
    BEGIN SELECT RAISE(ABORT, 'counterfactual_branch invalide (v0 = hold)'); END;
    """)

    # === counterfactual_resolution : append-only par horizon ===
    op.create_table(
        "counterfactual_resolution",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_counterfactual_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("resolved_at", sa.Text(), nullable=False,
                  server_default=sa.text("(datetime('now'))")),
        # Prix a T+N
        sa.Column("price_at_horizon_native", sa.Float(), nullable=True),
        sa.Column("price_at_horizon_eur", sa.Float(), nullable=True),
        # Valeurs comparees (EUR canonique)
        sa.Column("actual_value_eur", sa.Float(), nullable=False),
        sa.Column("counterfactual_value_eur", sa.Float(), nullable=False),
        sa.Column("delta_eur", sa.Float(), nullable=False),  # actual - counterfactual
        sa.Column("delta_pct", sa.Float(), nullable=False),  # vs anchor capital
        # Verdict deterministe
        sa.Column("verdict", sa.Text(), nullable=False),  # decision_beneficial | neutral | harmful
    )
    op.create_index("idx_cfr_dcf", "counterfactual_resolution",
                    ["decision_counterfactual_id", "horizon_days"])
    op.create_index("idx_cfr_ticker", "counterfactual_resolution", ["ticker", "resolved_at"])

    op.execute("""
    CREATE TRIGGER cfr_no_update BEFORE UPDATE ON counterfactual_resolution
    BEGIN SELECT RAISE(ABORT, 'counterfactual_resolution append-only : pas d UPDATE'); END;
    """)
    op.execute("""
    CREATE TRIGGER cfr_no_delete BEFORE DELETE ON counterfactual_resolution
    BEGIN SELECT RAISE(ABORT, 'counterfactual_resolution append-only : pas de DELETE'); END;
    """)
    # 1 resolution par (decision_counterfactual_id, horizon_days) -- unique
    op.execute("""
    CREATE UNIQUE INDEX uniq_cfr_dcf_horizon
    ON counterfactual_resolution(decision_counterfactual_id, horizon_days);
    """)
    op.execute("""
    CREATE TRIGGER cfr_verdict_valid BEFORE INSERT ON counterfactual_resolution
    FOR EACH ROW
    WHEN NEW.verdict NOT IN ('decision_beneficial', 'decision_neutral', 'decision_harmful')
    BEGIN SELECT RAISE(ABORT, 'verdict invalide'); END;
    """)


def downgrade():
    for trig in ["dcf_no_update", "dcf_no_delete", "dcf_decision_type_valid", "dcf_branch_valid",
                 "cfr_no_update", "cfr_no_delete", "cfr_verdict_valid"]:
        op.execute(f"DROP TRIGGER IF EXISTS {trig}")
    op.execute("DROP INDEX IF EXISTS uniq_cfr_dcf_horizon")
    op.drop_table("counterfactual_resolution")
    op.drop_table("decision_counterfactual")
