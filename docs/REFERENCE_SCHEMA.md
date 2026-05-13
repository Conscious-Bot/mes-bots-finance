# Database Schema Reference

**Generated**: 13 May 2026
**SQLite mode**: WAL (concurrent reads OK)
**DB path**: `data/bot.db`

Live snapshot of all tables with current row counts and indexes. Auto-regeneratable.

**Total tables**: 28 | **Total indexes**: 32 | **Total rows**: 792


## Core entities

### `sources` (38 rows)

```sql
CREATE TABLE sources (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, type TEXT NOT NULL,
    credibility REAL DEFAULT 0.5,
    n_signals INTEGER DEFAULT 0, n_correct INTEGER DEFAULT 0,
    last_signal_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
, half_life_days REAL, half_life_n_samples INTEGER DEFAULT 0, half_life_computed_at TEXT)
```

### `signals` (66 rows)

```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY, source_id INTEGER REFERENCES sources(id),
    timestamp TEXT NOT NULL, title TEXT, content TEXT, summary TEXT,
    score INTEGER, narratives TEXT, entities TEXT, sentiment TEXT,
    decay_at TEXT, raw_url TEXT
, gmail_id TEXT, user_feedback TEXT, echo_cluster_id INTEGER, signal_type TEXT, materiality_boost REAL DEFAULT 1.0, impact_magnitude REAL, reversibility REAL, time_to_realization TEXT, materiality_breakdown TEXT)
```

**Indexes**: `idx_signals_ts`, `idx_signals_score`, `idx_signals_gmail_id`, `idx_signals_echo_cluster`, `idx_signals_type`

### `theses` (1 rows)

```sql
CREATE TABLE theses (
    id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, opened_at TEXT NOT NULL,
    conviction INTEGER, direction TEXT, horizon TEXT,
    key_drivers TEXT, invalidation_triggers TEXT,
    entry_price REAL, target_price REAL, stop_price REAL,
    price_7d REAL, price_30d REAL, price_90d REAL,
    clv_7d REAL, clv_30d REAL, clv_90d REAL,
    status TEXT DEFAULT 'active', last_reviewed TEXT, notes TEXT
, triggers_profit_take TEXT, target_partial REAL, target_full REAL, last_revisit_at TEXT, triggered_partial_at TEXT, triggered_full_at TEXT, triggered_stop_at TEXT, last_price REAL, last_price_at TEXT, pre_mortem TEXT)
```

### `decisions` (2 rows)

```sql
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    ticker TEXT NOT NULL,
    decision_type TEXT NOT NULL CHECK(decision_type IN ('entry','scale_in','partial_exit','full_exit','override','no_action_flag')),
    direction TEXT,
    confidence_pre INTEGER,
    reasoning TEXT NOT NULL,
    thesis_id INTEGER,
    price_at_decision REAL,
    regime_snapshot TEXT,
    credit_regime_snapshot TEXT,
    materiality_top_signals TEXT,
    resolved_30d_at TEXT,
    price_30d REAL,
    return_30d_pct REAL,
    thesis_relative_30d TEXT,
    resolved_90d_at TEXT,
    price_90d REAL,
    return_90d_pct REAL,
    thesis_relative_90d TEXT,
    mistake_tag_auto TEXT,
    mistake_tag_manual TEXT,
    notes TEXT, bias_tags TEXT,
    FOREIGN KEY (thesis_id) REFERENCES theses(id)
)
```

**Indexes**: `idx_decisions_ticker`, `idx_decisions_created`, `idx_decisions_unresolved_30`, `idx_decisions_unresolved_90`

### `predictions` (46 rows)

```sql
CREATE TABLE predictions (
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
, probability_at_creation REAL, brier_score REAL)
```

**Indexes**: `idx_predictions_target`, `idx_predictions_signal`


## Materiality + scoring

### `conviction_history` (133 rows)

```sql
CREATE TABLE conviction_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    thesis_id INTEGER,
    polarity TEXT,
    signal_type TEXT,
    materiality REAL,
    quality REAL,
    novelty REAL,
    cross_confirmation REAL,
    market_impact REAL,
    regime_relevance REAL,
    is_noise INTEGER,
    why_this_matters TEXT,
    regime_snapshot TEXT,
    credit_regime_snapshot TEXT,
    primary_ticker TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, source_credibility_at_persist REAL,
    FOREIGN KEY (signal_id) REFERENCES signals(id),
    FOREIGN KEY (thesis_id) REFERENCES theses(id)
)
```

**Indexes**: `idx_conviction_signal`, `idx_conviction_created`, `idx_conviction_materiality`

### `signal_embeddings` (47 rows)

```sql
CREATE TABLE signal_embeddings (
    signal_id INTEGER PRIMARY KEY REFERENCES signals(id) ON DELETE CASCADE,
    embedding BLOB NOT NULL,
    model TEXT NOT NULL,
    embedded_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

**Indexes**: `idx_signal_emb_embedded`


## Ops + monitoring

### `llm_calls` (207 rows)

```sql
CREATE TABLE llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    tier TEXT,
    model TEXT,
    task TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cached_tokens INTEGER DEFAULT 0,
    cost_usd REAL,
    elapsed_ms INTEGER,
    error TEXT
)
```

**Indexes**: `idx_llm_calls_created`, `idx_llm_calls_tier`

### `handler_calls` (6 rows)

```sql
CREATE TABLE handler_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    handler_name TEXT NOT NULL,
    user_id INTEGER,
    chat_id INTEGER,
    args_summary TEXT
)
```

**Indexes**: `idx_handler_calls_name`, `idx_handler_calls_timestamp`


## Market data + macro

### `filings_8k_log` (30 rows)

```sql
CREATE TABLE filings_8k_log (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    cik TEXT NOT NULL,
    accession_number TEXT UNIQUE NOT NULL,
    filed_at TEXT NOT NULL,
    items_raw TEXT,
    item_codes TEXT,
    severity TEXT,
    severity_reason TEXT,
    filing_url TEXT,
    notified INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

**Indexes**: `idx_8k_ticker`, `idx_8k_severity`


## Auxiliary

### `watchlist` (0 rows)

```sql
CREATE TABLE watchlist (
    ticker TEXT PRIMARY KEY, added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    sector TEXT, notes TEXT,
    is_position INTEGER DEFAULT 0, position_size REAL, avg_cost REAL
)
```

### `feedback` (0 rows)

```sql
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY, target_type TEXT NOT NULL, target_id INTEGER NOT NULL,
    score INTEGER, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, note TEXT
)
```

### `narratives` (0 rows)

```sql
CREATE TABLE narratives (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, definition TEXT,
    related_tickers TEXT, strength_30d REAL DEFAULT 0, strength_90d REAL DEFAULT 0,
    last_inflection TEXT, state TEXT
)
```

### `debate_transcripts` (1 rows)

```sql
CREATE TABLE debate_transcripts (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    transcript_json TEXT NOT NULL,
    convergence_score REAL,
    verdict TEXT,
    total_cost_usd REAL
)
```

**Indexes**: `idx_debate_ticker`

### `positions` (0 rows)

```sql
CREATE TABLE positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            qty REAL NOT NULL,
            avg_cost REAL NOT NULL,
            realized_pnl REAL DEFAULT 0,
            opened_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            status TEXT DEFAULT 'open'
        )
```

**Indexes**: `idx_positions_ticker_status`, `idx_positions_ticker`, `idx_positions_opened`

### `position_events` (0 rows)

```sql
CREATE TABLE position_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER,
            ticker TEXT NOT NULL,
            event_type TEXT NOT NULL,
            qty REAL NOT NULL,
            price REAL,
            pnl REAL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
```

**Indexes**: `idx_position_events_ticker`


## Other / Phase-specific tables

### `analyses` (5 rows)

```sql
CREATE TABLE analyses (
    id INTEGER PRIMARY KEY, ticker TEXT, type TEXT, timestamp TEXT NOT NULL,
    content TEXT, metadata TEXT
)
```

### `bot_events` (113 rows)

```sql
CREATE TABLE bot_events (
    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
    event_type TEXT, details TEXT
)
```

### `calibration` (0 rows)

```sql
CREATE TABLE calibration (
    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
    confidence_bucket TEXT, n_predictions INTEGER, n_correct INTEGER,
    actual_rate REAL, drift REAL
)
```

### `events` (61 rows)

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,
    ticker TEXT,
    date TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_type, ticker, date) ON CONFLICT IGNORE
)
```

**Indexes**: `idx_events_date`, `idx_events_ticker`

### `insider_buy_clusters_log` (0 rows)

```sql
CREATE TABLE insider_buy_clusters_log (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    window_days INTEGER NOT NULL,
    distinct_buyers INTEGER,
    total_buy_m REAL,
    cluster_strength TEXT,
    top_buyers_json TEXT,
    price_at_detection REAL,
    return_30d REAL,
    return_90d REAL,
    resolved_30d_at TEXT,
    resolved_90d_at TEXT,
    status TEXT DEFAULT 'pending'
)
```

**Indexes**: `idx_ibc_ticker`, `idx_ibc_status`

### `insider_snapshots` (35 rows)

```sql
CREATE TABLE insider_snapshots (
            ticker TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            net_m REAL,
            n_buys INTEGER,
            n_sells INTEGER,
            total_buys_m REAL,
            total_sells_m REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ticker, snapshot_date)
        )
```

**Indexes**: `idx_insider_snap_ticker`

### `overrides` (0 rows)

```sql
CREATE TABLE overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            thesis_id INTEGER,
            level TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
```

### `patterns` (0 rows)

```sql
CREATE TABLE patterns (
    id INTEGER PRIMARY KEY, name TEXT, description TEXT,
    conditions_json TEXT, sample_prediction_ids TEXT,
    n_samples INTEGER, success_rate REAL,
    avg_outcome REAL, avg_drawdown REAL,
    last_updated TEXT, is_active BOOLEAN DEFAULT 1
)
```

### `regime` (0 rows)

```sql
CREATE TABLE regime (
    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
    regime TEXT, vix REAL, dxy REAL, us10y REAL, move REAL,
    credit_spread REAL, dollar_yen REAL,
    rrp REAL, tga REAL, net_liquidity REAL, notes TEXT
)
```

### `risk_checks` (0 rows)

```sql
CREATE TABLE risk_checks (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    proposed_usd REAL,
    verdict TEXT,
    risk_check_json TEXT,
    portfolio_snapshot_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

**Indexes**: `idx_risk_ticker`

### `shadow_decisions` (1 rows)

```sql
CREATE TABLE shadow_decisions (
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
)
```

### `user_decisions` (0 rows)

```sql
CREATE TABLE user_decisions (
    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
    ticker TEXT, action TEXT, bot_recommendation_id INTEGER,
    user_reasoning TEXT, outcome_horizon_days INTEGER,
    outcome_evaluated_at TEXT, outcome_json TEXT
)
```


## Regeneration

Re-run the generation script in Ship 3 of session 13/05/2026, or:

```python
from shared import storage
import sqlite3
conn = sqlite3.connect(storage._DB_PATH)
# query sqlite_master
```
