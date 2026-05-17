"""Day 10 E batch 2+3 extracted from bot/main.py.

Handlers: cmd_digest
"""


async def cmd_digest(update, ctx):  # noqa: ARG001
    """Digest v2: header metadata + narrative Sonnet + footer drill-down."""
    import sqlite3
    from datetime import datetime as _dt

    from shared import storage as _storage

    parts = update.message.text.split()
    hours = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 24
    await update.message.reply_text(f"Synthese unifiee en cours ({hours}h) ~30s...")

    # Pre-compute metadata for header (before LLM call)
    conn = sqlite3.connect(_storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        meta_row = conn.execute(
            "SELECT COUNT(DISTINCT src.name) AS sources, COUNT(*) AS n_signals "
            "FROM signals s LEFT JOIN sources src ON s.source_id = src.id "
            "WHERE s.timestamp >= datetime('now', ?) "
            "  AND COALESCE(s.impact_magnitude, 0) >= 2.0",
            (f"-{hours} hours",),
        ).fetchone()
        n_signals = meta_row["n_signals"] if meta_row else 0
        n_sources = meta_row["sources"] if meta_row else 0
        last_call_id = conn.execute("SELECT MAX(id) AS max_id FROM llm_calls").fetchone()
        last_id_before = last_call_id["max_id"] if last_call_id and last_call_id["max_id"] else 0
    except Exception:
        n_signals, n_sources, last_id_before = 0, 0, 0
    finally:
        conn.close()

    try:
        from intelligence import digest as _digest_mod

        narrative = _digest_mod.generate_unified_digest(since_hours=hours, max_signals=40)
    except Exception as e:
        await update.message.reply_text(f"Digest failed: {type(e).__name__}: {e}")
        return

    # Post-call: lookup cost from llm_calls
    cost_usd = 0.0
    try:
        conn = sqlite3.connect(_storage._DB_PATH)
        row = conn.execute(
            "SELECT SUM(cost_usd) AS cost FROM llm_calls WHERE id > ?",
            (last_id_before,),
        ).fetchone()
        if row and row[0]:
            cost_usd = float(row[0])
        conn.close()
    except Exception:
        pass

    # Header
    now_str = _dt.now().strftime("%d/%m %H:%M")
    header = (
        f"DIGEST {now_str} ({hours}h window)\n"
        f"Signals: {n_signals} | Sources: {n_sources} | Cost: ${cost_usd:.3f}\n"
        f"{'-' * 40}"
    )

    # Footer
    footer = (
        f"{'-' * 40}\n"
        f"Drill-down:\n"
        f"  /signal TICKER     -> signals 30d for ticker\n"
        f"  /find TICKER       -> cross-domain snapshot\n"
        f"  /thesis health     -> portfolio coverage check"
    )

    full_output = header + "\n\n" + narrative + "\n\n" + footer

    # Chunk if needed
    if len(full_output) > 3900:
        chunks = []
        cur = ""
        for para in full_output.split("\n\n"):
            if len(cur) + len(para) + 2 < 3900:
                cur = cur + "\n\n" + para if cur else para
            else:
                if cur:
                    chunks.append(cur)
                cur = para
        if cur:
            chunks.append(cur)
        for c in chunks:
            await update.message.reply_text(c)
    else:
        await update.message.reply_text(full_output)
