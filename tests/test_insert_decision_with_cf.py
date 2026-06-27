"""Tests pour shared/storage.py::insert_decision_with_cf.

Ferme la dette [[manual-exec-must-create-cf]] : tout script manuel d'exec
trade doit creer atomiquement decision + decision_counterfactual sinon
rule #7 ROUGE au close.
"""

from __future__ import annotations

import pytest

from shared import storage


@pytest.fixture
def fixture_thesis(migrated_db):
    """Cree une these active de reference pour les tests."""
    import sqlite3
    cx = sqlite3.connect(migrated_db)
    cx.execute(
        "INSERT INTO theses (ticker, status, conviction, position_type, direction, "
        "entry_price, target_partial, target_full, stop_price, "
        "invalidation_triggers, opened_at, last_reviewed) "
        "VALUES ('TEST.PA', 'active', 3, 'priced', 'long', 100.0, 130.0, 160.0, 80.0, "
        "'[\"trigger1\"]', datetime('now'), date('now'))"
    )
    tid = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    cx.commit()
    cx.close()
    return tid


def test_entry_creates_decision_and_cf(migrated_db, fixture_thesis):
    """entry → decision + CF atomiquement."""
    dec_id, cf_id = storage.insert_decision_with_cf(
        ticker="TEST.PA",
        decision_type="entry",
        reasoning="[STRUCTURED] these: test | invalidation: T | conviction: 3",
        thesis_id=fixture_thesis,
        conviction=3,
        price_native=100.0,
        qty_before=0.0,
        currency="EUR",
    )
    assert dec_id is not None
    assert cf_id is not None

    import sqlite3
    cx = sqlite3.connect(migrated_db)
    row = cx.execute(
        "SELECT decision_id, ticker, decision_type, counterfactual_branch, "
        "anchor_qty_before, anchor_currency, anchor_thesis_id, anchor_conviction "
        "FROM decision_counterfactual WHERE id=?", (cf_id,)
    ).fetchone()
    assert row == (dec_id, "TEST.PA", "entry", "hold", 0.0, "EUR", fixture_thesis, 3)


def test_scale_in_creates_both(migrated_db, fixture_thesis):
    """scale_in → CF aussi (qty_before > 0)."""
    _dec_id, cf_id = storage.insert_decision_with_cf(
        ticker="TEST.PA", decision_type="scale_in",
        reasoning="r", thesis_id=fixture_thesis, conviction=3,
        price_native=110.0, qty_before=5.0, currency="EUR",
    )
    assert cf_id is not None


def test_partial_exit_creates_both(migrated_db, fixture_thesis):
    _dec_id, cf_id = storage.insert_decision_with_cf(
        ticker="TEST.PA", decision_type="partial_exit",
        reasoning="r", thesis_id=fixture_thesis, conviction=3,
        price_native=125.0, qty_before=10.0, currency="EUR",
    )
    assert cf_id is not None


def test_full_exit_creates_both(migrated_db, fixture_thesis):
    _dec_id, cf_id = storage.insert_decision_with_cf(
        ticker="TEST.PA", decision_type="full_exit",
        reasoning="r", thesis_id=fixture_thesis, conviction=3,
        price_native=150.0, qty_before=10.0, currency="EUR",
    )
    assert cf_id is not None


def test_full_exit_closes_positions_meta(migrated_db, fixture_thesis):
    """Cure STMPA fantome 27/06 — full_exit doit UPDATE positions_meta.status='closed'.

    Avant cette cure : full_exit laissait positions_meta.status='open' avec qty=0
    (fantome a fermer) -> rouge test_pipeline_end_to_end.
    """
    import sqlite3
    cx = sqlite3.connect(migrated_db)
    # Setup : ticker positions_meta ouvert
    cx.execute(
        "INSERT INTO positions_meta (ticker, status, account, wrapper) "
        "VALUES ('TEST.PA', 'open', 'PEA', 'PEA')"
    )
    cx.commit()
    cx.close()

    # Act : full_exit via helper
    storage.insert_decision_with_cf(
        ticker="TEST.PA",
        decision_type="full_exit",
        reasoning="liquidation",
        thesis_id=fixture_thesis,
        conviction=3,
        price_native=150.0,
        qty_before=10.0,
        currency="EUR",
    )

    # Assert : positions_meta.status passe a 'closed'
    cx = sqlite3.connect(migrated_db)
    status = cx.execute(
        "SELECT status FROM positions_meta WHERE ticker='TEST.PA'"
    ).fetchone()[0]
    cx.close()
    assert status == "closed", f"Expected 'closed' apres full_exit, got {status!r}"


def test_full_exit_close_is_idempotent(migrated_db, fixture_thesis):
    """Si positions_meta deja closed, full_exit ne crashe pas et laisse closed."""
    import sqlite3
    cx = sqlite3.connect(migrated_db)
    cx.execute(
        "INSERT INTO positions_meta (ticker, status, account, wrapper) "
        "VALUES ('TEST.PA', 'closed', 'PEA', 'PEA')"
    )
    cx.commit()
    cx.close()

    storage.insert_decision_with_cf(
        ticker="TEST.PA", decision_type="full_exit",
        reasoning="r", thesis_id=fixture_thesis, conviction=3,
        price_native=150.0, qty_before=10.0, currency="EUR",
    )

    cx = sqlite3.connect(migrated_db)
    status = cx.execute(
        "SELECT status FROM positions_meta WHERE ticker='TEST.PA'"
    ).fetchone()[0]
    cx.close()
    assert status == "closed"


def test_partial_exit_does_NOT_close_positions_meta(migrated_db, fixture_thesis):
    """Garde-fou : partial_exit ne doit PAS fermer positions_meta (qty reste > 0)."""
    import sqlite3
    cx = sqlite3.connect(migrated_db)
    cx.execute(
        "INSERT INTO positions_meta (ticker, status, account, wrapper) "
        "VALUES ('TEST.PA', 'open', 'PEA', 'PEA')"
    )
    cx.commit()
    cx.close()

    storage.insert_decision_with_cf(
        ticker="TEST.PA", decision_type="partial_exit",
        reasoning="r", thesis_id=fixture_thesis, conviction=3,
        price_native=125.0, qty_before=10.0, currency="EUR",
    )

    cx = sqlite3.connect(migrated_db)
    status = cx.execute(
        "SELECT status FROM positions_meta WHERE ticker='TEST.PA'"
    ).fetchone()[0]
    cx.close()
    assert status == "open", f"partial_exit ne doit pas fermer, got {status!r}"


def test_override_skips_cf(migrated_db, fixture_thesis):
    """override → decision SANS CF (pas un trade materiel)."""
    dec_id, cf_id = storage.insert_decision_with_cf(
        ticker="TEST.PA", decision_type="override",
        reasoning="re-anchor structural", thesis_id=fixture_thesis, conviction=3,
        price_native=110.0, qty_before=5.0, currency="EUR",
    )
    assert dec_id is not None
    assert cf_id is None  # explicit None for non-material decisions


def test_no_action_flag_skips_cf(migrated_db, fixture_thesis):
    """no_action_flag → decision SANS CF (statu quo)."""
    _dec_id, cf_id = storage.insert_decision_with_cf(
        ticker="TEST.PA", decision_type="no_action_flag",
        reasoning="thesis unchanged hold", thesis_id=fixture_thesis, conviction=3,
        price_native=110.0, qty_before=5.0, currency="EUR",
    )
    assert cf_id is None


def test_invalid_decision_type_raises(migrated_db, fixture_thesis):
    with pytest.raises(ValueError, match="decision_type must be in"):
        storage.insert_decision_with_cf(
            ticker="TEST.PA", decision_type="invalid_type",
            reasoning="r", thesis_id=fixture_thesis, conviction=3,
            price_native=100.0, qty_before=0.0, currency="EUR",
        )


def test_satisfies_rule_7(migrated_db, fixture_thesis):
    """End-to-end : un trade insere via helper satisfait rule #7 du gate."""
    from shared import position_invariants as pi

    storage.insert_decision_with_cf(
        ticker="TEST.PA", decision_type="entry",
        reasoning="r", thesis_id=fixture_thesis, conviction=3,
        price_native=100.0, qty_before=0.0, currency="EUR",
    )

    import sqlite3
    cx = sqlite3.connect(migrated_db)
    violations = pi._check_no_recent_material_decision_orphan(cx)
    # Aucune violation rule #7 pour la decision qu'on vient d'inserer
    assert not any("TEST.PA" in v for v in violations)
    cx.close()


def test_atomic_with_external_conn(migrated_db, fixture_thesis):
    """Si conn passe en arg, l'helper N'OUVRE PAS de conn separee + ne commit pas.

    Permet d'embarquer dans une transaction plus large.
    """
    import sqlite3
    cx = sqlite3.connect(migrated_db)
    cx.execute("BEGIN")
    try:
        dec_id, _cf_id = storage.insert_decision_with_cf(
            ticker="TEST.PA", decision_type="entry",
            reasoning="r", thesis_id=fixture_thesis, conviction=3,
            price_native=100.0, qty_before=0.0, currency="EUR",
            conn=cx,
        )
        assert dec_id is not None
        # Avant commit, lecture sur AUTRE connection ne voit pas la decision
        cx_other = sqlite3.connect(migrated_db)
        n_other = cx_other.execute("SELECT COUNT(*) FROM decisions WHERE id=?", (dec_id,)).fetchone()[0]
        cx_other.close()
        assert n_other == 0  # tx non-committed isolation
        cx.commit()
    finally:
        cx.close()
