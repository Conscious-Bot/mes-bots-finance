"""
Crypto cycle indicators — free APIs, no key required.
Sources : Binance public API + yfinance.
Mission : détecter cycle tops pour mitigate 'hold crypto too long' bias.

Indicators :
  - BTC + ETH perp funding rates (Binance)
  - BTC open interest ratio vs 14d avg (Binance)
  - BTC Mayer Multiple = price / 200d MA (yfinance)
"""
import json
import logging
import urllib.request

log = logging.getLogger(__name__)

BINANCE_FAPI = "https://fapi.binance.com"


def get_funding_rate(symbol: str = "BTCUSDT") -> dict | None:
    """Latest perpetual funding rate from Binance."""
    try:
        url = f"{BINANCE_FAPI}/fapi/v1/premiumIndex?symbol={symbol}"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        rate_8h = float(data.get('lastFundingRate', 0))
        annualized = rate_8h * 3 * 365  # 3 fundings/day × 365
        if rate_8h >= 0.0005:        # >0.05% per 8h ≈ >55% annualized
            zone = 'top-zone'
        elif rate_8h >= 0.0003:      # >0.03% per 8h ≈ >33% annualized
            zone = 'elevated'
        elif rate_8h < 0:
            zone = 'negative'
        else:
            zone = 'normal'
        return {
            'symbol': symbol,
            'rate_8h': rate_8h,
            'rate_annualized': annualized,
            'zone': zone,
        }
    except Exception as e:
        log.warning(f"get_funding_rate {symbol}: {e}")
        return None


def get_open_interest_ratio(symbol: str = "BTCUSDT", days: int = 14) -> dict | None:
    """OI current vs N-day avg. >1.5 = top-zone, >1.2 = elevated."""
    try:
        url = f"{BINANCE_FAPI}/futures/data/openInterestHist?symbol={symbol}&period=1d&limit={days}"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        if not data or not isinstance(data, list):
            return None
        oi = [float(d.get('sumOpenInterestValue', 0)) for d in data]
        if not oi:
            return None
        current = oi[-1]
        avg = sum(oi[:-1]) / max(len(oi) - 1, 1)
        ratio = current / avg if avg > 0 else 1.0
        if ratio > 1.5:
            zone = 'top-zone'
        elif ratio > 1.2:
            zone = 'elevated'
        elif ratio < 0.7:
            zone = 'low'
        else:
            zone = 'normal'
        return {
            'symbol': symbol,
            'current_usd': current,
            'avg_usd': avg,
            'ratio': ratio,
            'zone': zone,
        }
    except Exception as e:
        log.warning(f"get_open_interest_ratio {symbol}: {e}")
        return None


def get_mayer_multiple() -> dict | None:
    """BTC price / 200d MA. Historically >2.4 = top, <0.8 = capitulation."""
    try:
        import yfinance as yf
        hist = yf.Ticker('BTC-USD').history(period='1y', interval='1d')
        if hist.empty or len(hist) < 200:
            return None
        close = hist['Close']
        ma200 = float(close.tail(200).mean())
        current = float(close.iloc[-1])
        mm = current / ma200 if ma200 > 0 else 1.0
        if mm > 2.4:
            zone = 'top-zone'
        elif mm > 1.7:
            zone = 'elevated'
        elif mm < 0.8:
            zone = 'capitulation'
        elif mm < 1.0:
            zone = 'low'
        else:
            zone = 'normal'
        return {
            'btc_price': current,
            'ma200': ma200,
            'mayer_multiple': mm,
            'zone': zone,
        }
    except Exception as e:
        log.warning(f"get_mayer_multiple: {e}")
        return None


def compute_crypto_zone() -> dict:
    """Aggregate all indicators into TOP/NEUTRAL/BOTTOM classification."""
    funding_btc = get_funding_rate('BTCUSDT')
    funding_eth = get_funding_rate('ETHUSDT')
    oi_btc = get_open_interest_ratio('BTCUSDT')
    mayer = get_mayer_multiple()

    indicators = []
    top_count = 0
    bottom_count = 0

    for name, ind in [('BTC funding', funding_btc), ('ETH funding', funding_eth)]:
        if not ind:
            continue
        indicators.append({
            'name': name,
            'value': f"{ind['rate_annualized']*100:+.1f}% ann. ({ind['rate_8h']*100:+.4f}%/8h)",
            'zone': ind['zone'],
        })
        if ind['zone'] == 'top-zone':
            top_count += 1
        elif ind['zone'] == 'negative':
            bottom_count += 1

    if oi_btc:
        indicators.append({
            'name': 'BTC OI vs 14d avg',
            'value': f"{oi_btc['ratio']:.2f}x (${oi_btc['current_usd']/1e9:.1f}B vs ${oi_btc['avg_usd']/1e9:.1f}B)",
            'zone': oi_btc['zone'],
        })
        if oi_btc['zone'] == 'top-zone':
            top_count += 1
        elif oi_btc['zone'] == 'low':
            bottom_count += 1

    if mayer:
        indicators.append({
            'name': 'BTC Mayer Multiple',
            'value': f"{mayer['mayer_multiple']:.2f} (${mayer['btc_price']:.0f} / MA200 ${mayer['ma200']:.0f})",
            'zone': mayer['zone'],
        })
        if mayer['zone'] == 'top-zone':
            top_count += 1
        elif mayer['zone'] in ('capitulation', 'low'):
            bottom_count += 1

    total = len(indicators)
    if total == 0:
        zone = 'unknown'
    elif top_count >= 3 or (top_count >= 2 and total <= 3):
        zone = 'TOP-ZONE'
    elif top_count >= 2:
        zone = 'ELEVATED'
    elif bottom_count >= 3 or (bottom_count >= 2 and total <= 3):
        zone = 'BOTTOM-ZONE'
    elif bottom_count >= 2:
        zone = 'CAPITULATION-WATCH'
    else:
        zone = 'NEUTRAL'

    return {
        'zone': zone,
        'top_count': top_count,
        'bottom_count': bottom_count,
        'total_indicators': total,
        'indicators': indicators,
    }


def format_crypto_zone(z: dict) -> str:
    if not z or z['zone'] == 'unknown':
        return "Crypto zone: unknown (all APIs failed)"
    emoji = {
        'TOP-ZONE': '🔴',
        'ELEVATED': '🟠',
        'NEUTRAL': '⚪',
        'CAPITULATION-WATCH': '🟡',
        'BOTTOM-ZONE': '🟢',
    }.get(z['zone'], '⚪')
    lines = [f"{emoji} CRYPTO: {z['zone']} ({z['top_count']} top / {z['bottom_count']} bottom)"]
    for ind in z['indicators']:
        z_str = ind['zone']
        ze = ('🔴' if z_str == 'top-zone' else
              '🟢' if z_str in ('negative', 'capitulation', 'low') else '⚪')
        lines.append(f"  {ze} {ind['name']}: {ind['value']} [{z_str}]")
    if z['zone'] == 'TOP-ZONE':
        lines.append("")
        lines.append("⚠ Historically high-risk zone. Consider reducing crypto exposure.")
    elif z['zone'] == 'BOTTOM-ZONE':
        lines.append("")
        lines.append("📊 Historically accumulation zone. Consider DCA.")
    return '\n'.join(lines)
