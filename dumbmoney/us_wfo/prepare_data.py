"""Prepare US market data for walk-forward optimization."""
import sqlite3, os, pandas as pd, numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'screener.db')

HIST_COLS = [
    'symbol', 'date', 'price', 'change_pct', 'volume',
    'weighted_alpha', 'atrp', 'streak', 'atr_value', 'atr_stop', 'atr_signal',
    'atr_crossed_above', 'atr_crossed_below', 'atr_streak',
    'prob_up_1d', 'prob_up_5d', 'prob_up_st_cross',
    'accel_a', 'accel_base', 'accel_signal', 'accel_crossed_up', 'accel_crossed_down',
    'confluence', 'next_day_return',
    'ai_overall_score', 'ai_tech_score', 'ai_momentum_score', 'ai_volume_score',
]

def load_us_data(start_date='2024-07-28', end_date='2026-07-28', stock_limit=None, min_price=1.0, min_volume=100000):
    print('Loading US market data...')
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA cache_size=-200000')
    assets = pd.read_sql("SELECT symbol FROM assets WHERE exchange != 'OTC'", conn)
    valid_syms = set(assets['symbol'].tolist())
    print('  Non-OTC assets: %d' % len(valid_syms))
    print('  Loading hist_screener...')
    cols = ', '.join(HIST_COLS)
    hs = pd.read_sql('SELECT %s FROM historical_screener WHERE date >= ? AND date <= ?' % cols, conn, params=[start_date, end_date])
    print('  Hist_screener rows: %d' % len(hs))
    hs = hs[hs['symbol'].isin(valid_syms)]
    hs = hs[(hs['price'] >= min_price) & (hs['volume'] >= min_volume)]
    print('  After price/volume filter: %d' % len(hs))
    print('  Loading bars OHLC...')
    sym_list = sorted(hs['symbol'].unique())
    if stock_limit:
        sym_list = sym_list[:stock_limit]
        hs = hs[hs['symbol'].isin(sym_list)]
        print('  Limited to %d stocks' % stock_limit)
    ph = ','.join('?' * len(sym_list))
    bars = pd.read_sql("SELECT symbol, date, open, high, low, close FROM bars WHERE timeframe='1Day' AND date >= ? AND date <= ? AND symbol IN (%s)" % ph, conn, params=[start_date, end_date] + sym_list)
    conn.close()
    print('  Bars rows: %d' % len(bars))
    merged = hs.merge(bars, on=['symbol', 'date'], how='inner')
    print('  Merged rows: %d' % len(merged))
    merged = merged.sort_values(['date', 'symbol']).reset_index(drop=True)
    print('  Computing next-day OHLC...')
    merged['next_close'] = merged.groupby('symbol')['close'].shift(-1)
    merged['next_high'] = merged.groupby('symbol')['high'].shift(-1)
    merged['next_low'] = merged.groupby('symbol')['low'].shift(-1)
    merged['next_open'] = merged.groupby('symbol')['open'].shift(-1)
    merged['next_day_return_calc'] = (merged['next_close'] - merged['price']) / merged['price']
    merged['dollar_volume'] = merged['volume'] * merged['price']
    before = len(merged)
    merged = merged.dropna(subset=['next_close'])
    print('  After dropping NaN next-day: %d (dropped %d)' % (len(merged), before - len(merged)))
    n_dates = merged['date'].nunique()
    n_syms = merged['symbol'].nunique()
    print('  Final: %d rows, %d dates, %d symbols' % (len(merged), n_dates, n_syms))
    print('  Date range: %s to %s' % (merged['date'].min(), merged['date'].max()))
    return merged

def load_us_data_smoke(start_date='2026-04-28', end_date='2026-07-28', stock_limit=100):
    return load_us_data(start_date, end_date, stock_limit=stock_limit)
