"""Cure P0-1 audit (3) 12/06/2026 — import-guard `shared/` → `dashboard/`.

Doctrine : `shared/` est la couche substrat (storage, prices, book, macro_state,
calibration, ...). `dashboard/` est la couche présentation (HTML, CSS, JS render).
La direction des imports est UNIQUE : présentation → substrat, jamais l'inverse.

Anti-pattern reconnu commentaire inline dans 3+ sessions sans correction
(macro_state.py:92 « Bands import lazy pour eviter circular dep dashboard.render »).
Tant que c'est un commentaire, ça n'enforce rien — seuls les tests contraignent.

Le test scan AST tous les .py de shared/ et assert qu'aucun n'importe dashboard.*.
Si tu vois ce test rouge :
1. Ne mets PAS ton helper dans dashboard/ pour ensuite l'importer depuis shared/.
2. Déplace le helper vers shared/ (la bonne couche), exporte-le, et fais l'inverse :
   dashboard/render.py importe depuis shared/ (direction propre).
3. Si vraiment besoin d'utiliser une fonction de dashboard/ (cas très rare,
   probablement déjà un bug), passe-la en injection de dépendance — pas en import.

Symétrique à `tests/test_doctrine_grep_gates.py` (yfinance, sqlite3) qui enforce
les passerelles canoniques. Ici c'est la direction des couches.

Hors scope (mais même classe — à étendre si besoin) :
- `intelligence/` → `dashboard/` (6 sites identifiés audit (3) 12/06 :
  decision_copilot, spof_and_sizing, portfolio_grade, analyze). À traiter dans
  une session dédiée — pas P0 immédiat parce que intelligence/ est plus haut
  dans la pile que shared/.
- `bot/handlers/misc.py` → `dashboard/chat` est intentionnel (handler routing).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"


def _imports_dashboard(py_file: Path) -> list[tuple[int, str]]:
    """Retourne la liste (lineno, import_line) des imports `dashboard.*` dans le fichier."""
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # `from dashboard.X import Y` ou `from dashboard import X`
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "dashboard" or mod.startswith("dashboard."):
                violations.append((node.lineno, f"from {mod} import ..."))
        # `import dashboard.X` ou `import dashboard`
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "dashboard" or alias.name.startswith("dashboard."):
                    violations.append((node.lineno, f"import {alias.name}"))
    return violations


def test_no_shared_module_imports_dashboard():
    """Aucun module de `shared/` ne doit importer `dashboard.*` (ni statique ni lazy).

    Cette direction casse la séparation substrat/présentation. Si tu as besoin
    d'un helper du dashboard dans shared/, c'est qu'il est mal placé : déplace-le
    vers shared/, puis fais dashboard/ l'importer (direction propre).
    """
    all_violations: dict[str, list[tuple[int, str]]] = {}
    for py_file in SHARED.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        viols = _imports_dashboard(py_file)
        if viols:
            rel = py_file.relative_to(ROOT).as_posix()
            all_violations[rel] = viols

    if all_violations:
        msg_lines = [
            "Couplage inversé shared/ → dashboard/ — anti-pattern P0 audit (3) :",
            "",
        ]
        for rel, viols in sorted(all_violations.items()):
            for lineno, import_line in viols:
                msg_lines.append(f"  {rel}:{lineno}  →  {import_line}")
        msg_lines.append("")
        msg_lines.append(
            "Cure : déplace le helper vers shared/ (la bonne couche), puis "
            "fais dashboard/ l'importer. Ne fais JAMAIS shared/ importer dashboard/."
        )
        raise AssertionError("\n".join(msg_lines))
