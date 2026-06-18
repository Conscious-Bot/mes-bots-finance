"""Source canonique unique des env vars PRESAGE.

Phase 1.1 absorption_roadmap (07/06). Pattern OpenBB
`openbb_platform/core/openbb_core/env.py` : singleton typed avec properties
+ defaults documentes inline + cache sur premier acces.

Avant ce fichier : ~14 `os.environ.get(...)` eparpilles dans 7 fichiers,
formats varies (string/int/bool), defaults dupliques (ex `EDGAR_USER_AGENT`
default ecrit 2 fois identique a la lettre pres mais dans 2 fichiers).

Apres : import `from shared.env import env` puis `env.anthropic_api_key`.

Co-existe avec `shared/config.py` :
- `shared/config.py` = config.yaml (parametres business : caps, thresholds,
  univers, etc.)
- `shared/env.py` = env vars (secrets, infra, runtime tuning)

Invariants
----------
- Bias model : pas de read at-rest. cached_property valeur lue au premier
  acces, conservee jusqu'a reset_cache(). Si l'env var change apres boot,
  appeler reset_cache() ou redemarrer.
- Threat model : ANTHROPIC_API_KEY required, raise RuntimeError si missing
  au moment d'acces (fail-fast, pas de fallback silencieux). Autres vars
  ont defaults documentes.
- Failure mode : .env file absent = OK tant que ENV vars sont set au shell.
  Si rien set, defaults applicables sauf anthropic_api_key qui crash.
"""

from __future__ import annotations

import os
from functools import cached_property
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")


class _Env:
    """Singleton env vars typed. Cached sur premier acces.

    KNOWN-GAP : pas de validation par regex / format strict sur les strings
    (ex EDGAR_USER_AGENT). Suffisant tant que le contenu est trust-controlled
    (Olivier definit son .env).
    """

    # === LLM (cascade Haiku/Sonnet/Opus + budget) ===

    @cached_property
    def anthropic_api_key(self) -> str:
        """Required. Source canonique unique pour Anthropic SDK client."""
        v = os.environ.get("ANTHROPIC_API_KEY")
        if not v:
            raise RuntimeError(
                "ANTHROPIC_API_KEY required. Set in .env at repo root "
                "or export in shell before launching bot/serve."
            )
        return v

    @cached_property
    def llm_cost_cap_disable(self) -> bool:
        """Override d'urgence pour bypass le hard cap 24h. Default False."""
        return os.environ.get("LLM_COST_CAP_DISABLE", "0") == "1"

    @cached_property
    def llm_cost_cap_usd_24h(self) -> float:
        """Budget LLM 24h en USD. Default 10.0. Hit cap = LLM down propre."""
        try:
            return float(os.environ.get("LLM_COST_CAP_USD_24H", "10.0"))
        except ValueError:
            return 10.0

    # === Telegram (canal user-facing) ===

    @cached_property
    def telegram_bot_token(self) -> str | None:
        """Token bot Telegram. None si pas set = bot inactive (mode dev local)."""
        return os.environ.get("TELEGRAM_BOT_TOKEN")

    @cached_property
    def telegram_chat_id(self) -> int:
        """Chat ID destinataire des messages bot. 0 = pas configure."""
        try:
            return int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
        except ValueError:
            return 0

    # === Data sources externes ===

    @cached_property
    def edgar_user_agent(self) -> str:
        """SEC EDGAR exige User-Agent identifiable (fair-access policy)."""
        return os.environ.get(
            "EDGAR_USER_AGENT", "Olivier Legendre olegendre@gmail.com"
        )

    @cached_property
    def fred_api_key(self) -> str:
        """FRED API key. Vide = endpoints sans-key utilisables seulement."""
        return os.environ.get("FRED_API_KEY", "").strip()

    # === Healthchecks (dead-man's-switch crons) ===

    @cached_property
    def healthchecks_j_day_url(self) -> str:
        """Ping URL pour J-day batch resolution. Vide = pas de ping."""
        return os.environ.get("HEALTHCHECKS_J_DAY_URL", "").strip()

    # === Dashboard serve.py ===

    @cached_property
    def presage_port(self) -> int:
        """Port HTTP serve.py. Default 8000."""
        try:
            return int(os.environ.get("PRESAGE_PORT", "8000"))
        except ValueError:
            return 8000

    @cached_property
    def presage_refresh_seconds(self) -> int:
        """Intervalle regen dashboard.html. Default 300s (5 min) post-audit 5.
        Avant 60s causait perception "valeurs bougent toutes seules" (auditor:
        "broker total est passé de 43,860 à 44,056 entre deux affichages" =
        yfinance jitter intra-cache-window. Override env PRESAGE_REFRESH=60
        pour dev iteration rapide. 5 min = trade-off perception fiabilite vs
        live freshness sur outil de discipline."""
        try:
            return int(os.environ.get("PRESAGE_REFRESH", "300"))
        except ValueError:
            return 300

    # === Scheduling ===

    @cached_property
    def timezone(self) -> str:
        """APScheduler timezone. Default Europe/Paris."""
        return os.environ.get("TZ", "Europe/Paris")

    # === Feature flags (resilience opt-ins, default OFF) ===

    @cached_property
    def resilience_fallback_enabled(self) -> bool:
        """Routing fallback rule_v1 quand LLMUnavailableError (scoring_orchestrator).
        Default OFF tant que rule_v1_fallback pas valide en calibration."""
        return os.environ.get("RESILIENCE_FALLBACK_ENABLED", "").strip().lower() in (
            "1", "true", "yes", "on"
        )

    @cached_property
    def resilience_shadow_enabled(self) -> bool:
        """Shadow pair LLM + rule_v1_shadow challenger (ADR 014). Default OFF."""
        return os.environ.get("RESILIENCE_SHADOW_ENABLED", "").strip().lower() in (
            "1", "true", "yes", "on"
        )

    # === API utility ===

    def reset_cache(self) -> None:
        """Force re-read au prochain acces. Pour tests + edge case manuel
        (ex : rotation API key sans restart process)."""
        cls = type(self)
        for attr_name, attr in list(cls.__dict__.items()):
            if isinstance(attr, cached_property):
                self.__dict__.pop(attr_name, None)

    def all_set(self) -> dict[str, object]:
        """Dump complet (debugging /healthz extension). Mask secrets."""
        def _mask(s: object) -> object:
            if not isinstance(s, str) or len(s) < 8:
                return s
            return s[:4] + "..." + s[-2:]
        try:
            return {
                "anthropic_api_key": _mask(self.anthropic_api_key) if os.environ.get("ANTHROPIC_API_KEY") else None,
                "llm_cost_cap_disable": self.llm_cost_cap_disable,
                "llm_cost_cap_usd_24h": self.llm_cost_cap_usd_24h,
                "telegram_bot_token": _mask(self.telegram_bot_token) if self.telegram_bot_token else None,
                "telegram_chat_id": self.telegram_chat_id,
                "edgar_user_agent": self.edgar_user_agent,
                "fred_api_key": _mask(self.fred_api_key) if self.fred_api_key else "",
                "healthchecks_j_day_url": _mask(self.healthchecks_j_day_url) if self.healthchecks_j_day_url else "",
                "presage_port": self.presage_port,
                "presage_refresh_seconds": self.presage_refresh_seconds,
                "timezone": self.timezone,
                "resilience_fallback_enabled": self.resilience_fallback_enabled,
                "resilience_shadow_enabled": self.resilience_shadow_enabled,
            }
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}


# Singleton exposé. Import : `from shared.env import env`
env = _Env()
