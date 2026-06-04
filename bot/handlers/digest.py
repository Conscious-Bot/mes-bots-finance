"""Day 10 E batch 2+3 extracted from bot/main.py.

Handlers: cmd_digest
"""


async def cmd_digest(update, ctx):  # noqa: ARG001
    """Digest v2: header metadata + narrative Sonnet + footer drill-down.

    Fallback degrade (03/06/2026, credit Anthropic out) : si 0 signaux scored
    (impact_magnitude >= 2.0) mais des signaux raw ingeres existent, dump raw
    par recence + source au lieu d'un "Aucun signal" trompeur. Honest state.
    """
    import sqlite3
    from datetime import datetime as _dt

    from shared import storage as _storage

    parts = update.message.text.split()
    hours = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 24
    await update.message.reply_text(f"Synthese unifiee en cours ({hours}h) ~30s...")

    # Pre-compute metadata for header (before LLM call)
    conn = sqlite3.connect(_storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    n_raw = 0
    raw_rows: list = []
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
        # Fallback : raw ingestion count + sample si scored vide
        if n_signals == 0:
            raw_meta = conn.execute(
                "SELECT COUNT(*) c, COUNT(DISTINCT src.name) s FROM signals s "
                "LEFT JOIN sources src ON s.source_id = src.id "
                "WHERE s.timestamp >= datetime('now', ?)",
                (f"-{hours} hours",),
            ).fetchone()
            n_raw = raw_meta["c"] if raw_meta else 0
            if n_raw > 0:
                raw_rows = conn.execute(
                    "SELECT s.timestamp, s.title, src.name AS source, "
                    "  COALESCE(s.materiality_boost, 1.0) AS mb, s.scoring_status "
                    "FROM signals s LEFT JOIN sources src ON s.source_id = src.id "
                    "WHERE s.timestamp >= datetime('now', ?) "
                    "ORDER BY mb DESC, s.timestamp DESC LIMIT 12",
                    (f"-{hours} hours",),
                ).fetchall()
        last_call_id = conn.execute("SELECT MAX(id) AS max_id FROM llm_calls").fetchone()
        last_id_before = last_call_id["max_id"] if last_call_id and last_call_id["max_id"] else 0
    except Exception:
        n_signals, n_sources, last_id_before = 0, 0, 0
    finally:
        conn.close()

    # Mode degrade : on saute le LLM si rien a digerer mais qu'on a du raw.
    if n_signals == 0 and n_raw > 0:
        now_str = _dt.now().strftime("%d/%m %H:%M")
        # Source clean : strip <email> tail pour lisibilite
        def _clean_src(s: str) -> str:
            if not s:
                return "(unknown)"
            i = s.find(" <")
            return (s[:i] if i > 0 else s).strip().strip('"')
        lines = [
            f"DIGEST {now_str} ({hours}h window) -- MODE DEGRADE",
            f"Raw ingested: {n_raw} | Scored (LLM): 0 | LLM status: pending/unavailable",
            "-" * 40,
            "Pipeline ingestion OK, scoring LLM en attente (credit out / down).",
            "Top signaux par materiality heuristique + recence :",
            "",
        ]
        for r in raw_rows:
            ts = (r["timestamp"] or "")[5:16].replace("T", " ")  # MM-DD HH:MM
            title = (r["title"] or "(no title)").strip()
            if len(title) > 95:
                title = title[:92] + "..."
            src = _clean_src(r["source"])
            if len(src) > 30:
                src = src[:27] + "..."
            mb = r["mb"] or 1.0
            mb_str = f" m{mb:.1f}" if mb != 1.0 else ""
            lines.append(f"  [{ts}{mb_str}] {src}")
            lines.append(f"    {title}")
        lines.append("")
        lines.append("-" * 40)
        lines.append("Drill-down:")
        lines.append("  /signal TICKER     -> signals 30d for ticker")
        lines.append("  /find TICKER       -> cross-domain snapshot")
        await update.message.reply_text("\n".join(lines))
        return

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
