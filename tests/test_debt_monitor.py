"""Property-based tests for intelligence.debt_monitor.

ADR 006 (Day 14): classify_phase + composite_phase_from_score invariants.
"""
from hypothesis import given, strategies as st

from intelligence.debt_monitor import (
    _PHASE_WEIGHT,
    INDICATOR_CONFIG,
    _score_contribution,
    classify_phase,
    composite_phase_from_score,
)


class TestClassifyPhase:
    """classify_phase invariants on every INDICATOR_CONFIG entry."""

    @given(st.sampled_from(list(INDICATOR_CONFIG.keys())),
           st.floats(min_value=-1e6, max_value=1e8, allow_nan=False, allow_infinity=False))
    def test_returns_valid_phase(self, indicator_name, value):
        """classify_phase always returns int in {1, 2, 3, 4} for any value/indicator."""
        ranges = INDICATOR_CONFIG[indicator_name]["phase_ranges"]
        phase = classify_phase(value, ranges)
        assert phase in {1, 2, 3, 4}

    @given(st.sampled_from(list(INDICATOR_CONFIG.keys())),
           st.floats(min_value=-1e6, max_value=1e8, allow_nan=False, allow_infinity=False))
    def test_idempotent(self, indicator_name, value):
        """Same value+ranges → same phase across calls."""
        ranges = INDICATOR_CONFIG[indicator_name]["phase_ranges"]
        assert classify_phase(value, ranges) == classify_phase(value, ranges)

    def test_range_coverage_inclusive_low(self):
        """For each (low, high, phase) in config, low value maps to that phase."""
        for name, cfg in INDICATOR_CONFIG.items():
            for low, high, expected_phase in cfg["phase_ranges"]:
                # Skip ranges with -inf or very negative bounds (T10Y2Y has -999)
                if low < -100:
                    continue
                # Pick value just inside the range
                value = low + (high - low) * 0.01 if high < 9999 else low + 1
                phase = classify_phase(value, cfg["phase_ranges"])
                assert phase == expected_phase, (
                    f"{name}: value={value} in [{low},{high}) expected P{expected_phase} got P{phase}"
                )

    def test_above_all_ranges_is_phase4(self):
        """Value above highest range → fallback Phase 4."""
        ranges = [(0, 1, 1), (1, 2, 2), (2, 3, 3), (3, 10, 4)]
        assert classify_phase(100.0, ranges) == 4

    def test_below_all_ranges_is_phase4(self):
        """Value below lowest range → fallback Phase 4 (extreme)."""
        ranges = [(10, 20, 1), (20, 30, 2), (30, 40, 3), (40, 50, 4)]
        assert classify_phase(5.0, ranges) == 4


class TestCompositePhase:
    """composite_phase_from_score invariants."""

    @given(st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    def test_returns_valid_phase(self, score):
        phase = composite_phase_from_score(score)
        assert phase in {1, 2, 3, 4}

    @given(st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False))
    def test_monotonic_non_decreasing(self, score):
        """Higher score → equal or higher phase."""
        p1 = composite_phase_from_score(score)
        p2 = composite_phase_from_score(score + 1)
        assert p2 >= p1

    def test_boundary_22(self):
        """Score 21.99 → P1, score 22 → P2."""
        assert composite_phase_from_score(21.99) == 1
        assert composite_phase_from_score(22.0) == 2

    def test_boundary_60(self):
        assert composite_phase_from_score(59.99) == 2
        assert composite_phase_from_score(60.0) == 3

    def test_boundary_115(self):
        assert composite_phase_from_score(114.99) == 3
        assert composite_phase_from_score(115.0) == 4

    def test_zero_is_phase1(self):
        assert composite_phase_from_score(0.0) == 1


class TestScoreContribution:
    """_score_contribution = indicator_weight × phase_weight."""

    def test_phase_weights_canonical(self):
        """Per Olivier spec: P1=1, P2=8, P3=16, P4=32."""
        assert _PHASE_WEIGHT == {1: 1, 2: 8, 3: 16, 4: 32}

    @given(st.floats(min_value=0.1, max_value=2.0, allow_nan=False, allow_infinity=False),
           st.integers(min_value=1, max_value=4))
    def test_contribution_positive(self, weight, phase):
        c = _score_contribution(weight, phase)
        assert c > 0

    def test_p4_max_contribution(self):
        """P4 contribution = weight × 32."""
        assert _score_contribution(1.0, 4) == 32
        assert _score_contribution(0.5, 4) == 16  # Tier 3 P4


class TestIndicatorConfig:
    """Sanity on INDICATOR_CONFIG structure."""

    def test_15_indicators(self):
        assert len(INDICATOR_CONFIG) == 15

    def test_tiers_distribution(self):
        tiers = [cfg["tier"] for cfg in INDICATOR_CONFIG.values()]
        assert tiers.count(1) == 7   # Tier 1 daily
        assert tiers.count(2) == 5   # Tier 2 weekly
        assert tiers.count(3) == 3   # Tier 3 monthly

    def test_weights_canonical_per_tier(self):
        for name, cfg in INDICATOR_CONFIG.items():
            t = cfg["tier"]
            expected = {1: 1.0, 2: 0.75, 3: 0.5}[t]
            assert cfg["weight"] == expected, f"{name} tier {t} weight {cfg['weight']} != {expected}"

    def test_all_phase_ranges_well_formed(self):
        """Each range is (low, high, phase) tuple with low<high, phase in {1,2,3,4}."""
        for name, cfg in INDICATOR_CONFIG.items():
            for low, high, phase in cfg["phase_ranges"]:
                assert low < high, f"{name}: range ({low}, {high}, {phase}) low >= high"
                assert phase in {1, 2, 3, 4}, f"{name}: invalid phase {phase}"
