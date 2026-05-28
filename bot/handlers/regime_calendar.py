from shared import config

"""Day 10 E batch 2+3 extracted from bot/main.py.

Handlers: cmd_calendar, cmd_calendar_refresh, cmd_regime
"""

from intelligence import calendar as calendar_mod, regime as regime_mod
from shared import storage

CALENDAR_REFRESH_TICKERS = config.get_tickers("core") if hasattr(config, "get_tickers") else []


async def cmd_regime(update, ctx):  # noqa: ARG001
    """Detection du regime de marche (risk_on/off/transition/crisis)."""
    await update.message.reply_text("Detection regime en cours (5-10s)...")
    try:
        r = regime_mod.detect_regime()
        msg = regime_mod.format_regime(r)
        await update.message.reply_text(msg[:4000])
    except Exception as e:
        await update.message.reply_text(f"Erreur: {type(e).__name__}: {e}")


async def cmd_calendar(update, ctx):  # noqa: ARG001
    """Evenements macro a venir (60j) + alertes pre-evenement par these."""
    events = storage.get_upcoming_events(days_ahead=60)
    msg = calendar_mod.format_calendar(events, days_ahead=60)
    alerts = calendar_mod.get_pre_event_thesis_alerts(days_ahead=14)
    alert_msg = calendar_mod.format_alerts(alerts)
    if alert_msg:
        msg = alert_msg + "\n\n---\n\n" + msg
    await update.message.reply_text(msg[:4000])


