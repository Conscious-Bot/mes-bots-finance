"""Prédicat near-stop CANONIQUE (cure 04/07 : 6 définitions → 1).

Avant : « position proche du stop » = 4 chiffres à l'écran (2/0/9/8) pour 4
définitions + 2 variantes cachées — le hero Positions disait « Near stop 0 ·
no losing position critical » pendant que la table du même écran taguait CCJ
« AT STOP » (frame perdante entrée-THÈSE vs P&L BROKER, seuils 5/10 mélangés,
un site sans filtre, un SQL ad hoc dans la bande monitors).
"""

from __future__ import annotations

from pathlib import Path

from shared.portfolio_analytics import (
    NEAR_STOP_ALERT_PCT,
    NEAR_STOP_WATCH_PCT,
    is_near_stop,
)

# ---------- le prédicat (source de vérité unique) ----------


def test_ccj_case_alert():
    """LE cas du fork : CCJ à 3.4% du stop, +7.4% vs entrée thèse mais −11.2%
    broker → ALERT (l'ancien hero l'excluait via le frame thèse)."""
    assert is_near_stop(3.4, -11.2, NEAR_STOP_ALERT_PCT) is True


def test_winner_trailing_stop_not_alert():
    """User 19/06 : « astera labs +90% pas du tout near stop » — un winner dont
    le stop trailing est remonté = sécurisation, pas alerte."""
    assert is_near_stop(3.0, +90.0, NEAR_STOP_ALERT_PCT) is False
    assert is_near_stop(3.0, +90.0, NEAR_STOP_WATCH_PCT) is False


def test_stop_breached_is_alert():
    """Stop déjà franchi (distance négative) + perdante → alerte a fortiori."""
    assert is_near_stop(-2.0, -5.0, NEAR_STOP_ALERT_PCT) is True


def test_thresholds_boundaries_strict():
    assert is_near_stop(4.99, -1.0, NEAR_STOP_ALERT_PCT) is True
    assert is_near_stop(5.0, -1.0, NEAR_STOP_ALERT_PCT) is False  # strict
    assert is_near_stop(9.99, -1.0, NEAR_STOP_WATCH_PCT) is True
    assert is_near_stop(10.0, -1.0, NEAR_STOP_WATCH_PCT) is False


def test_missing_data_fail_closed():
    """Donnée manquante → False (pas d'alerte fabriquée, L15)."""
    assert is_near_stop(None, -1.0) is False
    assert is_near_stop(3.0, None) is False
    assert is_near_stop(None, None) is False


def test_flat_pnl_not_losing():
    """pnl == 0 n'est pas perdante (strict < 0)."""
    assert is_near_stop(3.0, 0.0, NEAR_STOP_ALERT_PCT) is False


# ---------- adoption : toutes les surfaces passent par le canonique ----------


def test_render_sites_consume_canonical():
    """Source-read : les anciennes définitions parallèles ne ressuscitent pas."""
    src = Path("dashboard/render.py").read_text()
    # 1. le frame thèse du hero est mort
    assert "def _is_losing_row" not in src, (
        "_is_losing_row (frame entrée-THÈSE) a ressuscité — le hero divergera "
        "à nouveau de la table AT STOP"
    )
    # 2. le SQL ad hoc de la bande monitors est mort
    assert "p.last_price_native < t.entry_price" not in src, (
        "le chip near_stop de la bande a retrouvé sa définition SQL privée"
    )
    # 3. les sites consomment le prédicat canonique (≥4 imports/usages)
    assert src.count("is_near_stop") >= 6, (
        f"adoption du prédicat canonique en recul ({src.count('is_near_stop')} "
        "mentions) — un site a probablement réintroduit sa définition inline"
    )
    # 4. plus aucun seuil near-stop inline nu du type `down < 10` sur le chemin
    #    _rows_risque (le seuil vit dans NEAR_STOP_WATCH_PCT)
    assert "is_near = down < 10" not in src
    # 5. la collision de vocabulaire thèses est cassée (concept renommé)
    assert "Stop margin (thesis)" in src


def test_thresholds_are_named_constants():
    """Les seuils vivent dans shared.portfolio_analytics, pas en littéraux épars."""
    assert NEAR_STOP_ALERT_PCT == 5.0
    assert NEAR_STOP_WATCH_PCT == 10.0
