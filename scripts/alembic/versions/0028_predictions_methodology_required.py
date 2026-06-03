"""#98 ADR 014 hazard B : drop DEFAULT 'v1' on predictions.methodology_version.

Avant : `methodology_version TEXT NOT NULL DEFAULT 'v1'`. Tout INSERT qui
oublie de specifier la colonne tag silencieusement 'v1' -> exclu du
canonical filter quand v2 est canonical -> headline v2 silently
under-counts. Silent-failure exact que le doctrine combat, cachee dans
le schema.

Fix structurel : retrait du DEFAULT. La colonne reste NOT NULL. Un INSERT
qui omet la colonne crash IntegrityError ("NOT NULL constraint failed").
Defense en profondeur cote schema (cote code : insert_prediction valide
explicitement methodology_version param keyword-only).

SQLite pattern (pas d'ALTER COLUMN DEFAULT) :
  1. Create predictions_new sans DEFAULT
  2. INSERT INTO predictions_new SELECT * FROM predictions (preserve les
     valeurs existantes : v0 / v1 cohortes intactes)
  3. DROP predictions (drops indexes)
  4. ALTER predictions_new RENAME TO predictions
  5. Recreate indexes idx_predictions_target + idx_predictions_signal

FK prediction_audit_log.prediction_id REFERENCES predictions(id) : preserved
par la rename pattern. PRAGMA foreign_keys OFF temporairement pour eviter
les checks pendant le swap.

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-03
"""

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("PRAGMA foreign_keys = OFF")

    # Schema identique a 0027 MAIS sans DEFAULT 'v1' sur methodology_version.
    # Et methodology_version reste NOT NULL -> oubli = IntegrityError loud.
    op.execute(
        """
        CREATE TABLE predictions_new (
            id INTEGER PRIMARY KEY,
            signal_id INTEGER REFERENCES signals(id),
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL,
            horizon_days INTEGER NOT NULL,
            baseline_price REAL,
            baseline_date TEXT NOT NULL,
            target_date TEXT NOT NULL,
            resolved_at TEXT,
            final_price REAL,
            return_pct REAL,
            outcome TEXT,
            credibility_delta REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            probability_at_creation REAL,
            brier_score REAL,
            methodology_version TEXT NOT NULL,
            scoring_trace_json TEXT,
            source_metadata_json TEXT
        )
        """
    )

    # Copy data : ordre identique de colonnes preserve les valeurs existantes
    # (v0 quarantine 12/05 + v1 reste).
    op.execute(
        """
        INSERT INTO predictions_new
        SELECT id, signal_id, ticker, direction, horizon_days, baseline_price,
               baseline_date, target_date, resolved_at, final_price, return_pct,
               outcome, credibility_delta, created_at, probability_at_creation,
               brier_score, methodology_version, scoring_trace_json,
               source_metadata_json
        FROM predictions
        """
    )

    op.execute("DROP TABLE predictions")
    op.execute("ALTER TABLE predictions_new RENAME TO predictions")

    # Recreate indexes.
    op.execute("CREATE INDEX idx_predictions_target ON predictions(target_date)")
    op.execute("CREATE INDEX idx_predictions_signal ON predictions(signal_id)")

    op.execute("PRAGMA foreign_keys = ON")


def downgrade():
    # Restore DEFAULT 'v1' (rollback). Recipe symmetric.
    op.execute("PRAGMA foreign_keys = OFF")
    op.execute(
        """
        CREATE TABLE predictions_old (
            id INTEGER PRIMARY KEY,
            signal_id INTEGER REFERENCES signals(id),
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL,
            horizon_days INTEGER NOT NULL,
            baseline_price REAL,
            baseline_date TEXT NOT NULL,
            target_date TEXT NOT NULL,
            resolved_at TEXT,
            final_price REAL,
            return_pct REAL,
            outcome TEXT,
            credibility_delta REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            probability_at_creation REAL,
            brier_score REAL,
            methodology_version TEXT NOT NULL DEFAULT 'v1',
            scoring_trace_json TEXT,
            source_metadata_json TEXT
        )
        """
    )
    op.execute(
        """
        INSERT INTO predictions_old
        SELECT id, signal_id, ticker, direction, horizon_days, baseline_price,
               baseline_date, target_date, resolved_at, final_price, return_pct,
               outcome, credibility_delta, created_at, probability_at_creation,
               brier_score, methodology_version, scoring_trace_json,
               source_metadata_json
        FROM predictions
        """
    )
    op.execute("DROP TABLE predictions")
    op.execute("ALTER TABLE predictions_old RENAME TO predictions")
    op.execute("CREATE INDEX idx_predictions_target ON predictions(target_date)")
    op.execute("CREATE INDEX idx_predictions_signal ON predictions(signal_id)")
    op.execute("PRAGMA foreign_keys = ON")
