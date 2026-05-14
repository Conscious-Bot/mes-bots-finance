# yfinance returns None / garbage on known tickers

## Symptoms

- `shared/prices.get_price()` returns `None` for tickers known to trade today (NVDA, MSFT, etc.)
- `_close_at_or_after()` in `intelligence/insider_buy_cluster.py` consistently returns 0 or None
- `/brief` morning section shows "—" or "N/A" for prices on liquid names
- Cron `update_thesis_prices` (if/when added) logs `KeyError` on Close column
- BuyClusterSource persists clusters with `_price_at_detection=None`

## Triage (5 min)

1. Test direct yfinance call:
```bash
   python -c "
   import yfinance as yf
   t = yf.Ticker('NVDA')
   h = t.history(period='5d')
   print(h.tail(3))
   "
```
2. Check yfinance version vs known-good:
```bash
   python -c "import yfinance; print(yfinance.__version__)"
```
   Known-good baseline: pinned via `requirements.txt` (yfinance>=0.2.40).
3. Common root causes:
   - Yahoo Finance API breaking change (yfinance unofficial scrapes)
   - User-Agent / rate limit triggered (Yahoo started blocking)
   - DNS / network from this machine

## Recovery

### Library breaking change
1. Check yfinance GitHub issues: https://github.com/ranaroussi/yfinance/issues
2. If hotfix available, upgrade:
```bash
   pip install -U yfinance
   pip freeze | grep yfinance >> requirements.txt
```
3. Restart bot. Re-test.

### Yahoo blocking this machine
1. Wait 1h (transient blocks usually clear)
2. If persists: change user-agent in `shared/prices.py` (yfinance lets you pass a custom session)
3. As last resort: switch to alternative source (FMP API was on roadmap)

### Stale Pandas / numpy
Sometimes yfinance fails on column index mismatches after dep updates:
```bash
pip install -U pandas numpy
```

## Prevention hooks

- Pin yfinance version exactly in requirements.txt (currently `>=0.2.40` — too loose)
- Add canary test in smoke tests: `yf.Ticker('NVDA').history(period='1d')` returns non-empty
- Cache prices in `data/prices_cache.json` daily so price queries gracefully degrade
- Consider FMP API as fallback (paid $14/mo, was on month 4-6 plan)

## References

- `shared/prices.py` — yfinance wrapper
- `intelligence/insider_buy_cluster.py:_close_at_or_after` — main caller
