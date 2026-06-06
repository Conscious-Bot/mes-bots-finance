"""Phase B — tests compute_book_warnings.

Rules R1-R5 + degraded cases + sort/cap.
"""

from intelligence.macro_book_warnings import compute_book_warnings


def _semi_heavy_book() -> list[dict]:
    """Book 64% semis miroir etat 06/06."""
    return [
        {"ticker": "NVDA", "qty": 10.0, "avg_cost": 500.0},   # 5000 semis
        {"ticker": "AVGO", "qty": 5.0, "avg_cost": 400.0},    # 2000 semis
        {"ticker": "AMD", "qty": 10.0, "avg_cost": 150.0},    # 1500 semis
        {"ticker": "GOOGL", "qty": 5.0, "avg_cost": 200.0},   # 1000 tech_mega
        {"ticker": "CCJ", "qty": 10.0, "avg_cost": 50.0},     # 500 energy
        # total ~10000, semis = 8500 = 85%
    ]


def _jp_heavy_book() -> list[dict]:
    return [
        {"ticker": "4063.T", "qty": 100.0, "avg_cost": 30.0},   # 3000 semis JP
        {"ticker": "6857.T", "qty": 10.0, "avg_cost": 150.0},   # 1500 semis JP
        {"ticker": "GOOGL", "qty": 20.0, "avg_cost": 200.0},    # 4000 tech_mega
        {"ticker": "CCJ", "qty": 20.0, "avg_cost": 50.0},       # 1000 energy
    ]


def test_book_warnings_r1_semis_concentration_fragile():
    """FRAGILE + 85% semis -> R1 fires."""
    ws = compute_book_warnings("FRAGILE", _semi_heavy_book(), {"TYX": 4.98})
    rule_ids = [w["rule_id"] for w in ws]
    assert "R1_semis_concentration" in rule_ids
    r1 = next(w for w in ws if w["rule_id"] == "R1_semis_concentration")
    assert "TYX" in r1["rationale"]  # mentioned dans rationale puisque tyx > 4.5
    assert r1["severity"] == "med"


def test_book_warnings_r1_severity_high_under_stress():
    """STRESS + 85% semis -> R1 severity high."""
    ws = compute_book_warnings("STRESS", _semi_heavy_book(), {})
    r1 = next(w for w in ws if w["rule_id"] == "R1_semis_concentration")
    assert r1["severity"] == "high"


def test_book_warnings_r2_carry_unwind_jp():
    """USDJPY > 158 + JP positions > 10% -> R2 fires."""
    ws = compute_book_warnings("FRAGILE", _jp_heavy_book(), {"USDJPY": 159.5})
    rule_ids = [w["rule_id"] for w in ws]
    assert "R2_carry_unwind_jp" in rule_ids


def test_book_warnings_r2_silent_when_usdjpy_safe():
    """USDJPY < 158 -> R2 ne fire pas."""
    ws = compute_book_warnings("FRAGILE", _jp_heavy_book(), {"USDJPY": 150.0})
    rule_ids = [w["rule_id"] for w in ws]
    assert "R2_carry_unwind_jp" not in rule_ids


def test_book_warnings_r3_growth_tech_dominance():
    """LATE_CYCLE + 85% semis + 10% tech_mega = 95% growth-tech -> R3 fires."""
    ws = compute_book_warnings("LATE_CYCLE", _semi_heavy_book(), {})
    rule_ids = [w["rule_id"] for w in ws]
    assert "R3_growth_tech_dominance" in rule_ids


def test_book_warnings_risk_on_no_warnings():
    """RISK_ON regime + book sain (50/50) -> no warning."""
    book = [
        {"ticker": "NVDA", "qty": 5.0, "avg_cost": 500.0},   # 2500 semis
        {"ticker": "CCJ", "qty": 50.0, "avg_cost": 50.0},    # 2500 energy
    ]
    ws = compute_book_warnings("RISK_ON", book, {"USDJPY": 150.0, "VIX": 17.0})
    assert ws == []


def test_book_warnings_empty_book_safe():
    """Empty positions -> empty warnings, no crash."""
    assert compute_book_warnings("FRAGILE", [], {}) == []


def test_book_warnings_sort_by_severity():
    """Warnings retournes high-first."""
    ws = compute_book_warnings("STRESS", _semi_heavy_book(), {"USDJPY": 161.0})
    # R1 sous STRESS -> high. R2/R3 -> med.
    if len(ws) >= 2:
        sevs = [w["severity"] for w in ws]
        sev_rank = {"high": 0, "med": 1, "low": 2}
        ranks = [sev_rank[s] for s in sevs]
        assert ranks == sorted(ranks)


def test_book_warnings_max_4():
    """Cap a 4 warnings max (lisibilite panel)."""
    ws = compute_book_warnings("STRESS", _semi_heavy_book(), {"USDJPY": 161.0, "VIX": 25.0})
    assert len(ws) <= 4
