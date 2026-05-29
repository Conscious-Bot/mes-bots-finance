# Database Schema Reference

**Generated**: 29 May 2026 (auto-regen via `scripts/regen_schema_doc.py`)
**SQLite mode**: WAL (concurrent reads OK)
**DB path**: `data/bot.db`

Live snapshot of all tables with current row counts and indexes. Auto-regeneratable.

**Total tables**: 45 | **Total indexes**: 67 | **Total rows**: 4,386


## Core entities

### `decisions` (4 rows)

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
);
```

**Indexes**: `idx_decisions_created`, `idx_decisions_ticker`, `idx_decisions_unresolved_30`, `idx_decisions_unresolved_90`

### `position_events` (53 rows)

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
        );
```

**Indexes**: `idx_position_events_ticker`

### `positions` (29 rows)

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
        , account TEXT DEFAULT 'TR' NOT NULL);
```

**Indexes**: `idx_positions_opened`, `idx_positions_ticker`, `idx_positions_ticker_status`

### `predictions` (188 rows)

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
, probability_at_creation REAL, brier_score REAL);
```

**Indexes**: `idx_predictions_signal`, `idx_predictions_target`

### `signals` (291 rows)

```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY, source_id INTEGER REFERENCES sources(id),
    timestamp TEXT NOT NULL, title TEXT, content TEXT, summary TEXT,
    score INTEGER, narratives TEXT, entities TEXT, sentiment TEXT,
    decay_at TEXT, raw_url TEXT
, gmail_id TEXT, user_feedback TEXT, echo_cluster_id INTEGER, signal_type TEXT, materiality_boost REAL DEFAULT 1.0, impact_magnitude REAL, reversibility REAL, time_to_realization TEXT, materiality_breakdown TEXT);
```

**Indexes**: `idx_signals_echo_cluster`, `idx_signals_gmail_id`, `idx_signals_score`, `idx_signals_ts`, `idx_signals_type`

### `sources` (68 rows)

```sql
CREATE TABLE sources (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, type TEXT NOT NULL,
    credibility REAL DEFAULT 0.5,
    n_signals INTEGER DEFAULT 0, n_correct INTEGER DEFAULT 0,
    last_signal_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
, half_life_days REAL, half_life_n_samples INTEGER DEFAULT 0, half_life_computed_at TEXT);
```

**Indexes**: `idx_sources_credibility`, `idx_sources_last_signal`

### `theses` (52 rows)

```sql
CREATE TABLE theses (
    id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, opened_at TEXT NOT NULL,
    conviction INTEGER, direction TEXT, horizon TEXT,
    key_drivers TEXT, invalidation_triggers TEXT,
    entry_price REAL, target_price REAL, stop_price REAL,
    price_7d REAL, price_30d REAL, price_90d REAL,
    clv_7d REAL, clv_30d REAL, clv_90d REAL,
    status TEXT DEFAULT 'active', last_reviewed TEXT, notes TEXT
, triggers_profit_take TEXT, target_partial REAL, target_full REAL, last_revisit_at TEXT, triggered_partial_at TEXT, triggered_full_at TEXT, triggered_stop_at TEXT, last_price REAL, last_price_at TEXT, pre_mortem TEXT);
```

**Indexes**: `idx_theses_status`, `idx_theses_ticker_status`


## Intelligence loops

### `analyses` (50 rows)

```sql
CREATE TABLE analyses (
    id INTEGER PRIMARY KEY, ticker TEXT, type TEXT, timestamp TEXT NOT NULL,
    content TEXT, metadata TEXT
);
```

### `calibration` (0 rows)

```sql
CREATE TABLE calibration (
    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
    confidence_bucket TEXT, n_predictions INTEGER, n_correct INTEGER,
    actual_rate REAL, drift REAL
);
```

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
);
```

**Indexes**: `idx_conviction_created`, `idx_conviction_materiality`, `idx_conviction_signal`

### `debate_transcripts` (3 rows)

```sql
CREATE TABLE debate_transcripts (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    transcript_json TEXT NOT NULL,
    convergence_score REAL,
    verdict TEXT,
    total_cost_usd REAL
);
```

**Indexes**: `idx_debate_ticker`

### `debt_composite` (13 rows)

```sql
CREATE TABLE debt_composite (
                timestamp TEXT PRIMARY KEY,
                score REAL NOT NULL,
                phase INTEGER NOT NULL,
                tier_breakdown TEXT
            );
```

### `debt_signals` (107 rows)

```sql
CREATE TABLE debt_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                indicator_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                value REAL,
                phase INTEGER,
                raw_source TEXT,
                UNIQUE(indicator_name, timestamp)
            );
```

**Indexes**: `idx_debt_signals_ind_ts`

### `events` (64 rows)

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,
    ticker TEXT,
    date TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_type, ticker, date) ON CONFLICT IGNORE
);
```

**Indexes**: `idx_events_date`, `idx_events_ticker`

### `filings_8k_log` (42 rows)

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
);
```

**Indexes**: `idx_8k_severity`, `idx_8k_ticker`

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
);
```

**Indexes**: `idx_ibc_status`, `idx_ibc_ticker`

### `insider_snapshots` (332 rows)

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
        );
```

**Indexes**: `idx_insider_snap_ticker`

### `narratives` (0 rows)

```sql
CREATE TABLE narratives (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, definition TEXT,
    related_tickers TEXT, strength_30d REAL DEFAULT 0, strength_90d REAL DEFAULT 0,
    last_inflection TEXT, state TEXT
);
```

### `patterns` (0 rows)

```sql
CREATE TABLE patterns (
    id INTEGER PRIMARY KEY, name TEXT, description TEXT,
    conditions_json TEXT, sample_prediction_ids TEXT,
    n_samples INTEGER, success_rate REAL,
    avg_outcome REAL, avg_drawdown REAL,
    last_updated TEXT, is_active BOOLEAN DEFAULT 1
);
```

### `regime` (0 rows)

```sql
CREATE TABLE regime (
    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
    regime TEXT, vix REAL, dxy REAL, us10y REAL, move REAL,
    credit_spread REAL, dollar_yen REAL,
    rrp REAL, tga REAL, net_liquidity REAL, notes TEXT
);
```

**Indexes**: `idx_regime_timestamp`

### `risk_checks` (10 rows)

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
);
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
);
```

**Indexes**: `idx_shadow_decisions_resolved`, `idx_shadow_decisions_type_created`

### `signal_embeddings` (303 rows)

```sql
CREATE TABLE signal_embeddings (
    signal_id INTEGER PRIMARY KEY REFERENCES signals(id) ON DELETE CASCADE,
    embedding BLOB NOT NULL,
    model TEXT NOT NULL,
    embedded_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes**: `idx_signal_emb_embedded`


## User interface

### `feedback` (0 rows)

```sql
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY, target_type TEXT NOT NULL, target_id INTEGER NOT NULL,
    score INTEGER, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, note TEXT
);
```

**Indexes**: `idx_feedback_target`, `idx_feedback_timestamp`

### `overrides` (0 rows)

```sql
CREATE TABLE overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            thesis_id INTEGER,
            level TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
```

### `portfolio_targets` (36 rows)

```sql
CREATE TABLE portfolio_targets (
	id INTEGER NOT NULL, 
	ticker TEXT NOT NULL, 
	account TEXT NOT NULL, 
	bucket TEXT, 
	target_eur FLOAT NOT NULL, 
	target_weight_pct FLOAT, 
	narrative TEXT, 
	priority TEXT, 
	status TEXT DEFAULT 'planned' NOT NULL, 
	phase_week INTEGER, 
	active_from TEXT DEFAULT (datetime('now')) NOT NULL, 
	active_to TEXT, 
	source_doc TEXT, 
	thesis_id INTEGER, 
	created_at TEXT DEFAULT (datetime('now')) NOT NULL, 
	notes TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(thesis_id) REFERENCES theses (id)
);
```

**Indexes**: `idx_targets_account`, `idx_targets_status`, `idx_targets_ticker`

### `ticker_names` (306 rows)

```sql
CREATE TABLE ticker_names (
    ticker TEXT PRIMARY KEY,
    short_name TEXT,
    long_name TEXT,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### `user_decisions` (0 rows)

```sql
CREATE TABLE user_decisions (
    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
    ticker TEXT, action TEXT, bot_recommendation_id INTEGER,
    user_reasoning TEXT, outcome_horizon_days INTEGER,
    outcome_evaluated_at TEXT, outcome_json TEXT
);
```

### `watchlist` (0 rows)

```sql
CREATE TABLE watchlist (
    ticker TEXT PRIMARY KEY, added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    sector TEXT, notes TEXT,
    is_position INTEGER DEFAULT 0, position_size REAL, avg_cost REAL
);
```


## Operations

### `alembic_version` (1 rows)

```sql
CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL, 
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
```

### `bot_events` (331 rows)

```sql
CREATE TABLE bot_events (
    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
    event_type TEXT, details TEXT
);
```

**Indexes**: `idx_bot_events_type_ts`

### `handler_calls` (525 rows)

```sql
CREATE TABLE handler_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    handler_name TEXT NOT NULL,
    user_id INTEGER,
    chat_id INTEGER,
    args_summary TEXT
);
```

**Indexes**: `idx_handler_calls_name`, `idx_handler_calls_timestamp`

### `llm_calls` (1,193 rows)

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
);
```

**Indexes**: `idx_llm_calls_created`, `idx_llm_calls_tier`


## Uncategorized

### `bot_conceptions` (42 rows)

```sql
CREATE TABLE bot_conceptions (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT (datetime('now')), kind TEXT NOT NULL, target_key TEXT NOT NULL, conception_text TEXT NOT NULL, conviction INTEGER NOT NULL, valence REAL, sources_json TEXT, n_signals_used INTEGER, model_used TEXT, input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL, elapsed_ms INTEGER);
```

**Indexes**: `idx_conc_created`, `idx_conc_kind_target`

### `bot_copilot_interventions` (0 rows)

```sql
CREATE TABLE bot_copilot_interventions (
	id INTEGER NOT NULL, 
	ticker TEXT NOT NULL, 
	decision_type TEXT NOT NULL, 
	intent_reasoning TEXT, 
	intent_price FLOAT, 
	intent_qty FLOAT, 
	thesis_id INTEGER, 
	decision_id INTEGER, 
	verdict TEXT, 
	pressure_score INTEGER, 
	ancrage TEXT, 
	brief TEXT, 
	biases_active_json TEXT, 
	full_response_json TEXT, 
	model_used TEXT, 
	input_tokens INTEGER, 
	output_tokens INTEGER, 
	cost_usd FLOAT, 
	elapsed_ms INTEGER, 
	created_at TEXT DEFAULT (datetime('now')) NOT NULL, 
	resolved_30d_at TEXT, 
	return_30d_pct FLOAT, 
	outcome_label TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(thesis_id) REFERENCES theses (id), 
	FOREIGN KEY(decision_id) REFERENCES decisions (id)
);
```

**Indexes**: `idx_copilot_created`, `idx_copilot_decision`, `idx_copilot_ticker`, `idx_copilot_unresolved`

### `bot_preferences` (6 rows)

```sql
CREATE TABLE bot_preferences (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT (datetime('now')), kind TEXT NOT NULL, snapshot_date TEXT NOT NULL, metric_json TEXT NOT NULL, insight_text TEXT, confidence INTEGER NOT NULL DEFAULT 0, n_samples INTEGER, provenance TEXT NOT NULL DEFAULT 'deterministic', model_used TEXT, cost_usd REAL);
```

**Indexes**: `idx_pref_date`, `idx_pref_kind`

### `chat_extracted_signals` (3 rows)

```sql
CREATE TABLE chat_extracted_signals (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT (datetime('now')), chat_message_id INTEGER, kind TEXT NOT NULL, ticker TEXT, sector TEXT, theme TEXT, valence REAL, confidence REAL, evidence_quote TEXT, note TEXT, model_used TEXT, cost_usd REAL);
```

**Indexes**: `idx_ces_created`, `idx_ces_kind`, `idx_ces_ticker`

### `chat_messages` (4 rows)

```sql
CREATE TABLE chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT (datetime('now')), session_id TEXT, surface TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, model_used TEXT, input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL, latency_ms INTEGER, error TEXT);
```

**Indexes**: `idx_chat_created`, `idx_chat_session`

### `portfolio_grades` (5 rows)

```sql
CREATE TABLE portfolio_grades (id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_at TEXT NOT NULL DEFAULT (datetime('now')), snapshot_date TEXT NOT NULL, overall_score INTEGER NOT NULL, overall_grade TEXT NOT NULL, dimensions_json TEXT NOT NULL, total_capital_eur REAL, n_positions INTEGER, n_theses_active INTEGER, computation_version TEXT NOT NULL DEFAULT 'sprint5_deterministic', notes TEXT);
```

**Indexes**: `idx_grade_date`, `idx_grade_snapshot_at`

### `portfolio_narrative_clusters` (1 rows)

```sql
CREATE TABLE portfolio_narrative_clusters (id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_at TEXT NOT NULL DEFAULT (datetime('now')), snapshot_date TEXT NOT NULL, clusters_json TEXT NOT NULL, edges_json TEXT NOT NULL, model_used TEXT, input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL, elapsed_ms INTEGER, notes TEXT);
```

**Indexes**: `idx_narrative_cluster_date`

### `portfolio_snapshots` (5 rows)

```sql
CREATE TABLE portfolio_snapshots (snapshot_date TEXT PRIMARY KEY, captured_at TEXT NOT NULL, total_value_eur REAL NOT NULL, total_cost_eur REAL NOT NULL, pnl_eur REAL NOT NULL, pnl_pct REAL NOT NULL, n_positions INTEGER NOT NULL, n_priced INTEGER NOT NULL, hwm_value_eur REAL, drawdown_pct REAL, detail_json TEXT);
```

### `predictions_bak_probfix` (155 rows)

```sql
CREATE TABLE predictions_bak_probfix(
  id INT,
  signal_id INT,
  ticker TEXT,
  direction TEXT,
  horizon_days INT,
  baseline_price REAL,
  baseline_date TEXT,
  target_date TEXT,
  resolved_at TEXT,
  final_price REAL,
  return_pct REAL,
  outcome TEXT,
  credibility_delta REAL,
  created_at TEXT,
  probability_at_creation REAL,
  brier_score REAL
);
```

### `ticker_axes` (28 rows)

```sql
CREATE TABLE ticker_axes (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT (datetime('now')), ticker TEXT NOT NULL, demand_driver TEXT NOT NULL, value_chain_stage TEXT NOT NULL, moat_source TEXT NOT NULL, macro_factor TEXT NOT NULL, alt_drivers_json TEXT, confidence INTEGER, rationale TEXT, model_used TEXT, input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL);
```

**Indexes**: `idx_axes_macro`, `idx_axes_ticker`

### `ticker_meta` (1 rows)

```sql
CREATE TABLE ticker_meta (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT (datetime('now')), ticker TEXT NOT NULL, fade_rate_score INTEGER NOT NULL, moat_durability_years INTEGER, upstream_critical_deps_json TEXT, valo_what_priced_in TEXT, valo_pe_or_proxy REAL, valo_above_bull_case BOOLEAN, rationale TEXT, model_used TEXT, input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL);
```

**Indexes**: `idx_meta_fade`, `idx_meta_ticker`

### `user_profile` (1 rows)

```sql
CREATE TABLE user_profile (
	id INTEGER NOT NULL, 
	refreshed_at TEXT DEFAULT (datetime('now')) NOT NULL, 
	profile_json TEXT NOT NULL, 
	confidence_score INTEGER, 
	n_decisions_used INTEGER, 
	n_theses_used INTEGER, 
	n_predictions_resolved_used INTEGER, 
	n_signals_window INTEGER, 
	data_window_start TEXT, 
	data_window_end TEXT, 
	model_used TEXT, 
	input_tokens INTEGER, 
	output_tokens INTEGER, 
	cost_usd FLOAT, 
	elapsed_ms INTEGER, 
	notes TEXT, 
	PRIMARY KEY (id)
);
```

**Indexes**: `idx_user_profile_refreshed`


---

## Regeneration

```bash
python scripts/regen_schema_doc.py
```
