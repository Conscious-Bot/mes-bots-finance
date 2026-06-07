"""price_history + fx_history : append-only datated inputs (axe 3 first-principle).

Spec red-team 07/06 nuit++ : "stocke les inputs dates, derive les outputs live.
Ne stocke jamais une valeur qui est fonction d'un prix."

Avant : prices.py = RAM cache TTL only (_PX_CACHE _FX_CACHE), zero persistence.
Consequences :
- Pas de freshness queryable (pas de SELECT max(asof_age) FROM ...)
- Pas d'historique prix -> attribution 2x2 return decomposition impossible
- eur_value stocke gele dans positions.notes -> mort a la milliseconde suivante

Apres : prices.get() append + cache. La serie historique vient gratuite avec
la fraicheur queryable.

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-07
"""

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    # === price_history (append-only inputs dates) ===
    op.execute("""
        CREATE TABLE price_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker        TEXT NOT NULL,
            asof          TEXT NOT NULL,       -- timestamp observation (ISO UTC)
            price_native  REAL NOT NULL,
            currency      TEXT NOT NULL,
            source        TEXT NOT NULL        -- 'yfinance' / 'manual' / etc
        )
    """)
    # Vue "dernier prix" : SELECT ... ORDER BY asof DESC LIMIT 1 par ticker
    op.execute(
        "CREATE INDEX idx_px_ticker_asof ON price_history(ticker, asof DESC)"
    )
    # Filter par fraicheur globale (oldest_asof query)
    op.execute(
        "CREATE INDEX idx_px_asof ON price_history(asof DESC)"
    )

    # === fx_history (append-only FX dates) ===
    op.execute("""
        CREATE TABLE fx_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            base      TEXT NOT NULL,
            quote     TEXT NOT NULL,
            rate      REAL NOT NULL,
            asof      TEXT NOT NULL,
            source    TEXT NOT NULL
        )
    """)
    op.execute(
        "CREATE INDEX idx_fx_pair_asof ON fx_history(base, quote, asof DESC)"
    )
    op.execute(
        "CREATE INDEX idx_fx_asof ON fx_history(asof DESC)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_fx_asof")
    op.execute("DROP INDEX IF EXISTS idx_fx_pair_asof")
    op.execute("DROP TABLE IF EXISTS fx_history")
    op.execute("DROP INDEX IF EXISTS idx_px_asof")
    op.execute("DROP INDEX IF EXISTS idx_px_ticker_asof")
    op.execute("DROP TABLE IF EXISTS price_history")
