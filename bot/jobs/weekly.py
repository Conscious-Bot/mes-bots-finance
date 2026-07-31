"""Job cron SYNTHÈSE HEBDO (Format B) — dimanche 18h (tz scheduler = Europe/Paris).

Glue mince : intelligence.weekly_synthesis.generate_weekly_synthesis() (payload +
render + guards, testé) → fichier daté durable + push Telegram chunké.
Fail-closed : render renvoie déjà « INDISPONIBLE (incident) » sur payload vide.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

_OUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "weekly"


async def weekly_synthesis_job() -> None:
    try:
        from shared.healthcheck_ping import ping as _hc_ping
        _hc_ping("weekly_synthesis_job", status="start")
    except Exception:
        pass
    try:
        from intelligence.weekly_synthesis import generate_weekly_synthesis
        from shared import notify

        text = generate_weekly_synthesis()

        # Fichier daté durable (lecture confortable ; le Telegram reste le push)
        try:
            _OUT_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).date().isoformat()
            (_OUT_DIR / f"synthese_hebdo_{stamp}.md").write_text(text, encoding="utf-8")
        except Exception as e:
            log.warning(f"weekly file write failed (non-bloquant): {e}")

        notify.send_text(text)  # send_text chunke au-delà de 3800 chars

        try:
            from shared.healthcheck_ping import ping as _hc_ping
            _hc_ping("weekly_synthesis_job", status="ok")
        except Exception:
            pass
    except Exception as e:
        log.error(f"weekly_synthesis_job failed: {e}", exc_info=True)
        try:
            from shared import notify
            notify.send_text(f"SYNTHÈSE HEBDO — échec job (incident) : {type(e).__name__}: {str(e)[:160]}")
        except Exception:
            pass
