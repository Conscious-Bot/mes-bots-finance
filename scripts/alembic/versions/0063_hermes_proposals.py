"""hermes_proposals : SAS write-gate pour le majordome Hermes (20/06/2026).

Tier P du contrat SAS : Hermes ne peut JAMAIS ecrire l'etat Presage
directement. Il depose des lignes ici. Un drain APScheduler (cadence ~5
min) consume les pending, applique le doctrine_gate, puis :
- AUTO -> commit via storage passerelle typee (jamais Hermes)
- TAP  -> notify Telegram + attente reponse user
- KO   -> mark rejected avec verdict raison

kind (enum ferme, evite scope creep silencieux) :
- journal_decision  (AUTO) : log d'un trade deja execute (KPI #5)
- log_prediction    (TAP)  : nouvelle prediction (gate falsifiabilite + date + mecanisme)
- open_thesis       (TAP)  : touche book + conviction
- close_thesis      (TAP)  : touche book + conviction
- set_conviction    (TAP)  : jugement explicite c5/c4 etc, standard c5 brutal
- research_note     (TIER_R, ne devrait jamais arriver ici en pratique)

class (enum ferme) :
- auto : commit sans user-tap apres doctrine_gate OK
- tap  : commit seulement apres approval user explicit

status transitions (audit perm) :
  pending -> committed         (auto path, gate OK)
  pending -> awaiting_tap      (tap path, gate OK, attend user)
  awaiting_tap -> committed    (user approved)
  awaiting_tap -> declined     (user declined)
  pending -> rejected          (gate KO, verdict = raison)

verdict : raison textuelle du gate (ex : 'duplicate detected', 'sizing
exceeds cap-band', 'falsifiability test missing'). Pour transparence
audit + debug futur.

origin : 'hermes' default. Permet futurs majordomes (Athena, etc.) sans
schema migration. Audit chain : 'qui a propose'.

Append-only (audit doctrine #150 + L17) :
- DELETE interdit via trigger
- UPDATE autorise UNIQUEMENT sur status / verdict / resolved_at
  (id / kind / payload_json / class / origin / created_at sont immuables)
- Tout drain action = ligne immutable + status field transition

Revision ID: 0063
Revises: 0062
"""
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE proposals (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            kind         TEXT NOT NULL
                         CHECK(kind IN (
                             'journal_decision',
                             'log_prediction',
                             'open_thesis',
                             'close_thesis',
                             'set_conviction',
                             'research_note'
                         )),
            payload_json TEXT NOT NULL,
            class        TEXT NOT NULL
                         CHECK(class IN ('auto', 'tap')),
            status       TEXT NOT NULL DEFAULT 'pending'
                         CHECK(status IN (
                             'pending',
                             'committed',
                             'rejected',
                             'awaiting_tap',
                             'declined'
                         )),
            verdict      TEXT,
            resolved_at  TEXT,
            origin       TEXT NOT NULL DEFAULT 'hermes'
        )
    """)
    op.execute(
        "CREATE INDEX idx_proposals_status_created "
        "ON proposals(status, created_at)"
    )
    op.execute(
        "CREATE INDEX idx_proposals_kind_status "
        "ON proposals(kind, status)"
    )
    op.execute("""
        CREATE TRIGGER proposals_no_delete
        BEFORE DELETE ON proposals
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'proposals is append-only (audit doctrine #150). DELETE interdit.');
        END
    """)
    # UPDATE legitime sur status/verdict/resolved_at (le drain fait ces
    # transitions). Bloque toute mutation des champs immuables.
    op.execute("""
        CREATE TRIGGER proposals_no_update_immutable
        BEFORE UPDATE ON proposals
        FOR EACH ROW
        WHEN (NEW.id != OLD.id
              OR NEW.kind != OLD.kind
              OR NEW.payload_json != OLD.payload_json
              OR NEW.class != OLD.class
              OR NEW.origin != OLD.origin
              OR NEW.created_at != OLD.created_at)
        BEGIN
            SELECT RAISE(ABORT,
                'proposals : id / kind / payload_json / class / origin / created_at immuables (append-only audit).'
            );
        END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS proposals_no_update_immutable")
    op.execute("DROP TRIGGER IF EXISTS proposals_no_delete")
    op.execute("DROP INDEX IF EXISTS idx_proposals_kind_status")
    op.execute("DROP INDEX IF EXISTS idx_proposals_status_created")
    op.execute("DROP TABLE IF EXISTS proposals")
