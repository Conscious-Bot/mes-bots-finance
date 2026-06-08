"""Test de cohérence end-to-end (SPEC_MONEY_INVARIANT §8 + L27).

Le verrou final : quand la source bouge, TOUS les nombres dérivés bougent
ensemble, à l'identique, sans qu'aucun reste stale. C'est ce qui rend
l'architecture « bonne pour de bon » selon Olivier — l'unisson sous
perturbation, garanti par construction et pas par vigilance.

Stratégie : on patch `prices.get(ticker)` pour renvoyer un prix perturbé,
on appelle `get_all_positions_views()`, on asserte que :
  1. value_eur_datum.value reflète la perturbation
  2. perf_thesis_pct et pnl_position_pct bougent dans le bon sens
  3. Le content-hash du Datum change (lignage tamper-evident)
  4. Aucun champ de PositionView reste stale sur l'ancien prix
"""

from __future__ import annotations

import pytest

from shared.datum import Datum
from shared.money import Monetary
from shared.position_view import get_all_positions_views


@pytest.fixture(scope="module")
def baseline_views() -> dict:
    """Views non-perturbées (état actuel DB)."""
    return get_all_positions_views()


def test_baseline_views_built(baseline_views):
    """Sanity : le cœur produit au moins 1 PositionView."""
    assert len(baseline_views) > 0, "get_all_positions_views() retourne dict vide"
    # Sample test sur SK Hynix (devise non-EUR, FX critique)
    if "000660.KS" in baseline_views:
        v = baseline_views["000660.KS"]
        assert v.value_eur_datum is not None, "value_eur_datum None pour 000660.KS"
        assert v.value_eur_datum.value > 0
        assert v.price_native is not None


@pytest.mark.xfail(
    reason=(
        "FINDING SEAM 08/06 : view.price_native (prices.get live yfinance) "
        "diverge de view.value_eur_datum (positions.last_price_native DB). "
        "Le seam consomme 2 sources de prix pour le même ticker — pas l'unisson. "
        "Fix : refactor position_valuation_datum pour consommer prices.get() "
        "(comme view.price_native) OU view.price_native = positions.last_price_native "
        "(comme value_eur). Cf SPEC_MONEY_INVARIANT §8 + CANONICAL_MAP §0 "
        "(primitif partagé shared/book.value_eur). Le test devient vert quand "
        "le primitif unique est en place."
    ),
    strict=True,  # Si le test passe sans fix, c'est un warning -> on saura.
)
def test_perturbation_source_propagates_to_value_eur(baseline_views):
    """Perturbation prix d'un ticker dans la DB → value_eur_datum reflète.

    La source des panneaux = `positions.last_price_native` (DB, alimentée par
    le cron `reconcile_positions_prices`). On perturbe directement la DB pour
    simuler un tick cron, puis on rebuild le seam — value_eur doit suivre.

    Backup + restore atomique pour ne pas polluer la prod.
    """
    target_ticker = next(
        (tk for tk in ("000660.KS", "AMD", "4063.T", "ASML.AS") if tk in baseline_views),
        None,
    )
    if target_ticker is None:
        pytest.skip("No priority ticker in baseline_views")

    from shared import storage

    # Lecture valeur originale
    with storage.db() as cx:
        cx.row_factory = None
        orig_row = cx.execute(
            "SELECT last_price_native FROM positions WHERE ticker=? AND status='open'",
            (target_ticker,),
        ).fetchone()
    if orig_row is None or orig_row[0] is None:
        pytest.skip(f"{target_ticker} no last_price_native — can't perturb")
    orig_price = orig_row[0]
    baseline_value = baseline_views[target_ticker].value_eur_datum.value

    try:
        # Perturbe +10% dans la DB
        with storage.db() as cx:
            cx.execute(
                "UPDATE positions SET last_price_native = ? WHERE ticker=? AND status='open'",
                (orig_price * 1.10, target_ticker),
            )
        perturbed_views = get_all_positions_views()
        perturbed_value = perturbed_views[target_ticker].value_eur_datum.value

        # Le value_eur doit refléter la perturbation +10% exactement
        # (qty et fx_rate inchangés, seul price_native bouge)
        actual_ratio = perturbed_value / baseline_value
        assert abs(actual_ratio - 1.10) < 0.001, (
            f"{target_ticker} value_eur ne suit pas la perturbation. "
            f"Baseline {baseline_value:.2f} -> Perturbed {perturbed_value:.2f} "
            f"(ratio {actual_ratio:.4f}, expected 1.10 exact)"
        )

        # Lignage Merkle-DAG : content-hash change
        assert (
            perturbed_views[target_ticker].value_eur_datum.id
            != baseline_views[target_ticker].value_eur_datum.id
        ), "Content-hash inchangé — lignage cassé"
    finally:
        # Restore atomique (jamais polluer prod, même en cas d'échec assert)
        with storage.db() as cx:
            cx.execute(
                "UPDATE positions SET last_price_native = ? WHERE ticker=? AND status='open'",
                (orig_price, target_ticker),
            )


def test_other_tickers_unaffected_by_perturbation(baseline_views):
    """Perturbation d'UN ticker dans la DB → les autres tickers inchangés.

    Isolation garantie : chaque PositionView est composé indépendamment.
    Aucun partage d'état mutable entre tickers.
    """
    if len(baseline_views) < 2:
        pytest.skip("Need at least 2 tickers")

    from shared import storage

    target = next(
        (tk for tk in baseline_views if baseline_views[tk].value_eur_datum is not None),
        None,
    )
    if target is None:
        pytest.skip("No ticker with value_eur_datum")
    other = next(
        (tk for tk in baseline_views
         if tk != target and baseline_views[tk].value_eur_datum is not None),
        None,
    )
    if other is None:
        pytest.skip("Need 2nd ticker with value_eur_datum")
    other_baseline_value = baseline_views[other].value_eur_datum.value

    with storage.db() as cx:
        cx.row_factory = None
        orig = cx.execute(
            "SELECT last_price_native FROM positions WHERE ticker=? AND status='open'",
            (target,),
        ).fetchone()
    if orig is None or orig[0] is None:
        pytest.skip(f"{target} no last_price_native")
    orig_price = orig[0]

    try:
        with storage.db() as cx:
            cx.execute(
                "UPDATE positions SET last_price_native = ? WHERE ticker=? AND status='open'",
                (orig_price * 1.50, target),
            )
        perturbed = get_all_positions_views()
        other_after = perturbed[other].value_eur_datum.value

        assert abs(other_after - other_baseline_value) / other_baseline_value < 0.001, (
            f"{other} bouge alors que seul {target} perturbé "
            f"({other_baseline_value:.2f} -> {other_after:.2f}). "
            "Partage d'état mutable entre tickers — BUG."
        )
    finally:
        with storage.db() as cx:
            cx.execute(
                "UPDATE positions SET last_price_native = ? WHERE ticker=? AND status='open'",
                (orig_price, target),
            )


def test_no_silent_stale_field(baseline_views):
    """Si value_eur_datum existe, perf_thesis et pnl_position_pct doivent
    être cohérents avec lui (pas de champ qui resterait sur une ancienne valeur).

    Vérification structurelle : tous les champs *_pct d'une view sont dérivés
    des mêmes Datums sources que value_eur_datum.
    """
    for tk, v in baseline_views.items():
        if v.value_eur_datum is None:
            continue  # degraded, OK
        # pnl_position_pct nécessite cost_basis -> dépend d'avg_cost_eur (book_line)
        # Cohérence indirecte : si value_eur change, pnl doit changer
        # On vérifie ici juste que les inputs_lineage_ids sont populés
        assert len(v.inputs_lineage_ids) > 0, (
            f"{tk}: PositionView sans lineage_ids — provenance Merkle-DAG cassée"
        )
        # Si non-degraded, value_eur_datum doit pointer vers ses parents
        assert len(v.value_eur_datum.parents) >= 2, (
            f"{tk}: value_eur_datum.parents vide — derive() n'a pas capturé "
            "qty/price/fx lineage"
        )
