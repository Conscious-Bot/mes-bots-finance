"""#77 LOOP -- Tests signal_dedup_audit."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from intelligence.signal_dedup_audit import (
    compute_dedup_by_source,
    compute_dedup_quality,
    list_suspected_duplicates,
)


def _add_signal(db: Path, title: str, ticker: str = "NVDA",
                gmail_id: str | None = None,
                days_ago: int = 5,
                source_name: str = "src1") -> int:
    cx = sqlite3.connect(db)
    cx.execute(
        "INSERT OR IGNORE INTO sources (name, type, credibility) "
        "VALUES (?, 'newsletter', 0.7)",
        (source_name,),
    )
    src_id = cx.execute(
        "SELECT id FROM sources WHERE name=?", (source_name,)
    ).fetchone()[0]
    ts = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    # Generate unique gmail_id si non fourni
    import uuid as _uuid
    gid = gmail_id or f"gid:{_uuid.uuid4().hex[:12]}"
    cx.execute(
        "INSERT INTO signals (source_id, title, timestamp, entities, gmail_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (src_id, title, ts, f'["{ticker}"]', gid),
    )
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.commit()
    cx.close()
    return sig_id


# ─── compute_dedup_quality ────────────────────────────────────────────────


def test_empty_db_dedup_status_ok(migrated_db):
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_dedup_quality(cx)
        assert rec["n_total"] == 0
        assert rec["status"] == "OK"
        assert rec["collision_rate_pct"] == 0.0
    finally:
        cx.close()


def test_unique_signals_no_collision(migrated_db):
    """5 signals titres tous differents -> 0 collision, OK."""
    for i in range(5):
        _add_signal(migrated_db, title=f"Signal unique #{i}")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_dedup_quality(cx)
        assert rec["n_total"] == 5
        assert rec["n_distinct_gmail_id"] == 5
        assert rec["n_suspected_duplicates"] == 0
        assert rec["status"] == "OK"
    finally:
        cx.close()


def test_duplicate_titles_same_day_detected(migrated_db):
    """3 signals memes titres meme jour avec gmail_id distincts -> 3 suspected."""
    for _ in range(3):
        _add_signal(migrated_db, title="NVDA 8-K Q1 earnings beat", days_ago=2)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_dedup_quality(cx)
        assert rec["n_total"] == 3
        assert rec["n_distinct_gmail_id"] == 3  # gmail_id unique
        assert rec["n_suspected_duplicates"] == 3
        assert rec["n_groups_suspected"] == 1
        # 100% collision -> ALERT
        assert rec["status"] == "ALERT"
    finally:
        cx.close()


def test_different_days_not_grouped(migrated_db):
    """Meme titre mais jours differents -> pas group (fingerprint inclut jour)."""
    _add_signal(migrated_db, title="NVDA earnings", days_ago=2)
    _add_signal(migrated_db, title="NVDA earnings", days_ago=10)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_dedup_quality(cx)
        assert rec["n_suspected_duplicates"] == 0
    finally:
        cx.close()


def test_different_tickers_not_grouped(migrated_db):
    """Meme titre, meme jour, tickers differents -> pas group."""
    _add_signal(migrated_db, title="Quarterly earnings beat", ticker="NVDA", days_ago=2)
    _add_signal(migrated_db, title="Quarterly earnings beat", ticker="AAPL", days_ago=2)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_dedup_quality(cx)
        assert rec["n_suspected_duplicates"] == 0
    finally:
        cx.close()


def test_title_normalization_grouping(migrated_db):
    """Titres avec punct/case differents mais meme contenu -> grouped."""
    _add_signal(migrated_db, title="NVDA 8-K, Q1 EARNINGS BEAT!", days_ago=2)
    _add_signal(migrated_db, title="nvda 8-k q1 earnings beat", days_ago=2)
    _add_signal(migrated_db, title="NVDA  8-K  Q1   earnings beat", days_ago=2)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_dedup_quality(cx)
        assert rec["n_suspected_duplicates"] == 3
        assert rec["n_groups_suspected"] == 1
    finally:
        cx.close()


# ─── Status thresholds ──────────────────────────────────────────────────


def test_status_warn_when_rate_above_2pct(migrated_db):
    """50 signals unique + 2 duplicates -> 2/52 = 3.8% -> WARN."""
    for i in range(50):
        _add_signal(migrated_db, title=f"unique {i}", days_ago=2)
    _add_signal(migrated_db, title="dup news today", days_ago=2)
    _add_signal(migrated_db, title="dup news today", days_ago=2)
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_dedup_quality(cx)
        # rate = 2 / 52 * 100 = 3.85
        assert 2 < rec["collision_rate_pct"] < 5
        assert rec["status"] == "WARN"
    finally:
        cx.close()


# ─── list_suspected_duplicates ───────────────────────────────────────────


def test_list_returns_groups_sorted_desc(migrated_db):
    """Group avec n=4 puis n=2 -> n=4 first."""
    for _ in range(4):
        _add_signal(migrated_db, title="Big news today", days_ago=2)
    for _ in range(2):
        _add_signal(migrated_db, title="Small news today", days_ago=2)
    cx = sqlite3.connect(migrated_db)
    try:
        groups = list_suspected_duplicates(cx)
        assert len(groups) == 2
        assert groups[0]["n"] == 4
        assert groups[1]["n"] == 2
    finally:
        cx.close()


def test_min_group_size_filter(migrated_db):
    """min_group_size=3 -> groupe de 2 exclu."""
    for _ in range(2):
        _add_signal(migrated_db, title="news today", days_ago=2)
    cx = sqlite3.connect(migrated_db)
    try:
        groups2 = list_suspected_duplicates(cx, min_group_size=2)
        groups3 = list_suspected_duplicates(cx, min_group_size=3)
        assert len(groups2) == 1
        assert len(groups3) == 0
    finally:
        cx.close()


def test_skip_empty_titles(migrated_db):
    """Signals avec title vide/None ne sont pas comptes."""
    _add_signal(migrated_db, title="")
    _add_signal(migrated_db, title="")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = compute_dedup_quality(cx)
        assert rec["n_suspected_duplicates"] == 0
    finally:
        cx.close()


# ─── compute_dedup_by_source ─────────────────────────────────────────────


def test_dedup_by_source_attribution(migrated_db):
    """Source 'newsletter1' a 1 groupe de doublons, source2 unique."""
    _add_signal(migrated_db, title="dup news today", source_name="newsletter1", days_ago=2)
    _add_signal(migrated_db, title="dup news today", source_name="newsletter1", days_ago=2)
    _add_signal(migrated_db, title="unique news", source_name="newsletter2", days_ago=2)
    cx = sqlite3.connect(migrated_db)
    try:
        by_src = compute_dedup_by_source(cx)
        ns1 = next(x for x in by_src if x["source_name"] == "newsletter1")
        ns2 = next(x for x in by_src if x["source_name"] == "newsletter2")
        assert ns1["n_signals"] == 2
        assert ns1["n_suspected_duplicates"] == 2  # 2 rows in the dup group
        assert ns2["n_suspected_duplicates"] == 0
    finally:
        cx.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
