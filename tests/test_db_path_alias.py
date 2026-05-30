"""Regression : storage.DB_PATH et storage._DB_PATH doivent pointer au meme fichier.

Bug origine (audit 30/05 iter 7) : storage avait DEUX path globals distincts :
- DB_PATH (ROOT-absolu) utilise par le context manager db()
- _DB_PATH (CWD-relatif) utilise par ~20 fonctions raw connect

Les deux pointaient vers le meme fichier *si* CWD = ROOT (cas usuel). Mais
un test qui monkeypatch un seul des deux laissait l'autre intact -- le
caller correspondant continuait a ecrire dans la prod silencieusement.

Fix : _DB_PATH = DB_PATH (alias). Ce test garantit que la consolidation
ne regresse pas.
"""

from pathlib import Path


def test_db_path_and_underscore_db_path_are_identical():
    """storage._DB_PATH doit etre le meme objet que storage.DB_PATH (ou egal absolu)."""
    from shared import storage

    # Identite ou egalite absolue (Path absolu compare bien __eq__)
    a = Path(storage.DB_PATH).resolve()
    b = Path(storage._DB_PATH).resolve()
    assert a == b, (
        f"DB_PATH et _DB_PATH doivent pointer au meme fichier absolu.\n"
        f"  DB_PATH  : {a}\n"
        f"  _DB_PATH : {b}\n"
        f"Bug origine : tests pouvaient monkeypatch un seul des deux et "
        f"l'autre continuait a ecrire en prod (commit 30/05)."
    )


def test_monkeypatch_single_path_propagates(tmp_path, monkeypatch):
    """Apres la consolidation, monkeypatch DB_PATH doit suffire pour rerouter
    AUSSI les callers qui lisent _DB_PATH (puisque _DB_PATH = DB_PATH).

    Si ce test fail, le bug pollution prod est de retour.
    """
    from shared import storage

    fake_db = tmp_path / "fake.db"
    monkeypatch.setattr(storage, "DB_PATH", fake_db)

    # Les deux refs doivent maintenant pointer au meme fake.db
    assert Path(storage.DB_PATH).name == "fake.db"
    assert Path(storage._DB_PATH).name == "fake.db", (
        "monkeypatch DB_PATH ne propage pas a _DB_PATH -- bug pollution prod revenue"
    )
