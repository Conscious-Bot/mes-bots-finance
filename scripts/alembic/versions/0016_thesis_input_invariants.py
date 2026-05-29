"""Bake invariants schema sur theses : empeche le retour de F4 ORPHAN + F7 vol aveugle.

Directive user #2 audit 29/05 : "Bake ca maintenant : c'est gratuit pendant la
construction, cher en retrofit. un seul driver canonique / position, stop/cible
stockes avec leur justification fondamentale, prix obligatoire."

Triggers SQLite ajoutes :
1. BEFORE INSERT/UPDATE theses : si key_drivers contient "ORPHAN" (literal),
   bloque -> empeche le retour de "GOOGL these = AMZN" et "AMD ORPHAN".
2. BEFORE INSERT/UPDATE theses : conviction doit etre IN (1,2,3,4,5).
3. BEFORE INSERT theses status='active' : doit avoir entry_price OR
   target_full OR stop_price (pas tous NULL d'un coup -> empeche SNOW vol
   aveugle a la creation). UPDATE bien sur tolere car les inputs sont remplis
   progressivement.

Note : ces triggers sont volontairement STRICTS au niveau SQL. Le code qui
INSERT/UPDATE doit gerer les violations. Cf F7 SNOW : si on entre une these
sans aucun input, c'est qu'on veut la reflechir = utiliser un autre statut
(draft/wip) au lieu de "active".

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-29
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    # Trigger 1 : empeche "ORPHAN" en key_drivers (F4 GOOGL=AMZN)
    op.execute("""
    CREATE TRIGGER IF NOT EXISTS theses_no_orphan_drivers
    BEFORE INSERT ON theses
    FOR EACH ROW
    WHEN NEW.key_drivers LIKE '%ORPHAN%'
    BEGIN
        SELECT RAISE(ABORT, 'F4 invariant : key_drivers ne peut contenir "ORPHAN" -- ecris des drivers reels avant insert (utilise status=draft sinon)');
    END;
    """)
    op.execute("""
    CREATE TRIGGER IF NOT EXISTS theses_no_orphan_drivers_upd
    BEFORE UPDATE ON theses
    FOR EACH ROW
    WHEN NEW.key_drivers LIKE '%ORPHAN%' AND NEW.status = 'active'
    BEGIN
        SELECT RAISE(ABORT, 'F4 invariant : key_drivers ne peut contenir "ORPHAN" sur these active');
    END;
    """)
    # Trigger 2 : conviction valide
    op.execute("""
    CREATE TRIGGER IF NOT EXISTS theses_conviction_range
    BEFORE INSERT ON theses
    FOR EACH ROW
    WHEN NEW.conviction IS NOT NULL AND NEW.conviction NOT IN (1, 2, 3, 4, 5)
    BEGIN
        SELECT RAISE(ABORT, 'conviction doit etre 1-5');
    END;
    """)
    op.execute("""
    CREATE TRIGGER IF NOT EXISTS theses_conviction_range_upd
    BEFORE UPDATE ON theses
    FOR EACH ROW
    WHEN NEW.conviction IS NOT NULL AND NEW.conviction NOT IN (1, 2, 3, 4, 5)
    BEGIN
        SELECT RAISE(ABORT, 'conviction doit etre 1-5');
    END;
    """)
    # Trigger 3 : these active doit avoir au moins UN parametre fondamental
    # (sinon = vol aveugle integral comme SNOW etait)
    op.execute("""
    CREATE TRIGGER IF NOT EXISTS theses_active_must_have_inputs
    BEFORE INSERT ON theses
    FOR EACH ROW
    WHEN NEW.status = 'active'
      AND NEW.entry_price IS NULL
      AND NEW.target_full IS NULL
      AND NEW.stop_price IS NULL
    BEGIN
        SELECT RAISE(ABORT, 'F7 invariant : these active doit avoir entry_price OU target_full OU stop_price (sinon utilise status=draft)');
    END;
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS theses_no_orphan_drivers")
    op.execute("DROP TRIGGER IF EXISTS theses_no_orphan_drivers_upd")
    op.execute("DROP TRIGGER IF EXISTS theses_conviction_range")
    op.execute("DROP TRIGGER IF EXISTS theses_conviction_range_upd")
    op.execute("DROP TRIGGER IF EXISTS theses_active_must_have_inputs")
