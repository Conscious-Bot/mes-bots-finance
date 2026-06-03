"""Static drift test: scan Python AST for .execute() / .executemany() SQL strings,
verify table refs exist in current DB schema.

Catches Lesson 21 'invented identifier' bugs at CI time, before runtime.

Approach: AST-walk every Python file in source dirs, find Call nodes that are
method calls to .execute() / .executemany(), parse the 1st arg if it's a
constant string, regex-extract table refs (FROM/JOIN/INTO/UPDATE), validate
against DB schema.

Limitations:
- f-strings and concatenated strings are NOT scanned (dynamic SQL, can't
  statically verify table names anyway — rare and intentional in codebase).
- Tables-only scope. Column drift requires per-table context parsing (defer).

If this test fails after a legitimate schema migration, run:
    python scripts/regen_schema_doc.py
And re-run pytest. New tables will be picked up automatically.
"""

import ast
import re
from pathlib import Path

import pytest

from shared.schema import clear_cache, list_tables

REPO = Path(__file__).resolve().parent.parent
SOURCE_DIRS = ("shared", "intelligence", "bot", "data_sources", "risk", "scripts")

# Match FROM/JOIN/INTO/UPDATE followed by identifier.
# Now operating on SQL strings ONLY (post-AST-filter), so prose false positives
# are impossible. Only false positives = SQL constructs like subquery aliases,
# CTE names, dynamic placeholders.
_SQL_TABLE_REF_RE = re.compile(
    r"(?:FROM|JOIN|INTO|UPDATE)\s+([a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)

# SQL constructs that pass the regex but are not real table names.
# Document each entry.
_WHITELIST = {
    "sqlite_master",  # SQLite system view
    "pragma_table_info",  # SQLite pragma (rarely used in FROM but possible)
    "before",  # SQL keyword in CREATE TRIGGER BEFORE INSERT/UPDATE/DELETE
    "on",  # SQL keyword in CREATE TRIGGER ... ON table_name
    # Migration 0028 (ADR 014 hazard B) : temp tables transient pour SQLite
    # ALTER COLUMN recipe (rename swap). Existent uniquement le temps de la
    # migration upgrade()/downgrade(), pas dans le schema final.
    "predictions_new",
    "predictions_old",
}


def _extract_execute_sql(file_path: Path) -> list[tuple[str, int]]:
    """Return list of (sql_string, line_no) for every .execute()/.executemany()
    call with a constant string 1st arg in this file."""
    try:
        tree = ast.parse(file_path.read_text(errors="ignore"))
    except SyntaxError:
        return []

    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in ("execute", "executemany"):
            continue
        if not node.args:
            continue
        arg0 = node.args[0]
        # Plain string literal
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
            found.append((arg0.value, node.lineno))
        # Concatenation of constant strings (e.g. "SELECT ..." + " FROM x")
        elif isinstance(arg0, ast.BinOp) and isinstance(arg0.op, ast.Add):
            parts = []
            ok = True
            for sub in (arg0.left, arg0.right):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    parts.append(sub.value)
                else:
                    ok = False
                    break
            if ok:
                found.append(("".join(parts), node.lineno))
    return found


def _all_source_files() -> list[Path]:
    """All .py files under SOURCE_DIRS."""
    out = []
    for sub in SOURCE_DIRS:
        sub_path = REPO / sub
        if not sub_path.exists():
            continue
        out.extend(p for p in sub_path.rglob("*.py") if p.is_file())
    return out


@pytest.mark.live_book
def test_no_orphan_table_refs() -> None:
    """Every table referenced in .execute()/.executemany() SQL must exist.

    Forcing function for Lesson 21: 'grep before invoke'. If this test fails,
    either (a) typo / invented identifier (fix the SQL), (b) legitimate new
    table (add to schema, regen doc), (c) false positive on a SQL construct
    (add to _WHITELIST with rationale).
    """
    clear_cache()
    actual_tables = {t.lower() for t in list_tables()}
    orphans: dict[str, list[str]] = {}

    for path in _all_source_files():
        for sql, line_no in _extract_execute_sql(path):
            for m in _SQL_TABLE_REF_RE.finditer(sql):
                table = m.group(1).lower()
                if table in _WHITELIST:
                    continue
                if table not in actual_tables:
                    loc = f"{path.relative_to(REPO)}:{line_no}"
                    orphans.setdefault(table, []).append(loc)

    if orphans:
        msg_lines = ["Orphan table refs (Lesson 21 violation):\n"]
        for table, locs in sorted(orphans.items()):
            msg_lines.append(f"  '{table}' at: {sorted(set(locs))}")
        msg_lines.append("\nFix options:")
        msg_lines.append("  1. Typo? Correct the SQL.")
        msg_lines.append("  2. New table? Add to schema + run scripts/regen_schema_doc.py")
        msg_lines.append("  3. SQL construct false positive? Add to _WHITELIST with rationale.")
        pytest.fail("\n".join(msg_lines))


def test_schema_helpers_smoke() -> None:
    """Quick sanity: list_tables() returns non-empty + key tables present."""
    tables = list_tables()
    assert len(tables) > 10, f"Expected >10 tables, got {len(tables)}"
    assert "positions" in tables
    assert "theses" in tables
    assert "signals" in tables


def test_helper_catches_known_drift() -> None:
    """Regression: position_events.created_at was a Lesson 21 violation in
    Bash 105 (column doesn't exist, was assumed). Verify the helper catches it."""
    from shared.schema import SchemaError, assert_column_exists

    with pytest.raises(SchemaError, match="not in table 'position_events'"):
        assert_column_exists("position_events", "created_at")
