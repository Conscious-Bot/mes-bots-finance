"""Portfolio circuit breaker Elder rule (-6%/mois).

Doctrine 06/06 v5 audit pro : si portfolio DD > 6% sur 30j glissant,
gate les nouvelles positions. Convention pro Elder : "stop trading
si -6% mois", soit la regle de calibration pro #1 pour portfolio risk.

Wire :
 - cron daily check_circuit_breaker() : compute DD 30j vs threshold,
   stocke state {active, dd_pct, breach_date} dans circuit_state.
 - bot/handlers/trade_context : pre-trade check si circuit active.
"""

from __future__ import annotations

import logging

from shared import storage

log = logging.getLogger(__name__)


# In-memory state pour cooldown (TTL 24h default).
# Persistance optionnelle : Phase B audit refresh peut ajouter table.
_STATE: dict = {
    "active": False,
    "dd_pct": 0.0,
    "high_date": None,
    "low_date": None,
    "breach_date": None,
}


def compute_dd_30j() -> dict:
    """Compute portfolio DD glissant 30j depuis portfolio_snapshots.

    Returns {dd_pct, high_value, high_date, current_value, current_date}.
    """
    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT snapshot_date, total_value_eur "
                "FROM portfolio_snapshots "
                "WHERE snapshot_date > date('now', '-30 day') "
                "ORDER BY snapshot_date ASC"
            ).fetchall()
    except Exception as e:
        log.warning(f"compute_dd_30j read: {e}")
        return {"dd_pct": 0.0, "high_value": 0.0, "high_date": None,
                "current_value": 0.0, "current_date": None}

    if len(rows) < 2:
        return {"dd_pct": 0.0, "high_value": 0.0, "high_date": None,
                "current_value": 0.0, "current_date": None}

    high_value = 0.0
    high_date = None
    for date_str, val in rows:
        v = float(val or 0)
        if v > high_value:
            high_value = v
            high_date = date_str

    current_date, current_val = rows[-1]
    current_value = float(current_val or 0)
    if high_value <= 0:
        dd_pct = 0.0
    else:
        dd_pct = (current_value - high_value) / high_value * 100

    return {
        "dd_pct": dd_pct,
        "high_value": high_value,
        "high_date": high_date,
        "current_value": current_value,
        "current_date": current_date,
    }


def check_circuit_breaker() -> dict:
    """Run check. Update _STATE. Returns state."""
    try:
        from shared.calibration import get_drawdown_thresholds
        threshold_pct = float(
            get_drawdown_thresholds().get("portfolio_monthly_dd_circuit_breaker_pct") or 6.0
        )
    except Exception:
        threshold_pct = 6.0

    dd = compute_dd_30j()
    dd_pct = dd["dd_pct"]
    # dd_pct est négatif si en perte ; on compare la magnitude
    breach = dd_pct <= -threshold_pct
    _STATE["active"] = breach
    _STATE["dd_pct"] = dd_pct
    _STATE["high_date"] = dd["high_date"]
    _STATE["high_value"] = dd["high_value"]
    _STATE["current_date"] = dd["current_date"]
    _STATE["current_value"] = dd["current_value"]
    _STATE["threshold_pct"] = threshold_pct
    if breach and _STATE.get("breach_date") is None:
        _STATE["breach_date"] = dd["current_date"]
    elif not breach:
        _STATE["breach_date"] = None
    log.info(
        f"circuit_breaker dd={dd_pct:+.2f}% vs threshold {-threshold_pct:.1f}% -> "
        f"active={breach}"
    )
    return dict(_STATE)


def is_active() -> bool:
    """Pour pre-trade context : circuit breaker actif ?"""
    return bool(_STATE.get("active"))


def state() -> dict:
    """Lecture etat courant."""
    return dict(_STATE)


def cron_circuit_breaker_daily() -> None:
    """APScheduler entry : daily check. Si transition inactive->active,
    Telegram alert."""
    log.info("cron_circuit_breaker_daily starting")
    try:
        was_active = is_active()
        new_state = check_circuit_breaker()
        if new_state["active"] and not was_active:
            # Transition active : alert Telegram
            try:
                from shared import notify
                notify.send_text(
                    f"⚠️ *Circuit breaker ACTIVE* — portfolio DD "
                    f"{new_state['dd_pct']:+.2f}% sur 30j "
                    f"(seuil Elder rule {-new_state['threshold_pct']:.1f}%).\n\n"
                    f"High {new_state['high_date']} : "
                    f"{new_state['high_value']:,.0f} €\n"
                    f"Current {new_state['current_date']} : "
                    f"{new_state['current_value']:,.0f} €\n\n"
                    f"Nouvelles positions /trade buy GATED jusqu'à recovery "
                    f"(< {-new_state['threshold_pct']:.1f}% sur 30j)."
                )
            except Exception as e:
                log.warning(f"circuit_breaker telegram alert failed: {e}")
        elif not new_state["active"] and was_active:
            try:
                from shared import notify
                notify.send_text(
                    f"✓ Circuit breaker LIFTED — portfolio DD "
                    f"{new_state['dd_pct']:+.2f}% sur 30j sous seuil.\n"
                    f"/trade buy de nouveau autorisé."
                )
            except Exception as e:
                log.warning(f"circuit_breaker telegram lift failed: {e}")
    except Exception as e:
        log.exception(f"cron_circuit_breaker_daily crashed: {e}")
