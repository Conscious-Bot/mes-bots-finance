"""/why <pred_id> -- Expose scoring trace + provenance d'une prediction.

#74 UI : "pourquoi cette proba ?". Lit get_prediction_provenance et
formate en message Telegram concis.

Usage :
  /why 123       -> trace de prediction id=123
  /why NVDA      -> trace de la prediction la plus recente sur NVDA
"""

from __future__ import annotations

import logging

__all__ = ["cmd_why"]

log = logging.getLogger("bot")


def _format_provenance(prov: dict) -> str:
    """Format compact Telegram (Markdown)."""
    if not prov:
        return "_introuvable_"
    pred = prov.get("prediction") or {}
    sig = prov.get("signal") or {}
    src = prov.get("source") or {}
    trace = prov.get("scoring_trace") or {}
    src_meta = prov.get("source_metadata") or {}

    lines = [
        f"*Prediction #{pred.get('id', '?')}* — {pred.get('ticker', '?')}",
        f"direction : {pred.get('direction', '?')}  ·  "
        f"prob : {pred.get('probability_at_creation', '?')}  ·  "
        f"horizon : {pred.get('horizon_days', '?')}j",
    ]
    if pred.get("outcome"):
        lines.append(
            f"outcome : *{pred['outcome']}*  ·  Brier : {pred.get('brier_score', '?')}"
        )
    lines.append("")

    if trace:
        lines.append("*Scoring V2 (3 etapes)*")
        bare_rate = trace.get("base_rate")
        if bare_rate is not None:
            lines.append(f"  base_rate : {bare_rate}")
        ev_str = trace.get("evidence_strength")
        if ev_str:
            lines.append(f"  evidence : {ev_str}")
        ev_summary = trace.get("evidence_summary")
        if ev_summary:
            lines.append(f"  → {ev_summary[:300]}")
        anti = trace.get("anti_anchoring_reason")
        if anti:
            lines.append(f"  anti-ancrage : {anti[:200]}")
        reasoning = trace.get("reasoning")
        if reasoning:
            lines.append(f"  raisonnement : {reasoning[:300]}")
        lines.append("")
    else:
        lines.append("_scoring_trace indisponible (prediction pre-#70)_")
        lines.append("")

    if sig:
        title = (sig.get("title") or "")[:140]
        lines.append("*Signal source*")
        if title:
            lines.append(f"  titre : {title}")
        lines.append(f"  timestamp : {(sig.get('timestamp') or '')[:16]}")
        if src:
            lines.append(
                f"  source : {src.get('name', '?')}  "
                f"(credibility actuelle {src.get('credibility', '?')})"
            )
        if src_meta and src_meta.get("credibility_at_creation") is not None:
            lines.append(
                f"  credibility au moment de la prediction : "
                f"{src_meta['credibility_at_creation']}"
            )
        lines.append("")

    lines.append(
        f"_baseline {pred.get('baseline_price', '?')} a {pred.get('baseline_date', '?')} → "
        f"cible {pred.get('target_date', '?')}_"
    )
    return "\n".join(lines)


async def cmd_why(update, ctx):
    """Telegram handler."""
    if not ctx.args:
        await update.message.reply_text(
            "Usage : /why <prediction_id|ticker>\n"
            "  /why 123     -> prediction id 123\n"
            "  /why NVDA    -> prediction la plus recente sur NVDA"
        )
        return

    arg = ctx.args[0].strip().upper()

    try:
        from shared import storage
        pred_id: int | None = None

        if arg.isdigit():
            pred_id = int(arg)
        else:
            # Resoudre par ticker -> id de la prediction la plus recente
            with storage.db() as cx:
                row = cx.execute(
                    "SELECT id FROM predictions "
                    "WHERE ticker = ? AND methodology_version != 'v0' "
                    "ORDER BY id DESC LIMIT 1",
                    (arg,),
                ).fetchone()
            if not row:
                await update.message.reply_text(
                    f"Pas de prediction V1/V2 trouvee pour {arg}."
                )
                return
            pred_id = int(row[0] if not isinstance(row, dict) else row["id"])

        prov = storage.get_prediction_provenance(pred_id)
        if not prov:
            await update.message.reply_text(f"Prediction {pred_id} introuvable.")
            return
        text = _format_provenance(prov)
        await update.message.reply_text(text[:4000], parse_mode="Markdown")
    except Exception as e:
        log.exception(f"cmd_why crashed: {e}")
        await update.message.reply_text(f"why erreur : {type(e).__name__}")
