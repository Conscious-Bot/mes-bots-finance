"""Garde enum de biais (H11) + mapping lecture. Cf déclaration 02/08 +
docs/specs/terminologie_bias_events_fr.md (enum = lock_in/fomo_greed/other)."""
import pytest

from shared import storage


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("lock_in", "lock_in"),
        ("fomo_greed", "fomo_greed"),
        ("other", "other"),
        ("recency_bias", "other"),            # cognitif -> other (spec)
        ("confirmation_bias", "other"),
        ("vend_winners_trop_tot", "lock_in"),  # doublon FR (L1)
        ("override_vs_tribunal", "fomo_greed"),  # impulsion 30/07
        ("override_pre_print", "fomo_greed"),
        ("label_jamais_vu", "other"),          # inconnu -> other (conservatif)
    ],
)
def test_canonical_bias_maps_to_enum(raw, expected):
    assert storage.canonical_bias(raw) == expected


def test_canonical_bias_output_always_in_enum():
    for raw in ("lock_in", "recency_bias", "xyz", "vend_winners_trop_tot"):
        assert storage.canonical_bias(raw) in storage.CANONICAL_BIAS


@pytest.mark.parametrize("good", ['[]', '["fomo_greed"]', '["lock_in","other"]', "[]"])
def test_validate_accepts_canonical(good):
    storage._validate_bias_enum(good)  # ne lève pas


@pytest.mark.parametrize(
    "bad",
    [
        '["recency_bias"]',            # cognitif granulaire
        '["vend_winners_trop_tot"]',   # doublon sémantique de lock_in
        '["override_pre_print"]',      # label inventé
        '["fomo_greed","recency_bias"]',  # un bon + un mauvais
    ],
)
def test_validate_rejects_noncanonical_and_duplicates(bad):
    with pytest.raises(ValueError):
        storage._validate_bias_enum(bad)


def test_insert_decision_guard_raises_before_db():
    """La garde doit lever AVANT toute écriture (append-only ne pardonne pas)."""
    with pytest.raises(ValueError, match="non-canonique"):
        storage.insert_decision_with_cf(
            ticker="TEST", decision_type="scale_in",
            reasoning="[STRUCTURED] test", thesis_id=1, conviction=3,
            price_native=100.0, qty_before=1.0, currency="USD",
            bias_hypothesis_json='["override_vs_tribunal"]',
        )
