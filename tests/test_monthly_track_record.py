"""Tests monthly_track_record orchestrator (#89 cadence mensuelle)."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from intelligence.monthly_track_record import (
    list_snapshots,
    load_snapshot,
    run_monthly_track_record_job,
)


@pytest.fixture
def isolated_snapshots_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige _snapshots_dir vers tmp pour ne pas polluer data/."""
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir()
    monkeypatch.setattr(
        "intelligence.monthly_track_record._snapshots_dir",
        lambda: snap_dir,
    )
    return snap_dir


# ─── Smoke job ────────────────────────────────────────────────────────────


def test_job_creates_snapshot_file(migrated_db, isolated_snapshots_dir):
    cx = sqlite3.connect(migrated_db)
    try:
        result = run_monthly_track_record_job(cx)
        assert result["skipped"] is False
        assert "year_month" in result
        assert Path(result["snapshot_path"]).exists()
    finally:
        cx.close()


def test_snapshot_content_has_canonical_sections(migrated_db, isolated_snapshots_dir):
    cx = sqlite3.connect(migrated_db)
    try:
        result = run_monthly_track_record_job(cx)
        snap_path = Path(result["snapshot_path"])
        data = json.loads(snap_path.read_text())
        assert "year_month" in data
        assert "generated_at" in data
        assert "aggregator" in data
        assert "timeseries" in data
        assert "recal" in data
        # Aggregator section non-vide
        assert "posture_global" in data["aggregator"]
        assert "predictions" in data["aggregator"]
        assert "bias_events" in data["aggregator"]
        # Timeseries bundle
        assert "brier_rolling" in data["timeseries"]
        assert "bias_cumul_lock_in" in data["timeseries"]
    finally:
        cx.close()


def test_skip_when_snapshot_already_exists(migrated_db, isolated_snapshots_dir):
    cx = sqlite3.connect(migrated_db)
    try:
        result1 = run_monthly_track_record_job(cx)
        assert result1["skipped"] is False
        result2 = run_monthly_track_record_job(cx)
        assert result2["skipped"] is True
        assert result2["reason"] == "snapshot_already_exists"
    finally:
        cx.close()


def test_force_overwrites_existing(migrated_db, isolated_snapshots_dir):
    cx = sqlite3.connect(migrated_db)
    try:
        result1 = run_monthly_track_record_job(cx)
        # Modifie le snapshot manuellement pour detecter overwrite
        snap_path = Path(result1["snapshot_path"])
        snap_path.write_text('{"manual": true}')
        assert json.loads(snap_path.read_text()) == {"manual": True}

        result2 = run_monthly_track_record_job(cx, force=True)
        assert result2["skipped"] is False
        data = json.loads(snap_path.read_text())
        assert "manual" not in data
        assert "aggregator" in data
    finally:
        cx.close()


# ─── Recal applied ────────────────────────────────────────────────────────


def test_recal_dry_run_does_not_apply(migrated_db, isolated_snapshots_dir):
    """dry_run=True : recal calcule mais pas applique en DB."""
    # Seed source avec credibility a priori
    cx = sqlite3.connect(migrated_db)
    cx.execute(
        "INSERT INTO sources (name, type, credibility) VALUES ('s', 'newsletter', 0.5)"
    )
    cx.execute("INSERT INTO signals (source_id, title, timestamp, entities) "
               "VALUES (1, 't', ?, '[\"X\"]')",
               (datetime.now(UTC).isoformat(),))
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    # 10 predictions resolved correct brier 0.10
    for _ in range(10):
        cx.execute(
            "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, "
            "baseline_price, baseline_date, target_date, probability_at_creation, "
            "brier_score, outcome, resolved_at, methodology_version) "
            "VALUES (?, 'X', 'bullish', 28, 100.0, "
            "date('now', '-30 days'), date('now', '-2 days'), 0.7, 0.10, "
            "'correct', datetime('now', '-2 days'), 'v2')",
            (sig_id,),
        )
    cx.commit()
    cx.close()
    cx = sqlite3.connect(migrated_db)
    try:
        result = run_monthly_track_record_job(cx, recal_dry_run=True)
        assert result["recal_summary"]["n_sources_processed"] >= 1
        # Pas d'apply attendu
        assert result["recal_summary"]["n_applied"] == 0
        # Credibility en DB inchangee
        cred = cx.execute("SELECT credibility FROM sources WHERE name='s'").fetchone()[0]
        assert cred == 0.5
    finally:
        cx.close()


def test_recal_actually_applies_when_not_dry_run(migrated_db, isolated_snapshots_dir):
    cx = sqlite3.connect(migrated_db)
    cx.execute(
        "INSERT INTO sources (name, type, credibility) VALUES ('s', 'newsletter', 0.5)"
    )
    cx.execute("INSERT INTO signals (source_id, title, timestamp, entities) "
               "VALUES (1, 't', ?, '[\"X\"]')",
               (datetime.now(UTC).isoformat(),))
    sig_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    for _ in range(10):
        cx.execute(
            "INSERT INTO predictions (signal_id, ticker, direction, horizon_days, "
            "baseline_price, baseline_date, target_date, probability_at_creation, "
            "brier_score, outcome, resolved_at, methodology_version) "
            "VALUES (?, 'X', 'bullish', 28, 100.0, "
            "date('now', '-30 days'), date('now', '-2 days'), 0.7, 0.10, "
            "'correct', datetime('now', '-2 days'), 'v2')",
            (sig_id,),
        )
    cx.commit()
    cx.close()
    cx = sqlite3.connect(migrated_db)
    try:
        result = run_monthly_track_record_job(cx)
        assert result["recal_summary"]["n_applied"] >= 1
        # Credibility doit avoir monte (0.5 + 0.3*(0.90 - 0.5) = 0.62)
        cred = cx.execute("SELECT credibility FROM sources WHERE name='s'").fetchone()[0]
        assert cred > 0.5
    finally:
        cx.close()


# ─── load_snapshot + list_snapshots ───────────────────────────────────────


def test_load_snapshot_returns_data(migrated_db, isolated_snapshots_dir):
    cx = sqlite3.connect(migrated_db)
    try:
        result = run_monthly_track_record_job(cx)
        ym = result["year_month"]
    finally:
        cx.close()
    loaded = load_snapshot(ym)
    assert loaded is not None
    assert loaded["year_month"] == ym


def test_load_unknown_snapshot_returns_none(isolated_snapshots_dir):
    assert load_snapshot("1990-01") is None


def test_list_snapshots(migrated_db, isolated_snapshots_dir):
    # Avant le run : aucun
    assert list_snapshots() == []
    cx = sqlite3.connect(migrated_db)
    try:
        run_monthly_track_record_job(cx)
    finally:
        cx.close()
    snaps = list_snapshots()
    assert len(snaps) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
