"""Tracer-bullet test du seam render-level (SPEC §7.bis).

Discipline walking-skeleton (L24) : on valide le seam `get_all_positions_views()`
avec input REEL avant de migrer 13 panels qui en dependent. Le test prouve que
le seam donne des valeurs coherentes avec ce que le broker affiche, sur les
tickers les plus tendus du book (devises non-EUR/USD avec FX significatif).

Tickers prioritaires (Olivier 08/06 soir) :
  - 000660.KS (SK Hynix, KRW, FX ~0.000556)
  - 6857.T    (Advantest, JPY, FX ~0.005414)
  - 4063.T    (Shin-Etsu, JPY, meme FX)

Le test n'est PAS un test unitaire isole : il consomme la DB live (data/bot.db)
et fetch potentiellement yfinance. C'est intentionnel -- tracer-bullet a la L24
doctrine. Si yfinance est down ou la DB est hors etat attendu, le test skip
gracefully plutot que de polluer le signal.
"""

from __future__ import annotations

import pytest

from shared.position_view import PositionView, get_all_positions_views

# Valeurs broker connues au 2026-06-07 (price_asof 06:22 UTC, cf SQL).
# Tolerance : prix bougent au cours du temps (cron 15min). On verifie
# la coherence d'ordre, pas la valeur exacte instantanee.
BROKER_KNOWN = {
    "000660.KS": {
        "qty": 1.4809,
        "avg_cost_eur": 1084.83,
        "expected_pnl_pct_at_snapshot": 6.13,   # +6.1% au 07/06
        "currency_native": "KRW",
        "fx_band": (0.0004, 0.0008),           # KRW/EUR ~0.00056
    },
    "6857.T": {
        "qty": 12.1029,
        "avg_cost_eur": 149.79,
        "expected_pnl_pct_at_snapshot": -3.26,  # -3.3% au 07/06
        "currency_native": "JPY",
        "fx_band": (0.004, 0.008),             # JPY/EUR ~0.0054
    },
    "4063.T": {
        "qty": 107.5220,
        "avg_cost_eur": 41.85,
        "expected_pnl_pct_at_snapshot": -4.92,  # -4.9% au 07/06
        "currency_native": "JPY",
        "fx_band": (0.004, 0.008),
    },
}


def test_seam_returns_dict_typed_correctly():
    """Sanity : le seam retourne dict[str, PositionView] valide."""
    views = get_all_positions_views()
    assert isinstance(views, dict)
    for tk, v in views.items():
        assert isinstance(tk, str)
        assert tk == tk.upper(), f"ticker key not upper-cased: {tk}"
        assert isinstance(v, PositionView)
        assert v.ticker == tk


def test_seam_covers_priority_tickers():
    """Les 3 tickers prioritaires sont dans le seam (sinon yfinance ou DB cassee)."""
    views = get_all_positions_views()
    missing = [tk for tk in BROKER_KNOWN if tk not in views]
    if missing:
        pytest.skip(
            f"Tickers manquants du seam : {missing}. "
            "DB hors etat ou yfinance indisponible -- tracer-bullet skipped."
        )


@pytest.mark.parametrize("ticker", list(BROKER_KNOWN.keys()))
def test_seam_value_eur_coherent_with_qty_price_fx(ticker: str):
    """Le value_eur du seam doit etre coherent avec qty broker + prix natif + FX.

    Si le seam casse cette coherence, on a une fuite de devise quelque part dans
    la chaine compute_position / position_valuation_datum.
    """
    views = get_all_positions_views()
    if ticker not in views:
        pytest.skip(f"{ticker} absent du seam (DB/yfinance) -- skipped")
    v = views[ticker]

    if v.value_eur_datum is None:
        pytest.skip(f"{ticker} : value_eur_datum None (degraded) -- skipped")

    known = BROKER_KNOWN[ticker]
    value_eur = v.value_eur_datum.value
    qty = known["qty"]
    price_native = v.price_native
    fx_rate = v.fx_rate

    assert price_native is not None and price_native > 0
    assert fx_rate is not None
    lo, hi = known["fx_band"]
    assert lo < fx_rate < hi, (
        f"{ticker} fx_rate={fx_rate} hors bande attendue {known['fx_band']} "
        f"({known['currency_native']}/EUR)"
    )

    expected_value = qty * price_native * fx_rate
    # Tolerance 5% : qty seam peut differer legerement de qty broker (frais),
    # mais ordre de grandeur doit matcher.
    assert abs(value_eur - expected_value) / expected_value < 0.05, (
        f"{ticker} value_eur={value_eur:.2f} ecart >5% vs qty*price*fx={expected_value:.2f}"
    )


@pytest.mark.parametrize("ticker", list(BROKER_KNOWN.keys()))
def test_seam_pnl_position_pct_sane(ticker: str):
    """Le pnl_position_pct doit etre dans un ordre de grandeur sensé.

    PAS +184590% (le bug fondateur native vs EUR). PAS NaN. Doit etre dans
    [-50%, +500%] pour un book sain -- borne large pour resister aux mouvements
    de marche, mais qui detecte tout mismatch FX structurel.

    Le snapshot broker au 07/06 sert d'ancre orientation (signe + ordre), pas
    egalite stricte (le prix bouge entre snapshot et test live).
    """
    views = get_all_positions_views()
    if ticker not in views:
        pytest.skip(f"{ticker} absent du seam -- skipped")
    v = views[ticker]

    if v.pnl_position_pct is None:
        pytest.skip(f"{ticker} : pnl_position_pct None (degraded) -- skipped")

    pct = v.pnl_position_pct
    # Garde-fou anti-+184k% : si pct hors bande raisonnable, c'est un mismatch FX
    assert -50.0 < pct < 500.0, (
        f"{ticker} pnl_position_pct={pct:.2f}% hors bande sane [-50, +500]. "
        "Probable mismatch native/EUR dans la chaine."
    )

    # Orientation vs snapshot broker (signe meme si magnitude divergente).
    # On accepte un ecart absolu de 30 points (le prix peut bouger sensiblement
    # entre le snapshot et le test live, mais pas d'inverser signe sur +6% ou -3%).
    known_pct = BROKER_KNOWN[ticker]["expected_pnl_pct_at_snapshot"]
    assert abs(pct - known_pct) < 30.0, (
        f"{ticker} pnl_position_pct={pct:.2f}% diverge de >30pp vs broker snapshot "
        f"{known_pct:+.2f}% (07/06). Soit le marche a bouge enormement, soit la chaine derive."
    )


@pytest.mark.parametrize("ticker", list(BROKER_KNOWN.keys()))
def test_seam_perf_thesis_pct_native_vs_native(ticker: str):
    """perf_thesis_pct doit etre FX-invariant (native vs native).

    Si entry_native et price_native sont tous les deux en KRW (ou JPY), le ratio
    ne doit JAMAIS produire de +184590%. Garde-fou identique au pnl_position_pct.
    """
    views = get_all_positions_views()
    if ticker not in views:
        pytest.skip(f"{ticker} absent du seam -- skipped")
    v = views[ticker]

    if v.perf_thesis_pct is None:
        # entry_native ou price_native manquant -- acceptable, pas un fail
        pytest.skip(f"{ticker} : perf_thesis_pct None -- skipped")

    pct = v.perf_thesis_pct
    assert -50.0 < pct < 500.0, (
        f"{ticker} perf_thesis_pct={pct:.2f}% hors bande sane. "
        f"entry_native={v.entry_native}, price_native={v.price_native} -- "
        "probable mismatch devise (entry stocke en EUR vs price native)."
    )
