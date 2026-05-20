"""Regenerate docs/REFERENCE_SCHEMA.md from actual DB schema.

Usage:
    python -m scripts.regen_schema_doc
    OR
    python scripts/regen_schema_doc.py

Reads sqlite_master + row counts at generation time, categorizes tables
by domain, writes formatted markdown to docs/REFERENCE_SCHEMA.md.

The doc is auto-regeneratable — re-run after any schema migration.
"""

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "bot.db"
OUT = Path(__file__).resolve().parent.parent / "docs" / "REFERENCE_SCHEMA.md"

DOMAINS = {
    "Core entities": [
        "sources", "signals", "theses", "decisions", "predictions",
        "positions", "position_events",
    ],
    "Intelligence loops": [
        "calibration", "patterns", "narratives", "regime",
        "debt_composite", "debt_signals", "debate_transcripts",
        "shadow_decisions", "risk_checks", "conviction_history",
        "insider_buy_clusters_log", "insider_snapshots", "filings_8k_log",
        "signal_embeddings", "analyses", "events",
    ],
    "User interface": [
        "user_decisions", "feedback", "watchlist", "portfolio_targets",
        "overrides", "ticker_names",
    ],
    "Operations": [
        "llm_calls", "handler_calls", "bot_events", "alembic_version",
    ],
}


def main() -> int:
    if not DB.exists():
        print(f"[FAIL] DB not found: {DB}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    tables = conn.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()

    indexes_by_table: dict[str, list[str]] = {}
    for row in conn.execute(
        "SELECT name, tbl_name FROM sqlite_master "
        "WHERE type='index' AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL "
        "ORDER BY tbl_name, name"
    ).fetchall():
        indexes_by_table.setdefault(row["tbl_name"], []).append(row["name"])

    row_counts = {}
    total_rows = 0
    for t in tables:
        n = conn.execute(f"SELECT count(*) FROM {t['name']}").fetchone()[0]
        row_counts[t["name"]] = n
        total_rows += n

    # Catch uncategorized
    categorized = set()
    for ts in DOMAINS.values():
        categorized.update(ts)
    uncategorized = sorted({t["name"] for t in tables} - categorized)
    domains = dict(DOMAINS)
    if uncategorized:
        domains["Uncategorized"] = uncategorized
        print(f"[WARN] {len(uncategorized)} uncategorized tables: {uncategorized}", file=sys.stderr)

    now = datetime.now(UTC).strftime("%d %b %Y")
    total_indexes = sum(len(v) for v in indexes_by_table.values())

    out = [
        "# Database Schema Reference\n",
        f"**Generated**: {now} (auto-regen via `scripts/regen_schema_doc.py`)",
        "**SQLite mode**: WAL (concurrent reads OK)",
        "**DB path**: `data/bot.db`\n",
        "Live snapshot of all tables with current row counts and indexes. Auto-regeneratable.\n",
        f"**Total tables**: {len(tables)} | **Total indexes**: {total_indexes} | **Total rows**: {total_rows:,}\n",
    ]

    for domain, table_names in domains.items():
        domain_tables = [t for t in tables if t["name"] in table_names]
        if not domain_tables:
            continue
        out.append(f"\n## {domain}\n")
        for t in domain_tables:
            name = t["name"]
            n = row_counts[name]
            out.append(f"### `{name}` ({n:,} rows)\n")
            out.append("```sql")
            out.append(t["sql"] + ";")
            out.append("```\n")
            idxs = indexes_by_table.get(name, [])
            if idxs:
                out.append("**Indexes**: " + ", ".join(f"`{i}`" for i in idxs) + "\n")

    out.append("\n---\n")
    out.append("## Regeneration\n")
    out.append("```bash")
    out.append("python scripts/regen_schema_doc.py")
    out.append("```\n")

    OUT.write_text("\n".join(out))
    print(f"[OK] {OUT.relative_to(Path.cwd())} regenerated")
    print(f"  Tables: {len(tables)}")
    print(f"  Indexes: {total_indexes}")
    print(f"  Rows: {total_rows:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
