"""Ledger transactions append-only + positions_meta slim — couche additive.

Cf SPEC_LEDGER.md §1 (transactions append-only) + §2 (positions_meta) + §7 (invariants
porteurs) + §5 (ordre des opérations figé).

Cette migration est PUREMENT ADDITIVE :
  - CREATE TABLE transactions (vide au départ, back-fill séparé scripts/migrate_*)
  - CREATE TABLE positions_meta (vide au départ, back-fill séparé)
  - 3 triggers structurels : UPDATE-impossible, DELETE-impossible. UNIQUE broker_trade_id
    via contrainte de colonne.
  - Ne touche PAS table positions existante (coexistence).

Le swap positions → VIEW se fait dans migration 0048, gaté par
scripts/check_ledger_view_equivalence.py (cf SPEC_LEDGER §4 Catch 2).
Back-fill (anchor 21 propres + relevés TR 5 stale) entre 0046 et 0048,
JAMAIS après le swap.

Portable : pas de dépendance fichier backup. Fresh DB / CI / clone rejouent identique.
"""
from __future__ import annotations

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. CREATE TABLE transactions (append-only)
    op.execute("""
        CREATE TABLE transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT NOT NULL,
            side            TEXT NOT NULL,
            qty             REAL NOT NULL CHECK(qty > 0),
            price_native    REAL NOT NULL,
            fees_native     REAL NOT NULL DEFAULT 0,
            currency        TEXT NOT NULL,
            fx_at_trade     REAL NOT NULL,
            fx_is_derived   INTEGER NOT NULL DEFAULT 0 CHECK(fx_is_derived IN (0, 1)),
            trade_date      TEXT NOT NULL,
            broker_trade_id TEXT UNIQUE,
            source          TEXT NOT NULL,
            is_anchor       INTEGER NOT NULL DEFAULT 0 CHECK(is_anchor IN (0, 1)),
            notes           TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # 2. Index pour les sous-requêtes corrélées de la VIEW (cf SPEC_LEDGER §2.2)
    # La VIEW agrège par (ticker, side) avec tri par trade_date pour le PRU temporel.
    op.execute("CREATE INDEX idx_transactions_ticker_side_date ON transactions(ticker, side, trade_date)")

    # 3. Garde structurelle #1 : modification interdite (write-once append-only)
    op.execute(
        "CREATE TRIGGER transactions_writeonce_update "
        "BEFORE UPDATE ON transactions FOR EACH ROW "
        "BEGIN "
        "SELECT RAISE(ABORT, 'transactions append-only (SPEC_LEDGER §1) : modification interdite. Corriger via entrée compensatoire (ADJUST futur).'); "
        "END"
    )

    # 4. Garde structurelle #2 : suppression interdite (immuabilité)
    op.execute(
        "CREATE TRIGGER transactions_writeonce_delete "
        "BEFORE DELETE ON transactions FOR EACH ROW "
        "BEGIN "
        "SELECT RAISE(ABORT, 'transactions append-only (SPEC_LEDGER §1) : suppression interdite. Corriger via entrée compensatoire (ADJUST futur).'); "
        "END"
    )

    # Garde structurelle #3 : UNIQUE broker_trade_id déjà déclarée sur la colonne.

    # 5. CREATE TABLE positions_meta (slim, 5 colonnes déclarées)
    # Cf SPEC_LEDGER §2.1 : séparation dérivé/déclaré.
    # status reste un label sémantique (active/superseded/review/closed),
    # PAS dérivé de qty=0 (fait ≠ label, ne pas conflate).
    op.execute("""
        CREATE TABLE positions_meta (
            ticker  TEXT PRIMARY KEY,
            notes   TEXT,
            status  TEXT,
            account TEXT,
            wrapper TEXT
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS positions_meta")
    op.execute("DROP TRIGGER IF EXISTS transactions_writeonce_delete")
    op.execute("DROP TRIGGER IF EXISTS transactions_writeonce_update")
    op.execute("DROP INDEX IF EXISTS idx_transactions_ticker_side_date")
    op.execute("DROP TABLE IF EXISTS transactions")
