"""Lentille CI : etat GitHub Actions (read-only via `gh` CLI).

Hermes astreint au CI green (audit 20/06). Detecte :
- Runs failed sur les N derniers commits (defaut : 10 runs)
- Patterns de fail recurrents (meme job qui fail X fois)
- Drift : test name qui passe puis fail apres un commit (regression candidate)

Read-only strict : ne fait QUE `gh run list` et `gh run view --log-failed`.
N'execute jamais `gh rerun` / `gh workflow run` / aucune mutation.

Si `gh` CLI absent ou GITHUB_TOKEN missing, retourne candidats vide
(silent OK, Tier R observateur).
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class CIFailure:
    """Un run CI failed avec contexte."""
    run_id: str             # GitHub run id
    workflow: str           # CI / lint / etc
    commit_sha: str         # short sha
    commit_msg: str         # truncated
    failed_at: str          # ISO timestamp
    failed_test: str | None = None  # parsed from log if available
    age_hours: float = 0    # heures depuis le fail
    on_main: bool = True    # was it on main branch ?


def _run_gh(args: list[str], timeout: int = 30) -> str | None:
    """Run `gh` CLI command, return stdout. Returns None if gh missing/failed."""
    try:
        result = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def scan_recent_fails(limit: int = 10, branch: str = "main") -> list[CIFailure]:
    """List recent failed runs on the branch.

    Args:
        limit: nombre de runs a inspecter (defaut 10)
        branch: filter par branch (defaut main)

    Returns:
        list[CIFailure] des runs failed (peut etre vide).
    """
    raw = _run_gh([
        "run", "list",
        "--branch", branch,
        "--limit", str(limit),
        "--json", "databaseId,workflowName,conclusion,headSha,displayTitle,createdAt,status",
    ])
    if not raw:
        return []
    try:
        runs = json.loads(raw)
    except json.JSONDecodeError:
        return []
    failures: list[CIFailure] = []
    now = datetime.utcnow()
    for run in runs:
        if run.get("conclusion") != "failure":
            continue
        created = run.get("createdAt", "")
        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
            age_h = (now - created_dt).total_seconds() / 3600
        except Exception:
            age_h = 9999.0
        failures.append(CIFailure(
            run_id=str(run.get("databaseId", "")),
            workflow=run.get("workflowName", "?"),
            commit_sha=(run.get("headSha", "?") or "")[:7],
            commit_msg=(run.get("displayTitle", "") or "")[:80],
            failed_at=created,
            age_hours=age_h,
            on_main=(branch == "main"),
        ))
    return failures


def parse_failed_test_from_log(run_id: str) -> str | None:
    """Extract first FAILED test name from `gh run view --log-failed`."""
    raw = _run_gh(["run", "view", run_id, "--log-failed"], timeout=60)
    if not raw:
        return None
    # Match : 'FAILED tests/path::test_name' or 'FAILED tests/path::ClassName::test_name'
    m = re.search(r"FAILED\s+(\S+::\S+)", raw)
    return m.group(1) if m else None


def detect_recurrent_fails(failures: list[CIFailure]) -> dict[str, int]:
    """Count how many times the same test fails across recent runs.

    Returns:
        dict[test_name -> count]. Test names with count >= 2 = candidates flaky/regression.
    """
    counts: dict[str, int] = {}
    for f in failures:
        if not f.failed_test:
            continue
        counts[f.failed_test] = counts.get(f.failed_test, 0) + 1
    return counts


def scan(limit: int = 10, branch: str = "main",
         deep_parse: bool = True) -> dict[str, Any]:
    """Audit CI : recent fails + recurrent test patterns.

    Args:
        limit: nombre de runs a inspecter.
        branch: filter branch.
        deep_parse: si True, parse les logs pour extraire failed test names
            (plus lent, +30s/run).
    """
    fails = scan_recent_fails(limit=limit, branch=branch)
    if deep_parse:
        for f in fails:
            f.failed_test = parse_failed_test_from_log(f.run_id)
    recurrent = detect_recurrent_fails(fails)
    # Most recent fail's age (heures)
    last_fail_age = min((f.age_hours for f in fails), default=None)
    return {
        "failures": fails,
        "n_failures": len(fails),
        "recurrent_tests": recurrent,
        "n_recurrent": sum(1 for k, v in recurrent.items() if v >= 2),
        "last_fail_age_hours": last_fail_age,
        "ci_green": len(fails) == 0,
    }
