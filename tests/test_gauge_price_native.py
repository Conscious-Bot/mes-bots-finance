"""SPEC_GAUGE §5 tests verrouillants — axe-prix natif pur (post-bascule étape 2).

Organisation :
  - Helper tests (BL → dict)      : H1..H4
  - Renderer tests (dict → HTML)  : R1..R9
  - Scenarios end-to-end (BL→HTML): C1..C6
  - Bonus verrous structurels     : B1..B2

Stratégie fixture : SimpleNamespace local — pas de DB, déterministe, isole la
géométrie. Les cas réalistes (SK Hynix, AMD, 6857.T) viennent du sweep 10/06
panneau asym, valeurs hand-checked.

Les 2 tests pivots (verrouillent les bugs d'origine, frontalement) :
  - H1 test_helper_single_source : verrou L27 contre fork rebirth via current_price_eur
  - C5 test_no_negative_left_anywhere : verrou frontal contre partial négatif (interp 1)
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from dashboard.render import _gauge_prices_native, _position_axis_price

# ============================================================
# Helpers
# ============================================================

def make_bl(
    avg_cost_eur: float | None = 100.0,
    fx_rate_to_eur: float | None = 1.0,
    last_price_native: float | None = 150.0,
    stop_price: float | None = 100.0,
    target_full: float | None = 200.0,
    target_partial: float | None = 150.0,
    last_price_currency: str = "USD",
    **extra,
):
    """BookLine factice pour tests géométrie. extra propage les attrs piège."""
    kwargs = {
        "avg_cost_eur": avg_cost_eur,
        "fx_rate_to_eur": fx_rate_to_eur,
        "last_price_native": last_price_native,
        "stop_price": stop_price,
        "target_full": target_full,
        "target_partial": target_partial,
        "last_price_currency": last_price_currency,
    }
    kwargs.update(extra)
    return SimpleNamespace(**kwargs)


def make_pr(
    stop_native: float = 100.0,
    full_native: float = 200.0,
    partial_native: float | None = 150.0,
    cost_native: float = 110.0,
    cur_native: float = 150.0,
    currency: str = "USD",
    cost_eur: float = 110.0,
    cur_eur: float = 150.0,
    pnl_eur_pct: float = 36.36,
    has_band: bool = True,
):
    """Dict prices factice pour tests renderer isolé (sans passer par helper)."""
    return {
        "stop_native": stop_native,
        "full_native": full_native,
        "partial_native": partial_native,
        "cost_native": cost_native,
        "cur_native": cur_native,
        "currency": currency,
        "cost_eur": cost_eur,
        "cur_eur": cur_eur,
        "pnl_eur_pct": pnl_eur_pct,
        "has_band": has_band,
    }


def parse_left(html: str, marker_class: str) -> float | None:
    """Extrait la valeur left:X% du premier marker matchant la classe."""
    import re
    m = re.search(rf'class="[^"]*{re.escape(marker_class)}[^"]*"\s+style="left:([0-9.]+)%', html)
    return float(m.group(1)) if m else None


# ============================================================
# Helper tests (BL → dict)
# ============================================================

def test_helper_single_source_cur_eur_from_native_x_fx_never_from_eur_attr():
    """H1 — Verrou L27 : cur_eur = cur_native × fx, JAMAIS depuis current_price_eur.

    Le piège que ce test ferme : si un futur edit lit getattr(bl, 'current_price_eur', ...)
    au lieu de calculer cur_n × fx, le fork ressuscite — axe natif et label EUR
    portent des prix différents sur fx jitter. Cure nuit 09/06, verrouillée frontalement.
    """
    bl = make_bl(
        avg_cost_eur=100.0, fx_rate_to_eur=0.8, last_price_native=150.0,
        current_price_eur=99999.0,  # PIÈGE : attribut divergent. Le helper DOIT l'ignorer.
    )
    pr = _gauge_prices_native(bl)
    assert pr is not None
    assert pr["cur_eur"] == pytest.approx(150.0 * 0.8)
    assert pr["cur_eur"] != 99999.0
    assert pr["cost_native"] == pytest.approx(100.0 / 0.8)
    expected_pnl = (150.0 * 0.8 - 100.0) / 100.0 * 100.0
    assert pr["pnl_eur_pct"] == pytest.approx(expected_pnl)


def test_helper_fail_closed_when_avg_cost_eur_missing():
    """H2 — Fail-closed L15 : pas d'avg_cost_eur → None, pas de fallback inventé."""
    assert _gauge_prices_native(make_bl(avg_cost_eur=None)) is None
    assert _gauge_prices_native(make_bl(avg_cost_eur=0)) is None
    assert _gauge_prices_native(make_bl(avg_cost_eur=-5)) is None


def test_helper_fail_closed_when_fx_or_cur_missing():
    """H3 — Fail-closed sur fx ou last_price_native manquant."""
    assert _gauge_prices_native(make_bl(fx_rate_to_eur=None)) is None
    assert _gauge_prices_native(make_bl(fx_rate_to_eur=0)) is None
    assert _gauge_prices_native(make_bl(last_price_native=None)) is None
    assert _gauge_prices_native(make_bl(last_price_native=0)) is None


def test_helper_has_band_false_when_stop_or_full_missing():
    """H4 — has_band=False si stop ou full manque (cibles partielles partielles ok)."""
    pr_no_stop = _gauge_prices_native(make_bl(stop_price=None))
    assert pr_no_stop is not None and pr_no_stop["has_band"] is False

    pr_no_full = _gauge_prices_native(make_bl(target_full=None))
    assert pr_no_full is not None and pr_no_full["has_band"] is False

    pr_both = _gauge_prices_native(make_bl(stop_price=None, target_full=None))
    assert pr_both is not None and pr_both["has_band"] is False

    # Partial manquant ne casse pas la bande (cible accessoire)
    pr_no_partial = _gauge_prices_native(make_bl(target_partial=None))
    assert pr_no_partial is not None and pr_no_partial["has_band"] is True


# ============================================================
# Renderer tests (dict → HTML)
# ============================================================

def test_renderer_axis_band_anchored_on_stop_full():
    """R1 — stop@10%, full@90% par construction, indépendant de cur_native."""
    for cur in (50.0, 150.0, 250.0, 1000.0):
        html = _position_axis_price(make_pr(stop_native=100, full_native=200, cur_native=cur))
        assert 'class="tbar-tick stop"' in html and 'left:10.0%' in html
        assert 'class="tbar-tick target"' in html and 'left:90.0%' in html


def test_renderer_cost_above_full_goes_overflow_stale():
    """R2 — cost > full → caret lane droite (left>90) + classe stale + chevron ›."""
    html = _position_axis_price(make_pr(
        stop_native=100, full_native=200, cost_native=300, cur_native=150,
    ))
    cost_v = parse_left(html, "tbar-cost-caret")
    assert cost_v is not None and cost_v > 90.0, f"cost_v={cost_v} pas en lane droite"
    assert "tbar-cost-caret stale" in html
    assert "tbar-chevron-right" in html and "›" in html


def test_renderer_dot_overflow_chevron_when_beyond():
    """R3 — cur > full → dot lane droite + classe acc + chevron ›."""
    html = _position_axis_price(make_pr(
        stop_native=100, full_native=200, cur_native=250, cost_native=110,
    ))
    dot_v = parse_left(html, "tbar-dot")
    assert dot_v is not None and dot_v > 90.0
    assert "tbar-dot acc" in html
    assert "tbar-chevron-right" in html


def test_renderer_dot_bear_when_below_stop():
    """R4 (raffinement B) — cur < stop → dot lane gauche + classe bear + chevron ‹."""
    html = _position_axis_price(make_pr(
        stop_native=100, full_native=200, cur_native=80, cost_native=110,
    ))
    dot_v = parse_left(html, "tbar-dot")
    assert dot_v is not None and dot_v < 10.0
    assert "tbar-dot bear" in html
    assert "tbar-chevron-left" in html


def test_renderer_native_eur_separation_invariant():
    """R5 — € apparaît UNIQUEMENT dans title=, jamais dans style=."""
    import re
    html = _position_axis_price(make_pr(
        stop_native=100, full_native=200, cur_native=150,
        cost_eur=110.0, cur_eur=150.0,
    ))
    # title contient bien le €
    assert "€" in html
    # Aucun € dans les style= (uniquement les % de position visuelle)
    for style_match in re.findall(r'style="([^"]*)"', html):
        assert "€" not in style_match, f"€ trouvé dans style: {style_match}"


def test_renderer_hover_payload_no_pct_only_native_prices():
    """R6 — data-axmin/axmax = prix natifs, data-axis-mode='price-native', currency exposée."""
    html = _position_axis_price(make_pr(
        stop_native=100, full_native=200, currency="KRW",
    ))
    assert 'data-axmin="100.0000"' in html
    assert 'data-axmax="200.0000"' in html
    assert 'data-axis-mode="price-native"' in html
    assert 'data-currency="KRW"' in html


def test_renderer_fail_closed_when_full_missing_degraded_html():
    """R7 — has_band=False → HTML degraded, pas de tick target, message dans title."""
    html = _position_axis_price(make_pr(has_band=False, full_native=None))
    assert 'class="tbar sig-pricenat degraded"' in html or "degraded" in html
    assert 'class="tbar-tick target"' not in html
    assert "non défini" in html


def test_renderer_overflow_rational_bounded_never_clamped_to_100():
    """R8 — verrou §6.5 banni : overflow rationnel, asymptote vers 100, jamais clamp.

    cur_n=10000 avec full_n=200 → dot_v très proche de 100 mais STRICTEMENT < 100.
    """
    html = _position_axis_price(make_pr(
        stop_native=100, full_native=200, cur_native=10000, cost_native=110,
    ))
    dot_v = parse_left(html, "tbar-dot")
    assert dot_v is not None
    assert 90.0 < dot_v < 100.0, f"dot_v={dot_v} pas dans overflow rationnel strict"


def test_renderer_returns_empty_when_prices_none():
    """R9 — _position_axis_price(None) == '' (contrat fail-safe callers)."""
    assert _position_axis_price(None) == ""


# ============================================================
# Scenarios end-to-end (BL → dict → HTML)
# ============================================================

def test_scenario_skhynix_beyond_visual_and_classified():
    """C1 — SK Hynix KRW : cur > full → dot lane droite + chevron + classification Beyond.

    Fixture réaliste vraie saga SK Hynix : avg_cost_eur=126 → cost_native ≈ 180k
    KRW ≈ full_native (cost moyenné jusqu'à frôler la target, source du diagnostic
    10/06 + L30). Cas plus parlant que l'irréaliste cost=1.3M KRW.
    """
    bl = make_bl(
        avg_cost_eur=126.0, fx_rate_to_eur=0.0007,
        last_price_native=210000.0, stop_price=160000.0,
        target_full=180000.0, target_partial=170000.0,
        last_price_currency="KRW",
    )
    pr = _gauge_prices_native(bl)
    assert pr is not None and pr["has_band"]
    # Classification Beyond par construction (cur_n ≥ full_n)
    assert pr["cur_native"] >= pr["full_native"]
    html = _position_axis_price(pr)
    dot_v = parse_left(html, "tbar-dot")
    assert dot_v is not None and dot_v > 90.0
    assert "tbar-chevron-right" in html


def test_scenario_amd_closest_visual_and_classified():
    """C2 — AMD : cost très bas (cost<stop) → caret overflow gauche + dot dans bande Closest."""
    bl = make_bl(
        avg_cost_eur=170.0, fx_rate_to_eur=1.0,
        last_price_native=524.0, stop_price=396.0,
        target_full=600.0, target_partial=500.0,
        last_price_currency="USD",
    )
    pr = _gauge_prices_native(bl)
    assert pr is not None and pr["has_band"]
    # Classification Closest (cur < full)
    assert pr["cur_native"] < pr["full_native"]
    html = _position_axis_price(pr)
    dot_v = parse_left(html, "tbar-dot")
    assert dot_v is not None and 10.0 < dot_v < 90.0
    # cost overflow gauche (cost < stop) → caret en lane gauche + chevron ‹
    cost_v = parse_left(html, "tbar-cost-caret")
    assert cost_v is not None and cost_v < 10.0
    assert "tbar-chevron-left" in html


def test_scenario_6857t_partial_native_fixed_in_axis():
    """C3 — 6857.T JPY (renforcée) : partial tick à son prix natif fixe, jamais négatif.

    Verrou §6.1 interp 1 banni : peu importe où se trouve cost, le partial occupe
    sa position selon partial_native vs [stop_native, full_native], pas selon un %
    depuis cost.
    """
    bl = make_bl(
        avg_cost_eur=18.0, fx_rate_to_eur=0.0061,
        last_price_native=3500.0, stop_price=2000.0,
        target_full=4000.0, target_partial=3000.0,
        last_price_currency="JPY",
    )
    pr = _gauge_prices_native(bl)
    html = _position_axis_price(pr)
    # partial_native=3000, bande [2000,4000] → frac=(3000-2000)/2000=0.5 → 10+0.5*80=50%
    partial_v = parse_left(html, "tbar-tick partial")
    assert partial_v is not None and partial_v == pytest.approx(50.0, abs=0.1)
    # data-axmin reste stop_native (positif), jamais négatif
    assert 'data-axmin="2000.0000"' in html


def test_scenario_beyond_split_consistent_with_visual_no_divergence():
    """C4 — Pour N cas (cur >/=/< full), classification cur≥full ⇔ dot_v≥90 strict.

    Verrou §6.2 interp 2 banni : visuel et classement par construction ne peuvent
    plus diverger (cure SK Hynix dot sous tick mais Beyond / AMD dot au-dessus mais Closest).
    """
    cases = [
        ("below_full", 100.0, 200.0, 150.0, False),
        ("at_full",    100.0, 200.0, 200.0, True),
        ("above_full", 100.0, 200.0, 250.0, True),
        ("far_above",  100.0, 200.0, 1000.0, True),
    ]
    for name, stop, full, cur, expected_beyond in cases:
        bl = make_bl(stop_price=stop, target_full=full, last_price_native=cur)
        pr = _gauge_prices_native(bl)
        is_beyond_classif = pr["cur_native"] >= pr["full_native"]
        html = _position_axis_price(pr)
        dot_v = parse_left(html, "tbar-dot")
        is_beyond_visual = dot_v >= 90.0
        assert is_beyond_classif == is_beyond_visual == expected_beyond, (
            f"{name}: classif={is_beyond_classif} visual={is_beyond_visual} expected={expected_beyond}"
        )


def test_no_negative_left_anywhere_on_realistic_cases():
    """C5 — Verrou frontal : AUCUN left:-X% dans le HTML rendu, JAMAIS.

    Le bug d'origine (interp 1 partial négatif = "prise de profit à perte" absurde)
    tué par construction. Test enforce l'invariant littéralement sur 6 cas du book.
    """
    cases = [
        # (name, stop_n, full_n, partial_n, cur_n, avg_cost_eur, fx, ccy)
        ("CCJ",     62.14,    95.54,    80.0,    91.12,  94.98, 1.0,    "USD"),
        ("LNG",    100.0,    150.0,    120.0,   138.0,  125.0, 1.0,    "USD"),
        ("4063.T", 1500.0,   2500.0,   2000.0,  2300.0,  14.0, 0.0061, "JPY"),
        ("AMZN",   150.0,    250.0,    200.0,   220.0,  215.0, 1.0,    "USD"),
        ("6857.T", 2000.0,   4000.0,   3000.0,  3500.0,  18.0, 0.0061, "JPY"),
        ("AMD",    396.0,    600.0,    500.0,   524.0,  170.0, 1.0,    "USD"),  # cost<stop → caret overflow gauche
        # Nicety Olivier : couvrir branche overflow DROIT (Beyond, cost ≈ full saga réelle)
        ("SKHynix", 160000.0, 180000.0, 170000.0, 210000.0, 126.0, 0.0007, "KRW"),  # cur > full → dot overflow droit ; cost_n ≈ 180k ≈ full (vraie saga)
    ]
    for name, stop, full, partial, cur, avg_eur, fx, ccy in cases:
        bl = make_bl(
            avg_cost_eur=avg_eur, fx_rate_to_eur=fx, last_price_native=cur,
            stop_price=stop, target_full=full, target_partial=partial,
            last_price_currency=ccy,
        )
        pr = _gauge_prices_native(bl)
        assert pr is not None and pr["has_band"], f"{name}: helper fail-closed inattendu"
        html = _position_axis_price(pr)
        assert "left:-" not in html, f"{name}: NEGATIVE LEFT DETECTED → {html}"


def test_scenario_pr_identity_split_and_gauge_share_same_object():
    """C6 — Le dict pr du helper, consommé deux fois (split test + render), donne
    les mêmes valeurs natives. Verrou de la cure fork étape 2 (identité littérale)."""
    bl = make_bl(
        avg_cost_eur=18.0, fx_rate_to_eur=0.0061, last_price_native=3500.0,
        stop_price=2000.0, target_full=4000.0, target_partial=3000.0,
        last_price_currency="JPY",
    )
    pr1 = _gauge_prices_native(bl)
    pr2 = _gauge_prices_native(bl)
    # Mêmes valeurs (helper déterministe sur la même entrée)
    assert pr1["cur_native"] == pr2["cur_native"]
    assert pr1["full_native"] == pr2["full_native"]
    # Le split utilise cur_native vs full_native (les mêmes champs que le renderer)
    assert (pr1["cur_native"] >= pr1["full_native"]) == (pr2["cur_native"] >= pr2["full_native"])


# ============================================================
# Bonus verrous structurels
# ============================================================

def test_bonus_js_hover_inset_geometry_present_in_source():
    """B1 — Verrou §0-B anti +1820% : le JS hover doit contenir la géométrie inverse
    inset (p-10)/80 ET le marqueur 'hors bande'. Un revert au linéaire bête
    `axmin+(axmax-axmin)*p/100` (sans l'inset) se fait choper ici.

    Grep SOURCE (pas render output) — le JS est une string littérale statique dans
    render.py, indépendante du runtime ; pas besoin d'invoquer render() qui coûte
    ~75s + dépendance DB/réseau (contradit l'en-tête déterministe du fichier).
    """
    from pathlib import Path
    src = Path("dashboard/render.py").read_text()
    assert "(p-10)/80" in src, "JS hover linéaire détecté (régression §0-B)"
    assert "hors bande" in src


def test_bonus_known_gap_degraded_binary_documented_in_source():
    """B2 — KNOWN-GAP §4 doit être mentionné dans le code source (anti-régression
    sous-spec)."""
    from pathlib import Path
    src = Path("dashboard/render.py").read_text()
    assert "KNOWN-GAP" in src, "KNOWN-GAP §4 absent du source render.py"
