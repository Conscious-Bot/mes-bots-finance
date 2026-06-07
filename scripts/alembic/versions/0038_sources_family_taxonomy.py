"""sources.family taxonomy : axe 2 QUALITY_BAR 1er geste.

Spec QUALITY_BAR Axe 2 garde-fou : "deux sources qui s'accordent toujours ne
comptent pas pour deux. Ce n'est pas une lecture du marche, c'est une lecture
d'une cohorte narrative."

Diagnostic au moment de la migration : 74/76 sources sont des newsletters
(monoculture narrative confirmee). 1 sec_filing (EDGAR), 1 manual.

Taxonomy 'family' :
- primary_filing  : EDGAR 8-K/10-Q/10-K, regulatory primary docs (orthogonal)
- insider         : Form 4, insider clusters (orthogonal comportemental)
- narrative_newsletter : substacks, beehiiv, opinion macro (cohorte narrative)
- broker_research : Goldman/Morgan/Jefferies research notes
- social          : reddit, twitter, WSB
- chat            : user manual taps via Telegram
- manual          : ajouts manuels user
- other           : fallback

Backfill deterministe par type existant. Aucune heuristique sur les noms
(la classification fine viendra par classify_signal_types ou wire dedie).

L'helper effective_n_signals(signals) compte le nombre de FAMILLES distinctes,
pas le nombre de sources brut. Une newsletter et 8 autres newsletters = 1
famille distinct = N_effective=1 (la cohorte narrative compte pour 1).

Pas de wire scoring action (gating L15 calibration N<100). Surface dashboard
chip seulement. Wire materiality_v2 downweight viendra apres calibration.

Revision ID: 0038
Revises: 0037
Create Date: 2026-06-07
"""

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

VALID_FAMILIES = (
    "primary_filing", "insider", "narrative_newsletter", "broker_research",
    "social", "chat", "manual", "other",
)


def upgrade():
    # SQLite : pas de ALTER TABLE ADD COLUMN ... CHECK direct sur table populated.
    # On ajoute colonne + default puis backfill, puis on appliquera CHECK via
    # trigger CHECK validation au prochain rebuild si necessaire.
    op.execute(
        "ALTER TABLE sources ADD COLUMN family TEXT "
        "NOT NULL DEFAULT 'narrative_newsletter'"
    )
    # Backfill deterministe par type existant
    op.execute(
        "UPDATE sources SET family='primary_filing' WHERE type='sec_filing'"
    )
    op.execute(
        "UPDATE sources SET family='manual' WHERE type='manual'"
    )
    # newsletter -> default 'narrative_newsletter' deja applique
    # Index pour aggregation rapide par family (dashboard chip)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sources_family ON sources(family)"
    )


def downgrade():
    # SQLite < 3.35 ne supporte pas DROP COLUMN -- non-reversible accepte
    pass
