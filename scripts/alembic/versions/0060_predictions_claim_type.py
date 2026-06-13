"""Predictions : event/data claims first-class (cure 13/06 chantier #150 G2).

Le schema predictions actuel a ete construit sur UN SEUL type de claim : un
prix, sur un ticker, issu d'un signal. C'est l'empreinte du biais
price-as-proof gravee dans le schema lui-meme. Toute cette session 13/06 on
a dit "fais plus de claims event-type, le prix ne prouve pas la these" --
et le schema ne sait pas representer un claim qui n'est pas un prix.

Cette migration apprend au modele de donnees qu'une prediction peut etre
autre chose qu'un pari de prix. C'est le mini-prerequis G2 du chantier #150
(redevabilite decisionnelle), dont l'absence aurait force a logger les 10
sentinelles event-type en price-claims deguisees -- exactement la
contamination que le chantier combat (L25bis).

Changements :

  1. Nouvelles colonnes
     - claim_type TEXT NOT NULL CHECK IN ('price','event','data')
       Defaut 'price' a la creation, backfill 'price' pour les 285 lignes
       existantes (toutes price-driven legitimement).
     - resolution_source TEXT NULL pour 'price', requis cote app pour
       event/data (enforce via insert_prediction + test_schema_drift, pas
       CHECK SQL pour garder la flexibilite legacy).
     - origin TEXT NOT NULL CHECK IN ('signal','manual') DEFAULT 'signal'.
       Trace qui a pose le claim. 'manual' = pose Olivier (sentinelles,
       pre-registration thesis). 'signal' = pose auto-scorer.

  2. Ticker NULL-able
     Les claims macro (DRAM glut, hyperscaler capex, SEMI NA billings)
     n'ont pas de ticker propre. Forcer un ticker proxy (MU/SOXX/GEV) =
     contamination, pas commodite. Recreate table requis (SQLite ne
     supporte pas DROP NOT NULL via ALTER).

  3. signal_id reste NULL-able (deja le cas)
     'manual' origin peut avoir signal_id NULL. Validation app : origin
     'signal' DOIT avoir signal_id.

  4. baseline_price reste NULL-able (deja le cas)
     event-claim n'a pas de baseline. resolve_due_predictions skip event.

  5. direction enum implicite preserve
     Distribution actuelle : bullish/bearish. 'watch' techniquement
     accepte (pas de CHECK SQL). La voie auto-scorer continue de skip
     watch (cf learning.py:227, doctrine "watch sort du ledger" pour
     V2 inchangee). Voie manual ouvre watch pour sentinelles.

  6. Triggers append-only PRESERVES
     predictions_no_delete + predictions_resolve_writeonce (migration
     0058) re-crees apres recreate-table. AUDIT BRIER INTACTE.

  7. Indexes PRESERVES
     idx_predictions_target + idx_predictions_signal re-crees.

Backfill 290 lignes existantes : claim_type='price', origin='signal'.
Honnete (c'est ce qu'elles sont) et permet pour la 1ere fois une
calibration Brier SEGMENTABLE par type de claim -- valeur derivee bonus.

PRE-REQUIS OPERATIONNEL OBLIGATOIRE : bot.main PRESAGE STOPPE avant upgrade.
Le recreate-table (CREATE temp + COPY + DROP + RENAME + RE-CREATE triggers)
ouvre une fenetre ou les triggers append-only sont absents. Une ecriture
concurrente dans cette fenetre = corruption silencieuse + ledger non-protege.
Procedure : `kill -9 <PID bot.main>` AVANT `alembic upgrade head`. NE PAS
killer bot.py (tennis-bot parallel, cf [[parallel_projects_tennis_bot]]).

GARDE INTEGRITE : assertion COUNT(*) avant/apres copy. La migration ABORT si
les rows ne sont pas toutes copiees -- impossible de perdre du ledger
silencieusement.

Revision ID: 0060
Revises: 0059
"""
from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import text

    # SQLite : DROP NOT NULL sur ticker requiert recreate-table.
    # Pattern : CREATE temp -> COPY -> DROP -> RENAME -> RE-CREATE triggers+index.

    # GARDE INTEGRITE : compte la table source AVANT copy. Si != apres = ABORT.
    bind = op.get_bind()
    old_cnt = bind.execute(text("SELECT count(*) FROM predictions")).scalar()
    if old_cnt is None:
        raise RuntimeError("upgrade 0060 : SELECT count(*) returned None ; predictions inexistante ?")

    # 1. CREATE TABLE temp avec le nouveau schema
    # CHECK conditionnel sur resolution_source : la garde DB qui ferme la
    # CLASSE de sentinelle mal-formee, pas seulement l'instance (cf
    # tests/test_invariants_metier.py qui verifie que ce CHECK existe encore).
    op.execute("""
        CREATE TABLE predictions_new (
            id INTEGER PRIMARY KEY,
            signal_id INTEGER REFERENCES signals(id),
            ticker TEXT,
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
            source_metadata_json TEXT,
            claim_type TEXT NOT NULL DEFAULT 'price'
                CHECK(claim_type IN ('price', 'event', 'data')),
            resolution_source TEXT,
            origin TEXT NOT NULL DEFAULT 'signal'
                CHECK(origin IN ('signal', 'manual')),
            CHECK(claim_type = 'price' OR resolution_source IS NOT NULL)
        )
    """)

    # 2. COPY donnees existantes avec backfill claim_type='price' / origin='signal'
    op.execute("""
        INSERT INTO predictions_new (
            id, signal_id, ticker, direction, horizon_days, baseline_price,
            baseline_date, target_date, resolved_at, final_price, return_pct,
            outcome, credibility_delta, created_at, probability_at_creation,
            brier_score, methodology_version, scoring_trace_json,
            source_metadata_json, claim_type, origin
        )
        SELECT
            id, signal_id, ticker, direction, horizon_days, baseline_price,
            baseline_date, target_date, resolved_at, final_price, return_pct,
            outcome, credibility_delta, created_at, probability_at_creation,
            brier_score, methodology_version, scoring_trace_json,
            source_metadata_json, 'price', 'signal'
        FROM predictions
    """)

    # GARDE INTEGRITE : verifier que la copy a transfere TOUTES les rows.
    new_cnt = bind.execute(text("SELECT count(*) FROM predictions_new")).scalar()
    if new_cnt != old_cnt:
        raise RuntimeError(
            f"upgrade 0060 ABORT : backfill mismatch old_cnt={old_cnt} "
            f"new_cnt={new_cnt}. Une migration coeur qui ne compte pas ses "
            f"lignes est une migration qui espere. Tu perds {old_cnt - (new_cnt or 0)} "
            f"rows du ledger Brier si tu poursuis."
        )

    # 3. DROP triggers anciens (ne peuvent pas pointer une table renamed)
    op.execute("DROP TRIGGER IF EXISTS predictions_resolve_writeonce")
    op.execute("DROP TRIGGER IF EXISTS predictions_no_delete")

    # 4. DROP indexes anciens
    op.execute("DROP INDEX IF EXISTS idx_predictions_target")
    op.execute("DROP INDEX IF EXISTS idx_predictions_signal")

    # 5. DROP old table + RENAME new
    op.execute("DROP TABLE predictions")
    op.execute("ALTER TABLE predictions_new RENAME TO predictions")

    # 6. RE-CREATE triggers append-only (verbatim migration 0058)
    op.execute("""
        CREATE TRIGGER predictions_no_delete
        BEFORE DELETE ON predictions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'predictions append-only : DELETE interdit. Le track-record Brier exige l''immutabilité historique (audit 2026-06-12 P1.1).');
        END
    """)
    op.execute("""
        CREATE TRIGGER predictions_resolve_writeonce
        BEFORE UPDATE OF
            resolved_at, final_price, return_pct, outcome,
            credibility_delta, brier_score
        ON predictions
        FOR EACH ROW
        WHEN OLD.resolved_at IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'predictions resolve columns are write-once : déjà résolu, pas de réécriture du Brier/outcome (audit 2026-06-12 P1.1). Pour corriger : INSERT une ligne audit séparée.');
        END
    """)

    # 7. RE-CREATE indexes
    op.execute("CREATE INDEX idx_predictions_target ON predictions(target_date)")
    op.execute("CREATE INDEX idx_predictions_signal ON predictions(signal_id)")

    # 8. INDEX bonus sur claim_type (utile pour calibration segmentee)
    op.execute("CREATE INDEX idx_predictions_claim_type ON predictions(claim_type)")
    op.execute("CREATE INDEX idx_predictions_origin ON predictions(origin)")


def downgrade() -> None:
    # Symetrique : recreate table sans claim_type/resolution_source/origin,
    # ticker NOT NULL.
    # CAVEAT : les rows event/data sont PERDUES au downgrade (incompatibles
    # avec le schema d'origine ticker NOT NULL si ticker IS NULL).
    # Le downgrade est documente comme destructeur (downgrade 0058->0057 est
    # destructeur pour les triggers, ici pour les rows event-type).

    # 1. Refuse downgrade si des rows event/data avec ticker NULL existent
    #    (sinon recreate echoue silently sur NOT NULL violation).
    from sqlalchemy import text
    cnt = op.get_bind().execute(
        text(
            "SELECT count(*) FROM predictions "
            "WHERE claim_type IN ('event', 'data') OR ticker IS NULL"
        )
    ).scalar()
    if cnt and cnt > 0:
        raise RuntimeError(
            f"downgrade 0060->0059 refuse : {cnt} rows event/data ou ticker NULL "
            "incompatibles avec le schema price-only d'origine. Exporter d'abord."
        )

    op.execute("DROP INDEX IF EXISTS idx_predictions_origin")
    op.execute("DROP INDEX IF EXISTS idx_predictions_claim_type")
    op.execute("DROP INDEX IF EXISTS idx_predictions_signal")
    op.execute("DROP INDEX IF EXISTS idx_predictions_target")
    op.execute("DROP TRIGGER IF EXISTS predictions_resolve_writeonce")
    op.execute("DROP TRIGGER IF EXISTS predictions_no_delete")

    op.execute("""
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
            methodology_version TEXT NOT NULL,
            scoring_trace_json TEXT,
            source_metadata_json TEXT
        )
    """)
    op.execute("""
        INSERT INTO predictions_old SELECT
            id, signal_id, ticker, direction, horizon_days, baseline_price,
            baseline_date, target_date, resolved_at, final_price, return_pct,
            outcome, credibility_delta, created_at, probability_at_creation,
            brier_score, methodology_version, scoring_trace_json,
            source_metadata_json
        FROM predictions
    """)
    op.execute("DROP TABLE predictions")
    op.execute("ALTER TABLE predictions_old RENAME TO predictions")

    op.execute("""
        CREATE TRIGGER predictions_no_delete
        BEFORE DELETE ON predictions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'predictions append-only : DELETE interdit. Le track-record Brier exige l''immutabilité historique (audit 2026-06-12 P1.1).');
        END
    """)
    op.execute("""
        CREATE TRIGGER predictions_resolve_writeonce
        BEFORE UPDATE OF
            resolved_at, final_price, return_pct, outcome,
            credibility_delta, brier_score
        ON predictions
        FOR EACH ROW
        WHEN OLD.resolved_at IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'predictions resolve columns are write-once : déjà résolu, pas de réécriture du Brier/outcome (audit 2026-06-12 P1.1). Pour corriger : INSERT une ligne audit séparée.');
        END
    """)
    op.execute("CREATE INDEX idx_predictions_target ON predictions(target_date)")
    op.execute("CREATE INDEX idx_predictions_signal ON predictions(signal_id)")
