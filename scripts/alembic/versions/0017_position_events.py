"""position_audit_log : audit trail append-only des jugements / lifecycle.

Distinct de la table position_events legacy (qui logue les trades buy/sell/
adjust avec qty+price). position_audit_log capture les changements de
JUGEMENT user (conviction, fade, thesis, driver, lifecycle) -- la matiere
du track-record bitemporel.

Directive user 29/05 round 3 :
> "L'historique append-only EST ton track record. Une Position qui ne garde
>  que son 'etat courant' perd la memoire de 'ce que tu croyais, quand' --
>  or c'est exactement l'actif Path 6."

Schema append-only stricte : aucun UPDATE / DELETE possible (triggers).

event_type enum :
  - "conviction_change"      : nouvelle conviction (DatedJudgment)
  - "fade_change"            : nouveau fade
  - "thesis_revise"          : these revisee (claim / target / stop / triggers)
  - "outcome"                : prediction resolved (correct / incorrect / neutral)
  - "lifecycle_transition"   : construction -> active -> exiting -> sold
  - "driver_recategorize"    : changement de driver canonical (rare)
  - "input_correction"       : audit fix (ex: ORPHAN -> reecrit)

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "position_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.Text(), nullable=False,
                  server_default=sa.text("(datetime('now'))")),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("actor", sa.Text(), nullable=True),
    )
    op.create_index("idx_pal_ticker", "position_audit_log", ["ticker", "occurred_at"])
    op.create_index("idx_pal_type", "position_audit_log", ["event_type", "occurred_at"])

    op.execute("""
    CREATE TRIGGER position_audit_log_no_update
    BEFORE UPDATE ON position_audit_log
    BEGIN
        SELECT RAISE(ABORT, 'position_audit_log est append-only : pas d UPDATE');
    END;
    """)
    op.execute("""
    CREATE TRIGGER position_audit_log_no_delete
    BEFORE DELETE ON position_audit_log
    BEGIN
        SELECT RAISE(ABORT, 'position_audit_log est append-only : pas de DELETE');
    END;
    """)
    op.execute("""
    CREATE TRIGGER position_audit_log_event_type_valid
    BEFORE INSERT ON position_audit_log
    FOR EACH ROW
    WHEN NEW.event_type NOT IN (
        'conviction_change', 'fade_change', 'thesis_revise',
        'outcome', 'lifecycle_transition',
        'driver_recategorize', 'input_correction'
    )
    BEGIN
        SELECT RAISE(ABORT, 'event_type invalide');
    END;
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS position_audit_log_no_update")
    op.execute("DROP TRIGGER IF EXISTS position_audit_log_no_delete")
    op.execute("DROP TRIGGER IF EXISTS position_audit_log_event_type_valid")
    op.drop_index("idx_pal_type", "position_audit_log")
    op.drop_index("idx_pal_ticker", "position_audit_log")
    op.drop_table("position_audit_log")
