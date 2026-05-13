"""Wrapper Claude. Phase A2 — tier routing + cost logging + prefix caching."""
import json
import os
import sqlite3
import time
from pathlib import Path

from anthropic import Anthropic

from shared import config

_client = None
_DB_PATH = str(Path(__file__).resolve().parent.parent / "data" / "bot.db")

_TASK_TO_TIER = {
    'signal_scoring': 'extract',
    'why_matters': 'enrich',
    'synthesis': 'synthesize',
    'deep_analysis': 'synthesize',
}


def client():
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _resolve_model(tier=None, task=None):
    """Return (model_id, resolved_tier). tier overrides task."""
    cfg = config.load()
    if tier:
        m = cfg.get('tiers', {}).get(tier)
        if m:
            return m, tier
    if task:
        m = cfg.get('models', {}).get(task)
        if m:
            return m, _TASK_TO_TIER.get(task, 'enrich')
        return cfg.get('models', {}).get('synthesis'), 'enrich'
    return cfg.get('models', {}).get('synthesis'), 'enrich'


def _compute_cost(model, input_tokens, output_tokens, cached_tokens=0):
    cfg = config.load()
    pricing = cfg.get('pricing', {}).get(model)
    if not pricing:
        return None
    fresh_input = max(0, input_tokens - cached_tokens)
    in_cost = fresh_input * pricing.get('input', 0) / 1_000_000
    cache_cost = cached_tokens * pricing.get('cached_input', 0) / 1_000_000
    out_cost = output_tokens * pricing.get('output', 0) / 1_000_000
    return in_cost + cache_cost + out_cost


def _log_call(tier, model, task, input_tokens, output_tokens, cached_tokens,
              cost_usd, elapsed_ms, error=None):
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            "INSERT INTO llm_calls (tier, model, task, input_tokens, output_tokens, "
            "cached_tokens, cost_usd, elapsed_ms, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tier, model, task, input_tokens, output_tokens, cached_tokens,
             cost_usd, elapsed_ms, error)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def call(prompt: str, task: str | None = None, tier: str | None = None,
         max_tokens: int = 1500, system: str | None = None,
         cache_invariant: str | None = None) -> str:
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
    model, resolved_tier = _resolve_model(tier=tier, task=task)

    if cache_invariant:
        system_blocks = [
            {"type": "text", "text": cache_invariant,
             "cache_control": {"type": "ephemeral"}}
        ]
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
        text = msg.content[0].text.strip()
        usage = getattr(msg, 'usage', None)
        if usage:
            in_tok = getattr(usage, 'input_tokens', 0) or 0
            out_tok = getattr(usage, 'output_tokens', 0) or 0
            cached_tok = getattr(usage, 'cache_read_input_tokens', 0) or 0
        return text
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:200]}"
        raise
    finally:
        elapsed_ms = int((time.time() - t0) * 1000)
        cost = _compute_cost(model, in_tok, out_tok, cached_tok)
        _log_call(resolved_tier, model, task, in_tok, out_tok, cached_tok,
                  cost, elapsed_ms, error)


def call_json(prompt: str, task: str | None = None, tier: str | None = None,
              max_tokens: int = 800, system: str | None = None,
              cache_invariant: str | None = None) -> dict:
    """Like call() but expects + parses JSON response."""
    if tier is None and task is None:
        task = 'signal_scoring'
    raw = call(prompt + "\n\nRéponds UNIQUEMENT en JSON valide, sans markdown.",
               task=task, tier=tier, max_tokens=max_tokens,
               system=system, cache_invariant=cache_invariant)
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raw = call(prompt + "\n\nRetourne UNIQUEMENT un objet JSON valide.",
                   task=task, tier=tier, max_tokens=max_tokens,
                   system=system).strip()
        raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(raw)


def get_cost_summary(window_hours=24):
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
        return {'rows': [dict(r) for r in rows], 'errors': errors[0] if errors else 0}
    finally:
        conn.close()
