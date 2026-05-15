"""Property-based tests for storage.compute_drift_report."""
from hypothesis import given, strategies as st
from shared import storage


def test_drift_report_runs_clean():
    """Smoke: compute_drift_report returns dict with expected keys."""
    report = storage.compute_drift_report()
    assert "summary" in report
    s = report["summary"]
    assert "capital_deployed_eur" in s
    assert "capital_target_eur" in s
    assert "pct_deployed" in s


def test_drift_report_account_invariants():
    """Per-account: total_target - total_actual == total_drift (within float epsilon)."""
    report = storage.compute_drift_report()
    for account, block in report.items():
        if account == "summary":
            continue
        assert isinstance(block.get("rows"), list)
        computed_drift = block["total_target"] - block["total_actual"]
        assert abs(computed_drift - block["total_drift"]) < 0.01, \
            f"{account}: drift mismatch {computed_drift} vs {block['total_drift']}"


def test_drift_report_summary_consistency():
    """Summary capital_deployed + pending == target (within epsilon)."""
    report = storage.compute_drift_report()
    s = report["summary"]
    assert abs(s["capital_deployed_eur"] + s["capital_pending_eur"] - s["capital_target_eur"]) < 0.01


def test_drift_report_pct_in_range():
    """pct_deployed in [0, 200] (allow >100 if drift goes negative from orphans)."""
    report = storage.compute_drift_report()
    pct = report["summary"]["pct_deployed"]
    assert -1.0 <= pct <= 200.0, f"pct_deployed {pct} out of expected range"
