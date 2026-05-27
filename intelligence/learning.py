"""PredictionLedger: register et resolve des predictions.

Registration: signaux score>=6 + sentiment clair + tickers -> 1 prediction par ticker.
Resolution: apres target_date, fetch current_price, compare a baseline.
- bullish + ticker >=+5% : correct
- bullish + ticker <=-5% : incorrect
- sinon : neutral
credibility_delta (OUTCOME_DELTA) est calcule + stocke sur la ligne pour audit,
mais PLUS applique a sources.credibility (ADR 007: credibilite = autorite unique
Brier via recal mensuel). Voir docs/adrs/007.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from shared import math_helpers, prices, storage

HORIZON_DAYS = 30
OUTCOME_THRESHOLD = 0.05

OUTCOME_DELTA = {
    "correct": 0.03,
    "incorrect": -0.05,
    "neutral": 0.0,
}

# Phase Solidification P2 — diversification horizon par signal_type
# Rationale: catalyst = event-driven (jours/semaines), narrative = slow-burn (mois),
# opinion/data = standard horizon. Évite cluster temporel de resolutions.
SIGNAL_TYPE_HORIZONS = {
    "catalyst": 14,  # event-driven, short window
    "data": 30,  # macro prints, medium
    "opinion": 30,  # opinion pieces, medium
    "narrative": 60,  # slow-burn themes, long
}


def horizon_for_signal_type(signal_type, impact_magnitude=None):
    """Map signal_type + impact_magnitude to default horizon (days).

    High impact (≥4) narrows the window for faster decisive resolution.
    Returns HORIZON_DAYS (30) as fallback for unknown signal_type.

    Invariants:
    - Output >= 7 (minimum useful horizon)
    - catalyst always shorter than narrative
    - impact_magnitude can only narrow, never extend
    """
    base = SIGNAL_TYPE_HORIZONS.get(signal_type, HORIZON_DAYS)
    if impact_magnitude is not None and impact_magnitude >= 4 and base >= 14:
        return max(7, base // 2)
    return base


CRYPTO_DENY = {
    "BTC", "ETH", "LINK", "SOL", "ADA", "XRP", "DOGE", "AVAX", "DOT", "MATIC",
    "LTC", "BCH", "TRX", "TON", "NEAR", "ATOM", "UNI", "AAVE", "ARB", "OP",
    "SUI", "APT", "INJ", "SEI", "FIL", "ICP", "ETC", "XLM", "ALGO", "BNB",
    "SHIB", "PEPE", "USDT", "USDC", "DAI",
}  # stock-only: symboles crypto bruts bloques a la creation (26/05/2026)


def register_prediction(
    signal_id: int, ticker: str, direction: str, horizon_days: int | None = None,
    baseline_date: str | None = None, signal_type: str | None = None,
    impact_magnitude: float | None = None, score: int | None = None,
) -> int | None:
    if horizon_days is None:
        horizon_days = horizon_for_signal_type(signal_type, impact_magnitude)
    if direction not in ("bullish", "bearish"):
        return None
    if baseline_date is None:
        baseline_date = datetime.now(UTC).strftime("%Y-%m-%d")
    actual_date, baseline_price = prices.get_price_on_date(ticker, baseline_date)
    if baseline_price is None or actual_date is None:
        print(f"register_prediction: no baseline price for {ticker} @ {baseline_date}")
        return None
    target = (datetime.fromisoformat(actual_date) + timedelta(days=horizon_days)).strftime("%Y-%m-%d")
    return cast(int | None, storage.insert_prediction(
        signal_id=signal_id,
        ticker=ticker,
        direction=direction,
        horizon_days=horizon_days,
        baseline_price=baseline_price,
        baseline_date=actual_date,
        target_date=target,
        score=score,
        signal_type=signal_type,
        impact_magnitude=impact_magnitude,
    ))


def auto_register_predictions(signals: list[dict[str, Any]], horizon_days: int = HORIZON_DAYS) -> list[int]:
    """Iterate processed signals. Register predictions for score>=6 + bullish/bearish."""
    registered = []
    for sig in signals:
        score = sig.get("score") or 0
        sentiment = sig.get("sentiment") or ""
        if score < 6 or sentiment not in ("bullish", "bearish"):
            continue
        tickers = sig.get("tickers") or []
        if isinstance(tickers, str):
            try:
                import json

                tickers = json.loads(tickers)
            except Exception:
                tickers = []
        baseline_date = (sig.get("timestamp") or "")[:10] or None
        sig_id = sig.get("id")
        if sig_id is None:
            continue
        for tk in tickers[:5]:
            if tk.upper() in CRYPTO_DENY:
                continue

            pid = register_prediction(
                signal_id=sig_id,
                ticker=tk,
                direction=sentiment,
                horizon_days=horizon_days if horizon_days != HORIZON_DAYS else None,
                baseline_date=baseline_date,
                signal_type=sig.get("signal_type"),
                impact_magnitude=sig.get("impact_magnitude"),
                score=score,
            )
            if pid:
                registered.append(pid)
    return registered


def resolve_due_predictions(limit: int = 50) -> dict[str, Any]:
    """Find predictions past target_date, compute outcomes, update credibility."""
    due = storage.get_due_predictions(limit=limit)
    if not due:
        return {"resolved": 0, "details": []}
    results: dict[str, Any] = {"resolved": 0, "details": []}
    for pred in due:
        ticker = pred["ticker"]
        baseline_price = pred["baseline_price"]
        direction = pred["direction"]
        # Native-currency CORRECT here (not legacy).
        # This computes a RATIO (return_pct) which is FX-invariant — as long as
        # current_price and baseline_price are in same currency, the ratio holds.
        # baseline_price was set at prediction creation via same get_current_price
        # native path, so both sides match. Migrating to USD/EUR adds FX layer for
        # no math gain and breaks the symmetry. DO NOT migrate.
        current_price = prices.get_current_price(ticker)
        if current_price is None or current_price != current_price:  # None ou NaN (NaN != NaN)
            continue
        return_pct = (current_price - baseline_price) / baseline_price
        if direction == "bullish":
            if return_pct >= OUTCOME_THRESHOLD:
                outcome = "correct"
            elif return_pct <= -OUTCOME_THRESHOLD:
                outcome = "incorrect"
            else:
                outcome = "neutral"
        else:
            if return_pct <= -OUTCOME_THRESHOLD:
                outcome = "correct"
            elif return_pct >= OUTCOME_THRESHOLD:
                outcome = "incorrect"
            else:
                outcome = "neutral"
        delta = OUTCOME_DELTA[outcome]
        sig = storage.get_signal(pred["signal_id"]) if pred.get("signal_id") else None
        # ADR 007: credibilite = autorite unique Brier (recal mensuel). On n'applique
        # plus le delta categoriel incremental; delta reste calcule + stocke (audit).
        new_cred = None
        prob = pred.get("probability_at_creation")
        brier_score = math_helpers.brier_for(prob, outcome)
        storage.resolve_prediction_row(
            prediction_id=pred["id"],
            final_price=current_price,
            return_pct=return_pct,
            outcome=outcome,
            credibility_delta=delta,
            brier_score=brier_score,
        )
        results["resolved"] += 1
        results["details"].append(
            {
                "pred_id": pred["id"],
                "ticker": ticker,
                "direction": direction,
                "baseline": baseline_price,
                "final": current_price,
                "return_pct": return_pct,
                "outcome": outcome,
                "delta": delta,
                "source_name": sig.get("source_name") if sig else None,
                "new_cred": new_cred,
            }
        )
    return results


def format_resolve_report(results: dict[str, Any]) -> str:
    if results["resolved"] == 0:
        return "Aucune prediction a resoudre (target_date pas encore passe)."
    lines = [f"Resolution: {results['resolved']} predictions"]
    counts = {"correct": 0, "incorrect": 0, "neutral": 0}
    for d in results["details"]:
        counts[d["outcome"]] += 1
        src = (d.get("source_name") or "?")[:20]
        lines.append(
            f"  #{d['pred_id']} {d['ticker']} {d['direction'][:4]} [{src}]: "
            f"${d['baseline']:.2f} -> ${d['final']:.2f} ({d['return_pct']:+.1%}) "
            f"-> {d['outcome'].upper()} (cred {d['delta']:+.2f})"
        )
    lines.append(f"Summary: {counts['correct']} ok / {counts['incorrect']} ko / {counts['neutral']} neutral")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "resolve":
        results = resolve_due_predictions()
        print(format_resolve_report(results))
    else:
        print("Usage: python -m intelligence.learning resolve")
        print("Running resolve anyway...")
        results = resolve_due_predictions()
        print(format_resolve_report(results))
