"""SQL execution wrapper with observability.

Goal: diagnose silent SQL failures in 10sec instead of 30min. Wraps
sqlite3 conn/cursor execute() calls with:
- Duration (ms)
- Rows affected/returned
- Exception capture + context extraction (table/column from sqlite error msg)
- Caller frame inspect (module:function:lineno)
- Tag métier (optional explicit label)

USAGE:

    from shared.sql_observability import query

    # Read with fetchall:
    rows = query(cx, "SELECT id, ticker FROM positions WHERE status=?", ("active",),
                 tag="positions.load_active", fetch="all")

    # Read with fetchone:
    row = query(cx, "SELECT * FROM theses WHERE id=?", (tid,),
                tag="theses.get_by_id", fetch="one")

    # Write (INSERT/UPDATE/DELETE):
    query(cx, "UPDATE positions SET qty=? WHERE id=?", (q, pid),
          tag="positions.update_qty")

DESIGN CHOICES:

- Logger 'sql' separated from default 'bot' logger. Format:
    [SQL] {tag} {duration_ms}ms rows={n}            (happy path, INFO)
    [SQL ERROR] {tag} {context} caller={f}:{line}   (error, ERROR)

- Caller inspect uses inspect.stack()[1] for module:function:lineno.
  Falls back to '<unknown>' if frame unavailable (e.g. compiled code).

- Tag defaults to caller-inspected '{module}.{function}' if not provided.
  Explicit tags preferred for clearer log filtering.

- fetch=None means no result expected (write or DDL). Returns the cursor
  so caller can access .rowcount or .lastrowid if needed.

- fetch='all' returns rows list (or empty list, never None).
- fetch='one' returns single row tuple/dict or None if no match.

- Exception context: sqlite error messages often contain table/column hints.
  We extract them via regex to surface in the [SQL ERROR] line. Re-raises
  the original exception so callers can handle as before.

DOES NOT replace conn.execute(). Migration is progressive — wrap sites
where observability has high ROI (frequent crons, complex queries, recent
bug clusters). Bare conn.execute() remains valid for trivial one-shots.
"""

import inspect
import logging
import re
import sqlite3
import time
from typing import Any

_log = logging.getLogger("sql")

# Sqlite error messages we want to surface as structured context.
# Patterns derived empirically from sqlite3 error strings in Python 3.14.
# Sqlite error patterns. Empirically derived — verify with smoke before deploy.
_TABLE_MISSING_RE = re.compile(r"no such table:\s*([a-z_][a-z0-9_]*)", re.IGNORECASE)
_TABLE_COLUMN_RE = re.compile(
    r"table\s+([a-z_][a-z0-9_]*)\s+has no column named\s+([a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)
_COLUMN_RE = re.compile(r"no such column:?\s*([a-z_][a-z0-9_.]*)", re.IGNORECASE)


def _extract_error_context(exc: Exception) -> dict[str, str]:
    """Pull table/column hints out of sqlite error messages.

    Tries in order: missing-table, table-no-such-column, missing-column.
    The table-no-such-column pattern surfaces BOTH table and column.
    """
    msg = str(exc)
    ctx: dict[str, str] = {}
    if m := _TABLE_MISSING_RE.search(msg):
        ctx["table"] = m.group(1)
    elif m := _TABLE_COLUMN_RE.search(msg):
        ctx["table"] = m.group(1)
        ctx["column"] = m.group(2)
    if "column" not in ctx and (m := _COLUMN_RE.search(msg)):
        ctx["column"] = m.group(1)
    return ctx


def _caller_info(skip_frames: int = 2) -> str:
    """Return '{module}:{function}:{lineno}' for the caller skip_frames up.

    skip_frames=2 by default: 1 = _caller_info itself, 2 = query() wrapper,
    3 = actual caller. So pass skip_frames=2 to get the real caller.
    """
    try:
        stack = inspect.stack()
        if len(stack) <= skip_frames:
            return "<unknown>"
        frame = stack[skip_frames]
        module = frame.filename.split("/")[-1].replace(".py", "")
        return f"{module}:{frame.function}:{frame.lineno}"
    except Exception:
        return "<unknown>"


def query(
    conn: sqlite3.Connection | sqlite3.Cursor,
    sql: str,
    params: tuple | list | dict | None = None,
    *,
    tag: str | None = None,
    fetch: str | None = None,
) -> Any:
    """Execute SQL with observability.

    Args:
        conn: sqlite3 Connection or Cursor.
        sql:  SQL string.
        params: Optional bound parameters.
        tag:  Business label for log filtering. Defaults to caller frame.
        fetch: None | 'all' | 'one'. Controls return value:
               - None  → returns the cursor (caller may access rowcount, etc.)
               - 'all' → returns cursor.fetchall() list
               - 'one' → returns cursor.fetchone() row or None

    Raises:
        Re-raises any sqlite3.Error after logging structured context.
    """
    effective_tag = tag or _caller_info(skip_frames=2)
    start = time.perf_counter()
    try:
        if params is None:
            cur = conn.execute(sql)
        else:
            cur = conn.execute(sql, params)

        result: Any
        if fetch == "all":
            result = cur.fetchall()
            n = len(result)
        elif fetch == "one":
            result = cur.fetchone()
            n = 0 if result is None else 1
        else:
            result = cur
            n = cur.rowcount if cur.rowcount >= 0 else 0

        ms = int((time.perf_counter() - start) * 1000)
        _log.info(f"[SQL] {effective_tag} {ms}ms rows={n}")
        return result

    except sqlite3.Error as exc:
        ms = int((time.perf_counter() - start) * 1000)
        ctx = _extract_error_context(exc)
        ctx_str = " ".join(f"{k}={v}" for k, v in ctx.items())
        caller = _caller_info(skip_frames=2)
        _log.error(f"[SQL ERROR] {effective_tag} {ms}ms {ctx_str} caller={caller} | {type(exc).__name__}: {exc}")
        raise
