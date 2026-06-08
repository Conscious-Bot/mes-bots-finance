"""Tests verrouillants Datum + derive (SOCLE Phase 0 / Geste 1).

Walking-skeleton inclut un VRAI input HY_OAS via fixture FRED -- pas seulement
des Datums synthetiques. Le tracer-bullet a deja sauve C6 (cf L24 LESSONS) ;
on l'applique a Phase 0 par discipline.

Cf SPEC_SOCLE.md S1-S2 + memory/feedback_walking_skeleton.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.datum import Datum, derive

# === Test 1 : Datum frozen + extra forbid ===


def test_datum_frozen_no_mutation() -> None:
    d = Datum(value=42.0, asof="2026-06-08T10:00:00Z", source="test:fixture")
    from pydantic import ValidationError
    with pytest.raises((ValueError, AttributeError, TypeError, ValidationError)):
        d.value = 99.0  # type: ignore[misc]


def test_datum_extra_forbid() -> None:
    """Un champ inconnu = erreur (anti-tampering downstream qui ajouterait des champs)."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Datum(value=1.0, asof="2026-06-08T10:00:00Z", source="t", garbage="bad")  # type: ignore[call-arg]


def test_datum_defaults() -> None:
    """Defaults : confidence=1.0, parents=(), op=None, degraded=False."""
    d = Datum(value=1.0, asof="2026-06-08T10:00:00Z", source="leaf")
    assert d.confidence == 1.0
    assert d.parents == ()
    assert d.op is None
    assert d.degraded is False


# === Test 2 : id content-hash deterministe (Merkle-DAG seed) ===


def test_id_deterministic_same_inputs() -> None:
    """Meme value+asof+source+parents+op => meme id (sha256 stable)."""
    d1 = Datum(value=4.25, asof="2026-06-08T10:00:00Z", source="FRED:BAMLH0A0HYM2")
    d2 = Datum(value=4.25, asof="2026-06-08T10:00:00Z", source="FRED:BAMLH0A0HYM2")
    assert d1.id == d2.id
    assert len(d1.id) == 64  # sha256 hex


def test_id_changes_on_value() -> None:
    d1 = Datum(value=4.25, asof="2026-06-08T10:00:00Z", source="s")
    d2 = Datum(value=4.26, asof="2026-06-08T10:00:00Z", source="s")
    assert d1.id != d2.id


def test_id_changes_on_parents() -> None:
    """Different parents = different id (la lignee distingue le Datum)."""
    d_no_parents = Datum(value=10.0, asof="2026-06-08T10:00:00Z", source="derived")
    d_with_parents = Datum(value=10.0, asof="2026-06-08T10:00:00Z", source="derived",
                            parents=("abc", "def"))
    assert d_no_parents.id != d_with_parents.id


def test_id_changes_on_op() -> None:
    d_no_op = Datum(value=10.0, asof="2026-06-08T10:00:00Z", source="derived")
    d_with_op = Datum(value=10.0, asof="2026-06-08T10:00:00Z", source="derived", op="sum")
    assert d_no_op.id != d_with_op.id


def test_id_stable_across_dict_ordering() -> None:
    """Dict values stable cross-platform (json sort_keys)."""
    d1 = Datum(value={"b": 2, "a": 1}, asof="2026-06-08T10:00:00Z", source="s")
    d2 = Datum(value={"a": 1, "b": 2}, asof="2026-06-08T10:00:00Z", source="s")
    assert d1.id == d2.id


# === Test 3 : derive() propagation (la regle qui rend M1+fail-closed gratis) ===


def test_derive_value_via_fn() -> None:
    a = Datum(value=3.0, asof="2026-06-08T10:00:00Z", source="A")
    b = Datum(value=4.0, asof="2026-06-08T10:00:00Z", source="B")
    out = derive(lambda x, y: x + y, a, b, op="sum")
    assert out.value == 7.0


def test_derive_asof_is_min() -> None:
    """asof = le plus vieux contributeur. M1 honnete."""
    recent = Datum(value=1.0, asof="2026-06-08T12:00:00Z", source="A")
    old = Datum(value=2.0, asof="2026-06-01T10:00:00Z", source="B")
    out = derive(lambda x, y: x + y, recent, old)
    assert out.asof == "2026-06-01T10:00:00Z"


def test_derive_confidence_is_min() -> None:
    """Confiance = le plus faible dicte (fail-closed sur incertitude)."""
    a = Datum(value=1.0, asof="2026-06-08T10:00:00Z", source="A", confidence=0.9)
    b = Datum(value=1.0, asof="2026-06-08T10:00:00Z", source="B", confidence=0.3)
    out = derive(lambda x, y: x + y, a, b)
    assert out.confidence == pytest.approx(0.3)


def test_derive_degraded_any_propagates() -> None:
    """degraded propage : si UN input est degraded, output est degraded."""
    clean = Datum(value=1.0, asof="2026-06-08T10:00:00Z", source="A", degraded=False)
    stale = Datum(value=1.0, asof="2026-06-08T10:00:00Z", source="B", degraded=True)
    out = derive(lambda x, y: x + y, clean, stale)
    assert out.degraded is True


def test_derive_degraded_false_if_all_clean() -> None:
    a = Datum(value=1.0, asof="2026-06-08T10:00:00Z", source="A", degraded=False)
    b = Datum(value=1.0, asof="2026-06-08T10:00:00Z", source="B", degraded=False)
    out = derive(lambda x, y: x + y, a, b)
    assert out.degraded is False


def test_derive_parents_captures_input_ids() -> None:
    """Lignage : parents tuple = ids des inputs. C'est le seed du graphe."""
    a = Datum(value=1.0, asof="2026-06-08T10:00:00Z", source="A")
    b = Datum(value=2.0, asof="2026-06-08T10:00:00Z", source="B")
    out = derive(lambda x, y: x + y, a, b, op="sum")
    assert out.parents == (a.id, b.id)
    # Et c'est un tuple, pas une list (immutable)
    assert isinstance(out.parents, tuple)


def test_derive_op_recorded() -> None:
    a = Datum(value=1.0, asof="2026-06-08T10:00:00Z", source="A")
    out = derive(lambda x: x * 2, a, op="double")
    assert out.op == "double"


def test_derive_source_is_derived() -> None:
    a = Datum(value=1.0, asof="2026-06-08T10:00:00Z", source="A")
    out = derive(lambda x: x, a)
    assert out.source == "derived"


def test_derive_requires_inputs() -> None:
    with pytest.raises(ValueError, match="at least 1 input"):
        derive(lambda: 0)


# === Test 4 : composition multi-niveau (graphe profond) ===


def test_derive_chain_captures_full_lineage() -> None:
    """Trois niveaux : a, b -> c -> d. d.parents pointe c.id. c.parents pointe a.id, b.id.

    La chaine parents forme un Merkle-DAG navigable (le graphe vivant en germe).
    """
    a = Datum(value=2.0, asof="2026-06-08T10:00:00Z", source="A")
    b = Datum(value=3.0, asof="2026-06-08T10:00:00Z", source="B")
    c = derive(lambda x, y: x + y, a, b, op="add_ab")  # c.value = 5.0
    d = derive(lambda x: x * 2, c, op="double_c")       # d.value = 10.0
    assert d.value == 10.0
    assert d.parents == (c.id,)
    assert c.parents == (a.id, b.id)
    # d != c en id (different value, different parents, different op)
    assert d.id != c.id


# === Test 5 : WALKING-SKELETON -- vrai input HY_OAS via fixture FRED (cf L24) ===


@pytest.fixture(scope="module")
def hy_oas_observations() -> list[dict]:
    """FRED BAMLH0A0HYM2 fixture : observations ordered most-recent-first."""
    path = Path(__file__).parent / "fixtures" / "hy_oas_fred_2026-06-08.json"
    with path.open() as f:
        return json.load(f)["observations"]


def test_walking_skeleton_hy_oas_traverses_datum_and_derive(hy_oas_observations) -> None:
    """Tracer-bullet : un vrai HY_OAS (FRED BAMLH0A0HYM2 dernier point dispo)
    -> Datum leaf -> derive (multiplier par 100bp -> bps) -> assert lignage capture.

    Discipline L24 : ne pas valider le primitive uniquement sur mocks. Un vrai
    point FRED traverse Datum+derive avant qu'on construise les gateways dessus.
    """
    # Premier element = plus recent (ordered most-recent-first)
    last_obs = hy_oas_observations[0]
    raw_value_pct = float(last_obs["value"])  # ex. 3.10 (pourcentage)
    raw_asof = last_obs["date"] + "T00:00:00Z"

    # Leaf Datum : sortie d'un futur gateway FRED
    leaf = Datum(
        value=raw_value_pct,
        asof=raw_asof,
        source="FRED:BAMLH0A0HYM2",
        confidence=0.95,  # source officielle, confiance haute
    )
    assert leaf.value == raw_value_pct
    assert leaf.parents == ()  # leaf : sortie gateway, pas de parents

    # Derive : pourcentage -> basis points (operation triviale, focus sur la propagation)
    bps = derive(lambda pct: pct * 100, leaf, op="pct_to_bps")
    assert bps.value == raw_value_pct * 100
    assert bps.asof == raw_asof  # propage (seul input)
    assert bps.confidence == pytest.approx(0.95)  # propage (seul input)
    assert bps.parents == (leaf.id,)  # lignage capture
    assert bps.source == "derived"
    assert bps.op == "pct_to_bps"
    # Content-hash stable : meme dataset, meme leaf, meme op = meme id
    leaf2 = Datum(
        value=raw_value_pct, asof=raw_asof, source="FRED:BAMLH0A0HYM2", confidence=0.95
    )
    bps2 = derive(lambda pct: pct * 100, leaf2, op="pct_to_bps")
    assert bps.id == bps2.id  # Merkle-DAG reproductible


def test_walking_skeleton_propagation_under_degraded(hy_oas_observations) -> None:
    """Si le gateway marque leaf degraded (stale), derive propage."""
    last_obs = hy_oas_observations[0]
    raw_value_pct = float(last_obs["value"])
    raw_asof = last_obs["date"] + "T00:00:00Z"

    leaf_stale = Datum(
        value=raw_value_pct, asof=raw_asof, source="FRED:BAMLH0A0HYM2",
        confidence=0.95, degraded=True,  # gateway l'a marque (e.g. age > SLA)
    )
    out = derive(lambda x: x * 100, leaf_stale, op="pct_to_bps")
    assert out.degraded is True  # propagation automatique fail-closed
