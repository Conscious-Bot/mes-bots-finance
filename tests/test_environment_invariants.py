"""L35 — invariants d'environnement : verrou anti « python nu ».

Une automatisation depend d'un contrat explicite (interpreteur absolu ou
python3), jamais d'une convention implicite de la machine. Origine : hook
PostToolUse tiers cassé 07/08 (`/bin/sh: python: command not found`) — la
classe etait deja fermee sur les surfaces controlees ; ce test la MAINTIENT
fermee (ratchet decreasing-only : tout nouveau script/plist nait dedans).
"""

from __future__ import annotations

import plistlib
import re
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
CODE_DIRS = ("scripts", "bot", "shared", "intelligence", "dashboard", "risk", "tests")

# E1a : shebang python nu (sans le 3) = resolution PATH implicite.
_BARE_SHEBANG = re.compile(r"^#!\s*(?:/usr/bin/env\s+python|/usr/bin/python)\s*$")
# E1b : invocation subprocess/os.system d'un `python ` nu dans une string.
_BARE_SUBPROC = re.compile(r"""["'](?:[^"']*\s)?python\s(?!-m\s*$)[^"']*["']""")
_SUBPROC_LINE = re.compile(r"subprocess|os\.system|Popen\(")


def _py_files():
    for d in CODE_DIRS:
        root = REPO / d
        if root.is_dir():
            yield from root.rglob("*.py")


def test_no_bare_python_shebang() -> None:
    """E1 : aucun shebang `python` nu dans le repo (python3 minimum)."""
    offenders = []
    for f in _py_files():
        try:
            first = f.read_text(encoding="utf-8", errors="ignore").split("\n", 1)[0]
        except OSError:
            continue
        if _BARE_SHEBANG.match(first):
            offenders.append(str(f.relative_to(REPO)))
    assert not offenders, f"shebang `python` nu (L35 E1) : {offenders}"


def test_no_bare_python_in_subprocess_calls() -> None:
    """E1 : aucune ligne subprocess/os.system n'invoque `python ` nu."""
    offenders = []
    for f in _py_files():
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if _SUBPROC_LINE.search(line) and _BARE_SUBPROC.search(line) \
                    and "python3" not in line and not line.lstrip().startswith("#"):
                offenders.append(f"{f.relative_to(REPO)}:{i}")
    assert not offenders, f"subprocess `python` nu (L35 E1) : {offenders}"


def test_launchd_plists_use_absolute_interpreter() -> None:
    """E1 plists : tout LaunchAgent invoquant python le fait en chemin ABSOLU.

    Surface locale Mac uniquement — skip propre ailleurs (CI n'a pas de
    LaunchAgents ; l'invariant y est couvert par les deux tests repo).
    """
    la_dir = Path.home() / "Library" / "LaunchAgents"
    if not la_dir.is_dir():
        pytest.skip("pas de LaunchAgents (CI / non-Mac)")
    offenders = []
    for plist in la_dir.glob("*.plist"):
        try:
            data = plistlib.loads(plist.read_bytes())
        except Exception:
            continue  # plist tiers illisible : hors perimetre PRESAGE
        args = data.get("ProgramArguments") or []
        for a in args:
            if isinstance(a, str) and re.fullmatch(r"python3?", Path(a).name) \
                    and not a.startswith("/"):
                offenders.append(f"{plist.name}: {a}")
    assert not offenders, f"plist avec interpreteur non-absolu (L35 E1) : {offenders}"
