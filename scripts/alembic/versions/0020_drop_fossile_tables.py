"""Drop 4 tables fossiles identifiees audit 30/05/2026.

Audit phase 1.B revele tables vraiment mortes (0 INSERT callers OU backup
d'une migration ancienne) :

1. predictions_bak_probfix : 155 rows backup migration ADR 007 (probability
   fix 2026-05-23). Plus utilisee, juste pollue le schema.
2. calibration : 0 rows, 0 writers Python. Concept Path 6 jamais cable
   (le money-shot vient post-10/06 via une nouvelle table dediee).
3. regime : 0 rows, 0 writers. (Note : regime detection vit dans
   intelligence/regime.py mais en memoire / format different, pas via cette
   table fossile).
4. user_decisions : 0 rows, 0 writers. Confusion possible avec decisions
   (= la table reelle). Cette user_decisions est fossile.

Note : `patterns` table (0 rows) NON droppee -- decision_copilot.py et
scripts/copilot_test.py l'interrogent via `_fetch_bias_patterns()`. Code
dead-path en pratique (table vide) mais SELECT doit pas crasher. La table
sera peuplee si la feature bias-patterns est cablee plus tard.

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-30
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS predictions_bak_probfix")
    op.execute("DROP TABLE IF EXISTS calibration")
    op.execute("DROP TABLE IF EXISTS regime")
    op.execute("DROP TABLE IF EXISTS user_decisions")


def downgrade():
    # Reverse : recrée les schémas minimal (no data recovery).
    # Ces tables sont fossiles, downgrade rare. Schémas approximatifs.
    op.execute("""
    CREATE TABLE predictions_bak_probfix (
        id INTEGER PRIMARY KEY,
        ticker TEXT,
        created_at TEXT
    )""")
    op.execute("""
    CREATE TABLE calibration (
        id INTEGER PRIMARY KEY,
        ticker TEXT,
        snapshot_date TEXT
    )""")
    op.execute("""
    CREATE TABLE regime (
        id INTEGER PRIMARY KEY,
        snapshot_date TEXT,
        regime TEXT
    )""")
    op.execute("""
    CREATE TABLE user_decisions (
        id INTEGER PRIMARY KEY,
        ticker TEXT,
        decided_at TEXT
    )""")
