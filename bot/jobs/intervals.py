"""Intervals cron jobs — extracted from bot/jobs.py Phase C (21/05/2026)."""



import logging

from data_sources import gmail_
from intelligence.price_monitor import check_thesis_triggers
from shared import config, storage

log = logging.getLogger("bot")

CALENDAR_REFRESH_TICKERS = config.get_tickers("core") if hasattr(config, "get_tickers") else []


async def heartbeat():
    storage.update_state()
    log.info("heartbeat ok")

async def ingest_gmail_job():
    """Hourly Gmail ingestion + immediate materiality_v2 chaining.

    Phase Solidification P1 #2: rubric scoring runs RIGHT after ingestion to keep
    coverage high regardless of cron timing. The standalone cron materiality_v2 1h
    remains as catch-up safety net for any stragglers.
    """
    try:
        stats = gmail_.ingest_new_emails(max_results=50)
        if stats["new_ingested"]:
            log.info(f"gmail ingest: +{stats['new_ingested']} new emails")
            # Chain materiality_v2 immediately - score what was just ingested + small buffer
            try:
                from intelligence import materiality_v2

                target = min(stats["new_ingested"] + 5, 30)  # cap at 30 to avoid cost spike
                s, f, total = materiality_v2.score_pending_signals_v2(limit=target)
                if total > 0:
                    log.info(f"materiality_v2 chained: {s}/{total} scored, {f} failed")
            except Exception as e:
                log.warning(f"materiality_v2 chain error: {e}")
    except Exception as e:
        log.error(f"gmail ingest failed: {e}")

async def update_echo_clusters_job():
    """Phase A3 — Hourly: embed pending signals + compute echo clusters in 48h window."""
    log.info("Echo clusters update starting")
    try:
        from shared import echo as echo_mod, embeddings as emb_mod, storage as storage_mod

        pending = storage_mod.get_unembedded_signals(limit=100)
        if pending:
            txts = [(p.get("text_for_embed") or "")[:500] for p in pending]
            vecs = emb_mod.embed_batch(txts)
            for p, v in zip(pending, vecs):
                blob = emb_mod.serialize(v)
                storage_mod.store_signal_embedding(p["id"], blob, emb_mod.model_name())
            log.info(f"Embedded {len(pending)} pending signals")

        clusters = echo_mod.compute_clusters(window_hours=48, sim_threshold=0.85)
        echo_mod.persist_clusters(clusters)
        multi = [c for c in clusters if c["n_unique_sources"] >= 2]
        log.info(f"Echo clusters done: {len(clusters)} total, {len(multi)} multi-source")
    except Exception as e:
        log.exception(f"update_echo_clusters_job crashed: {e}")

async def score_pending_signals_job():
    """Phase data-quality fix — Hourly: score signals with entities IS NULL.
    Drains backlog of signals that the daily digest (limit=20/day) didn't cover.
    """
    log.info("Score pending signals starting")
    try:
        from intelligence import digest as digest_mod

        results = digest_mod.process_unprocessed(limit=50)
        if results:
            n_with_tickers = sum(1 for r in results if r.get("tickers"))
            n_errors = sum(1 for r in results if r.get("error"))
            log.info(
                f"Score pending: processed {len(results)} signals, {n_with_tickers} with tickers, {n_errors} LLM errors"
            )
    except Exception as e:
        log.exception(f"score_pending_signals_job crashed: {e}")

async def scheduled_classify_signal_types_job():
    """Phase Digestion 3a — Classify signals with signal_type=NULL every 30min."""
    try:
        from intelligence import signal_classify

        n_classified, types = signal_classify.classify_pending_signals(limit=30)
        if n_classified > 0:
            log.info(f"signal_type classifier: {n_classified} classified, distribution={types}")
    except Exception as e:
        log.warning(f"classify_signal_types_job error: {e}")

async def scheduled_recompute_materiality_boost_job():
    """Phase Digestion 3b — Recompute corroboration multipliers after echo clusters update."""
    try:
        from intelligence import materiality_boost

        n = materiality_boost.recompute_boosts_for_clustered_signals()
        if n > 0:
            log.info(f"materiality_boost: {n} signals re-boosted")
    except Exception as e:
        log.warning(f"recompute_boost_job error: {e}")

async def scheduled_materiality_v2_job():
    """Phase Digestion 3c — Score signals with structured rubric every 1h."""
    try:
        from intelligence import materiality_v2

        s, f, total = materiality_v2.score_pending_signals_v2(limit=30)
        if total > 0:
            log.info(f"materiality_v2: {s} scored, {f} failed of {total}")
    except Exception as e:
        log.warning(f"materiality_v2_job error: {e}")

async def price_monitor_job():
    """Cron 15min mkt hours: check active theses for price crossings."""
    try:
        r = check_thesis_triggers()
        if r["alerts"]:
            log.info(f"price_monitor: {len(r['alerts'])} alerts fired: {r['alerts']}")
        if r["fails"]:
            log.warning(f"price_monitor: failed tickers: {r['fails']}")
    except Exception as e:
        log.error(f"price_monitor_job: {e}")

