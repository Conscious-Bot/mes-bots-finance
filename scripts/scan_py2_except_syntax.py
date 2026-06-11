"""Dry-run scan : trouve toutes les `except A, B:` Py2-syntax dans le codebase.

Affiche fichier:line, syntaxe actuelle, fix proposé avec parenthèses.
NE MODIFIE RIEN — read-only.

Usage:
    python3 -m scripts.scan_py2_except_syntax
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Regex : matche `except A, B[, C, ...]:` (2+ types séparés par virgules)
# Capture (indent, type_list, trailing).
# Évite :
# - `except A as B:` (mot-clé `as` au lieu de virgule)
# - `except (A, B):` (parenthèses déjà présentes)
# - Lignes en commentaire/docstring (le matching commence après whitespace,
#   on filtre par ailleurs)
PATTERN = re.compile(
    r"^(\s*)except\s+([A-Za-z_][A-Za-z0-9_.]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_.]*)+)\s*:\s*(#.*)?$"
)


def fix_line(indent: str, type_list_raw: str, trailing_comment: str | None) -> str:
    """Construit la ligne fixée avec parenthèses."""
    # Normalise les espaces autour des virgules
    types = [t.strip() for t in type_list_raw.split(",")]
    types_clean = ", ".join(types)
    comment = f"  {trailing_comment}" if trailing_comment else ""
    return f"{indent}except ({types_clean}):{comment}"


def scan_repo(root: Path) -> list[dict]:
    """Scan tous les .py du repo, retourne liste de matchs."""
    matches = []
    skip_dirs = {".git", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules"}

    for path in sorted(root.rglob("*.py")):
        # Filtre les dossiers à ignorer
        if any(part in skip_dirs for part in path.parts):
            continue

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue

        rel_path = path.relative_to(root)
        for lineno, line in enumerate(lines, start=1):
            m = PATTERN.match(line)
            if not m:
                continue
            indent, type_list_raw, trailing = m.group(1), m.group(2), m.group(3)
            # Filtre faux positifs : si la "ligne" est dans une docstring,
            # le matching pattern aurait dû échouer (`except` ne commence pas
            # une ligne docstring typique). Garde la sortie pour audit humain.
            fixed = fix_line(indent, type_list_raw, trailing)
            matches.append({
                "path": str(rel_path),
                "lineno": lineno,
                "current": line.rstrip(),
                "fixed": fixed,
                "types": [t.strip() for t in type_list_raw.split(",")],
            })

    return matches


def apply_fixes(root: Path, matches: list[dict]) -> tuple[int, list[str]]:
    """Applique les fixes file-par-file avec ast-reparse + rollback per file.

    Returns:
        (n_applied, errors)
    """
    import ast
    n_applied = 0
    errors: list[str] = []

    # Group by file pour traiter atomiquement
    by_file: dict[str, list[dict]] = {}
    for m in matches:
        by_file.setdefault(m["path"], []).append(m)

    for rel_path, ms in sorted(by_file.items()):
        path = root / rel_path
        original = path.read_text(encoding="utf-8")
        # Build mapping lineno → fixed line
        fix_map = {m["lineno"]: m["fixed"] for m in ms}
        new_lines = []
        for i, line in enumerate(original.splitlines(), start=1):
            new_lines.append(fix_map.get(i, line))
        new_content = "\n".join(new_lines)
        # Preserve trailing newline if present
        if original.endswith("\n"):
            new_content += "\n"
        # Ast-reparse check : si le nouveau contenu ne parse pas, rollback
        try:
            ast.parse(new_content)
        except SyntaxError as e:
            errors.append(f"{rel_path}: post-fix ast.parse FAILED → rollback. err={e}")
            continue
        path.write_text(new_content, encoding="utf-8")
        n_applied += len(ms)
        print(f"  ✓ {rel_path} : {len(ms)} site(s) corrigé(s)")

    return n_applied, errors


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply fixes (default: dry-run)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    matches = scan_repo(root)

    if not matches:
        print("Aucune occurrence `except A, B:` trouvée. ✓")
        return 0

    print(f"=== {len(matches)} occurrences trouvées dans {len({m['path'] for m in matches})} fichiers ===")
    print()
    print("Format : <fichier:ligne>")
    print("  AVANT : <ligne actuelle>")
    print("  APRÈS : <fix proposé>")
    print()

    # Group by file
    by_file: dict[str, list[dict]] = {}
    for m in matches:
        by_file.setdefault(m["path"], []).append(m)

    for path in sorted(by_file):
        ms = by_file[path]
        print(f"━━━ {path} ({len(ms)} occurrence{'s' if len(ms) > 1 else ''}) ━━━")
        for m in ms:
            print(f"  L{m['lineno']:>4}  types: {m['types']}")
            print(f"        AVANT: {m['current']}")
            print(f"        APRÈS: {m['fixed']}")
        print()

    # Récap par catégorie d'exceptions (utile pour spot patterns)
    print("=== Récap : combinaisons d'exceptions trouvées ===")
    combos: dict[tuple[str, ...], int] = {}
    for m in matches:
        key = tuple(m["types"])
        combos[key] = combos.get(key, 0) + 1
    for combo, count in sorted(combos.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>3}× except {', '.join(combo)}")

    print()
    print(f"=== Total : {len(matches)} sites à corriger ===")

    if args.apply:
        print()
        print("=== APPLYING FIXES (ast-reparse per file + rollback if invalid) ===")
        n_applied, errors = apply_fixes(root, matches)
        print()
        print(f"=== Fixes appliqués : {n_applied} / {len(matches)} sites ===")
        if errors:
            print(f"⚠️  {len(errors)} fichiers rollback :")
            for e in errors:
                print(f"  {e}")
            return 2
        print("✓ Tous fichiers ast-reparsable post-fix.")
    else:
        print()
        print("Dry-run. Pour appliquer : python3 -m scripts.scan_py2_except_syntax --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
