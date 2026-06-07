"""Tests M-B Pydantic gates : M1 Buffett quality + M2 Taleb asymmetry.

Verrouille la logique deterministe des gates de creation thèse :
- M1 fire seulement si conviction >= 4 ET solidité tagged Incertain/Fragile
- M2 fire seulement si conviction >= 4 ET asymmetry_ratio < 2.0 calculable
- Watch direction -> M2 ne fire pas
- Conviction faible (<4) -> aucun gate ne fire

Si ces tests regressent, on a perdu la doctrine mentor heuristique
(L14 anti-pattern #1 : pas de persona LLM, gates determinist a la place).
"""

from __future__ import annotations

import pytest

from intelligence.thesis_creation_gates import (
    check_m1_buffett_quality,
    check_m2_taleb_asymmetry,
    check_m5_lynch_clarity,
    check_m9_damodaran_quantitative,
    check_m11_ackman_concentration,
    check_m12_pabrai_downside,
    run_creation_gates,
)

# --- M1 Buffett quality ----------------------------------------------------


@pytest.mark.parametrize("solidite", ["Incontournable", "Solide"])
def test_m1_high_conviction_acceptable_solidite_passes(solidite):
    """conviction 4-5 + solidité Incontournable/Solide -> pass."""
    for conv in (4, 5):
        r = check_m1_buffett_quality("NVDA", conv, solidite)
        assert r.passed, f"conv={conv} sol={solidite} doit passer : {r.message}"
        assert r.gate_name == "M1_buffett_quality"


@pytest.mark.parametrize("solidite", ["Incertain", "Fragile"])
def test_m1_high_conviction_bad_solidite_fails(solidite):
    """conviction >= 4 + solidité Incertain/Fragile -> FAIL."""
    for conv in (4, 5):
        r = check_m1_buffett_quality("TSLA", conv, solidite)
        assert not r.passed, f"conv={conv} sol={solidite} doit fail"
        assert "M1 Buffett FAIL" in r.message


def test_m1_low_conviction_never_fires():
    """conviction 1-3 : gate ne fire pas, quel que soit solidité."""
    for conv in (1, 2, 3):
        for sol in ("Incontournable", "Solide", "Incertain", "Fragile", None):
            r = check_m1_buffett_quality("ANY", conv, sol)
            assert r.passed, f"conv={conv} sol={sol} doit passer (gate not fired)"


def test_m1_no_solidite_warns_not_blocks():
    """Ticker hors canonical (solidité=None) -> pass avec warning, pas block."""
    r = check_m1_buffett_quality("UNKNOWN", 5, None)
    assert r.passed
    assert "warning" in r.message.lower()


# --- M2 Taleb asymmetry ---------------------------------------------------


def test_m2_long_acceptable_ratio_passes():
    """Long, conv 4, upside=15 / downside=5 -> ratio=3 >= 2 -> pass."""
    r = check_m2_taleb_asymmetry(
        ticker="NVDA", conviction=4, direction="long",
        entry=100.0, target_full=115.0, stop_price=95.0,
    )
    assert r.passed
    assert "3.00" in r.message or "asymmetry_ratio=3" in r.message


def test_m2_long_low_ratio_fails():
    """Long, conv 4, upside=8 / downside=5 -> ratio=1.6 < 2 -> FAIL."""
    r = check_m2_taleb_asymmetry(
        ticker="TSLA", conviction=4, direction="long",
        entry=100.0, target_full=108.0, stop_price=95.0,
    )
    assert not r.passed
    assert "M2 Taleb FAIL" in r.message
    assert "1.60" in r.message


def test_m2_short_acceptable_ratio_passes():
    """Short, conv 4, upside=20 / downside=10 -> ratio=2 -> pass."""
    r = check_m2_taleb_asymmetry(
        ticker="ZM", conviction=4, direction="short",
        entry=100.0, target_full=80.0, stop_price=110.0,
    )
    assert r.passed
    assert "2.00" in r.message


def test_m2_short_low_ratio_fails():
    """Short, conv 5, upside=5 / downside=10 -> ratio=0.5 -> FAIL."""
    r = check_m2_taleb_asymmetry(
        ticker="ANY", conviction=5, direction="short",
        entry=100.0, target_full=95.0, stop_price=110.0,
    )
    assert not r.passed
    assert "M2 Taleb FAIL" in r.message


def test_m2_watch_direction_does_not_fire():
    """direction=watch -> ne fire pas (pas de target/stop normalement)."""
    r = check_m2_taleb_asymmetry(
        ticker="ANY", conviction=5, direction="watch",
        entry=None, target_full=None, stop_price=None,
    )
    assert r.passed
    assert "watch" in r.message.lower()


def test_m2_low_conviction_does_not_fire():
    """conviction 1-3 : pas applicable."""
    for conv in (1, 2, 3):
        r = check_m2_taleb_asymmetry(
            ticker="ANY", conviction=conv, direction="long",
            entry=100.0, target_full=101.0, stop_price=95.0,  # ratio=0.2 mais skip
        )
        assert r.passed


def test_m2_missing_stop_warns_not_blocks():
    """stop_price=None : gate ne peut pas calculer -> warning, pas block."""
    r = check_m2_taleb_asymmetry(
        ticker="ANY", conviction=4, direction="long",
        entry=100.0, target_full=120.0, stop_price=None,
    )
    assert r.passed
    assert "non calculable" in r.message


def test_m2_invalid_geometry_warns_not_blocks():
    """Long avec stop > entry (geometrie cassée) -> warning, pas block."""
    r = check_m2_taleb_asymmetry(
        ticker="ANY", conviction=4, direction="long",
        entry=100.0, target_full=120.0, stop_price=105.0,  # stop > entry pour long
    )
    assert r.passed  # downside <= 0 -> ratio None -> warn


# --- M11 Ackman concentration check ---------------------------------------


def test_m11_low_conviction_does_not_fire():
    """conviction 1-4 : ne fire pas (Ackman n'attend que sur conviction 5)."""
    book_ranks = {"NVDA": 8}
    for conv in (1, 2, 3, 4):
        r = check_m11_ackman_concentration("NVDA", conv, book_ranks)
        assert r.passed, f"conv={conv} doit passer"


def test_m11_high_conviction_in_top5_passes():
    """conviction 5 + rang 1-5 -> pass."""
    book_ranks = {"NVDA": 1, "MSFT": 3, "ASML": 5}
    for ticker in ("NVDA", "MSFT", "ASML"):
        r = check_m11_ackman_concentration(ticker, 5, book_ranks)
        assert r.passed
        assert "top-5" in r.message or f"rang #{book_ranks[ticker]}" in r.message


def test_m11_high_conviction_outside_top5_fails():
    """conviction 5 + rang > 5 -> FAIL Ackman incoherence."""
    book_ranks = {"NVDA": 1, "MSFT": 3, "LOWPOS": 12}
    r = check_m11_ackman_concentration("LOWPOS", 5, book_ranks)
    assert not r.passed
    assert "M11 Ackman FAIL" in r.message
    assert "#12" in r.message


def test_m11_ticker_absent_from_book_warns_not_blocks():
    """Ticker pas en book (these en cours creation) -> warning pas block."""
    book_ranks = {"NVDA": 1}
    r = check_m11_ackman_concentration("NEW_THESIS_TICKER", 5, book_ranks)
    assert r.passed
    assert "warning" in r.message.lower()


def test_m11_book_ranks_none_tries_fetch():
    """book_ranks=None -> fetch via shared.book (peut crash en test).
    Si crash -> warning + passed=True. Si OK -> validate normalement."""
    r = check_m11_ackman_concentration("UNKNOWN_TICKER", 5, book_ranks=None)
    # Soit warning fetch indispo, soit ticker pas en book ; in both cases passed
    assert r.passed


# --- M5 Lynch clarity -----------------------------------------------------


def test_m5_low_conviction_does_not_fire():
    for conv in (1, 2, 3, 4):
        r = check_m5_lynch_clarity("ANY", conv, key_drivers=None, notes=None)
        assert r.passed


def test_m5_conviction_5_no_clarity_fails():
    """Conviction 5 + drivers vagues + notes vide -> FAIL Lynch."""
    r = check_m5_lynch_clarity(
        "ANY", 5, key_drivers=["drivers vagues sans pattern"], notes=""
    )
    assert not r.passed
    assert "M5 Lynch FAIL" in r.message


def test_m5_conviction_5_with_because_passes():
    r = check_m5_lynch_clarity(
        "NVDA", 5,
        key_drivers=["because AI capex compounds"],
        notes=None,
    )
    assert r.passed
    assert "clarity OK" in r.message


def test_m5_conviction_5_with_arrow_passes():
    r = check_m5_lynch_clarity(
        "NVDA", 5,
        key_drivers=["compute scarcity -> margin expansion"],
        notes=None,
    )
    assert r.passed


def test_m5_pattern_in_notes_also_works():
    r = check_m5_lynch_clarity(
        "NVDA", 5, key_drivers=None,
        notes="ten_x_path : Q1 beat -> Q2 raise -> 10x in 5y",
    )
    assert r.passed


# --- M9 Damodaran quantitative --------------------------------------------


def test_m9_low_conviction_does_not_fire():
    for conv in (1, 2, 3):
        r = check_m9_damodaran_quantitative("ANY", conv, key_drivers=None)
        assert r.passed


def test_m9_no_quantitative_drivers_fails():
    """Conviction 4+ + drivers narratifs purs -> FAIL."""
    r = check_m9_damodaran_quantitative(
        "ANY", 4, key_drivers=["narrative story without numbers"]
    )
    assert not r.passed
    assert "M9 Damodaran FAIL" in r.message


@pytest.mark.parametrize("driver", [
    "EPS growth 30%",
    "$15B FCF in 3y",
    "P/E 25 below sector",
    "10x return path",
    "ROIC 18 sustained",
    "Revenue 50B by 2028",
    "margin expansion 350 bps",
    "CAGR 25 expected",
])
def test_m9_quantitative_patterns_pass(driver):
    r = check_m9_damodaran_quantitative("ANY", 5, key_drivers=[driver])
    assert r.passed, f"driver {driver!r} doit matcher pattern : {r.message}"


def test_m9_at_least_one_quantitative_enough():
    """Plusieurs drivers narratifs + 1 chiffre -> pass."""
    r = check_m9_damodaran_quantitative(
        "ANY", 4,
        key_drivers=["narrative driver", "another vague claim", "EPS growth 30%"],
    )
    assert r.passed


# --- M12 Pabrai downside floor --------------------------------------------


def test_m12_low_conviction_does_not_fire():
    for conv in (1, 2, 3):
        r = check_m12_pabrai_downside("ANY", conv, notes=None)
        assert r.passed


def test_m12_no_notes_fails():
    """Conviction 4+ + notes None -> FAIL Pabrai."""
    r = check_m12_pabrai_downside("ANY", 4, notes=None)
    assert not r.passed
    assert "M12 Pabrai FAIL" in r.message
    assert "notes vide" in r.message


def test_m12_notes_without_downside_fails():
    r = check_m12_pabrai_downside(
        "ANY", 5, notes="just a generic comment without downside info"
    )
    assert not r.passed
    assert "M12 Pabrai FAIL" in r.message


@pytest.mark.parametrize("note", [
    "downside: 5000€ acceptable",
    "max_loss: -25%",
    "worst_case = -3000",
    "floor: $2000",
    "perte max : 1500€",
])
def test_m12_downside_patterns_pass(note):
    r = check_m12_pabrai_downside("ANY", 4, notes=note)
    assert r.passed, f"note {note!r} doit matcher : {r.message}"


# --- Aggregator ------------------------------------------------------------


def test_run_creation_gates_returns_six():
    """run_creation_gates lance les 6 gates (M1+M2+M5+M9+M11+M12)."""
    results = run_creation_gates(
        ticker="NVDA", direction="long", conviction=4,
        solidite="Solide",
        entry=100.0, target_full=120.0, stop_price=95.0,
        book_ranks={"NVDA": 2},
        key_drivers=["EPS growth 30% drives 10x path"],
        notes="downside: 2000€ acceptable",
    )
    assert len(results) == 6
    names = {r.gate_name for r in results}
    assert names == {
        "M1_buffett_quality", "M2_taleb_asymmetry", "M5_lynch_clarity",
        "M9_damodaran_quantitative", "M11_ackman_concentration",
        "M12_pabrai_downside",
    }
    assert all(r.passed for r in results)


def test_run_creation_gates_low_conviction_all_pass():
    """conviction 2 : tout passe trivialement."""
    results = run_creation_gates(
        ticker="ANY", direction="long", conviction=2,
        solidite="Fragile",
        entry=100.0, target_full=101.0, stop_price=95.0,  # ratio=0.2, would fail M2 si conv>=4
    )
    assert all(r.passed for r in results)


def test_run_creation_gates_full_disaster():
    """Conviction 5 + Fragile + low ratio + rank>5 + drivers vagues + notes
    vide -> 5 gates fail simultanement (tout sauf M5 si pas vraiment ride)."""
    results = run_creation_gates(
        ticker="LOWPOS", direction="long", conviction=5,
        solidite="Fragile",
        entry=100.0, target_full=105.0, stop_price=90.0,  # ratio=0.5
        book_ranks={"LOWPOS": 10},
        key_drivers=["vague narrative"],
        notes="",
    )
    failed = [r for r in results if not r.passed]
    # Tous les gates fire car conviction 5 + violations partout
    failed_names = {r.gate_name for r in failed}
    expected_fail = {
        "M1_buffett_quality",
        "M2_taleb_asymmetry",
        "M5_lynch_clarity",
        "M9_damodaran_quantitative",
        "M11_ackman_concentration",
        "M12_pabrai_downside",
    }
    assert failed_names == expected_fail, (
        f"Tous les 6 gates doivent FAIL ; manquent {expected_fail - failed_names}, "
        f"faux positifs {failed_names - expected_fail}"
    )
