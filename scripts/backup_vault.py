"""Backup du vault Obsidian PRESAGE — le « cerveau » NON-régénérable.

Chantier #31 (04/07) : le vault (254 notes, blocs FAIT figés, audits fondamentaux,
décisions) est acté « storage/cerveau/data bank durable » (memory 25/06) mais
n'était couvert par AUCUN backup (grep « vault » dans backup.sh = 0). Contrairement
à la DB (resync depuis la VM), le vault est IRRÉCUPÉRABLE s'il est perdu.

Le vault n'existe que derrière l'API REST Obsidian (127.0.0.1, Mac-only) : ce
script l'exporte via cette API (même mécanisme que l'export one-off du 27/06),
recompose l'arbre, tar.gz horodaté, rétention daily×14 + monthly×6.

Usage (Mac uniquement — la VM ne peut pas atteindre 127.0.0.1) :
    python scripts/backup_vault.py [--dest DIR]

Fail-LOUD : si l'API REST est injoignable, exit != 0 (un backup silencieusement
raté du cerveau est pire que pas de backup — on veut que l'ops le voie).
"""

from __future__ import annotations

import argparse
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_DEST = Path.home() / "presage_vault_backups"
DAILY_KEEP = 14   # 14 derniers jours
MONTHLY_KEEP = 6  # + 6 premiers-du-mois


def _walk_vault(folder: str = "") -> list[str]:
    """Liste RÉCURSIVE de toutes les notes (.md et pièces jointes) du vault.

    L'API REST liste un dossier à la fois ; les sous-dossiers sont suffixés '/'.
    """
    from shared import obsidian

    out: list[str] = []
    for entry in obsidian.list_notes(folder):
        full = f"{folder}{entry}" if folder else entry
        if entry.endswith("/"):
            out.extend(_walk_vault(full))
        else:
            out.append(full)
    return out


def backup_vault(dest: Path = DEFAULT_DEST) -> Path:
    """Exporte le vault entier en tar.gz horodaté. Raise si REST injoignable."""
    from shared import obsidian
    from shared.obsidian import ObsidianError

    dest.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    # Vérif fail-loud : l'API doit répondre AVANT de créer un tar vide trompeur.
    try:
        notes = _walk_vault()
    except ObsidianError as e:
        raise SystemExit(
            f"REFUS : API REST Obsidian injoignable ({e}). Le vault n'a PAS été "
            "sauvegardé. Vérifier qu'Obsidian tourne + OBSIDIAN_API_URL/KEY en .env. "
            "(Ce script est Mac-only : l'API vit sur 127.0.0.1.)"
        ) from e
    if not notes:
        raise SystemExit(
            "REFUS : le vault liste 0 note — probablement l'API répond mais le vault "
            "est vide/mauvais. On ne remplace pas un backup par du vide."
        )

    md_count = sum(1 for n in notes if n.endswith(".md"))
    tarball = dest / f"PRESAGE_vault_{ts}.tgz"

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "vault"
        n_ok = n_fail = 0
        for note in notes:
            try:
                content = obsidian.read_note(note)
            except ObsidianError:
                n_fail += 1
                continue
            target = staging / note
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            n_ok += 1
        # manifeste = audit trail dans le tar lui-même
        (staging / "_BACKUP_MANIFEST.txt").write_text(
            f"PRESAGE vault backup {ts}\n"
            f"notes listed: {len(notes)} ({md_count} .md)\n"
            f"exported OK: {n_ok}\n"
            f"read failed: {n_fail}\n",
            encoding="utf-8",
        )
        with tarfile.open(tarball, "w:gz") as tf:
            tf.add(staging, arcname="vault")

    size = tarball.stat().st_size
    print(f"vault backup OK -> {tarball} ({size:,} bytes, {n_ok}/{len(notes)} notes, {n_fail} échecs)")
    if n_fail:
        print(f"  ⚠ {n_fail} note(s) illisibles — vérifier avant de considérer le backup complet")
    _rotate(dest)
    return tarball


def _rotate(dest: Path) -> None:
    """Rétention daily×14 + monthly×6 (premier tar de chaque mois conservé).

    Politique QUALITY_BAR axe 3 (« 17 backups DB → 1 politique de rétention »),
    appliquée ici au vault. Les tars sont nommés PRESAGE_vault_YYYYMMDD_HHMMSS.tgz.
    """
    tars = sorted(dest.glob("PRESAGE_vault_*.tgz"))
    if len(tars) <= DAILY_KEEP:
        return
    keep: set[Path] = set(tars[-DAILY_KEEP:])  # 14 plus récents
    # + le premier de chaque mois (monthly), pour les MONTHLY_KEEP derniers mois
    by_month: dict[str, Path] = {}
    for t in tars:
        # PRESAGE_vault_YYYYMMDD_HHMMSS.tgz → mois = YYYYMM
        stamp = t.stem.replace("PRESAGE_vault_", "")
        month = stamp[:6]
        if month not in by_month:  # premier (plus ancien) du mois
            by_month[month] = t
    for month in sorted(by_month)[-MONTHLY_KEEP:]:
        keep.add(by_month[month])
    removed = 0
    for t in tars:
        if t not in keep:
            t.unlink(missing_ok=True)
            removed += 1
    if removed:
        print(f"  rotation : {removed} tar(s) supprimé(s), {len(keep)} conservés (daily×{DAILY_KEEP} + monthly×{MONTHLY_KEEP})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Backup du vault Obsidian PRESAGE (Mac-only)")
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="dossier des backups")
    args = ap.parse_args()
    backup_vault(args.dest)
