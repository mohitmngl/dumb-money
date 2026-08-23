import json
import urllib.request
import numpy as np
from datetime import datetime

API_KEY = 'PKUPBR7N6SS6NQUJ4U24NO7GEO'
API_SECRET = 'BFGrUckWUymMRYVe9kkrz1V2zVLXeoxBU7Kr5K54Cfsq'
BASE_URL = 'https://paper-api.alpaca.markets'
DATA_URL = 'https://data.alpaca.markets'

HEADERS = {
    'APCA-API-KEY-ID': API_KEY,
    'APCA-API-SECRET-KEY': API_SECRET
}

def api_get(path, base=BASE_URL):
    url = f'{base}{path}'
    req = urllib.request.Request(url, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())

def api_post(path, body, base=BASE_URL):
    url = f'{base}{path}'
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, headers=HEADERS, data=data, method='POST')
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())

def api_delete(path):
    url = f'{BASE_URL}{path}'
    req = urllib.request.Request(url, headers=HEADERS, method='DELETE')
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read()
    return json.loads(raw) if raw else {}

def get_clock():
    return api_get('/v2/clock')

def get_account():
    return api_get('/v2/account')

def get_positions():
    return api_get('/v2/positions')

def get_top_liquid(limit=50):
    snap = api_get(f'/v2/stocks/snapshots?symbols=', base=DATA_URL)
    return snap

def get_snapshots(symbols):
    sym_str = ','.join(symbols)
    return api_get(f'/v2/stocks/snapshots?symbols={sym_str}', base=DATA_URL)

def get_most_active(count=50):
    assets = api_get('/v2/assets?status=active&asset_class=us_equity')
    stocks = [a for a in assets if a.get('class') == 'us_equity' and a.get('tradable')]
    stocks.sort(key=lambda x: x.get('easy_to_borrow', False), reverse=True)
    return stocks[:count]

def fetch_1min_bars(symbol, limit=20):
    path = f'/v2/stocks/{symbol}/bars?timeframe=1Min&limit={limit}&feed=iex'
    data = api_get(path, base=DATA_URL)
    bars = data.get('bars', [])
    return bars

def fetch_latest_trades(symbols):
    results = {}
    for sym in symbols:
        try:
            path = f'/v2/stocks/{sym}/trades/latest?feed=iex'
            data = api_get(path, base=DATA_URL)
            trade = data.get('trade', {})
            if trade and trade.get('p'):
                results[sym] = {
                    'price': trade['p'],
                    'size': trade.get('s', 0),
                    'time': trade.get('t', ''),
                    'exchange': trade.get('x', '')
                }
        except:
            pass
    return results

def fetch_latest_quotes(symbols):
    results = {}
    for sym in symbols:
        try:
            path = f'/v2/stocks/{sym}/quotes/latest?feed=iex'
            data = api_get(path, base=DATA_URL)
            quote = data.get('quote', {})
            if quote:
                mid = (quote.get('bp', 0) + quote.get('ap', 0)) / 2
                results[sym] = {
                    'bid': quote.get('bp', 0),
                    'ask': quote.get('ap', 0),
                    'mid': mid,
                    'bid_size': quote.get('bs', 0),
                    'ask_size': quote.get('as', 0),
                    'time': quote.get('t', '')
                }
        except:
            pass
    return results

def fetch_1min_bars_batch(symbols, limit=50):
    results = {}
    for sym in symbols:
        try:
            bars = fetch_1min_bars(sym, limit)
            if bars and len(bars) >= 5:
                results[sym] = bars
        except Exception as e:
            pass
    return results

def compute_atr(highs, lows, closes, period=14):
    if len(closes) < 2:
        return np.array([])
    highs = np.array(highs, dtype=np.float64)
    lows = np.array(lows, dtype=np.float64)
    closes = np.array(closes, dtype=np.float64)
    prev_c = np.concatenate([[closes[0]], closes[:-1]])
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_c), np.abs(lows - prev_c)))
    atr = np.full_like(tr, np.nan)
    if len(tr) >= period:
        atr[period - 1] = tr[:period].mean()
        for i in range(period, len(tr)):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr

def compute_supertrend(highs, lows, closes, period=14, multiplier=3.0):
    atr = compute_atr(highs, lows, closes, period)
    if len(atr) == 0 or np.all(np.isnan(atr)):
        return None, None, None

    n = len(closes)
    upper_band = np.full(n, np.nan)
    lower_band = np.full(n, np.nan)
    supertrend = np.full(n, np.nan)
    direction = np.full(n, 0)

    hl2 = (np.array(highs) + np.array(lows)) / 2.0

    for i in range(period - 1, n):
        if np.isnan(atr[i]):
            continue
        basic_upper = hl2[i] + multiplier * atr[i]
        basic_lower = hl2[i] - multiplier * atr[i]

        if i == period - 1:
            upper_band[i] = basic_upper
            lower_band[i] = basic_lower
        else:
            upper_band[i] = basic_upper if basic_upper < upper_band[i - 1] or closes[i - 1] > upper_band[i - 1] else upper_band[i - 1]
            lower_band[i] = basic_lower if basic_lower > lower_band[i - 1] or closes[i - 1] < lower_band[i - 1] else lower_band[i - 1]

        if i == period - 1:
            direction[i] = 1
            supertrend[i] = lower_band[i]
        else:
            prev_dir = direction[i - 1]
            if prev_dir == 1:
                direction[i] = -1 if closes[i] < lower_band[i - 1] else 1
            else:
                direction[i] = 1 if closes[i] > upper_band[i - 1] else -1

            supertrend[i] = lower_band[i] if direction[i] == 1 else upper_band[i]

    return supertrend, direction, atr

def analyze_stock(bars):
    if not bars or len(bars) < 15:
        return None

    closes = [b['c'] for b in bars]
    highs = [b['h'] for b in bars]
    lows = [b['l'] for b in bars]
    volumes = [b['v'] for b in bars]
    timestamps = [b['t'] for b in bars]

    supertrend, direction, atr = compute_supertrend(highs, lows, closes, period=14, multiplier=3.0)

    if supertrend is None or np.isnan(supertrend[-1]):
        return None

    last_close = closes[-1]
    last_volume = volumes[-1]
    last_atr = atr[-1] if not np.isnan(atr[-1]) else 0
    atrp = (last_atr / last_close * 100) if last_close > 0 else 0
    st_value = supertrend[-1]
    st_direction = int(direction[-1])

    prev_st = supertrend[-2] if len(supertrend) > 1 and not np.isnan(supertrend[-2]) else st_value
    prev_dir = int(direction[-2]) if len(direction) > 1 else st_direction

    crossed_above = prev_dir == -1 and st_direction == 1
    crossed_below = prev_dir == 1 and st_direction == -1

    return {
        'symbol': bars[0]['S'] if 'S' in bars[0] else None,
        'last_close': last_close,
        'last_volume': last_volume,
        'atr': last_atr,
        'atrp': atrp,
        'supertrend': st_value,
        'direction': st_direction,
        'crossed_above': crossed_above,
        'crossed_below': crossed_below,
        'highs': highs,
        'lows': lows,
        'closes': closes,
        'bars': bars,
        'timestamp': timestamps[-1]
    }

def fire_order(symbol, notional, side):
    body = {
        'symbol': symbol,
        'notional': str(notional),
        'side': side,
        'type': 'market',
        'time_in_force': 'day'
    }
    return api_post('/v2/orders', body)

def get_order(order_id):
    return api_get(f'/v2/orders/{order_id}')

def cancel_order(order_id):
    return api_delete(f'/v2/orders/{order_id}')

def get_pending_orders():
    return api_get('/v2/orders?status=open')
