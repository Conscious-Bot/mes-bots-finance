"""Fix trigger ORPHAN trop large : matche "post-orphan rewrite" en faux positif.

Bug detecte 30/05 matin : price_monitor bloque sur AMD + GOOGL parce que
leurs key_drivers contiennent "post-orphan rewrite 2026-05-29" (description
du FIX d'hier). Le trigger 0016 matchait juste "%ORPHAN%" partout dans le
texte = faux positif.

Fix : pattern strict "ORPHAN:" (uppercase + colon) qui matche le pattern
ORIGINAL tag ("ORPHAN: position held but Thèse #5 names AMZN not GOOGL.")
sans toucher les descriptions retro.

Migration : drop les 2 triggers de 0016 + recreate avec pattern strict.

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-30
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    # Drop les 2 triggers trop larges
    op.execute("DROP TRIGGER IF EXISTS theses_no_orphan_drivers")
    op.execute("DROP TRIGGER IF EXISTS theses_no_orphan_drivers_upd")

    # Recree avec pattern strict "ORPHAN:" (avec colon = tag explicite)
    op.execute("""
    CREATE TRIGGER theses_no_orphan_drivers
    BEFORE INSERT ON theses
    FOR EACH ROW
    WHEN NEW.key_drivers LIKE '%ORPHAN:%' OR NEW.key_drivers LIKE '%"ORPHAN"%'
    BEGIN
        SELECT RAISE(ABORT, 'F4 invariant : key_drivers contient le tag ORPHAN explicite ("ORPHAN:" ou "ORPHAN" en liste) -- ecris des drivers reels avant insert (utilise status=draft sinon)');
    END;
    """)
    op.execute("""
    CREATE TRIGGER theses_no_orphan_drivers_upd
    BEFORE UPDATE ON theses
    FOR EACH ROW
    WHEN (NEW.key_drivers LIKE '%ORPHAN:%' OR NEW.key_drivers LIKE '%"ORPHAN"%') AND NEW.status = 'active'
    BEGIN
        SELECT RAISE(ABORT, 'F4 invariant : key_drivers contient le tag ORPHAN explicite sur these active');
    END;
    """)


def downgrade():
    # Revert au pattern large 0016
    op.execute("DROP TRIGGER IF EXISTS theses_no_orphan_drivers")
    op.execute("DROP TRIGGER IF EXISTS theses_no_orphan_drivers_upd")
    op.execute("""
    CREATE TRIGGER theses_no_orphan_drivers
    BEFORE INSERT ON theses
    FOR EACH ROW
    WHEN NEW.key_drivers LIKE '%ORPHAN%'
    BEGIN
        SELECT RAISE(ABORT, 'F4 invariant : key_drivers ne peut contenir "ORPHAN"');
    END;
    """)
    op.execute("""
    CREATE TRIGGER theses_no_orphan_drivers_upd
    BEFORE UPDATE ON theses
    FOR EACH ROW
    WHEN NEW.key_drivers LIKE '%ORPHAN%' AND NEW.status = 'active'
    BEGIN
        SELECT RAISE(ABORT, 'F4 invariant : key_drivers ne peut contenir "ORPHAN" sur these active');
    END;
    """)
