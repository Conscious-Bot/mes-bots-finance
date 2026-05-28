"""Unit tests for shared.sql_observability.

Note on log capture: we use a custom StreamHandler attached per-test to the
'sql' logger instead of pytest's caplog. Reason: caplog interacts with root
logger config and other tests' logging.basicConfig() calls (e.g. bot.main
import) cause flaky behavior when the full suite runs. Custom handler is
deterministic and independent.
"""

import io
import logging
import sqlite3

import pytest

from shared.sql_observability import _extract_error_context, query


@pytest.fixture
def conn():
    """In-memory DB with a small fixture table."""
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY, ticker TEXT, qty REAL)")
    c.executemany(
        "INSERT INTO positions(ticker, qty) VALUES (?, ?)",
        [
            ("NVDA", 100.0),
            ("TSM", 50.0),
            ("AMD", 30.0),
        ],
    )
    c.commit()
    return c


@pytest.fixture
def log_capture(monkeypatch):
    """Monkeypatch shared.sql_observability._log with a capturing stub.

    Bypasses Python logging framework entirely → no interaction with pytest
    log capture, no interference from other modules' basicConfig() calls,
    no test ordering issues. Pure functional check: did query() call
    _log.<level>(msg) with the expected message?

    Returns a list of (level, msg) tuples capturing all log calls during
    the test. Test assertions check this list directly.

    The production behavior (logs reaching stderr/file/etc.) is a
    configuration concern verified separately, not in unit tests.
    """
    from shared import sql_observability

    captured: list[tuple[str, str]] = []

    class CapturingLogger:
        def info(self, msg, *args, **kwargs):
            captured.append(("INFO", msg))

        def error(self, msg, *args, **kwargs):
            captured.append(("ERROR", msg))

        def warning(self, msg, *args, **kwargs):
            captured.append(("WARNING", msg))

        def debug(self, msg, *args, **kwargs):
            captured.append(("DEBUG", msg))

    monkeypatch.setattr(sql_observability, "_log", CapturingLogger())
    return captured


class TestQueryReadPaths:
    def test_fetch_all_returns_list(self, conn):
        rows = query(conn, "SELECT * FROM positions WHERE qty > ?", (40,), tag="t.fetch_all", fetch="all")
        assert isinstance(rows, list)
        assert len(rows) == 2

    def test_fetch_all_empty_returns_empty_list(self, conn):
        rows = query(conn, "SELECT * FROM positions WHERE qty > ?", (9999,), tag="t.empty_all", fetch="all")
        assert rows == []

    def test_fetch_one_returns_row(self, conn):
        row = query(conn, "SELECT ticker FROM positions WHERE id=?", (1,), tag="t.fetch_one", fetch="one")
        assert row == ("NVDA",)

    def test_fetch_one_none_when_no_match(self, conn):
        row = query(conn, "SELECT * FROM positions WHERE id=?", (999,), tag="t.no_match", fetch="one")
        assert row is None


class TestQueryWritePaths:
    def test_update_returns_cursor_with_rowcount(self, conn):
        cur = query(conn, "UPDATE positions SET qty=? WHERE id=?", (200.0, 1), tag="t.update")
        assert cur.rowcount == 1

    def test_insert_returns_cursor_with_lastrowid(self, conn):
        cur = query(conn, "INSERT INTO positions(ticker, qty) VALUES (?, ?)", ("MSFT", 75.0), tag="t.insert")
        assert cur.lastrowid is not None

    def test_delete_rowcount(self, conn):
        cur = query(conn, "DELETE FROM positions WHERE ticker=?", ("TSM",), tag="t.delete")
        assert cur.rowcount == 1


class TestLogging:
    def test_happy_path_logs_info(self, conn, log_capture):
        query(conn, "SELECT * FROM positions", tag="t.happy", fetch="all")
        info_logs = [m for lvl, m in log_capture if lvl == "INFO"]
        assert any("[SQL] t.happy" in m for m in info_logs), info_logs
        assert any("rows=3" in m for m in info_logs), info_logs

    def test_error_logs_error(self, conn, log_capture):
        with pytest.raises(sqlite3.OperationalError):
            query(conn, "SELECT * FROM nonexistent", tag="t.err")
        err_logs = [m for lvl, m in log_capture if lvl == "ERROR"]
        assert any("[SQL ERROR] t.err" in m for m in err_logs), err_logs

    def test_error_context_extracted_for_missing_table(self, conn, log_capture):
        with pytest.raises(sqlite3.OperationalError):
            query(conn, "SELECT * FROM missing_table", tag="t.errtable")
        err_logs = [m for lvl, m in log_capture if lvl == "ERROR"]
        assert any("table=missing_table" in m for m in err_logs), err_logs

    def test_error_context_extracted_for_missing_column(self, conn, log_capture):
        with pytest.raises(sqlite3.OperationalError):
            query(conn, "SELECT bad_col FROM positions", tag="t.errcol")
        err_logs = [m for lvl, m in log_capture if lvl == "ERROR"]
        assert any("column=bad_col" in m for m in err_logs), err_logs


class TestErrorContextExtraction:
    def test_no_such_table(self):
        e = sqlite3.OperationalError("no such table: foo")
        assert _extract_error_context(e) == {"table": "foo"}

    def test_no_such_column(self):
        e = sqlite3.OperationalError("no such column: bar")
        assert _extract_error_context(e) == {"column": "bar"}

    def test_table_has_no_column_named(self):
        e = sqlite3.OperationalError("table positions has no column named foo_col")
        ctx = _extract_error_context(e)
        assert ctx == {"table": "positions", "column": "foo_col"}

    def test_unknown_error_returns_empty(self):
        e = sqlite3.OperationalError("syntax error near 'WHERE'")
        assert _extract_error_context(e) == {}


class TestTagFallback:
    def test_tag_defaults_to_caller_when_none(self, conn, log_capture):
        query(conn, "SELECT 1", tag=None, fetch="one")
        info_logs = [m for lvl, m in log_capture if lvl == "INFO"]
        # Bare minimum: a [SQL] line was emitted with a non-None tag.
        # We don't assert exact caller filename — inspect.stack() in pytest
        # context may surface internal wrapper frames before the test frame.
        assert any("[SQL]" in m for m in info_logs), info_logs
        assert not any("[SQL] None " in m for m in info_logs), info_logs
        # Tag should have module:function:line format (colons present)
        assert any(":" in m for m in info_logs), info_logs
