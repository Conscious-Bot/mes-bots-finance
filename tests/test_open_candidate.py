"""v2.c.2 tests : open_candidate + supersede rule (ADR 010 Addendum v2.c).

User 01/06 : "Equivalent c.2 du piege de c.1 : le supersede doit void TOUS
les candidats open meme (ticker, bias), pas en supposer exactement un. Et
que le test assert qu'il ne reste aucun open orphelin apres. Sinon tu
accumules des candidats fantomes."

Le test critique = inserer DELIBEREMENT 3 open meme (ticker, bias)
(simulant un bug/race), appeler open_candidate, asserter qu'aucun
orphelin open ne reste.

Note : trigger d'emission (regle -> open_candidate) NON-CABLE en v2.c.5.
Ces tests verrouillent l'API ; la creation reste manuelle pour l'instant.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from intelligence.bias_events import open_candidate


def _schema_minimal(cx: sqlite3.Connection) -> None:
    """Clone DDL migration 0023 (avec note column)."""
    cx.executescript("""
        CREATE TABLE bias_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            ticker TEXT,
            bias TEXT NOT NULL CHECK(bias IN ('lock_in', 'fomo_greed', 'other')),
            action TEXT NOT NULL CHECK(action IN ('acted_on_bias', 'resisted')),
            decision_json TEXT NOT NULL,
            counterfactual_json TEXT NOT NULL,
            resolution_json TEXT,
            status TEXT NOT NULL DEFAULT 'open'
                CHECK(status IN ('open', 'resolved', 'void',
                                 'thesis_invalidated', 'reentered',
                                 'missing_data')),
            source TEXT NOT NULL CHECK(source IN ('auto_detected',
                                                  'telegram_tap', 'manual')),
            thesis_id INTEGER, prediction_id INTEGER, note_tags_json TEXT,
            horizon_days INTEGER NOT NULL,
            resolve_at TEXT NOT NULL
        );
    """)


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """In-disk SQLite isole + monkeypatch DB_PATH."""
    db = tmp_path / "test.db"
    cx = sqlite3.connect(db)
    _schema_minimal(cx)
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db)
    return db


def _count(db: Path, sql: str, params: tuple = ()) -> int:
    cx = sqlite3.connect(db)
    n = cx.execute(sql, params).fetchone()[0]
    cx.close()
    return n


# ─── Cas basiques ──────────────────────────────────────────────────────────


def test_open_candidate_table_vide_cree_1_row_open(isolated_db: Path) -> None:
    """Table vide -> open_candidate insert 1 row status='open'."""
    new_id = open_candidate(
        ticker="NVDA", bias="lock_in",
        discipline_said={"action": "hold", "ref": "rule:rightsize_c4"},
        horizon_days=30, anchor_price_eur=154.45,
        initial_qty=100.0, discipline_expected_delta=0.0,
    )
    assert isinstance(new_id, int) and new_id > 0
    assert _count(isolated_db, "SELECT COUNT(*) FROM bias_events") == 1
    assert _count(isolated_db, "SELECT COUNT(*) FROM bias_events WHERE status='open'") == 1


def test_open_candidate_persiste_captured_at_event_true(isolated_db: Path) -> None:
    """Invariant falsifiabilite ADR §3 : decision_json doit contenir
    captured_at_event=true."""
    open_candidate(
        ticker="NVDA", bias="lock_in",
        discipline_said={"action": "hold", "ref": "rule:x"},
        horizon_days=30, anchor_price_eur=154.45,
        initial_qty=100.0, discipline_expected_delta=0.0,
    )
    cx = sqlite3.connect(isolated_db)
    row = cx.execute("SELECT decision_json FROM bias_events WHERE id=1").fetchone()
    cx.close()
    decision = json.loads(row[0])
    assert decision["captured_at_event"] is True


def test_open_candidate_counterfactual_contient_initial_qty_et_expected_delta(
    isolated_db: Path,
) -> None:
    """v2.c.3 (resolve refactor) lit ces champs pour classify_net_delta."""
    open_candidate(
        ticker="NVDA", bias="lock_in",
        discipline_said={"action": "rightsize", "ref": "r"},
        horizon_days=30, anchor_price_eur=154.45,
        initial_qty=100.0, discipline_expected_delta=-20.0,
    )
    cx = sqlite3.connect(isolated_db)
    row = cx.execute("SELECT counterfactual_json FROM bias_events WHERE id=1").fetchone()
    cx.close()
    cf = json.loads(row[0])
    assert cf["initial_qty"] == 100.0
    assert cf["discipline_expected_delta"] == -20.0
    assert cf["counterfactual_method"] == "cash_idle"
    assert cf["anchor_price_eur"] == 154.45


# ─── SUPERSEDE : le piege c.2 ──────────────────────────────────────────────


def test_supersede_void_ancien_quand_1_existe(isolated_db: Path) -> None:
    """Cas normal : 1 candidat open existe, on en ouvre un nouveau -> ancien void."""
    id1 = open_candidate(
        ticker="NVDA", bias="lock_in",
        discipline_said={"action": "hold", "ref": "r1"},
        horizon_days=30, anchor_price_eur=154.45,
        initial_qty=100.0, discipline_expected_delta=0.0,
    )
    id2 = open_candidate(
        ticker="NVDA", bias="lock_in",
        discipline_said={"action": "rightsize", "ref": "r2"},
        horizon_days=14, anchor_price_eur=160.0,
        initial_qty=100.0, discipline_expected_delta=-30.0,
    )
    assert id2 > id1
    # Verifie : ancien void, nouveau open, total 2 rows
    cx = sqlite3.connect(isolated_db)
    rows = cx.execute(
        "SELECT id, status FROM bias_events WHERE ticker='NVDA' AND bias='lock_in' "
        "ORDER BY id"
    ).fetchall()
    cx.close()
    assert rows == [(id1, "void"), (id2, "open")]


def test_supersede_void_3_orphelins_meme_ticker_bias_aucun_open_residuel(
    isolated_db: Path,
) -> None:
    """USER 01/06 PIEGE C.2 : INSERT MANUEL de 3 open meme (ticker, bias)
    (simulant un bug/race historique). open_candidate doit void TOUS les
    3 + creer 1 nouveau. Assert : APRES, il reste EXACTEMENT 1 open meme
    (ticker, bias) -- aucun orphelin."""
    cx = sqlite3.connect(isolated_db)
    cf = json.dumps({
        "anchor_price_eur": 100.0,
        "counterfactual_method": "cash_idle",
        "discipline_expected_delta": 0.0,
        "horizon_days": 30,
        "initial_qty": 100.0,
    }, sort_keys=True)
    for i in range(3):
        cx.execute(
            "INSERT INTO bias_events "
            "(created_at, ticker, bias, action, decision_json, counterfactual_json, "
            " status, source, horizon_days, resolve_at) "
            "VALUES (?, 'NVDA', 'lock_in', 'acted_on_bias', '{}', ?, "
            "'open', 'manual', 30, ?)",
            (f"2026-05-0{i+1}T12:00:00Z", cf, f"2026-06-0{i+1}T12:00:00Z"),
        )
    cx.commit()
    cx.close()
    # 3 open orphelins existants -- bug historique simule
    assert _count(
        isolated_db,
        "SELECT COUNT(*) FROM bias_events WHERE ticker='NVDA' AND bias='lock_in' "
        "AND status='open'",
    ) == 3

    new_id = open_candidate(
        ticker="NVDA", bias="lock_in",
        discipline_said={"action": "hold", "ref": "rule:nouveau"},
        horizon_days=30, anchor_price_eur=180.0,
        initial_qty=100.0, discipline_expected_delta=0.0,
    )

    # CRITIQUE : APRES open_candidate, il reste EXACTEMENT 1 open meme
    # (ticker, bias) -- le nouveau. Les 3 orphelins sont voided.
    open_residuel = _count(
        isolated_db,
        "SELECT COUNT(*) FROM bias_events WHERE ticker='NVDA' AND bias='lock_in' "
        "AND status='open'",
    )
    assert open_residuel == 1, (
        f"Attendu 1 open (le nouveau), obtenu {open_residuel}. Si > 1 : "
        f"supersede n'a pas void tous les orphelins. Si 0 : INSERT failed."
    )

    void_total = _count(
        isolated_db,
        "SELECT COUNT(*) FROM bias_events WHERE ticker='NVDA' AND bias='lock_in' "
        "AND status='void'",
    )
    assert void_total == 3, f"Attendu 3 void, obtenu {void_total}"

    # Et le seul open = le nouveau qu'on vient de creer
    cx2 = sqlite3.connect(isolated_db)
    only_open_id = cx2.execute(
        "SELECT id FROM bias_events WHERE ticker='NVDA' AND bias='lock_in' "
        "AND status='open'"
    ).fetchone()[0]
    cx2.close()
    assert only_open_id == new_id


def test_supersede_ne_touche_pas_meme_ticker_bias_different(
    isolated_db: Path,
) -> None:
    """ticker NVDA + bias lock_in existant ouvert. open_candidate sur NVDA
    + bias fomo_greed -> ancien reste open (bias different = stream
    independant)."""
    id_lock = open_candidate(
        ticker="NVDA", bias="lock_in",
        discipline_said={"action": "hold", "ref": "r"},
        horizon_days=30, anchor_price_eur=100.0,
        initial_qty=100.0, discipline_expected_delta=0.0,
    )
    id_fomo = open_candidate(
        ticker="NVDA", bias="fomo_greed",
        discipline_said={"action": "exit", "ref": "r"},
        horizon_days=30, anchor_price_eur=100.0,
        initial_qty=100.0, discipline_expected_delta=-100.0,
    )
    # Les 2 doivent etre OPEN (streams independants)
    open_nvda = _count(
        isolated_db,
        "SELECT COUNT(*) FROM bias_events WHERE ticker='NVDA' AND status='open'",
    )
    assert open_nvda == 2
    cx = sqlite3.connect(isolated_db)
    statuses = dict(cx.execute(
        "SELECT id, status FROM bias_events WHERE ticker='NVDA'"
    ).fetchall())
    cx.close()
    assert statuses[id_lock] == "open"
    assert statuses[id_fomo] == "open"


def test_supersede_ne_touche_pas_ticker_different_meme_bias(
    isolated_db: Path,
) -> None:
    """ticker NVDA + bias lock_in existant ouvert. open_candidate sur AMD +
    bias lock_in -> NVDA reste open (ticker different = stream different)."""
    id_nvda = open_candidate(
        ticker="NVDA", bias="lock_in",
        discipline_said={"action": "hold", "ref": "r"},
        horizon_days=30, anchor_price_eur=100.0,
        initial_qty=100.0, discipline_expected_delta=0.0,
    )
    id_amd = open_candidate(
        ticker="AMD", bias="lock_in",
        discipline_said={"action": "rightsize", "ref": "r"},
        horizon_days=30, anchor_price_eur=200.0,
        initial_qty=50.0, discipline_expected_delta=-10.0,
    )
    cx = sqlite3.connect(isolated_db)
    statuses = dict(cx.execute(
        "SELECT id, status FROM bias_events WHERE status='open'"
    ).fetchall())
    cx.close()
    assert statuses[id_nvda] == "open"
    assert statuses[id_amd] == "open"
