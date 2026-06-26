"""FX tripwire : detect silent EUR loss from USD depreciation.

Tier 3 #7 wiring (26/06/2026) post red-teams critique :
« Currency exposure non hedgée + non instrumentée. ~30% USD-natif dans le book.
USD -10% sur 12 mois = -3% book silencieux. Pas un trigger, pas un alert,
pas une discipline. »

Build : compute USD/EUR rate move sur fenêtres rollantes (30d / 90d),
estime EUR loss silencieuse sur les positions USD-natives, alert si seuil
franchi.

Math (EUR investor perspective) :
- fx_history.rate (base=USD, quote=EUR) = combien d'EUR pour 1 USD
- Si rate DROP (ex 0.95 → 0.85), USD déprécié → USD assets valent moins en EUR (BAD)
- Si rate RISE, USD apprécié → USD assets valent plus en EUR (GOOD)
- Silent EUR loss = usd_exposure_eur × (-rate_change_pct)

Status :
- info : |rate change| < 3%
- warn : 3-7% (déprécié OU apprécié significatif)
- bad : > 7% (vraie alerte)

NB : on alerte aussi sur appreciation forte parce qu'elle expose à un retournement.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

log = logging.getLogger(__name__)


def _get_fx_rate_on_or_before(conn, target_date_iso: str) -> tuple[float, str] | None:
    """Rate USD/EUR le plus proche <= target_date.

    Returns (rate, actual_asof_date) ou None si fx_history vide.
    Fallback : si target trop ancien (avant 1er enregistrement), retourne le plus ancien.
    """
    row = conn.execute(
        "SELECT rate, asof FROM fx_history "
        "WHERE base='USD' AND quote='EUR' AND asof <= ? "
        "ORDER BY asof DESC LIMIT 1",
        (target_date_iso + "T23:59:59",),
    ).fetchone()
    if row:
        return float(row[0]), str(row[1])
    # Fallback : prend le plus ancien dispo (window plus large que data history)
    row = conn.execute(
        "SELECT rate, asof FROM fx_history "
        "WHERE base='USD' AND quote='EUR' "
        "ORDER BY asof ASC LIMIT 1",
    ).fetchone()
    return (float(row[0]), str(row[1])) if row else None


def _get_usd_exposure_eur(conn) -> tuple[float, int]:
    """Total EUR-value of positions natives USD held."""
    row = conn.execute("""
        SELECT
          COALESCE(SUM(last_price_eur * qty), 0) as exposure_eur,
          COUNT(*) as n_positions
        FROM positions
        WHERE qty > 0 AND last_price_currency = 'USD'
    """).fetchone()
    if not row:
        return 0.0, 0
    return float(row[0] or 0), int(row[1] or 0)


def compute_fx_tripwire(window_days: int = 30) -> dict[str, Any]:
    """Compute USD/EUR move + silent EUR loss estimate sur window_days.

    Returns :
        {
            'ok': bool,
            'window_days': int,
            'rate_start': float | None,       # USD→EUR au début du window
            'rate_end': float | None,         # USD→EUR maintenant
            'rate_change_pct': float | None,  # +/- en %
            'usd_exposure_eur': float,        # EUR-value des positions USD natives
            'n_positions_usd': int,
            'silent_eur_impact': float,       # EUR gagné/perdu sur la fenêtre
            'status': 'info' | 'warn' | 'bad',
            'direction': 'usd_up' | 'usd_down' | 'flat',
            'reason': str,
        }
    """
    from shared import storage

    out: dict[str, Any] = {
        "ok": False,
        "window_days": window_days,
        "rate_start": None,
        "rate_end": None,
        "rate_change_pct": None,
        "usd_exposure_eur": 0.0,
        "n_positions_usd": 0,
        "silent_eur_impact": 0.0,
        "status": "info",
        "direction": "flat",
        "reason": "",
    }

    today = date.today()
    target_start = (today - timedelta(days=window_days)).isoformat()
    target_end = today.isoformat()

    try:
        with storage.db() as conn:
            start_t = _get_fx_rate_on_or_before(conn, target_start)
            end_t = _get_fx_rate_on_or_before(conn, target_end)
            usd_exposure_eur, n_usd = _get_usd_exposure_eur(conn)
    except Exception as e:
        out["reason"] = f"db err: {e}"
        return out

    out["usd_exposure_eur"] = usd_exposure_eur
    out["n_positions_usd"] = n_usd

    if not start_t or not end_t:
        out["reason"] = "fx_history vide"
        return out

    rate_start, start_asof = start_t
    rate_end, end_asof = end_t

    if rate_start <= 0:
        out["reason"] = f"rate_start <= 0 ({rate_start})"
        return out

    # Effective window = days entre start_asof réel et end_asof réel
    effective_days = (date.fromisoformat(end_asof[:10]) - date.fromisoformat(start_asof[:10])).days
    out["effective_days"] = effective_days

    rate_change_pct = (rate_end - rate_start) / rate_start * 100
    out["rate_start"] = rate_start
    out["rate_end"] = rate_end
    out["rate_change_pct"] = rate_change_pct
    out["start_date"] = start_asof[:10]

    # Silent EUR impact : si rate +X%, USD positions valent X% de + en EUR
    silent_eur_impact = usd_exposure_eur * (rate_change_pct / 100)
    out["silent_eur_impact"] = silent_eur_impact

    # Direction
    if rate_change_pct > 0.5:
        out["direction"] = "usd_up"   # USD apprécié → GAIN EUR silencieux
    elif rate_change_pct < -0.5:
        out["direction"] = "usd_down"  # USD déprécié → PERTE EUR silencieuse
    else:
        out["direction"] = "flat"

    # Status (basé sur |move|, pas seulement perte — appreciation forte = volatilité à monitorer)
    abs_move = abs(rate_change_pct)
    if abs_move < 3:
        out["status"] = "info"
    elif abs_move < 7:
        out["status"] = "warn"
    else:
        out["status"] = "bad"

    out["ok"] = True
    out["reason"] = (
        f"USD/EUR {rate_start:.4f} → {rate_end:.4f} = {rate_change_pct:+.2f}% sur {window_days}j "
        f"| {out['direction']} | EUR impact silencieux {silent_eur_impact:+,.0f}€ "
        f"sur {usd_exposure_eur:,.0f}€ USD-expo ({n_usd} pos)"
    )
    return out


def get_fx_tripwire_summary() -> dict[str, Any]:
    """Compute 30d window (et 90d si data dispo)."""
    return {
        "w30": compute_fx_tripwire(30),
        "w90": compute_fx_tripwire(90),
    }
