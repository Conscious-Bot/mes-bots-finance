"""Init SQLite DB + bot_state.json. À lancer UNE fois."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
DB_PATH = DATA / "bot.db"
STATE_PATH = DATA / "bot_state.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, type TEXT NOT NULL,
    credibility REAL DEFAULT 0.5,
    n_signals INTEGER DEFAULT 0, n_correct INTEGER DEFAULT 0,
    last_signal_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY, source_id INTEGER REFERENCES sources(id),
    timestamp TEXT NOT NULL, title TEXT, content TEXT, summary TEXT,
    score INTEGER, narratives TEXT, entities TEXT, sentiment TEXT,
    decay_at TEXT, raw_url TEXT,
    gmail_id TEXT, user_feedback TEXT
);
CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_score ON signals(score DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_gmail_id ON signals(gmail_id);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY, ticker TEXT, type TEXT, timestamp TEXT NOT NULL,
    content TEXT, metadata TEXT
);
CREATE TABLE IF NOT EXISTS theses (
    id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, opened_at TEXT NOT NULL,
    conviction INTEGER, direction TEXT, horizon TEXT,
    key_drivers TEXT, invalidation_triggers TEXT,
    entry_price REAL, target_price REAL, stop_price REAL,
    price_7d REAL, price_30d REAL, price_90d REAL,
    clv_7d REAL, clv_30d REAL, clv_90d REAL,
    status TEXT DEFAULT 'active', last_reviewed TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS narratives (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, definition TEXT,
    related_tickers TEXT, strength_30d REAL DEFAULT 0, strength_90d REAL DEFAULT 0,
    last_inflection TEXT, state TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,
    ticker TEXT,
    date TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_type, ticker, date) ON CONFLICT IGNORE
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);
CREATE INDEX IF NOT EXISTS idx_events_ticker ON events(ticker);

CREATE TABLE IF NOT EXISTS regime (
    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
    regime TEXT, vix REAL, dxy REAL, us10y REAL, move REAL,
    credit_spread REAL, dollar_yen REAL,
    rrp REAL, tga REAL, net_liquidity REAL, notes TEXT
);
CREATE TABLE IF NOT EXISTS predictions (
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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_predictions_target ON predictions(target_date);
CREATE INDEX IF NOT EXISTS idx_predictions_signal ON predictions(signal_id);

CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY, name TEXT, description TEXT,
    conditions_json TEXT, sample_prediction_ids TEXT,
    n_samples INTEGER, success_rate REAL,
    avg_outcome REAL, avg_drawdown REAL,
    last_updated TEXT, is_active BOOLEAN DEFAULT 1
);
CREATE TABLE IF NOT EXISTS calibration (
    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
    confidence_bucket TEXT, n_predictions INTEGER, n_correct INTEGER,
    actual_rate REAL, drift REAL
);
CREATE TABLE IF NOT EXISTS user_decisions (
    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
    ticker TEXT, action TEXT, bot_recommendation_id INTEGER,
    user_reasoning TEXT, outcome_horizon_days INTEGER,
    outcome_evaluated_at TEXT, outcome_json TEXT
);
CREATE TABLE IF NOT EXISTS shadow_decisions (
    id INTEGER PRIMARY KEY,
    decision_type TEXT NOT NULL,
    decision_id TEXT,
    input_data TEXT,
    variants TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    main_outcome TEXT,
    aggressive_outcome TEXT,
    conservative_outcome TEXT,
    resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS watchlist (
    ticker TEXT PRIMARY KEY, added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    sector TEXT, notes TEXT,
    is_position INTEGER DEFAULT 0, position_size REAL, avg_cost REAL
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY, target_type TEXT NOT NULL, target_id INTEGER NOT NULL,
    score INTEGER, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, note TEXT
);
CREATE TABLE IF NOT EXISTS bot_events (
    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
    event_type TEXT, details TEXT
);
"""


def main():
    DATA.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    n_tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    conn.close()
    print(f"OK DB initialisée : {DB_PATH} ({n_tables} tables)")

    if not STATE_PATH.exists():
        state = {
            "peak_capital": 10000.0,
            "current_capital": 10000.0,
            "drawdown_pct": 0.0,
            "last_alert_drawdown_pct": 0.0,
            "last_balance_alert_ts": None,
            "last_heartbeat_ts": datetime.now().isoformat(),
            "bot_start_ts": datetime.now().isoformat(),
            "session_id": "session_1",
            "paper_only": True,
            "active_theses_count": 0,
            "predictions_pending_resolution": 0,
        }
        STATE_PATH.write_text(json.dumps(state, indent=2))
        print(f"OK bot_state initialisé : {STATE_PATH}")


if __name__ == "__main__":
    main()
