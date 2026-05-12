"""Phase C13 — Asymmetry-First Scoring.

Counter to "vend trop tôt winners" behavioral biais. For each active thesis +
position, compute asymmetry ratio = upside_to_target / |downside_to_stop| at
current price. Surface verdicts ranging STRONG RUN to FLIPPED.

Integrates with existing theses + positions tables. No new schema.
"""
import logging
log = logging.getLogger(__name__)


def _get_current_price(ticker):
    """Best-effort latest close via yfinance."""
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period='5d')
        if not h.empty:
            return float(h['Close'].iloc[-1])
    except Exception as e:
        log.warning(f"price fetch {ticker}: {e}")
    return None


def compute_thesis_asymmetry(thesis):
    """Compute asymmetry for a thesis dict. Returns dict with ratio + verdict + breakdown."""
    if not thesis:
        return None
    ticker = thesis.get('ticker')
    entry = thesis.get('entry_price')
    target_full = thesis.get('target_full') or thesis.get('target_price')
    target_partial = thesis.get('target_partial')
    stop = thesis.get('stop_price')
    direction = thesis.get('direction', 'long')

    current = _get_current_price(ticker)
    if current is None:
        return {'ticker': ticker, 'error': 'price fetch failed'}

    # Long-direction asymmetry
    if direction != 'long':
        return {'ticker': ticker, 'note': f'asymmetry not computed for direction={direction}',
                'current_price': current}
    if not (entry and target_full and stop):
        return {'ticker': ticker, 'note': 'incomplete thesis (need entry+target_full+stop)',
                'current_price': current, 'entry': entry, 'target_full': target_full, 'stop': stop}

    # Edge cases
    if current <= stop:
        return {
            'ticker': ticker, 'current_price': current, 'entry': entry,
            'target_full': target_full, 'target_partial': target_partial, 'stop': stop,
            'asymmetry_ratio': 0.0, 'verdict': 'STOP_BREACHED',
            'note': f'current ${current:.2f} ≤ stop ${stop:.2f}',
            'upside_pct': (target_full - current) / current * 100,
            'downside_pct': 0.0,
        }
    if current >= target_full:
        return {
            'ticker': ticker, 'current_price': current, 'entry': entry,
            'target_full': target_full, 'target_partial': target_partial, 'stop': stop,
            'asymmetry_ratio': 999.0, 'verdict': 'TARGET_HIT',
            'note': f'current ${current:.2f} ≥ target ${target_full:.2f}',
            'upside_pct': 0.0,
            'downside_pct': (current - stop) / current * 100,
        }

    upside_pct = (target_full - current) / current * 100
    downside_pct = (current - stop) / current * 100
    if downside_pct <= 0.001:
        return {'ticker': ticker, 'error': 'degenerate (downside ~0)', 'current_price': current}

    ratio = upside_pct / downside_pct

    if ratio > 3.0:
        verdict = 'STRONG_RUN'
    elif ratio > 1.5:
        verdict = 'FAVORABLE'
    elif ratio > 0.7:
        verdict = 'BALANCED'
    elif ratio > 0.3:
        verdict = 'UNFAVORABLE'
    else:
        verdict = 'FLIPPED'

    return {
        'ticker': ticker,
        'current_price': current,
        'entry': entry,
        'target_full': target_full,
        'target_partial': target_partial,
        'stop': stop,
        'asymmetry_ratio': ratio,
        'verdict': verdict,
        'upside_pct': upside_pct,
        'downside_pct': downside_pct,
    }


def compute_portfolio_asymmetry():
    """Aggregate asymmetry across all active theses. Returns list of dicts sorted by ratio."""
    from shared import storage
    results = []
    try:
        # Get all active theses
        import sqlite3
        conn = sqlite3.connect(storage._DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM theses WHERE status='active'").fetchall()
        theses = [dict(r) for r in rows]
        conn.close()
    except Exception as e:
        log.warning(f"compute_portfolio_asymmetry fetch failed: {e}")
        return []

    for t in theses:
        r = compute_thesis_asymmetry(t)
        if r:
            r['thesis_id'] = t.get('id')
            results.append(r)
    return sorted(results, key=lambda x: -(x.get('asymmetry_ratio') or 0))


def format_asymmetry_single(r):
    """Single-thesis asymmetry display."""
    if not r:
        return "No data"
    if 'error' in r:
        return f"{r.get('ticker','?')}: ERROR {r['error']}"
    if 'note' in r and 'asymmetry_ratio' not in r:
        return f"{r.get('ticker','?')} @ ${r.get('current_price', 0):.2f} — {r['note']}"

    verdict_icon = {
        'STRONG_RUN': '🟢🟢',
        'FAVORABLE': '🟢',
        'BALANCED': '🟡',
        'UNFAVORABLE': '🟠',
        'FLIPPED': '🔴',
        'STOP_BREACHED': '⛔',
        'TARGET_HIT': '🎯',
    }.get(r.get('verdict'), '?')

    lines = [f"{verdict_icon} {r['ticker']} — Asymmetry"]
    lines.append(f"Current: ${r['current_price']:.2f}  |  Entry: ${r['entry']:.2f}  |  Stop: ${r['stop']:.2f}  |  Target: ${r['target_full']:.2f}")
    lines.append(f"Upside to target:  +{r.get('upside_pct', 0):.1f}%")
    lines.append(f"Downside to stop: -{r.get('downside_pct', 0):.1f}%")
    ratio = r.get('asymmetry_ratio')
    if ratio is not None:
        if ratio >= 999:
            lines.append(f"Ratio: TARGET HIT")
        else:
            lines.append(f"Ratio: {ratio:.2f}  →  {r['verdict']}")
    if r.get('note'):
        lines.append(f"Note: {r['note']}")
    return "\n".join(lines)


def format_portfolio_asymmetry(results):
    """Portfolio-wide ranked display."""
    if not results:
        return "No active theses with complete entry/target/stop data."
    lines = [f"PORTFOLIO ASYMMETRY ({len(results)} active theses)"]
    lines.append("Ranked by upside/downside ratio (best first):\n")
    for r in results:
        if 'error' in r or 'asymmetry_ratio' not in r:
            continue
        verdict_icon = {
            'STRONG_RUN': '🟢🟢', 'FAVORABLE': '🟢', 'BALANCED': '🟡',
            'UNFAVORABLE': '🟠', 'FLIPPED': '🔴',
            'STOP_BREACHED': '⛔', 'TARGET_HIT': '🎯',
        }.get(r.get('verdict'), '?')
        ratio = r['asymmetry_ratio']
        ratio_str = "TARGET" if ratio >= 999 else f"{ratio:.2f}x"
        lines.append(
            f"{verdict_icon} {r['ticker']:6s} ratio={ratio_str:>7s}  "
            f"up=+{r.get('upside_pct',0):.0f}%  down=-{r.get('downside_pct',0):.0f}%  → {r['verdict']}"
        )
    return "\n".join(lines)
