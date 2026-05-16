"""Common helpers shared across bot/handlers/* modules.

Avoids duplicate top-level definitions and provides Telegram-safe
text formatting (post lesson from /journal_audit Markdown bug 69e70c1).
"""
from __future__ import annotations

from pathlib import Path

__all__ = ["db_path", "config_path", "telegram_safe"]


def db_path() -> Path:
    """Resolve repo_root/data/bot.db. Single source of truth."""
    return Path(__file__).resolve().parent.parent.parent / "data" / "bot.db"


def config_path() -> Path:
    """Resolve repo_root/config.yaml."""
    return Path(__file__).resolve().parent.parent.parent / "config.yaml"


_MD_CHARS = ("_", "*", "[", "]", "`")
_BACKSLASH = chr(92)


def telegram_safe(text: str) -> str:
    """Escape Telegram Markdown special chars to prevent parser crash.

    Strategy: prepend backslash before each of _, *, [, ], `. Use on dynamic
    content (DB strings, LLM outputs) before reply_text with parse_mode=Markdown.
    For plain-text output, this is unnecessary.

    Uses str.replace chain (no regex) to avoid backref escaping pitfalls.
    """
    if not text:
        return ""
    out = text
    for ch in _MD_CHARS:
        out = out.replace(ch, _BACKSLASH + ch)
    return out
