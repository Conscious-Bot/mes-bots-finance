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


def min_conviction() -> int:
    return cast(int, env("MIN_CONVICTION", 3, int))


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


def get_tier_breakdown():
    """Return dict with counts + per-sector breakdown for /tiers display."""
    cfg = load()
    universe = cfg.get("universe", {})
    return {
        "core": universe.get("core", {}),
        "watch_count": len(_flatten_section(universe.get("watch", []))),
        "extended": universe.get("extended", {}),
        "total": len(get_tickers("all")),
        "counts": {
            "core": len(get_tickers("core")),
            "watch": len(get_tickers("watch")),
            "extended": len(get_tickers("extended")),
        },
    }


def promote_ticker(ticker, new_tier):
    """Move ticker to a different tier. Returns (success_bool, message)."""
    global _config
    if new_tier not in ("core", "watch", "extended"):
        return False, f"Invalid tier '{new_tier}'. Use core/watch/extended."
    ticker = ticker.upper()
    cfg = load()
    universe = cfg.get("universe", {})
    old_tier = get_ticker_tier(ticker)
    if old_tier == new_tier:
        return False, f"{ticker} already in {new_tier}"
    # Remove from current location
    if old_tier:
        section = universe.get(old_tier)
        if isinstance(section, dict):
            for _cat, lst in section.items():
                if isinstance(lst, list) and ticker in lst:
                    lst.remove(ticker)
                    break
        elif isinstance(section, list) and ticker in section:
            section.remove(ticker)
    # Add to new tier
    target = universe.get(new_tier)
    if isinstance(target, dict):
        target.setdefault("promoted", []).append(ticker)
    elif isinstance(target, list):
        target.append(ticker)
    else:
        universe[new_tier] = [ticker]
    # Persist YAML
    import yaml as _yaml

    with open(ROOT / "config.yaml", "w") as f:
        _yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True, width=120)
    _config = None  # invalidate cache
    return True, f"{ticker}: {old_tier or 'none'} → {new_tier}"


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
