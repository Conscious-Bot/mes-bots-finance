"""stress_gate_alerts : journal append-only des evaluations stress-test.

Spec QUALITY_BAR Axe 4 1er geste : "cabler le stress-test existant a un
seuil + une alerte (la machinerie existe, l'alerte non)".

Pattern monitor canonique : docs/templates/monitor_pattern.md.

key = scenario_name (ex "AI capex -30%").
status enum = ok / warn / breach.
metric = drawdown_pct (float, negatif).
transition actionable = (* -> breach) -> notify Telegram.

Pas de wire bias_events : stress-gate = etat structurel du book
(concentration excessive), pas comportement-utilisateur. Distinct des
canaux fomo_greed (kill_criteria / over_cap) qui eux mecanisent le
biais cognitif.

Revision ID: 0037
Revises: 0036
Create Date: 2026-06-07
"""

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE stress_gate_alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            scenario_name   TEXT NOT NULL,
            status          TEXT NOT NULL CHECK(status IN ('ok', 'warn', 'breach')),
            drawdown_pct    REAL NOT NULL,
            warn_pct        REAL NOT NULL,
            breach_pct      REAL NOT NULL,
            notified        INTEGER NOT NULL DEFAULT 0,
            transition      TEXT CHECK(transition IN (
                'enter_breach', 'enter_warn', 'recover_ok',
                'recover_warn', 'no_change', NULL
            ))
        )
    """)
    op.execute("""
        CREATE INDEX idx_stress_gate_scenario
        ON stress_gate_alerts(scenario_name, created_at)
    """)
    op.execute("""
        CREATE INDEX idx_stress_gate_status
        ON stress_gate_alerts(status, created_at)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS stress_gate_alerts")
