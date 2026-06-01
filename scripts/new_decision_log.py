#!/usr/bin/env python3
"""new_decision_log.py — create new decision_log from TEMPLATE.md.

Auto-numerotation depuis ls docs/decision_logs/. Slugification titre.
Date pre-remplie. Copie TEMPLATE.md avec remplacements.

USAGE :
    python3 scripts/new_decision_log.py "casser ancre calibration"
    # -> docs/decision_logs/02_casser_ancre_calibration.md cree depuis template

OPTIONS :
    --dry-run : affiche le path qui serait cree, n'ecrit pas

Cf docs/decision_logs/TEMPLATE.md + CONVENTIONS section "Discipline statistique".
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT / "docs" / "decision_logs"
TEMPLATE = LOGS_DIR / "TEMPLATE.md"

# Mois en francais pour date_human
MOIS_FR = [
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
]


def slugify(title: str) -> str:
    """Title -> slug : lowercase, ascii-friendly, underscores."""
    s = title.lower().strip()
    # Replace accented chars
    s = s.replace("é", "e").replace("è", "e").replace("ê", "e").replace("ë", "e")
    s = s.replace("à", "a").replace("â", "a").replace("ä", "a")
    s = s.replace("ô", "o").replace("ö", "o")
    s = s.replace("î", "i").replace("ï", "i")
    s = s.replace("ù", "u").replace("û", "u").replace("ü", "u")
    s = s.replace("ç", "c")
    s = s.replace("'", " ").replace("’", " ")  # noqa: RUF001 -- ASCII-fold intentionnel du U+2019
    # Keep alphanumerics + spaces, replace rest with spaces
    s = re.sub(r"[^a-z0-9\s_-]", " ", s)
    # Collapse whitespace, replace with underscore
    s = re.sub(r"\s+", "_", s.strip())
    return s


def next_number() -> int:
    """Scan logs dir, return next available 2-digit number."""
    if not LOGS_DIR.exists():
        return 1
    existing = []
    for p in LOGS_DIR.glob("*.md"):
        if p.name == "TEMPLATE.md":
            continue
        m = re.match(r"^(\d{2})_", p.name)
        if m:
            existing.append(int(m.group(1)))
    return max(existing, default=0) + 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title", nargs="+", help="Titre du decision_log (en quotes si plusieurs mots)")
    parser.add_argument("--dry-run", action="store_true", help="Affiche le path qui serait cree, n'ecrit pas")
    args = parser.parse_args()

    if not TEMPLATE.exists():
        print(f"[ERR] template absent : {TEMPLATE}")
        sys.exit(1)

    title = " ".join(args.title).strip()
    if not title:
        print("[ERR] titre vide")
        sys.exit(1)

    num = next_number()
    slug = slugify(title)
    out_name = f"{num:02d}_{slug}.md"
    out_path = LOGS_DIR / out_name

    if out_path.exists():
        print(f"[ERR] fichier existe deja : {out_path}")
        sys.exit(1)

    # Build header
    today = datetime.now()
    date_human = f"{today.day} {MOIS_FR[today.month-1]} {today.year}"

    template_text = TEMPLATE.read_text(encoding="utf-8")

    # Replacements : remplir les placeholders du template
    out_text = template_text
    out_text = out_text.replace("# Decision Log #XX — [titre court verbe-action]",
                                f"# Decision Log #{num:02d} — {title}")
    out_text = out_text.replace("**Date** : [DD mois YYYY]",
                                f"**Date** : {date_human}")
    # Owner reste en placeholder (toujours Olivier mais le template l'a deja)

    if args.dry_run:
        print(f"[DRY-RUN] aurait cree : {out_path}")
        print("[DRY-RUN] header :")
        print(out_text.split("\n---", 1)[0])
        return

    out_path.write_text(out_text, encoding="utf-8")
    print(f"[OK] cree : {out_path}")
    print(f"[OK] header rempli : Decision Log #{num:02d} — {title} ({date_human})")
    print(f"\nEditer maintenant : {out_path}")


if __name__ == "__main__":
    main()
