#!/usr/bin/env python3
"""Génère un dump analysable du projet PRESAGE — en PARTIES bornées.

Objectif : permettre une analyse externe précise sans produire un fichier de
plusieurs mégaoctets illisible par un analyseur (le repo fait ~127 k lignes de
Python + ~1,3 Mo de doctrine).

SÉCURITÉ (non négociable) : n'inclut JAMAIS data/*.db, .env, credentials,
exports broker, digests, backups — ils contiennent des données personnelles
(nom, IBAN) et des secrets. La liste d'exclusion est explicite et testée.

Sortie dans `dumps/` :
    00_CARTE.md         cartographie : arbo, métriques, entrées, où lire quoi
    01_DOCTRINE.md      constitution, axiomes, politiques, risque, leçons
    02_CORE.md          shared/ + risk/ (le socle : ledger, prix, sizing)
    03_DASHBOARD.md     dashboard/ (rendu, serveur, styles, charts)
    04_INTELLIGENCE.md  intelligence/ (digest, monitors, scoring)
    05_TESTS.md         tests/ (invariants verrouillés)

Usage :
    python3 scripts/make_project_dump.py            # tout
    python3 scripts/make_project_dump.py --only 01  # une partie
"""
from __future__ import annotations

import argparse
import subprocess
from datetime import UTC, datetime

UTC = UTC  # compat 3.10 (le sandbox d'analyse peut être plus ancien que la prod 3.14)
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dumps"

# --- EXCLUSIONS DE SÉCURITÉ (PII / secrets / volumineux inutiles) -----------
EXCLUDED_DIRS = {
    ".git", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".hypothesis", "node_modules", "data", "backups", "digests", "dist",
    "baselines", ".claude", "dumps", "htmlcov", ".venv",
}
EXCLUDED_NAMES = {".env", ".env.local", "credentials.json", "token.json"}
EXCLUDED_SUFFIX = {".db", ".sqlite", ".sqlite3", ".csv", ".xlsx", ".png", ".jpg",
                   ".pdf", ".zip", ".gz", ".log", ".ipynb", ".html"}

MAX_FILE_KB = 400  # au-delà : on inclut la structure, pas le corps


def keep(p: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in p.parts):
        return False
    return not (p.name in EXCLUDED_NAMES or p.suffix in EXCLUDED_SUFFIX)


def collect(patterns: list[tuple]) -> list[Path]:
    """patterns : (base, glob) récursif, ou (base, glob, 'flat') non récursif."""
    files: list[Path] = []
    for pat in patterns:
        base, glob = pat[0], pat[1]
        flat = len(pat) > 2 and pat[2] == "flat"
        d = ROOT / base
        if not d.is_dir():
            continue
        it = d.glob(glob) if flat else d.rglob(glob)
        files += [p for p in sorted(it) if p.is_file() and keep(p)]
    return files


def outline(text: str, path: Path) -> str:
    """Pour un fichier trop gros : sommaire (defs/classes) au lieu du corps."""
    lines = []
    for i, ln in enumerate(text.splitlines(), 1):
        s = ln.strip()
        if s.startswith(("def ", "class ", "async def ", "# ---", "## ")):
            lines.append(f"{i:6}: {ln[:110]}")
    return (f"[FICHIER VOLUMINEUX — {path.stat().st_size // 1024} Ko — "
            f"SOMMAIRE SEUL]\n" + "\n".join(lines))


def write_part(name: str, title: str, intro: str, files: list[Path]) -> Path:
    OUT.mkdir(exist_ok=True)
    dest = OUT / name
    total = 0
    with dest.open("w", encoding="utf-8") as f:
        f.write(f"# PRESAGE — {title}\n\n")
        f.write(f"_Généré {datetime.now(UTC):%Y-%m-%d %H:%M UTC} — "
                f"{len(files)} fichiers._\n\n{intro}\n\n")
        f.write("## Sommaire\n\n")
        for p in files:
            f.write(f"- `{p.relative_to(ROOT)}` ({p.stat().st_size // 1024} Ko)\n")
        f.write("\n---\n")
        for p in files:
            rel = p.relative_to(ROOT)
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                txt = f"[illisible: {e}]"
            if p.stat().st_size > MAX_FILE_KB * 1024 and p.suffix == ".py":
                txt = outline(txt, p)
            lang = {".py": "python", ".md": "markdown", ".yaml": "yaml",
                    ".yml": "yaml", ".sh": "bash", ".sql": "sql"}.get(p.suffix, "")
            f.write(f"\n\n## `{rel}`\n\n```{lang}\n{txt}\n```\n")
            total += len(txt)
    print(f"  {dest.relative_to(ROOT)} — {len(files)} fichiers, {total // 1024} Ko")
    return dest


def make_carte() -> None:
    OUT.mkdir(exist_ok=True)
    tree = subprocess.run(
        ["bash", "-c",
         "find . -maxdepth 2 -type d "
         + " ".join(f"-not -path './{d}*'" for d in sorted(EXCLUDED_DIRS))
         + " | sort"],
        cwd=ROOT, capture_output=True, text=True).stdout

    def count(base: str, glob: str) -> tuple[int, int]:
        fs = collect([(base, glob)])
        return len(fs), sum(len(p.read_text(encoding="utf-8", errors="replace").splitlines()) for p in fs)

    rows = []
    for base, glob, label in [
        ("shared", "*.py", "socle (ledger, prix, book, datum)"),
        ("risk", "*.py", "risque (kill switch, sizing, engine)"),
        ("dashboard", "*.py", "dashboard (render, serve, charts)"),
        ("intelligence", "*.py", "intelligence (digest, monitors, scoring)"),
        ("bot", "*.py", "bot Telegram (handlers, jobs)"),
        ("scripts", "*.py", "scripts d'ops et migrations"),
        ("tests", "*.py", "tests (invariants verrouillés)"),
        ("config", "*.yaml", "politiques déclaratives"),
        ("docs", "*.md", "doctrine"),
    ]:
        n, lines = count(base, glob)
        rows.append(f"| `{base}/` | {n} | {lines} | {label} |")

    (OUT / "00_CARTE.md").write_text(f"""# PRESAGE — CARTE DU PROJET

_Généré {datetime.now(UTC):%Y-%m-%d %H:%M UTC}._

Système de décision d'investissement personnel : ledger append-only, moteur de
risque, dashboard local, pipeline d'information (digest), et un corpus de
doctrine (constitution, politiques, graphe d'hypothèses exécutable).

**Exclusions de sécurité appliquées à ce dump** : `data/` (base contenant nom et
IBAN), `.env`, credentials, exports broker, digests, backups, `venv/`.

## Volumétrie

| Répertoire | Fichiers | Lignes | Rôle |
|---|---|---|---|
{chr(10).join(rows)}

## Arborescence (2 niveaux)

```
{tree}
```

## Par où lire (ordre recommandé)

1. **`01_DOCTRINE.md`** — commencer par `PRESAGE_CONSTITUTION.md` (3 couches,
   10 axiomes), puis `config/policy.yaml` (toutes les constantes, nommées et
   datées), puis `config/assumptions.yaml` (graphe causal exécutable).
2. **`02_CORE.md`** — `shared/positions.py` (ledger), `shared/prices.py`
   (source unique de prix), `shared/book.py` (agrégation), `risk/` (sizing,
   kill switch).
3. **`03_DASHBOARD.md`** — `dashboard/render.py` génère le HTML,
   `dashboard/serve.py` sert en local avec auto-reload.
4. **`04_INTELLIGENCE.md`** — `intelligence/digest.py` (pipeline quotidien),
   les monitors, le scoring.
5. **`05_TESTS.md`** — les invariants réellement verrouillés.

## Points d'entrée exécutables

- `python3 -m dashboard.serve` — dashboard local (http://127.0.0.1:8000)
- `python3 -m bot.main` — process principal (crons APScheduler)
- `python3 scripts/assumption_graph.py` — audit du graphe causal
- `python3 scripts/assumption_graph.py --severity` — sévérité dérivée vs déclarée
- `pytest` — suite de tests

## Contraintes structurelles connues (à charge de l'analyse)

- `dashboard/render.py` ≈ 10 000 lignes : dette reconnue, découpe planifiée.
- Deux nœuds : VM (source de vérité) et Mac (réplique read-only). Sync horaire
  VM→Mac. Un seul écrivain autorisé (doctrine L34).
- Python 3.14 / SQLite WAL / APScheduler. Pas de FastAPI, Postgres ni Redis.
""", encoding="utf-8")
    print("  dumps/00_CARTE.md")


PARTS = {
    "01": ("01_DOCTRINE.md", "DOCTRINE VIVANTE (constitution, politiques, risque, leçons)",
           "**Commencer ici.** Corpus vivant : la constitution et ses 10 axiomes, "
           "les politiques déclaratives (aucune constante ailleurs dans le système), "
           "le graphe d'hypothèses exécutable, le framework de risque, les leçons "
           "transversales L1-L34. Les annexes historiques (ADR, specs, post-mortems, "
           "runbooks) sont dans `06_ANNEXES.md`.",
           [(".", "*.md", "flat"), ("docs", "*.md", "flat"), ("config", "*.yaml", "flat")]),
    "02": ("02_CORE.md", "SOCLE (shared/ + risk/)",
           "Le socle : ledger append-only, source unique de prix, agrégation du "
           "book, moteur de risque et sizing.",
           [("shared", "*.py"), ("risk", "*.py")]),
    "03": ("03_DASHBOARD.md", "DASHBOARD",
           "Génération HTML (render), serveur local avec auto-reload (serve), "
           "styles et graphiques.",
           [("dashboard", "*.py"), ("dashboard", "*.css"), ("dashboard", "*.js")]),
    "04": ("04_INTELLIGENCE.md", "INTELLIGENCE (digest, monitors, scoring)",
           "Pipeline d'information : ingestion, scoring, digest quotidien, "
           "monitors et sentinelles.",
           [("intelligence", "*.py")]),
    "05": ("05_TESTS.md", "TESTS (invariants verrouillés)",
           "Les tests qui verrouillent les invariants du système.",
           [("tests", "*.py")]),
    "06": ("06_ANNEXES.md", "ANNEXES (ADR, specs, post-mortems, runbooks, décisions)",
           "Historique et détail : décisions d'architecture (ADR), spécifications, "
           "post-mortems d'incidents, runbooks d'exploitation, journaux de décision "
           "d'investissement, gabarits. Utile pour la profondeur, non nécessaire "
           "pour comprendre l'architecture.",
           [("docs/adrs", "*.md"), ("docs/specs", "*.md"), ("docs/post-mortems", "*.md"),
            ("docs/runbooks", "*.md"), ("docs/decision_logs", "*.md"),
            ("docs/templates", "*.md"), ("docs/conventions", "*.md")]),
    "07": ("07_OPS.md", "OPS (scripts, crons, déploiement)",
           "Scripts d'exploitation, migrations, cron, déploiement et bot Telegram — "
           "la mécanique qui fait tourner le système au quotidien.",
           [("scripts", "*.py"), ("scripts", "*.sh"), ("crons", "*"),
            ("deploy", "*"), ("bot", "*.py")]),
    "09": ("09_RITUELS_CONFIG.md", "RITUELS & CONFIGURATION PROJET",
           "Les rituels opérationnels (commandes de clôture, crash-test, "
           "vérification des sentinelles, drill de backup) et la configuration du "
           "projet : dépendances, build, migrations, assets du dashboard.",
           [(".claude/commands", "*.md"), (".claude/skills", "*.md"),
            (".", "*.toml", "flat"), (".", "*.txt", "flat"), (".", "*.ini", "flat"),
            (".", "Makefile", "flat"), ("dashboard/static", "*.css"),
            ("dashboard/static", "*.js")]),
    "10": ("10_ARCHIVES.md", "ARCHIVES (audits, backtests, sessions, plans)",
           "Matériel historique : audits datés, résultats de backtests, journaux de "
           "sessions, plans et brouillons. Utile pour retracer la genèse des "
           "décisions d'architecture ; non nécessaire à la compréhension du système "
           "actuel. `docs/personal/` est EXCLU (contenu privé).",
           [("docs/audit", "*.md"), ("docs/audit_2026-06-03", "*.md"),
            ("docs/backtests", "*.md"), ("docs/backtest_audits", "*.md"),
            ("docs/calibration_audits", "*.md"), ("docs/plans", "*.md"),
            ("docs/drafts", "*.md"), ("docs/sessions", "*.md"),
            ("docs/snapshots", "*.md"), ("docs/archive", "*.md")]),
}


def make_schema() -> None:
    """Schéma SQL SEUL (structure) — jamais une ligne de données (PII)."""
    import sqlite3
    OUT.mkdir(exist_ok=True)
    dest = OUT / "08_SCHEMA.md"
    db = ROOT / "data" / "bot.db"
    head = ("# PRESAGE — SCHÉMA DE DONNÉES\n\n"
            f"_Généré {datetime.now(UTC):%Y-%m-%d %H:%M UTC}._\n\n"
            "**Structure uniquement — aucune ligne de données.** La base contient des "
            "informations personnelles (nom, IBAN) : seuls les `CREATE` sont extraits.\n\n"
            "Points d'architecture à observer : les triggers d'immuabilité "
            "(append-only sur le ledger et les prédictions), la vue `positions` "
            "recalculée depuis `transactions`, et les tables-journaux des monitors.\n\n")
    if not db.exists():
        dest.write_text(head + "> Base absente sur ce nœud — exécuter depuis la VM ou le Mac.\n",
                        encoding="utf-8")
        print("  dumps/08_SCHEMA.md (base absente)")
        return
    cx = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    parts = [head]
    for kind, title in (("table", "TABLES"), ("view", "VUES"),
                        ("trigger", "TRIGGERS (immuabilité, append-only)"),
                        ("index", "INDEX")):
        rows = cx.execute(
            "SELECT name, sql FROM sqlite_master WHERE type=? AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name", (kind,)).fetchall()
        parts.append(f"\n## {title} ({len(rows)})\n\n```sql\n")
        for _name, sql in rows:
            if sql:
                parts.append(sql.strip() + ";\n\n")
        parts.append("```\n")
    cx.close()
    dest.write_text("".join(parts), encoding="utf-8")
    print(f"  dumps/08_SCHEMA.md — {dest.stat().st_size // 1024} Ko")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="partie unique (00, 01, 02, 03, 04, 05)")
    args = ap.parse_args()
    print("Génération du dump PRESAGE →", OUT)
    if not args.only or args.only == "00":
        make_carte()
    if not args.only or args.only == "08":
        make_schema()
    for key, (name, title, intro, pats) in PARTS.items():
        if args.only and args.only != key:
            continue
        write_part(name, title, intro, collect(pats))
    print("\nTerminé. Exclusions PII/secrets appliquées.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
