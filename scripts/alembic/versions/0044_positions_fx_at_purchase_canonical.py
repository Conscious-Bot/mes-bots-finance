"""positions.avg_cost_native + fx_at_purchase : cure canonique definitive FX.

Directive Olivier 08/06 : la solution canonique long terme.

Diagnostic complete (apres migration 0043 + corrections manuelles) :
- avg_cost_eur backfill au fx_now est STRUCTURELLEMENT FAUX pour les tickers
  USD historiques (USD a baisse ~12-15% depuis 2024, donc avg_cost_eur
  reverse-engineering depuis fx_now donne un cost_basis trop bas, donc P&L
  surestime).
- La solution propre : stocker M1 triple pour avg_cost = (value_native,
  currency, fx_at_purchase). Ainsi avg_cost_eur = avg_cost_native * fx_at_purchase
  est DERIVE et FIGE au moment de l'achat -- jamais touche par les variations
  FX subsequentes.

Migration :
  ADD COLUMN avg_cost_native      REAL    -- valeur native du PRU (USD, JPY, KRW, EUR)
  ADD COLUMN avg_cost_currency    TEXT    -- devise du PRU (cohérent avec last_price_currency)
  ADD COLUMN fx_at_purchase       REAL    -- taux FX vers EUR au moment de l'achat (FIGE)

Backfill par convention detectee :
- USD tickers : avg_cost stocké = native USD ;
    fx_at_purchase = avg_cost_eur_USER (si Olivier l'a corrige manuellement)
                   / avg_cost ; sinon fallback fx_rate_to_eur (fx_now, approximatif)
- EUR-native (.AS/.PA) : avg_cost = native EUR, fx_at_purchase = 1.0
- JPY/KRW : avg_cost_legacy stocké EN EUR (ADR 005 obsolete) ;
    On garde avg_cost_eur tel quel mais on rend la convention native explicite :
    avg_cost_native = avg_cost_eur / fx_now (reconverti synthetique native pour cohérence schéma)
    fx_at_purchase = fx_now (synthetique mais coherent : avg_cost_eur dérive = avg_cost_native * fx_at_purchase)

Apres backfill : avg_cost_eur = avg_cost_native * fx_at_purchase (DERIVATION CANONIQUE).
Pour les futurs INSERT positions : prendre avg_cost_native + currency + fx_at_purchase
en entrée user (broker), pas avg_cost en mixed convention.

Revision ID: 0044
Revises: 0043
"""

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade():
    # ADD COLUMNs (nullable initial, backfill apres)
    op.execute("ALTER TABLE positions ADD COLUMN avg_cost_native REAL")
    op.execute("ALTER TABLE positions ADD COLUMN avg_cost_currency TEXT")
    op.execute("ALTER TABLE positions ADD COLUMN fx_at_purchase REAL")

    # Backfill :
    # 1. Tickers EUR-native : avg_cost = native EUR, fx_at_purchase = 1.0
    op.execute("""
        UPDATE positions
        SET avg_cost_native = avg_cost,
            avg_cost_currency = 'EUR',
            fx_at_purchase = 1.0
        WHERE last_price_currency = 'EUR' AND status = 'open'
    """)

    # 2. Tickers USD : avg_cost en native USD.
    # fx_at_purchase = avg_cost_eur (corrige manuellement par Olivier dans certains cas) / avg_cost
    # Pour les tickers non-corriges, ce ratio = fx_now (approximation).
    op.execute("""
        UPDATE positions
        SET avg_cost_native = avg_cost,
            avg_cost_currency = 'USD',
            fx_at_purchase = CASE
                WHEN avg_cost > 0 AND avg_cost_eur > 0
                    THEN avg_cost_eur / avg_cost
                ELSE fx_rate_to_eur
            END
        WHERE last_price_currency = 'USD' AND status = 'open'
    """)

    # 3. Tickers JPY/KRW : avg_cost legacy stocke EN EUR (ADR 005 obsolete).
    # On rend la convention explicite : avg_cost_native = avg_cost_eur / fx_now
    # (synthetic back-to-native). fx_at_purchase = fx_now (synthetic mais coherent).
    op.execute("""
        UPDATE positions
        SET avg_cost_native = CASE
                WHEN fx_rate_to_eur > 0 THEN avg_cost / fx_rate_to_eur
                ELSE avg_cost
            END,
            avg_cost_currency = last_price_currency,
            fx_at_purchase = fx_rate_to_eur
        WHERE last_price_currency IN ('JPY', 'KRW') AND status = 'open'
    """)


def downgrade():
    op.execute("ALTER TABLE positions DROP COLUMN avg_cost_native")
    op.execute("ALTER TABLE positions DROP COLUMN avg_cost_currency")
    op.execute("ALTER TABLE positions DROP COLUMN fx_at_purchase")
