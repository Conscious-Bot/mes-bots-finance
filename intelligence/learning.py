'''PredictionLedger: register et resolve des predictions.

Registration: signaux score>=6 + sentiment clair + tickers -> 1 prediction par ticker.
Resolution: apres target_date, fetch current_price, compare a baseline.
- bullish + ticker >=+5% : correct (cred +0.03)
- bullish + ticker <=-5% : incorrect (cred -0.05)
- sinon : neutral (cred +0)
Asymetrique: down feedback (outcome incorrect) pese 2x plus que correct.
'''
from datetime import UTC, datetime, timedelta

from shared import prices, storage

HORIZON_DAYS = 30
OUTCOME_THRESHOLD = 0.05

OUTCOME_DELTA = {
    'correct': 0.03,
    'incorrect': -0.05,
    'neutral': 0.0,
}

# Phase Solidification P2 — diversification horizon par signal_type
# Rationale: catalyst = event-driven (jours/semaines), narrative = slow-burn (mois),
# opinion/data = standard horizon. Évite cluster temporel de resolutions.
SIGNAL_TYPE_HORIZONS = {
    'catalyst': 14,    # event-driven, short window
    'data': 30,        # macro prints, medium
    'opinion': 30,     # opinion pieces, medium
    'narrative': 60,   # slow-burn themes, long
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


def register_prediction(signal_id, ticker, direction, horizon_days=None, baseline_date=None, signal_type=None, impact_magnitude=None):
    if horizon_days is None:
        horizon_days = horizon_for_signal_type(signal_type, impact_magnitude)
    if direction not in ('bullish', 'bearish'):
        return None
    if baseline_date is None:
        baseline_date = datetime.now(UTC).strftime('%Y-%m-%d')
    actual_date, baseline_price = prices.get_price_on_date(ticker, baseline_date)
    if baseline_price is None:
        print(f"register_prediction: no baseline price for {ticker} @ {baseline_date}")
        return None
    target = (datetime.fromisoformat(actual_date) + timedelta(days=horizon_days)).strftime('%Y-%m-%d')
    return storage.insert_prediction(
        signal_id=signal_id,
        ticker=ticker,
        direction=direction,
        horizon_days=horizon_days,
        baseline_price=baseline_price,
        baseline_date=actual_date,
        target_date=target,
    )


def auto_register_predictions(signals, horizon_days=HORIZON_DAYS):
    '''Iterate processed signals. Register predictions for score>=6 + bullish/bearish.'''
    registered = []
    for sig in signals:
        score = sig.get('score') or 0
        sentiment = sig.get('sentiment') or ''
        if score < 6 or sentiment not in ('bullish', 'bearish'):
            continue
        tickers = sig.get('tickers') or []
        if isinstance(tickers, str):
            try:
                import json
                tickers = json.loads(tickers)
            except Exception:
                tickers = []
        baseline_date = (sig.get('timestamp') or '')[:10] or None
        for tk in tickers[:5]:
            pid = register_prediction(
                signal_id=sig.get('id'),
                ticker=tk,
                direction=sentiment,
                horizon_days=horizon_days if horizon_days != HORIZON_DAYS else None,
                baseline_date=baseline_date,
                signal_type=sig.get('signal_type'),
                impact_magnitude=sig.get('impact_magnitude'),
            )
            if pid:
                registered.append(pid)
    return registered


def resolve_due_predictions(limit=50):
    '''Find predictions past target_date, compute outcomes, update credibility.'''
    due = storage.get_due_predictions(limit=limit)
    if not due:
        return {'resolved': 0, 'details': []}
    results = {'resolved': 0, 'details': []}
    for pred in due:
        ticker = pred['ticker']
        baseline_price = pred['baseline_price']
        direction = pred['direction']
        current_price = prices.get_current_price(ticker)
        if current_price is None:
            continue
        return_pct = (current_price - baseline_price) / baseline_price
        if direction == 'bullish':
            if return_pct >= OUTCOME_THRESHOLD:
                outcome = 'correct'
            elif return_pct <= -OUTCOME_THRESHOLD:
                outcome = 'incorrect'
            else:
                outcome = 'neutral'
        else:
            if return_pct <= -OUTCOME_THRESHOLD:
                outcome = 'correct'
            elif return_pct >= OUTCOME_THRESHOLD:
                outcome = 'incorrect'
            else:
                outcome = 'neutral'
        delta = OUTCOME_DELTA[outcome]
        sig = storage.get_signal(pred['signal_id']) if pred.get('signal_id') else None
        new_cred = None
        if sig and delta != 0:
            new_cred = storage.update_source_credibility(sig['source_id'], delta)
        prob = pred.get('probability_at_creation')
        brier_score = None
        if prob is not None:
            outcome_binary = {'correct': 1.0, 'incorrect': 0.0, 'neutral': 0.5}.get(outcome, 0.5)
            brier_score = (prob - outcome_binary) ** 2
        storage.resolve_prediction_row(
            prediction_id=pred['id'],
            final_price=current_price,
            return_pct=return_pct,
            outcome=outcome,
            credibility_delta=delta,
            brier_score=brier_score,
        )
        results['resolved'] += 1
        results['details'].append({
            'pred_id': pred['id'],
            'ticker': ticker,
            'direction': direction,
            'baseline': baseline_price,
            'final': current_price,
            'return_pct': return_pct,
            'outcome': outcome,
            'delta': delta,
            'source_name': sig.get('source_name') if sig else None,
            'new_cred': new_cred,
        })
    return results


def format_resolve_report(results):
    if results['resolved'] == 0:
        return "Aucune prediction a resoudre (target_date pas encore passe)."
    lines = [f"Resolution: {results['resolved']} predictions"]
    counts = {'correct': 0, 'incorrect': 0, 'neutral': 0}
    for d in results['details']:
        counts[d['outcome']] += 1
        src = (d.get('source_name') or '?')[:20]
        lines.append(
            f"  #{d['pred_id']} {d['ticker']} {d['direction'][:4]} [{src}]: "
            f"${d['baseline']:.2f} -> ${d['final']:.2f} ({d['return_pct']:+.1%}) "
            f"-> {d['outcome'].upper()} (cred {d['delta']:+.2f})"
        )
    lines.append(f"Summary: {counts['correct']} ok / {counts['incorrect']} ko / {counts['neutral']} neutral")
    return "\n".join(lines)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'resolve':
        results = resolve_due_predictions()
        print(format_resolve_report(results))
    else:
        print("Usage: python -m intelligence.learning resolve")
        print("Running resolve anyway...")
        results = resolve_due_predictions()
        print(format_resolve_report(results))
