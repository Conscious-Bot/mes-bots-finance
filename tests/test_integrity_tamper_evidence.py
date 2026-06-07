"""Preuve de tamper-evidence de la chaine d'integrite (predictions commit-reveal).

DEUX niveaux de detection :
- verify_chain : attrape la mutation INCOHERENTE (edit sans rebuild aval).
- ancrage externe (OTS, simule par un head fige a T0) : attrape la mutation
  COHERENTE (rebuild complet) que verify_chain, SEUL, laisse passer. C'est la
  raison d'etre de A4 (catch #3) : sans temoin externe, un operateur motive
  reecrit une chaine valide. Ce fichier le demontre noir sur blanc.

Hermetique : fonctions pures, zero DB -> CI-safe, pas de marker live_data.
"""

import json

import pytest

from shared import integrity

SAMPLE = [
    {"id": 1, "ticker": "TSM",     "direction": "long", "horizon_days": 30,
     "baseline_price": 227.00, "probability_at_creation": 0.62, "nonce": "a" * 64},
    {"id": 2, "ticker": "ASML.AS", "direction": "long", "horizon_days": 30,
     "baseline_price": 820.95, "probability_at_creation": 0.58, "nonce": "b" * 64},
    {"id": 3, "ticker": "CCJ",     "direction": "long", "horizon_days": 30,
     "baseline_price": 94.86,  "probability_at_creation": 0.55, "nonce": "c" * 64},
]


def _build_chain(payloads):
    """Chaine depuis genesis -> (rows[{seq,payload_json,prev_hash,chain_hash}], head)."""
    rows, prev = [], integrity.GENESIS_HASH
    for i, p in enumerate(payloads, start=1):
        used, chash = integrity.chain_append(prev, p)
        rows.append({
            "seq": i,
            "payload_json": json.dumps(p, sort_keys=True),
            "prev_hash": used,
            "chain_hash": chash,
        })
        prev = chash
    return rows, prev


def test_valid_chain_verifies():
    rows, _ = _build_chain(SAMPLE)
    ok, broken = integrity.verify_chain(rows)
    assert ok is True
    assert broken is None


def test_incoherent_mutation_caught_by_verify_chain():
    """Edit d'un payload passe SANS rebuild -> verify_chain (False, seq de la 1ere maille brisee)."""
    rows, _ = _build_chain(SAMPLE)
    tampered = json.loads(rows[1]["payload_json"])
    tampered["probability_at_creation"] = 0.99  # revision post-hoc
    rows[1]["payload_json"] = json.dumps(tampered, sort_keys=True)
    ok, broken = integrity.verify_chain(rows)
    assert ok is False
    assert broken == rows[1]["seq"]  # == 2


def test_coherent_rebuild_caught_ONLY_by_external_anchor():
    """LE test critique. Operateur rebatit TOUTE la chaine apres mutation :
    verify_chain PASSE (piege) -- mais le head diverge du head ancre OTS.
    Prouve que A4 (ancrage externe) est non-optionnel.
    """
    _rows, anchored_head = _build_chain(SAMPLE)  # head fige a T0 par OTS

    forged = [dict(p) for p in SAMPLE]
    forged[1]["probability_at_creation"] = 0.99   # mutation
    forged_rows, forged_head = _build_chain(forged)  # rebuild integral coherent

    ok, broken = integrity.verify_chain(forged_rows)
    assert ok is True
    assert broken is None  # verify_chain SEUL ne voit rien

    assert forged_head != anchored_head  # <-- tamper-evidence REELLE via l'ancre


def test_reveal_recomputes_commitment():
    """Commit-reveal : payload revele + nonce reproduit le chain_hash ; un faux non."""
    rows, _ = _build_chain(SAMPLE)
    assert integrity.compute_hash(SAMPLE[0], rows[0]["prev_hash"]) == rows[0]["chain_hash"]
    forged = {**SAMPLE[0], "probability_at_creation": 0.99}
    assert integrity.compute_hash(forged, rows[0]["prev_hash"]) != rows[0]["chain_hash"]


def test_genesis_is_first_prev():
    rows, _ = _build_chain(SAMPLE[:1])
    assert rows[0]["prev_hash"] == integrity.GENESIS_HASH


def test_nonce_hides_low_entropy_payload():
    """Deux predictions identiques SAUF le nonce -> hashes differents (hiding)."""
    base = {
        "id": 9, "ticker": "MU", "direction": "long", "horizon_days": 30,
        "baseline_price": 100.0, "probability_at_creation": 0.60,
    }
    h1 = integrity.compute_hash({**base, "nonce": "1" * 64}, integrity.GENESIS_HASH)
    h2 = integrity.compute_hash({**base, "nonce": "2" * 64}, integrity.GENESIS_HASH)
    assert h1 != h2


def test_canonical_raises_on_non_primitive():
    """Catch #1 : default=str banni -> raise loud sur type non serialisable."""
    class _Weird:
        pass
    with pytest.raises(integrity.NonCanonicalTypeError):
        integrity.canonical_payload({"x": _Weird()})


def test_canonical_float_reproducible_cross_process():
    """Le footgun #1 : meme payload -> bytes identiques apres round-trip JSON (2 process)."""
    p = {"baseline_price": 227.0, "probability_at_creation": 0.6166666666}
    assert integrity.canonical_payload(p) == integrity.canonical_payload(
        json.loads(json.dumps(p))
    )
