"""Tests stale_target monitor (#134).

7 tests minimum cf docs/templates/monitor_pattern.md :
1. Transition actionable (alive_to_dying) -> 1 notify, 1 audit row avec notified=1
2. État stable (no_change) -> 1 audit row no_change, 0 notify
3. Transition retour (dying_to_alive) -> audit seulement, pas notify
4. TEST CRITIQUE L4 : status reste "dying" entre 2 cycles, pas de re-fire spurieux
5. Cas dégénéré : aucune thèse en périmètre -> stats vides
6. Fail-safe : 1 these buggée (avg_cost None) -> errors+=1, autres continuent
7. classify pure : missing data -> MissingDataError ; pas de target -> None
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from intelligence import stale_target_monitor as _m
from intelligence.bias_events import MissingDataError


# ─── Tests 7 : classify pur (UNIT) ───────────────────────────────────────────


def test_classify_pure_no_target_returns_none():
    """target_full_value=None ET target_full=None -> None (non-classifiable)."""
    thesis = {"id": 1, "ticker": "ABC", "target_full": None, "target_full_value": None}
    assert _m.classify_thesis(thesis, avg_cost_eur=100.0, target_eur=None) is None


def test_classify_pure_missing_avg_cost_raises():
    """target défini mais avg_cost_eur=None -> MissingDataError (donnée critique)."""
    thesis = {"id": 1, "ticker": "ABC"}
    with pytest.raises(MissingDataError, match="avg_cost_eur=None"):
        _m.classify_thesis(thesis, avg_cost_eur=None, target_eur=150.0)


def test_classify_pure_zero_avg_cost_raises():
    """avg_cost_eur=0 -> MissingDataError (idem)."""
    thesis = {"id": 1, "ticker": "ABC"}
    with pytest.raises(MissingDataError, match="<=0"):
        _m.classify_thesis(thesis, avg_cost_eur=0, target_eur=150.0)


def test_classify_alive_edge_above_seuil():
    """edge_pct = (150-100)/100 = 50% > seuil 5% -> alive."""
    thesis = {"id": 1, "ticker": "ABC"}
    out = _m.classify_thesis(thesis, avg_cost_eur=100.0, target_eur=150.0)
    assert out["status"] == "alive"
    assert out["edge_pct"] == pytest.approx(50.0)


def test_classify_dying_edge_thin():
    """edge_pct = (103-100)/100 = 3% < seuil 5% -> dying."""
    thesis = {"id": 1, "ticker": "ABC"}
    out = _m.classify_thesis(thesis, avg_cost_eur=100.0, target_eur=103.0)
    assert out["status"] == "dying"
    assert out["edge_pct"] == pytest.approx(3.0)


def test_classify_dead_cost_exceeds_target():
    """cost > target -> edge négatif -> dead."""
    thesis = {"id": 1, "ticker": "ABC"}
    out = _m.classify_thesis(thesis, avg_cost_eur=120.0, target_eur=100.0)
    assert out["status"] == "dead"
    assert out["edge_pct"] < 0


# ─── Tests 1-6 : check_all_stale_target_transitions (INTEGRATION) ─────────────


@pytest.fixture
def _mocked_book_one_thesis():
    """Mock active_theses + get_book_index avec 1 thèse + 1 BookLine."""
    class _BookLineMock:
        def __init__(self, avg_cost_eur, fx_rate=1.0):
            self.avg_cost_eur = avg_cost_eur
            self.fx_rate_to_eur = fx_rate

    def _make(thesis_target_eur=150.0, avg_cost_eur=100.0):
        thesis = {
            "id": 42, "ticker": "ABC",
            "target_full": thesis_target_eur,
            "target_full_value": None,
            "target_full_currency": "EUR",
            "status": "active",
        }
        book = {"ABC": _BookLineMock(avg_cost_eur)}
        return thesis, book

    return _make


def test_transition_alive_to_dying_notifies(_mocked_book_one_thesis, migrated_db):
    """Cycle 1 : alive. Cycle 2 : seuil dépassé -> dying -> 1 notify."""
    # Cycle 1 : alive (cost=100, target=150 -> 50% edge)
    thesis, book = _mocked_book_one_thesis(thesis_target_eur=150.0, avg_cost_eur=100.0)
    with patch("shared.storage.active_theses", return_value=[thesis]), \
         patch("shared.book.get_book_index", return_value=book), \
         patch("shared.notify.send_text") as mock_notify:
        out = _m.check_all_stale_target_transitions()
    assert out["checked"] == 1
    assert out["alive"] == 1
    assert out["notified"] == 0  # alive default, pas de transition
    assert mock_notify.call_count == 0

    # Cycle 2 : avg_cost grimpe à 148 -> edge 1.3% < seuil 5% -> dying
    thesis2, book2 = _mocked_book_one_thesis(thesis_target_eur=150.0, avg_cost_eur=148.0)
    with patch("shared.storage.active_theses", return_value=[thesis2]), \
         patch("shared.book.get_book_index", return_value=book2), \
         patch("shared.notify.send_text") as mock_notify2:
        out2 = _m.check_all_stale_target_transitions()
    assert out2["dying"] == 1
    assert out2["transitions"] == 1
    assert out2["notified"] == 1
    assert mock_notify2.call_count == 1
    call_args = mock_notify2.call_args[0][0]
    assert "STALE TARGET" in call_args
    assert "ABC" in call_args
    assert "alive -> dying" in call_args


def test_stable_state_no_notify(_mocked_book_one_thesis, migrated_db):
    """Cycle 1 = cycle 2 (alive) -> audit row no_change, pas de notify."""
    thesis, book = _mocked_book_one_thesis(thesis_target_eur=150.0, avg_cost_eur=100.0)

    # 2 cycles consécutifs alive
    for _ in range(2):
        with patch("shared.storage.active_theses", return_value=[thesis]), \
             patch("shared.book.get_book_index", return_value=book), \
             patch("shared.notify.send_text") as mock_notify:
            out = _m.check_all_stale_target_transitions()
        assert out["alive"] == 1
        assert out["notified"] == 0
        assert mock_notify.call_count == 0

    # Vérifie 2 rows audit dans le journal
    from shared import storage as _s
    with _s.db() as cx:
        n = cx.execute(
            "SELECT COUNT(*) FROM stale_target_alerts WHERE thesis_id=42"
        ).fetchone()[0]
    assert n == 2
    # 2e row a transition='no_change'
    last = _s.get_latest_stale_target_per_thesis(42)
    assert last["transition"] == "no_change"


def test_l4_critical_no_refire_when_dying_stays_dying(
    _mocked_book_one_thesis, migrated_db,
):
    """TEST CRITIQUE L4 : status reste 'dying' entre 2 cycles, PAS de re-notify.

    C'est le test qui démontre que prev_status est lu depuis le journal
    stale_target_alerts (et donc 'dying' au cycle 2), pas depuis un cycle
    externe (bias_events resolved par exemple) qui reséquerait à 'alive'
    et causerait un re-fire.
    """
    # Cycle 1 : alive (edge 50% > seuil)
    thesis_alive, book_alive = _mocked_book_one_thesis(
        thesis_target_eur=150.0, avg_cost_eur=100.0,
    )
    with patch("shared.storage.active_theses", return_value=[thesis_alive]), \
         patch("shared.book.get_book_index", return_value=book_alive), \
         patch("shared.notify.send_text") as mock1:
        _m.check_all_stale_target_transitions()
    assert mock1.call_count == 0  # alive default, no notify

    # Cycle 2 : avg_cost passe à 148 -> dying. 1 notify.
    thesis_dying, book_dying = _mocked_book_one_thesis(
        thesis_target_eur=150.0, avg_cost_eur=148.0,
    )
    with patch("shared.storage.active_theses", return_value=[thesis_dying]), \
         patch("shared.book.get_book_index", return_value=book_dying), \
         patch("shared.notify.send_text") as mock2:
        _m.check_all_stale_target_transitions()
    assert mock2.call_count == 1  # alive_to_dying -> notify

    # Cycle 3 : MÊME état (dying, avg_cost=148). Doit PAS re-notify.
    with patch("shared.storage.active_theses", return_value=[thesis_dying]), \
         patch("shared.book.get_book_index", return_value=book_dying), \
         patch("shared.notify.send_text") as mock3:
        out3 = _m.check_all_stale_target_transitions()
    assert mock3.call_count == 0, (
        "Re-fire spurieux : dying -> dying doit être no_change, pas notify"
    )
    assert out3["transitions"] == 0
    last = _m._prev_status_for_stale_target(42)
    assert last == "dying"


def test_no_theses_in_perimeter_empty_stats(migrated_db):
    """Cas dégénéré : 0 thèses actives -> stats vides, 0 audit row."""
    with patch("shared.storage.active_theses", return_value=[]), \
         patch("shared.book.get_book_index", return_value={}):
        out = _m.check_all_stale_target_transitions()
    assert out["checked"] == 0
    assert out["notified"] == 0
    assert out["errors"] == 0


def test_consensus_divergent_flagged_when_target_30pct_above_consensus(
    _mocked_book_one_thesis, migrated_db,
):
    """Cross-check consensus : si target Olivier > consensus * 1.3, le row
    audit doit avoir consensus_delta_pct > 30 et stats.consensus_divergent++.

    Mock prices.get_analyst_consensus pour controler le scenario.
    """
    thesis, book = _mocked_book_one_thesis(thesis_target_eur=150.0, avg_cost_eur=100.0)
    fake_consensus = {
        "ticker": "ABC", "target_mean": 100.0, "n_analysts": 20,
        "target_median": 100.0, "target_high": 120.0, "target_low": 80.0,
        "recommendation_key": "buy", "recommendation_mean": 2.0,
        "currency": "USD", "asof": "2026-06-12", "source": "yfinance",
    }
    with patch("shared.storage.active_theses", return_value=[thesis]), \
         patch("shared.book.get_book_index", return_value=book), \
         patch("shared.prices.get_analyst_consensus", return_value=fake_consensus), \
         patch("shared.notify.send_text"):
        out = _m.check_all_stale_target_transitions()

    assert out["consensus_divergent"] == 1, "target 150 > consensus 100 * 1.3 -> divergent attendu"

    from shared import storage as _s
    last = _s.get_latest_stale_target_per_thesis(42)
    assert last["consensus_target"] == 100.0
    assert last["consensus_n"] == 20
    # delta = (150/100 - 1)*100 = 50%
    assert abs(last["consensus_delta_pct"] - 50.0) < 0.1


def test_consensus_none_when_not_covered(_mocked_book_one_thesis, migrated_db):
    """Si get_analyst_consensus retourne None (ticker pas couvert), les
    colonnes consensus_* doivent etre NULL mais le monitor continue sans crasher."""
    thesis, book = _mocked_book_one_thesis(thesis_target_eur=150.0, avg_cost_eur=100.0)
    with patch("shared.storage.active_theses", return_value=[thesis]), \
         patch("shared.book.get_book_index", return_value=book), \
         patch("shared.prices.get_analyst_consensus", return_value=None), \
         patch("shared.notify.send_text"):
        out = _m.check_all_stale_target_transitions()

    assert out["consensus_divergent"] == 0
    assert out["alive"] == 1  # status normal computed
    assert out["errors"] == 0  # pas d'erreur sur None consensus

    from shared import storage as _s
    last = _s.get_latest_stale_target_per_thesis(42)
    assert last["status"] == "alive"
    assert last.get("consensus_target") is None
    assert last.get("consensus_n") is None
    assert last.get("consensus_delta_pct") is None


def test_fail_safe_one_thesis_missing_data_others_continue(
    _mocked_book_one_thesis, migrated_db,
):
    """1 thèse buggée (avg_cost=None) -> errors+=1, l'autre est checked normalement."""
    class _BookLineNoCost:
        avg_cost_eur = None
        fx_rate_to_eur = 1.0

    class _BookLineOK:
        avg_cost_eur = 100.0
        fx_rate_to_eur = 1.0

    theses = [
        {"id": 1, "ticker": "BAD", "target_full": 150.0,
         "target_full_value": None, "target_full_currency": "EUR",
         "status": "active"},
        {"id": 2, "ticker": "GOOD", "target_full": 150.0,
         "target_full_value": None, "target_full_currency": "EUR",
         "status": "active"},
    ]
    book = {"BAD": _BookLineNoCost(), "GOOD": _BookLineOK()}

    with patch("shared.storage.active_theses", return_value=theses), \
         patch("shared.book.get_book_index", return_value=book), \
         patch("shared.notify.send_text"):
        out = _m.check_all_stale_target_transitions()
    assert out["checked"] == 2  # les 2 lignes parcourues
    assert out["errors"] == 1   # BAD compté en errors
    assert out["alive"] == 1    # GOOD classifié alive
