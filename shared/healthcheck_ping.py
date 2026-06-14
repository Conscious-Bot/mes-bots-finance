"""healthchecks.io ping helper for cron observability.

Pattern : chaque cron critique call ping(slug) à la fin de son run. Si
aucun ping en N min (configurable côté healthchecks.io UI), le service
envoie un email/SMS/Telegram alerte. Cette voie attrape les modes
"cron silently dead" (cf memory uptime case-bug postmortem 2026-05-14).

Setup une fois :
  1. Free signup https://healthchecks.io (20 checks free tier)
  2. Créer 1 check par cron critique (morning_chain, j_day_batch,
     group_cap_check, drift_detector, lock_in_resolution_check)
  3. Récupérer l'UUID par check
  4. Add to .env : HEALTHCHECKS_PROJECT_URL=https://hc-ping.com/<project_uuid>
     OR per-check : HC_MORNING_CHAIN=https://hc-ping.com/<uuid_morning>
  5. Dans chaque cron : `from shared.healthcheck_ping import ping ;
     ping("morning_chain")` à la fin

Discipline : ping APRES succès, jamais avant. Sinon on rate les
exceptions silencieuses (cf memory feedback_red_team_verify_before_assert).
"""
from __future__ import annotations

import os
import urllib.request

# Map slug → env var name (overridable per-slug, sinon fallback project URL + slug)
SLUG_ENV_OVERRIDES = {
    "morning_chain": "HC_MORNING_CHAIN",
    "j_day_batch": "HC_J_DAY_BATCH",
    "group_cap_check": "HC_GROUP_CAP_CHECK",
    "drift_detector": "HC_DRIFT_DETECTOR",
    "lock_in_resolution_check": "HC_LOCK_IN_RESOLUTION",
}


def _url_for(slug: str) -> str | None:
    """Resolve ping URL : per-slug env var first, else project URL + /slug."""
    override = SLUG_ENV_OVERRIDES.get(slug)
    if override and (u := os.environ.get(override)):
        return u
    project = os.environ.get("HEALTHCHECKS_PROJECT_URL")
    if project:
        return f"{project.rstrip('/')}/{slug}"
    return None


def ping(slug: str, status: str = "success", payload: str | None = None) -> bool:
    """Send heartbeat ping.

    status: 'success' (default), 'start', 'fail'.
    payload: optional body (e.g. error message for fail status).

    Returns True if ping succeeded, False if URL missing or network error.
    Never raises — observability infra failure must not break the cron itself.
    """
    url = _url_for(slug)
    if not url:
        return False
    if status == "start":
        url = f"{url}/start"
    elif status == "fail":
        url = f"{url}/fail"
    try:
        data = payload.encode("utf-8") if payload else None
        with urllib.request.urlopen(url, data=data, timeout=5) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def ping_fail(slug: str, error: str) -> bool:
    """Convenience : ping with fail status + error message body."""
    return ping(slug, status="fail", payload=error[:1024])


if __name__ == "__main__":
    import sys
    slug = sys.argv[1] if len(sys.argv) > 1 else "test"
    ok = ping(slug)
    print(f"  ping({slug}) → {'OK' if ok else 'FAIL'} (url resolved : {_url_for(slug)})")
