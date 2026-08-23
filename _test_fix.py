import sys, time, numpy as np
sys.path.insert(0, '.')
from dumbmoney.basket_screener import (
    _load_composition, _load_close_pivot, _load_ohlc_pivots,
    _gather_einsum, _compute_basket_ohlc, _compute_basket_indicators,
    _load_hist_metrics_chunk, _series_metrics, get_db
)

sids, sym_list, indices, weights = _load_composition("US")
n = len(sids)
sym_list2, dates, close = _load_close_pivot("US", sym_list)
ohlc = _load_ohlc_pivots("US", sym_list)

V = _gather_einsum(close, indices, weights)
series = _series_metrics(V)
Vn = series["V"]

basket_ohlc = _compute_basket_ohlc(close, ohlc[0], ohlc[1], ohlc[2], indices, weights)
basket_ind = _compute_basket_indicators(basket_ohlc, period=14, multiplier=1.0)

chunk = 200
d0, d1 = 0, min(chunk, len(dates))
chunk_dates = dates[d0:d1]
cd_len = d1 - d0

conn = get_db("US")
wm = _load_hist_metrics_chunk(conn, market="US", sym_list=sym_list, chunk_dates=chunk_dates,
                               W=None, Wn=None, indices=indices, weights=weights)
conn.close()

ai_m = wm.get("ai_matrix")
ai_bias = np.where(ai_m > 55, "bullish", np.where(ai_m < 45, "bearish", "neutral"))
ai_concl = np.where(ai_m > 60, "BUY", np.where(ai_m < 40, "SELL", "HOLD"))

# Fixed indexing
ai_bias_list = [ai_bias[:, di_off].tolist() for di_off in range(cd_len)]
ai_concl_list = [ai_concl[:, di_off].tolist() for di_off in range(cd_len)]

print(f"ai_bias_list[0] len: {len(ai_bias_list[0])}")
print(f"ai_concl_list[0] len: {len(ai_concl_list[0])}")

# Now test full zip for first date
_zero = lambda: np.zeros((n, cd_len), np.float32)
atr_sig = basket_ind["atr_signal"][:, d0:d1].astype(np.int32)
atr_cu = basket_ind["atr_crossed_above"][:, d0:d1].astype(np.int32)
atr_cd = basket_ind["atr_crossed_below"][:, d0:d1].astype(np.int32)
acc_sig = basket_ind["accel_signal"][:, d0:d1].astype(np.int32)
acc_cu = basket_ind["accel_crossed_up"][:, d0:d1].astype(np.int32)
acc_cd = basket_ind["accel_crossed_down"][:, d0:d1].astype(np.int32)
streak_full = np.round(Vn).astype(np.int32)
price_full = V
ret_full = series["ret"]
next_day_full = _zero()
next_5d_full = _zero()

ones_n = [1.0] * n
none_n = [None] * n

def _col(name, _off=0):
    return wm.get(name, _zero())[:, _off]
def _bcol(name, _off=0):
    return basket_ind[name][:, d0 + _off]

di_off = 0
dt = dates[d0]
args = [
    sids, [dt]*n, sids,
    price_full[:, d0].tolist(), ret_full[:, d0].tolist(),
    _col("volume").tolist(), _col("weighted_alpha").tolist(),
    _col("atrp").tolist(), streak_full[:, d0].astype(int).tolist(),
    atr_sig[:, di_off].tolist(), _bcol("atr_stop").tolist(),
    _bcol("atr_value").tolist(), np.round(_bcol("atr_streak")).astype(int).tolist(),
    atr_cu[:, di_off].tolist(), atr_cd[:, di_off].tolist(), ones_n,
    next_day_full[:, d0].tolist(), next_5d_full[:, d0].tolist(),
    _col("prob_up_1d").tolist(), _col("prob_up_5d").tolist(),
    none_n, none_n, none_n, none_n,
    _bcol("accel_a").tolist(), _bcol("accel_base").tolist(),
    acc_sig[:, di_off].tolist(), acc_cu[:, di_off].tolist(), acc_cd[:, di_off].tolist(),
    _bcol("accel_streak").astype(int).tolist(), _col("confluence").tolist(),
    ai_m[:, di_off].tolist(), ai_bias_list[di_off],
    _col("ai_tech_score").tolist(), _col("ai_momentum_score").tolist(),
    _col("ai_volume_score").tolist(), _col("ai_events_score").tolist(),
    _col("ai_volume_profile_score").tolist(), _col("ai_trendline_score").tolist(),
    _col("ai_sentiment_score").tolist(), ai_concl_list[di_off], ai_m[:, di_off].tolist(),
]
batch = list(zip(*args))
print(f"Batch rows for 1 date: {len(batch)} (expected {n})")
if len(batch) == n:
    print("PASS: zip produces correct row count!")
else:
    for i, a in enumerate(args):
        print(f"  arg[{i}]: len={len(a) if hasattr(a,'__len__') else 'scalar'}")
