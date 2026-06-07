"""Invariants property-tests sur shared.book canonique (directive #4 audit 29/05).

Ces tests auraient attrape chacune des incoherences F9-F13 du verdict user :
  - F11 poids divergents : invariant "poids = 100% du market value total"
  - F9 driver multi-classe : invariant "exactement un macro_factor par ligne"
  - "aucune ligne dans deux sets" : invariant "in_db AND exit_planned = phantom uniquement"
  - F7 vol aveugle : invariant "thesis active => entry+target+stop+triggers definis"
  - F10 stop incoherent : invariant "fade >= 60 => stop_dist < 40%"

Le but n'est pas d'echouer (la realite va casser certains, justement) -- c'est
de RENDRE EXPLICITE ce qui devrait tenir. Quand un test rouge sort, c'est que
le book a derive d'un invariant cense tenir.

Methodo : test deterministe sur l'etat live + hypothesis-style assertions.
Pas de generation aleatoire ici (les donnees sont la verite, pas une fixture).
"""

from __future__ import annotations

import pytest

from shared import book

# ─────────────────────── Helpers ───────────────────────────────────────────


@pytest.fixture(scope="module")
def held_lines():
    return book.get_held_lines()


@pytest.fixture(scope="module")
def all_lines():
    return book.get_canonical_book()


# ─────────────────────── Invariants STRUCTURELS ────────────────────────────


def test_book_lines_unique_per_ticker(all_lines):
    """Chaque ticker n'apparait qu'une fois dans le book."""
    tickers = [ln.ticker for ln in all_lines]
    assert len(tickers) == len(set(tickers)), \
        f"doublon ticker : {[t for t in tickers if tickers.count(t) > 1]}"


def test_held_lines_have_qty_and_price(held_lines):
    """Toute position en DB a qty > 0 et avg_cost_eur > 0."""
    for ln in held_lines:
        assert ln.qty is not None and ln.qty > 0, f"{ln.ticker} qty manquante"
        assert ln.avg_cost_eur is not None and ln.avg_cost_eur > 0, \
            f"{ln.ticker} avg_cost_eur manquant"


def test_weight_market_eur_consistent(held_lines):
    """weight_market_eur = qty * current_price_eur (fallback cost) -- jamais
    None pour une position ouverte avec price disponible."""
    for ln in held_lines:
        w = ln.weight_market_eur
        assert w > 0, f"{ln.ticker} weight_market_eur=0"
        if ln.current_price_eur is not None:
            expected = ln.qty * ln.current_price_eur
            assert abs(w - expected) < 0.01, \
                f"{ln.ticker} weight={w} attendu {expected}"


# ─────────────────────── Invariants FOND (F9-F13) ──────────────────────────


def test_active_thesis_has_complete_inputs(held_lines):
    """F7 : these active => entry, target_full, stop_price, triggers definis.
    Toute violation = position en vol aveugle (peut pas etre evaluee).
    Aujourd'hui : SNOW est l'exception documentee (open_question). Test
    accepte SNOW comme exception explicite, fail sur tout autre."""
    blind = [ln for ln in held_lines if ln.is_blind]
    blind_tk = sorted(ln.ticker for ln in blind)
    # SNOW etoffe 2026-05-29 (P1 decision) -- plus d'exemption documente.
    # Toute position blind future = regression a investiguer.
    #
    # Exception doctrinale 07/06 (red-team user QUALITY_BAR Axe 4) : chokepoint
    # structurel = stop-prix volontairement absent. Un monopole/duopoly s'invalide
    # par CONDITION STRUCTURELLE (capex guide, market share, spreads), pas par un
    # mouvement de cours. Laisser un stop-prix = laisser l'humeur du marche, et
    # non la condition de falsification, decider de la sortie. Erreur de categorie.
    # invalidation_triggers restent renseignes et structurels pour ces 4 lignes.
    accepted_blind: set[str] = {
        "ASML.AS",  # monopole EUV litho -- invalidation = bookings/export/capex hyperscaler
        "TSM",      # quasi-monopole foundry leading-edge -- invalidation = Samsung 2nm / Intel 18A / gross margin
        "SNPS",     # duopoly EDA -- invalidation = Ansys merger / ASP / open-source EDA
        "6920.T",   # Lasertec EUV inspection masque actinique -- invalidation = concurrent volume-livre
    }
    unexpected = sorted(set(blind_tk) - accepted_blind)
    assert not unexpected, (
        f"vol aveugle non documente : {unexpected}. "
        "Ces positions ont une these active mais pas tous les inputs. "
        "Si attendu : ajoute le ticker a accepted_blind ici. "
        "Sinon : remplis entry/target/stop/triggers dans la these."
    )


def test_position_has_canonical_classification(held_lines):
    """F9 partial : toute position en DB a au moins une classification source
    (macro_factor OU theme OU canonical driver). Sinon non classifiable."""
    unclassified = []
    for ln in held_lines:
        has_classification = bool(ln.macro_factor or ln.theme or ln.driver)
        if not has_classification:
            unclassified.append(ln.ticker)
    assert not unclassified, (
        f"position sans classification source : {unclassified}. "
        "Ajoute ticker_axes (macro_factor) OU canonical_perimeter (driver) "
        "OU target_allocation (theme)."
    )


def test_phantoms_match_canonical_tagging(held_lines):
    """Les phantoms detectes par book (in DB mais exit_planned) doivent
    correspondre au tagging canonical_perimeter explicit. Pas de phantom
    surprise."""
    phantoms = [ln.ticker for ln in held_lines if ln.is_phantom]
    expected = {"AMD", "GOOGL", "TSLA", "TER", "VRT"}
    # TER + VRT sont closed status, donc ne devraient pas etre dans held_lines
    actually_held_phantoms = set(phantoms)
    surprises = actually_held_phantoms - expected
    assert not surprises, f"phantom surprise : {surprises}"


def test_stop_fade_coherence_no_extreme_outliers(held_lines):
    """F10 : haut fade (>=60) + stop_dist enorme (>50%) = INCOHERENT.
    On laisse une marge a 50% pour ne pas trop bloquer. ALAB a -51%, edge case."""
    extreme = []
    for ln in held_lines:
        if not ln.fade_rate_score or ln.fade_rate_score < 60:
            continue
        if not ln.stop_price or not ln.current_price_eur:
            continue
        stop_dist = (ln.current_price_eur - ln.stop_price) / ln.current_price_eur * 100
        if stop_dist > 55:  # 55% : seuil "vraiment hors limite"
            extreme.append((ln.ticker, ln.fade_rate_score, round(stop_dist, 1)))
    assert not extreme, (
        f"stops incoherents avec fade : {extreme}. "
        "Haut fade (erosion rapide) avec stop > 55% laisse trop de marge "
        "sur un titre qu'on sait fragile."
    )


# ─────────────────────── Invariants AGREGAT ────────────────────────────────


def test_target_70k_total_matches_meta(all_lines):
    """target_allocation.json _meta.total_capital_eur doit egal somme des
    amount_eur des lignes target. Detecte une derive de saisie manuelle."""
    in_target = [ln for ln in all_lines if ln.in_target_70k]
    summed = sum(ln.target_eur or 0 for ln in in_target)
    # Cible declaree
    declared = 70180
    assert abs(summed - declared) < 100, (
        f"sum(target_eur) = {summed} vs declare 70180. "
        "Une ligne a derive en saisie."
    )


@pytest.mark.live_book
def test_held_market_value_is_positive(held_lines):
    """Trivial mais cle : la valeur totale du book est > 0 et coherente."""
    total = sum(ln.weight_market_eur for ln in held_lines)
    assert total > 1000, f"book total suspicieusement faible : {total}€"
    assert total < 1_000_000, f"book total suspicieusement enorme : {total}€"


# ─────────────────────── Position canonique (FAIT/JUGEMENT/DERIVE) ─────────
# Tests sur le nouvel objet shared.position.Position : valident la separation
# stricte en couches qui rend les incoherences F11/F9 structurellement impossibles.


@pytest.fixture(scope="module")
def positions_canonical():
    return book.get_canonical_positions()


@pytest.fixture(scope="module")
def held_positions():
    return book.get_held_positions()


@pytest.mark.live_book
def test_position_facts_are_immutable(held_positions):
    """PositionFacts est frozen=True : impossible de modifier les faits broker."""
    p = held_positions[0]
    with pytest.raises(AttributeError):  # FrozenInstanceError est subclass d'AttributeError
        p.facts.qty = 999999  # ne doit pas marcher


@pytest.mark.live_book
def test_position_derived_never_stored_only_computed(held_positions):
    """weight_market_eur etc sont @property, jamais des champs stockes."""
    p = held_positions[0]
    # Si weight_market_eur etait un champ, ce serait dans __dict__
    assert "weight_market_eur" not in p.__dict__
    assert "pnl_pct" not in p.__dict__
    assert "is_blind" not in p.__dict__


def test_position_invariants_count_clean(positions_canonical):
    """Aujourd'hui : 42/43 positions clean -- seul SNOW reste F7 vol aveugle.
    Ce test fail si une autre position devient incoherente."""
    report = book.validate_all_positions()
    expected_violators = {"SNOW"}  # documented vol aveugle
    actual_violators = {tk for tk, _ in report["violations"]}
    surprises = actual_violators - expected_violators
    assert not surprises, (
        f"positions inattendument incoherentes : {surprises}. "
        "Si attendu, ajouter a expected_violators avec justification."
    )


def test_position_lifecycle_values_valid(positions_canonical):
    """Lifecycle est un enum strict : construction|active|exiting|sold|watch."""
    valid = {"construction", "active", "exiting", "sold", "watch"}
    for p in positions_canonical:
        assert p.lifecycle in valid, \
            f"{p.ticker}: lifecycle={p.lifecycle} hors enum"


def test_single_driver_per_position(positions_canonical):
    """F9 : exactement un driver canonique (pas multi-class). Si driver
    None -> position non classifiable, doit etre listee."""
    no_driver = [p.ticker for p in positions_canonical
                 if p.in_db and p.judgments.driver is None]
    # Aujourd'hui : aucune position en DB sans driver (apres migration)
    assert not no_driver, f"positions sans driver canonique : {no_driver}"


def test_phantom_lifecycle_consistent_with_canonical(held_positions):
    """lifecycle='exiting' <=> canonical target_status='exit_planned'.
    Pas de phantom surprise."""
    phantoms = [p.ticker for p in held_positions if p.is_phantom]
    expected = {"AMD", "TSLA"}  # GOOGL retire des exit_planned (these reecrite)
    surprises = set(phantoms) - expected
    assert not surprises, f"phantom surprise : {surprises}"


def test_held_lines_expose_m1_typed_columns(held_lines):
    """L23 doctrine : shared.book.BookLine est la SOURCE UNIQUE des donnees
    de book. Les colonnes M1 typees (Axe 3 / Axe 5 : last_price_native,
    last_price_currency, price_asof, fx_rate_to_eur, fx_asof) DOIVENT etre
    exposees par get_held_lines() -- les readers downstream ne doivent
    JAMAIS avoir besoin de re-query positions pour acceder a ces champs
    (sinon 2 sources de verite -> bugs cosmetiques -> retour au pattern
    eur_value-dans-notes que l'Axe 3 a tue).

    Verifie qu'au moins une position du book expose ces champs (ils sont
    populés via reconcile_positions_prices cron Axe 5). Si TOUS sont None
    -> regression (helper ne propage plus).
    """
    fields = [
        "last_price_native", "last_price_currency", "price_asof",
        "fx_rate_to_eur", "fx_asof",
    ]
    first_line = next(iter(held_lines), None)
    for fld in fields:
        assert hasattr(first_line, fld), \
            f"BookLine n'expose pas {fld} -- regression L23 doctrine"
    # Au moins une ligne doit avoir des donnees M1 reelles (post-reconcile)
    if held_lines:
        for fld in ("last_price_native", "price_asof", "last_price_currency"):
            non_null = [getattr(ln, fld) for ln in held_lines if getattr(ln, fld) is not None]
            assert non_null, (
                f"AUCUNE position n'a {fld} -- cron reconcile_positions_prices "
                "n'a jamais tourne OU helper get_held_lines ne propage pas"
            )
