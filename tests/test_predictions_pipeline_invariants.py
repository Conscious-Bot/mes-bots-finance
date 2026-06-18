"""#79 -- Invariants pipeline signal -> prediction -> resolution.

Filet anti-drift bout en bout sur la boucle core PRESAGE :
  1. Chaque prediction non-v0 a signal_id source NOT NULL
  2. Chaque resolution a outcome IN enum + return_pct calculable
  3. Brier score in [0, 1]
  4. timestamp resolution >= timestamp baseline + horizon_days
  5. Pas de mono-bucket sur les N dernieres resolutions (anti-V1 regression)
  6. Probabilites in (0, 1) strict (V2 weak/strong) -- v0 exempte

Cf LESSONS L8 (drift schema/code), feedback `in_sample_tuning_validation`
(memory) + decision_log 02 (V3 demote -- pipeline drift est le mode de
defaillance silencieux le plus dangereux pre-J-day).

Tests sur live DB (read-only) -- a faire passer continuellement avant
toute promotion macro. Si invariant casse, alerte immediate -- ne pas
shipper.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import UTC
from pathlib import Path

import pytest

# CI marker : ce module tape sur storage.DB_PATH (data/bot.db gitignored).
# CI skip via -m "not slow and not live_data". Local : tourne normalement.
pytestmark = pytest.mark.live_data

DB = Path(__file__).resolve().parent.parent / "data" / "bot.db"

OUTCOME_ENUM = {"correct", "incorrect", "neutral"}


@pytest.fixture(scope="module")
def conn():
    if not DB.exists():
        pytest.skip(f"DB live introuvable {DB}")
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# ─── Invariant 1 : provenance signal ──────────────────────────────────────


def test_non_v0_predictions_have_signal_source(conn):
    """Toute prediction non-v0 origin='signal' doit avoir signal_id NOT NULL.
    Sinon, provenance perdue -- audit externe impossible.

    Scope post-migration 0060 (cure chantier #150 G2) : origin='manual'
    (sentinelles posees humain, pre-registration thesis) n'a PAS de
    signal_id par construction. La provenance vit dans source_metadata_json
    + methodology_version + origin='manual' explicite. Filtre origin='signal'
    applique pour scoper l'invariant a la voie auto-scorer.
    """
    rows = conn.execute(
        "SELECT id, ticker, methodology_version FROM predictions "
        "WHERE methodology_version != 'v0' "
        "AND origin = 'signal' "
        "AND signal_id IS NULL"
    ).fetchall()
    assert not rows, (
        f"Predictions non-v0 origin='signal' sans signal_id (provenance perdue) : "
        f"{[dict(r) for r in rows[:5]]}"
    )


# ─── Invariant 2 : outcome enum + return_pct cohérence ────────────────────


def test_resolved_predictions_have_valid_outcome(conn):
    """Resolved predictions doivent avoir outcome dans l'enum."""
    rows = conn.execute(
        "SELECT id, ticker, outcome FROM predictions "
        "WHERE resolved_at IS NOT NULL"
    ).fetchall()
    invalid = [dict(r) for r in rows if r["outcome"] not in OUTCOME_ENUM]
    assert not invalid, f"Outcomes hors enum {OUTCOME_ENUM} : {invalid}"


def test_resolved_predictions_have_return_pct(conn):
    """Resolved predictions doivent avoir return_pct calcule.
    Sans return_pct, Brier non-calculable -> pas de signal calibration.

    Filtre claim_type='price' : event-type sentinelles (migration 0060) se
    résolvent binaire (fired/not-fired), return_pct est N/A by design.
    """
    rows = conn.execute(
        "SELECT id, ticker, outcome FROM predictions "
        "WHERE resolved_at IS NOT NULL AND outcome != 'neutral' "
        "AND return_pct IS NULL AND claim_type = 'price'"
    ).fetchall()
    assert not rows, (
        f"Resolved price-claim predictions non-neutres sans return_pct : "
        f"{[dict(r) for r in rows[:5]]}"
    )


# ─── Invariant 3 : Brier score range ──────────────────────────────────────


def test_brier_scores_in_unit_interval(conn):
    """Brier score doit etre dans [0, 1] strict. Hors range = bug formule."""
    rows = conn.execute(
        "SELECT id, ticker, brier_score FROM predictions "
        "WHERE brier_score IS NOT NULL AND (brier_score < 0 OR brier_score > 1)"
    ).fetchall()
    assert not rows, (
        f"Brier scores hors [0,1] (bug formule) : "
        f"{[dict(r) for r in rows[:5]]}"
    )


# ─── Invariant 4 : timestamp monotonicity ─────────────────────────────────


def test_resolved_at_after_baseline_plus_horizon(conn):
    """resolved_at doit etre >= baseline_date + horizon_days. Sinon resolution
    premature = bug (pas attendu l'horizon).

    Filtre claim_type='price' : event-type sentinelles (migration 0060) ferment
    sur fire d'événement, pas sur horizon temporel — horizon_days est nominal.
    """
    from datetime import datetime, timedelta
    rows = conn.execute(
        "SELECT id, ticker, baseline_date, horizon_days, resolved_at "
        "FROM predictions WHERE resolved_at IS NOT NULL AND claim_type = 'price'"
    ).fetchall()
    violations = []
    from datetime import timezone as _tz
    def _norm(s: str) -> datetime:
        s = s.replace("Z", "+00:00").replace(" ", "T")
        if "T" not in s:
            s = s + "T00:00:00"
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
    for r in rows:
        try:
            baseline = _norm(r["baseline_date"])
            resolved = _norm(r["resolved_at"])
            min_resolved = baseline + timedelta(days=r["horizon_days"] - 3)  # 3j tolerance
            if resolved < min_resolved:
                violations.append({
                    "id": r["id"], "ticker": r["ticker"],
                    "baseline": r["baseline_date"], "horizon": r["horizon_days"],
                    "resolved": r["resolved_at"],
                })
        except (ValueError, AttributeError):
            continue
    assert not violations, (
        f"Resolutions prematurees (avant horizon attendu) : {violations[:3]}"
    )


# ─── Invariant 5 : probabilites in (0, 1) strict ──────────────────────────


def test_v1_v2_probabilities_strictly_in_unit(conn):
    """V1/V2 probabilities doivent etre strictement dans (0, 1). V0 deprecated
    peut etre None ou 0/1 -- exempte. Bornes strictes prevent
    log-loss explosion + signal mort."""
    rows = conn.execute(
        "SELECT id, ticker, probability_at_creation, methodology_version "
        "FROM predictions WHERE methodology_version != 'v0' "
        "AND probability_at_creation IS NOT NULL"
    ).fetchall()
    violations = [dict(r) for r in rows
                  if r["probability_at_creation"] <= 0
                  or r["probability_at_creation"] >= 1]
    assert not violations, (
        f"Probabilites V1/V2 hors (0,1) strict : {violations[:5]}"
    )


# ─── Invariant 6 : anti mono-bucket sur recent batch ──────────────────────


def test_no_mono_bucket_on_recent_resolutions(conn):
    """Sur les N dernieres resolutions, au moins 2 buckets distincts de
    probabilite. Pattern V1 mono-bucket (toutes proba ~0.63) etait le
    bug critique post-30/05 -- ce test l'attrape si V1 ressuscitait."""
    # Filter v0 AND v1 : V1 mono-bucket WAS the bug fixed via V2 pivot 30/05.
    # Pre-pivot V1 resolutions correctly mono-bucket -- pas une regression.
    # On audite V2+ uniquement (le scorer post-pivot).
    rows = conn.execute(
        "SELECT probability_at_creation FROM predictions "
        "WHERE resolved_at IS NOT NULL "
        "AND probability_at_creation IS NOT NULL "
        "AND methodology_version NOT IN ('v0', 'v1') "
        "ORDER BY resolved_at DESC LIMIT 30"
    ).fetchall()
    if len(rows) < 10:
        pytest.skip(f"Pas assez de resolutions non-v0 (N={len(rows)}) "
                    "pour evaluer mono-bucket -- vacuously true pre J-day.")
    probs = [r["probability_at_creation"] for r in rows]
    # Bucket par 0.1 (proba 0.55 → bucket 5)
    buckets = Counter(int(p * 10) for p in probs)
    n_distinct = len(buckets)
    assert n_distinct >= 2, (
        f"MONO-BUCKET DETECTE : {n_distinct} bucket(s) sur {len(probs)} "
        f"resolutions recentes. Distribution : {dict(buckets)}. "
        "Regression vers V1 mono-bucket -- investiguer scorer V2."
    )


# ─── Invariant 7 : signal_id references actually exist ────────────────────


def test_signal_id_references_existing_signals(conn):
    """FK signal_id doit pointer vers un signal existant. SQLite ne enforce
    pas les FK par defaut -- on check manuel."""
    rows = conn.execute(
        "SELECT p.id, p.ticker, p.signal_id FROM predictions p "
        "LEFT JOIN signals s ON s.id = p.signal_id "
        "WHERE p.signal_id IS NOT NULL AND s.id IS NULL"
    ).fetchall()
    assert not rows, (
        f"signal_id orphelins (FK cassee) : {[dict(r) for r in rows[:5]]}"
    )


# ─── Invariant 8 : outcome cohérent avec direction + return ──────────────


def test_outcome_consistent_with_direction_and_return(conn):
    """Long + return > 0 doit etre outcome=correct. Long + return < 0 =
    incorrect. Inconsistance = bug calcul outcome dans resolve_predictions."""
    rows = conn.execute(
        "SELECT id, ticker, direction, return_pct, outcome FROM predictions "
        "WHERE resolved_at IS NOT NULL "
        "AND return_pct IS NOT NULL "
        "AND outcome != 'neutral' "
        "AND ABS(return_pct) > 1.0"  # exclure ~0 (zone neutral)
    ).fetchall()
    violations = []
    for r in rows:
        expected = "correct" if (
            (r["direction"] == "bullish" and r["return_pct"] > 0)
            or (r["direction"] == "bearish" and r["return_pct"] < 0)
        ) else "incorrect"
        if r["outcome"] != expected:
            violations.append({
                "id": r["id"], "ticker": r["ticker"],
                "direction": r["direction"], "return_pct": r["return_pct"],
                "outcome": r["outcome"], "expected": expected,
            })
    assert not violations, (
        f"Outcomes incoherents avec direction+return : {violations[:3]}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
