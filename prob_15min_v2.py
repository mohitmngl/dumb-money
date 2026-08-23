import time, json, urllib.request, numpy as np
from datetime import datetime

t_start = time.time()
HEADERS = {'APCA-API-KEY-ID': 'PKUPBR7N6SS6NQUJ4U24NO7GEO', 'APCA-API-SECRET-KEY': 'BFGrUckWUymMRYVe9kkrz1V2zVLXeoxBU7Kr5K54Cfsq'}

TOP_LIQUID = [
    'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AMD','NFLX','BABA',
    'SPY','QQQ','JPM','V','UNH','MA','JNJ','WMT','PG','XOM',
    'HD','COST','ABBV','MRK','PEP','KO','AVGO','LLY','CRM','TMO',
    'ACN','ORCL','NKE','ADBE','TXN','QCOM','INTC','CSCO','PFE','DIS',
    'PYPL','UBER','SQ','COIN','PLTR','SOFI','RIVN','LCID','HOOD','RBLX'
]

def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())

def fetch_bars(sym, tf="15Min", limit=200):
    url = f'https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe={tf}&limit={limit}&feed=iex'
    return fetch_json(url).get('bars', [])

def fetch_daily(sym, limit=40):
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
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_bollinger(closes, period=20):
    if len(closes) < period:
        return 0.0, 0.0, 0.0
    sma = closes[-period:].mean()
    std = closes[-period:].std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    pct = (closes[-1] - lower) / max(upper - lower, 0.001)
    return pct, upper, lower

def score_stock(bars_15m, daily_bars):
    n = len(bars_15m)
    if n < 5:
        return 0.0, "NEED_DATA"
    
    closes = np.array([b['c'] for b in bars_15m], dtype=np.float64)
    highs = np.array([b['h'] for b in bars_15m], dtype=np.float64)
    lows = np.array([b['l'] for b in bars_15m], dtype=np.float64)
    volumes = np.array([b['v'] for b in bars_15m], dtype=np.float64)
    
    score = 0.0
    signals = []
    
    # --- 15-MIN SIGNALS ---
    
    # 1. Short-term momentum (last 3 bars vs prev 3)
    if n >= 6:
        recent = closes[-3:].mean()
        prev = closes[-6:-3].mean()
        mom = (recent - prev) / prev * 100
        mom_score = np.clip(mom / 0.3, -2, 2)
        score += mom_score * 2.0
        signals.append(f"mom15={mom:+.2f}%")
    else:
        mom = (closes[-1] - closes[0]) / closes[0] * 100
        score += np.clip(mom / 0.5, -2, 2) * 1.5
        signals.append(f"mom15={mom:+.2f}%")
    
    # 2. Volume surge (last bar vs avg of bars 2-6)
    if n >= 6:
        vol_avg = volumes[-6:-1].mean()
        vol_surge = volumes[-1] / max(vol_avg, 1)
        vol_score = np.clip((vol_surge - 1) * 1.5, -2, 2)
        score += vol_score * 1.5
        signals.append(f"vol={vol_surge:.1f}x")
    
    # 3. Price position in range
    h = highs.max()
    l = lows.min()
    pos = (closes[-1] - l) / max(h - l, 0.001)
    pos_score = (pos - 0.5) * 4
    score += pos_score * 1.0
    signals.append(f"pos={pos:.2f}")
    
    # 4. Consecutive bar direction
    streak = 0
    for i in range(n-1, 0, -1):
        if closes[i] > closes[i-1]:
            if streak >= 0: streak += 1
            else: break
        elif closes[i] < closes[i-1]:
            if streak <= 0: streak -= 1
            else: break
        else: break
    strk_score = np.clip(streak / 2, -2, 2)
    score += strk_score * 1.5
    signals.append(f"strk={streak:+d}")
    
    # 5. RSI on 15min
    rsi = calc_rsi(closes, period=min(14, n-1))
    rsi_score = (rsi - 50) / 25
    score += rsi_score * 1.0
    signals.append(f"rsi={rsi:.0f}")
    
    # 6. Bollinger position
    bb_pct, _, _ = calc_bollinger(closes, period=min(20, n))
    bb_score = (bb_pct - 0.5) * 3
    score += bb_score * 1.0
    signals.append(f"bb={bb_pct:.2f}")
    
    # --- DAILY CONTEXT SIGNALS ---
    if daily_bars and len(daily_bars) >= 10:
        dc = np.array([b['c'] for b in daily_bars], dtype=np.float64)
        dh = np.array([b['h'] for b in daily_bars], dtype=np.float64)
        dl = np.array([b['l'] for b in daily_bars], dtype=np.float64)
        
        # Daily trend: 5d vs 20d SMA
        if len(dc) >= 20:
            sma5 = dc[-5:].mean()
            sma20 = dc[-20:].mean()
            daily_trend = 1 if sma5 > sma20 else -1
            score += daily_trend * 1.0
            signals.append(f"dTrend={'↑' if daily_trend > 0 else '↓'}")
        
        # Daily momentum
        if len(dc) >= 5:
            dmom = (dc[-1] - dc[-5]) / dc[-5] * 100
            score += np.clip(dmom / 3, -1.5, 1.5)
            signals.append(f"dMom={dmom:+.1f}%")
    
    prob = 1 / (1 + np.exp(-score * 0.4))
    return prob, " ".join(signals)

# ===== MAIN =====
print("Phase 1: Download 15min bars...")
t1 = time.time()
bars_15m = {}
for sym in TOP_LIQUID:
    try:
        bars = fetch_bars(sym)
        if bars and len(bars) >= 3:
            bars_15m[sym] = bars
    except: pass
t2 = time.time()
print(f"  Got {len(bars_15m)} stocks in {t2-t1:.1f}s")

print("Phase 2: Download daily bars...")
daily = {}
for sym in bars_15m:
    try:
        d = fetch_daily(sym)
        if d: daily[sym] = d
    except: pass
t3 = time.time()
print(f"  Got {len(daily)} daily datasets in {t3-t2:.1f}s")

print("Phase 3: Score stocks...")
results = []
for sym in bars_15m:
    prob, details = score_stock(bars_15m[sym], daily.get(sym))
    last_close = bars_15m[sym][-1]['c']
    results.append((sym, prob, last_close, details))

results.sort(key=lambda x: x[1], reverse=True)

now_str = datetime.now().strftime('%H:%M:%S')
print(f"\n{'='*95}")
print(f"  15-MIN PROBABILITY MODEL  |  {now_str}  |  {len(results)} stocks scored")
print(f"{'='*95}")
print(f"{'#':>3} {'Symbol':>6} {'Prob':>7} {'Price':>10}  Signals")
print(f"{'-'*95}")
for i, (sym, prob, price, det) in enumerate(results):
    marker = " <<<" if i < 2 else ""
    print(f"{i+1:>3} {sym:>6} {prob:>6.1%} ${price:>9.2f}  {det}{marker}")

print(f"\n{'='*95}")
print("  TOP 2 ENTRIES ($500 each):")
print(f"{'='*95}")
for i in range(min(2, len(results))):
    sym, prob, price, _ = results[i]
    qty = 500 / price
    print(f"  {i+1}. BUY {sym} @ ${price:.2f} = {qty:.4f} shares  (prob={prob:.1%})")
print(f"\n  Total allocation: $1,000")
print(f"\n  Timing: ~{t2-t1:.0f}s download + ~{t3-t2:.0f}s daily + ~{time.time()-t3:.1f}s scoring = ~{time.time()-t_start:.0f}s total")
print(f"{'='*95}")
