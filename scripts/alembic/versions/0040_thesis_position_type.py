"""thesis position_type enum (3 valeurs, axe EXIT seul) + tags orthogonaux.

Spec user red-team 07/06 :
- 3 types mutuellement exclusifs sur l'axe EXIT POLICY uniquement :
  - structural : exit seulement sur invalidation-trigger, pas de stop-prix
  - priced     : discipline stop/target normale (defaut)
  - tactical   : borne par catalyseur/temps, stop serre, trim agressif
- position_tags_json : orthogonal libre {mega_cap, commodity, satellite, ...},
  non-canonical pour decision.
- structural_justification REQUIS si position_type='structural'.
  Hook tamper-evident : assignation a structural append au thesis_integrity_log
  (chain hash). Tu ne peux pas re-tagger un loser en structural sans laisser
  une trace. C'est la garde contre Catch 1 user : "chokepoint self-assigne
  devient excuse au lieu de discipline".

Revision ID: 0040
Revises: 0039
Create Date: 2026-06-07
"""

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite : ADD COLUMN avec CHECK n'est pas applique en mode strict sur
    # table populated. CHECK enforce sur INSERT/UPDATE futurs. Suffisant car
    # backfill explicite via storage.set_position_type.
    op.execute(
        "ALTER TABLE theses ADD COLUMN position_type TEXT NOT NULL "
        "DEFAULT 'priced' "
        "CHECK(position_type IN ('structural', 'priced', 'tactical'))"
    )
    op.execute(
        "ALTER TABLE theses ADD COLUMN position_tags_json TEXT NOT NULL "
        "DEFAULT '[]'"
    )
    op.execute(
        "ALTER TABLE theses ADD COLUMN structural_justification TEXT"
    )
    op.execute(
        "CREATE INDEX idx_theses_position_type "
        "ON theses(position_type, status)"
    )


def downgrade():
    # SQLite < 3.35 ne supporte pas DROP COLUMN natif -- non-reversible
    pass
