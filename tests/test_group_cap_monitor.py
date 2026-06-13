"""Tests group_cap monitor (#149) -- 4e monitor canonique.

8 tests cf docs/templates/monitor_pattern.md :
1. Transition actionable (dormant_to_over) -> 1 notify, 1 audit row
2. État stable (no_change) -> 1 audit row no_change, 0 notify
3. Transition retour (over_to_dormant) -> audit seulement, pas notify
4. TEST CRITIQUE L4 : status reste "over" 2 cycles, pas de re-fire spurieux
5. Cas dégénéré : groupe absent du book -> classify None, skip silencieux
6. Fail-safe : classify Raise MissingDataError sur book vide
7. classify pure : group_pct exact, status seuil
8. config GROUPS : "memory" = {000660.KS, MU} cap 6%
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from intelligence import group_cap_monitor as _m
from intelligence.bias_events import MissingDataError


def _make_bookline(ticker, qty, weight_eur):
    class _BL:
        pass
    bl = _BL()
    bl.ticker = ticker
    bl.qty = qty
    bl.weight_market_eur = weight_eur
    return bl


# ─── Tests UNIT classify_group ────────────────────────────────────────────────


def test_classify_group_dormant_below_cap():
    """group_pct < cap_pct -> dormant."""
    book = [
        _make_bookline("000660.KS", 1, 2000),  # 4%
        _make_bookline("MU", 1, 500),           # 1%
        _make_bookline("OTHER", 1, 47500),      # 95%
    ]
    out = _m.classify_group("memory", {"000660.KS", "MU"}, 6.0, book)
    assert out is not None
    assert out["status"] == "dormant"
    assert out["group_pct"] == pytest.approx(5.0)
    assert out["group_eur"] == 2500


def test_classify_group_over_above_cap():
    """group_pct > cap_pct -> over."""
    book = [
        _make_bookline("000660.KS", 1, 4000),  # 8%
        _make_bookline("MU", 1, 0),
        _make_bookline("OTHER", 1, 46000),
    ]
    out = _m.classify_group("memory", {"000660.KS", "MU"}, 6.0, book)
    assert out["status"] == "over"
    assert out["group_pct"] == pytest.approx(8.0)


def test_classify_group_absent_returns_none():
    """Tickers du groupe absents du book -> None (non-classifiable légitime)."""
    book = [_make_bookline("OTHER", 1, 50000)]
    out = _m.classify_group("memory", {"000660.KS", "MU"}, 6.0, book)
    assert out is None


def test_classify_group_empty_book_raises():
    """Book entièrement vide -> MissingDataError."""
    with pytest.raises(MissingDataError, match="book vide"):
        _m.classify_group("memory", {"000660.KS", "MU"}, 6.0, [])


def test_classify_group_book_eur_zero_raises():
    """Book avec weight_market_eur=0 partout -> MissingDataError."""
    book = [_make_bookline("X", 1, 0)]
    with pytest.raises(MissingDataError, match="book_eur"):
        _m.classify_group("memory", {"000660.KS", "MU"}, 6.0, book)


def test_classify_seuil_strict_above():
    """group_pct = cap_pct exact -> dormant (seuil strict >)."""
    book = [
        _make_bookline("000660.KS", 1, 3000),
        _make_bookline("OTHER", 1, 47000),
    ]
    out = _m.classify_group("memory", {"000660.KS", "MU"}, 6.0, book)
    assert out["group_pct"] == pytest.approx(6.0)
    assert out["status"] == "dormant"  # 6.0 > 6.0 False -> dormant


def test_groups_config_memory_default():
    """Config canonique : memory = {000660.KS, MU} cap 6%."""
    assert "memory" in _m.GROUPS
    tickers, cap = _m.GROUPS["memory"]
    assert tickers == {"000660.KS", "MU"}
    assert cap == 6.0


# ─── Tests INTEGRATION check_all_group_cap_transitions ───────────────────────


def test_transition_dormant_to_over_notifies(migrated_db):
    """Cycle 1 : dormant. Cycle 2 : depasse cap -> over -> 1 notify."""
    book_dormant = [
        _make_bookline("000660.KS", 1, 2000),  # 4%
        _make_bookline("MU", 1, 500),           # 1%, sum 5%
        _make_bookline("OTHER", 1, 47500),
    ]
    book_over = [
        _make_bookline("000660.KS", 1, 4000),  # 8%
        _make_bookline("MU", 1, 0),
        _make_bookline("OTHER", 1, 46000),
    ]

    with patch("shared.book.get_held_lines", return_value=book_dormant), \
         patch("shared.notify.send_text") as mock1:
        out1 = _m.check_all_group_cap_transitions()
    assert out1["dormant"] == 1
    assert mock1.call_count == 0

    with patch("shared.book.get_held_lines", return_value=book_over), \
         patch("shared.notify.send_text") as mock2:
        out2 = _m.check_all_group_cap_transitions()
    assert out2["over"] == 1
    assert out2["transitions"] == 1
    assert out2["notified"] == 1
    assert mock2.call_count == 1
    msg = mock2.call_args[0][0]
    assert "GROUP CAP" in msg
    assert "MEMORY" in msg
    assert "8.0%" in msg


def test_l4_critical_no_refire_when_over_stays_over(migrated_db):
    """TEST CRITIQUE L4 : status reste 'over' entre 2 cycles, PAS de re-notify.

    Prouve que prev_status est lu depuis group_cap_alerts (journal dedie),
    pas depuis bias_events ou source externe re-resequee.
    """
    book_dormant = [_make_bookline("000660.KS", 1, 2000),
                    _make_bookline("OTHER", 1, 48000)]
    book_over = [_make_bookline("000660.KS", 1, 4000),
                 _make_bookline("OTHER", 1, 46000)]

    # Cycle 1 : dormant
    with patch("shared.book.get_held_lines", return_value=book_dormant), \
         patch("shared.notify.send_text") as mock1:
        _m.check_all_group_cap_transitions()
    assert mock1.call_count == 0

    # Cycle 2 : passe over -> 1 notify
    with patch("shared.book.get_held_lines", return_value=book_over), \
         patch("shared.notify.send_text") as mock2:
        _m.check_all_group_cap_transitions()
    assert mock2.call_count == 1

    # Cycle 3 : MÊME état (over). Doit PAS re-notify.
    with patch("shared.book.get_held_lines", return_value=book_over), \
         patch("shared.notify.send_text") as mock3:
        out3 = _m.check_all_group_cap_transitions()
    assert mock3.call_count == 0, "Re-fire spurieux : over -> over doit être no_change"
    assert out3["transitions"] == 0
    assert _m._prev_status_for_group("memory") == "over"


def test_over_to_dormant_audit_only_no_notify(migrated_db):
    """over -> dormant : audit row écrit, mais pas de notify (rien à annoncer)."""
    book_over = [_make_bookline("000660.KS", 1, 4000),
                 _make_bookline("OTHER", 1, 46000)]
    book_dormant = [_make_bookline("000660.KS", 1, 2000),
                    _make_bookline("OTHER", 1, 48000)]

    # Pose le state 'over' au cycle 1
    with patch("shared.book.get_held_lines", return_value=book_over), \
         patch("shared.notify.send_text"):
        _m.check_all_group_cap_transitions()

    # Cycle 2 : retour à dormant
    with patch("shared.book.get_held_lines", return_value=book_dormant), \
         patch("shared.notify.send_text") as mock:
        out = _m.check_all_group_cap_transitions()
    assert out["dormant"] == 1
    assert out["transitions"] == 1  # observable
    assert out["notified"] == 0
    assert mock.call_count == 0


def test_group_absent_no_alert_row(migrated_db):
    """Si groupe entièrement vendu (absent du book) -> skip silencieux."""
    book = [_make_bookline("OTHER", 1, 50000)]
    with patch("shared.book.get_held_lines", return_value=book), \
         patch("shared.notify.send_text") as mock:
        out = _m.check_all_group_cap_transitions()
    assert out["checked"] == 1  # check tente le groupe
    # Mais ni dormant ni over (None ne s'incrémente nulle part)
    assert out["dormant"] == 0
    assert out["over"] == 0
    assert mock.call_count == 0
