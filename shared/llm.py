"""Wrapper Claude. Phase A2 — tier routing + cost logging + prefix caching."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, cast

from anthropic import Anthropic

from shared import config
from shared.env import env

_client = None
_DB_PATH = str(Path(__file__).resolve().parent.parent / "data" / "bot.db")

_TASK_TO_TIER = {
    "signal_scoring": "extract",
    "why_matters": "enrich",
    "synthesis": "synthesize",
    "deep_analysis": "synthesize",
}


def client() -> Any:  # anthropic.Anthropic
    global _client
    if _client is None:
        _client = Anthropic(api_key=env.anthropic_api_key)
    return _client


def _resolve_model(tier: str | None = None, task: str | None = None) -> tuple[str, str]:
    """Return (model_id, resolved_tier). tier overrides task.

    Phase B (#93) : si _should_downgrade_to_haiku() (cost cap soft a 80%),
    force route via 'extract' tier (Haiku) quelque soit le tier/task demande.
    Marker resolved_tier = '<orig>+haiku_softcap' pour audit trail.
    """
    cfg = config.load()
    if tier:
        m = cfg.get("tiers", {}).get(tier)
        if m:
            chosen, resolved_tier = m, tier
        else:
            chosen, resolved_tier = cfg.get("models", {}).get("synthesis"), "enrich"
    elif task:
        m = cfg.get("models", {}).get(task)
        if m:
            chosen, resolved_tier = m, _TASK_TO_TIER.get(task, "enrich")
        else:
            chosen, resolved_tier = cfg.get("models", {}).get("synthesis"), "enrich"
    else:
        chosen, resolved_tier = cfg.get("models", {}).get("synthesis"), "enrich"

    # Phase B : downgrade auto a Haiku si cost cap soft (80%) franchi.
    # Effet boundary : la decision se prend a chaque call (pct re-evalue),
    # donc si l'on retombe sous 80%, le downgrade se leve automatiquement.
    if _should_downgrade_to_haiku() and resolved_tier != "extract":
        haiku = cfg.get("tiers", {}).get("extract")
        if haiku and haiku != chosen:
            return haiku, f"{resolved_tier}+haiku_softcap"
    return chosen, resolved_tier


def _compute_cost(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    cfg = config.load()
    pricing = cfg.get("pricing", {}).get(model)
    if not pricing:
        return 0.0
    fresh_input = max(0, input_tokens - cached_tokens)
    in_cost = fresh_input * pricing.get("input", 0) / 1_000_000
    cache_cost = cached_tokens * pricing.get("cached_input", 0) / 1_000_000
    out_cost = output_tokens * pricing.get("output", 0) / 1_000_000
    return float(in_cost + cache_cost + out_cost)


def _log_call(tier, model, task, input_tokens, output_tokens, cached_tokens, cost_usd, elapsed_ms, error=None):
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            "INSERT INTO llm_calls (tier, model, task, input_tokens, output_tokens, "
            "cached_tokens, cost_usd, elapsed_ms, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tier, model, task, input_tokens, output_tokens, cached_tokens, cost_usd, elapsed_ms, error),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# #87 (02/06) -- Cost cap mitigation vendor lock Anthropic.
# Default 10 USD/24h. Override via env LLM_COST_CAP_USD_24H. Bypass d'urgence
# LLM_COST_CAP_DISABLE=1. Soft warn a 80%, hard raise a 100%.
_COST_CAP_LAST_WARNED = 0.0


class CostCapExceeded(RuntimeError):
    """Raised quand la consommation LLM 24h depasse LLM_COST_CAP_USD_24H.

    Mitigation vendor lock Anthropic : limite l'exposition financiere si
    cron runaway ou bug d'infinite-retry. Override emergency via env
    LLM_COST_CAP_DISABLE=1.
    """


class LLMUnavailableError(RuntimeError):
    """#93 Composant A : LLM provider indisponible (credit_exhausted ou rate_limited).

    Distincte de CostCapExceeded (decision locale) : ici c'est l'UPSTREAM
    qui dit non. Les consommateurs doivent attraper cette exception
    explicitement, logger en ERROR, et marquer l'item pending_llm.

    Spec user 03/06 : "JAMAIS default=0.5, JAMAIS drop silencieux
    (lecon tennis-bot). Le bug '28/28 failed en silence' doit devenir
    impossible."

    Attributes:
        reason: 'credit_exhausted' (400 + credit balance too low) ou
                'rate_limited' (429).
        retry_after: seconds si serveur a renvoye Retry-After (429), sinon None.
        upstream_msg: message brut de l'API pour debug.
    """

    def __init__(self, reason: str, upstream_msg: str = "", retry_after: int | None = None):
        self.reason = reason
        self.retry_after = retry_after
        self.upstream_msg = upstream_msg
        super().__init__(f"LLM unavailable ({reason}): {upstream_msg[:200]}")


def set_llm_status(
    status: str,
    reason: str | None = None,
    active_model: str | None = None,
) -> None:
    """Ecrit l'etat global du LLM dans bot_state.json (visible par dashboard / Telegram).

    Etats canoniques :
    - 'healthy'  : derniere call() reussie, pas de signe degradation.
    - 'degraded' : LLMUnavailableError recente OU cost_cap_soft (Haiku auto) OU
                   cost_cap_hard (CostCapExceeded). Le `reason` discrimine.
    - 'down'     : persistance prolongee. 1B fait debounce + bascule sur rule scorer.

    Phase B : transition fire Telegram alert exactly once (set_llm_status est
    no-op si statut+reason identiques -> debounce naturel).

    active_model : 'haiku' / 'sonnet' / 'opus' / None. Surface dashboard badge.
    """
    from datetime import UTC, datetime

    from shared import storage

    try:
        s = storage.load_state()
    except Exception:
        s = {}
    state_initialized = "llm_status" in s
    prev_status = s.get("llm_status", "healthy")
    prev_reason = s.get("llm_status_reason")
    prev_active_model = s.get("llm_active_model")
    # Debounce : pas de re-ecriture si rien ne change. MAIS toujours ecrire la
    # 1ere fois (state_initialized=False) sinon le 1er set_llm_status sur
    # bot_state vierge serait silencieusement perdu (bug test_active_model).
    if (
        state_initialized
        and prev_status == status
        and prev_reason == reason
        and (active_model is None or active_model == prev_active_model)
    ):
        return  # no-op (debounce write + alert spam)

    s["llm_status"] = status
    s["llm_status_since"] = datetime.now(UTC).isoformat()
    s["llm_status_reason"] = reason
    if active_model is not None:
        s["llm_active_model"] = active_model
    import contextlib
    with contextlib.suppress(Exception):
        storage.save_state(s)  # fail-open : ne pas casser l'appel LLM si bot_state ecriture echoue

    # Telegram alert sur transition (Phase B). Fail-safe : si notify casse,
    # l'etat reste sauvegarde -- on n'echange pas la verite contre le bruit.
    with contextlib.suppress(Exception):
        _maybe_notify_transition(prev_status, prev_reason, status, reason)


def _maybe_notify_transition(
    prev_status: str,
    _prev_reason: str | None,
    new_status: str,
    new_reason: str | None,
) -> None:
    """Fire Telegram alert sur transition LLM significative.

    Couvre : healthy -> degraded (premier signe de degradation),
             degraded -> down (escalade resilience),
             {degraded,down} -> healthy (recovery).
    Pas d'alert sur degraded->degraded meme avec reason different (un mode
    degrade reste degrade ; les details vont dans le log structure).
    """
    from shared import notify

    transitions_to_alert = {
        ("healthy", "degraded"),
        ("healthy", "down"),
        ("degraded", "down"),
        ("degraded", "healthy"),
        ("down", "healthy"),
        ("down", "degraded"),
    }
    key = (prev_status, new_status)
    if key not in transitions_to_alert:
        return

    icons = {"healthy": "✅", "degraded": "⚠️", "down": "🚨"}
    icon_new = icons.get(new_status, "•")
    if new_status == "healthy":
        msg = f"{icon_new} LLM recovered : {prev_status} -> healthy"
    else:
        reason_str = new_reason or "?"
        msg = (
            f"{icon_new} LLM {new_status} ({reason_str}) -- prev {prev_status}. "
            f"Voir dashboard badge + tail dashboard/serve.log."
        )
    notify.send_text(msg)


def get_llm_status() -> dict[str, Any]:
    """Retourne {status, since, reason, active_model}. Defaut healthy si jamais ecrit."""
    from shared import storage

    try:
        s = storage.load_state()
    except Exception:
        s = {}
    return {
        "status": s.get("llm_status", "healthy"),
        "since": s.get("llm_status_since"),
        "reason": s.get("llm_status_reason"),
        "active_model": s.get("llm_active_model"),
    }


def _classify_anthropic_error(e: Exception) -> LLMUnavailableError | None:
    """Detecte credit_exhausted / rate_limited dans une exception Anthropic.

    Strategie : status_code first (le plus stable), fallback sur substring
    match du message (Anthropic peut renvoyer 400 avec un message specifique
    "credit balance too low" pour distinguer du 400-malformed-request).

    Returns LLMUnavailableError mappe, ou None si l'exception n'est PAS
    une indispo upstream (laisser remonter telle quelle : parse, network,
    autres).
    """
    msg = str(e)
    status = getattr(e, "status_code", None)
    if status is None:
        # anthropic SDK : APIError.response.status_code
        resp = getattr(e, "response", None)
        if resp is not None:
            status = getattr(resp, "status_code", None) or getattr(resp, "status", None)
    msg_low = msg.lower()
    if "credit balance is too low" in msg_low or "credit balance too low" in msg_low:
        return LLMUnavailableError("credit_exhausted", upstream_msg=msg)
    if status == 429 or "rate limit" in msg_low or "too many requests" in msg_low:
        retry_after = None
        for token in msg.split():
            if token.isdigit() and 1 <= int(token) <= 86400:
                retry_after = int(token)
                break
        return LLMUnavailableError("rate_limited", upstream_msg=msg, retry_after=retry_after)
    return None


def _get_cost_usage_24h() -> float:
    """Cost USD cumule sur les 24 dernieres heures depuis llm_calls."""
    try:
        conn = sqlite3.connect(_DB_PATH)
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls "
            "WHERE created_at > datetime('now', '-24 hours')"
        ).fetchone()
        conn.close()
        return float(row[0]) if row else 0.0
    except Exception:
        return 0.0  # fail-open : ne pas bloquer si DB indispo


_COST_CAP_SOFT_PCT = 0.8


def _model_short_name(model_id: str | None) -> str | None:
    """'claude-haiku-4-5-...' -> 'haiku'. Pour dashboard badge + state."""
    if not model_id:
        return None
    m = model_id.lower()
    if "haiku" in m:
        return "haiku"
    if "sonnet" in m:
        return "sonnet"
    if "opus" in m:
        return "opus"
    return model_id


def _cost_cap_config() -> tuple[float, bool]:
    """Returns (cap_usd_24h, disabled). disabled=True -> bypass.

    Reset cache au call : permet tests qui monkeypatch LLM_COST_CAP_DISABLE
    de voir l'override sans avoir a reload le module."""
    env.reset_cache()
    if env.llm_cost_cap_disable:
        return 0.0, True
    cap = env.llm_cost_cap_usd_24h
    return cap, cap <= 0


def _get_cost_pct() -> float | None:
    """Returns used/cap dans [0, inf) ou None si cap disabled."""
    cap, disabled = _cost_cap_config()
    if disabled:
        return None
    return _get_cost_usage_24h() / cap


def _should_downgrade_to_haiku() -> bool:
    """True si cost pct >= 80% (cap soft, downgrade auto Haiku)."""
    pct = _get_cost_pct()
    return pct is not None and pct >= _COST_CAP_SOFT_PCT


def _check_cost_cap() -> None:
    """Check 24h cost vs cap. Soft-warn + Haiku-downgrade a 80%, raise a 100%."""
    cap, disabled = _cost_cap_config()
    if disabled:
        return
    used = _get_cost_usage_24h()
    if used >= cap:
        # Phase B : set status AVANT de raise pour que dashboard badge + Telegram
        # capturent le hard-cap. Sinon CostCapExceeded remonte silencieusement
        # cote consumer et seul le log structure le voit.
        set_llm_status("degraded", reason="cost_cap_hard", active_model=None)
        raise CostCapExceeded(
            f"LLM cost cap atteint : {used:.2f} USD / {cap:.2f} USD sur "
            "24h. Override LLM_COST_CAP_DISABLE=1 si intentionnel."
        )
    # Soft warn : log une seule fois par tranche de 10% au-dessus de 80%
    global _COST_CAP_LAST_WARNED
    pct = used / cap
    if pct >= _COST_CAP_SOFT_PCT and pct - _COST_CAP_LAST_WARNED >= 0.1:
        import logging
        logging.getLogger("shared.llm").warning(
            f"LLM cost approche cap : {used:.2f}/{cap:.2f} USD ({pct * 100:.0f}%) "
            "-- Haiku auto active"
        )
        _COST_CAP_LAST_WARNED = pct


def call(
    prompt: str,
    task: str | None = None,
    tier: str | None = None,
    max_tokens: int = 1500,
    system: str | None = None,
    cache_invariant: str | None = None,
) -> str:
    """Phase A2: tier-routed Claude call with optional prefix caching.

    Args:
        prompt: User prompt
        task: Legacy task name (signal_scoring, synthesis, deep_analysis, why_matters)
        tier: Explicit tier ('extract', 'enrich', 'synthesize'). Overrides task.
        max_tokens: Max output tokens
        system: System prompt (string)
        cache_invariant: Stable prefix content (regime, watchlist, credibility state...).
                        Marked cache_control:ephemeral for 5min prefix caching.
                        Must be >=1024 tokens to actually cache.
    Returns: text response (stripped)
    """
    _check_cost_cap()  # #87 hard stop si cap atteint
    model, resolved_tier = _resolve_model(tier=tier, task=task)

    if cache_invariant:
        system_blocks = [{"type": "text", "text": cache_invariant, "cache_control": {"type": "ephemeral"}}]
        if system:
            system_blocks.append({"type": "text", "text": system})
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": [{"role": "user", "content": prompt}],
        }
    else:
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

    t0 = time.time()
    error = None
    text = ""
    in_tok = out_tok = cached_tok = 0
    try:
        msg = client().messages.create(**kwargs)
        text = cast(str, msg.content[0].text.strip())
        usage = getattr(msg, "usage", None)
        if usage:
            in_tok = getattr(usage, "input_tokens", 0) or 0
            out_tok = getattr(usage, "output_tokens", 0) or 0
            cached_tok = getattr(usage, "cache_read_input_tokens", 0) or 0
        # Phase B : si downgrade Haiku actif, status reste degraded (cost_cap_soft)
        # meme si l'appel reussit. La qualite est sous l'ideal -> dashboard montre.
        if "+haiku_softcap" in resolved_tier:
            set_llm_status("degraded", reason="cost_cap_soft", active_model="haiku")
        else:
            set_llm_status("healthy", reason=None, active_model=_model_short_name(model))
        return text
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:200]}"
        unavailable = _classify_anthropic_error(e)
        if unavailable is not None:
            set_llm_status("degraded", reason=unavailable.reason, active_model=None)
            raise unavailable from e
        raise
    finally:
        elapsed_ms = int((time.time() - t0) * 1000)
        cost = _compute_cost(model, in_tok, out_tok, cached_tok)
        _log_call(resolved_tier, model, task, in_tok, out_tok, cached_tok, cost, elapsed_ms, error)


def call_multiturn(
    messages: list[dict],
    task: str | None = None,
    tier: str | None = None,
    max_tokens: int = 1500,
    system: str | None = None,
    cache_invariant: str | None = None,
) -> str:
    """Multi-turn variant of call() — used by dashboard chat surface (Sprint 7+).

    messages : [{role: 'user'|'assistant', content: str}, ...] — alternating turns.
    cache_invariant : marked cache_control:ephemeral on system block (5min TTL).
    Returns text response (stripped).
    """
    _check_cost_cap()  # #87 hard stop si cap atteint
    model, resolved_tier = _resolve_model(tier=tier, task=task)
    if cache_invariant:
        system_blocks = [{"type": "text", "text": cache_invariant, "cache_control": {"type": "ephemeral"}}]
        if system:
            system_blocks.append({"type": "text", "text": system})
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": messages,
        }
    else:
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

    t0 = time.time()
    error = None
    text = ""
    in_tok = out_tok = cached_tok = 0
    try:
        msg = client().messages.create(**kwargs)
        text = cast(str, msg.content[0].text.strip())
        usage = getattr(msg, "usage", None)
        if usage:
            in_tok = getattr(usage, "input_tokens", 0) or 0
            out_tok = getattr(usage, "output_tokens", 0) or 0
            cached_tok = getattr(usage, "cache_read_input_tokens", 0) or 0
        # Phase B : si downgrade Haiku actif, status reste degraded (cost_cap_soft)
        # meme si l'appel reussit. La qualite est sous l'ideal -> dashboard montre.
        if "+haiku_softcap" in resolved_tier:
            set_llm_status("degraded", reason="cost_cap_soft", active_model="haiku")
        else:
            set_llm_status("healthy", reason=None, active_model=_model_short_name(model))
        return text
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:200]}"
        unavailable = _classify_anthropic_error(e)
        if unavailable is not None:
            set_llm_status("degraded", reason=unavailable.reason, active_model=None)
            raise unavailable from e
        raise
    finally:
        elapsed_ms = int((time.time() - t0) * 1000)
        cost = _compute_cost(model, in_tok, out_tok, cached_tok)
        _log_call(resolved_tier, model, task, in_tok, out_tok, cached_tok, cost, elapsed_ms, error)


def call_json(
    prompt: str,
    task: str | None = None,
    tier: str | None = None,
    max_tokens: int = 800,
    system: str | None = None,
    cache_invariant: str | None = None,
) -> dict:
    """Like call() but expects + parses JSON response."""
    if tier is None and task is None:
        task = "signal_scoring"
    raw = call(
        prompt + "\n\nRéponds UNIQUEMENT en JSON valide, sans markdown.",
        task=task,
        tier=tier,
        max_tokens=max_tokens,
        system=system,
        cache_invariant=cache_invariant,
    )
    raw = raw.strip()
    # Strip markdown code fences (was using lstrip with multi-char, fragile)
    raw = raw.removeprefix("```json").removeprefix("```")
    raw = raw.removesuffix("```").strip()
    try:
        return cast(dict[str, Any], json.loads(raw))
    except json.JSONDecodeError:
        raw = call(
            prompt + "\n\nRetourne UNIQUEMENT un objet JSON valide.",
            task=task,
            tier=tier,
            max_tokens=max_tokens,
            system=system,
        ).strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return cast(dict[str, Any], json.loads(raw))


def get_cost_summary(window_hours: int = 24) -> dict[str, Any]:
    """Aggregate cost stats by tier+model for last N hours."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(f"""
            SELECT tier, model, COUNT(*) AS n_calls,
                   SUM(input_tokens) AS in_t, SUM(output_tokens) AS out_t,
                   SUM(cached_tokens) AS cached_t, SUM(cost_usd) AS cost,
                   AVG(elapsed_ms) AS avg_ms
            FROM llm_calls
            WHERE datetime(created_at) >= datetime('now', '-{int(window_hours)} hours')
              AND error IS NULL
            GROUP BY tier, model
            ORDER BY cost DESC NULLS LAST
        """).fetchall()
        errors = conn.execute(f"""
            SELECT COUNT(*) AS n FROM llm_calls
            WHERE datetime(created_at) >= datetime('now', '-{int(window_hours)} hours')
              AND error IS NOT NULL
        """).fetchone()
        return {"rows": [dict(r) for r in rows], "errors": errors[0] if errors else 0}
    finally:
        conn.close()
