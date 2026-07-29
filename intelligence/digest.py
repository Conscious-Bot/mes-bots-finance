"""Newsletter digest synthesizer.

Reads unprocessed raw email signals from DB, calls Claude to extract structured
insights (score, sentiment, tickers, narratives, summary), updates DB,
returns formatted digest for Telegram.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from shared import config, llm, storage
from shared.prompts import DIGEST_SYNTHESIZER
from shared.sql_observability import query

log = logging.getLogger(__name__)


def synthesize_signal(
    signal_dict: dict[str, Any],
    watchlist: list[str],
    regime_context: str | None = None,
    insider_context: str | None = None,
) -> dict[str, Any]:
    """Call LLM to extract structured insights. Optionally with regime preamble."""
    body = (signal_dict.get("content") or "")[:10000]
    watchlist_str = ", ".join(watchlist[:30]) + (f"... ({len(watchlist)} total)" if len(watchlist) > 30 else "")
    base_prompt = DIGEST_SYNTHESIZER.format(
        ticker_watchlist=watchlist_str,
        source=signal_dict.get("source_name", "unknown"),
        subject=(signal_dict.get("title") or "")[:300],
        body=body,
    )
    prompt = (regime_context or "") + (insider_context or "") + base_prompt
    try:
        result = llm.call_json(prompt, task="signal_scoring", max_tokens=1500)
        return result
    except Exception as e:
        return {
            "score": 0,
            "sentiment": "neutral",
            "tickers": [],
            "drivers": [],
            "summary": None,  # null → score_pending cron retries
            "actionable": False,
            "narratives": [],
            "confidence": 0,
            "error": str(e),
        }


def process_unprocessed(limit: int = 20) -> list[dict[str, Any]]:
    """Process up to `limit` unprocessed raw signals. Fetches regime once per batch."""
    cfg = config.load()
    watchlist = cfg.get("universe", {}).get("watchlist", [])
    signals = storage.get_unprocessed_signals(limit=limit)
    if not signals:
        return []
    regime_context = None
    try:
        from intelligence import regime as _regime_mod

        regime_context = _build_regime_context(_regime_mod.detect_regime())
    except Exception as _e:
        log.warning(f"Regime ctx fetch failed: {_e}")
    insider_context = None
    try:
        insider_context = _build_insider_context()
    except Exception as _e:
        log.warning(f"Insider ctx fetch failed: {_e}")
    processed = []
    for sig in signals:
        insights = synthesize_signal(sig, watchlist, regime_context=regime_context, insider_context=insider_context)
        try:
            storage.update_signal_insights(
                sig["id"],
                score=int(insights.get("score", 0)),
                sentiment=insights.get("sentiment", "neutral"),
                tickers=insights.get("tickers", []),
                narratives=insights.get("narratives", []),
                summary=insights.get("summary", ""),
            )
            processed.append({**sig, **insights})
        except Exception as e:
            log.warning(f"Failed to store insights for signal {sig['id']}: {e}")
    try:
        from intelligence import learning as _learning

        _pids = _learning.auto_register_predictions(processed)
        if _pids:
            log.info(f"Registered {len(_pids)} predictions from {len(processed)} signals")
    except Exception as _e:
        log.warning(f"Auto-register predictions failed: {_e}")
    return processed


def build_digest_telegram(processed_signals: list[dict[str, Any]], top_n: int = 5) -> str:
    """Format top-N scored signals for Telegram (plain text)."""
    if not processed_signals:
        return "Aucun signal a digerer."
    sorted_sigs = sorted(processed_signals, key=lambda s: s.get("score") or 0, reverse=True)
    parts = [f"Digest - {len(processed_signals)} signaux traites", ""]
    for i, s in enumerate(sorted_sigs[:top_n], 1):
        source = (s.get("source_name") or "unknown")[:40]
        score = s.get("score", "?")
        sentiment = s.get("sentiment", "?")
        summary = s.get("summary", "")
        tickers = s.get("tickers") or []
        fb = s.get("user_feedback") or ""
        fb_marker = " [+]" if fb == "up" else (" [-]" if fb == "down" else "")
        parts.append(f"{i}. #{s.get('id', '?')} [{source}] score {score}/10 ({sentiment}){fb_marker}")
        if tickers:
            parts.append(f"   tickers: {', '.join(tickers)}")
        parts.append(f"   {summary}")
        parts.append("")
    return "\n".join(parts)


def run_digest(limit: int = 20, top_n: int = 5, fallback_hours: int = 72, include_regime: bool = True) -> str:
    """Full digest pipeline. Falls back to recent if nothing new.
    Prepends regime banner if include_regime=True.
    """
    processed = process_unprocessed(limit=limit)
    if not processed:
        recent = storage.get_recent_processed_signals(hours=fallback_hours, limit=20)
        if not recent:
            digest_msg = "Aucun signal a digerer (ni nouveau ni en stock)."
        else:
            digest_msg = f"Aucun NOUVEAU signal. Stock recents ({fallback_hours}h):\n\n" + build_digest_telegram(
                recent, top_n=top_n
            )
    else:
        digest_msg = build_digest_telegram(processed, top_n=top_n)

    if include_regime:
        try:
            from intelligence import regime as _regime

            r = _regime.detect_regime()
            banner = _regime.format_regime(r)
            return cast(str, banner) + "\n\n---\n\n" + digest_msg
        except Exception as _e:
            log.warning(f"Regime banner failed: {_e}")
    return digest_msg


if __name__ == "__main__":
    print("=== Test digest pipeline ===")
    print("Fetching unprocessed signals...")
    unproc = storage.get_unprocessed_signals(limit=3)
    print(f"Found {len(unproc)} unprocessed signals (limit 3)")
    if unproc:
        print("\nRunning digest on first 3 signals (may take 30-60s)...")
        msg = run_digest(limit=3, top_n=3)
        print(msg)
    else:
        print("\nNo unprocessed signals. Run 'python -m data_sources.gmail_' first.")


def _build_regime_context(r: dict[str, Any]) -> str:
    """Build regime context preamble for LLM signal scoring."""
    if not r:
        return ""
    lines = [
        "=== MACRO REGIME (consider in scoring) ===",
        f"Overall: {r.get('overall', 'unknown')}",
        f"Equity: {r.get('equity', '?')} | Crypto: {r.get('crypto', '?')} | Macro: {r.get('macro', '?')}",
        "",
        "Regime-aware adjustments to your score:",
        "- LATE-CYCLE-WARNING: bullish cyclicals/AI/semis -1 to -2 points",
        "- CRYPTO-TOP-ZONE: crypto bullish -2 (FOMO bias risk)",
        "- RISK-OFF: defensives +1, cyclicals -1",
        "- CRYPTO-BOTTOM-ZONE: crypto bullish +1 (asymmetric entry)",
        "- COMPLACENCY: slight bullish discount, hedge appetite up",
        "- NEUTRAL: minimal adjustment, score per signal merit",
        "",
        "Score must reflect BOTH signal quality AND regime fit.",
        "===",
        "",
    ]
    return "\n".join(lines)


# Phase Tickers Tiered — dynamic from config.yaml universe.core
import contextlib

from shared import config as _cfg

INSIDER_TOP_TICKERS = _cfg.get_tickers("core")


def _build_insider_context() -> str:
    """Fetch top-watchlist insider briefs (cached 24h) and format for LLM prompt."""
    try:
        from shared import edgar as _edgar_mod

        briefs = _edgar_mod.get_insider_briefs(INSIDER_TOP_TICKERS)
        return cast(str, _edgar_mod.format_insider_context_for_prompt(briefs))
    except Exception as e:
        print(f"Insider context failed: {e}")
        return ""


def run_enhanced_digest(
    limit: int = 20,
    top_n: int = 5,
    fallback_hours: int = 72,
    include_regime: bool = True,
    annotate_top: int = 3,
    persist: bool = True,
) -> str:
    import logging

    log = logging.getLogger(__name__)
    existing_msg = run_digest(limit=limit, top_n=top_n, fallback_hours=fallback_hours, include_regime=include_regime)
    if not existing_msg:
        return existing_msg
    try:
        from intelligence import materiality, why_matters
        from shared import macro, storage as storage_mod

        with storage_mod.db() as cx:
            rows = query(
                cx,
                "SELECT * FROM signals WHERE timestamp > datetime('now', ?) ORDER BY timestamp DESC LIMIT 100",
                ("-" + str(fallback_hours) + " hours",),
                tag="digest.fallback_recent_signals",
                fetch="all",
            )
        signals = [dict(r) for r in rows]
        if not signals:
            return existing_msg

        regime_info = {}
        try:
            from intelligence import regime as regime_mod

            r = regime_mod.detect_regime()
            regime_info["overall"] = r.get("overall", "NEUTRAL")
        except Exception:
            regime_info["overall"] = "NEUTRAL"
        with contextlib.suppress(Exception):
            regime_info["credit"] = macro.get_credit_regime()

        scored = []
        for sig in signals:
            try:
                score = materiality.score_materiality(sig, signals, signals, regime_info)
                scored.append((sig, score))
            except Exception as e:
                log.warning("score failed " + str(sig.get("id")) + ": " + str(e))

        non_noise = [(sig, sc) for sig, sc in scored if not sc.get("noise")]
        non_noise.sort(key=lambda x: -x[1]["composite"])
        top = non_noise[:annotate_top]

        why_map = {}
        for sig, score in top:
            try:
                w = why_matters.generate_why_matters(sig, score, regime_info)
                if w:
                    why_map[sig["id"]] = w
            except Exception as e:
                log.warning("why failed " + str(sig.get("id")) + ": " + str(e))

        if persist:
            credit_class = None
            if isinstance(regime_info.get("credit"), dict):
                credit_class = regime_info["credit"].get("overall")
            for sig, score in scored:
                try:
                    storage_mod.persist_materiality(
                        signal_id=sig["id"],
                        score_dict=score,
                        regime=regime_info.get("overall"),
                        credit_regime=credit_class,
                        why_this_matters=why_map.get(sig["id"]),
                    )
                except Exception as e:
                    log.warning("persist failed: " + str(e))

        if not top:
            return existing_msg

        sections = ["TOP MATERIAL SIGNALS (last " + str(fallback_hours) + "h)\n"]
        for i, (sig, score) in enumerate(top, 1):
            derived = score.get("_derived", {}) or {}
            tickers = derived.get("tickers", []) or []
            primary = tickers[0] if tickers else "-"
            sig_type = derived.get("signal_type", "?")
            title = (sig.get("title") or sig.get("summary") or "")[:80]
            why = why_map.get(sig["id"], "")
            sections.append(
                "#"
                + str(i)
                + " ["
                + primary
                + "] ["
                + sig_type
                + "] materiality="
                + ("{:.3f}".format(score["composite"]))
            )
            sections.append("   " + title)
            if why:
                sections.append("   --> " + why)
            sections.append("")

        return "\n".join(sections) + "\n---\n\n" + existing_msg

    except Exception as e:
        log.warning("enhance digest failed: " + str(e))
        return existing_msg


# ============ Phase Digestion Output — Unified Narrative Synthesis ============


def _get_canonical_perimeter() -> set[str]:
    """Perimetre canonique = positions tenues. Source de verite unique.

    Le digest, les clusters, les gates et le copilot lisent ICI.
    Hors-canonique = NVDA, MRVL, MSTR, IBIT, COIN, CEG (non tenu), etc.
    Si le user ajoute une position, elle entre automatiquement dans le
    perimetre. S'il sort, elle en sort.
    """
    from shared import storage

    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT DISTINCT ticker FROM positions WHERE qty > 0 AND status='open'"
            ).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def book_state_header() -> str | None:
    """Bloc mécanique ÉTAT BOOK (zéro LLM) : digue + stops franchis.

    Cure 29/07/2026 (Olivier : « le digest coupe trop d'infos ») : la partie
    du digest qui n'a PAS le droit d'être résumée/coupée est déterministe par
    construction — elle ne passe pas par le narratif LLM. Fail-soft : None si
    données indisponibles, le digest narratif reste utilisable sans.
    """
    import sqlite3

    from shared import storage
    from shared.portfolio_analytics import is_stop_breached

    lines: list[str] = []
    try:
        con = sqlite3.connect(storage._DB_PATH)
        con.row_factory = sqlite3.Row
        d = con.execute(
            "SELECT status, drawdown_pct, hwm_value_eur, current_value_eur "
            "FROM digue_alerts ORDER BY id DESC LIMIT 1"
        ).fetchone()
        con.close()
        if d and d["drawdown_pct"] is not None:
            lines.append(
                f"Digue: {d['status']} | DD réalisé: {d['drawdown_pct']:+.1f}% "
                f"(HWM {d['hwm_value_eur']:,.0f}€ -> {d['current_value_eur']:,.0f}€)"
            )
    except Exception as e:
        log.warning(f"book_state_header digue read failed (soft): {e}")
    try:
        from intelligence import asymmetry as _asym

        computed = [r for r in _asym.compute_portfolio_asymmetry() if "asymmetry_ratio" in r]
        breached = sorted(
            ((r["ticker"], r.get("downside_pct")) for r in computed
             if is_stop_breached(r.get("downside_pct"))),
            key=lambda x: (x[1] if x[1] is not None else 0.0),
        )
        if breached:
            worst = ", ".join(f"{tk} {dn:.1f}%" for tk, dn in breached[:3] if dn is not None)
            lines.append(f"Stops franchis: {len(breached)} | pires: {worst}")
    except Exception as e:
        log.warning(f"book_state_header breached compute failed (soft): {e}")
    return "\n".join(lines) if lines else None


_CATALYST_STATIC_SEED = [
    # Catalysts que le calendrier yfinance rate (internationales + macro annuelle).
    # A maintenir a la main jusqu'au P1 (universe.yaml + refresh elargi).
    ("2026-07-30", "Samsung earnings (matin KST)"),
    ("2026-08-05", "Infineon earnings (cible d'achat)"),
    ("2026-08-06", "Ajinomoto earnings (cible d'achat)"),
    ("2026-08-07", "Harmonic Drive earnings (cible d'achat)"),
    # L17 : pas de donnee de marche perissable (proba pricee etc.) dans un seed
    # statique — les probas vivent dans le flux, pas dans le declaratif.
    ("2026-09-15", "FOMC + dot plot"),
]


def _dedup_ticker_events(raw: list[dict]) -> list[dict]:
    """Dedup des events par (ticker, event_type) : garde l'estimation la plus
    RECENTE (max created_at ; tie-break = date la plus proche).

    Cause (digest 29/07) : daily_calendar_refresh insere une nouvelle row quand
    l'API deplace une date d'earnings, et UNIQUE(etype,ticker,date) ON CONFLICT
    IGNORE laisse vivre l'ancienne estimation -> doublons (META 29+30/07,
    AMD 04+05/08...). La derniere estimation API = la meilleure connaissance.
    Les macro (ticker NULL/'MACRO') ne sont PAS dedupliques : dates distinctes
    = events distincts (FOMC, NFP, CPI).
    """
    out: list[dict] = []
    keep: dict[tuple, dict] = {}
    for r in raw:
        tk = r.get("ticker")
        if tk in (None, "", "MACRO"):
            out.append(r)
            continue
        key = (tk, r.get("event_type"))
        cur = keep.get(key)
        if cur is None:
            keep[key] = r
            continue
        r_created = str(r.get("created_at") or "")
        c_created = str(cur.get("created_at") or "")
        if r_created > c_created or (r_created == c_created and str(r.get("date")) < str(cur.get("date"))):
            keep[key] = r
    out.extend(keep.values())
    out.sort(key=lambda x: str(x.get("date")))
    return out


# T13 (SPEC digest_enrichment_v2) : le digest INFORME, il ne recommande jamais
# une transaction. Verbes de trade a l'imperatif/infinitif d'ordre = violation.
_T13_RE = None


def _t13_guard(narrative: str) -> str:
    """Garde post-rendu T13 : detecte les formulations imperatives de trade
    dans la synthese LLM et APPEND un avertissement (ne censure jamais en
    silence — etat honnete L3 : le lecteur voit le texte ET le drapeau).

    La vraie defense est dans le prompt (section POINTS DE DECISION) ; cette
    garde est le filet mecanique (L27 : coherence mecanique > vigilance).
    """
    import re

    global _T13_RE
    if _T13_RE is None:
        _T13_RE = re.compile(
            r"(?i)\b("
            r"vend(?:re|s|ez)|ach(?:e|è)te(?:r|z)?|all(?:è|é|e)ge(?:r|z)?|"
            r"renforce(?:r|z)?|r(?:é|e)dui(?:re|s|sez)|sor(?:s|tir|tez)|"
            r"coupe(?:r|z)?|poser? un stop|prend(?:re|s|ez) (?:des |tes )?profits"
            r")\b"
        )
    if _T13_RE.search(narrative):
        return (
            narrative
            + "\n\n⚠ GARDE T13 : formulation imperative de trade detectee "
            "ci-dessus. Les ordres d'un LLM ne sont PAS autoritatifs (L9) — "
            "seuls les FAITS comptent ; la decision passe par le framework "
            "(Q1 these intacte ? / Q2 poids vs cible)."
        )
    return narrative


def _deterministic_catalysts(days_ahead: int = 14) -> str:
    """Section CATALYSTS deterministe (table `events` + seed statique), ZERO NLP.

    Incident Heimdall 29/07 : la section catalysts etait extraite par le LLM
    depuis les newsletters (qui ne publient pas de calendriers earnings) ->
    rendait 'Aucun catalyst' pendant la semaine la plus dense du trimestre =
    fail-silent. Fix : jointure deterministe de `events` (peuplee par
    daily_calendar_refresh_job) + seed pour les internationales que yfinance rate.
    Never-fail-silent : un vide PROUVE qu'il a cherche (bornes + source affichees).
    """
    import sqlite3

    from shared import storage

    today = datetime.now(UTC).date()
    end = today + timedelta(days=days_ahead)
    rows: list[tuple[str, str]] = []
    try:
        conn = sqlite3.connect(storage._DB_PATH)
        conn.row_factory = sqlite3.Row
        raw = [
            dict(r)
            for r in conn.execute(
                "SELECT date, event_type, ticker, description, created_at FROM events "
                "WHERE date >= ? AND date <= ? ORDER BY date",
                (today.isoformat(), end.isoformat()),
            )
        ]
        conn.close()
        for r in _dedup_ticker_events(raw):
            lbl = r["description"] or str(r["event_type"])
            tk = r["ticker"]
            rows.append((str(r["date"]), lbl if tk in (None, "MACRO") else f"{tk} — {lbl}"))
    except Exception as e:
        return (
            "CATALYSTS DATES\n"
            f"\U0001F6A8 INCIDENT : module catalysts en echec ({type(e).__name__}) "
            "— sortie NON FIABLE (never-fail-silent).\n"
        )
    seen = set(rows)
    for d, lbl in _CATALYST_STATIC_SEED:
        if today.isoformat() <= d <= end.isoformat() and (d, lbl) not in seen:
            rows.append((d, lbl))
    rows.sort()
    if not rows:
        return (
            "CATALYSTS DATES\n"
            f"Aucun catalyst (fenetre VERIFIEE {today} -> {end}, source: events + seed). "
            "Si suspect en fenetre active -> INCIDENT module.\n"
        )
    body = "\n".join(f"- {d} : {lbl}" for d, lbl in rows)
    return f"CATALYSTS DATES (deterministe — events + seed, fenetre {today}->{end})\n{body}\n"


def generate_unified_digest(since_hours: int = 24, max_signals: int = 40, exclude_low_score: bool = True) -> str:
    """Single narrative synthesizing all recent signals into themes + catalysts + noise + actions.

    Sprint 19 : perimetre filtre au canonique (positions tenues). Les signaux
    sur des tickers hors-canonique sont skippes. Le prompt liste explicitement
    le perimetre actif au lieu d'un univers hardcode obsolete.
    """
    import json
    import sqlite3

    from shared import llm, storage

    conn = sqlite3.connect(storage._DB_PATH)
    conn.row_factory = sqlite3.Row
    cutoff = (datetime.now(UTC) - timedelta(hours=int(since_hours))).strftime("%Y-%m-%d %H:%M:%S")
    # Use impact_magnitude (materiality_v2) instead of deprecated score field
    # Threshold 2.0 = materially impactful events on scale 1-5
    where_score = "AND COALESCE(s.impact_magnitude, 0) >= 2.0" if exclude_low_score else ""
    rows = query(
        conn,
        "SELECT s.id, s.title, s.summary, s.signal_type, s.score, "
        "s.impact_magnitude, s.reversibility, s.time_to_realization, "
        "s.materiality_boost, s.entities, src.name AS source "
        "FROM signals s LEFT JOIN sources src ON s.source_id = src.id "
        "WHERE s.timestamp >= ? " + where_score + " "
        "ORDER BY (COALESCE(s.score, 0) * COALESCE(s.materiality_boost, 1.0)) DESC LIMIT ?",
        (cutoff, int(max_signals)),
        tag="digest.fetch_signals_for_synthesis",
        fetch="all",
    )
    conn.close()
    if not rows:
        return "Aucun signal pertinent sur les dernieres " + str(since_hours) + "h."

    # Sprint 19 : filter signals au perimetre canonique
    canonical = _get_canonical_perimeter()
    filtered_rows = []
    skipped = 0
    for r in rows:
        try:
            ents = json.loads(r["entities"]) if r["entities"] else []
            if not isinstance(ents, list):
                ents = []
        except Exception:
            ents = []
        # Keep si au moins un ticker canonique mentionne OU si pas d'entites tagged
        # (signal macro sans ticker -> pertinent quand meme)
        if ents and not (set(ents) & canonical):
            skipped += 1
            continue
        filtered_rows.append(r)
    rows = filtered_rows

    if not rows:
        return f"Aucun signal canonique sur les dernieres {since_hours}h ({skipped} skippes hors-perimetre)."

    # Brief 10 points #8 : RERANKING book-anchored.
    # Le signal n'est pertinent que s'il rapproche une these de son
    # kill-criterion ou de sa validation. On retrie par score book-anchored
    # (kill-criterion match + validation match + margin urgency).
    try:
        from intelligence import book_anchored_scoring as _bas

        # Convertir rows (sqlite3.Row) en dicts pour passage au scorer
        rows_dicts = [dict(r) for r in rows]
        ranked = _bas.rank_signals_book_anchored(rows_dicts)
        # On garde la signature (signals iteres comme rows) en remplacant
        # rows par le tri book-anchored. Les scores book sont attaches en
        # annotations pour eventuelles vues downstream.
        rows = [item["signal"] for item in ranked]
        # Annote le top 5 pour le prompt LLM (lui dire pourquoi c'est pertinent)
        rerank_top5 = []
        for item in ranked[:5]:
            bs = item["book_score"]
            if bs["score"] > 0:
                rerank_top5.append({
                    "title": item["signal"].get("title", "")[:80],
                    "book_score": bs["score"],
                    "reasoning": bs["reasoning"],
                })
        rerank_meta = (
            "\nRERANK BOOK-ANCHORED (top 5 par score book) :\n"
            + "\n".join(
                f"  [{m['book_score']:>2}] {m['title']} -- {m['reasoning']}"
                for m in rerank_top5
            )
        ) if rerank_top5 else ""
    except Exception as _e:
        log.warning(f"book_anchored reranking failed: {_e}")
        rerank_meta = ""

    sources_set = set()
    catalysts = narratives = opinions = data = 0
    blocks = []
    for r in rows:
        sources_set.add(r["source"] or "?")
        st = r["signal_type"] or "?"
        if st == "catalyst":
            catalysts += 1
        elif st == "narrative":
            narratives += 1
        elif st == "opinion":
            opinions += 1
        elif st == "data":
            data += 1
        ents = ""
        try:
            if r["entities"]:
                e = json.loads(r["entities"])
                if isinstance(e, list) and e:
                    ents = " | tickers: " + ", ".join(e[:5])
        except Exception as e:
            log.debug(f"Signal entities parse failed (non-blocking): {e}")
        score = r["score"] or 0
        boost = r["materiality_boost"] or 1.0
        adj = score * boost
        imp = r["impact_magnitude"]
        line = "[#" + str(r["id"]) + " " + st + " | adj=" + str(round(adj, 1)) + "/10"
        if imp is not None:
            line += " impact=" + str(int(imp)) + "/5 time=" + str(r["time_to_realization"] or "?")
        line += "] " + (r["source"] or "?") + ": " + (r["title"] or "?")[:160] + ents
        summary = (r["summary"] or "")[:400]
        if summary:
            line += "\n   " + summary
        blocks.append(line)
    signals_text = "\n\n".join(blocks)
    stats_line = (
        "Stats: "
        + str(catalysts)
        + " catalysts, "
        + str(data)
        + " data, "
        + str(narratives)
        + " narratives, "
        + str(opinions)
        + " opinions, "
        + str(len(sources_set))
        + " sources distinctes."
    )
    today_str = datetime.now(UTC).strftime("%d/%m/%Y %H:%M")
    canonical_str = ", ".join(sorted(canonical)) if canonical else "(aucune position)"
    prompt = (
        "Tu es l'analyste finance d'un investisseur particulier serieux. "
        "Profil thesis-driven slow alpha sur tech/semis/AI + decorrelants "
        "(defense EU, uranium, GNL, terres rares). Biais identifies : "
        "vend winners trop tot, ne sort pas les doublons assez vite.\n\n"
        "PERIMETRE CANONIQUE (= positions tenues, SOURCE DE VERITE UNIQUE) :\n"
        f"  {canonical_str}\n\n"
        f"{rerank_meta}\n\n"
        f"INTERDIT : parler de NVDA, MRVL, MSTR, IBIT, COIN, CEG, VST ou tout "
        f"ticker hors perimetre canonique ci-dessus, meme si un signal "
        f"l'evoque. Ces tickers ne sont PAS dans son book.\n\n"
        "Date du jour: " + today_str + ". Window analyse: derniers " + str(since_hours) + "h.\n\n"
        "Voici " + str(len(rows)) + " signaux digeres. " + stats_line + "\n\n"
        "=== SIGNAUX BRUTS ===\n" + signals_text + "\n\n"
        "=== PRODUIS UNE SYNTHESE NARRATIVE UNIFIEE ===\n\n"
        "REGLE CRITIQUE: ne JAMAIS inventer ou hardcoder une date dans ton output. La date du jour est ci-dessus. "
        "Si tu references une date, elle doit etre soit la date du jour ("
        + today_str[:10]
        + ") soit une date explicite d'un signal cite.\n\n"
        "REGLE CATALYSTS: NE GENERE PAS de section CATALYSTS — elle est fournie de facon "
        "DETERMINISTE en amont (table events + seed). N'invente aucune date d'event.\n\n"
        "Structure obligatoire:\n\n"
        "VERDICT: X urgent / Y monitoring / Z noise -- et NOMME les urgents : 'urgent: TICKER (motif 3-5 mots)'\n"
        "(1 ligne tout en haut. X+Y+Z doit correspondre a ton analyse globale, pas au count brut.)\n\n"
        "PAR POSITION TOUCHEE (ordre = pertinence book decroissante)\n"
        "Une entree par ticker canonique avec >=1 signal. Format par entree :\n"
        "TICKER -- 2-4 lignes : le fait nouveau PRECIS (chiffres exacts des signaux, pas de paraphrase vague), "
        "reference [#id] de chaque signal utilise, et si le rerank book-anchored le signale : quel "
        "trigger/kill-criterion ca rapproche. Ne fusionne JAMAIS deux tickers dans une meme entree.\n\n"
        "THEMES TRANSVERSAUX (0-3, seulement si un meme fait touche >=3 positions)\n"
        "Nom court + tickers + pourquoi ca matte. Pas de remplissage si rien de transversal.\n\n"
        "(Section CATALYSTS DATES fournie deterministiquement en amont — ne la genere PAS.)\n\n"
        "BRUIT JETE\n"
        "UNE SEULE LIGNE format: 'Skipped: N sources, mostly [theme1, theme2]'. Pas de details, pas de liste.\n\n"
        "POINTS DE DECISION (max 5 bullets)\n"
        "Format STRICT par bullet : 'TICKER : [fait + chiffre, ref #id] touche "
        "[trigger/kill-criterion/question ouverte NOMME] -> a passer dans le framework "
        "(Q1 these intacte ? / Q2 poids vs cible)'.\n"
        "INTERDIT ABSOLU (doctrine L9 - le digest INFORME, il ne recommande JAMAIS une "
        "transaction) : tout imperatif de trade (vendre, acheter, alleger, reduire, "
        "renforcer, sortir, couper, prendre des profits, poser un stop), tout pourcentage "
        "de sizing, toute urgence d'execution ('aujourd'hui', 'maintenant', 'cette "
        "semaine' comme injonction). Les biais documentes servent a CONTEXTUALISER un "
        "fait, jamais a presser une action. La decision appartient au framework du "
        "gerant, pas a toi.\n\n"
        "Ton: direct, jargon pro francais, pragmatique, max 900 mots. Precision > brievete : "
        "cite les chiffres des signaux. Pas de fawning, dire les choses sans edulcorer."
    )
    try:
        narrative = llm.call(prompt, tier="enrich", max_tokens=3000)
        if not narrative:
            return _deterministic_catalysts() + "\n\nSynthesis failed (empty response). " + str(len(rows)) + " signaux disponibles."
        # Catalysts DETERMINISTES prefixes (Heimdall fix 29/07) : autoritaires,
        # le LLM ne genere plus sa section catalysts (fail-silent supprime).
        return _deterministic_catalysts() + "\n\n" + _t13_guard(narrative.strip())
    except Exception as e:
        return "Synthesis failed: " + type(e).__name__ + ": " + str(e)[:200]
