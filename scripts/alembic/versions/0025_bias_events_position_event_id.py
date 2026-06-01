"""Pile 2.1 v2.c.6 -- ADD COLUMN bias_events.position_event_id

Surface 2 lock_in (biais #1 PRESAGE) : la detection winner-sold fire dans
shared.positions.add_sell apres cx.commit() (cf LESSONS L7). Le bias_event
ouvert doit pointer vers l'event metier de vente (position_events.id avec
event_type='sell') pour audit-trail explicite.

Voie propre (user 01/06 Q4) : nouvelle colonne FK + index, pas de stockage
en JSON. Permet query directe :
    SELECT b.* FROM bias_events b
    JOIN position_events pe ON pe.id = b.position_event_id
    WHERE pe.event_type='sell' AND b.bias='lock_in'

Indexe partial (WHERE NOT NULL) pour ne pas grossir l'index sur les
bias_events kca/over_cap qui n'ont pas de position_event_id.

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-01
"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE bias_events ADD COLUMN position_event_id INTEGER REFERENCES position_events(id)")
    op.execute(
        "CREATE INDEX idx_bias_events_position_event "
        "ON bias_events(position_event_id) WHERE position_event_id IS NOT NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_bias_events_position_event")
    # SQLite ne supporte pas DROP COLUMN avant 3.35 ; on laisse la colonne
    # orpheline (compatible runtime ; les downgrades rares justifient la trace).
