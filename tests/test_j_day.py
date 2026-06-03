"""Tests J-day batch close job (#13)."""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from bot.jobs.j_day import J_DAY_DATE, _build_brier_telegram_msg


def _insert_pred(cx: sqlite3.Connection, **kw):
    cols = (
        "signal_id, ticker, direction, horizon_days, baseline_date, target_date, "
        "resolved_at, return_pct, outcome, probability_at_creation, brier_score, "
        "methodology_version"
    )
    vals = tuple(
        kw.get(c.strip()) for c in cols.split(",")
    )
    cx.execute(
        f"INSERT INTO predictions ({cols}) VALUES ({','.join('?' * len(vals))})",
        vals,
    )
    cx.commit()


def test_build_brier_msg_empty_returns_no_resolution(migrated_db):
    with patch("shared.storage.db") as mock_db:
        mock_db.return_value.__enter__.return_value = sqlite3.connect(migrated_db)
        mock_db.return_value.__enter__.return_value.row_factory = sqlite3.Row
        msg, metrics = _build_brier_telegram_msg("2099-01-01")
    # ADR 014 disambiguation : J-day est un archive-report V1, marker honnete
    # explicite (jamais silent zero) cf docs/adrs/014.
    assert "aucune prediction V1 resolue" in msg
    assert metrics == {}


def test_build_brier_msg_counts_outcomes(migrated_db):
    cx = sqlite3.connect(migrated_db)
    cx.row_factory = sqlite3.Row
    _insert_pred(cx, signal_id=1, ticker="NVDA", direction="bullish", horizon_days=28,
                 baseline_date="2026-05-13", target_date="2026-06-10",
                 resolved_at="2026-06-10 09:05:00", return_pct=0.05,
                 outcome="correct", probability_at_creation=0.6, brier_score=0.16,
                 methodology_version="v1")
    _insert_pred(cx, signal_id=2, ticker="AMD", direction="bullish", horizon_days=28,
                 baseline_date="2026-05-13", target_date="2026-06-10",
                 resolved_at="2026-06-10 09:05:00", return_pct=-0.05,
                 outcome="incorrect", probability_at_creation=0.6, brier_score=0.36,
                 methodology_version="v1")
    _insert_pred(cx, signal_id=3, ticker="TSM", direction="bullish", horizon_days=28,
                 baseline_date="2026-05-13", target_date="2026-06-10",
                 resolved_at="2026-06-10 09:05:00", return_pct=0.0,
                 outcome="neutral", probability_at_creation=0.6, brier_score=None,
                 methodology_version="v1")

    with patch("shared.storage.db") as mock_db:
        mock_db.return_value.__enter__.return_value = cx
        msg, metrics = _build_brier_telegram_msg(J_DAY_DATE)

    assert metrics["n_total"] == 3
    assert metrics["n_correct"] == 1
    assert metrics["n_incorrect"] == 1
    assert metrics["n_neutral"] == 1
    assert metrics["n_scored"] == 2  # neutral excluded
    assert metrics["brier_raw_avg"] == pytest.approx(0.26, abs=0.01)
    assert "J-DAY BATCH" in msg
    assert "N resolved: 3 (1/1/1" in msg


def test_build_brier_msg_mono_bucket_warning(migrated_db):
    """All probas at same value -> mono-bucket warning fires."""
    cx = sqlite3.connect(migrated_db)
    cx.row_factory = sqlite3.Row
    for tk, brier in [("NVDA", 0.16), ("AMD", 0.36), ("TSM", 0.36)]:
        _insert_pred(cx, signal_id=1, ticker=tk, direction="bullish",
                     horizon_days=28, baseline_date="2026-05-13",
                     target_date="2026-06-10", resolved_at="2026-06-10 09:05:00",
                     return_pct=0.05, outcome="correct",
                     probability_at_creation=0.626, brier_score=brier,
                     methodology_version="v1")
    with patch("shared.storage.db") as mock_db:
        mock_db.return_value.__enter__.return_value = cx
        msg, metrics = _build_brier_telegram_msg(J_DAY_DATE)
    assert metrics["mono_bucket_warning"] is True
    assert "WARNING" in msg
    assert "<=2 unique buckets" in msg


def test_build_brier_msg_cluster_dedup(migrated_db):
    """Same signal_id + ticker + direction collapses to 1 cluster."""
    cx = sqlite3.connect(migrated_db)
    cx.row_factory = sqlite3.Row
    # 3 predictions same cluster (same signal_id + NVDA + bullish)
    for prob, brier in [(0.6, 0.16), (0.6, 0.20), (0.6, 0.24)]:
        _insert_pred(cx, signal_id=42, ticker="NVDA", direction="bullish",
                     horizon_days=28, baseline_date="2026-05-13",
                     target_date="2026-06-10", resolved_at="2026-06-10 09:05:00",
                     return_pct=0.05, outcome="correct",
                     probability_at_creation=prob, brier_score=brier,
                     methodology_version="v1")
    # 1 distinct (different signal_id)
    _insert_pred(cx, signal_id=99, ticker="AMD", direction="bullish",
                 horizon_days=28, baseline_date="2026-05-13",
                 target_date="2026-06-10", resolved_at="2026-06-10 09:05:00",
                 return_pct=0.05, outcome="correct",
                 probability_at_creation=0.7, brier_score=0.30,
                 methodology_version="v1")
    with patch("shared.storage.db") as mock_db:
        mock_db.return_value.__enter__.return_value = cx
        msg, metrics = _build_brier_telegram_msg(J_DAY_DATE)
    assert metrics["n_scored"] == 4
    assert metrics["n_clusters"] == 2
    assert metrics["dedup_ratio"] == pytest.approx(2.0, abs=0.01)
    assert "dedup ratio 2.00x" in msg
