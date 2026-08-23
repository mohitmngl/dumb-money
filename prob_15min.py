import time, json, urllib.request, numpy as np

t_start = time.time()
HEADERS = {'APCA-API-KEY-ID': 'PKUPBR7N6SS6NQUJ4U24NO7GEO', 'APCA-API-SECRET-KEY': 'BFGrUckWUymMRYVe9kkrz1V2zVLXeoxBU7Kr5K54Cfsq'}

TOP_LIQUID = [
    'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AMD','NFLX','BABA',
    'SPY','QQQ','JPM','V','UNH','MA','JNJ','WMT','PG','XOM',
    'HD','COST','ABBV','MRK','PEP','KO','AVGO','LLY','CRM','TMO',
    'ACN','ORCL','NKE','ADBE','TXN','QCOM','INTC','CSCO','PFE','DIS',
    'PYPL','UBER','SQ','COIN','PLTR','SOFI','RIVN','LCID','HOOD','RBLX'
]

def fetch_bars(sym, timeframe="15Min", limit=200):
    url = f'https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe={timeframe}&limit={limit}&feed=iex'
    req = urllib.request.Request(url, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read()).get('bars', [])

def calc_probability(bars):
    if len(bars) < 20:
        return 0.5, "NEED_DATA"
    closes = np.array([b['c'] for b in bars], dtype=np.float64)
    highs = np.array([b['h'] for b in bars], dtype=np.float64)
    lows = np.array([b['l'] for b in bars], dtype=np.float64)
    volumes = np.array([b['v'] for b in bars], dtype=np.float64)
    
    # 1. SMA trend (5-bar and 15-bar)
    sma5 = closes[-5:].mean()
    sma15 = closes[-15:].mean()
    trend_up = 1 if sma5 > sma15 else -1
    
    # 2. Recent momentum (last 5 bars)
    ret5 = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0
    momentum = np.clip(ret5 / 2, -3, 3)
    
    # 3. Volume surge (current vs average)
    vol_avg = volumes[-20:-5].mean() if len(volumes) >= 20 else volumes.mean()
    vol_surge = volumes[-1] / max(vol_avg, 1) if vol_avg > 0 else 1
    vol_signal = np.clip((vol_surge - 1) * 2, -2, 2)
    
    # 4. Price position (where is close relative to high-low range)
    h20 = highs[-20:].max()
    l20 = lows[-20:].min()
    pos = (closes[-1] - l20) / max(h20 - l20, 0.01)
    pos_signal = (pos - 0.5) * 4
    
    # 5. Streak
    streak = 0
    for i in range(len(closes)-1, 0, -1):
        if closes[i] > closes[i-1]:
            if streak >= 0: streak += 1
            else: break
        elif closes[i] < closes[i-1]:
            if streak <= 0: streak -= 1
            else: break
        else:
            break
    streak_signal = np.clip(streak / 3, -2, 2)
    
    # 6. ATRP on 15min
    tr_arr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
    atr14 = tr_arr[-14:].mean() if len(tr_arr) >= 14 else tr_arr.mean()
    atrp = (atr14 / closes[-1]) * 100 if closes[-1] > 0 else 0
    
    # Combined score
    score = (trend_up * 2.0 + momentum * 1.5 + vol_signal * 1.0 + 
             pos_signal * 1.5 + streak_signal * 1.0)
    
    # Probability from score via sigmoid
    prob = 1 / (1 + np.exp(-score * 0.5))
    
    details = f"trend={trend_up:+d} mom={ret5:+.2f}% vol={vol_surge:.1f}x pos={pos:.2f} strk={streak:+d} atrp={atrp:.1f}%"
    return prob, details

# Download bars for all stocks
print(f"Downloading 15min bars for {len(TOP_LIQUID)} stocks...")
t1 = time.time()
all_bars = {}
for sym in TOP_LIQUID:
    try:
        bars = fetch_bars(sym)
        if bars and len(bars) >= 5:
            all_bars[sym] = bars
    except Exception as e:
        pass
t2 = time.time()
print(f"Downloaded {len(all_bars)} stocks in {t2-t1:.1f}s\n")

# Calculate probabilities
results = []
for sym, bars in all_bars.items():
    prob, details = calc_probability(bars)
    last_close = bars[-1]['c']
    results.append((sym, prob, last_close, details))

results.sort(key=lambda x: x[1], reverse=True)

print("=" * 90)
print(f"{'Rank':>4} {'Sym':>6} {'Prob':>6} {'Price':>9} Details")
print("=" * 90)
for i, (sym, prob, price, details) in enumerate(results):
    marker = " <<< BUY" if i < 2 else ""
    print(f"{i+1:>4} {sym:>6} {prob:>5.1%} ${price:>8.2f} {details}{marker}")

print()
print("=" * 90)
print("TOP 2 PICKS FOR $500 EACH:")
print("=" * 90)
for i in range(min(2, len(results))):
    sym, prob, price, details = results[i]
    qty = 500 / price
    print(f"  BUY {sym}: ${500:.0f} / ${price:.2f} = {qty:.4f} shares (prob={prob:.1%})")

elapsed = time.time() - t_start
print(f"\nTotal time: {elapsed:.1f}s")
print(f"  Bar download: {t2-t1:.1f}s")
print(f"  Probability calc: {time.time()-t2:.1f}s")
