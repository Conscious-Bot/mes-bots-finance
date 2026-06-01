"""v2.c.5 tests : over_cap_monitor -- detection transition + audit decouple.

User 01/06 critique architecturale post-1er design :
> Mon plan mettait l'etat de transition dans l'open-ness de bias_events.
> Un candidat over_cap se resout a +30j ; si NVDA est toujours over,
> il n'y a plus d'open candidate -> re-fire spurieux. "Resolu-mais-
> toujours-over" devient indistinguable de "jamais franchi".

Solution : prev_status lu depuis over_cap_alerts (journal incremental
dedie, migration 0024), pas depuis bias_events.open. Orthogonalite ADR
preservee : 1 evenement = 1 franchissement = 1 prediction sur 1 contrefactuel.

Tests canoniques :
- Transition dormant -> over : 1 alert (transition=dormant_to_over, notified=1),
  1 candidat bias_event ouvert
- Etat over -> over : 1 alert (transition=no_change), AUCUN notify, AUCUN
  nouveau candidat (idempotence anti-piege #1)
- Etat over -> dormant : 1 alert (transition=over_to_dormant), AUCUN notify
- LE TEST CRITIQUE : "resolu-mais-toujours-over" : bias_event force a
  resolved alors que over_cap_alerts dit over -> nouvelle eval continue
  no_change (pas de re-fire). Demontre le decouplage.
- Aucun cap configure -> stats vides
- Fail-safe : 1 ligne buggee n'arrete pas la boucle
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from intelligence import over_cap_monitor as ocm
from intelligence.bias_events import MissingDataError


def _schema_minimal(cx: sqlite3.Connection) -> None:
    """Clone DDL migrations 0023 (bias_events) + 0024 (over_cap_alerts)."""
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
            thesis_id INTEGER, prediction_id INTEGER, note TEXT,
            horizon_days INTEGER NOT NULL,
            resolve_at TEXT NOT NULL
        );
        CREATE TABLE over_cap_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            ticker TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('over', 'dormant')),
            weight_pct REAL NOT NULL,
            cap_pct REAL NOT NULL,
            conviction INTEGER,
            notified INTEGER NOT NULL DEFAULT 0 CHECK(notified IN (0, 1)),
            transition TEXT CHECK(
                transition IN ('dormant_to_over', 'over_to_dormant',
                               'no_change') OR transition IS NULL),
            bias_event_id INTEGER
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


def _mock_book_lines(monkeypatch: pytest.MonkeyPatch, lines: list[dict]) -> None:
    """Stub shared.book.get_held_lines (function-level patch, pas module)."""
    class _Line:
        def __init__(self, d):
            self.ticker = d["ticker"]
            self.weight_market_eur = d["weight"]
            self.qty = d.get("qty", 100.0)
            self.current_price_eur = d.get("price_eur", 150.0)

    import shared.book
    monkeypatch.setattr(
        shared.book, "get_held_lines",
        lambda: [_Line(ln) for ln in lines],
    )


def _mock_config(monkeypatch: pytest.MonkeyPatch, caps: dict[int, float]) -> None:
    """Stub shared.config.load() avec caps fournis."""
    import shared.config
    monkeypatch.setattr(
        shared.config, "load",
        lambda: {"concentration": {"line_cap_by_conviction": caps}},
    )


def _mock_theses(monkeypatch: pytest.MonkeyPatch, convs: dict[str, int]) -> None:
    """Stub storage.active_theses() avec map ticker -> conviction."""
    rows = [{"ticker": tk, "conviction": c} for tk, c in convs.items()]
    import shared.storage
    monkeypatch.setattr(shared.storage, "active_theses", lambda: rows)


def _mock_notify(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Stub shared.notify.send_text et retourne le mock REPRESENTANT send_text.
    Asserts via le retour : `mock.call_count`, `mock.call_args` (PAS via
    `.send_text`, qui serait une attribut fraiche du MagicMock parent)."""
    import shared.notify
    fake = MagicMock()
    monkeypatch.setattr(shared.notify, "send_text", fake)
    return fake


def _query(db: Path, sql: str, params: tuple = ()) -> list[tuple]:
    cx = sqlite3.connect(db)
    rows = cx.execute(sql, params).fetchall()
    cx.close()
    return rows


# ─── Test 1 : transition dormant -> over (cas heureux) ─────────────────────


def test_transition_dormant_to_over_emit_notify_wire_audit(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cas canonique : NVDA pese 8% du book, cap c4=5% -> over. Pas d'alert
    precedente (jamais evalue). Attendu : 1 notify, 1 candidat bias_event,
    1 audit row transition=dormant_to_over notified=1 bias_event_id renseigne."""
    # Caps : c4=5% (NVDA over), c5=95% (AMD dormant car 92% < 95%)
    _mock_config(monkeypatch, {4: 0.05, 5: 0.95})
    _mock_book_lines(monkeypatch, [
        {"ticker": "NVDA", "weight": 8000.0, "qty": 100.0, "price_eur": 150.0},
        {"ticker": "AMD", "weight": 92000.0, "qty": 50.0, "price_eur": 200.0},
    ])
    _mock_theses(monkeypatch, {"NVDA": 4, "AMD": 5})
    notify_mock = _mock_notify(monkeypatch)

    stats = ocm.check_all_overcap_transitions()
    assert stats["checked"] == 2
    assert stats["over"] == 1  # NVDA only
    assert stats["transitions"] == 1
    assert stats["notified"] == 1
    assert stats["wired"] == 1

    notify_mock.assert_called_once()
    msg = notify_mock.call_args[0][0]
    assert "OVER CAP" in msg and "NVDA" in msg

    # 1 candidat bias_event ouvert pour NVDA fomo_greed rule:over_cap
    biases = _query(
        isolated_db,
        "SELECT ticker, bias, status, decision_json FROM bias_events",
    )
    assert len(biases) == 1
    assert biases[0][0] == "NVDA" and biases[0][1] == "fomo_greed"
    assert biases[0][2] == "open"
    decision = json.loads(biases[0][3])
    assert decision["discipline_said"]["ref"] == "rule:over_cap"
    assert decision["discipline_said"]["action"] == "rightsize"

    # Audit row : 2 rows (NVDA + AMD). NVDA = transition+notified, AMD = no_change
    alerts = _query(
        isolated_db,
        "SELECT ticker, status, transition, notified, bias_event_id "
        "FROM over_cap_alerts ORDER BY id",
    )
    by_ticker = {r[0]: r for r in alerts}
    assert by_ticker["NVDA"][1] == "over"
    assert by_ticker["NVDA"][2] == "dormant_to_over"
    assert by_ticker["NVDA"][3] == 1
    assert by_ticker["NVDA"][4] is not None  # bias_event_id renseigne
    assert by_ticker["AMD"][1] == "dormant"
    assert by_ticker["AMD"][2] == "no_change"  # AMD wpct < cap_pct, jamais transitioned
    assert by_ticker["AMD"][3] == 0


# ─── Test 2 : etat over -> over (idempotence anti-piege #1) ────────────────


def test_etat_over_to_over_no_notify_no_wire(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NVDA reste over deux cycles consecutifs. 2e cycle : prev_status=over
    (lu depuis last over_cap_alerts row), new=over -> no_change. AUCUN
    notify, AUCUN nouveau candidat. C'est le piege #1 anti-spirale."""
    _mock_config(monkeypatch, {4: 0.05})
    _mock_book_lines(monkeypatch, [
        {"ticker": "NVDA", "weight": 8000.0, "qty": 100.0, "price_eur": 150.0},
        {"ticker": "AMD", "weight": 92000.0, "qty": 50.0, "price_eur": 200.0},
    ])
    _mock_theses(monkeypatch, {"NVDA": 4})
    notify = _mock_notify(monkeypatch)

    # Cycle 1 : transition
    stats1 = ocm.check_all_overcap_transitions()
    assert stats1["transitions"] == 1
    assert notify.call_count == 1

    # Cycle 2 : meme etat
    stats2 = ocm.check_all_overcap_transitions()
    assert stats2["transitions"] == 0, "etat stable over->over ne doit pas re-fire"
    assert stats2["wired"] == 0
    assert stats2["notified"] == 0
    # Notify total inchange (1 seul)
    assert notify.call_count == 1

    # Toujours 1 seul candidat bias_event open (pas de double)
    n_open = _query(
        isolated_db,
        "SELECT COUNT(*) FROM bias_events WHERE ticker='NVDA' AND status='open'",
    )[0][0]
    assert n_open == 1

    # 2 rows audit pour NVDA : 1 dormant_to_over + 1 no_change
    rows = _query(
        isolated_db,
        "SELECT transition, notified FROM over_cap_alerts "
        "WHERE ticker='NVDA' ORDER BY id",
    )
    assert rows[0] == ("dormant_to_over", 1)
    assert rows[1] == ("no_change", 0)


# ─── Test 3 : transition over -> dormant (user a trim) ─────────────────────


def test_transition_over_to_dormant_audit_only(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cycle 1 : NVDA 8% over cap 5%. Cycle 2 : user a trim, NVDA est sous
    cap. Transition over_to_dormant -> audit row seulement, pas de notify
    (rien a annoncer). L'open candidate existant continue de courir vers
    resolve_at (le contrefactuel sera evalue dans 30j)."""
    _mock_config(monkeypatch, {4: 0.05})
    _mock_book_lines(monkeypatch, [
        {"ticker": "NVDA", "weight": 8000.0, "qty": 100.0, "price_eur": 150.0},
        {"ticker": "OTHER", "weight": 92000.0, "qty": 1.0, "price_eur": 1.0},
    ])
    _mock_theses(monkeypatch, {"NVDA": 4})
    notify = _mock_notify(monkeypatch)

    ocm.check_all_overcap_transitions()  # cycle 1 : transition
    assert notify.call_count == 1

    # Cycle 2 : NVDA passe sous cap (user a trim 50 shares -> weight chute)
    _mock_book_lines(monkeypatch, [
        {"ticker": "NVDA", "weight": 3000.0, "qty": 50.0, "price_eur": 150.0},
        {"ticker": "OTHER", "weight": 97000.0, "qty": 1.0, "price_eur": 1.0},
    ])
    stats2 = ocm.check_all_overcap_transitions()
    assert stats2["transitions"] == 0  # PAS dormant_to_over
    assert stats2["notified"] == 0
    assert notify.call_count == 1  # Inchange

    # Audit cycle 2 : transition=over_to_dormant
    last = _query(
        isolated_db,
        "SELECT transition, status, notified FROM over_cap_alerts "
        "WHERE ticker='NVDA' ORDER BY id DESC LIMIT 1",
    )[0]
    assert last == ("over_to_dormant", "dormant", 0)

    # bias_event open precedent inchange (continue vers resolve_at)
    n_open = _query(
        isolated_db,
        "SELECT COUNT(*) FROM bias_events WHERE ticker='NVDA' AND status='open'",
    )[0][0]
    assert n_open == 1


# ─── Test 4 : LE TEST CRITIQUE -- resolu-mais-toujours-over =/= jamais ────


def test_resolu_mais_toujours_over_ne_re_fire_pas(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """USER 01/06 CRITIQUE ARCHITECTURALE : a +30j, le candidat over_cap
    se resout (status passe a 'resolved'). Si on lisait prev_status depuis
    bias_events.open, il n'y aurait plus d'open -> prev=dormant -> re-fire
    spurieux au cycle suivant alors que la position est TOUJOURS over.

    Le decouplage via over_cap_alerts evite ce piege : meme si bias_events
    a passe en resolved, over_cap_alerts.last dit toujours 'over' ->
    transition=no_change -> AUCUN notify, AUCUN nouveau candidat.

    Setup : 1 cycle qui transitionne -> resolu force (simule +30j passe) ->
    cycle suivant avec MEME position over.
    """
    _mock_config(monkeypatch, {4: 0.05})
    _mock_book_lines(monkeypatch, [
        {"ticker": "NVDA", "weight": 8000.0, "qty": 100.0, "price_eur": 150.0},
        {"ticker": "OTHER", "weight": 92000.0, "qty": 1.0, "price_eur": 1.0},
    ])
    _mock_theses(monkeypatch, {"NVDA": 4})
    notify = _mock_notify(monkeypatch)

    # Cycle 1 : transition dormant -> over
    stats1 = ocm.check_all_overcap_transitions()
    assert stats1["transitions"] == 1
    assert notify.call_count == 1

    # SIMULER +30j : on FORCE le bias_event a status='resolved' (comme si
    # resolve_due_bias_events l'avait passe). C'est exactement le scenario
    # piege que la critique user vise.
    cx = sqlite3.connect(isolated_db)
    cx.execute("UPDATE bias_events SET status='resolved' WHERE ticker='NVDA'")
    cx.commit()
    cx.close()

    # Cycle 2 : meme position toujours over
    stats2 = ocm.check_all_overcap_transitions()
    # CRITIQUE : avec le mauvais design (lecture bias_events.open), on
    # aurait stats2["transitions"]=1. Avec le bon (lecture over_cap_alerts),
    # transitions=0.
    assert stats2["transitions"] == 0, (
        "BIAS_EVENTS RESOLVED ne doit PAS RE-FIRE over_cap. "
        "Si ce test fail = la lecture prev_status passe par bias_events "
        "au lieu de over_cap_alerts = le compteur se re-arme = piege #1."
    )
    assert notify.call_count == 1, "Pas de re-notify spurieux"

    # bias_events count : 1 seul (l'ancien resolved, pas de nouveau open)
    n_total = _query(
        isolated_db,
        "SELECT COUNT(*) FROM bias_events WHERE ticker='NVDA'",
    )[0][0]
    assert n_total == 1, "Pas de nouveau candidat cree apres resolved"

    # over_cap_alerts : 2 rows pour NVDA, dernier = no_change (toujours over)
    last_alert = _query(
        isolated_db,
        "SELECT transition, status FROM over_cap_alerts "
        "WHERE ticker='NVDA' ORDER BY id DESC LIMIT 1",
    )[0]
    assert last_alert == ("no_change", "over")


# ─── Test 5 : cas degenere -- aucun cap configure ──────────────────────────


def test_aucun_cap_configure_no_op(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """config.concentration.line_cap_by_conviction vide -> stats vides,
    AUCUN audit row, AUCUN bias_event."""
    _mock_config(monkeypatch, {})
    _mock_book_lines(monkeypatch, [
        {"ticker": "NVDA", "weight": 8000.0, "qty": 100.0, "price_eur": 150.0},
    ])
    _mock_theses(monkeypatch, {"NVDA": 4})
    notify = _mock_notify(monkeypatch)

    stats = ocm.check_all_overcap_transitions()
    assert stats == {"checked": 0, "over": 0, "transitions": 0,
                     "notified": 0, "wired": 0, "errors": 0}
    notify.assert_not_called()
    assert _query(isolated_db, "SELECT COUNT(*) FROM over_cap_alerts")[0][0] == 0
    assert _query(isolated_db, "SELECT COUNT(*) FROM bias_events")[0][0] == 0


def test_ticker_sans_these_active_ignore(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Position tenue mais pas de these active (donc conviction inconnue) :
    skip, no audit (on ne peut pas comparer a un cap sans conviction)."""
    _mock_config(monkeypatch, {4: 0.05})
    _mock_book_lines(monkeypatch, [
        {"ticker": "ORPHAN", "weight": 8000.0, "qty": 100.0, "price_eur": 150.0},
    ])
    _mock_theses(monkeypatch, {})  # no these
    notify = _mock_notify(monkeypatch)

    stats = ocm.check_all_overcap_transitions()
    assert stats["checked"] == 1
    assert stats["over"] == 0
    assert stats["transitions"] == 0
    notify.assert_not_called()
    assert _query(isolated_db, "SELECT COUNT(*) FROM over_cap_alerts")[0][0] == 0


# ─── classify_position : missing data RAISE (user §6 invariant) ───────────


def test_classify_position_raise_missing_data_si_qty_zero() -> None:
    """USER 01/06 §6 invariant : ligne avec qty=0 (classifiable -- conv
    + cap configures) DOIT raise MissingDataError, PAS retourner None.
    Sinon drop silencieux dans IGNORED -> ligne jamais instrumentee."""
    lines = [{"ticker": "NVDA", "weight": 5000.0, "qty": 0.0,
              "current_price_eur": 150.0}]
    convs = {"NVDA": 4}
    caps = {4: 0.05}
    with pytest.raises(MissingDataError, match="qty=0"):
        ocm.classify_position("NVDA", lines, convs, caps)


def test_classify_position_raise_missing_data_si_price_none() -> None:
    """price None sur ligne classifiable -> MissingDataError, pas None."""
    lines = [{"ticker": "NVDA", "weight": 5000.0, "qty": 100.0,
              "current_price_eur": None}]
    convs = {"NVDA": 4}
    caps = {4: 0.05}
    with pytest.raises(MissingDataError, match="anchor_eur"):
        ocm.classify_position("NVDA", lines, convs, caps)


def test_classify_position_none_si_no_these_active() -> None:
    """Ligne sans these active -> None (non-classifiable legitime).
    PAS de raise -- la ligne est attendue d'etre ignoree."""
    lines = [{"ticker": "ORPHAN", "weight": 5000.0, "qty": 100.0,
              "current_price_eur": 150.0}]
    convs = {}  # no these
    caps = {4: 0.05}
    assert ocm.classify_position("ORPHAN", lines, convs, caps) is None


def test_classify_position_none_si_conv_sans_cap() -> None:
    """Conviction (e.g. c0 non-mappee) sans cap -> None legitime."""
    lines = [{"ticker": "C0_LINE", "weight": 5000.0, "qty": 100.0,
              "current_price_eur": 150.0}]
    convs = {"C0_LINE": 0}
    caps = {4: 0.05}  # c0 absent
    assert ocm.classify_position("C0_LINE", lines, convs, caps) is None


def test_monitor_compte_missing_en_errors_pas_silent(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une ligne avec qty=0 doit faire stats.errors+=1 (visible), pas
    disparaitre. Verifie le couplage classify->check_all."""
    _mock_config(monkeypatch, {4: 0.05})
    _mock_book_lines(monkeypatch, [
        {"ticker": "NVDA", "weight": 5000.0, "qty": 0.0, "price_eur": 150.0},
        {"ticker": "AMD", "weight": 3000.0, "qty": 50.0, "price_eur": 200.0},
    ])
    _mock_theses(monkeypatch, {"NVDA": 4, "AMD": 4})
    _mock_notify(monkeypatch)

    stats = ocm.check_all_overcap_transitions()
    assert stats["errors"] >= 1, "qty=0 doit etre compte en errors, pas skip"


# ─── Test 6 : fail-safe -- 1 ligne buggee n'arrete pas la boucle ───────────


def test_failure_sur_une_ligne_ne_bloque_pas_les_autres(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une evaluation qui raise (e.g., insert echoue) ne casse pas le check
    des autres tickers. NVDA buggee -> AMD doit etre evaluee quand meme."""
    _mock_config(monkeypatch, {4: 0.05, 5: 0.08})
    _mock_book_lines(monkeypatch, [
        {"ticker": "NVDA", "weight": 8000.0, "qty": 100.0, "price_eur": 150.0},
        {"ticker": "AMD", "weight": 92000.0, "qty": 50.0, "price_eur": 200.0},
    ])
    _mock_theses(monkeypatch, {"NVDA": 4, "AMD": 5})
    _mock_notify(monkeypatch)

    # Patch _prev_status_for_overcap pour raise sur NVDA
    real_prev = ocm._prev_status_for_overcap

    def selective_boom(ticker):
        if ticker == "NVDA":
            raise RuntimeError("simulated bug")
        return real_prev(ticker)

    monkeypatch.setattr(ocm, "_prev_status_for_overcap", selective_boom)

    stats = ocm.check_all_overcap_transitions()
    assert stats["errors"] == 1
    # AMD continue d'etre check (audit row presente)
    amd_rows = _query(
        isolated_db,
        "SELECT COUNT(*) FROM over_cap_alerts WHERE ticker='AMD'",
    )[0][0]
    assert amd_rows == 1
