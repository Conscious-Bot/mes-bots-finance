"""A0 : Add variant_perception + driver_epic + benchmark cols to theses.

Spec red-team 07/06 nuit DECISION_QUALITY_ENGINE A0. Champs PIT figes a
l'entree, hashes par A2 integrity layer pour tamper-evidence.

Retro-compat : default NULL pour theses existantes. add_thesis WARNING si
vide sur conviction >= 4 (gate weak-faute, pas bloquant).

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-07
"""

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    # ADD COLUMN with NULL default = retro-compat existing theses
    op.execute("ALTER TABLE theses ADD COLUMN variant_perception TEXT")
    op.execute("ALTER TABLE theses ADD COLUMN driver_epic TEXT")  # JSON-serialized EpicDriver
    op.execute("ALTER TABLE theses ADD COLUMN benchmark TEXT")


def downgrade():
    # SQLite ne supporte pas DROP COLUMN nativement < 3.35 -- on accepte non-reversible
    pass
