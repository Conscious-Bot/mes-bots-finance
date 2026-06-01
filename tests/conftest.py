"""pytest config — adds project root to sys.path + fixture migrated_db.

#41 (01/06/2026) -- fixture `migrated_db` reusable : cree une DB sqlite
temp + lance `alembic upgrade head` dessus + monkeypatch storage.DB_PATH.
Resolve L8 (test fixtures != schema prod) a la racine : les futurs tests
qui demandent `migrated_db` taperont AUTOMATIQUEMENT le schema head,
zero drift possible.

Usage dans un test :

    def test_open_candidate_writes_note_tags_json(migrated_db):
        # migrated_db est un Path, et storage.DB_PATH est deja patche.
        from intelligence.over_cap_monitor import open_candidate
        open_candidate(...)
        # Si la migration 0023 a ete posee, note_tags_json est present.

Pattern recommande pour TOUT nouveau test qui doit ecrire/lire en DB.
Anciens tests (avec mini-schema inline ou DB live) restent valides mais
ne sont plus le pattern par defaut.
"""

import os
import sys
from pathlib import Path

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture
def migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """DB sqlite temp avec schema head (alembic upgrade head).

    Resolve L8 : fixtures derivees de la migration courante, pas snapshots
    statiques. Toute colonne/index/trigger ajoute par une migration sera
    automatiquement present.

    Returns:
        Path vers la DB temp. `shared.storage.DB_PATH` est patche vers
        cette DB pour la duree du test.
    """
    from shared import storage

    db = tmp_path / "migrated.db"
    storage.bootstrap_schema(db_path=str(db))
    monkeypatch.setattr(storage, "DB_PATH", db)
    return db
