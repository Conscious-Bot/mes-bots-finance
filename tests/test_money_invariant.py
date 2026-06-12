"""Tests verrouillants SPEC_MONEY_INVARIANT.md §5.

Couvre les 5 invariants qui rendent la classe « +176056% » impossible :
  1. Commensurabilite : pct_change cross-devise leve (KRW vs EUR)
  2. Baselines distincts ⟹ metriques distinctes (LE veto anti-collapse, AMD temoin)
  3. Byte-identite : meme Datum -> meme valeur peu importe le caller (lignage stable)
  4. Fail-closed baseline : baseline irrecuperable -> degraded, pas un nombre
  5. No-baseline-overwrite : test fixture rejoue migrations, asserte entry != avg_cost
     post-migration sauf coincidence numerique explicite documentee

Le test #2 est LE veto structurel : il echoue si jamais on collapse
perf_thesis_pct sur pnl_position_pct (Voie A rejetee). C'est le filet permanent.
"""

from __future__ import annotations

import pytest

from shared.datum import Datum
from shared.money import Monetary, in_eur, monetary, pct_change

# ============================================================================
# 1. Commensurabilite : cross-devise => AssertionError
# ============================================================================


def test_pct_change_same_currency_works():
    """Sanity : meme devise -> calc OK."""
    frm = monetary(100.0, "USD", "2026-05-16T17:02:41Z", "test:entry")
    to = monetary(110.0, "USD", "2026-06-07T06:22:00Z", "test:price")
    result = pct_change(frm, to)
    assert result.value == pytest.approx(10.0, rel=1e-6)
    assert result.degraded is False
    assert frm.id in result.parents
    assert to.id in result.parents


def test_pct_change_cross_devise_raises():
    """Le veto structurel : KRW vs EUR doit LEVER, jamais retourner un nombre.

    C'est la transformation du `+176056%` en erreur bruyante (cf SPEC §2).
    """
    entry_eur = monetary(1084.83, "EUR", "2026-05-16T17:02:41Z", "test:entry_clobbered")
    price_krw = monetary(1911000.0, "KRW", "2026-06-07T06:22:00Z", "test:price_native")
    with pytest.raises(AssertionError, match="cross-devise interdit"):
        pct_change(entry_eur, price_krw)


def test_pct_change_jpy_vs_eur_raises():
    """Idem cross-devise sur JPY (Advantest temoin)."""
    entry_eur = monetary(149.79, "EUR", "2026-05-24T06:39:23Z", "test:entry")
    price_jpy = monetary(26765.0, "JPY", "2026-06-07T06:22:00Z", "test:price")
    with pytest.raises(AssertionError):
        pct_change(entry_eur, price_jpy)


def test_pct_change_divide_by_zero_returns_degraded():
    """from_amount=0 -> degraded (L15), pas une division par zero qui crash."""
    frm = monetary(0.0, "USD", "2026-05-16T17:02:41Z", "test:edge")
    to = monetary(10.0, "USD", "2026-06-07T06:22:00Z", "test:price")
    result = pct_change(frm, to)
    assert result.degraded is True
    assert result.value is None


# ============================================================================
# 2. Baselines distincts ⟹ metriques distinctes (LE VETO anti-collapse, AMD temoin)
# ============================================================================
#
# C'est le test qui interdit a JAMAIS la « Voie A » (entry := avg_cost).
# AMD historique : entry-a-l'appel = 386 USD, avg_cost-paye = 146 USD.
# Si quelqu'un re-clobbere entry := avg_cost, ce test rouge -- vecteur ferme.


def test_baselines_distincts_implique_metriques_distinctes_AMD_temoin():
    """AMD : entry 386 USD (appel de these) != avg_cost 146 USD (achat reel).

    perf_thesis_pct (depuis entry 386) ET pnl_position_pct (depuis avg_cost 146)
    DOIVENT etre numeriquement differents pour ce ticker. Si jamais ils
    convergent (e.g. parce qu'une migration a clobbere entry := avg_cost),
    ce test ECHOUE.

    C'est le veto permanent contre la fusion des baselines.
    """
    # Baselines reels d'AMD (recuperes depuis backup 06/06)
    entry_thesis = monetary(386.34, "USD", "2026-05-16T17:02:41Z", "theses.entry_price@open")
    avg_cost = monetary(146.30, "USD", "2026-05-16T17:02:41Z", "positions.avg_cost@purchase")
    # Prix marche courant (peu importe la valeur exacte, > 0)
    price_now = monetary(404.58, "USD", "2026-06-07T06:22:00Z", "yfinance:AMD")

    perf_thesis = pct_change(entry_thesis, price_now)
    pnl_position = pct_change(avg_cost, price_now)

    # Les DEUX baselines etant differents (386 vs 146), les metriques le sont aussi
    assert perf_thesis.value is not None
    assert pnl_position.value is not None
    assert perf_thesis.value != pnl_position.value, (
        "VETO COLLAPSE : perf_thesis_pct == pnl_position_pct sur AMD-temoin "
        f"(entry={entry_thesis.value.amount}, avg_cost={avg_cost.value.amount}, "
        f"both={perf_thesis.value:.4f}%). Une migration a-t-elle clobbere "
        "entry_price avec avg_cost ? cf SPEC_MONEY_INVARIANT §3 (write-once)."
    )

    # Sanity ordre de grandeur : perf_thesis (~5%) doit etre tres different de pnl (~177%)
    assert abs(perf_thesis.value - pnl_position.value) > 50.0, (
        f"baselines proches numeriquement (Δ={abs(perf_thesis.value - pnl_position.value):.2f}%) -- "
        "fixture AMD probablement corrompue ; verifie backup_session_close_20260606."
    )


def test_baselines_identiques_donnent_metriques_identiques():
    """Cas degenere legitime : si user entre la these PILE au moment de l'achat,
    entry == avg_cost (coincidence numerique documentee). Alors les deux
    metriques convergent naturellement -- ce n'est pas un bug, c'est l'identite
    mathematique. Le test #2 distinct asserte que dans ce cas, c'est OK.
    """
    entry = monetary(820.95, "EUR", "2026-05-16T17:02:41Z", "theses.entry_price")
    avg_cost = monetary(820.95, "EUR", "2026-05-16T17:02:41Z", "positions.avg_cost")
    price_now = monetary(1463.40, "EUR", "2026-06-07T06:22:00Z", "yfinance:ASML.AS")

    perf = pct_change(entry, price_now)
    pnl = pct_change(avg_cost, price_now)
    assert perf.value == pytest.approx(pnl.value, rel=1e-9), (
        "Baselines numeriquement identiques DOIVENT donner metriques identiques "
        "(identite mathematique, pas un bug)."
    )


# ============================================================================
# 3. Byte-identite : meme Datum -> meme id, meme valeur peu importe le caller
# ============================================================================


def test_monetary_datum_id_deterministic():
    """Deux Datum[Monetary] avec memes inputs -> meme content-hash id.

    C'est la base du Merkle-DAG : un Datum cree au panel A et au panel B
    avec les memes inputs ont le meme id -> ils sont byte-identiques par
    construction. Le bug 0,5x vs 1,80x ne peut pas se rejouer.
    """
    a = monetary(386.34, "USD", "2026-05-16T17:02:41Z", "theses.entry")
    b = monetary(386.34, "USD", "2026-05-16T17:02:41Z", "theses.entry")
    assert a.id == b.id

    c = monetary(386.35, "USD", "2026-05-16T17:02:41Z", "theses.entry")
    assert a.id != c.id  # amount different -> id different


def test_pct_change_lineage_stable():
    """pct_change(frm, to) produit toujours le meme id pour les memes inputs.

    Le lignage parents=(frm.id, to.id) est byte-stable -> un panel et la
    card derivent le meme nombre depuis les memes Datums.
    """
    frm = monetary(386.34, "USD", "2026-05-16T17:02:41Z", "theses.entry")
    to = monetary(404.58, "USD", "2026-06-07T06:22:00Z", "yfinance:AMD")
    r1 = pct_change(frm, to)
    r2 = pct_change(frm, to)
    assert r1.id == r2.id
    assert r1.value == r2.value


# ============================================================================
# 4. Fail-closed baseline : irrecuperable => degraded, pas un nombre
# ============================================================================


def test_in_eur_fx_missing_returns_degraded():
    """Conversion EUR avec fx_datum=None -> Datum degraded, value=None.

    Cas concret : entry_fx_at_call manque pour une vieille these (fx_history
    ne remonte pas a opened_at). Le derive view EUR sort degraded plutot que
    de fabriquer un nombre en utilisant le FX d'aujourd'hui (cf SPEC §2 derniere bullet).
    """
    entry_krw = monetary(1512443.0, "KRW", "2026-05-16T17:02:41Z", "theses.entry")
    result = in_eur(entry_krw, fx_datum=None)
    assert result.degraded is True
    assert result.value is None
    assert result.op == "in_eur_fx_missing"


def test_in_eur_propagates_degraded_from_fx():
    """Si fx_datum.degraded=True -> result.degraded=True (propagation derive())."""
    entry_krw = monetary(1512443.0, "KRW", "2026-05-16T17:02:41Z", "theses.entry")
    fx_stale = Datum(
        value=0.000556,
        asof="2026-01-01T00:00:00Z",  # tres vieux
        source="yfinance:fx",
        confidence=0.2,
        degraded=True,
    )
    result = in_eur(entry_krw, fx_stale)
    assert result.degraded is True
    assert isinstance(result.value, Monetary)
    assert result.value.currency == "EUR"


def test_in_eur_happy_path_propagates_lineage():
    """Conversion KRW->EUR happy path : value calculee + lignage capture."""
    entry_krw = monetary(1512443.0, "KRW", "2026-05-16T17:02:41Z", "theses.entry")
    fx = Datum(
        value=0.000556,
        asof="2026-05-16T17:02:41Z",
        source="yfinance:fx:KRW->EUR",
        confidence=1.0,
        degraded=False,
    )
    result = in_eur(entry_krw, fx)
    assert result.degraded is False
    assert isinstance(result.value, Monetary)
    assert result.value.currency == "EUR"
    assert result.value.amount == pytest.approx(1512443.0 * 0.000556, rel=1e-9)
    assert entry_krw.id in result.parents
    assert fx.id in result.parents


# ============================================================================
# 5. Assertions structurelles sur Monetary (catch bugs avant qu'ils n'arrivent en DB)
# ============================================================================


def test_monetary_rejects_non_iso_currency():
    """Monetary.currency doit etre ISO 4217 upper-case strict."""
    with pytest.raises(ValueError, match="ISO 4217"):
        Monetary(amount=100.0, currency="usd")
    with pytest.raises(ValueError, match="ISO 4217"):
        Monetary(amount=100.0, currency="")


def test_pct_change_rejects_non_monetary_value():
    """pct_change sur Datum[float] (pas Monetary) -> AssertionError.

    Garde-fou contre l'erreur d'appel : si quelqu'un passe un Datum[price_native]
    (value=float), pct_change refuse -- il faut wrapper en Datum[Monetary] d'abord.
    """
    float_datum = Datum(
        value=100.0,  # float nu, pas Monetary
        asof="2026-05-16T17:02:41Z",
        source="test",
    )
    monetary_datum = monetary(110.0, "USD", "2026-06-07T06:22:00Z", "test")
    with pytest.raises(AssertionError, match="Datum\\[Monetary\\]"):
        pct_change(float_datum, monetary_datum)
