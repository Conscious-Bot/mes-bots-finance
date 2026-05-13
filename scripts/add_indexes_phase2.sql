-- Phase 2 deep cleaning - SQL indexes for tables identified as missing them
-- in audit 13 May 2026. All idempotent (IF NOT EXISTS).
-- Safe to re-run. Read-only impact on existing data.

CREATE INDEX IF NOT EXISTS idx_bot_events_type_ts
    ON bot_events(event_type, timestamp);

CREATE INDEX IF NOT EXISTS idx_regime_timestamp
    ON regime(timestamp);

CREATE INDEX IF NOT EXISTS idx_feedback_timestamp
    ON feedback(timestamp);

CREATE INDEX IF NOT EXISTS idx_feedback_target
    ON feedback(target_type, target_id);

CREATE INDEX IF NOT EXISTS idx_shadow_decisions_type_created
    ON shadow_decisions(decision_type, created_at);

CREATE INDEX IF NOT EXISTS idx_shadow_decisions_resolved
    ON shadow_decisions(resolved_at);

-- Step 1 nice-to-have (13 May 2026 evening): indexes on growing tables
-- theses queried frequently by handlers (cmd_thesis, cmd_thesis_list, cmd_brief)
-- sources queried by credibility ranking commands (/tiers, /sources_brier)

CREATE INDEX IF NOT EXISTS idx_theses_ticker_status
    ON theses(ticker, status);

CREATE INDEX IF NOT EXISTS idx_theses_status
    ON theses(status);

CREATE INDEX IF NOT EXISTS idx_sources_credibility
    ON sources(credibility DESC);

CREATE INDEX IF NOT EXISTS idx_sources_last_signal
    ON sources(last_signal_at DESC);
