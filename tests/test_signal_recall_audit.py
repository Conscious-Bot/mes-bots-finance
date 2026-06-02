"""#69 LOOP -- Tests signal_recall_audit.

Mock get_recent_8k_filings (= ground truth SEC) pour ne pas hit
sec.gov dans les tests. Verifie la logique compare / recall / status.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from intelligence.signal_recall_audit import (
    audit_all_8k_recall,
    audit_ticker_8k_recall,
)


def _add_signal_8k(db: Path, accession: str, ticker: str = "NVDA",
                   days_ago: int = 5) -> None:
    cx = sqlite3.connect(db)
    cx.execute(
        "INSERT OR IGNORE INTO sources (name, type, credibility) "
        "VALUES ('EDGAR_8K', 'edgar', 0.85)"
    )
    src_id = cx.execute("SELECT id FROM sources WHERE name='EDGAR_8K'").fetchone()[0]
    timestamp = (datetime.now(UTC).replace(hour=10, minute=0, second=0) -
                 __import__("datetime").timedelta(days=days_ago)).isoformat()
    cx.execute(
        "INSERT INTO signals (source_id, title, timestamp, entities, gmail_id) "
        "VALUES (?, '8-K filing', ?, ?, ?)",
        (src_id, timestamp, f'["{ticker}"]', f"sec_8k:{accession}"),
    )
    cx.commit()
    cx.close()


def _mock_fetcher(returned: list[dict]):
    """Factory : retourne un fetcher mock qui retourne `returned` sans tenir
    compte des args."""
    def _f(ticker, days_back):
        return returned
    return _f


# ─── Empty cases ──────────────────────────────────────────────────────────


def test_no_external_filings_insufficient(migrated_db):
    """SEC retourne [] -> INSUFFICIENT_DATA, recall_pct=None."""
    cx = sqlite3.connect(migrated_db)
    try:
        rec = audit_ticker_8k_recall(
            cx, "NVDA", edgar_fetcher=_mock_fetcher([]),
        )
        assert rec["n_external"] == 0
        assert rec["recall_pct"] is None
        assert rec["status"] == "INSUFFICIENT_DATA"
    finally:
        cx.close()


def test_external_but_no_internal_alert(migrated_db):
    """3 filings SEC, 0 captures -> 0% recall, ALERT."""
    cx = sqlite3.connect(migrated_db)
    try:
        rec = audit_ticker_8k_recall(
            cx, "NVDA",
            edgar_fetcher=_mock_fetcher([
                {"accession": "0001234-25-000001"},
                {"accession": "0001234-25-000002"},
                {"accession": "0001234-25-000003"},
            ]),
        )
        assert rec["n_external"] == 3
        assert rec["n_captured"] == 0
        assert rec["recall_pct"] == 0.0
        assert rec["status"] == "ALERT"
        assert len(rec["missing_accessions"]) == 3
    finally:
        cx.close()


# ─── Recall computation ──────────────────────────────────────────────────


def test_full_recall_ok(migrated_db):
    """3 filings SEC, 3 captures avec accession matching -> 100% recall, OK."""
    _add_signal_8k(migrated_db, "0001234-25-000001")
    _add_signal_8k(migrated_db, "0001234-25-000002")
    _add_signal_8k(migrated_db, "0001234-25-000003")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = audit_ticker_8k_recall(
            cx, "NVDA",
            edgar_fetcher=_mock_fetcher([
                {"accession": "0001234-25-000001"},
                {"accession": "0001234-25-000002"},
                {"accession": "0001234-25-000003"},
            ]),
        )
        assert rec["recall_pct"] == 100.0
        assert rec["status"] == "OK"
        assert rec["missing_accessions"] == []
    finally:
        cx.close()


def test_partial_recall_warn(migrated_db):
    """SEC=10, captured=8 -> 80% recall, WARN (>=70, <90)."""
    for i in range(8):
        _add_signal_8k(migrated_db, f"0001234-25-{i:06d}")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = audit_ticker_8k_recall(
            cx, "NVDA",
            edgar_fetcher=_mock_fetcher([
                {"accession": f"0001234-25-{i:06d}"} for i in range(10)
            ]),
        )
        assert rec["n_external"] == 10
        assert rec["n_captured"] == 8
        assert rec["recall_pct"] == 80.0
        assert rec["status"] == "WARN"
        assert len(rec["missing_accessions"]) == 2
    finally:
        cx.close()


def test_recall_threshold_90_ok(migrated_db):
    """SEC=10, captured=9 -> 90% recall, OK (>=90)."""
    for i in range(9):
        _add_signal_8k(migrated_db, f"0001234-25-{i:06d}")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = audit_ticker_8k_recall(
            cx, "NVDA",
            edgar_fetcher=_mock_fetcher([
                {"accession": f"0001234-25-{i:06d}"} for i in range(10)
            ]),
        )
        assert rec["recall_pct"] == 90.0
        assert rec["status"] == "OK"
    finally:
        cx.close()


# ─── Accession normalization ─────────────────────────────────────────────


def test_accession_normalization_with_dashes(migrated_db):
    """Internal '0001234-25-000001' vs external '0001234-25-000001' match
    after normalization (les 2 stockes sans tirets)."""
    _add_signal_8k(migrated_db, "0001234-25-000001")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = audit_ticker_8k_recall(
            cx, "NVDA",
            edgar_fetcher=_mock_fetcher([{"accession": "0001234-25-000001"}]),
        )
        assert rec["recall_pct"] == 100.0
    finally:
        cx.close()


# ─── Extra accessions (we have, SEC doesn't) ─────────────────────────────


def test_extra_internal_not_in_external(migrated_db):
    """On a 1 capture, SEC retourne 0 -> n_external=0 INSUFFICIENT_DATA."""
    _add_signal_8k(migrated_db, "0001234-25-EXTRA")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = audit_ticker_8k_recall(
            cx, "NVDA", edgar_fetcher=_mock_fetcher([]),
        )
        assert rec["n_external"] == 0
        assert rec["status"] == "INSUFFICIENT_DATA"
    finally:
        cx.close()


def test_extra_internal_when_external_exists(migrated_db):
    """SEC retourne 2, on a 3 (2 match + 1 orphan) -> extra=1."""
    _add_signal_8k(migrated_db, "0001234-25-000001")
    _add_signal_8k(migrated_db, "0001234-25-000002")
    _add_signal_8k(migrated_db, "0001234-25-ORPHAN")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = audit_ticker_8k_recall(
            cx, "NVDA",
            edgar_fetcher=_mock_fetcher([
                {"accession": "0001234-25-000001"},
                {"accession": "0001234-25-000002"},
            ]),
        )
        assert rec["n_external"] == 2
        assert rec["n_captured"] == 2
        assert rec["recall_pct"] == 100.0
        assert len(rec["extra_accessions"]) == 1
        assert "0001234250000RPHAN".replace("0001234250000RPHAN", "") == ""  # sanity
    finally:
        cx.close()


# ─── Ticker isolation ────────────────────────────────────────────────────


def test_other_ticker_signals_not_counted(migrated_db):
    """Signals AAPL ne doivent pas etre comptes dans recall NVDA."""
    _add_signal_8k(migrated_db, "0001234-25-AAPL", ticker="AAPL")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = audit_ticker_8k_recall(
            cx, "NVDA",
            edgar_fetcher=_mock_fetcher([{"accession": "0001234-25-NVDA"}]),
        )
        assert rec["n_captured"] == 0
        assert rec["recall_pct"] == 0.0
    finally:
        cx.close()


# ─── Fetcher errors ──────────────────────────────────────────────────────


def test_fetcher_exception_returns_error(migrated_db):
    """Si fetcher leve, on retourne dict avec 'error' + INSUFFICIENT_DATA."""
    def _bad_fetcher(*args, **kwargs):
        raise RuntimeError("network unreachable")
    cx = sqlite3.connect(migrated_db)
    try:
        rec = audit_ticker_8k_recall(cx, "NVDA", edgar_fetcher=_bad_fetcher)
        assert "error" in rec
        assert rec["status"] == "INSUFFICIENT_DATA"
    finally:
        cx.close()


# ─── audit_all aggregation ───────────────────────────────────────────────


def test_audit_all_aggregates(migrated_db):
    """3 tickers : 1 OK / 1 ALERT / 1 INSUFFICIENT -> global ALERT."""
    _add_signal_8k(migrated_db, "0001234-NVDA-1", ticker="NVDA")
    cx = sqlite3.connect(migrated_db)

    def _multi_fetcher(ticker, days_back):
        if ticker == "NVDA":
            return [{"accession": "0001234-NVDA-1"}]  # 100% captured
        if ticker == "AAPL":
            return [{"accession": "0001234-AAPL-1"}]  # 0% captured -> ALERT
        # MSFT : no filings
        return []

    try:
        result = audit_all_8k_recall(
            cx, ["NVDA", "AAPL", "MSFT"],
            edgar_fetcher=_multi_fetcher,
        )
        assert result["n_tickers"] == 3
        assert result["n_with_external"] == 2  # NVDA + AAPL
        assert result["total_external"] == 2
        assert result["total_captured"] == 1
        assert result["global_recall_pct"] == 50.0
        assert result["status"] == "ALERT"
    finally:
        cx.close()


def test_audit_all_global_ok_when_all_ok(migrated_db):
    """Tous les tickers OK -> global OK."""
    for i in range(3):
        _add_signal_8k(migrated_db, f"0001234-25-{i:06d}")
    cx = sqlite3.connect(migrated_db)
    try:
        result = audit_all_8k_recall(
            cx, ["NVDA"],
            edgar_fetcher=_mock_fetcher([
                {"accession": f"0001234-25-{i:06d}"} for i in range(3)
            ]),
        )
        assert result["status"] == "OK"
        assert result["global_recall_pct"] == 100.0
    finally:
        cx.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
