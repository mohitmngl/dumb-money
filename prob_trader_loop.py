import time, json, urllib.request, numpy as np
from datetime import datetime

HEADERS = {'APCA-API-KEY-ID': 'PKUPBR7N6SS6NQUJ4U24NO7GEO', 'APCA-API-SECRET-KEY': 'BFGrUckWUymMRYVe9kkrz1V2zVLXeoxBU7Kr5K54Cfsq'}
TRADE_NOTIONAL = 500
TOP_N = 2
CHECK_INTERVAL = 90
PROB_THRESHOLD = 0.70

TOP_LIQUID = [
    'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AMD','NFLX',
    'SPY','QQQ','JPM','V','UNH','MA','JNJ','WMT','PG','XOM',
    'HD','COST','ABBV','MRK','PEP','KO','AVGO','LLY','CRM',
    'ACN','ORCL','NKE','ADBE','TXN','QCOM','INTC','CSCO','PFE','DIS',
    'PYPL','UBER','SQ','COIN','PLTR','SOFI','HOOD','RBLX'
]

def api(method, path, body=None):
    url = f'https://paper-api.alpaca.markets{path}'
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, headers=HEADERS, data=data, method=method)
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())

def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())

def fetch_bars(sym, tf="15Min", limit=100):
    url = f'https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe={tf}&limit={limit}&feed=iex'
    return fetch_json(url).get('bars', [])

def fetch_daily(sym, limit=20):
    url = f'https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Day&limit={limit}&feed=iex'
    return fetch_json(url).get('bars', [])

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = gains[-period:].mean()
    avg_loss = losses[-period:].mean()
    if avg_loss == 0: return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))

def score_stock(bars_15m, daily_bars=None):
    n = len(bars_15m)
    if n < 5: return 0.0, "NEED_DATA"
    closes = np.array([b['c'] for b in bars_15m], dtype=np.float64)
    highs = np.array([b['h'] for b in bars_15m], dtype=np.float64)
    lows = np.array([b['l'] for b in bars_15m], dtype=np.float64)
    volumes = np.array([b['v'] for b in bars_15m], dtype=np.float64)
    score = 0.0
    signals = []
    if n >= 6:
        recent = closes[-3:].mean()
        prev = closes[-6:-3].mean()
        mom = (recent - prev) / prev * 100
        score += np.clip(mom / 0.3, -2, 2) * 2.0
        signals.append(f"mom={mom:+.2f}%")
    if n >= 6:
        vol_avg = volumes[-6:-1].mean()
        vol_surge = volumes[-1] / max(vol_avg, 1)
        score += np.clip((vol_surge - 1) * 1.5, -2, 2) * 1.5
        signals.append(f"vol={vol_surge:.1f}x")
    h, l = highs.max(), lows.min()
    pos = (closes[-1] - l) / max(h - l, 0.001)
    score += (pos - 0.5) * 4 * 1.0
    signals.append(f"pos={pos:.2f}")
    streak = 0
    for i in range(n-1, 0, -1):
        if closes[i] > closes[i-1]:
            if streak >= 0: streak += 1
            else: break
        elif closes[i] < closes[i-1]:
            if streak <= 0: streak -= 1
            else: break
        else: break
    score += np.clip(streak / 2, -2, 2) * 1.5
    signals.append(f"strk={streak:+d}")
    rsi = calc_rsi(closes, min(14, n-1))
    score += (rsi - 50) / 25 * 1.0
    signals.append(f"rsi={rsi:.0f}")
    if daily_bars and len(daily_bars) >= 10:
        dc = np.array([b['c'] for b in daily_bars], dtype=np.float64)
        if len(dc) >= 20:
            sma5, sma20 = dc[-5:].mean(), dc[-20:].mean()
            dt = 1 if sma5 > sma20 else -1
            score += dt * 1.0
            signals.append(f"dTrend={'+' if dt > 0 else '-'}")
        if len(dc) >= 5:
            dmom = (dc[-1] - dc[-5]) / dc[-5] * 100
            score += np.clip(dmom / 3, -1.5, 1.5)
            signals.append(f"dMom={dmom:+.1f}%")
    prob = 1 / (1 + np.exp(-score * 0.4))
    return prob, " ".join(signals)

def get_positions():
    return {p['symbol']: p for p in api('GET', '/v2/positions')}

def close_position(sym):
    try:
        api('DELETE', f'/v2/positions/{sym}')
        print(f"    CLOSED {sym}")
        return True
    except:
        return False

def buy_stock(sym, notional):
    body = {"symbol": sym, "notional": str(notional), "side": "buy", "type": "market", "time_in_force": "day"}
    o = api('POST', '/v2/orders', body)
    print(f"    BUY {sym} ${notional}: {o['status']}")
    return o

print(f"{'='*70}")
print(f"  15-MIN PROBABILITY TRADER")
print(f"  Notional per trade: ${TRADE_NOTIONAL}  |  Top {TOP_N}  |  Threshold: {PROB_THRESHOLD:.0%}")
print(f"  Check interval: {CHECK_INTERVAL}s")
print(f"{'='*70}")

run_count = 0
while True:
    t_cycle = time.time()
    now = datetime.now()
    run_count += 1

    clock = api('GET', '/v2/clock')
    if not clock['is_open']:
        print(f"\n[{now.strftime('%H:%M:%S')}] Market closed. Waiting for open: {clock['next_open']}")
        time.sleep(60)
        continue

    print(f"\n[{now.strftime('%H:%M:%S')}] Cycle #{run_count} - Scanning...")

    positions = get_positions()
    current_syms = set(positions.keys())
    print(f"  Current positions: {list(current_syms) if current_syms else 'none'}")

    bars_data = {}
    for sym in TOP_LIQUID:
        try:
            b = fetch_bars(sym)
            if b and len(b) >= 5:
                bars_data[sym] = b
        except: pass

    daily_data = {}
    for sym in bars_data:
        try:
            d = fetch_daily(sym)
            if d: daily_data[sym] = d
        except: pass

    results = []
    for sym, bars in bars_data.items():
        prob, det = score_stock(bars, daily_data.get(sym))
        results.append((sym, prob, bars[-1]['c'], det))
    results.sort(key=lambda x: x[1], reverse=True)

    print(f"  Scored {len(results)} stocks")
    top = results[:TOP_N]
    for i, (sym, prob, price, det) in enumerate(top):
        print(f"    #{i+1} {sym} prob={prob:.1%} ${price:.2f} [{det}]")

    top_syms = set(s for s, _, _, _ in top)

    for sym in list(current_syms):
        if sym not in top_syms:
            print(f"  Dropping {sym} (not in top {TOP_N}):")
            close_position(sym)

    for sym, prob, price, _ in top:
        if prob >= PROB_THRESHOLD:
            if sym in current_syms:
                print(f"  HOLDING {sym} (prob={prob:.1%} >= {PROB_THRESHOLD:.0%})")
            else:
                print(f"  ENTERING {sym} (prob={prob:.1%} >= {PROB_THRESHOLD:.0%}):")
                buy_stock(sym, TRADE_NOTIONAL)
        else:
            print(f"  SKIP {sym} (prob={prob:.1%} < {PROB_THRESHOLD:.0%})")
            if sym in current_syms:
                print(f"  Closing {sym} (prob dropped below threshold):")
                close_position(sym)

    elapsed = time.time() - t_cycle
    wait = max(0, CHECK_INTERVAL - elapsed)
    print(f"  Cycle took {elapsed:.0f}s. Next check in {wait:.0f}s.")
    if wait > 0:
        time.sleep(wait)
