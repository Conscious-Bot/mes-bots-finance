"""J-day batch close job (single-fire 2026-06-10 09:30).

Le 10/06 est le premier batch significatif de predictions V1 a J+28.
Ce job se substitue au workflow manuel : Brier report + same-day snapshot
+ Telegram digest. Cron date-trigger one-shot, fire-and-forget.

Order :
  1. attente garantie daily_resolve_job (09:00) -> 17 V1 restantes resolvent
  2. compute Brier report sur la date (Telegram + log structure)
  3. force monthly track_record snapshot pour 2026-06 (vs cron 1er juillet)
  4. re-render public site_public/track.html avec donnees fresh

Idempotent : si re-lance, le snapshot 2026-06 sera ecrase (force=True).
"""

from __future__ import annotations

import logging
from datetime import date

from shared import notify

log = logging.getLogger("bot")

J_DAY_DATE = "2026-06-10"


def _build_brier_telegram_msg(target_date: str) -> tuple[str, dict]:
    """Compute Brier metrics for predictions resolved on target_date.

    Returns (telegram_message, metrics_dict).
    """
    from shared import storage

    # ADR 014 § Archive-report rule : ce rapport est le wrapup V1.
    # Son sujet = methodology_version='v1' EXPLICITEMENT. On n'applique PAS
    # canonical_predictions_filter() ici (ce filtre exclut v1 et le rapport
    # deviendrait un silent zero le 10/06 -- bug interdit par CONVENTIONS #6).
    # canonical_filter sert UNIQUEMENT aux surfaces forward-headline
    # (track record public, KPI #2 forward, calibration audit). Ce rapport
    # est un archive-report sur une famille morte -> il cible la famille.
    with storage.db() as cx:
        rows = cx.execute(
            """SELECT id, ticker, direction, return_pct, outcome,
                      probability_at_creation, brier_score, signal_id
               FROM predictions
               WHERE date(resolved_at) = ? AND resolved_at IS NOT NULL
                 AND methodology_version = 'v1'""",
            (target_date,),
        ).fetchall()

    if not rows:
        # Honest marker plutot que silent zero : on dit POURQUOI c'est vide.
        return (
            f"J-day {target_date} : aucune prediction V1 resolue ce jour. "
            "(Archive V1 close. v2 pas encore demarre -> headline canonique a venir.)",
            {},
        )

    n = len(rows)
    n_correct = sum(1 for r in rows if r["outcome"] == "correct")
    n_incorrect = sum(1 for r in rows if r["outcome"] == "incorrect")
    n_neutral = n - n_correct - n_incorrect

    briers = [r["brier_score"] for r in rows if r["brier_score"] is not None]
    clusters: dict[tuple, list[float]] = {}
    for r in rows:
        if r["brier_score"] is None:
            continue
        k = (r["signal_id"], r["ticker"], r["direction"])
        clusters.setdefault(k, []).append(r["brier_score"])
    cluster_briers = [sum(v) / len(v) for v in clusters.values()]

    avg_raw = sum(briers) / len(briers) if briers else None
    avg_dedup = sum(cluster_briers) / len(cluster_briers) if cluster_briers else None
    dedup_ratio = (len(briers) / len(clusters)) if clusters else None

    unique_probs = {round(r["probability_at_creation"] or 0, 2) for r in rows}
    mono_bucket = len(unique_probs) <= 2

    metrics = {
        "target_date": target_date,
        "n_total": n,
        "n_correct": n_correct,
        "n_incorrect": n_incorrect,
        "n_neutral": n_neutral,
        "n_scored": len(briers),
        "n_clusters": len(clusters),
        "dedup_ratio": dedup_ratio,
        "brier_raw_avg": avg_raw,
        "brier_dedup_avg": avg_dedup,
        "mono_bucket_warning": mono_bucket,
    }

    pct_corr = (n_correct / n * 100) if n else 0
    lines = [
        f"J-DAY BATCH {target_date}",
        "Famille : V1 (transitional, exclue du headline canonique public)",
        f"N resolved: {n} ({n_correct}/{n_incorrect}/{n_neutral} = {pct_corr:.0f}% correct)",
    ]
    if avg_raw is not None:
        verdict = "BEATS" if avg_raw < 0.25 else "WORSE THAN"
        lines.append(f"Brier raw: {avg_raw:.3f} ({verdict} 0.25 baseline)")
    if avg_dedup is not None and dedup_ratio is not None:
        lines.append(
            f"Brier dedup: {avg_dedup:.3f} on {len(clusters)} clusters "
            f"(dedup ratio {dedup_ratio:.2f}x)"
        )
    if mono_bucket and briers:
        lines.append(
            "WARNING: probas in <=2 unique buckets => reliability diagram degenerate. "
            "Calibration non-publishable on this batch alone."
        )

    return ("\n".join(lines), metrics)


async def j_day_batch_close_job():
    """One-shot J-day 10/06 wrapup : Brier report + same-day snapshot + Telegram.

    Wired via APScheduler `date` trigger 2026-06-10 09:30. Runs after
    morning_chain (daily_resolve_job 09:00). Idempotent (snapshot force=True).
    """
    today = date.today().isoformat()
    if today != J_DAY_DATE:
        log.warning(
            f"j_day_batch_close_job fired on {today} not {J_DAY_DATE} -- skipping"
        )
        return

    log.info(f"J-day batch close starting for {J_DAY_DATE}")

    # 1. Brier report Telegram
    try:
        msg, metrics = _build_brier_telegram_msg(J_DAY_DATE)
        notify.send_text(msg)
        log.info(f"J-day Brier report sent: {metrics}")
    except Exception as e:
        log.error(f"j_day_batch_close_job Brier report failed: {e}", exc_info=True)
        notify.send_text(f"J-day {J_DAY_DATE} Brier report FAILED: {type(e).__name__}: {e}")

    # 2. Force monthly snapshot for 2026-06 (vs cron 1er juillet)
    try:
        from intelligence.monthly_track_record import run_monthly_track_record_job

        result = run_monthly_track_record_job(year_month="2026-06", force=True)
        snap_path = result.get("snapshot_path", "?")
        public_path = result.get("public_html_path", "?")
        notify.send_text(
            f"J-day snapshot exported:\n"
            f"  JSON: {snap_path}\n"
            f"  Public HTML: {public_path}"
        )
        log.info(f"J-day snapshot success: {result}")
    except Exception as e:
        log.error(f"j_day_batch_close_job snapshot failed: {e}", exc_info=True)
        notify.send_text(
            f"J-day {J_DAY_DATE} snapshot FAILED: {type(e).__name__}: {e}"
        )

    # 3. Out-of-band dead-man-s-switch : ping healthchecks.io. Si l'URL est
    # configuree (.env HEALTHCHECKS_J_DAY_URL) et que ce ping arrive,
    # healthchecks confirme silencieusement. S'il N'arrive PAS dans la grace
    # window configuree cote healthchecks, leur infra envoie un alert email
    # / SMS / webhook -- INDEPENDANT du Mac. C'est la vraie protection contre
    # "Mac asleep / no network / process crashed", qu'aucun cron local ne
    # peut detecter (le watcher j_day_watcher.sh fire dans la meme box).
    #
    # Setup une fois : creer un check sur healthchecks.io (cron 30 9 10 6 *,
    # grace 4h), copier la ping URL dans .env HEALTHCHECKS_J_DAY_URL.
    # Fail-safe : si l'URL absent ou ping fail, on ne casse pas le job.
    try:
        import os
        import urllib.request

        ping_url = os.environ.get("HEALTHCHECKS_J_DAY_URL", "").strip()
        if ping_url:
            req = urllib.request.Request(ping_url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                log.info(
                    f"J-day healthchecks.io ping sent (status={resp.status})"
                )
        else:
            log.warning(
                "J-day healthchecks.io ping skipped : HEALTHCHECKS_J_DAY_URL "
                "absent du .env. Out-of-band dead-man-s-switch INACTIF."
            )
    except Exception as e:
        log.warning(f"J-day healthchecks.io ping failed (non-fatal): {e}")
