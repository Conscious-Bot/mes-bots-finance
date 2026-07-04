"""Garde fail-loud de la page publique track record (audit 04/07, dashboard C1).

Le pattern section→{"error"}→.get(...,0) pouvait publier une page toute-à-zéro
(28 résolues réelles montrées comme 0) sur la surface qui, selon son propre
footer, est « l'unique référence ». On refuse plutôt que publier des zéros.
"""

from __future__ import annotations

import pytest

from scripts.render_public_track import RefusePublish, _assert_publishable


def test_refuse_empty_record():
    with pytest.raises(RefusePublish, match="entièrement vide"):
        _assert_publishable({"predictions": {"n_resolved": 0, "n_open": 0}, "theses": {"n_active": 0}})


def test_refuse_errored_section():
    with pytest.raises(RefusePublish, match="erreur"):
        _assert_publishable({"predictions": {"error": "db locked"}})


def test_accept_real_record():
    # aucun raise
    _assert_publishable(
        {"predictions": {"n_resolved": 28, "n_open": 225}, "theses": {"n_active": 27}}
    )


def test_accept_partial_but_nonzero():
    """Un seul signal non nul suffit (ex. thèses actives sans prédiction résolue
    en tout début) — on ne refuse QUE le tout-à-zéro."""
    _assert_publishable({"predictions": {"n_resolved": 0, "n_open": 0}, "theses": {"n_active": 5}})


def test_missing_keys_treated_as_zero():
    with pytest.raises(RefusePublish):
        _assert_publishable({})
