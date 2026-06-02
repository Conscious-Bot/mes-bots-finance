"""/track_record -- expose le track record public via Telegram.

Lecture-only. Appelle compute_public_track_record + format compact pour
Telegram (limite 4000 char). Sur demande, peut surfacer une snapshot
mensuelle archivee (data/track_record/snapshots/YYYY-MM.json).

Usage :
  /track_record         -> snapshot live (compute now)
  /track_record 2026-06 -> snapshot mensuel dated (si dispo)
  /track_record latest  -> dernier snapshot archive
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from bot.handlers._common import db_path

__all__ = ["cmd_track_record"]

log = logging.getLogger("bot")


def _format_aggregator_compact(agg: dict[str, Any]) -> str:
    """Compact Telegram message (< 4000 char)."""
    posture = agg.get("posture_global", "—")
    pred = agg.get("predictions", {})
    theses = agg.get("theses", {})
    by_posture = theses.get("by_posture", {})
    alpha = agg.get("alpha", {})
    bias_list = agg.get("bias_events", [])

    lines = ["📊 *PRESAGE Track Record*"]
    lines.append(f"Posture globale : *{posture}*")
    lines.append("")

    # Predictions
    n_resolved = pred.get("n_resolved", 0)
    n_open = pred.get("n_open", 0)
    brier_avg = pred.get("brier_avg")
    brier_status = pred.get("brier_status", "—")
    acc = pred.get("accuracy_pct")
    lines.append("*Predictions*")
    lines.append(f"  ouvertes : {n_open} · resolues : {n_resolved}")
    if brier_avg is not None:
        lines.append(f"  Brier moyen : {brier_avg:.3f} ({brier_status})")
    if acc is not None:
        lines.append(f"  accuracy : {acc}%")
    lines.append("")

    # Bias events cumul
    lines.append("*Biais comportementaux*")
    total_delta = agg.get("bias_total_delta_signed_eur", 0.0)
    sign = "+" if total_delta >= 0 else ""
    lines.append(f"  delta cumule : {sign}{total_delta:.0f} €")
    for b in bias_list:
        if b.get("n_resolved", 0) > 0:
            d = b.get("total_delta_signed_eur", 0.0)
            ds = "+" if d >= 0 else ""
            posture_b = b.get("posture", "—")
            lines.append(
                f"  {b['bias']:<12} {b['n_resolved']:>3} resol · "
                f"{ds}{d:.0f} € · {posture_b}"
            )
    lines.append("")

    # Thèses
    n_active = theses.get("n_active", 0)
    lines.append("*Theses*")
    lines.append(f"  actives : {n_active}")
    if by_posture:
        ok = by_posture.get("OK", 0)
        warn = by_posture.get("WARN", 0)
        alert = by_posture.get("ALERT", 0)
        insuf = by_posture.get("INSUFFICIENT_DATA", 0)
        lines.append(f"  OK : {ok} · WARN : {warn} · ALERT : {alert} · n/d : {insuf}")
    top_alerts = theses.get("top_alert_tickers", [])
    if top_alerts:
        names = ", ".join(t.get("ticker", "?") for t in top_alerts[:3])
        lines.append(f"  top alertes : {names}")
    lines.append("")

    # Alpha
    if alpha and "error" not in alpha:
        alpha_pct = alpha.get("alpha_pct")
        book = alpha.get("book_return_pct")
        bench = alpha.get("bench_return_pct")
        ticker = alpha.get("bench_ticker", "bench")
        window = alpha.get("window_months", "?")
        if alpha_pct is not None:
            sign_a = "+" if alpha_pct >= 0 else ""
            lines.append("*Alpha*")
            lines.append(
                f"  book {book:+.1f}% vs {ticker} {bench:+.1f}% = "
                f"alpha {sign_a}{alpha_pct:.1f}% sur {window}m"
            )
            lines.append("")

    # Methodology one-liner
    m = agg.get("methodology", {})
    if m and "error" not in m:
        lines.append(
            f"_scorer {m.get('scorer_version', '?')} · "
            f"horizon pred {m.get('prediction_horizon_days', '?')}j · "
            f"horizon lock_in {m.get('lock_in_horizon_days', '?')}j · "
            f"recal floors [{m.get('credibility_floor_ceiling', ['?', '?'])[0]:.2f}, "
            f"{m.get('credibility_floor_ceiling', ['?', '?'])[1]:.2f}]_"
        )

    return "\n".join(lines)


async def cmd_track_record(update, ctx):
    """Telegram handler.
    Args :
      /track_record         -> compute live snapshot
      /track_record 2026-06 -> load snapshot YYYY-MM
      /track_record latest  -> load le plus recent snapshot
    """
    args = ctx.args if ctx.args else []
    arg = args[0] if args else None

    try:
        if arg:
            from intelligence.monthly_track_record import (
                list_snapshots,
                load_snapshot,
            )
            if arg == "latest":
                snaps = list_snapshots()
                if not snaps:
                    await update.message.reply_text(
                        "Aucun snapshot mensuel archive. Cron mensuel "
                        "(1er du mois 8h) le creera automatiquement."
                    )
                    return
                arg = snaps[-1]
            snap = load_snapshot(arg)
            if snap is None:
                await update.message.reply_text(
                    f"Snapshot {arg} introuvable. Disponibles : "
                    f"{', '.join(list_snapshots()[-5:]) or 'aucun'}"
                )
                return
            agg = snap.get("aggregator", {})
            header = f"📁 _Snapshot {arg} (genere {snap.get('generated_at', '?')[:16]})_\n\n"
            text = header + _format_aggregator_compact(agg)
        else:
            # Live snapshot
            from intelligence.track_record_aggregator import (
                compute_public_track_record,
            )
            cx = sqlite3.connect(db_path())
            try:
                agg = compute_public_track_record(cx)
            finally:
                cx.close()
            text = _format_aggregator_compact(agg)

        # Telegram limite 4096 char message
        await update.message.reply_text(text[:4000], parse_mode="Markdown")
    except Exception as e:
        log.exception(f"cmd_track_record crashed: {e}")
        await update.message.reply_text(f"track_record erreur : {type(e).__name__}")
