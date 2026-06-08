"""positions.avg_cost_eur : canonique EUR pour P&L cohérent FX.

Directive Olivier 08/06 : "on choisit EUR et on s'y tient. Sourcer +
convertir auto a l'entree. Plus de probleme de conversion."

Diagnostic legacy (avant ce fix) :
- positions.avg_cost stockee sans convention claire :
  * USD tickers (AMD, ENTG, TSM, ...) : avg_cost en NATIVE (USD)
  * EUR-native (.AS/.PA) : avg_cost en EUR
  * JPY/KRW (.T/.KS) : avg_cost en EUR (legacy ADR 005 conversion a l'achat)
- Les consumers consomment au hasard l'une ou l'autre interpretation
  -> P&L incohérent sur les positions etrangeres (bug recurrent).

Fix canonique (cette migration) :
- ADD COLUMN avg_cost_eur REAL : valeur normalisee EUR cohérente partout
- Backfill par regle deterministe :
  * Si last_price_currency == 'USD' et abs(avg_cost) plus plausible en native :
    avg_cost_eur = avg_cost × fx_rate_to_eur
  * Sinon (EUR/JPY/KRW historique conversion-a-l'achat) :
    avg_cost_eur = avg_cost (deja EUR)
- Tous consumers lisent avg_cost_eur (source canonique).

avg_cost (colonne native) reste conservee pour audit + futur switch_currency UI
(cf TODO #119) -- mais le P&L canonique passe TOUJOURS par avg_cost_eur.

Note : pour les futures positions ajoutees, l'entree user sera convertie
automatiquement (gateway pattern, cf SOCLE Datum) -- ce sera une autre
amelioration du code d'insertion.

Revision ID: 0043
Revises: 0042
Create Date: 2026-06-08
"""

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade():
    # 1. ADD COLUMN avg_cost_eur (nullable initialement, on backfill juste apres)
    op.execute("ALTER TABLE positions ADD COLUMN avg_cost_eur REAL")

    # 2. Backfill canonique par regle deterministe.
    # On detecte la convention de avg_cost actuel par cohérence :
    #   - Pour USD tickers : avg_cost est en NATIVE (USD), donc avg_cost_eur = avg_cost * fx
    #   - Pour autres tickers : avg_cost est en EUR (legacy), avg_cost_eur = avg_cost tel quel
    # Detection : si last_price_currency == 'USD' -> convertir, sinon tel quel.
    op.execute("""
        UPDATE positions
        SET avg_cost_eur = CASE
            WHEN last_price_currency = 'USD'
                AND avg_cost IS NOT NULL
                AND fx_rate_to_eur IS NOT NULL
            THEN avg_cost * fx_rate_to_eur
            ELSE avg_cost
        END
        WHERE status = 'open' AND qty > 0
    """)


def downgrade():
    # SQLite ne supporte pas DROP COLUMN nativement ; alembic batch mode requis.
    # Pour rollback, restore depuis backup DB ou re-create table sans la colonne.
    op.execute("ALTER TABLE positions DROP COLUMN avg_cost_eur")
