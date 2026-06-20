"""Lentille runtime : telemetry handler_calls + scheduler_runs.

Lit la telemetrie deja produite par le bot (Tier R = read-only DB) pour
detecter :
- Handlers Telegram avec 0 appel sur la fenetre (defaut 90 jours)
- Crons APScheduler qui fire mais produisent 0 matter (success sans effet)

ZERO ECRITURE, connexion sqlite3 mode=ro (audit doctrine SAS).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from shared import storage as _storage


@dataclass
class RuntimeCandidate:
    """Un symbole dont la telemetrie suggere qu'il n'est plus utilise."""
    name: str                # handler name (ex: cmd_review) ou cron job name
    kind: str                # handler | cron_job
    days_since_last: int     # > window = candidate
    n_calls_window: int      # 0 sur la fenetre
    evidence: str            # citation telemetry


def scan_handlers(window_days: int = 90) -> list[RuntimeCandidate]:
    """Detecte les handlers Telegram avec 0 appel sur fenetre.

    Necessite que handler_calls table existe (telemetry du bot). Si absente,
    retourne liste vide (silent OK : Tier R, on est observateur).
    """
    candidates: list[RuntimeCandidate] = []
    try:
        with _storage.db_ro() as cx:
            # Verify table exists
            r = cx.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='handler_calls'"
            ).fetchone()
            if not r:
                return []
            cutoff = (datetime.utcnow() - timedelta(days=window_days)).strftime("%Y-%m-%d")
            rows = cx.execute(
                "SELECT handler_name, COUNT(*) AS n, MAX(called_at) AS last_call "
                "FROM handler_calls "
                "GROUP BY handler_name "
                "HAVING last_call < ? OR last_call IS NULL",
                (cutoff,)
            ).fetchall()
            for row in rows:
                last = row["last_call"]
                try:
                    last_dt = datetime.fromisoformat(last) if last else None
                    days = (datetime.utcnow() - last_dt).days if last_dt else 9999
                except Exception:
                    days = 9999
                candidates.append(RuntimeCandidate(
                    name=row["handler_name"],
                    kind="handler",
                    days_since_last=days,
                    n_calls_window=0,
                    evidence=f"last_call={last or 'NEVER'} (window={window_days}d)",
                ))
    except Exception:
        return []
    return candidates


def scan_crons(window_days: int = 90) -> list[RuntimeCandidate]:
    """Detecte les crons APScheduler qui fire mais n'ont pas tourne dans la
    fenetre, OU qui tournent mais avec 100% fail.

    Lit scheduler_runs (migration 0062).
    """
    candidates: list[RuntimeCandidate] = []
    try:
        with _storage.db_ro() as cx:
            cutoff = (datetime.utcnow() - timedelta(days=window_days)).strftime("%Y-%m-%d")
            # Crons sans run recent
            rows = cx.execute(
                "SELECT job_name, COUNT(*) AS n, MAX(started_at) AS last_run "
                "FROM scheduler_runs "
                "GROUP BY job_name "
                "HAVING last_run < ?",
                (cutoff,)
            ).fetchall()
            for row in rows:
                last = row["last_run"]
                try:
                    last_dt = datetime.fromisoformat(last) if last else None
                    days = (datetime.utcnow() - last_dt).days if last_dt else 9999
                except Exception:
                    days = 9999
                candidates.append(RuntimeCandidate(
                    name=row["job_name"],
                    kind="cron_job",
                    days_since_last=days,
                    n_calls_window=0,
                    evidence=f"last_run={last or 'NEVER'} (window={window_days}d)",
                ))
    except Exception:
        return []
    return candidates


def scan(window_days: int = 90) -> dict[str, Any]:
    """Combine handlers + crons en un dict synthese."""
    handlers = scan_handlers(window_days)
    crons = scan_crons(window_days)
    return {
        "handlers": handlers,
        "crons": crons,
        "n_total": len(handlers) + len(crons),
        "by_name": {c.name: c for c in handlers + crons},
    }
