"""Decorator @scheduler_run_logged : wrap top-level crons avec scheduler_runs tracking.

Cure 14/06/2026 audit cron : `_safe_run` couvre chain steps inside morning/evening
chain, mais les top-level crons APScheduler (heartbeat, ingest_gmail, integrity_anchor,
etc.) n'ecrivaient pas dans scheduler_runs -> /system-health Cron sanity ne voyait
que ~3 jobs sur ~30.

Ce decorator wraps any callable (sync ou async) et :
1. Insert started row dans scheduler_runs au top
2. Update success + duration en fin OK
3. Update fail + error_msg si exception (puis re-raise pour ne pas masquer)

Silent-miss strict sur les writes DB : si scheduler_runs indispo, le cron tourne
quand meme (observabilite infra doit jamais casser le run observe).

Usage :
    @scheduler_run_logged("heartbeat")
    async def heartbeat():
        ...
"""
from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable


def scheduler_run_logged(slug: str | None = None) -> Callable:
    """Decorator factory. slug = identifier dans scheduler_runs (default = fn name)."""
    def decorator(fn: Callable) -> Callable:
        _slug = slug or fn.__name__

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                run_id = None
                t0 = time.monotonic()
                try:
                    from shared.storage import insert_scheduler_run_start
                    run_id = insert_scheduler_run_start(_slug)
                except Exception:
                    pass
                try:
                    result = await fn(*args, **kwargs)
                    try:
                        from shared.storage import update_scheduler_run_end
                        update_scheduler_run_end(run_id, "success", time.monotonic() - t0)
                    except Exception:
                        pass
                    return result
                except Exception as e:
                    try:
                        from shared.storage import update_scheduler_run_end
                        update_scheduler_run_end(
                            run_id, "fail", time.monotonic() - t0,
                            f"{type(e).__name__}: {e}",
                        )
                    except Exception:
                        pass
                    raise
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args, **kwargs):
                run_id = None
                t0 = time.monotonic()
                try:
                    from shared.storage import insert_scheduler_run_start
                    run_id = insert_scheduler_run_start(_slug)
                except Exception:
                    pass
                try:
                    result = fn(*args, **kwargs)
                    try:
                        from shared.storage import update_scheduler_run_end
                        update_scheduler_run_end(run_id, "success", time.monotonic() - t0)
                    except Exception:
                        pass
                    return result
                except Exception as e:
                    try:
                        from shared.storage import update_scheduler_run_end
                        update_scheduler_run_end(
                            run_id, "fail", time.monotonic() - t0,
                            f"{type(e).__name__}: {e}",
                        )
                    except Exception:
                        pass
                    raise
            return sync_wrapper

    return decorator
