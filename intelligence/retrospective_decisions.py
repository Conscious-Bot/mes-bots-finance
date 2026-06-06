"""Cron retrospective decisions +30j/+90j.

Pour chaque row de position_decisions_context >= horizon jours :
- Fetch price current du ticker
- Compute outcome_pct (return depuis decision)
- Compute pnl_pct signe selon action (buy: +outcome / sell: -outcome)
- Determine verdict :
    aligned_positive  : decision alignee systeme + outcome positif
    aligned_negative  : alignee + outcome negatif (signal failed)
    against_positive  : contre systeme + outcome positif (gut beat signal)
    against_negative  : contre + outcome negatif (systeme avait raison)
    neutral           : |outcome| < 3% (insignifiant)

Logique "alignee/contre" :
 - Si decision avait warnings macro actifs (R1/R2/R4) ou bias warnings :
   ces signaux disaient "ne fais pas" -> decision "contre systeme"
 - Sinon : "alignee systeme" (pas de signal contre)

Doctrine : nourrir bias_ledger en donnees per-decision RESOLUES, pas
juste aggregees. Chaque trade contribue un row contextuel observable.
"""

from __future__ import annotations

import json
import logging

from shared import storage

log = logging.getLogger(__name__)


_NEUTRAL_THRESHOLD_PCT = 3.0  # |outcome| < 3% = neutral


def _fetch_current_price_eur(ticker: str) -> float | None:
    """Lit le prix EUR courant via cache _cached_price_eur."""
    try:
        from shared.prices import get_current_price_in_eur
        return get_current_price_in_eur(ticker)
    except Exception as e:
        log.warning(f"retrospective fetch price {ticker}: {e}")
        return None


def _classify_verdict(
    outcome_pct: float,
    pnl_pct: float,
    regime_warnings_json: str,
    bias_warnings_json: str,
) -> str:
    """Returns 'aligned_positive' / 'aligned_negative' / 'against_positive' /
    'against_negative' / 'neutral'.
    """
    if abs(outcome_pct) < _NEUTRAL_THRESHOLD_PCT:
        return "neutral"
    # Count signaux "contre" au moment decision
    try:
        rw = json.loads(regime_warnings_json) if regime_warnings_json else []
    except (json.JSONDecodeError, TypeError):
        rw = []
    try:
        bw = json.loads(bias_warnings_json) if bias_warnings_json else []
    except (json.JSONDecodeError, TypeError):
        bw = []
    against_system = bool(rw) or bool(bw)
    positive_outcome = pnl_pct > 0
    if against_system:
        return "against_positive" if positive_outcome else "against_negative"
    return "aligned_positive" if positive_outcome else "aligned_negative"


def process_horizon(horizon_days: int) -> dict:
    """Processe les decisions >= horizon jours. Returns counts."""
    pending = storage.list_pending_retrospectives(horizon_days)
    if not pending:
        return {"processed": 0, "horizon": horizon_days, "skipped_no_price": 0}

    processed = 0
    skipped = 0
    for row in pending:
        ctx = storage.get_decision_context(row["id"])
        if not ctx:
            continue
        ticker = ctx["ticker"]
        decision_price = float(ctx["price"])
        action = ctx["action"]
        current_price = _fetch_current_price_eur(ticker)
        if current_price is None or current_price <= 0:
            skipped += 1
            continue
        outcome_pct = (current_price - decision_price) / decision_price * 100.0
        # PnL signed : buy benefit = outcome positif, sell benefit = outcome negatif
        pnl_pct = outcome_pct if action == "buy" else -outcome_pct
        verdict = _classify_verdict(
            outcome_pct=outcome_pct,
            pnl_pct=pnl_pct,
            regime_warnings_json=ctx.get("regime_warnings_json") or "",
            bias_warnings_json=ctx.get("bias_warnings_json") or "",
        )
        ok = storage.update_retrospective(
            context_id=row["id"],
            horizon_days=horizon_days,
            outcome_pct=outcome_pct,
            pnl_pct=pnl_pct,
            verdict=verdict,
        )
        if ok:
            processed += 1
        log.info(
            f"retrospective_{horizon_days}d id={row['id']} {action} {ticker} "
            f"price {decision_price:.2f}->{current_price:.2f} "
            f"outcome={outcome_pct:+.1f}% pnl={pnl_pct:+.1f}% verdict={verdict}"
        )
    return {
        "processed": processed,
        "horizon": horizon_days,
        "skipped_no_price": skipped,
        "total_pending": len(pending),
    }


def cron_retrospective_daily() -> None:
    """APScheduler entry : daily 09:30 (apres market open). Processe +30j et +90j."""
    log.info("cron_retrospective_daily starting")
    try:
        r30 = process_horizon(30)
        r90 = process_horizon(90)
        log.info(
            f"cron_retrospective_daily complete: +30j {r30['processed']}/{r30.get('total_pending', 0)}, "
            f"+90j {r90['processed']}/{r90.get('total_pending', 0)}"
        )
    except Exception as e:
        log.exception(f"cron_retrospective_daily crashed: {e}")


def summary_by_verdict(horizon_days: int = 30) -> dict[str, int]:
    """Aggregate counts par verdict pour bias_ledger feed."""
    try:
        col = f"retrospective_{horizon_days}d_verdict"
        with storage.db() as cx:
            rows = cx.execute(
                f"SELECT {col} AS v, COUNT(*) AS n "
                f"FROM position_decisions_context "
                f"WHERE {col} IS NOT NULL "
                f"GROUP BY {col}"
            ).fetchall()
            return {row[0]: int(row[1]) for row in rows}
    except Exception as e:
        log.warning(f"summary_by_verdict failed: {e}")
        return {}
