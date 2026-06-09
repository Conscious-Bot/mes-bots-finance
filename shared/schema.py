"""Schema introspection helpers — forcing function for Lesson 21.

USAGE PATTERN (write-time guard, opt-in):

    from shared.schema import assert_column_exists

    def my_new_query():
        assert_column_exists("position_events", "ts")  # fails fast if drift
        cx.execute("SELECT ts FROM position_events WHERE ...")

Without this guard, invented identifiers (typos, assumed columns, drift)
only surface at runtime via cryptic SQLite OperationalError. Lesson 21
documented 5 such violations in a single session (Bash 99-105).

Helpers are LRU-cached, so calling them per-query is cheap (one PRAGMA
per table per process). Use generously — discipline > performance here.

CI complement: tests/test_schema_drift.py runs a static regex scan of
all Python source files to catch orphan table refs at lint time.
"""

import sqlite3
from functools import lru_cache
from pathlib import Path

_DB_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "bot.db"


class SchemaError(LookupError):
    """Raised when a schema invariant fails.

    Typed as LookupError so it composes with standard except clauses
    that already catch KeyError / IndexError patterns.
    """


@lru_cache(maxsize=4)
def _schema_cache(db_path: str) -> dict[str, tuple[str, ...]]:
    """{table_or_view_name -> tuple of column names}. Cached per db_path.

    Inclut tables ET views (depuis migration 0048, `positions` est une VIEW
    dérivée). PRAGMA table_info supporte les deux types sans distinction.
    """
    conn = sqlite3.connect(db_path)
    try:
        tables = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {t: tuple(r[1] for r in conn.execute(f"PRAGMA table_info({t})")) for t in tables}
    finally:
        conn.close()


def list_tables(db: Path | str = _DB_DEFAULT) -> list[str]:
    """Return sorted list of table names in the DB."""
    return sorted(_schema_cache(str(db)).keys())


def list_columns(table: str, db: Path | str = _DB_DEFAULT) -> list[str]:
    """Return list of column names for `table`. Raises SchemaError if table missing."""
    schema = _schema_cache(str(db))
    if table not in schema:
        raise SchemaError(f"Table '{table}' does not exist. Available: {sorted(schema.keys())}")
    return list(schema[table])


def assert_table_exists(table: str, db: Path | str = _DB_DEFAULT) -> None:
    """Raise SchemaError if `table` is not in the DB."""
    schema = _schema_cache(str(db))
    if table not in schema:
        raise SchemaError(f"Table '{table}' does not exist. Available: {sorted(schema.keys())}")


def assert_column_exists(table: str, column: str, db: Path | str = _DB_DEFAULT) -> None:
    """Raise SchemaError if `column` is not in `table` (table must also exist)."""
    cols = list_columns(table, db)
    if column not in cols:
        raise SchemaError(f"Column '{column}' not in table '{table}'. Available: {cols}")


def clear_cache() -> None:
    """Clear LRU cache. Useful after migrations or in tests."""
    _schema_cache.cache_clear()
