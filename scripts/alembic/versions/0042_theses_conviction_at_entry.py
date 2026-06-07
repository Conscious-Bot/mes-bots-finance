"""theses.conviction_at_entry : capture PIT conviction pour drift detection.

Spec user red-team 07/06 carte-decision #1 :
"Conviction PIT vs maintenant (drift)" -- detecter quand l'user a re-evalue
silencieusement une these (conviction c5 -> c4 sans trace).

Aujourd'hui : theses.conviction est ECRASE par chaque update -- pas d'historique.
Apres cette migration : conviction = courante (drift libre via update_thesis_field),
conviction_at_entry = baseline PIT (jamais mise a jour apres initial INSERT).

Backfill 26 actives : conviction_at_entry = conviction courante (snapshot J0,
on perd l'historique mai mais on capture le present comme baseline). Acceptable
per decision user "snapshot J0".

Hook drift : update_thesis_field detecte conviction change -> append au
thesis_integrity_log (tamper-evident). Toute drift conviction est tracee.

Revision ID: 0042
Revises: 0041
Create Date: 2026-06-07
"""

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE theses ADD COLUMN conviction_at_entry INTEGER"
    )
    # Backfill : snapshot J0 = conviction courante. On perd l'historique
    # avant 07/06 mais on capture le present comme baseline auditable.
    op.execute(
        "UPDATE theses SET conviction_at_entry = conviction "
        "WHERE conviction_at_entry IS NULL"
    )
    op.execute(
        "CREATE INDEX idx_theses_conviction_drift "
        "ON theses(conviction, conviction_at_entry) "
        "WHERE conviction != conviction_at_entry"
    )


def downgrade():
    pass
