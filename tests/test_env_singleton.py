"""Tests Phase 1.1 absorption_roadmap — `shared/env.py` singleton typed.

Doctrine :
- Singleton survit aux re-imports (one instance).
- Defaults appliques quand env var absente.
- Cache stable entre acces successifs (lecture une fois).
- reset_cache() force re-read (rotation API key / tests).
- Required (anthropic_api_key) raise RuntimeError si missing.
- all_set() mask les secrets (no leak dans logs).
- Booleans tolerent "1"/"true"/"yes"/"on" insensitive + autres = False.
"""

from __future__ import annotations

import importlib

import pytest


def _reload_env(monkeypatch: pytest.MonkeyPatch):
    """Pattern : recharge shared.env en stubbing load_dotenv pour eviter
    que .env reel re-injecte des secrets pendant les tests."""
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    import shared.env
    monkeypatch.setattr(shared.env, "load_dotenv", lambda *a, **k: False, raising=False)
    importlib.reload(shared.env)
    return shared.env.env


def test_singleton_identity():
    """env access deux fois -> meme instance (pas un module-factory)."""
    import shared.env as mod
    a = mod.env
    b = mod.env
    assert a is b


def test_defaults_applied_when_unset(monkeypatch: pytest.MonkeyPatch):
    """Aucune env var set -> defaults documentes."""
    env = _reload_env(monkeypatch)
    for var in (
        "EDGAR_USER_AGENT",
        "FRED_API_KEY",
        "HEALTHCHECKS_J_DAY_URL",
        "LLM_COST_CAP_DISABLE",
        "LLM_COST_CAP_USD_24H",
        "PRESAGE_PORT",
        "PRESAGE_REFRESH",
        "TZ",
        "RESILIENCE_FALLBACK_ENABLED",
        "RESILIENCE_SHADOW_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)
    env.reset_cache()
    assert env.edgar_user_agent == "Olivier Legendre olegendre@gmail.com"
    assert env.fred_api_key == ""
    assert env.healthchecks_j_day_url == ""
    assert env.llm_cost_cap_disable is False
    assert env.llm_cost_cap_usd_24h == 10.0
    assert env.presage_port == 8000
    assert env.presage_refresh_seconds == 60
    assert env.timezone == "Europe/Paris"
    assert env.resilience_fallback_enabled is False
    assert env.resilience_shadow_enabled is False


def test_required_anthropic_raises_when_missing(monkeypatch: pytest.MonkeyPatch):
    """Required key absente -> RuntimeError au moment d'acces (fail-fast)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env = _reload_env(monkeypatch)
    env.reset_cache()
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY required"):
        _ = env.anthropic_api_key


def test_cache_is_sticky(monkeypatch: pytest.MonkeyPatch):
    """Une fois lue, la valeur reste cache meme si env change apres."""
    monkeypatch.setenv("EDGAR_USER_AGENT", "first@example.com")
    env = _reload_env(monkeypatch)
    env.reset_cache()
    assert env.edgar_user_agent == "first@example.com"
    monkeypatch.setenv("EDGAR_USER_AGENT", "second@example.com")
    assert env.edgar_user_agent == "first@example.com"  # cache


def test_reset_cache_forces_reread(monkeypatch: pytest.MonkeyPatch):
    """reset_cache() force re-read au prochain acces."""
    monkeypatch.setenv("FRED_API_KEY", "key_v1")
    env = _reload_env(monkeypatch)
    env.reset_cache()
    assert env.fred_api_key == "key_v1"
    monkeypatch.setenv("FRED_API_KEY", "key_v2")
    env.reset_cache()
    assert env.fred_api_key == "key_v2"


def test_int_parsing_fallback_on_invalid(monkeypatch: pytest.MonkeyPatch):
    """PRESAGE_PORT=garbage -> default 8000 (pas de crash)."""
    monkeypatch.setenv("PRESAGE_PORT", "not_an_int")
    monkeypatch.setenv("PRESAGE_REFRESH", "-also-not-")
    monkeypatch.setenv("LLM_COST_CAP_USD_24H", "bogus")
    env = _reload_env(monkeypatch)
    env.reset_cache()
    assert env.presage_port == 8000
    assert env.presage_refresh_seconds == 60
    assert env.llm_cost_cap_usd_24h == 10.0


def test_bool_truthy_variants(monkeypatch: pytest.MonkeyPatch):
    """Booleans : 1/true/yes/on insensitive."""
    env = _reload_env(monkeypatch)
    for truthy in ("1", "true", "TRUE", "yes", "YES", "on", "On"):
        monkeypatch.setenv("RESILIENCE_FALLBACK_ENABLED", truthy)
        env.reset_cache()
        assert env.resilience_fallback_enabled is True, f"{truthy!r} should be True"
    for falsy in ("0", "false", "no", "off", "", "maybe", "2"):
        monkeypatch.setenv("RESILIENCE_FALLBACK_ENABLED", falsy)
        env.reset_cache()
        assert env.resilience_fallback_enabled is False, f"{falsy!r} should be False"


def test_llm_cost_cap_disable_strict(monkeypatch: pytest.MonkeyPatch):
    """LLM_COST_CAP_DISABLE garde le contrat strict 'exactly 1' du legacy.

    Important : ne PAS elargir a yes/true/on -- l'override d'urgence doit
    rester volontaire et explicite (pas un setting accidentel)."""
    env = _reload_env(monkeypatch)
    monkeypatch.setenv("LLM_COST_CAP_DISABLE", "1")
    env.reset_cache()
    assert env.llm_cost_cap_disable is True
    for not_strict in ("true", "yes", "on", "0", ""):
        monkeypatch.setenv("LLM_COST_CAP_DISABLE", not_strict)
        env.reset_cache()
        assert env.llm_cost_cap_disable is False, f"{not_strict!r} must NOT disable cap"


def test_all_set_masks_secrets(monkeypatch: pytest.MonkeyPatch):
    """all_set() est safe pour logs : pas de secret en clair."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-supersecret1234567890")
    monkeypatch.setenv("FRED_API_KEY", "fredsecretkey42abc")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:ABCdef_botToken_secret")
    env = _reload_env(monkeypatch)
    env.reset_cache()
    s = env.all_set()
    assert s["anthropic_api_key"] is not None
    assert "supersecret" not in str(s["anthropic_api_key"])
    assert "..." in str(s["anthropic_api_key"])
    assert "fredsecretkey" not in str(s["fred_api_key"])
    assert "ABCdef_botToken_secret" not in str(s["telegram_bot_token"])


def test_all_set_returns_native_types_for_non_secrets(monkeypatch: pytest.MonkeyPatch):
    """all_set() expose les non-secrets en native (debugging facile)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("PRESAGE_PORT", "9000")
    monkeypatch.setenv("TZ", "UTC")
    env = _reload_env(monkeypatch)
    env.reset_cache()
    s = env.all_set()
    assert s["presage_port"] == 9000
    assert s["timezone"] == "UTC"
    assert isinstance(s["llm_cost_cap_disable"], bool)
