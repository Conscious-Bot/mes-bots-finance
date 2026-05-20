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

log = logging.getLogger(__name__)


def synthesize_signal(signal_dict: dict[str, Any], watchlist: list[str], regime_context: str | None = None, insider_context: str | None = None) -> dict[str, Any]:
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


def run_enhanced_digest(limit: int = 20, top_n: int = 5, fallback_hours: int = 72, include_regime: bool = True, annotate_top: int = 3, persist: bool = True) -> str:
    import logging

    log = logging.getLogger(__name__)
    existing_msg = run_digest(limit=limit, top_n=top_n, fallback_hours=fallback_hours, include_regime=include_regime)
    if not existing_msg:
        return existing_msg
    try:
        from intelligence import materiality, why_matters
        from shared import macro, storage as storage_mod

        with storage_mod.db() as cx:
            rows = cx.execute(
                "SELECT * FROM signals WHERE timestamp > datetime('now', ?) ORDER BY timestamp DESC LIMIT 100",
                ("-" + str(fallback_hours) + " hours",),
            ).fetchall()
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


def generate_unified_digest(since_hours: int = 24, max_signals: int = 40, exclude_low_score: bool = True) -> str:
    """Single narrative synthesizing all recent signals into themes + catalysts + noise + actions.

    Replaces the per-email summary format with thematic synthesis.
    Cost: ~$0.025/call (Sonnet enrich, ~6k input + 1k output).
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
    rows = conn.execute(
        "SELECT s.id, s.title, s.summary, s.signal_type, s.score, "
        "s.impact_magnitude, s.reversibility, s.time_to_realization, "
        "s.materiality_boost, s.entities, src.name AS source "
        "FROM signals s LEFT JOIN sources src ON s.source_id = src.id "
        "WHERE s.timestamp >= ? " + where_score + " "
        "ORDER BY (COALESCE(s.score, 0) * COALESCE(s.materiality_boost, 1.0)) DESC LIMIT ?",
        (cutoff, int(max_signals)),
    ).fetchall()
    conn.close()
    if not rows:
        return "Aucun signal pertinent sur les dernieres " + str(since_hours) + "h."
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
        line = "[" + st + " | adj=" + str(round(adj, 1)) + "/10"
        if imp is not None:
            line += " impact=" + str(int(imp)) + "/5 time=" + str(r["time_to_realization"] or "?")
        line += "] " + (r["source"] or "?") + ": " + (r["title"] or "?")[:140] + ents
        summary = (r["summary"] or "")[:300]
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
    prompt = (
        "Tu es l'analyste finance d'Olivier (profil thesis-driven slow alpha sur tech/semis/AI/crypto, "
        "biais asymetriques: vend winners trop tot PLTR/NVDA, ne vend pas crypto aux tops, "
        "univers core: NVDA AVGO TSM MU ASML AMD ARM MSFT GOOGL META CEG VST GEV MSTR IBIT COIN V BLK LLY NVO+74 watch+82 extended).\n\n"
        "Date du jour: " + today_str + ". Window analyse: derniers " + str(since_hours) + "h.\n\n"
        "Voici " + str(len(rows)) + " signaux digeres. " + stats_line + "\n\n"
        "=== SIGNAUX BRUTS ===\n" + signals_text + "\n\n"
        "=== PRODUIS UNE SYNTHESE NARRATIVE UNIFIEE ===\n\n"
        "REGLE CRITIQUE: ne JAMAIS inventer ou hardcoder une date dans ton output. La date du jour est ci-dessus. "
        "Si tu references une date, elle doit etre soit la date du jour (" + today_str[:10] + ") soit une date explicite d'un signal cite.\n\n"
        "REGLE CATALYSTS: un CATALYST est un event marche concret avec date approximative (earnings, FOMC, FDA decision, etc). "
        "Une 'newsletter a lire' ou 'reunion regulateurs dans semaines/mois' N'EST PAS un catalyst. Si rien de concret: dis 'Aucun catalyst date concret detecte dans ce window'.\n\n"
        "Structure obligatoire:\n\n"
        "VERDICT: X urgent / Y monitoring / Z noise\n"
        "(1 ligne tout en haut. X+Y+Z doit correspondre a ton analyse globale, pas au count brut.)\n\n"
        "THEMES MAJEURS (3-5 max)\n"
        "Pour chaque theme: nom court, tickers concernes, signaux convergents (multi-source = boost credibilite), "
        "1-2 phrases sur pourquoi ca matte ou pas pour Olivier.\n\n"
        "CATALYSTS A SURVEILLER\n"
        "Top 3-5 events specifiques avec ticker + date approximative + impact attendu. Si aucun: une ligne explicite.\n\n"
        "BRUIT JETE\n"
        "UNE SEULE LIGNE format: 'Skipped: N sources, mostly [theme1, theme2]'. Pas de details, pas de liste.\n\n"
        "ACTION ITEMS POUR OLIVIER (max 3 bullets)\n"
        "Decisions concretes a prendre/surveiller selon son thesis active et ses biais asymetriques.\n\n"
        "Ton: direct, jargon pro francais, pragmatique, max 600 mots. Pas de fawning, dire les choses sans edulcorer."
    )
    try:
        narrative = llm.call(prompt, tier="enrich", max_tokens=2000)
        if not narrative:
            return "Synthesis failed (empty response). " + str(len(rows)) + " signaux disponibles."
        return narrative.strip()
    except Exception as e:
        return "Synthesis failed: " + type(e).__name__ + ": " + str(e)[:200]
