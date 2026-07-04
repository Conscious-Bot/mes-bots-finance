"""Backup vault Obsidian (#31 04/07) — rotation + fail-loud + walk récursif.

Le end-to-end (export REST réel) n'est testable que sur le Mac avec Obsidian
lancé ; ici on teste la LOGIQUE : rotation daily+monthly, refus fail-loud, walk.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

import scripts.backup_vault as bv


def _touch(dest: Path, stamp: str) -> Path:
    p = dest / f"PRESAGE_vault_{stamp}.tgz"
    p.write_bytes(b"x")
    return p


def test_rotation_keeps_daily_and_monthly(tmp_path):
    # 20 tars sur 3 mois : mai (5), juin (10), juillet (5)
    stamps = (
        [f"202605{d:02d}_120000" for d in range(1, 6)]
        + [f"202606{d:02d}_120000" for d in range(1, 11)]
        + [f"202607{d:02d}_120000" for d in range(1, 6)]
    )
    for s in stamps:
        _touch(tmp_path, s)
    bv._rotate(tmp_path)
    remaining = {p.stem.replace("PRESAGE_vault_", "") for p in tmp_path.glob("*.tgz")}
    # 14 plus récents conservés
    newest_14 = set(sorted(stamps)[-14:])
    assert newest_14 <= remaining, "les 14 daily les plus récents doivent survivre"
    # + premier de chaque mois (monthly) : 20260501, 20260601, 20260701
    assert "20260501_120000" in remaining, "premier de mai (monthly) doit survivre"
    assert "20260601_120000" in remaining
    # un vieux tar de mai NON-premier doit être supprimé
    assert "20260503_120000" not in remaining


def test_rotation_noop_under_threshold(tmp_path):
    for d in range(1, 6):
        _touch(tmp_path, f"20260701_1200{d:02d}")
    bv._rotate(tmp_path)
    assert len(list(tmp_path.glob("*.tgz"))) == 5  # <=14, rien supprimé


def test_backup_fails_loud_when_api_down(tmp_path, monkeypatch):
    """API injoignable → SystemExit (pas de tar vide trompeur)."""
    from shared.obsidian import ObsidianError

    def _boom(folder=""):
        raise ObsidianError("connection refused")

    monkeypatch.setattr(bv, "_walk_vault", _boom)
    with pytest.raises(SystemExit, match="REFUS"):
        bv.backup_vault(tmp_path)
    assert list(tmp_path.glob("*.tgz")) == []  # rien créé


def test_backup_refuses_empty_vault(tmp_path, monkeypatch):
    """0 note listée → refus (ne remplace pas un backup par du vide)."""
    monkeypatch.setattr(bv, "_walk_vault", lambda folder="": [])
    with pytest.raises(SystemExit, match="0 note"):
        bv.backup_vault(tmp_path)


def test_backup_happy_path_with_mocked_api(tmp_path, monkeypatch):
    """Export nominal mocké : tar créé, structure préservée, manifeste présent."""
    notes = ["PRESAGE.md", "theses/TSM.md", "journal/digests/D.md"]
    monkeypatch.setattr(bv, "_walk_vault", lambda folder="": notes)
    import shared.obsidian as _obs
    monkeypatch.setattr(_obs, "read_note", lambda p: f"# {p}\ncontenu")
    out = bv.backup_vault(tmp_path)
    assert out.exists()
    with tarfile.open(out) as tf:
        names = tf.getnames()
    assert "vault/theses/TSM.md" in names  # arbre préservé
    assert "vault/_BACKUP_MANIFEST.txt" in names  # audit trail


def test_walk_recurses_folders(monkeypatch):
    """_walk_vault descend dans les sous-dossiers (suffixe '/')."""
    import shared.obsidian as _obs

    tree = {
        "": ["PRESAGE.md", "theses/"],
        "theses/": ["TSM.md", "sub/"],
        "theses/sub/": ["CCJ.md"],
    }
    monkeypatch.setattr(_obs, "list_notes", lambda folder="": tree[folder])
    got = bv._walk_vault()
    assert set(got) == {"PRESAGE.md", "theses/TSM.md", "theses/sub/CCJ.md"}
