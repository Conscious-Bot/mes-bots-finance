"""SQLite accessors. Toute la mémoire passe par ici.

Re-exports L17 : la passerelle expose IntegrityError pour que les callers
n'aient pas à importer sqlite3 directement (sinon test_no_new_sqlite3_bypass
mord). Ajouter ici les autres exceptions sqlite3 utiles si besoin.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from sqlite3 import IntegrityError  # re-export passerelle L17
from typing import Any

__all__ = ["DB_PATH", "IntegrityError", "db"]  # extension possible

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "bot.db"
STATE_PATH = ROOT / "data" / "bot_state.json"


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def load_state() -> dict[str, Any]:
    from typing import cast

    return cast(dict[str, Any], json.loads(STATE_PATH.read_text()))


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def update_state(**kwargs: Any) -> None:
    s = load_state()
    s.update(kwargs)
    s["last_heartbeat_ts"] = datetime.now(UTC).isoformat()
    save_state(s)


def log_event(event_type: str, details: Any = None) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO bot_events(timestamp, event_type, details) VALUES(?,?,?)",
            (datetime.now(UTC).isoformat(), event_type, json.dumps(details) if isinstance(details, dict) else details),
        )


def active_signals(min_score: int = 5, since_hours: int = 24) -> list[dict]:
    since = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()
    now = datetime.now(UTC).isoformat()
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
            (status, datetime.now(UTC).isoformat(), notes, thesis_id),
        )


def add_to_watchlist(ticker: str, sector: str | None = None, notes: str | None = None) -> None:
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


def add_feedback(target_type: str, target_id: int, score: float, note: str | None = None) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO feedback(target_type, target_id, score, note) VALUES(?,?,?,?)",
            (target_type, target_id, score, note),
        )


def seed_narratives(narratives_config: list[dict[str, Any]]) -> None:
    with db() as conn:
        for n in narratives_config:
            conn.execute(
                "INSERT OR IGNORE INTO narratives(name, definition) VALUES(?,?)", (n["name"], n.get("definition", ""))
            )


# === Phase 2 : Gmail ingestion helpers ===

import sqlite3 as _sqlite3

# ─── ADR 014 -- Ledger segmentation par methodology_version ───────────────────
# Canonique = familles de predicteurs incluses dans Brier headline / KPI #3 /
# calibration. Le reste (v0, v1 archives, rule_v1_shadow paired, rule_v1_fallback
# plancher degrade) est mesure separement via brier_by_methodology(version).
# Source unique : aucune query consommatrice ne re-derive ces filtres.

CANONICAL_METHODOLOGY_EXCLUSIONS: tuple[str, ...] = (
    "v0",                # cohorte quarantine 12/05 (horizon=30 hardcode)
    "v1",                # pre-pivot mono-bucket
    "rule_v1_shadow",    # challenger paired -- mesure delta vs LLM, hors headline
    "rule_v1_fallback",  # plancher degrade LLM down, mesure separement
)


def canonical_predictions_filter() -> str:
    """Fragment SQL WHERE qui exclut les methodologies non-canoniques.

    Pattern d'usage :
        sql = f"SELECT * FROM predictions WHERE resolved_at IS NOT NULL "
              f"AND {canonical_predictions_filter()}"
        rows = conn.execute(sql).fetchall()

    Tous les consommateurs canoniques (KPI #2 morning_brief, KPI #3 calibration,
    J-day batch, panneau vigie calibration, monthly_track_record) doivent passer
    par ce fragment. Aucune SQL parallele.

    ADR 014. Source unique. Ne pas dupliquer.
    """
    quoted = ", ".join(f"'{v}'" for v in CANONICAL_METHODOLOGY_EXCLUSIONS)
    return f"methodology_version NOT IN ({quoted})"


# ─── ADR 014 § Substance tier (post-#97 hazard A fix) ─────────────────────────
# Substance accounting : "toutes les predictions LLM reelles" pour scorer
# inputs (base_rates, outcome_context), accounting operationnel (morning_brief,
# v2_vigilance), per-thesis tracking (portfolio_grade, thesis_track_record),
# et LLM-loop audit (render._loop). Inclut v1 archive + v2 canonical + futures
# llm_v3 / ensemble_v1 / etc. EXCLUT :
#   - v0 (cohorte quarantine 12/05)
#   - rule_v1_shadow (non-LLM challenger paired ; pollute analogues + base rates)
#   - rule_v1_fallback (non-LLM plancher ; pollute le meme)
# Pre-fix : ces surfaces utilisaient `methodology_version != 'v0'` (denylist
# implicite). Quand rule_v1_* shippe (#94/#96), serait silently swept dans
# l'accounting -> contamination. Le filtre devient SOURCE UNIQUE comme
# canonical_predictions_filter().

SUBSTANCE_METHODOLOGY_EXCLUSIONS: tuple[str, ...] = (
    "v0",                # quarantine
    "rule_v1_shadow",    # non-LLM family : ne pas mixer dans LLM substance
    "rule_v1_fallback",  # non-LLM family : ne pas mixer dans LLM substance
)


def substance_predictions_filter() -> str:
    """Fragment SQL WHERE pour les surfaces de substance accounting LLM.

    Inclut TOUTES les familles LLM (v1, v2, futures llm_v3...), exclut v0
    quarantine + familles non-LLM (rule_v1_shadow/fallback). Strictement plus
    large que canonical_predictions_filter() qui exclut aussi v1 archive.

    Pattern d'usage : identique a canonical_predictions_filter(). Aucune
    query consommatrice ne re-derive ce filtre.

    Distinction avec canonical_filter (ADR 014 § Disambiguation rule) :
      - canonical = forward-headline (track record public, KPI #2 forward,
                    calibration audit). Brier publi-facing.
      - substance = LLM-only working set (base_rates, outcome_context,
                    portfolio_grade, thesis_track_record, v2_vigilance,
                    morning_brief, render._loop).

    Surface user-facing lookup (prediction_why /pred_why) reste sur le
    `!= 'v0'` direct car l'utilisateur veut retrouver TOUTE prediction faite
    sur un ticker (y compris shadow/fallback) avec leur provenance.
    """
    quoted = ", ".join(f"'{v}'" for v in SUBSTANCE_METHODOLOGY_EXCLUSIONS)
    return f"methodology_version NOT IN ({quoted})"


def brier_by_methodology(methodology_version: str) -> dict:
    """Stats Brier pour UNE famille de predicteur (resolved, scored, raw avg, dedup avg).

    Utilise pour /shadow_compare, /methodology_status, et tout readout qui veut
    un Brier d'une famille separement (ex : 'rule_v1_shadow' pour mesurer le
    baseline determinist vs LLM canonique 'v2').

    Returns {n_total, n_scored, n_correct, n_incorrect, n_neutral,
             brier_raw_avg, brier_dedup_avg, dedup_ratio}.
    """
    with db() as conn:
        rows = conn.execute(
            "SELECT id, ticker, direction, outcome, brier_score, signal_id "
            "FROM predictions "
            "WHERE methodology_version = ? AND resolved_at IS NOT NULL",
            (methodology_version,),
        ).fetchall()
    if not rows:
        return {
            "methodology_version": methodology_version,
            "n_total": 0, "n_scored": 0, "n_correct": 0, "n_incorrect": 0,
            "n_neutral": 0, "brier_raw_avg": None, "brier_dedup_avg": None,
            "dedup_ratio": None,
        }
    n_total = len(rows)
    n_correct = sum(1 for r in rows if r["outcome"] == "correct")
    n_incorrect = sum(1 for r in rows if r["outcome"] == "incorrect")
    n_neutral = n_total - n_correct - n_incorrect
    briers = [r["brier_score"] for r in rows if r["brier_score"] is not None]
    clusters: dict[tuple, list[float]] = {}
    for r in rows:
        if r["brier_score"] is None:
            continue
        k = (r["signal_id"], r["ticker"], r["direction"])
        clusters.setdefault(k, []).append(r["brier_score"])
    cluster_briers = [sum(v) / len(v) for v in clusters.values()]
    avg_raw = sum(briers) / len(briers) if briers else None
    avg_dedup = sum(cluster_briers) / len(cluster_briers) if cluster_briers else None
    dedup_ratio = (len(briers) / len(clusters)) if clusters else None
    return {
        "methodology_version": methodology_version,
        "n_total": n_total, "n_scored": len(briers),
        "n_correct": n_correct, "n_incorrect": n_incorrect, "n_neutral": n_neutral,
        "brier_raw_avg": avg_raw, "brier_dedup_avg": avg_dedup,
        "dedup_ratio": dedup_ratio,
    }


def get_open_positions() -> list[dict]:
    """Positions detenues (qty > 0). avg_cost en EUR.

    Cure 12/06 (#132 sweep) : SQL-direct lisait p.avg_cost qui est NULL par
    construction depuis migration positions VUE (#105/#120). Resultait en
    avg_cost=0 silencieux -> snapshots quotidiens avec total_cost_eur=0
    (bug pre-existant) + meme classe de bug que M10 Taleb barbell #133bis.
    Cure : passer par BookLine.avg_cost_eur (PMP roulant computed live).
    Les 3 callers (compute_snapshot, position_view.get_all_positions_views,
    portfolio_views handler) recoivent maintenant la vraie valeur.
    """
    from shared import book
    held = book.get_held_lines()
    return [
        {
            "ticker": ln.ticker,
            "qty": float(ln.qty or 0),
            "avg_cost": float(ln.avg_cost_eur or 0),
        }
        for ln in held
        if (ln.qty or 0) > 0
    ]


_SNAPSHOT_DDL = (
    "CREATE TABLE IF NOT EXISTS portfolio_snapshots ("
    "snapshot_date TEXT PRIMARY KEY, captured_at TEXT NOT NULL, "
    "total_value_eur REAL NOT NULL, total_cost_eur REAL NOT NULL, "
    "pnl_eur REAL NOT NULL, pnl_pct REAL NOT NULL, "
    "n_positions INTEGER NOT NULL, n_priced INTEGER NOT NULL, "
    "hwm_value_eur REAL, drawdown_pct REAL, detail_json TEXT)"
)


def _ensure_snapshot_table(conn: _sqlite3.Connection) -> None:
    conn.execute(_SNAPSHOT_DDL)


def upsert_portfolio_snapshot(snap: dict) -> None:
    "Ecrit/met a jour le snapshot du jour (idempotent sur snapshot_date)."
    import json

    cols = (
        "snapshot_date",
        "captured_at",
        "total_value_eur",
        "total_cost_eur",
        "pnl_eur",
        "pnl_pct",
        "n_positions",
        "n_priced",
        "hwm_value_eur",
        "drawdown_pct",
        "detail_json",
    )
    vals = [snap[c] if c != "detail_json" else json.dumps(snap.get("detail_json") or {}, sort_keys=True) for c in cols]
    sets = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "snapshot_date")
    sql = (
        "INSERT INTO portfolio_snapshots (" + ", ".join(cols) + ") "
        "VALUES (" + ", ".join("?" for _ in cols) + ") "
        "ON CONFLICT(snapshot_date) DO UPDATE SET " + sets
    )
    with db() as conn:
        _ensure_snapshot_table(conn)
        conn.execute(sql, vals)
        conn.commit()


def latest_snapshot_hwm() -> float | None:
    with db() as conn:
        _ensure_snapshot_table(conn)
        row = conn.execute("SELECT MAX(hwm_value_eur) FROM portfolio_snapshots").fetchone()
    return float(row[0]) if row and row[0] is not None else None


def get_portfolio_snapshots(limit: int = 400) -> list[dict]:
    with db() as conn:
        _ensure_snapshot_table(conn)
        rows = conn.execute(
            "SELECT snapshot_date, total_value_eur, total_cost_eur, pnl_pct, "
            "n_positions, n_priced, hwm_value_eur, drawdown_pct "
            "FROM portfolio_snapshots ORDER BY snapshot_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
    keys = ("date", "value", "cost", "pnl_pct", "n_positions", "n_priced", "hwm", "drawdown_pct")
    return [dict(zip(keys, r)) for r in rows]


# Note : _DB_PATH n'est plus un module attribute statique. Il est resolu
# dynamiquement via __getattr__ (defini en bas du fichier) -> retourne
# toujours la valeur COURANTE de DB_PATH. Ainsi, monkeypatch(storage,
# "DB_PATH", x) propage automatiquement a tous les ~28 callers externes
# qui font storage._DB_PATH. Bug pollution prod 30/05 : un test
# monkeypatch _DB_PATH n'affectait pas DB_PATH (et vice versa), et
# l'ancienne _DB_PATH = Path("data/bot.db") etait CWD-relative -- les
# deux sources de bug fixees par cette consolidation.


def _naive_utc_iso() -> str:
    """Generate UTC timestamp as naive ISO 8601 string (no offset suffix).

    Used for DB columns historically storing naive timestamps. The strip-tz
    antipattern wrapped here is intentional: existing DB columns (decisions.
    resolved_*_at, analyses.timestamp, insider_buy_clusters_log.detected_at,
    etc.) store naive ISO. Migrating columns to aware = string-compare format
    risk on existing rows (see Lesson 26 in CONVENTIONS.md).

    Equivalent to deprecated datetime.utcnow().isoformat() but explicit about
    UTC source and naive-by-design intent. Use this helper at every DB write
    site that targets a naive-convention column.

    Schema-migration to aware-aware everywhere is tracked as P4 (separate ship).
    """
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


def signal_exists_by_gmail_id(gmail_id: str) -> bool:
    """Check if a Gmail message has already been ingested."""
    conn = _sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT 1 FROM signals WHERE gmail_id = ? LIMIT 1", (gmail_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def get_or_create_source(sender: str) -> int:
    """Resolve sender string to source_id. Creates a new source if unknown."""
    conn: _sqlite3.Connection = _sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT id FROM sources WHERE name = ?", (sender,)).fetchone()
        if row:
            return int(row[0])
        cur = conn.execute(
            "INSERT INTO sources (name, type, credibility, n_signals) VALUES (?, ?, ?, ?)",
            (sender, "newsletter", 0.5, 0),
        )
        conn.commit()
        # lastrowid is int|None per type stubs, but always int after successful INSERT
        return cur.lastrowid or 0
    finally:
        conn.close()


def get_or_create_source_typed(
    name: str, type_: str, credibility: float, family: str | None = None,
) -> int:
    """Resolve name to source_id, cree avec type+credibility specifies si absente.

    Pour sources primaires (sec_filing, regulatory, etc.) qui ont une credibility
    de base != 0.50. Utilise par intelligence/edgar_signal_wire.py (8-K SEC).

    family : Axe 2 QUALITY_BAR taxonomy. Si None, deduction par type_ :
      sec_filing -> primary_filing, insider -> insider, manual -> manual,
      autres -> narrative_newsletter (default DB).
    """
    if family is None:
        family = {
            "sec_filing": "primary_filing",
            "insider": "insider",
            "manual": "manual",
            "broker_research": "broker_research",
            "social": "social",
            "chat": "chat",
        }.get(type_, "narrative_newsletter")
    conn: _sqlite3.Connection = _sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT id FROM sources WHERE name = ?", (name,)).fetchone()
        if row:
            return int(row[0])
        cur = conn.execute(
            "INSERT INTO sources (name, type, credibility, n_signals, family) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, type_, credibility, 0, family),
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def insert_primary_filing_signal(
    source_id: int,
    dedup_key: str,
    timestamp: str,
    title: str,
    summary: str,
    content: str,
    entities_json: str,
    signal_type: str = "catalyst",
    score: int = 7,
    sentiment: str = "bullish",
    impact_magnitude: float = 3.0,
) -> int | None:
    """Insert un signal issu d'un filing primaire (SEC 8-K, insider, etc.).

    Sentiment='bullish' = placeholder (V2 recalcule la vraie direction au scoring).
    score=7 = passe filter auto_register_predictions score>=6.
    dedup_key stocke dans gmail_id (colonne UNIQUE existante).

    Retourne signal_id si nouveau, None si deja insere (dedup silencieux).
    """
    conn = _sqlite3.connect(DB_PATH)
    try:
        try:
            cur = conn.execute(
                "INSERT INTO signals (source_id, gmail_id, timestamp, title, content, "
                "summary, score, sentiment, entities, signal_type, impact_magnitude) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source_id, dedup_key, timestamp, title, content, summary,
                    score, sentiment, entities_json, signal_type, impact_magnitude,
                ),
            )
        except _sqlite3.IntegrityError:
            return None  # dedup
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def insert_raw_signal(source_id: int, gmail_id: str, timestamp: str, subject: str, content: str) -> int | None:
    """Insert a raw email-derived signal. Returns new signal_id, or None on welcome/duplicate.

    Atomicity invariant: n_signals counter and last_signal_at are updated ONLY if INSERT succeeds.
    Handles UNIQUE constraint on gmail_id gracefully (duplicate emails return None).
    """
    if _is_welcome_signal(subject, content):
        return None
    conn = _sqlite3.connect(DB_PATH)
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


def _parse_thesis_row(row):
    """Convert sqlite Row to dict with JSON fields parsed."""
    d = dict(row)
    for fld in ("key_drivers", "invalidation_triggers", "triggers_profit_take"):
        if d.get(fld):
            with suppress(TypeError, ValueError):
                d[fld] = json.loads(d[fld])
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
    variant_perception=None,  # A0 : ou tu differes du consensus (None = pas declare)
    driver_epic=None,          # A0 : EpicDriver JSON (kpi, direction, magnitude, price_channel)
    benchmark=None,            # A0 : benchmark canonique pre-engaged
):
    """Insert a new thesis. Returns thesis_id."""
    now = datetime.now(UTC).isoformat()

    def _to_list(v):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return [v]

    # A0 : serialiser driver_epic en JSON si dict
    if isinstance(driver_epic, dict):
        driver_epic = json.dumps(driver_epic, sort_keys=True)

    conn = _sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            """INSERT INTO theses
            (ticker, direction, horizon, conviction,
             key_drivers, invalidation_triggers,
             entry_price, target_price, target_partial, target_full,
             triggers_profit_take, stop_price, notes,
             variant_perception, driver_epic, benchmark,
             opened_at, status, last_reviewed, last_revisit_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
            (
                ticker.upper(),
                direction,
                horizon,
                int(conviction),
                json.dumps(_to_list(key_drivers)),
                json.dumps(_to_list(invalidation_triggers)),
                float(entry_price),
                float(target_price) if target_price is not None else None,
                float(target_partial) if target_partial is not None else None,
                float(target_full) if target_full is not None else None,
                json.dumps(_to_list(triggers_profit_take)),
                float(stop_price) if stop_price is not None else None,
                notes,
                variant_perception,
                driver_epic,
                benchmark,
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
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM theses WHERE status = ? ORDER BY opened_at DESC", (status,)).fetchall()
        return [_parse_thesis_row(r) for r in rows]
    finally:
        conn.close()


def get_thesis(thesis_id):
    """Get a thesis by id. Returns dict or None."""
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM theses WHERE id = ?", (thesis_id,)).fetchone()
        return _parse_thesis_row(row) if row else None
    finally:
        conn.close()


def get_thesis_by_ticker(ticker, status="active"):
    """Get the active thesis for a ticker. Returns dict or None."""
    conn = _sqlite3.connect(DB_PATH)
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
    now = datetime.now(UTC).isoformat()
    conn = _sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE theses SET last_revisit_at = ? WHERE id = ?", (now, thesis_id))
        conn.commit()
    finally:
        conn.close()


def append_thesis_note(thesis_id, note):
    """Append a timestamped note to a thesis."""
    now = datetime.now(UTC).isoformat()
    conn = _sqlite3.connect(DB_PATH)
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
    now = datetime.now(UTC).isoformat()
    parts = [status.upper() + ":"]
    if exit_price is not None:
        parts.append(f"exit_price={exit_price}")
    if reason:
        parts.append(f"reason={reason}")
    note_line = " ".join(parts)
    conn = _sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT notes FROM theses WHERE id = ?", (thesis_id,)).fetchone()
        existing = (row[0] if row and row[0] else "") or ""
        new_notes = existing + ("\n" if existing else "") + f"[{now}] {note_line}"
        conn.execute("UPDATE theses SET status = ?, notes = ? WHERE id = ?", (status, new_notes, thesis_id))
        conn.commit()
    finally:
        conn.close()


def get_theses_due_for_revisit(days_threshold=30):
    """Return active theses due for revisit.

    Due = revisited longer ago than threshold, OR never revisited AND opened
    longer ago than threshold. Bug-fix 2026-05-22: previously treated NULL
    last_revisit_at as immediately due regardless of opened_at age, flagging
    fresh (5-day-old) theses for monthly revisit (blast radius = whole book).
    """
    cutoff = (datetime.now(UTC) - timedelta(days=days_threshold)).isoformat()
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT * FROM theses
               WHERE status = 'active'
                 AND (
                      (last_revisit_at IS NOT NULL AND last_revisit_at < ?)
                   OR (last_revisit_at IS NULL AND opened_at < ?)
                 )
               ORDER BY opened_at""",
            (cutoff, cutoff),
        ).fetchall()
        return [_parse_thesis_row(r) for r in rows]
    finally:
        conn.close()


# === Phase 2 Chunk 3 : Digest helpers ===


def get_unprocessed_signals(limit=20):
    """Get raw signals (emails) not yet scored. Returns list of dicts with source_name."""
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """UPDATE signals
               SET score = ?, sentiment = ?, entities = ?, narratives = ?, summary = ?
               WHERE id = ?""",
            (
                int(score),
                sentiment,
                json.dumps(tickers if isinstance(tickers, list) else []),
                json.dumps(narratives if isinstance(narratives, list) else []),
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
    conn = _sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE signals SET user_feedback = ? WHERE id = ?", (rating, signal_id))
        conn.commit()
    finally:
        conn.close()


def get_signal(signal_id):
    """Get a signal with source info joined."""
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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

    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM shadow_decisions WHERE resolved_at IS NULL ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def insert_prediction(
    signal_id,
    ticker,
    direction,
    horizon_days,
    baseline_price,
    baseline_date,
    target_date,
    *,
    methodology_version: str,
    score=None,
    signal_type=None,
    impact_magnitude=None,
    probability_override=None,
    scoring_trace_json=None,
    source_metadata_json=None,
):
    """Brier: probability_at_creation source determined by caller.

    ADR 014 § Hazard B (#98) : methodology_version est PARAMETRE EXPLICITE
    keyword-only. Pas de default = pas de silent-mistag possible. La colonne
    SQL n'a plus de DEFAULT (migration 0028) -- un caller qui oublierait
    crash a l'insert (defense en profondeur).

    Versioning:
    - V2 (signal_scorer_v2) : caller passes probability_override (LLM-elicited,
      base-rate-first, 3-step prompt). methodology_version='v2'.
    - V1 (estimate_probability) : si probability_override is None, fallback sur
      formule deterministe (cap [0.50, 0.72], bug mono-bucket 30/05).
      methodology_version='v1'. Conserve pour rollback / A-B futur.
    - rule_v1_shadow / rule_v1_fallback : #94/#96 RuleScorer, callers
      specifient explicitement.

    V1 path : score/signal_type/impact_magnitude threaded ; credibility re-queried.
    Si score is None et probability_override is None : NOT registered (floored
    0.50 polluerait Brier ledger, bug 27/05).
    """
    import logging as _logging

    from shared.math_helpers import estimate_probability

    if not methodology_version or not isinstance(methodology_version, str):
        # Garde explicite : meme si Python n'a pas force le typing, on echoue
        # loud plutot que silent-mistag. Doublure du schema sans-DEFAULT.
        raise ValueError(
            "insert_prediction: methodology_version is required and must be a non-empty str "
            "(ADR 014 hazard B fix). Pass 'v1', 'v2', 'rule_v1_shadow', etc. explicitly."
        )

    conn = _sqlite3.connect(DB_PATH)
    try:
        if probability_override is not None:
            # V2 path : trust caller's probability
            if not (0.0 <= probability_override <= 1.0):
                _logging.getLogger(__name__).error(
                    f"insert_prediction: probability_override={probability_override} out of [0,1]"
                )
                return None
            prob = round(float(probability_override), 4)
        else:
            # V1 path : formula
            if score is None:
                _logging.getLogger(__name__).error(
                    f"insert_prediction: score=None for signal {signal_id} ({ticker}) — "
                    "prediction NOT registered (floored 0.50 would pollute Brier ledger)"
                )
                return None
            row = conn.execute(
                "SELECT s.credibility FROM signals sig JOIN sources s ON sig.source_id = s.id WHERE sig.id = ?",
                (signal_id,),
            ).fetchone()
            credibility = row[0] if row else None
            prob = estimate_probability(score, credibility, signal_type, impact_magnitude)
        cur = conn.execute(
            "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, baseline_price, "
            "baseline_date, target_date, probability_at_creation, "
            "scoring_trace_json, source_metadata_json, methodology_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (signal_id, ticker, direction, horizon_days, baseline_price, baseline_date,
             target_date, prob, scoring_trace_json, source_metadata_json, methodology_version),
        )
        conn.commit()
        _pred_id = cur.lastrowid
        # Integrity chain commit-reveal -- post-commit, silent-miss (L7 pattern
        # cf lock_in hook). payload+nonce restent prives dans bot.db ; le ledger
        # public (integrity_anchor.sh) exporte hash chain seul.
        if _pred_id is None:
            # SQLite ne retourne lastrowid=None que sur INSERT echoue silencieux
            # (constraint violation pre-commit etc) -- fail-loud avant integrity.
            raise RuntimeError("insert_prediction: lastrowid is None (INSERT failed?)")
        try:
            record_prediction_integrity(conn, _pred_id)
        except Exception as _e:
            _logging.getLogger(__name__).warning(
                f"prediction_integrity silent miss for {_pred_id}: {_e}",
                exc_info=True,
            )
        return _pred_id
    finally:
        conn.close()


def get_prediction_provenance(pred_id: int) -> dict | None:
    """#70 + #74 -- Audit trail full per prediction.

    Returns dict {prediction, signal, source, scoring_trace, source_metadata}
    avec la chaine complete de provenance. None si pred_id introuvable.

    Sert le panneau loupe ticker (UI "pourquoi cette proba?") + l'audit
    externe (chaine reproductible bout en bout).
    """
    import json as _json
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        pred_row = conn.execute(
            "SELECT * FROM predictions WHERE id = ?", (pred_id,)
        ).fetchone()
        if not pred_row:
            return None
        pred = dict(pred_row)

        sig = None
        src = None
        if pred.get("signal_id"):
            sig_row = conn.execute(
                "SELECT * FROM signals WHERE id = ?", (pred["signal_id"],)
            ).fetchone()
            if sig_row:
                sig = dict(sig_row)
                if sig.get("source_id"):
                    src_row = conn.execute(
                        "SELECT * FROM sources WHERE id = ?", (sig["source_id"],)
                    ).fetchone()
                    if src_row:
                        src = dict(src_row)

        trace = None
        if pred.get("scoring_trace_json"):
            try:
                trace = _json.loads(pred["scoring_trace_json"])
            except (TypeError, ValueError):
                trace = None

        src_meta = None
        if pred.get("source_metadata_json"):
            try:
                src_meta = _json.loads(pred["source_metadata_json"])
            except (TypeError, ValueError):
                src_meta = None

        return {
            "prediction": pred,
            "signal": sig,
            "source": src,
            "scoring_trace": trace,
            "source_metadata": src_meta,
        }
    finally:
        conn.close()


def get_due_predictions(limit=50):
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM predictions WHERE target_date <= date('now') AND resolved_at IS NULL ORDER BY target_date ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def resolve_prediction_row(
    prediction_id, final_price, return_pct, outcome, credibility_delta,
    brier_score=None, source: str = "resolve_due_predictions", actor: str | None = None,
):
    """Phase A1 — Brier: stores brier_score at resolution time.

    PIT (ADR-001 + migration 0022) : log dans prediction_audit_log avant
    UPDATE. Premiere resolution -> 1 ligne event_type='resolve'. Re-resolution
    -> 2 lignes ('re_resolve_pre' + 're_resolve'). Audit-grade."""
    import json as _json

    conn = _sqlite3.connect(DB_PATH)
    try:
        prev = conn.execute(
            "SELECT resolved_at, final_price, return_pct, outcome, "
            "       credibility_delta, brier_score "
            "FROM predictions WHERE id=?",
            (prediction_id,),
        ).fetchone()
        is_reresolve = bool(prev and prev[0] is not None)
        if is_reresolve:
            conn.execute(
                "INSERT INTO prediction_audit_log "
                "(prediction_id, event_type, payload_json, source, actor) VALUES (?, ?, ?, ?, ?)",
                (
                    prediction_id, "re_resolve_pre",
                    _json.dumps({
                        "resolved_at": prev[0], "final_price": prev[1],
                        "return_pct": prev[2], "outcome": prev[3],
                        "credibility_delta": prev[4], "brier_score": prev[5],
                    }),
                    source, actor,
                ),
            )
        event_type = "re_resolve" if is_reresolve else "resolve"
        conn.execute(
            "INSERT INTO prediction_audit_log "
            "(prediction_id, event_type, payload_json, source, actor) VALUES (?, ?, ?, ?, ?)",
            (
                prediction_id, event_type,
                _json.dumps({
                    "final_price": final_price, "return_pct": return_pct,
                    "outcome": outcome, "credibility_delta": credibility_delta,
                    "brier_score": brier_score,
                }),
                source, actor,
            ),
        )
        conn.execute(
            "UPDATE predictions SET resolved_at=CURRENT_TIMESTAMP, final_price=?, return_pct=?, "
            "outcome=?, credibility_delta=?, brier_score=? WHERE id=?",
            (final_price, return_pct, outcome, credibility_delta, brier_score, prediction_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_predictions(limit=20):
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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

    if horizon_days not in (30, 90):
        raise ValueError("horizon_days must be 30 or 90")
    suffix = f"{horizon_days}d"
    conn = _sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            f"UPDATE decisions SET resolved_{suffix}_at = ?, price_{suffix} = ?, "
            f"return_{suffix}_pct = ?, thesis_relative_{suffix} = ?, "
            f"mistake_tag_auto = COALESCE(mistake_tag_auto, ?) "
            f"WHERE id = ?",
            (
                _naive_utc_iso(),
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE decisions SET mistake_tag_manual = ? WHERE id = ?", (manual_tag, decision_id))
        conn.commit()
    finally:
        conn.close()


def get_journal_stats():
    """Aggregate stats over resolved decisions."""
    conn = _sqlite3.connect(DB_PATH)
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


def recalibrate_source_credibility_from_hitrate(min_n=10):
    """Phase A1 — Cron mensuel: sources.credibility = hit-rate correct/(correct+incorrect) + shrinkage Beta(2,2) vers 0.5 (ex 1-mean(brier), recalibre 2026-05-23)
    for sources with N>=min_n resolved predictions.
    Returns dict of updates applied {source_name: (old_cred, new_cred, n)}.
    """
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT s.id AS source_id, s.name AS source_name, s.credibility AS old_cred,
                   SUM(CASE WHEN p.outcome='correct' THEN 1 ELSE 0 END) AS n_correct, SUM(CASE WHEN p.outcome='incorrect' THEN 1 ELSE 0 END) AS n_incorrect,
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
        from shared import math_helpers

        updates = {}
        for r in rows:
            new_cred = math_helpers.credibility_from_hitrate(r["n_correct"], r["n_incorrect"])
            conn.execute("UPDATE sources SET credibility = ? WHERE id = ?", (new_cred, r["source_id"]))
            updates[r["source_name"]] = (r["old_cred"], new_cred, r["n"])
        conn.commit()
        return updates
    finally:
        conn.close()


def get_brier_stats_by_source():
    """Phase A1 — Return per-source Brier stats for /sources_brier handler."""
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT embedding FROM signal_embeddings WHERE signal_id=?", (signal_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_unembedded_signals(limit=100, min_chars=20):
    """Phase A3 — Signals without embedding. Uses summary or fallback title."""
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE signals SET echo_cluster_id=? WHERE id=?", (cluster_id, signal_id))
        conn.commit()
    finally:
        conn.close()


def get_signals_by_source_with_tickers(source_id):
    """Phase A4 — Signals from source with non-empty entities (tickers)."""
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    """OBSOLÈTE depuis migration 0048 : positions est une VUE dérivée.

    Cf SPEC_LEDGER §1 : pour ingérer un buy, INSERT INTO transactions
    (side='BUY', ...) via shared.positions.add_buy().
    """
    raise NotImplementedError(
        "create_or_update_position_on_buy: positions est une VUE (migration 0048). "
        "INSERT INTO transactions (side='BUY', ...) à la place. Cf SPEC_LEDGER §1."
    )


def record_position_sell(ticker, qty, price):
    """OBSOLÈTE depuis migration 0048 : positions est une VUE.

    Cf SPEC_LEDGER §1 : pour ingérer une vente, INSERT INTO transactions
    (side='SELL', ...) via shared.positions.add_sell().
    """
    raise NotImplementedError(
        "record_position_sell: positions est une VUE (migration 0048). "
        "INSERT INTO transactions (side='SELL', ...) à la place. Cf SPEC_LEDGER §1."
    )


def get_active_positions():
    """Phase B5 — Active positions (status='open')."""
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM positions WHERE status='open' ORDER BY opened_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_position_by_ticker(ticker):
    """Phase B5 — Active position for ticker, or None."""
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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


def get_latest_decision():
    """Return (id, ticker, decision_type, reasoning) of the most recent decision, or None."""
    conn = _sqlite3.connect(DB_PATH)
    try:
        return conn.execute(
            "SELECT id, ticker, decision_type, reasoning FROM decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()


def get_decision_brief(decision_id):
    """Return (id, ticker, decision_type, reasoning) for a specific decision, or None."""
    conn = _sqlite3.connect(DB_PATH)
    try:
        return conn.execute(
            "SELECT id, ticker, decision_type, reasoning FROM decisions WHERE id=?",
            (decision_id,),
        ).fetchone()
    finally:
        conn.close()


def update_decision_reasoning(decision_id, reasoning):
    """Replace the reasoning field of a decision row. Returns True if a row was affected."""
    conn = _sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            "UPDATE decisions SET reasoning=? WHERE id=?",
            (reasoning, decision_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_decision_bias_tags(decision_id, tags):
    """Phase B6 — Persist bias_tags JSON array on a decision."""
    import json as _json

    conn = _sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE decisions SET bias_tags=? WHERE id=?", (_json.dumps(tags) if tags else None, decision_id))
        conn.commit()
    finally:
        conn.close()


def get_bias_stats(ticker=None, since_days=180):
    """Phase B6 — Aggregate bias frequencies across resolved or unresolved decisions."""
    import json as _json

    conn = _sqlite3.connect(DB_PATH)
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
        counts: dict[str, int] = {}
        type_counts: dict[str, dict[str, int]] = {}
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
    conn = _sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE theses SET pre_mortem=? WHERE id=?", (pre_mortem_json, thesis_id))
        conn.commit()
    finally:
        conn.close()


def get_thesis_pre_mortem(thesis_id):
    """Phase B7 — Fetch pre-mortem JSON string for a thesis."""
    conn = _sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT pre_mortem FROM theses WHERE id=?", (thesis_id,)).fetchone()
        return row[0] if row and row[0] else None
    finally:
        conn.close()


def get_thesis_full(thesis_id):
    """Phase B7 — Full thesis row for pre-mortem context."""
    conn = _sqlite3.connect(DB_PATH)
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

    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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

    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM filings_8k_log WHERE accession_number=?", (accession,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_recent_8k_filings_db(ticker=None, severity=None, days=60, limit=50):
    """Phase C9 — Query 8-K log with optional ticker/severity filters."""
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        q = "SELECT * FROM filings_8k_log WHERE date(filed_at) >= date('now', ?)"
        params: list[Any] = [f"-{int(days)} days"]
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

    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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

    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE signals SET signal_type=? WHERE id=?", (signal_type, signal_id))
        conn.commit()
    finally:
        conn.close()


def get_unclassified_signals(limit=50):
    """Phase Digestion — fetch signals with signal_type=NULL for classifier cron."""
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
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
    conn = _sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE signals SET materiality_boost=? WHERE id=?", (float(boost), signal_id))
        conn.commit()
    finally:
        conn.close()


def get_signals_in_cluster_with_sources(cluster_id):
    """Phase Digestion — distinct sources count for echo cluster."""
    conn = _sqlite3.connect(DB_PATH)
    try:
        n = conn.execute(
            "SELECT COUNT(DISTINCT source_id) FROM signals WHERE echo_cluster_id=?", (int(cluster_id),)
        ).fetchone()[0]
        return int(n)
    finally:
        conn.close()


def bootstrap_schema(db_path: str | None = None, alembic_ini: str | None = None) -> None:
    """Idempotently bootstrap the DB schema to head (latest migration).

    Equivalent to `alembic upgrade head` programmatically. Use this:
    - In tests that need a fresh DB
    - In CI environments where DB doesn't exist
    - On fresh installs / new deployments
    - In migration scripts that need to ensure baseline

    Args:
        db_path: Path to SQLite DB file. If None, uses default from alembic.ini.
        alembic_ini: Path to alembic.ini. If None, finds it at project root.

    Sprint 1.3 deliverable. Sole entry point for non-runtime DB creation.
    """
    from pathlib import Path as _Path

    from alembic import command
    from alembic.config import Config

    if alembic_ini is None:
        # Default: alembic.ini at project root (parent of shared/)
        alembic_ini = str(_Path(__file__).resolve().parent.parent / "alembic.ini")

    config = Config(alembic_ini)
    if db_path:
        config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(config, "head")

    # Set WAL mode for concurrent reads (matches bot runtime config)
    import sqlite3 as _sqlite3

    target_db = db_path or config.get_main_option("sqlalchemy.url", "").replace("sqlite:///", "")
    if target_db:
        conn = _sqlite3.connect(target_db)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.close()


def compute_drift_report() -> dict:
    """Compute drift between portfolio_targets (active) and positions (open) per account.

    Returns dict with structure:
      {
        "PEA": {
          "rows": [{ticker, target_eur, actual_eur, drift_eur, status, ...}, ...],
          "total_target": float,
          "total_actual": float,
          "total_drift": float,
        },
        "TR": {...},
        "summary": {
          "capital_deployed_eur": float,
          "capital_pending_eur": float,
          "capital_target_eur": float,
          "pct_deployed": float,
        }
      }
    """
    with db() as cx:
        targets = cx.execute(
            "SELECT ticker, account, target_eur, status, priority, phase_week, narrative, bucket "
            "FROM portfolio_targets WHERE active_to IS NULL ORDER BY account, target_eur DESC"
        ).fetchall()

        # Post-0049 : VUE.avg_cost = NULL fail-closed. Récupère qty + account
        # depuis la VUE, PMP via helper rolling (PMP fiscal FR correct).
        from shared.ledger_pmp import compute_pmp_realized
        positions_meta_rows = cx.execute(
            "SELECT ticker, account, qty FROM positions WHERE status='open' AND qty > 0"
        ).fetchall()
        actual_by_key: dict = {}
        for r in positions_meta_rows:
            ticker, account, qty = r["ticker"], r["account"], r["qty"]
            if not (qty and account):
                continue
            pmp = compute_pmp_realized(cx, ticker)
            if pmp.pmp_eur:
                key = (ticker, account)
                actual_by_key[key] = actual_by_key.get(key, 0.0) + (qty * pmp.pmp_eur)

    by_account: dict = {}
    for t in targets:
        acc = t["account"]
        if acc not in by_account:
            by_account[acc] = {"rows": [], "total_target": 0.0, "total_actual": 0.0, "total_drift": 0.0}
        actual = actual_by_key.get((t["ticker"], acc), 0.0) or 0.0
        drift = t["target_eur"] - actual
        by_account[acc]["rows"].append(
            {
                "ticker": t["ticker"],
                "target_eur": t["target_eur"],
                "actual_eur": actual,
                "drift_eur": drift,
                "status": t["status"],
                "priority": t["priority"],
                "phase_week": t["phase_week"],
                "narrative": t["narrative"],
                "bucket": t["bucket"],
            }
        )
        by_account[acc]["total_target"] += t["target_eur"]
        by_account[acc]["total_actual"] += actual
        by_account[acc]["total_drift"] += drift

    # Add positions without target (orphan holdings)
    target_keys = {(t["ticker"], t["account"]) for t in targets}
    for (ticker, acc), actual in actual_by_key.items():
        if (ticker, acc) not in target_keys:
            if acc not in by_account:
                by_account[acc] = {"rows": [], "total_target": 0.0, "total_actual": 0.0, "total_drift": 0.0}
            by_account[acc]["rows"].append(
                {
                    "ticker": ticker,
                    "target_eur": 0.0,
                    "actual_eur": actual,
                    "drift_eur": -actual,
                    "status": "orphan_no_target",
                    "priority": None,
                    "phase_week": None,
                    "narrative": None,
                    "bucket": None,
                }
            )
            by_account[acc]["total_actual"] += actual
            by_account[acc]["total_drift"] -= actual

    total_target = sum(a["total_target"] for a in by_account.values())
    total_actual = sum(a["total_actual"] for a in by_account.values())
    pct_deployed = (total_actual / total_target * 100.0) if total_target > 0 else 0.0

    return {
        **by_account,
        "summary": {
            "capital_deployed_eur": total_actual,
            "capital_pending_eur": total_target - total_actual,
            "capital_target_eur": total_target,
            "pct_deployed": pct_deployed,
        },
    }


def get_signals_for_ticker(ticker, days=30, limit=8):
    """Get recent signals mentioning ticker, weighted by source_credibility * materiality_v2.

    Returns list of dicts sorted by weighted_score desc, capped at limit.
    Uses LIKE match against entities JSON, then Python-side parse for false-positive elimination.
    P0 of /risk_check v2 roadmap (docs/risk_check_v2_roadmap.md).
    """
    import json

    ticker_up = ticker.upper()
    json_match = f'%"{ticker_up}"%'

    with db() as conn:
        rows = conn.execute(
            """SELECT s.id, s.title, s.summary, s.signal_type, s.sentiment,
                      s.score, s.materiality_boost, s.timestamp, s.echo_cluster_id, s.entities,
                      s.impact_magnitude, s.reversibility,
                      src.name AS source_name, src.credibility AS source_credibility
               FROM signals s
               LEFT JOIN sources src ON s.source_id = src.id
               WHERE s.entities LIKE ?
                 AND s.timestamp > datetime('now', '-' || ? || ' days')
                 AND s.entities IS NOT NULL
                 AND s.entities != ''
                 AND s.entities != '[]'
               ORDER BY (COALESCE(s.score, 50) * COALESCE(s.materiality_boost, 1.0) * COALESCE(src.credibility, 0.5)) DESC
               LIMIT ?""",
            (json_match, days, limit * 2),
        ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        entities_str = d.get("entities") or "[]"
        try:
            entities_list = json.loads(entities_str)
            if isinstance(entities_list, list):
                upper_list = [e.upper() if isinstance(e, str) else "" for e in entities_list]
                if ticker_up in upper_list:
                    cred = d.get("source_credibility") or 0.5
                    score = d.get("score") or 50
                    boost = d.get("materiality_boost") or 1.0
                    mat = score * boost / 100.0
                    d["materiality"] = mat
                    d["weighted_score"] = cred * mat
                    results.append(d)
        except (json.JSONDecodeError, TypeError):
            continue
        if len(results) >= limit:
            break

    return results


def build_signals_context_block(ticker: str) -> str:
    """Public formatter: top-N weighted signals on ticker as text block for LLM prompts.

    P0 of /risk_check v2 roadmap. Single source of truth, consumed by:
    - run_risk_check (intelligence/risk_manager)
    - analyze_stock.build_prompt (intelligence/analyze)
    """
    import logging

    log = logging.getLogger(__name__)
    try:
        signals = get_signals_for_ticker(ticker, days=30, limit=8) or []
    except Exception as e:
        log.warning(f"signals query {ticker} failed: {e}")
        return "Signal query failed; no recent signals context available."
    if not signals:
        return f"No recent signals on {ticker} in past 30 days from monitored sources."
    lines = [f"Top {len(signals)} weighted signals on {ticker} (last 30d, by credibility x materiality):"]
    for s in signals:
        date = (s.get("timestamp") or "")[:10]
        source = s.get("source_name") or "unknown"
        cred = s.get("source_credibility") or 0.5
        tier = "S" if cred >= 0.7 else "A" if cred >= 0.5 else "B" if cred >= 0.3 else "?"
        mat = s.get("materiality") or 0.5
        sentiment = s.get("sentiment") or "neutral"
        sig_type = s.get("signal_type") or "?"
        title = (s.get("title") or "")[:100]
        weighted = s.get("weighted_score", cred * mat)
        lines.append(
            f"  - [{date}] {source} (Tier {tier}, cred {cred:.2f}) {sig_type}/{sentiment} mat={mat:.2f} -> {title} [w={weighted:.2f}]"
        )
    return "\n".join(lines)


# === bot_copilot_interventions (Phase 1.5) ====================================

import logging as _copilot_logging

_copilot_log = _copilot_logging.getLogger("shared.storage.copilot")

_COPILOT_DDL = (
    "CREATE TABLE IF NOT EXISTS bot_copilot_interventions ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "ticker TEXT NOT NULL, decision_type TEXT NOT NULL, "
    "intent_reasoning TEXT, intent_price REAL, intent_qty REAL, "
    "thesis_id INTEGER, decision_id INTEGER, "
    "verdict TEXT, pressure_score INTEGER, ancrage TEXT, brief TEXT, "
    "biases_active_json TEXT, full_response_json TEXT, "
    "model_used TEXT, input_tokens INTEGER, output_tokens INTEGER, "
    "cost_usd REAL, elapsed_ms INTEGER, "
    "created_at TEXT NOT NULL DEFAULT (datetime('now')), "
    "resolved_30d_at TEXT, return_30d_pct REAL, outcome_label TEXT, "
    "FOREIGN KEY (thesis_id) REFERENCES theses(id), "
    "FOREIGN KEY (decision_id) REFERENCES decisions(id))"
)

_COPILOT_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_copilot_ticker ON bot_copilot_interventions(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_copilot_decision ON bot_copilot_interventions(decision_id)",
    "CREATE INDEX IF NOT EXISTS idx_copilot_created ON bot_copilot_interventions(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_copilot_unresolved ON bot_copilot_interventions(resolved_30d_at)",
]


def _ensure_copilot_table(conn: _sqlite3.Connection) -> None:
    """Defensive : ensure bot_copilot_interventions exists (idempotent).
    Belt-and-suspenders with alembic migration 0003."""
    conn.execute(_COPILOT_DDL)
    for ix in _COPILOT_IDX:
        conn.execute(ix)


def log_copilot_intervention(
    ticker: str,
    decision_type: str,
    intent_reasoning: str | None,
    intent_price: float | None,
    intent_qty: float | None,
    thesis_id: int | None,
    response: dict | None,
    llm_meta: dict | None = None,
) -> int | None:
    """Log a pre-trade co-pilot intervention. Returns intervention_id or None on failure."""
    import json as _json

    if response is None:
        # Still log : the fact that the copilot was invoked and failed is data too
        response = {}
    llm_meta = llm_meta or {}
    biases = response.get("biases_active") or []
    try:
        with db() as conn:
            _ensure_copilot_table(conn)
            cur = conn.execute(
                "INSERT INTO bot_copilot_interventions "
                "(ticker, decision_type, intent_reasoning, intent_price, intent_qty, thesis_id, "
                "verdict, pressure_score, ancrage, brief, biases_active_json, full_response_json, "
                "model_used, input_tokens, output_tokens, cost_usd, elapsed_ms) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ticker,
                    decision_type,
                    intent_reasoning,
                    intent_price,
                    intent_qty,
                    thesis_id,
                    response.get("verdict"),
                    response.get("pressure_score"),
                    response.get("ancrage"),
                    response.get("brief"),
                    _json.dumps(biases, ensure_ascii=False) if biases else None,
                    _json.dumps(response, ensure_ascii=False) if response else None,
                    llm_meta.get("model"),
                    llm_meta.get("input_tokens"),
                    llm_meta.get("output_tokens"),
                    llm_meta.get("cost_usd"),
                    llm_meta.get("elapsed_ms"),
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"log_copilot_intervention failed for {ticker} {decision_type}: {e}")
        return None


def link_copilot_intervention_decision(intervention_id: int, decision_id: int) -> None:
    """Back-link the intervention to the actual decision row created post-trade."""
    try:
        with db() as conn:
            conn.execute(
                "UPDATE bot_copilot_interventions SET decision_id=? WHERE id=?",
                (decision_id, intervention_id),
            )
    except Exception as e:
        _copilot_log.warning(f"link_copilot_intervention_decision failed id={intervention_id}: {e}")


def get_recent_copilot_interventions(limit: int = 20) -> list[dict]:
    """All-ticker recent interventions feed (for dashboard surface)."""
    try:
        with db() as conn:
            _ensure_copilot_table(conn)
            rows = conn.execute(
                "SELECT id, created_at, ticker, decision_type, verdict, pressure_score, "
                "ancrage, brief, return_30d_pct, outcome_label "
                "FROM bot_copilot_interventions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            cols = [
                "id", "created_at", "ticker", "decision_type", "verdict",
                "pressure_score", "ancrage", "brief", "return_30d_pct", "outcome_label",
            ]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        _copilot_log.warning(f"get_recent_copilot_interventions failed: {e}")
        return []


def get_recent_copilot_interventions_for_ticker(ticker: str, limit: int = 5) -> list[dict]:
    """For chat surface RAG : the bot's recent stances on this ticker."""
    try:
        with db() as conn:
            _ensure_copilot_table(conn)
            rows = conn.execute(
                "SELECT id, created_at, decision_type, verdict, pressure_score, ancrage, brief, "
                "biases_active_json, return_30d_pct, outcome_label "
                "FROM bot_copilot_interventions WHERE ticker=? "
                "ORDER BY created_at DESC LIMIT ?",
                (ticker, limit),
            ).fetchall()
            cols = [
                "id",
                "created_at",
                "decision_type",
                "verdict",
                "pressure_score",
                "ancrage",
                "brief",
                "biases_active_json",
                "return_30d_pct",
                "outcome_label",
            ]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        _copilot_log.warning(f"get_recent_copilot_interventions failed for {ticker}: {e}")
        return []


# === user_profile (Phase 2 Sprint 1) ==========================================

_USER_PROFILE_DDL = (
    "CREATE TABLE IF NOT EXISTS user_profile ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "refreshed_at TEXT NOT NULL DEFAULT (datetime('now')), "
    "profile_json TEXT NOT NULL, "
    "confidence_score INTEGER, "
    "n_decisions_used INTEGER, n_theses_used INTEGER, "
    "n_predictions_resolved_used INTEGER, n_signals_window INTEGER, "
    "data_window_start TEXT, data_window_end TEXT, "
    "model_used TEXT, input_tokens INTEGER, output_tokens INTEGER, "
    "cost_usd REAL, elapsed_ms INTEGER, notes TEXT)"
)
_USER_PROFILE_IDX = ["CREATE INDEX IF NOT EXISTS idx_user_profile_refreshed ON user_profile(refreshed_at)"]


def _ensure_user_profile_table(conn: _sqlite3.Connection) -> None:
    conn.execute(_USER_PROFILE_DDL)
    for ix in _USER_PROFILE_IDX:
        conn.execute(ix)


def insert_user_profile(profile_json: str, source_counts: dict, llm_meta: dict | None = None) -> int | None:
    """Insert a new user_profile snapshot (append-only). Returns id."""
    llm_meta = llm_meta or {}
    try:
        with db() as conn:
            _ensure_user_profile_table(conn)
            cur = conn.execute(
                "INSERT INTO user_profile "
                "(profile_json, confidence_score, n_decisions_used, n_theses_used, "
                "n_predictions_resolved_used, n_signals_window, data_window_start, "
                "data_window_end, model_used, input_tokens, output_tokens, cost_usd, "
                "elapsed_ms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    profile_json,
                    source_counts.get("confidence_score"),
                    source_counts.get("n_decisions"),
                    source_counts.get("n_theses"),
                    source_counts.get("n_predictions_resolved"),
                    source_counts.get("n_signals_window"),
                    source_counts.get("window_start"),
                    source_counts.get("window_end"),
                    llm_meta.get("model"),
                    llm_meta.get("input_tokens"),
                    llm_meta.get("output_tokens"),
                    llm_meta.get("cost_usd"),
                    llm_meta.get("elapsed_ms"),
                    source_counts.get("notes"),
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_user_profile failed: {e}")
        return None


def get_latest_user_profile() -> dict | None:
    """Read the most recent user_profile snapshot. Returns dict with profile + meta."""
    try:
        with db() as conn:
            _ensure_user_profile_table(conn)
            row = conn.execute(
                "SELECT id, refreshed_at, profile_json, confidence_score, n_decisions_used, "
                "n_theses_used, n_predictions_resolved_used, n_signals_window "
                "FROM user_profile ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "refreshed_at": row[1],
                "profile_json": row[2],
                "confidence_score": row[3],
                "n_decisions_used": row[4],
                "n_theses_used": row[5],
                "n_predictions_resolved_used": row[6],
                "n_signals_window": row[7],
            }
    except Exception as e:
        _copilot_log.warning(f"get_latest_user_profile failed: {e}")
        return None


def fetch_pending_copilot_resolutions(limit: int = 100) -> list[dict]:
    """Sprint 4 — fetch interventions older than 30d still unresolved, joined with decisions return."""
    try:
        with db() as cx:
            _ensure_copilot_table(cx)
            rows = cx.execute(
                "SELECT i.id, i.verdict, i.decision_type, i.decision_id, "
                "d.return_30d_pct "
                "FROM bot_copilot_interventions i "
                "LEFT JOIN decisions d ON d.id = i.decision_id "
                "WHERE i.resolved_30d_at IS NULL "
                "AND i.created_at <= datetime('now', '-30 day') "
                "LIMIT ?",
                (limit,),
            ).fetchall()
            cols = ["id", "verdict", "decision_type", "decision_id", "return_30d_pct"]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        _copilot_log.warning(f"fetch_pending_copilot_resolutions failed: {e}")
        return []


def resolve_copilot_intervention(intervention_id: int, return_pct: float | None, outcome_label: str) -> None:
    """Sprint 4 — Mark an intervention as resolved with 30d outcome."""
    try:
        with db() as cx:
            cx.execute(
                "UPDATE bot_copilot_interventions SET resolved_30d_at=datetime('now'), "
                "return_30d_pct=?, outcome_label=? WHERE id=?",
                (return_pct, outcome_label, intervention_id),
            )
    except Exception as e:
        _copilot_log.warning(f"resolve_copilot_intervention {intervention_id} failed: {e}")


# === portfolio_grades (Sprint 5) =============================================

_GRADE_DDL = (
    "CREATE TABLE IF NOT EXISTS portfolio_grades ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "snapshot_at TEXT NOT NULL DEFAULT (datetime('now')), "
    "snapshot_date TEXT NOT NULL, "
    "overall_score INTEGER NOT NULL, overall_grade TEXT NOT NULL, "
    "dimensions_json TEXT NOT NULL, "
    "total_capital_eur REAL, n_positions INTEGER, n_theses_active INTEGER, "
    "computation_version TEXT NOT NULL DEFAULT 'sprint5_deterministic', "
    "notes TEXT)"
)
_GRADE_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_grade_date ON portfolio_grades(snapshot_date)",
    "CREATE INDEX IF NOT EXISTS idx_grade_snapshot_at ON portfolio_grades(snapshot_at)",
]


def _ensure_grade_table(conn: _sqlite3.Connection) -> None:
    conn.execute(_GRADE_DDL)
    for ix in _GRADE_IDX:
        conn.execute(ix)


def insert_portfolio_grade(grade: dict) -> int | None:
    """Insert a portfolio grade snapshot. Returns id."""
    try:
        with db() as cx:
            _ensure_grade_table(cx)
            cur = cx.execute(
                "INSERT INTO portfolio_grades "
                "(snapshot_date, overall_score, overall_grade, dimensions_json, "
                "total_capital_eur, n_positions, n_theses_active, computation_version) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    grade.get("snapshot_date"),
                    grade.get("overall_score"),
                    grade.get("overall_grade"),
                    __import__("json").dumps(grade.get("dimensions") or {}, ensure_ascii=False),
                    grade.get("total_capital_eur"),
                    grade.get("n_positions"),
                    grade.get("n_theses_active"),
                    grade.get("computation_version", "sprint5_deterministic"),
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_portfolio_grade failed: {e}")
        return None


def get_latest_portfolio_grade() -> dict | None:
    try:
        with db() as cx:
            _ensure_grade_table(cx)
            row = cx.execute(
                "SELECT id, snapshot_date, overall_score, overall_grade, dimensions_json, "
                "total_capital_eur, n_positions, n_theses_active "
                "FROM portfolio_grades ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "snapshot_date": row[1],
                "overall_score": row[2],
                "overall_grade": row[3],
                "dimensions_json": row[4],
                "total_capital_eur": row[5],
                "n_positions": row[6],
                "n_theses_active": row[7],
            }
    except Exception as e:
        _copilot_log.warning(f"get_latest_portfolio_grade failed: {e}")
        return None


def get_portfolio_grade_n_days_ago(days: int) -> dict | None:
    """Returns the most recent grade snapshot from approximately N days ago."""
    try:
        with db() as cx:
            _ensure_grade_table(cx)
            row = cx.execute(
                "SELECT id, snapshot_date, overall_score, overall_grade "
                "FROM portfolio_grades "
                "WHERE snapshot_date <= date('now', ?) "
                "ORDER BY snapshot_date DESC LIMIT 1",
                (f"-{days} day",),
            ).fetchone()
            if not row:
                return None
            return {"id": row[0], "snapshot_date": row[1], "overall_score": row[2], "overall_grade": row[3]}
    except Exception as e:
        _copilot_log.warning(f"get_portfolio_grade_n_days_ago({days}) failed: {e}")
        return None


# === portfolio_narrative_clusters (Sprint 6) =================================

_NARRATIVE_DDL = (
    "CREATE TABLE IF NOT EXISTS portfolio_narrative_clusters ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "snapshot_at TEXT NOT NULL DEFAULT (datetime('now')), "
    "snapshot_date TEXT NOT NULL, "
    "clusters_json TEXT NOT NULL, "
    "edges_json TEXT NOT NULL, "
    "model_used TEXT, input_tokens INTEGER, output_tokens INTEGER, "
    "cost_usd REAL, elapsed_ms INTEGER, notes TEXT)"
)


def _ensure_narrative_table(conn: _sqlite3.Connection) -> None:
    conn.execute(_NARRATIVE_DDL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_narrative_cluster_date "
        "ON portfolio_narrative_clusters(snapshot_date)"
    )


def insert_narrative_snapshot(snapshot_date: str, clusters_json: str, edges_json: str) -> int | None:
    """Sprint 6 — store an LLM narrative cluster snapshot. Returns id."""
    try:
        with db() as cx:
            _ensure_narrative_table(cx)
            cur = cx.execute(
                "INSERT INTO portfolio_narrative_clusters "
                "(snapshot_date, clusters_json, edges_json) VALUES (?,?,?)",
                (snapshot_date, clusters_json, edges_json),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_narrative_snapshot failed: {e}")
        return None


def get_latest_narrative_snapshot() -> dict | None:
    try:
        with db() as cx:
            _ensure_narrative_table(cx)
            row = cx.execute(
                "SELECT id, snapshot_date, clusters_json, edges_json "
                "FROM portfolio_narrative_clusters ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "snapshot_date": row[1],
                "clusters_json": row[2],
                "edges_json": row[3],
            }
    except Exception as e:
        _copilot_log.warning(f"get_latest_narrative_snapshot failed: {e}")
        return None


# === chat_messages (Sprint 9) ================================================

_CHAT_DDL = (
    "CREATE TABLE IF NOT EXISTS chat_messages ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "created_at TEXT NOT NULL DEFAULT (datetime('now')), "
    "session_id TEXT, "
    "surface TEXT NOT NULL, "
    "role TEXT NOT NULL, "
    "content TEXT NOT NULL, "
    "model_used TEXT, input_tokens INTEGER, output_tokens INTEGER, "
    "cost_usd REAL, latency_ms INTEGER, error TEXT)"
)
_CHAT_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(created_at)",
]


def _ensure_chat_table(conn: _sqlite3.Connection) -> None:
    conn.execute(_CHAT_DDL)
    for ix in _CHAT_IDX:
        conn.execute(ix)


def insert_chat_message(
    surface: str,
    role: str,
    content: str,
    session_id: str | None = None,
    llm_meta: dict | None = None,
) -> int | None:
    """Persist a chat turn. surface = 'dashboard' | 'telegram'. role = 'user' | 'assistant'."""
    meta = llm_meta or {}
    try:
        with db() as cx:
            _ensure_chat_table(cx)
            cur = cx.execute(
                "INSERT INTO chat_messages "
                "(session_id, surface, role, content, model_used, input_tokens, "
                "output_tokens, cost_usd, latency_ms, error) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    surface,
                    role,
                    content,
                    meta.get("model_used"),
                    meta.get("input_tokens"),
                    meta.get("output_tokens"),
                    meta.get("cost_usd"),
                    meta.get("latency_ms"),
                    meta.get("error"),
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_chat_message failed: {e}")
        return None


def get_recent_chat_messages(limit: int = 50, session_id: str | None = None) -> list[dict]:
    """Read recent chat turns (newest first). Filter by session if given."""
    try:
        with db() as cx:
            _ensure_chat_table(cx)
            if session_id:
                rows = cx.execute(
                    "SELECT id, created_at, session_id, surface, role, content "
                    "FROM chat_messages WHERE session_id=? "
                    "ORDER BY id DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = cx.execute(
                    "SELECT id, created_at, session_id, surface, role, content "
                    "FROM chat_messages ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            cols = ["id", "created_at", "session_id", "surface", "role", "content"]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        _copilot_log.warning(f"get_recent_chat_messages failed: {e}")
        return []


def get_chat_session_history(session_id: str, limit: int = 20) -> list[dict]:
    """Get a single session's turns in chronological order (for multi-turn restore)."""
    try:
        with db() as cx:
            _ensure_chat_table(cx)
            rows = cx.execute(
                "SELECT role, content FROM chat_messages "
                "WHERE session_id=? ORDER BY id ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            return [{"role": r[0], "content": r[1]} for r in rows]
    except Exception as e:
        _copilot_log.warning(f"get_chat_session_history failed: {e}")
        return []


# === thesis_set chat-driven (Sprint 9.c) =====================================

_THESIS_FIELD_NUM = {"target_price", "target_partial", "target_full", "stop_price", "entry_price", "conviction"}
_THESIS_FIELD_TEXT = {"notes", "horizon", "key_drivers", "invalidation_triggers", "triggers_profit_take", "status", "direction"}


def update_thesis_field(ticker: str, field: str, value) -> tuple[bool, str, object]:
    """Update one editable field on the active thesis for ticker.

    Returns (success, message, old_value). Used by /thesis_set Telegram handler
    AND chat-driven set_field intent — single write surface (CONVENTIONS §5).

    Hook drift conviction (Carte-decision #1 etape 1) : si field='conviction' ET
    nouvelle valeur != old, append au thesis_integrity_log (event=conviction_drift)
    avec old/new + asof. Tamper-evident : le drift conviction silencieux
    (moteur biais #1 lock-in) laisse une trace dans la chain.
    NB : conviction_at_entry n'est JAMAIS touche par cette fonction (snapshot
    PIT immuable, set seulement a l'INSERT initial).
    """
    field_lc = (field or "").lower()
    if field_lc not in _THESIS_FIELD_NUM | _THESIS_FIELD_TEXT:
        return False, f"field '{field}' non editable", None
    if field_lc in _THESIS_FIELD_NUM:
        try:
            value = float(value) if field_lc != "conviction" else int(value)
        except (TypeError, ValueError):
            return False, f"valeur '{value}' invalide pour {field}", None
    thesis_id = None
    old_val = None
    new_val = value
    with db() as cx:
        r = cx.execute(
            "SELECT id FROM theses WHERE ticker=? AND status='active'",
            (ticker.upper(),),
        ).fetchone()
        if not r:
            return False, f"pas de these active sur {ticker}", None
        thesis_id = r["id"]
        old = cx.execute(f"SELECT {field_lc} FROM theses WHERE id=?", (thesis_id,)).fetchone()
        old_val = old[0] if old else None
        cx.execute(
            f"UPDATE theses SET {field_lc}=?, last_reviewed=CURRENT_TIMESTAMP WHERE id=?",
            (value, thesis_id),
        )
        cx.commit()

    # Hook drift conviction : append integrity log si changement effectif
    if field_lc == "conviction" and old_val is not None and int(old_val) != int(new_val):
        from datetime import UTC as _UTC, datetime as _datetime
        payload = {
            "event": "conviction_drift",
            "thesis_id": thesis_id,
            "ticker": ticker.upper(),
            "old_conviction": int(old_val),
            "new_conviction": int(new_val),
            "delta": int(new_val) - int(old_val),
            "asof": _datetime.now(_UTC).isoformat(timespec="seconds"),
        }
        try:
            insert_thesis_integrity_row(thesis_id, payload)
        except Exception as e:
            _copilot_log.warning(f"conviction drift hook failed: {e}")

    return True, f"{ticker} {field_lc} : {old_val} → {value}", old_val


# === chat_extracted_signals (Sprint 9.d) =====================================

_CES_DDL = (
    "CREATE TABLE IF NOT EXISTS chat_extracted_signals ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "created_at TEXT NOT NULL DEFAULT (datetime('now')), "
    "chat_message_id INTEGER, "
    "kind TEXT NOT NULL, "
    "ticker TEXT, sector TEXT, theme TEXT, "
    "valence REAL, confidence REAL, "
    "evidence_quote TEXT, note TEXT, "
    "model_used TEXT, cost_usd REAL)"
)
_CES_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_ces_ticker ON chat_extracted_signals(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_ces_kind ON chat_extracted_signals(kind)",
    "CREATE INDEX IF NOT EXISTS idx_ces_created ON chat_extracted_signals(created_at)",
]


def _ensure_ces_table(conn: _sqlite3.Connection) -> None:
    conn.execute(_CES_DDL)
    for ix in _CES_IDX:
        conn.execute(ix)


def insert_chat_signal(
    chat_message_id: int | None,
    kind: str,
    ticker: str | None = None,
    sector: str | None = None,
    theme: str | None = None,
    valence: float | None = None,
    confidence: float | None = None,
    evidence_quote: str | None = None,
    note: str | None = None,
    llm_meta: dict | None = None,
) -> int | None:
    meta = llm_meta or {}
    try:
        with db() as cx:
            _ensure_ces_table(cx)
            cur = cx.execute(
                "INSERT INTO chat_extracted_signals "
                "(chat_message_id, kind, ticker, sector, theme, valence, confidence, "
                "evidence_quote, note, model_used, cost_usd) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    chat_message_id, kind, ticker, sector, theme, valence,
                    confidence, evidence_quote, note,
                    meta.get("model_used"), meta.get("cost_usd"),
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_chat_signal failed: {e}")
        return None


def get_recent_chat_signals(limit: int = 50, ticker: str | None = None, kind: str | None = None) -> list[dict]:
    try:
        with db() as cx:
            _ensure_ces_table(cx)
            q = (
                "SELECT id, created_at, chat_message_id, kind, ticker, sector, theme, "
                "valence, confidence, evidence_quote, note "
                "FROM chat_extracted_signals"
            )
            conds = []
            params: list = []
            if ticker:
                conds.append("ticker=?")
                params.append(ticker)
            if kind:
                conds.append("kind=?")
                params.append(kind)
            if conds:
                q += " WHERE " + " AND ".join(conds)
            q += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = cx.execute(q, params).fetchall()
            cols = [
                "id", "created_at", "chat_message_id", "kind", "ticker", "sector",
                "theme", "valence", "confidence", "evidence_quote", "note",
            ]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        _copilot_log.warning(f"get_recent_chat_signals failed: {e}")
        return []


# === bot_conceptions (Layer 2 — Sprint 10) ===================================

_CONC_DDL = (
    "CREATE TABLE IF NOT EXISTS bot_conceptions ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "created_at TEXT NOT NULL DEFAULT (datetime('now')), "
    "kind TEXT NOT NULL, target_key TEXT NOT NULL, "
    "conception_text TEXT NOT NULL, "
    "conviction INTEGER NOT NULL, valence REAL, "
    "sources_json TEXT, n_signals_used INTEGER, "
    "model_used TEXT, input_tokens INTEGER, output_tokens INTEGER, "
    "cost_usd REAL, elapsed_ms INTEGER)"
)
_CONC_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_conc_kind_target ON bot_conceptions(kind, target_key)",
    "CREATE INDEX IF NOT EXISTS idx_conc_created ON bot_conceptions(created_at)",
]


def _ensure_conc_table(conn: _sqlite3.Connection) -> None:
    conn.execute(_CONC_DDL)
    for ix in _CONC_IDX:
        conn.execute(ix)


def insert_bot_conception(
    kind: str,
    target_key: str,
    conception_text: str,
    conviction: int,
    valence: float | None = None,
    sources_json: str | None = None,
    n_signals_used: int | None = None,
    llm_meta: dict | None = None,
) -> int | None:
    meta = llm_meta or {}
    try:
        with db() as cx:
            _ensure_conc_table(cx)
            cur = cx.execute(
                "INSERT INTO bot_conceptions "
                "(kind, target_key, conception_text, conviction, valence, sources_json, "
                "n_signals_used, model_used, input_tokens, output_tokens, cost_usd, elapsed_ms) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    kind, target_key, conception_text, conviction, valence,
                    sources_json, n_signals_used,
                    meta.get("model_used"), meta.get("input_tokens"),
                    meta.get("output_tokens"), meta.get("cost_usd"), meta.get("elapsed_ms"),
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_bot_conception failed: {e}")
        return None


def get_latest_conception(kind: str, target_key: str) -> dict | None:
    """Return the most recent conception for (kind, target_key)."""
    try:
        with db() as cx:
            _ensure_conc_table(cx)
            row = cx.execute(
                "SELECT id, created_at, conception_text, conviction, valence, "
                "sources_json, n_signals_used "
                "FROM bot_conceptions WHERE kind=? AND target_key=? "
                "ORDER BY id DESC LIMIT 1",
                (kind, target_key),
            ).fetchone()
            if not row:
                return None
            cols = ["id", "created_at", "conception_text", "conviction", "valence",
                    "sources_json", "n_signals_used"]
            return dict(zip(cols, row, strict=False))
    except Exception as e:
        _copilot_log.warning(f"get_latest_conception failed: {e}")
        return None


def get_all_current_conceptions(kind: str | None = None) -> list[dict]:
    """Return one row per (kind, target_key) — the latest version of each.

    Uses MAX(id) per group. Optionally filter by kind.
    """
    try:
        with db() as cx:
            _ensure_conc_table(cx)
            base = (
                "SELECT bc.id, bc.created_at, bc.kind, bc.target_key, "
                "bc.conception_text, bc.conviction, bc.valence, bc.n_signals_used "
                "FROM bot_conceptions bc "
                "JOIN (SELECT kind, target_key, MAX(id) AS mid FROM bot_conceptions GROUP BY kind, target_key) m "
                "ON bc.id = m.mid"
            )
            params: list = []
            if kind:
                base += " WHERE bc.kind=?"
                params.append(kind)
            base += " ORDER BY bc.conviction DESC, bc.target_key"
            rows = cx.execute(base, params).fetchall()
            cols = ["id", "created_at", "kind", "target_key", "conception_text",
                    "conviction", "valence", "n_signals_used"]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        _copilot_log.warning(f"get_all_current_conceptions failed: {e}")
        return []


# === bot_preferences (Layer 3 — Sprint 11) ===================================

_PREF_DDL = (
    "CREATE TABLE IF NOT EXISTS bot_preferences ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "created_at TEXT NOT NULL DEFAULT (datetime('now')), "
    "kind TEXT NOT NULL, snapshot_date TEXT NOT NULL, "
    "metric_json TEXT NOT NULL, insight_text TEXT, "
    "confidence INTEGER NOT NULL DEFAULT 0, n_samples INTEGER, "
    "provenance TEXT NOT NULL DEFAULT 'deterministic', "
    "model_used TEXT, cost_usd REAL)"
)
_PREF_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_pref_kind ON bot_preferences(kind)",
    "CREATE INDEX IF NOT EXISTS idx_pref_date ON bot_preferences(snapshot_date)",
]


def _ensure_pref_table(conn: _sqlite3.Connection) -> None:
    conn.execute(_PREF_DDL)
    for ix in _PREF_IDX:
        conn.execute(ix)


def insert_bot_preference(
    kind: str,
    snapshot_date: str,
    metric_json: str,
    insight_text: str | None = None,
    confidence: int = 0,
    n_samples: int | None = None,
    provenance: str = "deterministic",
    llm_meta: dict | None = None,
) -> int | None:
    meta = llm_meta or {}
    try:
        with db() as cx:
            _ensure_pref_table(cx)
            cur = cx.execute(
                "INSERT INTO bot_preferences "
                "(kind, snapshot_date, metric_json, insight_text, confidence, "
                "n_samples, provenance, model_used, cost_usd) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    kind, snapshot_date, metric_json, insight_text, confidence,
                    n_samples, provenance,
                    meta.get("model_used"), meta.get("cost_usd"),
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_bot_preference failed: {e}")
        return None


def get_latest_preferences(kinds: list[str] | None = None) -> list[dict]:
    """Latest preference per kind. If `kinds` filter is None, return all kinds."""
    try:
        with db() as cx:
            _ensure_pref_table(cx)
            q = (
                "SELECT bp.id, bp.created_at, bp.kind, bp.snapshot_date, "
                "bp.metric_json, bp.insight_text, bp.confidence, bp.n_samples, bp.provenance "
                "FROM bot_preferences bp "
                "JOIN (SELECT kind, MAX(id) AS mid FROM bot_preferences GROUP BY kind) m "
                "ON bp.id = m.mid"
            )
            params: list = []
            if kinds:
                ph = ",".join(["?"] * len(kinds))
                q += f" WHERE bp.kind IN ({ph})"
                params.extend(kinds)
            q += " ORDER BY bp.kind"
            rows = cx.execute(q, params).fetchall()
            cols = ["id", "created_at", "kind", "snapshot_date", "metric_json",
                    "insight_text", "confidence", "n_samples", "provenance"]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        _copilot_log.warning(f"get_latest_preferences failed: {e}")
        return []


# === ticker_axes (Sprint 12 — refactor critique) =============================

_AXES_DDL = (
    "CREATE TABLE IF NOT EXISTS ticker_axes ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "created_at TEXT NOT NULL DEFAULT (datetime('now')), "
    "ticker TEXT NOT NULL, "
    "demand_driver TEXT NOT NULL, value_chain_stage TEXT NOT NULL, "
    "moat_source TEXT NOT NULL, macro_factor TEXT NOT NULL, "
    "alt_drivers_json TEXT, confidence INTEGER, rationale TEXT, "
    "model_used TEXT, input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL)"
)
_AXES_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_axes_ticker ON ticker_axes(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_axes_macro ON ticker_axes(macro_factor)",
]


def _ensure_axes_table(conn: _sqlite3.Connection) -> None:
    conn.execute(_AXES_DDL)
    for ix in _AXES_IDX:
        conn.execute(ix)


def insert_ticker_axes(
    ticker: str,
    demand_driver: str,
    value_chain_stage: str,
    moat_source: str,
    macro_factor: str,
    alt_drivers_json: str | None = None,
    confidence: int | None = None,
    rationale: str | None = None,
    llm_meta: dict | None = None,
) -> int | None:
    meta = llm_meta or {}
    try:
        with db() as cx:
            _ensure_axes_table(cx)
            cur = cx.execute(
                "INSERT INTO ticker_axes "
                "(ticker, demand_driver, value_chain_stage, moat_source, macro_factor, "
                "alt_drivers_json, confidence, rationale, model_used, input_tokens, "
                "output_tokens, cost_usd) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ticker.upper(), demand_driver, value_chain_stage, moat_source,
                    macro_factor, alt_drivers_json, confidence, rationale,
                    meta.get("model_used"), meta.get("input_tokens"),
                    meta.get("output_tokens"), meta.get("cost_usd"),
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_ticker_axes failed: {e}")
        return None


def get_latest_ticker_axes(ticker: str) -> dict | None:
    try:
        with db() as cx:
            _ensure_axes_table(cx)
            row = cx.execute(
                "SELECT ticker, demand_driver, value_chain_stage, moat_source, "
                "macro_factor, alt_drivers_json, confidence, rationale, created_at "
                "FROM ticker_axes WHERE ticker=? ORDER BY id DESC LIMIT 1",
                (ticker.upper(),),
            ).fetchone()
            if not row:
                return None
            cols = ["ticker", "demand_driver", "value_chain_stage", "moat_source",
                    "macro_factor", "alt_drivers_json", "confidence", "rationale",
                    "created_at"]
            return dict(zip(cols, row, strict=False))
    except Exception as e:
        _copilot_log.warning(f"get_latest_ticker_axes failed: {e}")
        return None


def get_all_latest_ticker_axes() -> list[dict]:
    """One row per ticker — latest. Used by axes-aware redundancy / decorrelation."""
    try:
        with db() as cx:
            _ensure_axes_table(cx)
            rows = cx.execute(
                "SELECT ta.ticker, ta.demand_driver, ta.value_chain_stage, ta.moat_source, "
                "ta.macro_factor, ta.alt_drivers_json, ta.confidence, ta.created_at "
                "FROM ticker_axes ta "
                "JOIN (SELECT ticker, MAX(id) AS mid FROM ticker_axes GROUP BY ticker) m "
                "ON ta.id = m.mid"
            ).fetchall()
            cols = ["ticker", "demand_driver", "value_chain_stage", "moat_source",
                    "macro_factor", "alt_drivers_json", "confidence", "created_at"]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        _copilot_log.warning(f"get_all_latest_ticker_axes failed: {e}")
        return []


# === ticker_meta (Sprint 14 — fade-rate + SPOF + valo) =======================

_META_DDL = (
    "CREATE TABLE IF NOT EXISTS ticker_meta ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "created_at TEXT NOT NULL DEFAULT (datetime('now')), "
    "ticker TEXT NOT NULL, "
    "fade_rate_score INTEGER NOT NULL, "
    "moat_durability_years INTEGER, "
    "upstream_critical_deps_json TEXT, "
    "valo_what_priced_in TEXT, valo_pe_or_proxy REAL, valo_above_bull_case BOOLEAN, "
    "rationale TEXT, "
    "model_used TEXT, input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL)"
)
_META_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_meta_ticker ON ticker_meta(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_meta_fade ON ticker_meta(fade_rate_score)",
]


def _ensure_meta_table(conn: _sqlite3.Connection) -> None:
    conn.execute(_META_DDL)
    for ix in _META_IDX:
        conn.execute(ix)


def insert_ticker_meta(
    ticker: str,
    fade_rate_score: int,
    moat_durability_years: int | None = None,
    upstream_critical_deps_json: str | None = None,
    valo_what_priced_in: str | None = None,
    valo_pe_or_proxy: float | None = None,
    valo_above_bull_case: bool | None = None,
    rationale: str | None = None,
    llm_meta: dict | None = None,
) -> int | None:
    meta = llm_meta or {}
    try:
        with db() as cx:
            _ensure_meta_table(cx)
            cur = cx.execute(
                "INSERT INTO ticker_meta "
                "(ticker, fade_rate_score, moat_durability_years, upstream_critical_deps_json, "
                "valo_what_priced_in, valo_pe_or_proxy, valo_above_bull_case, rationale, "
                "model_used, input_tokens, output_tokens, cost_usd) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ticker.upper(), fade_rate_score, moat_durability_years,
                    upstream_critical_deps_json, valo_what_priced_in, valo_pe_or_proxy,
                    valo_above_bull_case, rationale,
                    meta.get("model_used"), meta.get("input_tokens"),
                    meta.get("output_tokens"), meta.get("cost_usd"),
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_ticker_meta failed: {e}")
        return None


def get_all_latest_ticker_meta() -> list[dict]:
    """One row per ticker — latest."""
    try:
        with db() as cx:
            _ensure_meta_table(cx)
            rows = cx.execute(
                "SELECT tm.ticker, tm.fade_rate_score, tm.moat_durability_years, "
                "tm.upstream_critical_deps_json, tm.valo_what_priced_in, "
                "tm.valo_pe_or_proxy, tm.valo_above_bull_case, tm.rationale, tm.created_at "
                "FROM ticker_meta tm "
                "JOIN (SELECT ticker, MAX(id) AS mid FROM ticker_meta GROUP BY ticker) m "
                "ON tm.id = m.mid"
            ).fetchall()
            cols = ["ticker", "fade_rate_score", "moat_durability_years",
                    "upstream_critical_deps_json", "valo_what_priced_in",
                    "valo_pe_or_proxy", "valo_above_bull_case", "rationale", "created_at"]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        _copilot_log.warning(f"get_all_latest_ticker_meta failed: {e}")
        return []


# === kill_criteria_alerts (Sprint 15) ========================================

_KCA_DDL = (
    "CREATE TABLE IF NOT EXISTS kill_criteria_alerts ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "created_at TEXT NOT NULL DEFAULT (datetime('now')), "
    "thesis_id INTEGER NOT NULL, ticker TEXT NOT NULL, "
    "status TEXT NOT NULL, "
    "triggers_evaluated_json TEXT NOT NULL, "
    "dominant_reason TEXT, evidence_quote TEXT, confidence INTEGER, "
    "notified BOOLEAN NOT NULL DEFAULT 0, "
    "model_used TEXT, cost_usd REAL)"
)
_KCA_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_kca_thesis ON kill_criteria_alerts(thesis_id)",
    "CREATE INDEX IF NOT EXISTS idx_kca_status ON kill_criteria_alerts(status)",
    "CREATE INDEX IF NOT EXISTS idx_kca_ticker ON kill_criteria_alerts(ticker)",
]


def _ensure_kca_table(conn: _sqlite3.Connection) -> None:
    conn.execute(_KCA_DDL)
    for ix in _KCA_IDX:
        conn.execute(ix)


def insert_kill_criteria_alert(
    thesis_id: int,
    ticker: str,
    status: str,
    triggers_evaluated_json: str,
    dominant_reason: str | None = None,
    evidence_quote: str | None = None,
    confidence: int | None = None,
    notified: bool = False,
    llm_meta: dict | None = None,
) -> int | None:
    meta = llm_meta or {}
    try:
        with db() as cx:
            _ensure_kca_table(cx)
            cur = cx.execute(
                "INSERT INTO kill_criteria_alerts "
                "(thesis_id, ticker, status, triggers_evaluated_json, dominant_reason, "
                "evidence_quote, confidence, notified, model_used, cost_usd) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    thesis_id, ticker.upper(), status, triggers_evaluated_json,
                    dominant_reason, evidence_quote, confidence, 1 if notified else 0,
                    meta.get("model_used"), meta.get("cost_usd"),
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_kill_criteria_alert failed: {e}")
        return None


def get_latest_kca_per_thesis(thesis_id: int) -> dict | None:
    try:
        with db() as cx:
            _ensure_kca_table(cx)
            row = cx.execute(
                "SELECT id, created_at, status, dominant_reason, evidence_quote, confidence "
                "FROM kill_criteria_alerts WHERE thesis_id=? ORDER BY id DESC LIMIT 1",
                (thesis_id,),
            ).fetchone()
            if not row:
                return None
            cols = ["id", "created_at", "status", "dominant_reason", "evidence_quote", "confidence"]
            return dict(zip(cols, row, strict=False))
    except Exception as e:
        _copilot_log.warning(f"get_latest_kca_per_thesis failed: {e}")
        return None


def get_all_latest_kca() -> list[dict]:
    """One row per thesis — latest only."""
    try:
        with db() as cx:
            _ensure_kca_table(cx)
            rows = cx.execute(
                "SELECT kca.id, kca.created_at, kca.thesis_id, kca.ticker, kca.status, "
                "kca.dominant_reason, kca.evidence_quote, kca.confidence "
                "FROM kill_criteria_alerts kca "
                "JOIN (SELECT thesis_id, MAX(id) AS mid FROM kill_criteria_alerts GROUP BY thesis_id) m "
                "ON kca.id = m.mid "
                "ORDER BY (CASE kca.status WHEN 'triggered' THEN 0 WHEN 'at_risk' THEN 1 ELSE 2 END), "
                "kca.confidence DESC"
            ).fetchall()
            cols = ["id", "created_at", "thesis_id", "ticker", "status",
                    "dominant_reason", "evidence_quote", "confidence"]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        _copilot_log.warning(f"get_all_latest_kca failed: {e}")
        return []


# === over_cap_alerts (Pile 2.1 v2.c.5) =======================================
# Journal incremental par evaluation over_cap, miroir kill_criteria_alerts.
# Table cree via migration alembic 0024 (pas de DDL lazy ici). Voir le
# module intelligence/over_cap_monitor pour la sequence transition->wire.


def insert_over_cap_alert(
    ticker: str,
    status: str,
    weight_pct: float,
    cap_pct: float,
    conviction: int | None = None,
    notified: bool = False,
    transition: str | None = None,
    bias_event_id: int | None = None,
) -> int | None:
    """Insert un row d'evaluation over_cap. status ∈ {over, dormant}. La
    table est append-only ; prev_status = derniere row (cf
    get_latest_oca_per_ticker). transition ∈ {dormant_to_over, over_to_dormant,
    no_change, NULL}."""
    try:
        with db() as cx:
            cur = cx.execute(
                "INSERT INTO over_cap_alerts "
                "(ticker, status, weight_pct, cap_pct, conviction, "
                " notified, transition, bias_event_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ticker.upper(), status, float(weight_pct), float(cap_pct),
                    conviction, 1 if notified else 0, transition, bias_event_id,
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_over_cap_alert failed: {e}")
        return None


def get_latest_oca_per_ticker(ticker: str) -> dict | None:
    """Last evaluation row for ticker, ou None si jamais evalue."""
    try:
        with db() as cx:
            row = cx.execute(
                "SELECT id, created_at, status, weight_pct, cap_pct, "
                "       conviction, notified, transition, bias_event_id "
                "FROM over_cap_alerts WHERE ticker=? "
                "ORDER BY id DESC LIMIT 1",
                (ticker.upper(),),
            ).fetchone()
            if not row:
                return None
            cols = ["id", "created_at", "status", "weight_pct", "cap_pct",
                    "conviction", "notified", "transition", "bias_event_id"]
            return dict(zip(cols, row, strict=False))
    except Exception as e:
        _copilot_log.warning(f"get_latest_oca_per_ticker failed: {e}")
        return None


# === stale_target monitor (#134 / migration 0056) ============================


def insert_stale_target_alert(
    thesis_id: int,
    ticker: str,
    status: str,
    cost_eur: float,
    target_eur: float,
    edge_pct: float,
    notified: bool = False,
    transition: str | None = None,
    consensus_target: float | None = None,
    consensus_n: int | None = None,
    consensus_delta_pct: float | None = None,
) -> int | None:
    """Insert un row d'evaluation stale_target. status in {alive, dying, dead}.
    Append-only ; prev_status = derniere row (cf get_latest_stale_target_per_thesis).
    transition in {alive_to_dying, dying_to_dead, dying_to_alive, dead_to_dying,
                   dead_to_alive, alive_to_dead, no_change, NULL}.

    PAS de bias_event_id (signal pur, pas anti-bias wire).

    Migration 0057 (12/06/2026) : colonnes consensus_* ajoutees pour cross-check
    target Olivier vs consensus rue. Nullable si yfinance .info pas dispo.
    """
    try:
        with db() as cx:
            cur = cx.execute(
                "INSERT INTO stale_target_alerts "
                "(thesis_id, ticker, status, cost_eur, target_eur, edge_pct, "
                " notified, transition, consensus_target, consensus_n, "
                " consensus_delta_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(thesis_id), ticker.upper(), status,
                    float(cost_eur), float(target_eur), float(edge_pct),
                    1 if notified else 0, transition,
                    float(consensus_target) if consensus_target is not None else None,
                    int(consensus_n) if consensus_n is not None else None,
                    float(consensus_delta_pct) if consensus_delta_pct is not None else None,
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_stale_target_alert failed: {e}")
        return None


def get_latest_stale_target_per_thesis(thesis_id: int) -> dict | None:
    """Last evaluation row for thesis_id, ou None si jamais evalue."""
    try:
        with db() as cx:
            row = cx.execute(
                "SELECT id, created_at, ticker, status, cost_eur, target_eur, "
                "       edge_pct, notified, transition, consensus_target, "
                "       consensus_n, consensus_delta_pct "
                "FROM stale_target_alerts WHERE thesis_id=? "
                "ORDER BY id DESC LIMIT 1",
                (int(thesis_id),),
            ).fetchone()
            if not row:
                return None
            cols = ["id", "created_at", "ticker", "status", "cost_eur",
                    "target_eur", "edge_pct", "notified", "transition",
                    "consensus_target", "consensus_n", "consensus_delta_pct"]
            return dict(zip(cols, row, strict=False))
    except Exception as e:
        _copilot_log.warning(f"get_latest_stale_target_per_thesis failed: {e}")
        return None


# === conviction PIT + drift (migration 0042) =================================


def get_conviction_drift(thesis_id: int) -> dict | None:
    """Lit conviction PIT (at_entry) vs courante + delta + last drift event.

    Returns dict {
      current: int | None,
      at_entry: int | None,
      delta: int,                      # current - at_entry
      drifted: bool,                   # delta != 0
      last_drift_at: str | None,       # timestamp dernier event drift dans chain
      n_drifts: int,                   # nombre d'events drift historiques
    } ou None si these introuvable.
    """
    try:
        with db() as cx:
            row = cx.execute(
                "SELECT conviction, conviction_at_entry "
                "FROM theses WHERE id=?",
                (thesis_id,),
            ).fetchone()
            if not row:
                return None
            current = row[0]
            at_entry = row[1]
            delta = (
                int(current) - int(at_entry)
                if (current is not None and at_entry is not None) else 0
            )
            # Compte drifts dans chain. Colonne canonique = captured_at
            # (cf migration 0033). Tests utilisent created_at en alias.
            try:
                drift_rows = cx.execute(
                    "SELECT payload_json, captured_at FROM thesis_integrity_log "
                    "WHERE thesis_id=? ORDER BY seq DESC",
                    (thesis_id,),
                ).fetchall()
            except Exception:
                # Fallback test schemas qui utilisent created_at
                drift_rows = cx.execute(
                    "SELECT payload_json, created_at FROM thesis_integrity_log "
                    "WHERE thesis_id=? ORDER BY seq DESC",
                    (thesis_id,),
                ).fetchall()
            n_drifts = 0
            last_drift_at = None
            for pr in drift_rows:
                if '"conviction_drift"' in (pr[0] or ""):
                    n_drifts += 1
                    if last_drift_at is None:
                        last_drift_at = pr[1]
            return {
                "current": current,
                "at_entry": at_entry,
                "delta": delta,
                "drifted": delta != 0,
                "last_drift_at": last_drift_at,
                "n_drifts": n_drifts,
            }
    except Exception as e:
        _copilot_log.warning(f"get_conviction_drift failed: {e}")
        return None


# === thesis position_type (axe EXIT POLICY, migration 0040) ==================
# Hook tamper-evident : assignation a 'structural' append au thesis_integrity_log.
# Garde anti-Catch1 (red-team user 07/06) : tu ne peux pas re-tagger un loser
# en structural sans laisser de trace dans la chain d'integrite.


class StructuralJustificationRequired(ValueError):
    """Raised quand on tente d'assigner position_type='structural' sans
    structural_justification (Catch 1 red-team user)."""


def set_position_type(
    thesis_id: int,
    position_type: str,
    structural_justification: str | None = None,
    position_tags: list[str] | None = None,
) -> dict | None:
    """Set position_type sur une these, avec hook tamper-evident si structural.

    Args:
        thesis_id: id these.
        position_type: 'structural' | 'priced' | 'tactical'.
        structural_justification: REQUIS si position_type=='structural'.
            Texte libre justifiant l'assignation (critere objectif verifiable).
        position_tags: optional liste de tags orthogonaux (mega_cap, commodity,
            satellite, ...). Non-canonical pour decision.

    Returns:
        dict {thesis_id, position_type, integrity_seq, integrity_hash} ou None
        si erreur. integrity_seq/hash uniquement si structural.

    Raises:
        StructuralJustificationRequired si structural sans justification.
        ValueError si position_type invalide.
    """
    import json as _json
    from datetime import UTC as _UTC, datetime as _datetime

    if position_type not in ("structural", "priced", "tactical"):
        raise ValueError(f"position_type invalide : {position_type!r}")
    if position_type == "structural" and not structural_justification:
        raise StructuralJustificationRequired(
            "position_type='structural' requires structural_justification "
            "(Catch 1 garde : critere objectif verifiable). "
            "Cf docs/QUALITY_BAR.md doctrine M2 pre-registration."
        )
    tags_json = _json.dumps(position_tags or [], ensure_ascii=False)
    try:
        with db() as cx:
            row = cx.execute(
                "SELECT ticker, position_type, structural_justification "
                "FROM theses WHERE id=?",
                (thesis_id,),
            ).fetchone()
            if not row:
                _copilot_log.warning(f"set_position_type: thesis_id {thesis_id} not found")
                return None
            ticker, old_type, _old_justif = row
            cx.execute(
                "UPDATE theses SET position_type=?, position_tags_json=?, "
                "structural_justification=? WHERE id=?",
                (position_type, tags_json, structural_justification, thesis_id),
            )
        # Hook tamper-evident : si on ASSIGNE structural (changement ou
        # confirmation) -> append au thesis_integrity_log.
        result = {"thesis_id": thesis_id, "position_type": position_type}
        if position_type == "structural":
            payload = {
                "event": "position_type_assigned",
                "thesis_id": thesis_id,
                "ticker": ticker,
                "position_type": "structural",
                "structural_justification": structural_justification,
                "tags": position_tags or [],
                "previous_type": old_type or "priced",
                "asof": _datetime.now(_UTC).isoformat(timespec="seconds"),
            }
            anchor = insert_thesis_integrity_row(thesis_id, payload)
            if anchor:
                result["integrity_seq"] = anchor["seq"]
                result["integrity_hash"] = anchor["chain_hash"]
        return result
    except StructuralJustificationRequired:
        raise
    except Exception as e:
        _copilot_log.warning(f"set_position_type failed: {e}")
        return None


def demote_from_structural(
    thesis_id: int, reason: str, demoted_to: str = "priced",
) -> dict | None:
    """Auto-demote_from_structural -- Q3 master decision.

    Symetrique a set_position_type structural : le privilege "structural"
    (pas de stop-prix, exit reserve invalidation) est merite par la premise.
    Si l'invalidation fire (compute_thesis_erosion verdict=INVALIDATION_HIT),
    la premise est cassee par definition -> privilege revoque automatiquement,
    position passe a 'priced' (discipline stop/target normale).

    Tamper-evident : append thesis_integrity_log event=auto_demote_from_structural
    avec reason + old_type + new_type + asof. Anti-rationalisation : l'auto-demote
    laisse une trace immuable -- impossible d'effacer.

    Args:
        thesis_id : id these.
        reason : raison textuelle (typiquement le verdict INVALIDATION_HIT detail).
        demoted_to : 'priced' (defaut, recommande) ou 'tactical' (sur-reaction,
            cf master Q3 option C rejetee).

    Returns:
        dict {thesis_id, ticker, old_type, new_type, integrity_seq, integrity_hash}
        ou None si these introuvable ou pas structural (pas de demote a faire).

    Raises:
        ValueError si demoted_to invalide ou reason vide.
    """
    from datetime import UTC as _UTC, datetime as _datetime

    if demoted_to not in ("priced", "tactical"):
        raise ValueError(f"demoted_to invalide : {demoted_to!r}")
    if not reason or not reason.strip():
        raise ValueError("reason ne peut etre vide (anti-rationalisation tamper-evident)")

    try:
        with db() as cx:
            row = cx.execute(
                "SELECT ticker, position_type, structural_justification "
                "FROM theses WHERE id=?",
                (thesis_id,),
            ).fetchone()
            if not row:
                _copilot_log.warning(f"demote_from_structural: thesis {thesis_id} not found")
                return None
            ticker, old_type, old_justif = row
            if old_type != "structural":
                # No-op : si pas structural, rien a demoter
                _copilot_log.info(
                    f"demote_from_structural noop: thesis {thesis_id} type={old_type}",
                )
                return None
            # Demote : update position_type, preserve old structural_justification
            # comme metadata historique (mais le knob ne l'enforce plus -- ce n'est
            # plus required pour priced).
            cx.execute(
                "UPDATE theses SET position_type=? WHERE id=?",
                (demoted_to, thesis_id),
            )
        # Append integrity log tamper-evident (en dehors du with db() pour
        # eviter double-with). insert_thesis_integrity_row ouvre sa propre cx.
        payload = {
            "event": "auto_demote_from_structural",
            "thesis_id": thesis_id,
            "ticker": ticker,
            "old_type": "structural",
            "new_type": demoted_to,
            "old_structural_justification": old_justif,
            "reason": reason[:500],
            "asof": _datetime.now(_UTC).isoformat(timespec="seconds"),
        }
        anchor = insert_thesis_integrity_row(thesis_id, payload)
        result = {
            "thesis_id": thesis_id,
            "ticker": ticker,
            "old_type": "structural",
            "new_type": demoted_to,
            "reason": reason,
        }
        if anchor:
            result["integrity_seq"] = anchor["seq"]
            result["integrity_hash"] = anchor["chain_hash"]
        return result
    except Exception as e:
        _copilot_log.warning(f"demote_from_structural failed: {e}")
        return None


def get_position_type(thesis_id: int) -> dict | None:
    """Lit position_type + tags + justification d'une these."""
    import json as _json
    try:
        with db() as cx:
            row = cx.execute(
                "SELECT position_type, position_tags_json, structural_justification "
                "FROM theses WHERE id=?",
                (thesis_id,),
            ).fetchone()
            if not row:
                return None
            tags = []
            with suppress(json.JSONDecodeError, TypeError):
                tags = _json.loads(row[1] or "[]")
            return {
                "position_type": row[0],
                "position_tags": tags,
                "structural_justification": row[2],
            }
    except Exception as e:
        _copilot_log.warning(f"get_position_type failed: {e}")
        return None


# === thesis_erosion_classifications (migration 0041) =========================


def insert_erosion_classification(
    erosion_log_id: int,
    signal_id: int,
    signal_source: str,
    bears_on: str | None,
    target_index: int | None,
    relation: str | None,
    confidence: float | None,
    materiality: float | None,
    rationale: str | None,
    evidence_quote: str | None,
) -> int | None:
    """Persiste une classification LLM signal vs these. Append-only.

    signal_source in {signals, chat} (distinguer les 2 sources)."""
    try:
        with db() as cx:
            cur = cx.execute(
                "INSERT INTO thesis_erosion_classifications "
                "(erosion_log_id, signal_id, signal_source, bears_on, "
                " target_index, relation, confidence, materiality, "
                " rationale, evidence_quote) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    erosion_log_id, signal_id, signal_source,
                    bears_on, target_index, relation,
                    confidence, materiality, rationale, evidence_quote,
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_erosion_classification failed: {e}")
        return None


def get_classifications_for_erosion(erosion_log_id: int) -> list[dict]:
    """Lit les classifications associees a un erosion_log (pour position-card)."""
    try:
        with db() as cx:
            rows = cx.execute(
                "SELECT id, signal_id, signal_source, bears_on, target_index, "
                "       relation, confidence, materiality, rationale, evidence_quote "
                "FROM thesis_erosion_classifications WHERE erosion_log_id=? "
                "ORDER BY confidence DESC NULLS LAST, materiality DESC NULLS LAST",
                (erosion_log_id,),
            ).fetchall()
            cols = ["id", "signal_id", "signal_source", "bears_on",
                    "target_index", "relation", "confidence", "materiality",
                    "rationale", "evidence_quote"]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        _copilot_log.warning(f"get_classifications_for_erosion failed: {e}")
        return []


# === thesis_erosion_log (aiguillage anti-entetement, migration 0039) =========
# Journal append-only verdict erosion contenu these vs evidence post-opened_at.
# Complementaire de thesis_track_record (Brier) + M14 (staleness temporelle).


def insert_thesis_erosion(
    thesis_id: int,
    ticker: str,
    verdict: str,
    n_confirm: int = 0,
    n_erode: int = 0,
    n_invalidation_hit: int = 0,
    driver_status_json: str = "[]",
    signals_considered_json: str = "[]",
    degraded: bool = False,
    steer: str | None = None,
) -> int | None:
    """Insert verdict erosion. Append-only.

    verdict in {INTACT, EROSION_DETECTED, INVALIDATION_HIT, STALE_UNUPDATED,
    REVIEW_DUE_DEGRADED}."""
    try:
        with db() as cx:
            cur = cx.execute(
                "INSERT INTO thesis_erosion_log "
                "(thesis_id, ticker, verdict, n_confirm, n_erode, "
                " n_invalidation_hit, driver_status_json, signals_considered_json, "
                " degraded, steer) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    thesis_id, ticker.upper(), verdict,
                    int(n_confirm), int(n_erode), int(n_invalidation_hit),
                    driver_status_json, signals_considered_json,
                    1 if degraded else 0, steer,
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_thesis_erosion failed: {e}")
        return None


def get_latest_erosion_per_thesis(thesis_id: int) -> dict | None:
    """Dernier verdict erosion pour une these, ou None."""
    try:
        with db() as cx:
            row = cx.execute(
                "SELECT id, computed_at, verdict, n_confirm, n_erode, "
                "       n_invalidation_hit, driver_status_json, "
                "       signals_considered_json, degraded, steer "
                "FROM thesis_erosion_log WHERE thesis_id=? "
                "ORDER BY id DESC LIMIT 1",
                (thesis_id,),
            ).fetchone()
            if not row:
                return None
            cols = ["id", "computed_at", "verdict", "n_confirm", "n_erode",
                    "n_invalidation_hit", "driver_status_json",
                    "signals_considered_json", "degraded", "steer"]
            return dict(zip(cols, row, strict=False))
    except Exception as e:
        _copilot_log.warning(f"get_latest_erosion_per_thesis failed: {e}")
        return None


_PRIMARY_ENTITY_TOP_N = 3  # ticker in top-N entities = vraie cible (pas cross-mention)


def get_material_signals_since(
    ticker: str, since_iso: str, limit: int = 12,
) -> list[dict]:
    """Signals materiels referencant ticker comme TARGET PRIMAIRE depuis since_iso.

    Calibration 08/06 (audit thesis_erosion 1er run) : filter laxiste
    entities LIKE '%"TICKER"%' capturait des signaux ou le ticker etait mention
    secondaire dans une liste de 7+ entities (ex : "Retatrutide weight-loss"
    avec entities=[LLY, NVDA, AVGO, TSM, AMD, MSFT, GOOGL, META, AMZN] -- LLY
    est la cible, GOOGL est mention macro secondaire). Le LLM Haiku, force
    de classifier ce signal pour GOOGL, sur-interpretait en "erodes" via une
    chaine logique tordue (capital reshuffling -> compute concurrent -> margins).

    Fix : prend SEULEMENT les signaux ou ticker est dans les TOP_N premieres
    entities (heuristique = mention primaire, pas secondaire).

    Deux sources :
    - signals : entities[0:N] contient ticker + materiality = impact * boost
    - chat_extracted_signals : ticker = TICKER + materiality = confidence * 3
    """
    import json as _json

    ticker_u = ticker.upper()
    try:
        with db() as cx:
            out: list[dict] = []
            # Sur-fetch pour filtrer cote Python sur position dans entities.
            # Le LIKE garde un pre-filtre cheap, le post-filtre Python verifie
            # que le ticker est dans top-N entities = mention primaire.
            for r in cx.execute(
                "SELECT id, timestamp AS asof, title, summary, entities, "
                "COALESCE(impact_magnitude, 1) * COALESCE(materiality_boost, 1) AS materiality "
                "FROM signals WHERE timestamp > ? AND entities LIKE ? "
                "ORDER BY materiality DESC LIMIT ?",
                # Sur-fetch 5x pour avoir marge apres filtre primary
                (since_iso, f'%"{ticker_u}"%', limit * 5),
            ).fetchall():
                # Parse entities JSON, garde seulement si ticker in top-N
                try:
                    ents = _json.loads(r[4] or "[]")
                    if not isinstance(ents, list):
                        continue
                    top_n = [str(e).upper() for e in ents[:_PRIMARY_ENTITY_TOP_N]]
                    if ticker_u not in top_n:
                        continue  # mention secondaire, skip
                except (_json.JSONDecodeError, TypeError):
                    continue
                cols = ["id", "asof", "title", "summary", "materiality"]
                out.append(dict(zip(cols, (r[0], r[1], r[2], r[3], r[5]), strict=False)))
            for r in cx.execute(
                "SELECT id, created_at AS asof, "
                "COALESCE(note, '') AS title, "
                "COALESCE(evidence_quote, '') AS summary, "
                "COALESCE(confidence, 0.5) * 3 AS materiality "
                "FROM chat_extracted_signals "
                "WHERE created_at > ? AND ticker = ? "
                "ORDER BY materiality DESC LIMIT ?",
                (since_iso, ticker_u, limit),
            ).fetchall():
                cols = ["id", "asof", "title", "summary", "materiality"]
                out.append(dict(zip(cols, r, strict=False)))
            out.sort(key=lambda x: x["materiality"], reverse=True)
            return out[:limit]
    except Exception as e:
        _copilot_log.warning(f"get_material_signals_since failed: {e}")
        return []


# === stress_gate_alerts (Axe 4 QUALITY_BAR v2.c.6) ===========================
# Journal incremental par evaluation stress-test, miroir over_cap_alerts.
# Table cree via migration alembic 0037. Voir intelligence/stress_gate_monitor
# pour la sequence classify -> transition -> notify.


def insert_stress_gate_alert(
    scenario_name: str,
    status: str,
    drawdown_pct: float,
    warn_pct: float,
    breach_pct: float,
    notified: bool = False,
    transition: str | None = None,
) -> int | None:
    """Insert row d'evaluation stress-gate. status in {ok, warn, breach}.
    Append-only ; prev_status = derniere row (cf get_latest_stress_gate_per_scenario).
    transition in {enter_breach, enter_warn, recover_ok, recover_warn, no_change, NULL}."""
    try:
        with db() as cx:
            cur = cx.execute(
                "INSERT INTO stress_gate_alerts "
                "(scenario_name, status, drawdown_pct, warn_pct, breach_pct, "
                " notified, transition) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    scenario_name, status, float(drawdown_pct),
                    float(warn_pct), float(breach_pct),
                    1 if notified else 0, transition,
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_stress_gate_alert failed: {e}")
        return None


def get_latest_stress_gate_per_scenario(scenario_name: str) -> dict | None:
    """Last evaluation row pour scenario, ou None si jamais evalue."""
    try:
        with db() as cx:
            row = cx.execute(
                "SELECT id, created_at, status, drawdown_pct, warn_pct, "
                "       breach_pct, notified, transition "
                "FROM stress_gate_alerts WHERE scenario_name=? "
                "ORDER BY id DESC LIMIT 1",
                (scenario_name,),
            ).fetchone()
            if not row:
                return None
            cols = ["id", "created_at", "status", "drawdown_pct", "warn_pct",
                    "breach_pct", "notified", "transition"]
            return dict(zip(cols, row, strict=False))
    except Exception as e:
        _copilot_log.warning(f"get_latest_stress_gate_per_scenario failed: {e}")
        return None


def get_latest_stress_gate_all() -> list[dict]:
    """Latest row per scenario (1 ligne par scenario distinct). Pour dashboard surface."""
    try:
        with db() as cx:
            rows = cx.execute(
                "SELECT s.id, s.created_at, s.scenario_name, s.status, "
                "       s.drawdown_pct, s.warn_pct, s.breach_pct, s.notified, "
                "       s.transition "
                "FROM stress_gate_alerts s "
                "INNER JOIN ("
                "  SELECT scenario_name, MAX(id) AS max_id "
                "  FROM stress_gate_alerts GROUP BY scenario_name"
                ") m ON s.id = m.max_id "
                "ORDER BY s.drawdown_pct ASC"
            ).fetchall()
            cols = ["id", "created_at", "scenario_name", "status",
                    "drawdown_pct", "warn_pct", "breach_pct", "notified",
                    "transition"]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        _copilot_log.warning(f"get_latest_stress_gate_all failed: {e}")
        return []


# === position_decisions_context (Friction décision #2) ======================
# Snapshot canonique du contexte au moment de chaque /trade confirm.
# Cron retrospective +30j/+90j ecrit les verdicts (cf cron_retrospective_decisions).
# Source canonique : alimente bias_ledger en donnees per-decision.


def insert_decision_context(
    action: str,
    ticker: str,
    qty: float,
    price: float,
    regime: str | None,
    regime_score: float | None,
    bucket_act: int | None,
    bucket_watch: int | None,
    bucket_calm: int | None,
    bucket_silent: int | None,
    cluster_id: str | None,
    cluster_share_before: float | None,
    cluster_share_after: float | None,
    regime_warnings_json: str,
    bias_warnings_json: str,
    signals_30d_str: str,
    decision_id: int | None = None,
) -> int | None:
    """Append row dans position_decisions_context au moment /trade confirm.

    Tous champs nullable sauf action/ticker/qty/price (defensive : graceful
    degrade si macro_state read failed).
    """
    try:
        with db() as cx:
            cur = cx.execute(
                "INSERT INTO position_decisions_context "
                "(decision_id, action, ticker, qty, price, "
                " regime, regime_score, bucket_act, bucket_watch, "
                " bucket_calm, bucket_silent, cluster_id, "
                " cluster_share_before, cluster_share_after, "
                " regime_warnings_json, bias_warnings_json, signals_30d_str) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    decision_id, action, ticker.upper(), float(qty), float(price),
                    regime, regime_score, bucket_act, bucket_watch,
                    bucket_calm, bucket_silent, cluster_id,
                    cluster_share_before, cluster_share_after,
                    regime_warnings_json, bias_warnings_json, signals_30d_str,
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_decision_context failed: {e}")
        return None


def get_decision_context(context_id: int) -> dict | None:
    """Lit une row de context par id."""
    try:
        with db() as cx:
            row = cx.execute(
                "SELECT id, created_at, decision_id, action, ticker, qty, price, "
                "       regime, regime_score, bucket_act, bucket_watch, bucket_calm, "
                "       bucket_silent, cluster_id, cluster_share_before, cluster_share_after, "
                "       regime_warnings_json, bias_warnings_json, signals_30d_str, "
                "       retrospective_30d_at, retrospective_30d_outcome_pct, "
                "       retrospective_30d_pnl_pct, retrospective_30d_verdict, "
                "       retrospective_90d_at, retrospective_90d_outcome_pct, "
                "       retrospective_90d_pnl_pct, retrospective_90d_verdict "
                "FROM position_decisions_context WHERE id = ?",
                (context_id,),
            ).fetchone()
            if not row:
                return None
            cols = [
                "id", "created_at", "decision_id", "action", "ticker", "qty", "price",
                "regime", "regime_score", "bucket_act", "bucket_watch", "bucket_calm",
                "bucket_silent", "cluster_id", "cluster_share_before", "cluster_share_after",
                "regime_warnings_json", "bias_warnings_json", "signals_30d_str",
                "retrospective_30d_at", "retrospective_30d_outcome_pct",
                "retrospective_30d_pnl_pct", "retrospective_30d_verdict",
                "retrospective_90d_at", "retrospective_90d_outcome_pct",
                "retrospective_90d_pnl_pct", "retrospective_90d_verdict",
            ]
            return dict(zip(cols, row, strict=False))
    except Exception as e:
        _copilot_log.warning(f"get_decision_context failed: {e}")
        return None


def list_pending_retrospectives(horizon_days: int) -> list[dict]:
    """Liste les decision_contexts qui ont depasse l'horizon mais pas encore
    retrospective. Returns rows ready for cron processing.

    horizon_days : 30 ou 90.
    """
    col = f"retrospective_{horizon_days}d_at"
    try:
        with db() as cx:
            rows = cx.execute(
                f"SELECT id, created_at, action, ticker, qty, price "
                f"FROM position_decisions_context "
                f"WHERE {col} IS NULL "
                f"  AND created_at < datetime('now', '-' || ? || ' day') "
                f"ORDER BY created_at DESC LIMIT 100",
                (int(horizon_days),),
            ).fetchall()
            return [
                {
                    "id": r[0], "created_at": r[1], "action": r[2],
                    "ticker": r[3], "qty": float(r[4]), "price": float(r[5]),
                }
                for r in rows
            ]
    except Exception as e:
        _copilot_log.warning(f"list_pending_retrospectives failed: {e}")
        return []


def update_retrospective(
    context_id: int,
    horizon_days: int,
    outcome_pct: float,
    pnl_pct: float,
    verdict: str,
) -> bool:
    """Update retrospective fields. Returns True si succes."""
    col_at = f"retrospective_{horizon_days}d_at"
    col_outcome = f"retrospective_{horizon_days}d_outcome_pct"
    col_pnl = f"retrospective_{horizon_days}d_pnl_pct"
    col_verdict = f"retrospective_{horizon_days}d_verdict"
    try:
        with db() as cx:
            cx.execute(
                f"UPDATE position_decisions_context "
                f"SET {col_at} = datetime('now'), {col_outcome} = ?, "
                f"    {col_pnl} = ?, {col_verdict} = ? "
                f"WHERE id = ?",
                (float(outcome_pct), float(pnl_pct), verdict, int(context_id)),
            )
        return True
    except Exception as e:
        _copilot_log.warning(f"update_retrospective failed: {e}")
        return False


# === macro_regime_alerts (Phase A macro stress monitor) =====================
# Journal append-only par evaluation regime macro. Table cree via migration
# alembic 0029. Voir intelligence/macro_regime.py pour la classify pure +
# check_regime_transition.


def insert_macro_regime_alert(
    regime: str,
    score: float,
    danger_count: int,
    warn_count: int,
    asleep_count: int,
    silent_count: int,
    triggers_json: str,
    notified: bool = False,
    transition: str | None = None,
) -> int | None:
    """Insert une row d'evaluation regime. regime ∈ {COMPLACENT, RISK_ON,
    LATE_CYCLE, FRAGILE, STRESS}. transition ∈ {no_change, changed, NULL}."""
    try:
        with db() as cx:
            cur = cx.execute(
                "INSERT INTO macro_regime_alerts "
                "(regime, score, danger_count, warn_count, asleep_count, "
                " silent_count, triggers, notified, transition) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    regime, float(score), int(danger_count), int(warn_count),
                    int(asleep_count), int(silent_count), triggers_json,
                    1 if notified else 0, transition,
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_macro_regime_alert failed: {e}")
        return None


def get_latest_macro_regime() -> dict | None:
    """Last regime evaluation, None si journal vide."""
    try:
        with db() as cx:
            row = cx.execute(
                "SELECT id, created_at, regime, score, danger_count, warn_count, "
                "       asleep_count, silent_count, triggers, notified, transition "
                "FROM macro_regime_alerts "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            cols = ["id", "created_at", "regime", "score", "danger_count",
                    "warn_count", "asleep_count", "silent_count", "triggers",
                    "notified", "transition"]
            return dict(zip(cols, row, strict=False))
    except Exception as e:
        _copilot_log.warning(f"get_latest_macro_regime failed: {e}")
        return None


# === risk_signal_evaluations (Phase 1.5 stage 2 absorption_roadmap) ===
# Pattern miroir macro_regime_alerts : append-only, latest via ORDER BY.
# Doctrine L17 LESSONS : live state cron-written ici, declarative en
# config/risk_watch.yaml. Plus de write-back sur le YAML.

def insert_risk_signal_evaluation(
    risk_id: str,
    signal_id: str,
    status: str,
    reason: str | None = None,
    confidence: int | None = None,
    evidence_ids_json: str | None = None,
    transition: str | None = None,
) -> int | None:
    """Insert 1 evaluation cron pour (risk_id, signal_id).

    status ∈ {monitoring, at_risk, triggered, resolved}.
    confidence ∈ [0, 100] ou None.
    transition ∈ {no_change, changed, NULL}.

    Retourne lastrowid ou None sur exception (fail-safe : la cron continue
    son loop sans crash sur 1 evaluation perdue)."""
    if status not in ("monitoring", "at_risk", "triggered", "resolved"):
        _copilot_log.warning(
            f"insert_risk_signal_evaluation : status {status!r} invalide"
        )
        return None
    try:
        with db() as cx:
            cur = cx.execute(
                "INSERT INTO risk_signal_evaluations "
                "(risk_id, signal_id, status, reason, confidence, "
                " evidence_ids_json, transition) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    risk_id, signal_id, status, reason,
                    int(confidence) if confidence is not None else None,
                    evidence_ids_json, transition,
                ),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_risk_signal_evaluation failed: {e}")
        return None


def get_latest_risk_signal_evaluation(
    risk_id: str, signal_id: str
) -> dict | None:
    """Derniere evaluation pour (risk_id, signal_id). None si jamais evalue."""
    try:
        with db() as cx:
            row = cx.execute(
                "SELECT id, evaluated_at, risk_id, signal_id, status, "
                "       reason, confidence, evidence_ids_json, transition "
                "FROM risk_signal_evaluations "
                "WHERE risk_id = ? AND signal_id = ? "
                "ORDER BY evaluated_at DESC, id DESC LIMIT 1",
                (risk_id, signal_id),
            ).fetchone()
            if not row:
                return None
            cols = ["id", "evaluated_at", "risk_id", "signal_id", "status",
                    "reason", "confidence", "evidence_ids_json", "transition"]
            return dict(zip(cols, row, strict=False))
    except Exception as e:
        _copilot_log.warning(f"get_latest_risk_signal_evaluation failed: {e}")
        return None


def insert_price_observation(
    ticker: str,
    price_native: float,
    currency: str,
    source: str = "yfinance",
    asof: str | None = None,
) -> int | None:
    """Append-only price observation (M1 doctrine : triple value+asof+source).

    Pattern : ecrit par shared/prices.py apres live fetch success.
    asof default = datetime.now(UTC).isoformat().

    Returns lastrowid ou None sur exception (silent-miss L7 si DB down).
    """
    from datetime import UTC as _UTC, datetime as _dt
    if asof is None:
        asof = _dt.now(_UTC).isoformat()
    try:
        with db() as cx:
            cur = cx.execute(
                "INSERT INTO price_history (ticker, asof, price_native, currency, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (ticker.upper(), asof, float(price_native), currency.upper(), source),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_price_observation {ticker} failed: {e}")
        return None


def insert_price_observations_bulk(
    rows: list[tuple[str, str, float, str, str]],
) -> int:
    """Bulk insert price_history. Skip si (ticker, asof, source) deja present.

    Args:
        rows : list de (ticker, asof_iso, price_native, currency, source)

    Returns:
        Nombre de rows effectivement inseres (apres dedup).

    Use case : backfill 5y x 26 tickers ~ 33k rows. Single transaction = ~100x
    plus rapide que insert_price_observation en boucle.
    """
    if not rows:
        return 0
    inserted = 0
    try:
        with db() as cx:
            for ticker, asof, price, currency, source in rows:
                # Dedup defensive : skip si exact match deja la
                existing = cx.execute(
                    "SELECT 1 FROM price_history "
                    "WHERE ticker=? AND asof=? AND source=? LIMIT 1",
                    (ticker.upper(), asof, source),
                ).fetchone()
                if existing:
                    continue
                cx.execute(
                    "INSERT INTO price_history "
                    "(ticker, asof, price_native, currency, source) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (ticker.upper(), asof, float(price),
                     currency.upper(), source),
                )
                inserted += 1
    except Exception as e:
        _copilot_log.warning(f"insert_price_observations_bulk failed: {e}")
    return inserted


def insert_fx_observation(
    base: str,
    quote: str,
    rate: float,
    source: str = "yfinance",
    asof: str | None = None,
) -> int | None:
    """Append-only FX observation. Pattern miroir insert_price_observation."""
    from datetime import UTC as _UTC, datetime as _dt
    if asof is None:
        asof = _dt.now(_UTC).isoformat()
    try:
        with db() as cx:
            cur = cx.execute(
                "INSERT INTO fx_history (base, quote, rate, asof, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (base.upper(), quote.upper(), float(rate), asof, source),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_fx_observation {base}/{quote} failed: {e}")
        return None


def get_latest_price(ticker: str) -> dict | None:
    """Dernier prix observe pour ticker. None si aucune observation.

    Returns dict {ticker, asof, price_native, currency, source} ou None.
    Pas de fallback : caller (valuation) classifie freshness via SLA.
    """
    try:
        with db() as cx:
            row = cx.execute(
                "SELECT ticker, asof, price_native, currency, source "
                "FROM price_history WHERE ticker = ? "
                "ORDER BY asof DESC LIMIT 1",
                (ticker.upper(),),
            ).fetchone()
            if not row:
                return None
            return {
                "ticker": row[0], "asof": row[1], "price_native": row[2],
                "currency": row[3], "source": row[4],
            }
    except Exception as e:
        _copilot_log.warning(f"get_latest_price {ticker} failed: {e}")
        return None


def get_latest_fx_rate(base: str, quote: str) -> dict | None:
    """Dernier FX observe pour (base, quote). None si aucune observation."""
    try:
        with db() as cx:
            row = cx.execute(
                "SELECT base, quote, rate, asof, source "
                "FROM fx_history WHERE base = ? AND quote = ? "
                "ORDER BY asof DESC LIMIT 1",
                (base.upper(), quote.upper()),
            ).fetchone()
            if not row:
                return None
            return {
                "base": row[0], "quote": row[1], "rate": row[2],
                "asof": row[3], "source": row[4],
            }
    except Exception as e:
        _copilot_log.warning(f"get_latest_fx_rate {base}/{quote} failed: {e}")
        return None


def record_prediction_integrity(conn, prediction_id: int) -> str | None:
    """Append 1 maille a la chaine integrity PREDICTIONS (commit-reveal).

    payload_json (incl nonce 256 bits) reste PRIVE dans bot.db (gitignored).
    Le ledger public exporte hash chain SEUL, payload revele a la resolution
    de la prediction (catch hiding red-team 07/06 nuit++).

    Idempotent par prediction_id (UNIQUE INDEX). Appele post-commit
    insert_prediction, silent-miss tolere (L7 pattern).

    Args:
        conn : sqlite3 connection (reuse caller's tx)
        prediction_id : id de la prediction qu'on vient d'inserer

    Returns:
        chain_hash hex string ou None si deja chained / prediction introuvable.
    """
    import json as _json
    import secrets as _secrets

    from shared import integrity
    if conn.execute(
        "SELECT 1 FROM prediction_integrity_log WHERE prediction_id=?",
        (prediction_id,),
    ).fetchone():
        return None
    cols = (
        "id", "signal_id", "ticker", "direction", "horizon_days",
        "baseline_price", "baseline_date", "target_date",
        "probability_at_creation", "methodology_version", "created_at",
    )
    row = conn.execute(
        f"SELECT {','.join(cols)} FROM predictions WHERE id=?",
        (prediction_id,),
    ).fetchone()
    if row is None:
        return None
    payload = dict(zip(cols, row, strict=True))
    payload["nonce"] = _secrets.token_hex(32)  # commit-reveal hiding 256 bits
    last = conn.execute(
        "SELECT chain_hash FROM prediction_integrity_log "
        "ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    prev_in = last[0] if last else integrity.GENESIS_HASH
    prev_used, chain_hash = integrity.chain_append(prev_in, payload)
    conn.execute(
        "INSERT INTO prediction_integrity_log "
        "(prediction_id, payload_json, prev_hash, chain_hash) "
        "VALUES (?,?,?,?)",
        (
            prediction_id,
            _json.dumps(payload, sort_keys=True),
            prev_used,
            chain_hash,
        ),
    )
    conn.commit()
    return chain_hash


def get_prediction_integrity_chain() -> list[dict]:
    """Chain ordonnee pour verify_chain / export ledger.

    Lit la table PRIVEE. L'export public (integrity_anchor.sh) STRIPPE
    payload_json apres lecture pour preserver le hiding commit-reveal.
    """
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        return [
            dict(r) for r in conn.execute(
                "SELECT seq, prediction_id, captured_at, payload_json, "
                "       prev_hash, chain_hash "
                "FROM prediction_integrity_log ORDER BY seq ASC"
            )
        ]
    finally:
        conn.close()


def insert_thesis_integrity_row(
    thesis_id: int,
    payload: dict,
) -> dict | None:
    """A3 hook helper : append thesis_integrity_log apres add_thesis commit.

    Compute chain_hash via shared.integrity (canonical 6-decimal floats).
    Reads previous chain_hash via MAX(seq) order. Genesis = 64x'0'.

    Returns dict {seq, chain_hash} ou None si exception.
    Idempotence : chain_hash UNIQUE -> double-insert proteged au DB level."""
    import json as _json

    from shared.integrity import GENESIS_HASH, compute_hash
    try:
        with db() as cx:
            # Find previous head
            prev = cx.execute(
                "SELECT chain_hash, seq FROM thesis_integrity_log "
                "ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            prev_hash = prev[0] if prev else GENESIS_HASH
            next_seq = (prev[1] + 1) if prev else 1
            # Compute chain
            new_hash = compute_hash(payload, prev_hash)
            # Insert
            payload_json = _json.dumps(payload, sort_keys=True, default=str)
            cx.execute(
                "INSERT INTO thesis_integrity_log "
                "(seq, thesis_id, payload_json, prev_hash, chain_hash) "
                "VALUES (?, ?, ?, ?, ?)",
                (next_seq, thesis_id, payload_json, prev_hash, new_hash),
            )
            return {"seq": next_seq, "chain_hash": new_hash}
    except Exception as e:
        _copilot_log.warning(f"insert_thesis_integrity_row failed: {e}")
        return None


def get_thesis_integrity_chain() -> list[dict]:
    """A5 verify support : retourne toutes les rows ordonnees par seq.
    Format dict pour shared.integrity.verify_chain consumption."""
    try:
        with db() as cx:
            rows = cx.execute(
                "SELECT seq, thesis_id, captured_at, payload_json, "
                "       prev_hash, chain_hash, anchor_ref "
                "FROM thesis_integrity_log ORDER BY seq"
            ).fetchall()
            cols = ["seq", "thesis_id", "captured_at", "payload_json",
                    "prev_hash", "chain_hash", "anchor_ref"]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        _copilot_log.warning(f"get_thesis_integrity_chain failed: {e}")
        return []


def update_thesis_integrity_anchor(seq: int, anchor_ref: str) -> bool:
    """A4 support : ecrit anchor_ref (git tag signe / OpenTimestamps proof)
    apres anchor externe daily. NULL accepte pour rows pre-anchor."""
    try:
        with db() as cx:
            cx.execute(
                "UPDATE thesis_integrity_log SET anchor_ref = ? WHERE seq = ?",
                (anchor_ref, seq),
            )
            return True
    except Exception as e:
        _copilot_log.warning(f"update_thesis_integrity_anchor failed: {e}")
        return False


def get_all_latest_risk_signal_evaluations() -> dict[tuple[str, str], dict]:
    """Map {(risk_id, signal_id): latest_evaluation_dict} pour TOUTES les paires
    deja evaluees au moins une fois.

    Pattern SQL : window function ROW_NUMBER() partitionne par (risk_id, signal_id)
    + ORDER BY evaluated_at DESC + filter rn=1. Permet render.py de hydrater
    la vue declarative avec un seul query DB."""
    try:
        with db() as cx:
            rows = cx.execute("""
                SELECT id, evaluated_at, risk_id, signal_id, status,
                       reason, confidence, evidence_ids_json, transition
                FROM (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY risk_id, signal_id
                        ORDER BY evaluated_at DESC, id DESC
                    ) AS rn
                    FROM risk_signal_evaluations
                )
                WHERE rn = 1
            """).fetchall()
            cols = ["id", "evaluated_at", "risk_id", "signal_id", "status",
                    "reason", "confidence", "evidence_ids_json", "transition"]
            return {
                (row[2], row[3]): dict(zip(cols, row, strict=False))
                for row in rows
            }
    except Exception as e:
        _copilot_log.warning(f"get_all_latest_risk_signal_evaluations failed: {e}")
        return {}


# === data_clusters_snapshots (Sprint 17) =====================================

_DC_DDL = (
    "CREATE TABLE IF NOT EXISTS data_clusters_snapshots ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "created_at TEXT NOT NULL DEFAULT (datetime('now')), "
    "snapshot_date TEXT NOT NULL, "
    "snapshot_json TEXT NOT NULL)"
)


def _ensure_dc_table(conn: _sqlite3.Connection) -> None:
    conn.execute(_DC_DDL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dc_date ON data_clusters_snapshots(snapshot_date)")


def insert_data_clusters_snapshot(snapshot_json: str) -> int | None:
    from datetime import UTC as _UTC, datetime as _dt
    try:
        with db() as cx:
            _ensure_dc_table(cx)
            cur = cx.execute(
                "INSERT INTO data_clusters_snapshots (snapshot_date, snapshot_json) VALUES (?,?)",
                (_dt.now(_UTC).date().isoformat(), snapshot_json),
            )
            return cur.lastrowid
    except Exception as e:
        _copilot_log.warning(f"insert_data_clusters_snapshot failed: {e}")
        return None


# ─────────────────────── PASSERELLE DERIVEE (point #3 du brief) ────────────
# "Tout calcul de derive passe par UNE SEULE fonction storage.get_position_view"
# Cette passerelle delegue a shared.views, le module de calcul. Mais l'API
# stable et publique vit ici, sur storage.py -- conforme au principe
# "passerelle unique" (CONVENTIONS §5).


def get_position_view(ticker: str | None = None):
    """Passerelle UNIQUE pour acceder aux derives portfolio (point #3 brief).

    Args:
        ticker: si fourni, retourne le PositionView de ce ticker (ou None).
                Si None, retourne le BookView complet.

    Returns:
        - PositionView (frozen dataclass) si ticker fourni et present
        - BookView (avec by_ticker, by_macro_factor, totals) si ticker=None
        - None si ticker non trouve

    REGLE : aucun calcul de poids/asymetrie/P&L hors de cette fonction.
    Si une vue importe shared.views directement, c'est tolere (passerelle
    interne). Si une vue calcule p["weight"] / total -> bug a souder.
    """
    from shared import views

    if ticker is None:
        return views.compute_book_view()
    return views.compute_book_view().view_of(ticker)


def get_book_view():
    """Alias explicit pour le BookView complet. Equivalent get_position_view()
    sans ticker. Lisibilite cote appelant."""
    from shared import views

    return views.compute_book_view()


def assert_book_invariants(*, strict: bool = True) -> list[str]:
    """Lance le gate statique des invariants (point #9 brief).

    Appelle au demarrage de l'app et en CI. strict=True (defaut) leve
    InvariantViolation au moindre defaut.

    Returns:
        Liste vide si tout est vert. Liste de violations sinon.
    """
    from shared import position_invariants as _pi

    with db() as cx:
        return _pi.run_static_gate(cx, strict=strict)


def __getattr__(name: str):
    """Module-level __getattr__ : resolve _DB_PATH dynamiquement vers DB_PATH.

    Pourquoi : ~28 callers externes lisent storage._DB_PATH. Anciennement
    un attribut statique, sa valeur etait frozen au load et un monkeypatch
    sur storage.DB_PATH n'affectait pas storage._DB_PATH (bug pollution
    prod 30/05). En passant par __getattr__, l'acces storage._DB_PATH lit
    la valeur COURANTE de DB_PATH a chaque fois -> monkeypatch propage.

    Python 3.7+ module __getattr__ s'applique uniquement aux attributs
    absents du namespace module. Donc setattr(storage, "_DB_PATH", x)
    override ce mecanisme et fixe l'attribut explicitement (toujours
    possible si besoin special). Pour le cas usage normal, on ne fait
    PAS setattr _DB_PATH -- on monkeypatch DB_PATH et _DB_PATH suit.
    """
    if name == "_DB_PATH":
        return DB_PATH
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
