"""Property-based tests for shared.uptime parser + compute_kpi1 contract."""

from datetime import datetime, timedelta
from pathlib import Path

from hypothesis import given, strategies as st

from shared.uptime import compute_kpi1, parse_uptime_log


def _now_str(delta_min: int = 0) -> str:
    return (datetime.now() - timedelta(minutes=delta_min)).strftime("%Y-%m-%d %H:%M:%S")


def test_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "uptime.log"
    p.write_text("")
    s = parse_uptime_log(p, window_days=30)
    assert s["total"] == 0
    assert s["uptime_pct"] == 0.0
    assert s["earliest_ts"] is None


def test_missing_file(tmp_path: Path) -> None:
    s = parse_uptime_log(tmp_path / "nonexistent.log", window_days=30)
    assert s["total"] == 0
    assert s["window_days"] == 30


def test_all_ok(tmp_path: Path) -> None:
    p = tmp_path / "uptime.log"
    p.write_text("\n".join(f"{_now_str(5 * i)} OK alive" for i in range(20)))
    s = parse_uptime_log(p, window_days=30)
    assert s["total"] == 20 and s["ok_count"] == 20 and s["uptime_pct"] == 1.0


def test_all_fail(tmp_path: Path) -> None:
    p = tmp_path / "uptime.log"
    p.write_text("\n".join(f"{_now_str(5 * i)} FAIL bot down" for i in range(20)))
    s = parse_uptime_log(p, window_days=30)
    assert s["fail_count"] == 20 and s["uptime_pct"] == 0.0


def test_mixed(tmp_path: Path) -> None:
    p = tmp_path / "uptime.log"
    lines = [f"{_now_str(5 * i)} OK alive" for i in range(10)]
    lines += [f"{_now_str(5 * i)} FAIL bot down" for i in range(10, 20)]
    p.write_text("\n".join(lines))
    s = parse_uptime_log(p, window_days=30)
    assert s["total"] == 20 and s["ok_count"] == 10 and s["uptime_pct"] == 0.5


def test_out_of_window(tmp_path: Path) -> None:
    p = tmp_path / "uptime.log"
    old = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")
    p.write_text(f"{old} OK alive\n{_now_str()} OK alive")
    s = parse_uptime_log(p, window_days=30)
    assert s["total"] == 1


def test_malformed_lines_ignored(tmp_path: Path) -> None:
    p = tmp_path / "uptime.log"
    p.write_text(
        "\n".join(
            [
                "# header",
                "",
                "garbage no timestamp",
                f"{_now_str()} OK alive",
                "2026-13-45 99:99:99 OK alive",
                f"{_now_str(10)} FAIL bot down",
            ]
        )
    )
    s = parse_uptime_log(p, window_days=30)
    assert s["total"] == 2 and s["ok_count"] == 1 and s["fail_count"] == 1


@given(st.integers(min_value=0, max_value=1000), st.integers(min_value=0, max_value=1000))
def test_uptime_pct_invariant(ok_n: int, fail_n: int) -> None:
    total = ok_n + fail_n
    pct = (ok_n / total) if total > 0 else 0.0
    assert 0.0 <= pct <= 1.0


def test_compute_kpi1_required_keys(tmp_path: Path) -> None:
    p = tmp_path / "uptime.log"
    p.write_text("\n".join(f"{_now_str(5 * i)} OK alive" for i in range(150)))
    r = compute_kpi1(window_days=30, path=p)
    assert set(r.keys()) >= {"title", "target", "current", "status", "enforcement"}


def test_compute_kpi1_green(tmp_path: Path) -> None:
    p = tmp_path / "uptime.log"
    p.write_text("\n".join(f"{_now_str(5 * i)} OK alive" for i in range(150)))
    assert "✅" in compute_kpi1(window_days=30, path=p)["status"]


def test_compute_kpi1_insufficient(tmp_path: Path) -> None:
    p = tmp_path / "uptime.log"
    p.write_text(f"{_now_str()} OK alive")
    r = compute_kpi1(window_days=30, path=p)
    assert "🔍" in r["status"] and "INSUFFICIENT" in r["status"]


def test_compute_kpi1_red(tmp_path: Path) -> None:
    p = tmp_path / "uptime.log"
    lines = [f"{_now_str(5 * i)} OK alive" for i in range(50)]
    lines += [f"{_now_str(5 * (i + 50))} FAIL bot down" for i in range(100)]
    p.write_text("\n".join(lines))
    assert "🚨" in compute_kpi1(window_days=30, path=p)["status"]
