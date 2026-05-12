"""Newsletter digest synthesizer.

Reads unprocessed raw email signals from DB, calls Claude to extract structured
insights (score, sentiment, tickers, narratives, summary), updates DB,
returns formatted digest for Telegram.
"""
from shared import storage, llm, config
from shared.prompts import DIGEST_SYNTHESIZER


def synthesize_signal(signal_dict, watchlist, regime_context=None, insider_context=None):
    """Call LLM to extract structured insights. Optionally with regime preamble."""
    body = (signal_dict.get('content') or '')[:10000]
    watchlist_str = ", ".join(watchlist[:30]) + (f"... ({len(watchlist)} total)" if len(watchlist) > 30 else "")
    base_prompt = DIGEST_SYNTHESIZER.format(
        ticker_watchlist=watchlist_str,
        source=signal_dict.get('source_name', 'unknown'),
        subject=(signal_dict.get('title') or '')[:300],
        body=body,
    )
    prompt = (regime_context or "") + (insider_context or "") + base_prompt
    try:
        result = llm.call_json(prompt, task='signal_scoring', max_tokens=1500)
        return result
    except Exception as e:
        return {
            'score': 0, 'sentiment': 'neutral', 'tickers': [],
            'drivers': [], 'summary': None,  # null → score_pending cron retries
            'actionable': False, 'narratives': [], 'confidence': 0,
            'error': str(e),
        }


def process_unprocessed(limit=20):
    """Process up to `limit` unprocessed raw signals. Fetches regime once per batch."""
    cfg = config.load()
    watchlist = cfg.get('universe', {}).get('watchlist', [])
    signals = storage.get_unprocessed_signals(limit=limit)
    if not signals:
        return []
    regime_context = None
    try:
        from intelligence import regime as _regime_mod
        regime_context = _build_regime_context(_regime_mod.detect_regime())
    except Exception as _e:
        print(f"Regime ctx fetch failed: {_e}")
    insider_context = None
    try:
        insider_context = _build_insider_context()
    except Exception as _e:
        print(f"Insider ctx fetch failed: {_e}")
    processed = []
    for sig in signals:
        insights = synthesize_signal(sig, watchlist, regime_context=regime_context, insider_context=insider_context)
        try:
            storage.update_signal_insights(
                sig['id'],
                score=int(insights.get('score', 0)),
                sentiment=insights.get('sentiment', 'neutral'),
                tickers=insights.get('tickers', []),
                narratives=insights.get('narratives', []),
                summary=insights.get('summary', ''),
            )
            processed.append({**sig, **insights})
        except Exception as e:
            print(f"Failed to store insights for signal {sig['id']}: {e}")
    try:
        from intelligence import learning as _learning
        _pids = _learning.auto_register_predictions(processed)
        if _pids:
            print(f"Registered {len(_pids)} predictions from {len(processed)} signals")
    except Exception as _e:
        print(f"Auto-register predictions failed: {_e}")
    return processed


def build_digest_telegram(processed_signals, top_n=5):
    """Format top-N scored signals for Telegram (plain text)."""
    if not processed_signals:
        return "Aucun signal a digerer."
    sorted_sigs = sorted(processed_signals, key=lambda s: s.get('score') or 0, reverse=True)
    parts = [f"Digest - {len(processed_signals)} signaux traites", ""]
    for i, s in enumerate(sorted_sigs[:top_n], 1):
        source = (s.get('source_name') or 'unknown')[:40]
        score = s.get('score', '?')
        sentiment = s.get('sentiment', '?')
        summary = s.get('summary', '')
        tickers = s.get('tickers') or []
        fb = s.get('user_feedback') or ''
        fb_marker = ' [+]' if fb == 'up' else (' [-]' if fb == 'down' else '')
        parts.append(f"{i}. #{s.get('id', '?')} [{source}] score {score}/10 ({sentiment}){fb_marker}")
        if tickers:
            parts.append(f"   tickers: {', '.join(tickers)}")
        parts.append(f"   {summary}")
        parts.append("")
    return "\n".join(parts)


def run_digest(limit=20, top_n=5, fallback_hours=72, include_regime=True):
    """Full digest pipeline. Falls back to recent if nothing new.
    Prepends regime banner if include_regime=True.
    """
    processed = process_unprocessed(limit=limit)
    if not processed:
        recent = storage.get_recent_processed_signals(hours=fallback_hours, limit=20)
        if not recent:
            digest_msg = "Aucun signal a digerer (ni nouveau ni en stock)."
        else:
            digest_msg = f"Aucun NOUVEAU signal. Stock recents ({fallback_hours}h):\n\n" + build_digest_telegram(recent, top_n=top_n)
    else:
        digest_msg = build_digest_telegram(processed, top_n=top_n)

    if include_regime:
        try:
            from intelligence import regime as _regime
            r = _regime.detect_regime()
            banner = _regime.format_regime(r)
            return banner + "\n\n---\n\n" + digest_msg
        except Exception as _e:
            print(f"Regime banner failed: {_e}")
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



def _build_regime_context(r):
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
from shared import config as _cfg
INSIDER_TOP_TICKERS = _cfg.get_tickers('core')


def _build_insider_context():
    """Fetch top-watchlist insider briefs (cached 24h) and format for LLM prompt."""
    try:
        from shared import edgar as _edgar_mod
        briefs = _edgar_mod.get_insider_briefs(INSIDER_TOP_TICKERS)
        return _edgar_mod.format_insider_context_for_prompt(briefs)
    except Exception as e:
        print(f"Insider context failed: {e}")
        return ""


def run_enhanced_digest(limit=20, top_n=5, fallback_hours=72, include_regime=True,
                         annotate_top=3, persist=True):
    import logging
    log = logging.getLogger(__name__)
    existing_msg = run_digest(limit=limit, top_n=top_n,
                               fallback_hours=fallback_hours, include_regime=include_regime)
    if not existing_msg:
        return existing_msg
    try:
        from intelligence import materiality, why_matters
        from shared import macro, storage as storage_mod

        with storage_mod.db() as cx:
            rows = cx.execute(
                "SELECT * FROM signals WHERE timestamp > datetime('now', ?) ORDER BY timestamp DESC LIMIT 100",
                ("-" + str(fallback_hours) + " hours",)
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
        try:
            regime_info["credit"] = macro.get_credit_regime()
        except Exception:
            pass

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
            sections.append("#" + str(i) + " [" + primary + "] [" + sig_type + "] materiality=" + ("%.3f" % score["composite"]))
            sections.append("   " + title)
            if why:
                sections.append("   --> " + why)
            sections.append("")

        return "\n".join(sections) + "\n---\n\n" + existing_msg

    except Exception as e:
        log.warning("enhance digest failed: " + str(e))
        return existing_msg
