"""Tests book_context (SPEC digest_enrichment_v2 §1-2, T9-partiel).

Couvre : rendu contexte book depuis theses+book mockés, fail-closed par champ
(L15), tri par poids, parse triggers JSON, chargement open_questions.yaml
(réel + malformé -> []).
"""
from __future__ import annotations

from unittest.mock import patch

from intelligence import book_context as _bc


class _BL:
    def __init__(self, weight_eur: float):
        self.weight_market_eur = weight_eur


def _thesis(**kw) -> dict:
    base = {
        "id": 1, "ticker": "AAA", "conviction": 4, "status": "active",
        "target_full_value": 100.0, "target_full_currency": "USD",
        "target_full": None, "stop_value": None, "stop_currency": None,
        "stop_price": 80.0, "variant_perception": "variant test",
        "invalidation_triggers": '["trigger un", "trigger deux"]',
    }
    base.update(kw)
    return base


# ─── build_book_context ──────────────────────────────────────────────────────


def test_context_renders_all_active_theses_sorted_by_weight():
    theses = [
        _thesis(id=1, ticker="AAA"),
        _thesis(id=2, ticker="BBB", conviction=5),
    ]
    book = {"AAA": _BL(100.0), "BBB": _BL(300.0)}
    with patch("shared.storage.active_theses", return_value=theses), \
         patch("shared.book.get_book_index", return_value=book):
        out = _bc.build_book_context()
    lines = out.splitlines()
    assert "2 thèses actives" in lines[0]
    # BBB (300/400 = 75%) doit passer avant AAA (25%)
    assert lines[1].startswith("BBB | 75.0% | c5")
    assert lines[2].startswith("AAA | 25.0% | c4")
    assert "tgt 100 USD" in lines[2]
    assert "trigger un · trigger deux" in lines[2]


def test_context_fail_closed_missing_fields():
    """Champs absents -> '—' / '?%', jamais de valeur inventée (L15)."""
    theses = [_thesis(
        ticker="NUDE", conviction=None, target_full_value=None,
        target_full=None, stop_price=None, variant_perception=None,
        invalidation_triggers=None,
    )]
    with patch("shared.storage.active_theses", return_value=theses), \
         patch("shared.book.get_book_index", return_value={}):
        out = _bc.build_book_context()
    line = out.splitlines()[1]
    assert "?%" in line          # pas de BookLine -> poids inconnu, pas 0 inventé
    assert "c—" in line
    assert "tgt —" in line
    assert "var: —" in line
    assert "inval: —" in line


def test_context_storage_failure_degrades_not_raises():
    """Accès theses en échec -> bloc INDISPONIBLE, pas d'exception (L5)."""
    with patch("shared.storage.active_theses", side_effect=RuntimeError("db down")):
        out = _bc.build_book_context()
    assert "INDISPONIBLE" in out


# ─── _parse_triggers ─────────────────────────────────────────────────────────


def test_parse_triggers_valid_and_invalid():
    assert _bc._parse_triggers('["a", "b"]') == "a · b"
    assert _bc._parse_triggers("pas du json{") == "—"
    assert _bc._parse_triggers(None) == "—"
    assert _bc._parse_triggers("[]") == "—"


# ─── open_questions ──────────────────────────────────────────────────────────


def test_load_open_questions_real_file():
    """Le vrai config/open_questions.yaml parse et contient au moins Q1
    avec id+question (test d'intégration léger sur le fichier commité)."""
    qs = _bc.load_open_questions()
    assert isinstance(qs, list)
    if qs:  # si le fichier est présent dans ce checkout
        assert all(q.get("id") and q.get("question") for q in qs)
        assert any(q["id"] == "Q1" for q in qs)


def test_load_open_questions_malformed_fail_closed(tmp_path, monkeypatch):
    """YAML illisible -> [] + pas d'exception (le digest continue sans
    la section QUESTIONS, il n'en invente pas)."""
    bad = tmp_path / "open_questions.yaml"
    bad.write_text("::: pas du yaml [", encoding="utf-8")
    monkeypatch.setattr(_bc, "_OPEN_QUESTIONS_PATH", bad)
    assert _bc.load_open_questions() == []
    # render reste honnête (L3) : état explicite, pas de section fantôme
    assert "aucune déclarée" in _bc.render_open_questions()


def test_load_open_questions_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(_bc, "_OPEN_QUESTIONS_PATH", tmp_path / "absent.yaml")
    assert _bc.load_open_questions() == []
