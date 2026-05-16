"""Anti-erosion log handlers for /log_value and /log_friction.

Extracted from bot/main.py in Sprint 1.1 chunk 1 (2026-05-16) as part of the
handler consolidation V4 spec. Mechanical move only, zero logic change.

VALUE_LOG.md captures moments where the bot empirically helped a decision.
friction.md captures moments of UX/cognitive friction with the bot.

Both are anti-erosion mechanisms for solo 12-month build: if VALUE_LOG.md is
empty at J+30 the bot has no measurable user value; if friction.md has 0
entries the bot is not being used reflectively.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

__all__ = ["_append_log_entry", "cmd_log_value", "cmd_log_friction"]


def _append_log_entry(filename: str, message: str) -> None:
    """Append a timestamped entry to a log file at the repo root."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    log_path = repo_root / filename
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {message}\n")


async def cmd_log_value(update, ctx):  # noqa: ARG001
    """Append entry to VALUE_LOG.md. Usage: /log_value <message>"""
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        await update.message.reply_text(
            "Usage: /log_value <message>\n"
            "Exemple: /log_value bot m'a alerte sur 8K NVDA avant que je le rate"
        )
        return
    try:
        _append_log_entry("VALUE_LOG.md", text)
        await update.message.reply_text(f"OK logged to VALUE_LOG.md:\n  {text[:300]}")
    except Exception as e:
        await update.message.reply_text(f"Error writing VALUE_LOG.md: {e}")


async def cmd_log_friction(update, ctx):  # noqa: ARG001
    """Append entry to friction.md. Usage: /log_friction <message>"""
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        await update.message.reply_text(
            "Usage: /log_friction <message>\n"
            "Exemple: /log_friction /brief lent ce matin (15s)"
        )
        return
    try:
        _append_log_entry("friction.md", text)
        await update.message.reply_text(f"OK logged to friction.md:\n  {text[:300]}")
    except Exception as e:
        await update.message.reply_text(f"Error writing friction.md: {e}")
