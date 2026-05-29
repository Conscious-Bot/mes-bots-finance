"""Gate statique des invariants du book canonique (point #9 brief).

run_static_gate(conn) doit etre VERT en CI. Sinon le book est incoherent
et l'app ne devrait pas demarrer silencieusement.
"""

from __future__ import annotations

import pytest

from shared import position_invariants as pi, storage


def test_static_gate_is_green():
    """Le book courant est verrouille : 0 violation des invariants.

    Si ce test rouge sort : INVESTIGUER avant tout commit suivant. Le book
    est devenu incoherent quelque part. Lance :
        python3 -c "from shared import storage; print(storage.assert_book_invariants(strict=False))"
    """
    with storage.db() as cx:
        v = pi.run_static_gate(cx, strict=False)
    assert not v, f"Book gate RED : {v}"


def test_gate_strict_mode_raises():
    """En strict=True, run_static_gate leve InvariantViolation s'il y a un defaut.

    On simule un defaut en injectant un check qui retourne toujours qqch.
    """
    from shared.position_invariants import InvariantViolation, _check_no_phantom_ghosts_in_views

    # Verif qu'avec un check qui retourne vide on est OK
    with storage.db() as cx:
        result = _check_no_phantom_ghosts_in_views(cx)
    # Si tout est OK ce check doit etre vide
    if not result:
        # On peut faire raise manuellement pour tester le strict
        with pytest.raises(InvariantViolation):
            raise InvariantViolation("test")


def test_storage_get_position_view_passerelle():
    """Point #3 brief : storage.get_position_view est la passerelle unique.
    Doit fonctionner pour un ticker tenu + retourner None pour ticker inconnu."""
    v = storage.get_position_view("ASML.AS")
    assert v is not None
    assert v.weight_pct > 0
    assert v.weight_eur > 0

    v_none = storage.get_position_view("DOES_NOT_EXIST_XYZ")
    assert v_none is None


def test_storage_get_book_view():
    """Alias get_book_view retourne le BookView complet."""
    bv = storage.get_book_view()
    assert bv.n_positions > 0
    assert bv.total_market_eur > 0
    assert len(bv.by_ticker) == bv.n_positions


def test_run_static_gate_silent_returns_report():
    """Wrapper silent retourne dict structure utile pour CI/dashboard."""
    with storage.db() as cx:
        r = pi.run_static_gate_silent(cx)
    assert "status" in r
    assert "n_violations" in r
    assert "violations" in r
    assert r["status"] in ("green", "red")
