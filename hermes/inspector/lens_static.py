"""Lentille statique : ruff + vulture.

Combine 2 outils determinist :
- ruff : F-rules (unused-import, redefinition, etc.) + RUF (unused-vars)
- vulture : dead code detector via AST (functions/vars jamais referencees)

Confiance min vulture = 80% (defaults audit ratified). Doctrine-aware via
hermes.inspector.doctrine.is_excluded().

Sortie : dict de candidats avec preuves citees.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .doctrine import is_excluded


@dataclass
class StaticCandidate:
    """Un symbole candidate-mort detecte par la lentille statique."""
    name: str                          # nom du symbole (fonction / classe / var)
    file: str                          # chemin relatif
    line: int                          # ligne dans le fichier
    kind: str                          # function | class | variable | import | attribute
    tool: str                          # ruff | vulture
    rule: str                          # F841 | F401 | RUF059 | vulture-...
    confidence: int                    # 0-100, vulture %
    excluded: bool = False             # match doctrine exclusion
    exclusion_reason: str | None = None
    raw_message: str = ""              # citation outil source


def run_ruff(targets: list[str]) -> list[StaticCandidate]:
    """Lance ruff check --output-format=json sur les targets, parse les
    F-rules + RUF-rules (dead/unused symbols)."""
    cmd = ["ruff", "check", "--output-format=json", *targets]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if not result.stdout:
        return []
    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    out: list[StaticCandidate] = []
    INTERESTING = ("F401", "F811", "F841", "RUF059", "RUF034", "F501")
    for issue in issues:
        code = issue.get("code", "")
        if not code.startswith(INTERESTING):
            continue
        msg = issue.get("message", "")
        candidate_name = msg.split("`")[1] if "`" in msg else msg[:40]
        file_rel = Path(issue["filename"]).relative_to(Path.cwd()).as_posix() \
            if "filename" in issue else "?"
        excluded, reason = is_excluded(candidate_name, msg)
        out.append(StaticCandidate(
            name=candidate_name,
            file=file_rel,
            line=issue.get("location", {}).get("row", 0),
            kind="symbol",
            tool="ruff",
            rule=code,
            confidence=100,  # ruff is deterministic
            excluded=excluded,
            exclusion_reason=reason,
            raw_message=msg,
        ))
    return out


def run_vulture(targets: list[str], min_confidence: int = 80) -> list[StaticCandidate]:
    """Lance vulture sur les targets avec confidence min.

    vulture output format : 'file:line: unused <kind> 'name' (N% confidence)'
    """
    cmd = ["vulture", f"--min-confidence={min_confidence}", *targets]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    # vulture exits non-zero quand il trouve des candidats, c'est normal
    out: list[StaticCandidate] = []
    for line in result.stdout.splitlines():
        if ":" not in line:
            continue
        # Parse : 'path/to/file.py:42: unused function 'foo' (75% confidence)'
        try:
            loc_part, msg = line.split(": ", 1)
            file_rel, line_no = loc_part.rsplit(":", 1)
            line_no_i = int(line_no)
        except (ValueError, IndexError):
            continue
        # Kind + name + confidence
        import re
        m = re.match(r"unused (\w+) ['\"]?([^'\"]+)['\"]? \((\d+)% confidence\)", msg)
        if not m:
            continue
        kind, name, conf = m.group(1), m.group(2), int(m.group(3))
        excluded, reason = is_excluded(name, line)
        out.append(StaticCandidate(
            name=name,
            file=file_rel,
            line=line_no_i,
            kind=kind,
            tool="vulture",
            rule=f"vulture-{kind}",
            confidence=conf,
            excluded=excluded,
            exclusion_reason=reason,
            raw_message=line.strip(),
        ))
    return out


def scan(targets: list[str] | None = None,
         min_vulture_confidence: int = 80) -> dict[str, Any]:
    """Lance les 2 outils statiques sur les targets.

    Defaults : dashboard/ intelligence/ shared/ bot/
    """
    if targets is None:
        targets = ["dashboard/", "intelligence/", "shared/", "bot/"]
    ruff_findings = run_ruff(targets)
    vulture_findings = run_vulture(targets, min_vulture_confidence)
    all_findings = ruff_findings + vulture_findings
    # Group par fichier:nom pour synthese
    by_key: dict[str, list[StaticCandidate]] = {}
    for c in all_findings:
        key = f"{c.file}::{c.name}"
        by_key.setdefault(key, []).append(c)
    return {
        "candidates_raw": all_findings,
        "candidates_grouped": by_key,
        "n_total": len(all_findings),
        "n_excluded": sum(1 for c in all_findings if c.excluded),
        "n_active": sum(1 for c in all_findings if not c.excluded),
    }
