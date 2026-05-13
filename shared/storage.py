"""SQLite accessors. Toute la mémoire passe par ici."""

import json
import sqlite3
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "bot.db"
STATE_PATH = ROOT / "data" / "bot_state.json"


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict):
    STATE_PATH.write_text(json.dumps(state, indent=2))


def update_state(**kwargs):
    s = load_state()
    s.update(kwargs)
    s["last_heartbeat_ts"] = datetime.now().isoformat()
    save_state(s)


def log_event(event_type: str, details=None):
    with db() as conn:
        conn.execute(
            "INSERT INTO bot_events(timestamp, event_type, details) VALUES(?,?,?)",
            (datetime.now().isoformat(), event_type, json.dumps(details) if isinstance(details, dict) else details),
        )


def active_signals(min_score: int = 5, since_hours: int = 24) -> list[dict]:
    since = (datetime.now() - timedelta(hours=since_hours)).isoformat()
    now = datetime.now().isoformat()
    with db() as conn:
        rows = conn.execute(
            """
            SELECT s.*, src.name as source_name, src.credibility
            FROM signals s JOIN sources src ON s.source_id = src.id
            WHERE s.decay_at > ? AND s.timestamp > ? AND s.score >= ?
            ORDER BY (s.score * src.credibility) DESC
        """,
            (now, since, min_score),
        ).fetchall()
        return [dict(r) for r in rows]


def add_thesis(
    ticker, conviction, direction, horizon, drivers, invalidation, entry_price=None, target=None, stop=None
) -> int:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO theses(ticker, opened_at, conviction, direction, horizon,
                              key_drivers, invalidation_triggers,
                              entry_price, target_price, stop_price)
            VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
            (
                ticker,
                datetime.now().isoformat(),
                conviction,
                direction,
                horizon,
                drivers,
                invalidation,
                entry_price,
                target,
                stop,
            ),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def active_theses() -> list[dict]:
    with db() as conn:
        return [
            dict(r)
            for r in conn.execute("SELECT * FROM theses WHERE status = 'active' ORDER BY opened_at DESC").fetchall()
        ]


def thesis_by_id(thesis_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM theses WHERE id = ?", (thesis_id,)).fetchone()
        return dict(row) if row else None


def update_thesis_status(thesis_id: int, status: str, notes: str | None = None):
    with db() as conn:
        conn.execute(
            "UPDATE theses SET status = ?, last_reviewed = ?, notes = COALESCE(?, notes) WHERE id = ?",
            (status, datetime.now().isoformat(), notes, thesis_id),
        )


def log_prediction(source_type, source_id, ticker, claim, horizon_days, confidence) -> int:
    expires_at = (datetime.now() + timedelta(days=horizon_days)).isoformat()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO predictions(timestamp, source_type, source_id, ticker,
                                    claim_json, horizon_days, expires_at, confidence)
            VALUES(?,?,?,?,?,?,?,?)
        """,
            (
                datetime.now().isoformat(),
                source_type,
                source_id,
                ticker,
                json.dumps(claim),
                horizon_days,
                expires_at,
                confidence,
            ),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def expired_unresolved_predictions() -> list[dict]:
    now = datetime.now().isoformat()
    with db() as conn:
        return [
            dict(r)
            for r in conn.execute(
                """
            SELECT * FROM predictions
            WHERE expires_at < ? AND outcome_evaluated_at IS NULL
        """,
                (now,),
            ).fetchall()
        ]


def record_outcome(prediction_id: int, outcome: dict, correct: bool):
    with db() as conn:
        conn.execute(
            """
            UPDATE predictions
            SET outcome_evaluated_at = ?, actual_outcome_json = ?, correct = ?
            WHERE id = ?
        """,
            (datetime.now().isoformat(), json.dumps(outcome), correct, prediction_id),
        )


def add_to_watchlist(ticker, sector=None, notes=None):
    with db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO watchlist(ticker, sector, notes) VALUES(?,?,?)
        """,
            (ticker, sector, notes),
        )


def get_watchlist() -> list[str]:
    with db() as conn:
        return [r["ticker"] for r in conn.execute("SELECT ticker FROM watchlist").fetchall()]


def add_feedback(target_type, target_id, score, note=None):
    with db() as conn:
        conn.execute(
            "INSERT INTO feedback(target_type, target_id, score, note) VALUES(?,?,?,?)",
            (target_type, target_id, score, note),
        )


def seed_narratives(narratives_config: list[dict]):
    with db() as conn:
        for n in narratives_config:
            conn.execute(
                "INSERT OR IGNORE INTO narratives(name, definition) VALUES(?,?)", (n["name"], n.get("definition", ""))
            )


# === Phase 2 : Gmail ingestion helpers ===

import sqlite3 as _sqlite3
from pathlib import Path as _Path

_DB_PATH = _Path("data/bot.db")


def signal_exists_by_gmail_id(gmail_id):
    """Check if a Gmail message has already been ingested."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        row = conn.execute("SELECT 1 FROM signals WHERE gmail_id = ? LIMIT 1", (gmail_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def get_or_create_source(sender):
    """Resolve sender string to source_id. Creates a new source if unknown."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        row = conn.execute("SELECT id FROM sources WHERE name = ?", (sender,)).fetchone()
        if row:
            return row[0]
        cur = conn.execute(
            "INSERT INTO sources (name, type, credibility, n_signals) VALUES (?, ?, ?, ?)",
            (sender, "newsletter", 0.5, 0),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_raw_signal(source_id, gmail_id, timestamp, subject, content):
    """Insert a raw email-derived signal. Returns new signal_id, or None on welcome/duplicate.

    Atomicity invariant: n_signals counter and last_signal_at are updated ONLY if INSERT succeeds.
    Handles UNIQUE constraint on gmail_id gracefully (duplicate emails return None).
    """
    if _is_welcome_signal(subject, content):
        return None
    conn = _sqlite3.connect(_DB_PATH)
    try:
        try:
            cur = conn.execute(
                "INSERT INTO signals (source_id, gmail_id, timestamp, title, content) VALUES (?, ?, ?, ?, ?)",
                (source_id, gmail_id, timestamp, subject, content),
            )
        except _sqlite3.IntegrityError:
            # Duplicate gmail_id — already ingested previously
            return None
        # INSERT succeeded → safe to bump counter + last_signal_at atomically
        conn.execute(
            "UPDATE sources SET n_signals = n_signals + 1, last_signal_at = ? WHERE id = ?", (timestamp, source_id)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# === Phase 2 : Thesis tracker helpers ===

import json as _t_json
from datetime import UTC, datetime as _t_dt, timedelta as _t_td


def _parse_thesis_row(row):
    """Convert sqlite Row to dict with JSON fields parsed."""
    d = dict(row)
    for fld in ("key_drivers", "invalidation_triggers", "triggers_profit_take"):
        if d.get(fld):
            with suppress(TypeError, ValueError):
                d[fld] = _t_json.loads(d[fld])
    return d


def insert_thesis(
    ticker,
    direction,
    horizon,
    conviction,
    key_drivers,
    invalidation_triggers,
    entry_price,
    target_price=None,
    target_partial=None,
    target_full=None,
    triggers_profit_take=None,
    stop_price=None,
    notes=None,
):
    """Insert a new thesis. Returns thesis_id."""
    now = _t_dt.now(UTC).isoformat()

    def _to_list(v):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return [v]

    conn = _sqlite3.connect(_DB_PATH)
    try:
        cur = conn.execute(
            """INSERT INTO theses
            (ticker, direction, horizon, conviction,
             key_drivers, invalidation_triggers,
             entry_price, target_price, target_partial, target_full,
             triggers_profit_take, stop_price, notes,
             opened_at, status, last_reviewed, last_revisit_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
            (
                ticker.upper(),
                direction,
                horizon,
                int(conviction),
                _t_json.dumps(_to_list(key_drivers)),
                _t_json.dumps(_to_list(invalidation_triggers)),
                float(entry_price),
                float(target_price) if target_price is not None else None,
                float(target_partial) if target_partial is not None else None,
                float(target_full) if target_full is not None else None,
                _t_json.dumps(_to_list(triggers_profit_take)),
                float(stop_price) if stop_price is not None else None,
                notes,
                now,
                now,
                now,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_theses(status="active"):
    """List theses by status. Returns list of dicts (JSON parsed)."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM theses WHERE status = ? ORDER BY opened_at DESC", (status,)).fetchall()
        return [_parse_thesis_row(r) for r in rows]
    finally:
        conn.close()


def get_thesis(thesis_id):
    """Get a thesis by id. Returns dict or None."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM theses WHERE id = ?", (thesis_id,)).fetchone()
        return _parse_thesis_row(row) if row else None
    finally:
        conn.close()


def get_thesis_by_ticker(ticker, status="active"):
    """Get the active thesis for a ticker. Returns dict or None."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM theses WHERE ticker = ? AND status = ? LIMIT 1", (ticker.upper(), status)
        ).fetchone()
        return _parse_thesis_row(row) if row else None
    finally:
        conn.close()


def update_thesis_revisit(thesis_id):
    """Mark thesis as revisited now."""
    now = _t_dt.now(UTC).isoformat()
    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute("UPDATE theses SET last_revisit_at = ? WHERE id = ?", (now, thesis_id))
        conn.commit()
    finally:
        conn.close()


def append_thesis_note(thesis_id, note):
    """Append a timestamped note to a thesis."""
    now = _t_dt.now(UTC).isoformat()
    conn = _sqlite3.connect(_DB_PATH)
    try:
        row = conn.execute("SELECT notes FROM theses WHERE id = ?", (thesis_id,)).fetchone()
        existing = (row[0] if row and row[0] else "") or ""
        new_notes = existing + ("\n" if existing else "") + f"[{now}] {note}"
        conn.execute("UPDATE theses SET notes = ? WHERE id = ?", (new_notes, thesis_id))
        conn.commit()
    finally:
        conn.close()


def close_thesis(thesis_id, status, exit_price=None, reason=None):
    """Close a thesis. status must be 'invalidated' | 'realized' | 'stale'."""
    if status not in ("invalidated", "realized", "stale"):
        raise ValueError(f"Invalid close status: {status}")
    now = _t_dt.now(UTC).isoformat()
    parts = [status.upper() + ":"]
    if exit_price is not None:
        parts.append(f"exit_price={exit_price}")
    if reason:
        parts.append(f"reason={reason}")
    note_line = " ".join(parts)
    conn = _sqlite3.connect(_DB_PATH)
    try:
        row = conn.execute("SELECT notes FROM theses WHERE id = ?", (thesis_id,)).fetchone()
        existing = (row[0] if row and row[0] else "") or ""
        new_notes = existing + ("\n" if existing else "") + f"[{now}] {note_line}"
        conn.execute("UPDATE theses SET status = ?, notes = ? WHERE id = ?", (status, new_notes, thesis_id))
        conn.commit()
    finally:
        conn.close()


def get_theses_due_for_revisit(days_threshold=30):
    """Return active theses where last_revisit_at older than threshold."""
    cutoff = (_t_dt.now(UTC) - _t_td(days=days_threshold)).isoformat()
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT * FROM theses
               WHERE status = 'active'
                 AND (last_revisit_at IS NULL OR last_revisit_at < ?)
               ORDER BY opened_at""",
            (cutoff,),
        ).fetchall()
        return [_parse_thesis_row(r) for r in rows]
    finally:
        conn.close()


# === Phase 2 Chunk 3 : Digest helpers ===


def get_unprocessed_signals(limit=20):
    """Get raw signals (emails) not yet scored. Returns list of dicts with source_name."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT s.*, src.name as source_name
               FROM signals s
               JOIN sources src ON s.source_id = src.id
               WHERE s.score IS NULL AND s.gmail_id IS NOT NULL
               ORDER BY s.timestamp ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_signal_insights(signal_id, score, sentiment, tickers, narratives, summary):
    """Update a signal with LLM-extracted insights."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute(
            """UPDATE signals
               SET score = ?, sentiment = ?, entities = ?, narratives = ?, summary = ?
               WHERE id = ?""",
            (
                int(score),
                sentiment,
                _t_json.dumps(tickers if isinstance(tickers, list) else []),
                _t_json.dumps(narratives if isinstance(narratives, list) else []),
                summary,
                signal_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# === Phase 2 Chunk 4 : Feedback + credibility helpers ===


def set_signal_feedback(signal_id, rating):
    """Set user feedback on a signal. rating: 'up' | 'down'."""
    if rating not in ("up", "down"):
        raise ValueError(f"rating must be 'up' or 'down', got {rating}")
    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute("UPDATE signals SET user_feedback = ? WHERE id = ?", (rating, signal_id))
        conn.commit()
    finally:
        conn.close()


def get_signal(signal_id):
    """Get a signal with source info joined."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        row = conn.execute(
            """SELECT s.*, src.name as source_name, src.credibility as source_credibility
               FROM signals s JOIN sources src ON s.source_id = src.id
               WHERE s.id = ?""",
            (signal_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_source_credibility(source_id, delta):
    """Adjust credibility by delta, clamped to [0.05, 1.0]."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        row = conn.execute("SELECT credibility FROM sources WHERE id = ?", (source_id,)).fetchone()
        if not row:
            return None
        current = row[0] if row[0] is not None else 0.5
        new = max(0.05, min(1.0, current + delta))
        conn.execute("UPDATE sources SET credibility = ? WHERE id = ?", (new, source_id))
        conn.commit()
        return new
    finally:
        conn.close()


def get_top_sources(n=10, min_signals=3):
    """Get top sources by credibility."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT name, credibility, n_signals FROM sources
               WHERE n_signals >= ?
               ORDER BY credibility DESC LIMIT ?""",
            (min_signals, n),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_worst_sources(n=5, min_signals=5):
    """Get worst sources by credibility (candidates to drop)."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT name, credibility, n_signals FROM sources
               WHERE n_signals >= ?
               ORDER BY credibility ASC LIMIT ?""",
            (min_signals, n),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_recent_processed_signals(hours=72, limit=20):
    """Fetch recently processed signals (score IS NOT NULL), joined with source.
    Parses entities/narratives JSON, aliases entities -> tickers for digest compat.
    """
    import json as _json

    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT s.id, s.source_id, s.timestamp, s.title, s.summary,
                      s.score, s.narratives, s.entities, s.sentiment, s.user_feedback,
                      src.name as source_name, src.credibility as source_credibility
               FROM signals s JOIN sources src ON s.source_id = src.id
               WHERE s.score IS NOT NULL
                 AND s.timestamp >= datetime('now', ?)
               ORDER BY s.timestamp DESC LIMIT ?""",
            (f"-{hours} hours", limit),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            for jkey in ("entities", "narratives"):
                val = d.get(jkey)
                if val:
                    with suppress(Exception):
                        d[jkey] = _json.loads(val)
                else:
                    d[jkey] = []
            d["tickers"] = d.get("entities") or []
            result.append(d)
        return result
    finally:
        conn.close()


def insert_shadow_decision(decision_type, decision_id, input_data, variants):
    """Persist a shadow decision for later outcome resolution."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        cur = conn.execute(
            "INSERT INTO shadow_decisions (decision_type, decision_id, input_data, variants) VALUES (?, ?, ?, ?)",
            (decision_type, decision_id, input_data, variants),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_unresolved_shadow_decisions(limit=100):
    """Fetch shadow decisions not yet resolved."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM shadow_decisions WHERE resolved_at IS NULL ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def insert_prediction(signal_id, ticker, direction, horizon_days, baseline_price, baseline_date, target_date):
    """Phase A1 — Brier: snapshots source.credibility as probability_at_creation."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        prob = None
        try:
            row = conn.execute(
                "SELECT s.credibility FROM signals sig JOIN sources s ON sig.source_id = s.id WHERE sig.id = ?",
                (signal_id,),
            ).fetchone()
            if row:
                prob = row[0]
        except Exception as _e:
            import logging as _logging

            _logging.getLogger(__name__).warning(f"insert_prediction silent failure: {_e}")
        cur = conn.execute(
            "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, baseline_price, "
            "baseline_date, target_date, probability_at_creation) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (signal_id, ticker, direction, horizon_days, baseline_price, baseline_date, target_date, prob),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_due_predictions(limit=50):
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM predictions WHERE target_date <= date('now') AND resolved_at IS NULL ORDER BY target_date ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def resolve_prediction_row(prediction_id, final_price, return_pct, outcome, credibility_delta, brier_score=None):
    """Phase A1 — Brier: stores brier_score at resolution time."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute(
            "UPDATE predictions SET resolved_at=CURRENT_TIMESTAMP, final_price=?, return_pct=?, "
            "outcome=?, credibility_delta=?, brier_score=? WHERE id=?",
            (final_price, return_pct, outcome, credibility_delta, brier_score, prediction_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_predictions(limit=20):
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT p.*, src.name as source_name FROM predictions p LEFT JOIN signals s ON p.signal_id = s.id LEFT JOIN sources src ON s.source_id = src.id ORDER BY p.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def insert_event(event_type, date, ticker=None, description=None):
    """Insert event, idempotent via UNIQUE constraint."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO events (event_type, ticker, date, description) VALUES (?, ?, ?, ?)",
            (event_type, ticker, date, description),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_upcoming_events(days_ahead=14):
    """Events within next days_ahead days."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM events WHERE date >= date('now') AND date <= date('now', '+' || ? || ' days') ORDER BY date ASC",
            (days_ahead,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_old_events(keep_days=30):
    """Clean up events older than keep_days."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        cur = conn.execute("DELETE FROM events WHERE date < date('now', '-' || ? || ' days')", (keep_days,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


import re as _re_w

_WELCOME_RE = _re_w.compile(
    r"welcome to|confirm your|verify your|subscription confirmed|"
    r"thanks? for subscribing|you'?re subscribed|successfully subscribed|"
    r"subscription successful|please confirm|activate your|"
    r"confirm your email|verify your email|complete your registration",
    _re_w.IGNORECASE,
)


def _is_welcome_signal(title, body):
    """True if email looks like welcome/confirmation/short noise."""
    if title and _WELCOME_RE.search(title):
        return True
    return bool(not body or len(body) < 500)


# === Phase 11: conviction_history helpers ===


def persist_materiality(signal_id, score_dict, thesis_id=None, why_this_matters=None, regime=None, credit_regime=None):
    """Persist a materiality scoring result to conviction_history table."""
    derived = score_dict.get("_derived", {}) or {}
    tickers = derived.get("tickers", []) or []
    primary = tickers[0] if tickers else None

    with db() as cx:
        cx.execute(
            """
            INSERT INTO conviction_history (
                signal_id, thesis_id, polarity, signal_type,
                materiality, quality, novelty, cross_confirmation,
                market_impact, regime_relevance, is_noise,
                why_this_matters, regime_snapshot, credit_regime_snapshot,
                primary_ticker
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                signal_id,
                thesis_id,
                derived.get("polarity"),
                derived.get("signal_type"),
                score_dict.get("composite"),
                score_dict.get("quality"),
                score_dict.get("novelty"),
                score_dict.get("cross_confirmation"),
                score_dict.get("market_impact"),
                score_dict.get("regime_relevance"),
                1 if score_dict.get("noise") else 0,
                why_this_matters,
                regime,
                credit_regime,
                primary,
            ),
        )


def get_materiality(signal_id):
    """Get latest materiality scoring for a signal."""
    with db() as cx:
        row = cx.execute(
            """
            SELECT * FROM conviction_history WHERE signal_id = ?
            ORDER BY created_at DESC LIMIT 1
        """,
            (signal_id,),
        ).fetchone()
    return dict(row) if row else None


def get_top_material_signals(n=10, since_hours=24):
    """Get top N signals by materiality from last N hours, excluding noise."""
    with db() as cx:
        rows = cx.execute(
            """
            SELECT s.*, ch.materiality, ch.quality, ch.why_this_matters,
                   ch.primary_ticker, ch.signal_type, ch.polarity, ch.created_at as scored_at
            FROM conviction_history ch
            JOIN signals s ON s.id = ch.signal_id
            WHERE ch.id IN (
                SELECT MAX(id) FROM conviction_history GROUP BY signal_id
            )
            AND ch.created_at > datetime('now', ?)
            AND (ch.is_noise IS NULL OR ch.is_noise = 0)
            ORDER BY ch.materiality DESC
            LIMIT ?
        """,
            ("-" + str(since_hours) + " hours", n),
        ).fetchall()
    return [dict(r) for r in rows]


def log_decision(
    ticker,
    decision_type,
    confidence,
    reasoning,
    direction=None,
    thesis_id=None,
    price_at_decision=None,
    regime=None,
    credit_regime=None,
    materiality_top=None,
):
    """Phase 18 — Log a new decision. Returns row id."""
    import json as _json

    valid_types = {"entry", "scale_in", "partial_exit", "full_exit", "override", "no_action_flag"}
    if decision_type not in valid_types:
        raise ValueError(f"decision_type must be in {valid_types}, got {decision_type}")
    conn = _sqlite3.connect(_DB_PATH)
    try:
        cur = conn.execute(
            "INSERT INTO decisions (ticker, decision_type, direction, confidence_pre, reasoning, "
            "thesis_id, price_at_decision, regime_snapshot, credit_regime_snapshot, materiality_top_signals) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ticker.upper(),
                decision_type,
                direction,
                confidence,
                reasoning,
                thesis_id,
                price_at_decision,
                regime,
                credit_regime,
                _json.dumps(materiality_top) if materiality_top else None,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_decision(decision_id):
    """Fetch single decision by id. Returns dict or None."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_unresolved_decisions(horizon_days):
    """Decisions older than horizon_days not yet resolved at that horizon."""
    if horizon_days not in (30, 90):
        raise ValueError("horizon_days must be 30 or 90")
    col = f"resolved_{horizon_days}d_at"
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT * FROM decisions WHERE {col} IS NULL "
            f"AND date(created_at) <= date('now', '-{horizon_days} days') "
            f"ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def resolve_decision(decision_id, horizon_days, price, return_pct, thesis_relative, mistake_tag_auto):
    """Persist J+30 or J+90 resolution."""
    from datetime import datetime

    if horizon_days not in (30, 90):
        raise ValueError("horizon_days must be 30 or 90")
    suffix = f"{horizon_days}d"
    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute(
            f"UPDATE decisions SET resolved_{suffix}_at = ?, price_{suffix} = ?, "
            f"return_{suffix}_pct = ?, thesis_relative_{suffix} = ?, "
            f"mistake_tag_auto = COALESCE(mistake_tag_auto, ?) "
            f"WHERE id = ?",
            (
                datetime.now(UTC).replace(tzinfo=None).isoformat(),
                price,
                return_pct,
                thesis_relative,
                mistake_tag_auto,
                decision_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_decisions(n=20, only_resolved=False, ticker=None):
    """List recent decisions, optionally filtered."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        where = []
        params = []
        if only_resolved:
            where.append("resolved_30d_at IS NOT NULL")
        if ticker:
            where.append("ticker = ?")
            params.append(ticker.upper())
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        params.append(n)
        rows = conn.execute(f"SELECT * FROM decisions{clause} ORDER BY created_at DESC LIMIT ?", params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def override_mistake_tag(decision_id, manual_tag):
    """Manual override of auto-suggested mistake tag."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute("UPDATE decisions SET mistake_tag_manual = ? WHERE id = ?", (manual_tag, decision_id))
        conn.commit()
    finally:
        conn.close()


def get_journal_stats():
    """Aggregate stats over resolved decisions."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        by_mistake = conn.execute("""
            SELECT COALESCE(mistake_tag_manual, mistake_tag_auto) AS tag,
                   COUNT(*) AS n,
                   AVG(return_30d_pct) AS avg_ret_30,
                   AVG(return_90d_pct) AS avg_ret_90
            FROM decisions
            WHERE resolved_30d_at IS NOT NULL
            GROUP BY tag
            ORDER BY n DESC
        """).fetchall()
        by_type = conn.execute("""
            SELECT decision_type, COUNT(*) AS n,
                   AVG(return_30d_pct) AS avg_ret_30
            FROM decisions
            WHERE resolved_30d_at IS NOT NULL
            GROUP BY decision_type
            ORDER BY n DESC
        """).fetchall()
        return {"by_mistake": by_mistake, "by_type": by_type}
    finally:
        conn.close()


def recalibrate_source_credibility_from_brier(min_n=10):
    """Phase A1 — Cron mensuel: update sources.credibility = 1 - mean(brier_score)
    for sources with N>=min_n resolved predictions.
    Returns dict of updates applied {source_name: (old_cred, new_cred, n)}.
    """
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT s.id AS source_id, s.name AS source_name, s.credibility AS old_cred,
                   AVG(p.brier_score) AS mean_brier,
                   COUNT(p.id) AS n
            FROM sources s
            JOIN signals sig ON sig.source_id = s.id
            JOIN predictions p ON p.signal_id = sig.id
            WHERE p.brier_score IS NOT NULL
            GROUP BY s.id, s.name, s.credibility
            HAVING n >= ?
        """,
            (min_n,),
        ).fetchall()
        updates = {}
        for r in rows:
            new_cred = max(0.0, min(1.0, 1.0 - r["mean_brier"]))
            conn.execute("UPDATE sources SET credibility = ? WHERE id = ?", (new_cred, r["source_id"]))
            updates[r["source_name"]] = (r["old_cred"], new_cred, r["n"])
        conn.commit()
        return updates
    finally:
        conn.close()


def get_brier_stats_by_source():
    """Phase A1 — Return per-source Brier stats for /sources_brier handler."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT s.name AS source_name, s.credibility AS current_cred,
                   COUNT(p.id) AS n_resolved,
                   AVG(p.brier_score) AS mean_brier,
                   SUM(CASE WHEN p.outcome='correct' THEN 1 ELSE 0 END) AS n_correct,
                   SUM(CASE WHEN p.outcome='neutral' THEN 1 ELSE 0 END) AS n_neutral,
                   SUM(CASE WHEN p.outcome='incorrect' THEN 1 ELSE 0 END) AS n_incorrect
            FROM sources s
            LEFT JOIN signals sig ON sig.source_id = s.id
            LEFT JOIN predictions p ON p.signal_id = sig.id AND p.brier_score IS NOT NULL
            GROUP BY s.id, s.name, s.credibility
            ORDER BY mean_brier ASC NULLS LAST, n_resolved DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def store_signal_embedding(signal_id, embedding_blob, model_name):
    """Phase A3 — Persist embedding for a signal. INSERT OR REPLACE."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO signal_embeddings (signal_id, embedding, model, embedded_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (signal_id, embedding_blob, model_name),
        )
        conn.commit()
    finally:
        conn.close()


def get_signal_embedding(signal_id):
    """Phase A3 — Fetch raw embedding blob for a signal."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        row = conn.execute("SELECT embedding FROM signal_embeddings WHERE signal_id=?", (signal_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_unembedded_signals(limit=100, min_chars=20):
    """Phase A3 — Signals without embedding. Uses summary or fallback title."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT s.id,
                   COALESCE(NULLIF(s.summary, ''), s.title) AS text_for_embed,
                   s.title, s.summary
            FROM signals s
            LEFT JOIN signal_embeddings se ON se.signal_id = s.id
            WHERE se.signal_id IS NULL
              AND COALESCE(NULLIF(s.summary, ''), s.title) IS NOT NULL
              AND length(COALESCE(NULLIF(s.summary, ''), s.title)) >= ?
            ORDER BY s.id DESC
            LIMIT ?
        """,
            (min_chars, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_embedded_signals_window(hours=48):
    """Phase A3 — Recent embedded signals with metadata for clustering."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(f"""
            SELECT s.id, s.title, s.summary,
                   COALESCE(NULLIF(s.summary, ''), s.title) AS text_for_embed,
                   s.source_id, s.timestamp, s.echo_cluster_id,
                   se.embedding,
                   src.name AS source_name
            FROM signals s
            INNER JOIN signal_embeddings se ON se.signal_id = s.id
            LEFT JOIN sources src ON src.id = s.source_id
            WHERE datetime(s.timestamp) >= datetime('now', '-{int(hours)} hours')
            ORDER BY s.timestamp DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_echo_cluster_id(signal_id, cluster_id):
    """Phase A3 — Tag a signal with its computed echo cluster."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute("UPDATE signals SET echo_cluster_id=? WHERE id=?", (cluster_id, signal_id))
        conn.commit()
    finally:
        conn.close()


def get_signals_by_source_with_tickers(source_id):
    """Phase A4 — Signals from source with non-empty entities (tickers)."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, timestamp, title, entities
            FROM signals
            WHERE source_id = ?
              AND entities IS NOT NULL
              AND entities != ''
              AND entities != '[]'
            ORDER BY timestamp ASC
        """,
            (source_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_source_half_life(source_id, median_days, n_samples):
    """Phase A4 — Persist computed half-life on source row."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute(
            "UPDATE sources SET half_life_days=?, half_life_n_samples=?, "
            "half_life_computed_at=CURRENT_TIMESTAMP WHERE id=?",
            (median_days, n_samples, source_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_sources_with_half_life():
    """Phase A4 — All sources with half-life metadata for display."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT s.id, s.name, s.credibility, s.n_signals,
                   s.half_life_days, s.half_life_n_samples, s.half_life_computed_at
            FROM sources s
            ORDER BY
              CASE WHEN s.half_life_days IS NULL THEN 1 ELSE 0 END,
              s.half_life_days ASC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_or_update_position_on_buy(ticker, qty, price, notes=None):
    """Phase B5 — Record buy. Returns (position_id, decision_type, new_avg, new_qty).
    decision_type = 'entry' if first buy, 'scale_in' otherwise.
    Uses existing schema: qty / avg_cost / status='open'/'closed'.
    """
    if qty <= 0 or price <= 0:
        raise ValueError(f"qty and price must be positive, got qty={qty} price={price}")
    ticker = ticker.upper()
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        active = conn.execute(
            "SELECT * FROM positions WHERE ticker=? AND status='open' ORDER BY opened_at DESC LIMIT 1", (ticker,)
        ).fetchone()
        if active:
            old_qty = active["qty"]
            old_avg = active["avg_cost"]
            new_qty = old_qty + qty
            new_avg = (old_qty * old_avg + qty * price) / new_qty
            conn.execute(
                "UPDATE positions SET qty=?, avg_cost=?, last_updated=CURRENT_TIMESTAMP WHERE id=?",
                (new_qty, new_avg, active["id"]),
            )
            conn.commit()
            return active["id"], "scale_in", new_avg, new_qty
        else:
            cur = conn.execute(
                "INSERT INTO positions (ticker, qty, avg_cost, notes, status) VALUES (?, ?, ?, ?, 'open')",
                (ticker, qty, price, notes),
            )
            conn.commit()
            return cur.lastrowid, "entry", price, qty
    finally:
        conn.close()


def record_position_sell(ticker, qty, price):
    """Phase B5 — Record sell. Returns (position_id, decision_type, realized_pnl_delta, new_qty)."""
    if qty <= 0 or price <= 0:
        raise ValueError(f"qty and price must be positive, got qty={qty} price={price}")
    ticker = ticker.upper()
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        active = conn.execute(
            "SELECT * FROM positions WHERE ticker=? AND status='open' ORDER BY opened_at DESC LIMIT 1", (ticker,)
        ).fetchone()
        if not active:
            raise ValueError(f"No active position for {ticker}")
        if qty > active["qty"]:
            raise ValueError(f"Sell qty {qty} > current qty {active['qty']} for {ticker}")
        avg = active["avg_cost"]
        realized_delta = qty * (price - avg)
        new_qty = active["qty"] - qty
        new_total_pnl = (active["realized_pnl"] or 0) + realized_delta
        if new_qty <= 1e-9:
            conn.execute(
                "UPDATE positions SET qty=0, realized_pnl=?, status='closed', last_updated=CURRENT_TIMESTAMP WHERE id=?",
                (new_total_pnl, active["id"]),
            )
            dtype = "full_exit"
        else:
            conn.execute(
                "UPDATE positions SET qty=?, realized_pnl=?, last_updated=CURRENT_TIMESTAMP WHERE id=?",
                (new_qty, new_total_pnl, active["id"]),
            )
            dtype = "partial_exit"
        conn.commit()
        return active["id"], dtype, realized_delta, new_qty
    finally:
        conn.close()


def get_active_positions():
    """Phase B5 — Active positions (status='open')."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM positions WHERE status='open' ORDER BY opened_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_position_by_ticker(ticker):
    """Phase B5 — Active position for ticker, or None."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM positions WHERE ticker=? AND status='open' ORDER BY opened_at DESC LIMIT 1",
            (ticker.upper(),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_positions_history(ticker=None, limit=50):
    """Phase B5 — All positions including closed."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        if ticker:
            rows = conn.execute(
                "SELECT * FROM positions WHERE ticker=? ORDER BY opened_at DESC LIMIT ?", (ticker.upper(), limit)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM positions ORDER BY opened_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_decision_bias_tags(decision_id, tags):
    """Phase B6 — Persist bias_tags JSON array on a decision."""
    import json as _json

    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute("UPDATE decisions SET bias_tags=? WHERE id=?", (_json.dumps(tags) if tags else None, decision_id))
        conn.commit()
    finally:
        conn.close()


def get_bias_stats(ticker=None, since_days=180):
    """Phase B6 — Aggregate bias frequencies across resolved or unresolved decisions."""
    import json as _json

    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        if ticker:
            rows = conn.execute(
                "SELECT decision_type, bias_tags FROM decisions "
                "WHERE bias_tags IS NOT NULL AND ticker=? "
                "AND date(created_at) >= date('now', ?)",
                (ticker.upper(), f"-{int(since_days)} days"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT decision_type, bias_tags FROM decisions "
                "WHERE bias_tags IS NOT NULL "
                "AND date(created_at) >= date('now', ?)",
                (f"-{int(since_days)} days",),
            ).fetchall()
        counts = {}
        type_counts = {}
        total_with_tags = 0
        for r in rows:
            try:
                tags = _json.loads(r["bias_tags"]) if r["bias_tags"] else []
            except Exception:
                tags = []
            if tags:
                total_with_tags += 1
                for t in tags:
                    counts[t] = counts.get(t, 0) + 1
                    type_counts.setdefault(r["decision_type"], {})
                    type_counts[r["decision_type"]][t] = type_counts[r["decision_type"]].get(t, 0) + 1
        return {
            "total_decisions_analyzed": len(rows),
            "total_with_tags": total_with_tags,
            "bias_counts": sorted(counts.items(), key=lambda x: -x[1]),
            "by_decision_type": type_counts,
        }
    finally:
        conn.close()


def update_thesis_pre_mortem(thesis_id, pre_mortem_json):
    """Phase B7 — Persist pre-mortem JSON for a thesis."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute("UPDATE theses SET pre_mortem=? WHERE id=?", (pre_mortem_json, thesis_id))
        conn.commit()
    finally:
        conn.close()


def get_thesis_pre_mortem(thesis_id):
    """Phase B7 — Fetch pre-mortem JSON string for a thesis."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        row = conn.execute("SELECT pre_mortem FROM theses WHERE id=?", (thesis_id,)).fetchone()
        return row[0] if row and row[0] else None
    finally:
        conn.close()


def get_thesis_full(thesis_id):
    """Phase B7 — Full thesis row for pre-mortem context."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM theses WHERE id=?", (thesis_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ============ Phase C7 — Insider BUY cluster empirical tracking ============


def log_buy_cluster(ticker, detected_at, window_days, cluster_dict, price_at_detection):
    """Phase C7 — Persist a detected BUY cluster. Returns new id."""
    import json as _json

    conn = _sqlite3.connect(_DB_PATH)
    try:
        cur = conn.execute(
            "INSERT INTO insider_buy_clusters_log (ticker, detected_at, window_days, "
            "distinct_buyers, total_buy_m, cluster_strength, top_buyers_json, "
            "price_at_detection, status) VALUES (?,?,?,?,?,?,?,?,'pending')",
            (
                ticker.upper(),
                detected_at,
                window_days,
                cluster_dict.get("distinct_buyers", 0),
                cluster_dict.get("total_buy_m", 0.0),
                cluster_dict.get("cluster_strength", "none"),
                _json.dumps(cluster_dict.get("top_buyers", [])),
                price_at_detection,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_recent_buy_cluster_log(ticker, days=7):
    """Phase C7 — Dedup check: most recent cluster log for ticker in last N days."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM insider_buy_clusters_log "
            "WHERE ticker=? AND date(detected_at) >= date('now', ?) "
            "ORDER BY detected_at DESC LIMIT 1",
            (ticker.upper(), f"-{int(days)} days"),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_unresolved_buy_clusters(checkpoint_days):
    """Phase C7 — Clusters older than checkpoint_days that haven't been resolved at that checkpoint."""
    col = "return_30d" if checkpoint_days == 30 else "return_90d"
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT * FROM insider_buy_clusters_log "
            f"WHERE {col} IS NULL "
            f"AND date(detected_at) <= date('now', ?) "
            f"AND price_at_detection IS NOT NULL "
            f"ORDER BY detected_at ASC",
            (f"-{int(checkpoint_days)} days",),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def resolve_buy_cluster_return(cluster_id, checkpoint_days, return_pct, resolved_at):
    """Phase C7 — Persist resolved return at J+30 or J+90."""
    col_ret = "return_30d" if checkpoint_days == 30 else "return_90d"
    col_dt = "resolved_30d_at" if checkpoint_days == 30 else "resolved_90d_at"
    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute(
            f"UPDATE insider_buy_clusters_log SET {col_ret}=?, {col_dt}=? WHERE id=?",
            (return_pct, resolved_at, cluster_id),
        )
        # If both resolved, mark status
        row = conn.execute(
            "SELECT return_30d, return_90d FROM insider_buy_clusters_log WHERE id=?", (cluster_id,)
        ).fetchone()
        if row and row[0] is not None and row[1] is not None:
            conn.execute("UPDATE insider_buy_clusters_log SET status='resolved' WHERE id=?", (cluster_id,))
        conn.commit()
    finally:
        conn.close()


def get_buy_clusters_for_ticker(ticker, limit=20):
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM insider_buy_clusters_log WHERE ticker=? ORDER BY detected_at DESC LIMIT ?",
            (ticker.upper(), int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_buy_cluster_stats(since_days=365):
    """Phase C7 — Empirical alpha summary across all detected clusters."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM insider_buy_clusters_log "
            "WHERE date(detected_at) >= date('now', ?) "
            "ORDER BY detected_at DESC",
            (f"-{int(since_days)} days",),
        ).fetchall()
        rows = [dict(r) for r in rows]
        n_total = len(rows)
        r30 = [r["return_30d"] for r in rows if r["return_30d"] is not None]
        r90 = [r["return_90d"] for r in rows if r["return_90d"] is not None]

        def _stats(returns):
            if not returns:
                return None
            sorted_r = sorted(returns)
            n = len(sorted_r)
            mean = sum(sorted_r) / n
            median = sorted_r[n // 2] if n % 2 else (sorted_r[n // 2 - 1] + sorted_r[n // 2]) / 2
            hit = sum(1 for r in sorted_r if r > 0)
            return {
                "n": n,
                "mean": mean,
                "median": median,
                "hit_rate": hit / n,
                "best": sorted_r[-1],
                "worst": sorted_r[0],
            }

        by_strength = {}
        for s in ("strong", "moderate", "weak"):
            sub = [r["return_30d"] for r in rows if r["cluster_strength"] == s and r["return_30d"] is not None]
            if sub:
                by_strength[s] = {"n": len(sub), "mean_30d": sum(sub) / len(sub)}

        return {
            "n_total": n_total,
            "n_resolved_30d": len(r30),
            "n_resolved_90d": len(r90),
            "stats_30d": _stats(r30),
            "stats_90d": _stats(r90),
            "by_strength": by_strength,
        }
    finally:
        conn.close()


# ============ Phase C9 — 8-K filings tracking ============


def log_8k_filing(ticker, cik, accession, filed_at, items_raw, item_codes, severity, severity_reason, filing_url):
    """Phase C9 — Persist 8-K filing (INSERT OR IGNORE on accession UNIQUE). Returns id or None."""
    import json as _json

    conn = _sqlite3.connect(_DB_PATH)
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO filings_8k_log (ticker, cik, accession_number, "
            "filed_at, items_raw, item_codes, severity, severity_reason, filing_url) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                ticker.upper(),
                cik,
                accession,
                filed_at,
                items_raw,
                _json.dumps(item_codes),
                severity,
                severity_reason,
                filing_url,
            ),
        )
        conn.commit()
        return cur.lastrowid if cur.rowcount > 0 else None
    finally:
        conn.close()


def get_8k_filing_by_accession(accession):
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM filings_8k_log WHERE accession_number=?", (accession,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_recent_8k_filings_db(ticker=None, severity=None, days=60, limit=50):
    """Phase C9 — Query 8-K log with optional ticker/severity filters."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        q = "SELECT * FROM filings_8k_log WHERE date(filed_at) >= date('now', ?)"
        params = [f"-{int(days)} days"]
        if ticker:
            q += " AND ticker=?"
            params.append(ticker.upper())
        if severity:
            q += " AND severity=?"
            params.append(severity)
        q += " ORDER BY filed_at DESC LIMIT ?"
        params.append(int(limit))
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ============ Phase C11 — Multi-round debate persistence ============


def save_debate_transcript(ticker, transcript_dict, convergence_score, verdict, total_cost_usd=None):
    """Phase C11 — Persist full debate transcript. Returns new id."""
    import json as _json

    conn = _sqlite3.connect(_DB_PATH)
    try:
        cur = conn.execute(
            "INSERT INTO debate_transcripts (ticker, transcript_json, convergence_score, verdict, total_cost_usd) "
            "VALUES (?,?,?,?,?)",
            (
                ticker.upper(),
                _json.dumps(transcript_dict, ensure_ascii=False),
                convergence_score,
                verdict,
                total_cost_usd,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_recent_debates(ticker=None, limit=10):
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        if ticker:
            rows = conn.execute(
                "SELECT * FROM debate_transcripts WHERE ticker=? ORDER BY started_at DESC LIMIT ?",
                (ticker.upper(), int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM debate_transcripts ORDER BY started_at DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_risk_check(ticker, side, proposed_usd, verdict, risk_check_dict, portfolio_snapshot):
    """Phase C12 — Persist risk check result."""
    import json as _json

    conn = _sqlite3.connect(_DB_PATH)
    try:
        cur = conn.execute(
            "INSERT INTO risk_checks (ticker, side, proposed_usd, verdict, "
            "risk_check_json, portfolio_snapshot_json) VALUES (?,?,?,?,?,?)",
            (
                ticker.upper(),
                side,
                proposed_usd,
                verdict,
                _json.dumps(risk_check_dict, ensure_ascii=False),
                _json.dumps(portfolio_snapshot, ensure_ascii=False),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_decisions_for_ticker(ticker, since_days=90, limit=10):
    """Phase C12 — Recent decisions for ticker (used by risk_manager)."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM decisions WHERE ticker=? "
            "AND date(created_at) >= date('now', ?) "
            "ORDER BY created_at DESC LIMIT ?",
            (ticker.upper(), f"-{int(since_days)} days", int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ============ Phase Digestion Quality — signal_type + corroboration ============


def set_signal_type(signal_id, signal_type):
    """Phase Digestion — persist signal type classification."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute("UPDATE signals SET signal_type=? WHERE id=?", (signal_type, signal_id))
        conn.commit()
    finally:
        conn.close()


def get_unclassified_signals(limit=50):
    """Phase Digestion — fetch signals with signal_type=NULL for classifier cron."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, title, summary, content FROM signals WHERE signal_type IS NULL ORDER BY timestamp DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_signals_by_type(signal_type, since_hours=72, limit=20):
    """Phase Digestion — query signals by classification."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        from datetime import datetime as _dt, timedelta as _td

        cutoff = (_dt.now() - _td(hours=int(since_hours))).strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute(
            "SELECT s.*, src.name AS source_name FROM signals s "
            "LEFT JOIN sources src ON s.source_id = src.id "
            "WHERE s.signal_type=? AND s.timestamp >= ? "
            "ORDER BY (s.score * COALESCE(s.materiality_boost, 1.0)) DESC LIMIT ?",
            (signal_type, cutoff, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_materiality_boost(signal_id, boost):
    """Phase Digestion — persist corroboration boost factor."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        conn.execute("UPDATE signals SET materiality_boost=? WHERE id=?", (float(boost), signal_id))
        conn.commit()
    finally:
        conn.close()


def get_signals_in_cluster_with_sources(cluster_id):
    """Phase Digestion — distinct sources count for echo cluster."""
    conn = _sqlite3.connect(_DB_PATH)
    try:
        n = conn.execute(
            "SELECT COUNT(DISTINCT source_id) FROM signals WHERE echo_cluster_id=?", (int(cluster_id),)
        ).fetchone()[0]
        return int(n)
    finally:
        conn.close()
