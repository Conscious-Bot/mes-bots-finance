'''Price data wrapper. Thin abstraction over yfinance so we can swap
in Polygon/Tiingo later without touching downstream code.

Returns None on failures - downstream must handle gracefully.
'''
import logging as _logging
from datetime import datetime, timedelta

_logging.getLogger('yfinance').setLevel(_logging.CRITICAL)
# Also suppress yfinance's print() to stdout for missing tickers
import contextlib

import yfinance.utils as _yfu

with contextlib.suppress(Exception):
    _yfu.get_yf_logger().setLevel(_logging.CRITICAL)

import yfinance as yf


def get_current_price(ticker):
    '''Latest close price. Returns float or None.'''
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='5d', interval='1d')
        if hist.empty:
            return None
        return float(hist['Close'].iloc[-1])
    except Exception as e:
        print(f"price fetch error for {ticker}: {e}")
        return None


def get_price_on_date(ticker, date):
    '''Close price on or after `date` (str YYYY-MM-DD or datetime).
    Falls back to next trading day. Returns (actual_date_str, price) or (None, None).
    '''
    if isinstance(date, datetime):
        date_str = date.strftime('%Y-%m-%d')
        target = date
    else:
        date_str = str(date)[:10]
        try:
            target = datetime.fromisoformat(date_str)
        except Exception:
            return (None, None)

    end = (target + timedelta(days=10)).strftime('%Y-%m-%d')
    try:
        t = yf.Ticker(ticker)
        hist = t.history(start=date_str, end=end, interval='1d')
        if hist.empty:
            return (None, None)
        first = hist.iloc[0]
        actual = first.name.strftime('%Y-%m-%d')
        return (actual, float(first['Close']))
    except Exception as e:
        print(f"price fetch error for {ticker} @ {date_str}: {e}")
        return (None, None)


def get_returns(ticker, baseline_date, current_date=None):
    '''Return between baseline_date and current_date (default now).'''
    b_actual, b_price = get_price_on_date(ticker, baseline_date)
    if b_price is None:
        return {'error': f'no baseline price for {ticker} @ {baseline_date}'}
    if current_date is None:
        c_price = get_current_price(ticker)
        c_actual = datetime.now().strftime('%Y-%m-%d')
    else:
        c_actual, c_price = get_price_on_date(ticker, current_date)
    if c_price is None:
        return {'error': f'no current price for {ticker}'}
    return {
        'ticker': ticker,
        'baseline_date': b_actual,
        'baseline_price': b_price,
        'current_date': c_actual,
        'current_price': c_price,
        'return_pct': (c_price - b_price) / b_price,
    }


if __name__ == '__main__':
    print('Test get_current_price(NVDA):')
    p = get_current_price('NVDA')
    print(f'  current = ${p:.2f}' if p else '  FAILED')

    print('Test get_price_on_date(NVDA, 2026-04-11):')
    d, p = get_price_on_date('NVDA', '2026-04-11')
    print(f'  {d} = ${p:.2f}' if p else '  FAILED')

    print('Test get_returns(NVDA, 2026-02-11):')
    r = get_returns('NVDA', '2026-02-11')
    if 'error' in r:
        print(f"  ERROR: {r['error']}")
    else:
        print(f"  {r['ticker']}: {r['baseline_date']} ${r['baseline_price']:.2f} -> {r['current_date']} ${r['current_price']:.2f} = {r['return_pct']:+.1%}")


def get_price_window(ticker, start_date, end_date):
    """Phase A4 — Daily closes between start and end (inclusive).
    Returns list of (date_str_YYYYMMDD, close_float). Empty list on failure.
    """
    if isinstance(start_date, datetime):
        start_str = start_date.strftime('%Y-%m-%d')
    else:
        start_str = str(start_date)[:10]
    if isinstance(end_date, datetime):
        end_str = end_date.strftime('%Y-%m-%d')
    else:
        end_str = str(end_date)[:10]
    try:
        t = yf.Ticker(ticker)
        hist = t.history(start=start_str, end=end_str, interval='1d')
        if hist.empty:
            return []
        return [(d.strftime('%Y-%m-%d'), float(c)) for d, c in hist['Close'].items()]
    except Exception as e:
        print(f"price window error for {ticker}: {e}")
        return []
