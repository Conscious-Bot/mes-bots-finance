"""Loading + validation config.yaml + .env"""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

_config: dict[str, Any] | None = None


def load() -> dict[str, Any]:
    global _config
    if _config is None:
        _config = cast(dict[str, Any], yaml.safe_load((ROOT / "config.yaml").read_text()))
    return _config


def get() -> dict[str, Any]:
    """Alias canonique : returns merged config dict. Cf risk/kill_switch.py (26/06)."""
    return load()


class ConfigurationError(Exception):
    """Raised when a config section is missing or invalid."""


def env(key: str, default: Any = None, cast: Callable[[Any], Any] = str) -> Any:
    v = os.environ.get(key, default)
    if v is None:
        return None
    try:
        return cast(v) if cast is not bool else str(v).lower() in ("true", "1", "yes")
    except Exception:
        return default


def capital() -> float:
    return cast(float, env("CAPITAL", 10000, float))


def paper_only() -> bool:
    return cast(bool, env("PAPER_ONLY", "true", bool))


def telegram_chat_id() -> int:
    return cast(int, env("TELEGRAM_CHAT_ID", 0, int))


def telegram_token() -> str:
    return cast(str, env("TELEGRAM_BOT_TOKEN"))


# ============ Tier-aware accessors (Phase Tickers Tiered) ============


def _flatten_section(section):
    if isinstance(section, dict):
        out = []
        for v in section.values():
            if isinstance(v, list):
                out.extend(v)
        return out
    if isinstance(section, list):
        return list(section)
    return []


def get_tickers(tier="all"):
    """Return list of tickers for a tier.

    tier: 'core' | 'watch' | 'extended' | 'core+watch' | 'all'
    """
    cfg = load()
    universe = cfg.get("universe", {})
    core = _flatten_section(universe.get("core", {}))
    watch = _flatten_section(universe.get("watch", {}))
    extended = _flatten_section(universe.get("extended", {}))
    if tier == "core":
        return core
    if tier == "watch":
        return watch
    if tier == "extended":
        return extended
    if tier == "core+watch":
        return core + watch
    return core + watch + extended


def get_ticker_tier(ticker):
    """Return 'core' | 'watch' | 'extended' | None."""
    t = (ticker or "").upper()
    if not t:
        return None
    if t in get_tickers("core"):
        return "core"
    if t in get_tickers("watch"):
        return "watch"
    if t in get_tickers("extended"):
        return "extended"
    return None


# Backward-compat lazy module attributes
def __getattr__(name):
    if name == "WATCHLIST":
        return get_tickers("core+watch")
    if name == "INSIDER_TICKERS":
        return get_tickers("core")
    raise AttributeError(f"module 'shared.config' has no attribute {name!r}")


# Phase Solidification P2 — Cost budget (per FICHE_TECHNIQUE)
# Moved from bot/main.py 2026-05-16 to break circular import after chunk 2 extract.
# Consumed by: bot/handlers/observability.py (/cost_trajectory) + bot/main.py (weekly_cost_summary_job cron)
BUDGET_MONTHLY_USD = 50.0
