"""A5 tests : shared/integrity.py + thesis_integrity_log hash chain.

Spec red-team 07/06 nuit DECISION_QUALITY_ENGINE A5 : 7 tests dont le
CRITIQUE (payload mute -> chain_hash diverge -> verify cassee).

Sans A4 (anchor externe git tag signe / OpenTimestamps), une attaque
locale rewrite-everything peut reconstruire chain coherent. A4 = pre-requis
pour tamper-evidence reel. Mais A1-A3 + A5 deja necessaires.
"""

from __future__ import annotations

import json

import pytest

from shared.integrity import (
    GENESIS_HASH,
    canonical_payload,
    chain_append,
    compute_hash,
    verify_chain,
)

# === Test 1 : canonical reproducibility (float format strict) ===

def test_canonical_floats_format_6_decimals():
    """Hash bit-identique entre 2 builds Python differents.

    Sans format strict floats, json.dumps(0.1) varie. Le format 6 decimales
    garantit que canonical_payload(p) = canonical_payload(p) byte-for-byte.
    """
    p1 = {"price": 0.1 + 0.2}  # = 0.30000000000000004 en float
    p2 = {"price": 0.3}
    s1 = canonical_payload(p1)
    s2 = canonical_payload(p2)
    # 0.300000 (strict 6 dec) -> egal
    assert s1 == s2, f"floats diffs : {s1!r} vs {s2!r}"


def test_canonical_sort_keys_deterministic():
    """sort_keys -> ordre clefs deterministe quelque soit dict.update order."""
    p1 = {"b": 1, "a": 2}
    p2 = {"a": 2, "b": 1}
    assert canonical_payload(p1) == canonical_payload(p2)


def test_canonical_handles_nested_floats():
    """Recursive walk dict + list."""
    p1 = {"x": [1.5, {"y": 2.0}], "z": (3.14, 4.0)}
    s1 = canonical_payload(p1)
    # Tous les floats deviennent "1.500000" / "2.000000" / etc
    assert "1.500000" in s1
    assert "2.000000" in s1
    assert "3.140000" in s1


# === Test 2 : hash chain genesis + append ===

def test_genesis_hash_is_64_zeros():
    assert GENESIS_HASH == "0" * 64
    assert len(GENESIS_HASH) == 64


def test_chain_append_first_entry_uses_genesis():
    """Premier append : prev = GENESIS, new_hash deterministe."""
    prev, h = chain_append(None, {"k": 1})
    assert prev == GENESIS_HASH
    assert len(h) == 64
    # Recompute manuellement pour sanity
    assert h == compute_hash({"k": 1}, GENESIS_HASH)


def test_chain_append_chains_correctly():
    """2e entry : prev = h1, new_hash != h1."""
    _, h1 = chain_append(None, {"k": 1})
    prev2, h2 = chain_append(h1, {"k": 2})
    assert prev2 == h1
    assert h2 != h1
    assert h2 == compute_hash({"k": 2}, h1)


# === Test 3 : verify_chain happy path ===

def test_verify_chain_ok_on_well_formed():
    """Chain coherent from genesis -> ok True."""
    rows = []
    prev = GENESIS_HASH
    payloads = [{"x": i} for i in range(5)]
    for seq, p in enumerate(payloads, start=1):
        h = compute_hash(p, prev)
        rows.append({
            "seq": seq, "payload_json": json.dumps(p),
            "prev_hash": prev, "chain_hash": h,
        })
        prev = h
    ok, broken = verify_chain(rows)
    assert ok
    assert broken is None


# === Test 4 : verify_chain detects payload mutation (CRITIQUE) ===

def test_verify_chain_detects_payload_mutation():
    """LE test critique : payload mute apres insert -> verify casse.

    Sans cette propriete, A1-A3 = theater. Le but de la chain est PRECISEMENT
    de catch un attaquant qui modifie payload_json a la main en DB pour
    reviser conviction post-hoc.
    """
    rows = []
    prev = GENESIS_HASH
    payloads = [{"conviction": 3}, {"conviction": 4}, {"conviction": 5}]
    for seq, p in enumerate(payloads, start=1):
        h = compute_hash(p, prev)
        rows.append({
            "seq": seq, "payload_json": json.dumps(p),
            "prev_hash": prev, "chain_hash": h,
        })
        prev = h

    # ATTAQUE : un operateur tente de re-ecrire la row 1 conviction 3 -> 5
    # (revision post-hoc pour gonfler son skill apparent)
    rows[0]["payload_json"] = json.dumps({"conviction": 5})

    ok, broken_seq = verify_chain(rows)
    assert not ok, "payload mutation must be detected (anti-tamper)"
    assert broken_seq == 1, f"first broken seq = 1, got {broken_seq}"


# === Test 5 : verify_chain detects chain_hash mutation ===

def test_verify_chain_detects_chain_hash_mutation():
    """Mutation directe de chain_hash -> next row prev_hash ne match plus."""
    rows = []
    prev = GENESIS_HASH
    for seq in range(1, 4):
        p = {"k": seq}
        h = compute_hash(p, prev)
        rows.append({
            "seq": seq, "payload_json": json.dumps(p),
            "prev_hash": prev, "chain_hash": h,
        })
        prev = h

    # ATTAQUE : reecrit chain_hash de la row 1 (sans recomputer row 2-3)
    rows[0]["chain_hash"] = "f" * 64

    ok, broken_seq = verify_chain(rows)
    assert not ok
    assert broken_seq == 1 or broken_seq == 2  # row 1 chain_hash wrong, ou row 2 prev_hash mismatch


# === Test 6 : verify_chain empty = ok ===

def test_verify_chain_empty_is_ok():
    """No rows -> chain vide = ok (genesis non depasse, pas anomalie)."""
    ok, broken = verify_chain([])
    assert ok
    assert broken is None


# === Test 7 : verify_chain sur DB live (integration storage) ===

def test_verify_chain_through_storage_helpers(migrated_db):
    """Pipeline complet : insert_thesis_integrity_row -> get_thesis_integrity_chain
    -> verify_chain. Doctrine end-to-end."""
    from shared.storage import (
        get_thesis_integrity_chain,
        insert_thesis_integrity_row,
    )

    # Insert 3 entries
    for thesis_id in (1, 2, 3):
        res = insert_thesis_integrity_row(
            thesis_id=thesis_id,
            payload={"conviction": thesis_id, "driver": "test"},
        )
        assert res is not None
        assert "chain_hash" in res

    chain = get_thesis_integrity_chain()
    assert len(chain) == 3
    ok, broken = verify_chain(chain)
    assert ok, f"verify cassee a seq={broken}"

    # Stress test : muter directement la row en DB et reverify
    from shared import storage
    with storage.db() as cx:
        cx.execute(
            "UPDATE thesis_integrity_log SET payload_json = ? WHERE seq = 1",
            (json.dumps({"conviction": 99, "driver": "TAMPERED"}),),
        )
    chain_post_tamper = get_thesis_integrity_chain()
    ok, broken = verify_chain(chain_post_tamper)
    assert not ok, "Mutation row 1 doit etre detectee"
    assert broken == 1
