"""CLI entry point : python -m hermes.inspector [--lens ...] [--since Nd] [...]

Doctrine SAS Tier R : ZERO ECRITURE en dehors de docs/AUDIT_HERMES_*.md.
Aucune modification de code, jamais. Le verdict reste a toi.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import report, runner


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m hermes.inspector",
        description="Hermes Tier R audit triangulation 3-lentilles (statique + runtime + decision).",
    )
    p.add_argument(
        "--lens",
        choices=("static", "runtime", "decision", "all"),
        default="all",
        help="Lentille a executer (defaut: all).",
    )
    p.add_argument(
        "--since",
        default="90d",
        help="Fenetre runtime + decision (ex: 90d, 30d). Defaut: 90d.",
    )
    p.add_argument(
        "--target",
        action="append",
        default=None,
        help="Cible scan statique (repetable). Defaut: dashboard/ intelligence/ shared/ bot/.",
    )
    p.add_argument(
        "--min-confidence",
        type=int,
        default=80,
        help="Min vulture confidence percent (defaut: 80).",
    )
    p.add_argument(
        "--out-dir",
        default="docs",
        help="Dossier de sortie pour le report markdown (defaut: docs/).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche summary mais n'ecrit pas le fichier.",
    )

    args = p.parse_args(argv)

    # Parse --since
    if args.since.endswith("d"):
        window_days = int(args.since[:-1])
    else:
        window_days = int(args.since)

    lenses = (args.lens,) if args.lens != "all" else ("static", "runtime", "decision")
    audit = runner.run(
        lenses=lenses,
        window_days=window_days,
        targets=args.target,
        vulture_min_confidence=args.min_confidence,
    )

    summary = audit.get("summary", {})
    print("=== Hermes audit ===")
    print(f"Window         : {window_days} days")
    print(f"Lenses         : {', '.join(lenses)}")
    print(f"Targets        : {audit['meta']['targets']}")
    print(f"DEAD (3/3)     : {summary.get('DEAD', 0)}")
    print(f"CANDIDATE (2/3): {summary.get('CANDIDATE', 0)}")
    print(f"WATCH (1/3)    : {summary.get('WATCH', 0)}")
    print(f"excluded       : {summary.get('excluded', 0)}")
    print(f"total findings : {summary.get('total_findings', 0)}")

    if args.dry_run:
        print("\n[dry-run] No file written.")
        return 0

    out_path = report.serialize(audit, out_dir=Path(args.out_dir))
    print(f"\nReport written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
