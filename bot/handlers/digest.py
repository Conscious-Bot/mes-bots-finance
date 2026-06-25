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
        if n_signals == 0:
            raw_meta = conn.execute(
                "SELECT COUNT(*) c FROM signals s "
                "WHERE s.timestamp >= datetime('now', ?)",
                (f"-{hours} hours",),
            ).fetchone()
            n_raw = raw_meta["c"] if raw_meta else 0
        last_call_id = conn.execute("SELECT MAX(id) AS max_id FROM llm_calls").fetchone()
        last_id_before = last_call_id["max_id"] if last_call_id and last_call_id["max_id"] else 0
    except Exception:
        n_signals, n_sources, last_id_before = 0, 0, 0
    finally:
        conn.close()

    # Mode vacances : pas de LLM call si rien a digerer mais qu'on a du raw.
    # Brief HONNETE non-score, source unique = shared.degraded_signals.
    # Principe (user 04/06) : "le bot arrete de pretendre juger" -- pas de
    # fake-scorer qui contamine le Brier, juste filings + matches book + flux.
    if n_signals == 0 and n_raw > 0:
        from shared.degraded_signals import build_degraded_brief

        now_str = _dt.now().strftime("%d/%m %H:%M")
        brief = build_degraded_brief(_storage._DB_PATH, hours=hours)
        lines = [
            f"DIGEST {now_str} ({hours}h window) -- MODE VACANCES",
            f"Raw ingere: {n_raw} | Scoring LLM: en pause | Synthese: en pause",
            "Track record predictions: autonome (resolutions automatiques).",
            "-" * 40,
            "",
            brief or "(pipeline OK, aucun signal au-dela du metadata)",
            "",
            "-" * 40,
            "Drill-down: /signal TICKER  |  /find TICKER",
        ]
        full = "\n".join(lines)
        if len(full) > 3900:
            full = full[:3850] + "\n...[truncated]"
        await update.message.reply_text(full)
        # Mirror Obsidian vault (mode vacances aussi, cf doctrine 25/06)
        try:
            from shared import obsidian as _obs
            date_iso = _dt.now().strftime("%Y-%m-%d")
            note_path = f"journal/digests/DIGEST_{date_iso}.md"
            fm = _obs.frontmatter(
                type_="digest", date_iso=date_iso,
                aliases=[f"digest_bot_{date_iso}_vacances"],
                tickers=[], theses_touchees=[], noms_propres=[],
                hubs=[], status="archive",
            )
            content = fm + (
                f"\n# Digest bot — {date_iso} (MODE VACANCES)\n\n"
                f"Mirror du digest Telegram dégradé (LLM down, brief honest non-scoré).\n\n"
                f"```\n{full}\n```\n\n"
                "## [À COMPLÉTER PAR O.]\n\nRien à distiller (mode vacances). : —\n"
            )
            _obs.write_note(note_path, content, overwrite=True)
        except Exception as obs_err:
            import logging
            logging.getLogger("bot.digest").warning(
                "Obsidian mirror failed (soft): %s: %s",
                type(obs_err).__name__, obs_err,
            )
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

    # Mirror Obsidian vault PRESAGE (workflow C, cf memory
    # project-obsidian-vault-primary-substrate doctrine 25/06/2026).
    # Le vault = raffinerie cumulative. Chaque digest TG -> note datee dans
    # journal/digests/. Si Obsidian inaccessible (vault offline / clé manquante),
    # soft-fail : log warning, ne casse pas le digest principal.
    try:
        from shared import obsidian as _obs
        date_iso = _dt.now().strftime("%Y-%m-%d")
        note_path = f"journal/digests/DIGEST_{date_iso}.md"
        candidates = [
            "Concentration — grappe AI-compute",
            "Grille de Conviction",
            "World Model — le modèle causal (apex)",
        ]
        existing, _ghosts = _obs.filter_existing_links(candidates)
        fm = _obs.frontmatter(
            type_="digest",
            date_iso=date_iso,
            aliases=[f"digest_bot_{date_iso}"],
            tickers=[],
            theses_touchees=[],
            noms_propres=[],
            hubs=existing,
            status="archive",
        )
        content = fm + (
            f"\n# Digest bot — {date_iso}\n\n"
            f"Mirror du digest Telegram (cmd_digest) écrit automatiquement\n"
            f"par bot/handlers/digest.py post-send TG.\n\n"
            f"## Output Telegram brut\n\n"
            f"```\n{full_output}\n```\n\n"
            f"## 🔗 Rattachements\n\n"
            + (", ".join(f"[[{h}]]" for h in existing) if existing else "  (aucun hub)\n")
            + "\n\n## [À COMPLÉTER PAR O.] — distillation\n\n"
            "Patterns à graver ? Signaux à promouvoir en thèse ? : —\n"
        )
        # Overwrite : si plusieurs digests par jour, le dernier ecrase (idempotent)
        _obs.write_note(note_path, content, overwrite=True)
    except Exception as obs_err:
        # Soft-fail : log seulement, ne casse pas cmd_digest
        import logging
        logging.getLogger("bot.digest").warning(
            "Obsidian mirror failed (soft): %s: %s",
            type(obs_err).__name__, obs_err,
        )
