"""Tests prorata Digue 2 ADR 015 (risk.kill_switch.compute_prorata_plan).

Logique pure avec dépendances mockées (membership / holdings / prix). CI-safe.
Le prorata est UNIFORME et NON-DISCRÉTIONNAIRE : pct de chaque ligne compute_ai,
sans sélection — c'est l'invariant anti-biais #1 à verrouiller.
"""

from unittest import mock

from risk import kill_switch as ks


def _run_plan(members, positions, prices_map, pct=0.20):
    with (
        mock.patch.object(ks, "_cluster_membership", return_value={m.upper() for m in members}),
        mock.patch.object(ks.storage, "get_open_positions", return_value=positions),
        mock.patch.object(
            ks.prices, "get_current_price_in_eur", side_effect=lambda t: prices_map.get(t.upper())
        ),
    ):
        return ks.compute_prorata_plan(pct)


def test_prorata_trims_20pct_of_each_held_cluster_line():
    plan = _run_plan(
        members=["NVDA", "TSM"],
        positions=[{"ticker": "NVDA", "qty": 10}, {"ticker": "TSM", "qty": 5}],
        prices_map={"NVDA": 100.0, "TSM": 200.0},
    )
    by = {ln["ticker"]: ln for ln in plan["lines"]}
    assert by["NVDA"]["qty_trim"] == 2.0  # 20% de 10
    assert by["TSM"]["qty_trim"] == 1.0  # 20% de 5
    assert by["NVDA"]["value_trim_eur"] == 200.0
    assert by["TSM"]["value_trim_eur"] == 200.0
    assert plan["total_trim_eur"] == 400.0
    assert plan["cluster_value_eur"] == 2000.0  # 10*100 + 5*200
    assert plan["n_lines"] == 2


def test_non_cluster_lines_excluded():
    plan = _run_plan(
        members=["NVDA"],
        positions=[{"ticker": "NVDA", "qty": 10}, {"ticker": "KO", "qty": 50}],
        prices_map={"NVDA": 100.0, "KO": 60.0},
    )
    assert plan["n_lines"] == 1
    assert plan["lines"][0]["ticker"] == "NVDA"


def test_uniform_no_selection_every_line_same_pct():
    """Anti-biais #1 : AUCUNE sélection — chaque ligne trimée du même ratio."""
    plan = _run_plan(
        members=["A", "B", "C"],
        positions=[{"ticker": "A", "qty": 100}, {"ticker": "B", "qty": 7}, {"ticker": "C", "qty": 3}],
        prices_map={"A": 1.0, "B": 1.0, "C": 1.0},
    )
    for ln in plan["lines"]:
        assert abs(ln["qty_trim"] / ln["qty_held"] - 0.20) < 1e-9


def test_missing_price_excluded_not_fabricated():
    """Fail-soft : ligne sans prix → exclue + listée dans missing, PAS de trim inventé."""
    plan = _run_plan(
        members=["NVDA", "TSM"],
        positions=[{"ticker": "NVDA", "qty": 10}, {"ticker": "TSM", "qty": 5}],
        prices_map={"NVDA": 100.0},  # TSM absent
    )
    assert plan["n_lines"] == 1
    assert "TSM" in plan["missing"]
    assert plan["total_trim_eur"] == 200.0


def test_zero_and_negative_qty_skipped():
    plan = _run_plan(
        members=["NVDA", "TSM"],
        positions=[{"ticker": "NVDA", "qty": 0}, {"ticker": "TSM", "qty": -1}],
        prices_map={"NVDA": 100.0, "TSM": 200.0},
    )
    assert plan["n_lines"] == 0
    assert plan["total_trim_eur"] == 0.0


def test_format_empty_plan():
    plan = _run_plan(members=["NVDA"], positions=[], prices_map={})
    assert "aucune ligne" in ks.format_prorata_plan(plan)


def test_format_lists_lines_and_cash():
    plan = _run_plan(
        members=["NVDA"],
        positions=[{"ticker": "NVDA", "qty": 10}],
        prices_map={"NVDA": 100.0},
    )
    txt = ks.format_prorata_plan(plan)
    assert "NVDA" in txt
    assert "20%" in txt


def test_stage2_action_is_prorata_not_selective():
    """La reco Stage 2 doit être requalifiée sélectif → prorata uniforme."""
    assert "PRORATA" in ks.STAGE_ACTION[2].upper()
    assert "plus-corrélées" not in ks.STAGE_ACTION[2]
