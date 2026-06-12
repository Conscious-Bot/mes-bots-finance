"""Cure P0-1 audit (3) 12/06/2026 — import-guards layer inversion `dashboard/`.

Doctrine : `shared/` est la couche substrat (storage, prices, book, macro_state,
calibration, ...). `dashboard/` est la couche présentation (HTML, CSS, JS render).
La direction des imports est UNIQUE : présentation → substrat, jamais l'inverse.

Deux niveaux d'enforcement :

1. `shared/` → `dashboard/` : ZÉRO TOLÉRANCE (test 1). Anti-pattern reconnu
   3+ sessions sans correction (macro_state.py:92 « Bands import lazy pour
   eviter circular dep dashboard.render »). Tant que commentaire, 0% enforcement.

2. `intelligence/` → `dashboard/` : RATCHET-FRIENDLY (test 2). 6 sites legacy
   identifiés audit (3) — whitelist explicite avec KNOWN-GAP, le 7e fait rougir.
   Cure : déplacer les helpers vers shared/ ou config/, mais c'est un travail
   plus large dédié post-#120 (refactor dashboard/render.py). En attendant,
   ratchet décroissant-only (cf memory feedback_seam_not_big_bang).

Si tu vois un de ces tests rouge :
- Ne mets PAS ton helper dans dashboard/ pour ensuite l'importer depuis shared/
  ou intelligence/.
- Déplace le helper vers shared/ (la bonne couche), exporte-le, et fais l'inverse :
  dashboard/render.py importe depuis shared/ (direction propre).
- Si vraiment besoin d'utiliser une fonction de dashboard/ (cas très rare,
  probablement déjà un bug), passe-la en injection de dépendance — pas en import.

Symétrique à `tests/test_doctrine_grep_gates.py` (yfinance, sqlite3) qui enforce
les passerelles canoniques. Ici c'est la direction des couches.

Hors scope (intentionnel) :
- `bot/handlers/misc.py` → `dashboard/chat` est intentionnel (handler routing).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
INTELLIGENCE = ROOT / "intelligence"

# Whitelist ratchet pour intelligence/ → dashboard/. Chaque entrée = un import
# legacy connu et documenté. Le 7e import fait rougir le test (ratchet décroissant).
# Format : (rel_path, lineno, module_imported)
# Cure structurelle : déplacer les définitions concernées de dashboard/ vers
# shared/ (TICKER_SECTOR → shared/sector_taxonomy.py ou config/sector_profiles.yaml,
# _positions/_cluster_health/_pnl_cost_map → shared/portfolio_analytics.py,
# format_llm_unavailable_marker → garder dans dashboard/ mais inversion-corrigée
# par injection de dépendance). À faire dans une session dédiée post-#120.
_INTELLIGENCE_LEGACY_WHITELIST: set[tuple[str, int, str]] = {
    # spof_and_sizing.py × 2 : RÉSOLUS cure #120 étape 3 (12/06) — _positions
    # déplacé vers shared/portfolio_view_builder.py, spof importe depuis shared/.
    # decision_copilot.py + portfolio_grade.py:184 : RÉSOLUS cure P2 audit (3)
    # reste whitelist (12/06) — TICKER_SECTOR déplacé vers shared/sector_taxonomy.py.
    # portfolio_grade.py:664 : RÉSOLU cure P2 audit (3) reste whitelist (12/06) —
    # _cluster_health + _pnl_cost_map déplacés vers shared/portfolio_analytics.py.
    ("intelligence/analyze.py", 534, "dashboard.restitution"),       # format_llm_unavailable_marker
}


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


def _imports_dashboard_with_modules(py_file: Path) -> list[tuple[int, str]]:
    """Comme _imports_dashboard mais retourne (lineno, module_imported) pour
    permettre le matching contre la whitelist ratchet."""
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "dashboard" or mod.startswith("dashboard."):
                out.append((node.lineno, mod))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "dashboard" or alias.name.startswith("dashboard."):
                    out.append((node.lineno, alias.name))
    return out


def test_intelligence_dashboard_imports_ratchet_decreasing_only():
    """Ratchet : aucun NOUVEAU `intelligence/` → `dashboard.*` au-delà de la
    whitelist legacy. Le 7e import fait rougir.

    Cure structurelle (à faire post-#120) : déplacer les helpers concernés
    depuis dashboard/ vers shared/ (ou config/) — TICKER_SECTOR, _positions,
    _cluster_health, _pnl_cost_map. format_llm_unavailable_marker reste dans
    dashboard/ mais l'usage par intelligence/analyze.py devrait passer par
    injection de dépendance, pas import direct.

    Inverse du ratchet (legacy résolu) : si tu déplaces un helper vers shared/,
    retire l'entrée de _INTELLIGENCE_LEGACY_WHITELIST — sinon le test signalera
    qu'une entrée whitelist n'a plus d'import correspondant (decreasing-only).
    """
    actual: set[tuple[str, int, str]] = set()
    for py_file in INTELLIGENCE.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        rel = py_file.relative_to(ROOT).as_posix()
        for lineno, module in _imports_dashboard_with_modules(py_file):
            actual.add((rel, lineno, module))

    new_violations = actual - _INTELLIGENCE_LEGACY_WHITELIST
    resolved_legacy = _INTELLIGENCE_LEGACY_WHITELIST - actual

    if new_violations:
        msg_lines = [
            "NOUVEAU couplage intelligence/ → dashboard/ (au-delà de la whitelist legacy) :",
            "",
        ]
        for rel, lineno, module in sorted(new_violations):
            msg_lines.append(f"  {rel}:{lineno}  →  from {module} import ...")
        msg_lines.append("")
        msg_lines.append(
            "Cure : déplace le helper concerné vers shared/ (la bonne couche), "
            "puis fais intelligence/ l'importer depuis shared/. Le ratchet "
            "doit être DECREASING-ONLY — on ne refait pas la dette structurelle "
            "qu'on vient de mesurer."
        )
        raise AssertionError("\n".join(msg_lines))

    if resolved_legacy:
        msg_lines = [
            "Entrées _INTELLIGENCE_LEGACY_WHITELIST sans import correspondant :",
            "",
        ]
        for rel, lineno, module in sorted(resolved_legacy):
            msg_lines.append(f"  {rel}:{lineno}  →  from {module} import ...")
        msg_lines.append("")
        msg_lines.append(
            "Cure : retire ces entrées de _INTELLIGENCE_LEGACY_WHITELIST. "
            "Le ratchet a fait son travail — décroît la dette."
        )
        raise AssertionError("\n".join(msg_lines))
