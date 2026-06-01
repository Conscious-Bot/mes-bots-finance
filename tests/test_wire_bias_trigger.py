"""v2.c.5 tests : wire_bias_trigger -- l'interrupteur live.

User 01/06 cadre :
> c.5 est observation-only -- il logge des candidats, il ne change rien a
> ce que le bot decide ni au comportement. Le danger reel est le sur-
> declenchement (#1) ; le reste est de la greffe propre.

5 tests canoniques :
1. reco nouvelle              -> exactement 1 candidat
2. reco recurrente identique  -> aucun nouveau, created_at INCHANGE (cle)
3. reco changee               -> supersede (void + nouveau)
4. open_candidate echoue      -> caller survit (fail-safe)
5. pas de contexte (recos=[]) -> aucun candidat
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from intelligence.bias_events import wire_bias_trigger


def _schema_minimal(cx: sqlite3.Connection) -> None:
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
    db = tmp_path / "test.db"
    cx = sqlite3.connect(db)
    _schema_minimal(cx)
    cx.commit()
    cx.close()
    monkeypatch.setattr("shared.storage.DB_PATH", db)
    return db


def _reco(
    *,
    ticker: str = "NVDA",
    bias: str = "lock_in",
    action: str = "rightsize",
    ref: str = "rule:cap_c4",
    expected_delta: float = -20.0,
    anchor_eur: float = 154.45,
    initial_qty: float = 100.0,
    horizon_days: int = 30,
) -> dict:
    return {
        "ticker": ticker, "bias": bias,
        "discipline_said": {"action": action, "ref": ref},
        "horizon_days": horizon_days,
        "anchor_price_eur": anchor_eur,
        "initial_qty": initial_qty,
        "discipline_expected_delta": expected_delta,
    }


def _query(db: Path, sql: str, params: tuple = ()) -> list[tuple]:
    cx = sqlite3.connect(db)
    rows = cx.execute(sql, params).fetchall()
    cx.close()
    return rows


# ─── Test #1 : reco nouvelle -> 1 candidat exactement ──────────────────────


def test_reco_nouvelle_ouvre_exactement_1_candidat(isolated_db: Path) -> None:
    """Cas le plus simple : aucun open existant, 1 reco emise -> 1 open."""
    stats = wire_bias_trigger([_reco()])
    assert stats == {"opened": 1, "kept": 0, "superseded": 0, "errors": 0}
    rows = _query(
        isolated_db,
        "SELECT COUNT(*) FROM bias_events WHERE ticker='NVDA' AND bias='lock_in' "
        "AND status='open'",
    )
    assert rows[0][0] == 1


# ─── Test #2 : reco recurrente identique -> NO-OP, created_at preserve ────
#     (LE TEST CLE -- anti-piege #1 sur-declenchement)


def test_reco_recurrente_identique_no_op_created_at_inchange(
    isolated_db: Path,
) -> None:
    """USER 01/06 PIEGE #1 -- le test CLE : si la regle ressort la meme reco
    a chaque cycle (chaque brief, chaque /tiers), open_candidate ne doit
    PAS se redeclencher. Sinon supersede en boucle remet created_at a zero
    et la fenetre n'accumule jamais.

    Setup : 1 reco emise initialement. Puis on simule 3 ouvertures avec la
    MEME reco (mais a des moments differents) pour mimer cycles successifs.
    Assertion : 1 seul open, son created_at == celui du premier appel.
    """
    # Emission initiale
    stats1 = wire_bias_trigger([_reco()])
    assert stats1["opened"] == 1
    rows1 = _query(
        isolated_db,
        "SELECT id, created_at FROM bias_events "
        "WHERE ticker='NVDA' AND bias='lock_in' AND status='open'",
    )
    assert len(rows1) == 1
    original_id, original_created_at = rows1[0]

    # Simulate cycles : on attend un peu et on re-appelle 3x avec MEME reco
    time.sleep(0.05)
    stats2 = wire_bias_trigger([_reco()])
    time.sleep(0.05)
    stats3 = wire_bias_trigger([_reco()])
    time.sleep(0.05)
    stats4 = wire_bias_trigger([_reco()])

    assert stats2 == stats3 == stats4 == {
        "opened": 0, "kept": 1, "superseded": 0, "errors": 0,
    }

    # CRITIQUE : 1 seul open, MEME id, MEME created_at qu'a la 1ere emission
    rows_after = _query(
        isolated_db,
        "SELECT id, created_at FROM bias_events "
        "WHERE ticker='NVDA' AND bias='lock_in' AND status='open'",
    )
    assert len(rows_after) == 1, "Aucun supersede attendu sur reco identique"
    assert rows_after[0][0] == original_id, "id non preserve = supersede en boucle"
    assert rows_after[0][1] == original_created_at, (
        "created_at modifie = le supersede a vide la fenetre. "
        "PIEGE #1 = wire_bias_trigger surdeclencheur."
    )

    # Aucun void parasite n'a ete cree
    void_count = _query(
        isolated_db,
        "SELECT COUNT(*) FROM bias_events WHERE status='void'",
    )[0][0]
    assert void_count == 0, "Voids parasites = supersede a tort"


# ─── Test #3 : reco materiellement changee -> supersede ────────────────────


def test_reco_changee_supersede(isolated_db: Path) -> None:
    """Cas legitime : la regle dit 'rightsize' au cycle T, puis 'exit' au
    cycle T+1 (these invalidee, par ex.). C'est materiellement different
    -> supersede : void l'ancien + INSERT le nouveau."""
    # T : rightsize
    wire_bias_trigger([_reco(action="rightsize", ref="rule:cap_c4")])
    # T+1 : same ticker+bias mais action change
    stats = wire_bias_trigger([_reco(
        action="exit", ref="rule:kill_criteria_pmf",
        expected_delta=-100.0,  # exit full
    )])
    assert stats == {"opened": 0, "kept": 0, "superseded": 1, "errors": 0}

    # 1 open (le nouveau exit), 1 void (l'ancien rightsize)
    rows = _query(
        isolated_db,
        "SELECT status, decision_json FROM bias_events "
        "WHERE ticker='NVDA' AND bias='lock_in' ORDER BY id",
    )
    assert len(rows) == 2
    assert rows[0][0] == "void"
    assert rows[1][0] == "open"
    # Le nouveau open contient bien la nouvelle reco
    import json
    new_decision = json.loads(rows[1][1])
    assert new_decision["discipline_said"]["action"] == "exit"
    assert new_decision["discipline_said"]["ref"] == "rule:kill_criteria_pmf"


def test_reco_changee_meme_action_ref_different_supersede(
    isolated_db: Path,
) -> None:
    """Granularite : meme action='rightsize' mais ref change (e.g., regle de
    cap c4 -> c3 apres downgrade conviction) -> supersede."""
    wire_bias_trigger([_reco(action="rightsize", ref="rule:cap_c4")])
    stats = wire_bias_trigger([_reco(action="rightsize", ref="rule:cap_c3")])
    assert stats["superseded"] == 1
    assert stats["kept"] == 0


# ─── Test #4 : open_candidate echoue -> fail-safe ──────────────────────────


def test_open_candidate_failure_does_not_break_caller(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """USER 01/06 FAIL-SAFE STRICT : open_candidate raise -> wire_bias_trigger
    NE TRAVERSE PAS l'exception. Stats.errors+=1, mais le caller (brief,
    /tiers) survit.

    Sans ce test, un bug dans open_candidate (e.g., FK invalide, contrainte
    CHECK ratee) casserait le brief matinal -- inacceptable."""
    def boom(**kwargs):
        raise RuntimeError("simulated bug in open_candidate")

    monkeypatch.setattr("intelligence.bias_events.open_candidate", boom)
    # Doit NE PAS raise
    stats = wire_bias_trigger([_reco(), _reco(ticker="AMD")])
    assert stats["errors"] == 2
    assert stats["opened"] == 0


def test_failure_sur_une_reco_ne_bloque_pas_la_suivante(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Granularite fail-safe : la 1ere reco fait raise, mais la 2eme se
    traite quand meme. Une reco buggee n'empoisonne pas la boucle."""
    real_open = __import__(
        "intelligence.bias_events", fromlist=["open_candidate"]
    ).open_candidate
    call_count = {"n": 0}

    def selective_boom(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("only first raises")
        return real_open(**kwargs)

    monkeypatch.setattr("intelligence.bias_events.open_candidate", selective_boom)
    stats = wire_bias_trigger([
        _reco(ticker="NVDA"),  # raise
        _reco(ticker="AMD"),   # succeed
    ])
    assert stats["errors"] == 1
    assert stats["opened"] == 1
    # AMD bien insere malgre NVDA buggee
    n_amd = _query(
        isolated_db,
        "SELECT COUNT(*) FROM bias_events WHERE ticker='AMD' AND status='open'",
    )[0][0]
    assert n_amd == 1


# ─── Test #5 : pas de contexte -> aucun candidat ───────────────────────────


def test_recommandations_vides_aucun_candidat(isolated_db: Path) -> None:
    """Pas de reco emise (e.g., aucun overcap, aucune these en exit) -> rien
    a faire. La fonction est un no-op."""
    stats = wire_bias_trigger([])
    assert stats == {"opened": 0, "kept": 0, "superseded": 0, "errors": 0}
    n = _query(isolated_db, "SELECT COUNT(*) FROM bias_events")[0][0]
    assert n == 0


# ─── Bonus : streams independants par bias ─────────────────────────────────


def test_streams_independants_par_bias_meme_ticker(isolated_db: Path) -> None:
    """Coverage : reco lock_in + reco fomo_greed sur meme ticker -> 2 opens
    independants (pas de cross-supersede)."""
    stats = wire_bias_trigger([
        _reco(ticker="NVDA", bias="lock_in", action="rightsize"),
        _reco(ticker="NVDA", bias="fomo_greed", action="exit",
              expected_delta=-100.0),
    ])
    assert stats["opened"] == 2
    n_open = _query(
        isolated_db,
        "SELECT COUNT(*) FROM bias_events WHERE ticker='NVDA' AND status='open'",
    )[0][0]
    assert n_open == 2


def test_streams_independants_par_ticker(isolated_db: Path) -> None:
    """Coverage : meme bias lock_in mais 2 tickers differents -> 2 opens."""
    stats = wire_bias_trigger([
        _reco(ticker="NVDA", bias="lock_in"),
        _reco(ticker="ARM", bias="lock_in"),
    ])
    assert stats["opened"] == 2
    # Et appel suivant identique = 2 kept (idempotence par ticker)
    stats2 = wire_bias_trigger([
        _reco(ticker="NVDA", bias="lock_in"),
        _reco(ticker="ARM", bias="lock_in"),
    ])
    assert stats2["kept"] == 2
    assert stats2["opened"] == 0
