"""Verrouille le durcissement de check_currency_native_consistency (04/08/2026).

LE TROU FERMÉ : l'invariant lisait UNIQUEMENT les colonnes legacy
(stop_price/target_price) pendant que la vérité vivait dans le schéma M1
(stop_value/stop_currency). Résultat mesuré sur la vraie base : 6 violations
invisibles — stops morts-nés MU (1 000 posé prix 751, mai) et KLAC, devises
EUR déclarées sur tickers USD (AVGO, AMZN — stops ET target_full).

Et le gate n'était exécuté QUE par la CI sur fixture : verte, pendant que la
prod divergeait. Il est désormais câblé dans le panneau monitors (Alerts).

Tests EXÉCUTABLES (module importable py3.10) — fixture mémoire + prix mockés.
"""
from __future__ import annotations

import sqlite3
import sys
import types

import pytest

import shared.thesis_invariants as ti


@pytest.fixture()
def cx():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE theses(
        id INTEGER PRIMARY KEY, ticker TEXT, status TEXT,
        stop_price REAL, entry_price REAL, target_price REAL,
        target_partial REAL, target_full REAL,
        stop_value REAL, stop_currency TEXT,
        target_partial_value REAL, target_partial_currency TEXT,
        target_full_value REAL, target_full_currency TEXT)""")
    c.execute("CREATE TABLE positions(ticker TEXT, qty REAL, status TEXT)")
    return c


@pytest.fixture(autouse=True)
def fake_prices(monkeypatch):
    """Prix natifs contrôlés — le check importe shared.prices DANS la fonction."""
    prices = {"MU": 891.88, "KLAC": 194.56, "AVGO": 389.0, "6857.T": 32500.0}
    mod = types.ModuleType("shared.prices")
    mod.get_current_price = lambda tk: prices.get(tk)
    monkeypatch.setitem(sys.modules, "shared.prices", mod)
    return prices


def _seed(cx, ticker, **kw):
    cols = {"status": "active", "ticker": ticker} | kw
    keys = ",".join(cols)
    cx.execute(f"INSERT INTO theses({keys}) VALUES({','.join('?'*len(cols))})",
               tuple(cols.values()))
    cx.execute("INSERT INTO positions VALUES(?,?,?)", (ticker, 10.0, "open"))


# ── Règle 1 : devise déclarée ≠ devise native = violation directe ───────────

def test_devise_declaree_fausse_est_attrapee_sans_heuristique(cx):
    """Le cas AVGO réel : stop_currency='EUR' sur un ticker USD.

    L'ancien check au ratio ne pouvait PAS l'attraper (EUR/USD ≈ 0.87,
    ratio dans la bande). La devise DÉCLARÉE se compare, elle ne s'estime pas.
    """
    _seed(cx, "AVGO", stop_value=335.0, stop_currency="EUR",
          target_full_value=500.0, target_full_currency="EUR")
    v = ti.check_currency_native_consistency(cx)
    assert sum("currency_declared" in x and "AVGO" in x for x in v) == 2, (
        "stop ET target_full en mauvaise devise doivent produire 2 violations"
    )


# ── Règle 2 : stop mort-né (≥ prix courant) ─────────────────────────────────

def test_stop_au_dessus_du_prix_est_mort_ne(cx):
    """Le cas MU réel : stop 1 000 $ posé quand le prix était 751 $.

    Un stop franchi À LA POSE n'est pas un stop — §XIV : « jamais de limbo »."""
    _seed(cx, "MU", stop_value=1000.0, stop_currency="USD")
    v = ti.check_currency_native_consistency(cx)
    assert any("stop_mort_ne" in x and "MU" in x for x in v)


def test_stop_sain_sous_le_prix_ne_declenche_rien(cx):
    _seed(cx, "MU", stop_value=685.0, stop_currency="USD")   # §XIV réel
    v = ti.check_currency_native_consistency(cx)
    assert not any("MU" in x for x in v)


# ── Règle 3 : ratio écrasé = split/unité non répercuté ──────────────────────

def test_split_non_repercute_est_suspecte(cx):
    """Le cas KLAC inverse : un stop resté en unités pré-split 10:1
    (23 $ contre un prix à 194 $) doit lever une alerte d'unité."""
    _seed(cx, "KLAC", stop_value=23.0, stop_currency="USD")
    v = ti.check_currency_native_consistency(cx)
    assert any("stop_unite_suspecte" in x and "KLAC" in x for x in v)


# ── Non-régression : le legacy reste vérifié, le sain reste silencieux ──────

def test_legacy_ratio_toujours_verifie(cx):
    """Le comportement historique (ratio sur stop_price legacy) survit."""
    _seed(cx, "6857.T", stop_price=225.0)  # JPY attendu : 225 vs 32 500 → ratio 0.007
    v = ti.check_currency_native_consistency(cx)
    assert any("currency_native" in x and "6857.T" in x for x in v)


def test_these_entierement_saine_zero_violation(cx):
    _seed(cx, "6857.T", stop_value=22500.0, stop_currency="JPY",
          target_full_value=45000.0, target_full_currency="JPY")
    assert ti.check_currency_native_consistency(cx) == []


def test_prix_indisponible_skip_gracieux(cx):
    """Ticker sans prix → skip, jamais une violation fabriquée (L15)."""
    _seed(cx, "INCONNU.XX", stop_value=10.0, stop_currency="EUR")
    assert ti.check_currency_native_consistency(cx) == []
