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


@pytest.fixture(scope="session")
def _migrated_db_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Template DB migre UNE fois par session via bootstrap_schema (alembic
    upgrade head). Consomme par migrated_db qui en fait un snapshot par test
    via SQLite backup() API.

    Optimisation 11/06 : migration coute ~1.2s, sans template chaque test
    paye ce cout (N tests = N migrations). Avec template + N backups (~ms
    chacun), on paye 1.2s une seule fois.

    Checkpoint WAL post-bootstrap pour s'assurer que le .db principal est
    complet (defensive — backup() est par-construction WAL-safe, mais
    PRAGMA wal_checkpoint(TRUNCATE) garantit hygiene).
    """
    import sqlite3

    from shared import storage

    template_path = tmp_path_factory.mktemp("alembic_template") / "head.db"
    storage.bootstrap_schema(db_path=str(template_path))
    # Force WAL checkpoint : vide le sidecar -wal, garantit que .db principal
    # contient l'état complet avant toute copie ultérieure.
    cx = sqlite3.connect(str(template_path))
    cx.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    cx.close()
    return template_path


@pytest.fixture
def migrated_db(
    _migrated_db_template: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """DB sqlite temp avec schema head (alembic upgrade head).

    Resolve L8 : fixtures derivees de la migration courante, pas snapshots
    statiques. Toute colonne/index/trigger ajoute par une migration sera
    automatiquement present.

    OPTIMISE 11/06 : copie via SQLite backup() API depuis un template
    session-scoped (migre UNE fois) au lieu de relancer alembic.upgrade(head)
    par test. Gain : ~1.2s/test → ~ms/test.

    backup() API SQLite est by-construction WAL-safe — produit un snapshot
    coherent quel que soit l'etat du -wal/-shm sidecars (contrairement a
    shutil.copy qui ne touche que le .db principal et peut rater des
    ecritures WAL non-checkpointees).

    Contrat inchange : retourne Path + monkeypatch storage.DB_PATH.

    Returns:
        Path vers la DB temp. `shared.storage.DB_PATH` est patche vers
        cette DB pour la duree du test.
    """
    import sqlite3

    from shared import storage

    db = tmp_path / "migrated.db"
    # SQLite backup API : snapshot coherent, WAL-safe par construction
    with sqlite3.connect(str(_migrated_db_template)) as src, sqlite3.connect(str(db)) as dst:
        src.backup(dst)
    monkeypatch.setattr(storage, "DB_PATH", db)
    return db


@pytest.fixture(autouse=True)
def _reset_price_caches():
    """Isolation inter-tests des caches prix/FX (#147).

    Vide les caches in-process de shared.prices AVANT chaque test. Sans ça, un
    cache (FX surtout) porte d'un test a l'autre fait diverger les agregats
    somme-parties au-dela de la tolerance -> flaky ordre-dependant
    (test_aggregate_sum_equals_parts + test_coherence_under_perturbation
    passaient isoles, failaient en full-run).

    Reset SEULEMENT si shared.prices est deja importe (sys.modules) : un test
    pur qui n'y touche pas ne force pas l'import et n'a rien a polluer. Source
    unique du reset = prices.reset_caches() (L1), pas un clear de dicts internes.
    """
    import sys

    _prices = sys.modules.get("shared.prices")
    if _prices is not None:
        _prices.reset_caches()
    yield


def _has_book_data() -> bool:
    """Detection robuste : DB courante a-t-elle des positions ?

    Retourne False si DB vide / schema-only / erreur acces. Utilise par le
    marker `live_book` (cf pytest_collection_modifyitems) pour skip cleanly
    les tests data-dependants en CI fresh checkout.
    """
    try:
        from shared import storage
        bv = storage.get_book_view()
        return bv.n_positions > 0
    except Exception:
        return False


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_book: test requires a populated bot.db (positions > 0). "
        "Auto-skip in CI fresh checkout, run in dev local.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """Auto-skip tests marques @pytest.mark.live_book si la DB est vide.

    Pattern symetrique au marker `slow` (network/LLM tests skipped via -m
    "not slow" en CI). Ici on skip dynamiquement selon l'etat de la DB,
    pour les tests qui valident des invariants sur le book reel."""
    if _has_book_data():
        return
    skip = pytest.mark.skip(reason="requires live book data (n_positions > 0)")
    for item in items:
        if "live_book" in item.keywords:
            item.add_marker(skip)
