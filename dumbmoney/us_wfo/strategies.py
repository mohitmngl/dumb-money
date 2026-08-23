"""Entry signal definitions, filter logic, SL/TP for US WFO."""
import numpy as np, pandas as pd

ENTRY_TYPES = [
    'st_bullish', 'st_cross_above',
    'st_bullish+accel_bullish', 'st_bullish+accel_cross_up',
    'st_bullish+high_alpha', 'st_bullish+high_prob', 'st_bullish+high_confluence',
    'st_bullish+accel_bullish+high_prob', 'st_bullish+accel_bullish+high_confluence',
]

def apply_entry_filters(df, params):
    mask = pd.Series(True, index=df.index)
    et = params['entry_type']
    if 'st_bullish' in et: mask &= (df['atr_signal'] == 1)
    if 'st_cross_above' in et: mask &= (df['atr_crossed_above'] == 1)
    if 'accel_bullish' in et: mask &= (df['accel_signal'] == 1)
    if 'accel_cross_up' in et: mask &= (df['accel_crossed_up'] == 1)
    if 'high_alpha' in et: mask &= (df['weighted_alpha'] >= params.get('min_weighted_alpha', 0))
    if 'high_prob' in et: mask &= (df['prob_up_1d'] >= params.get('min_prob_up_1d', 50))
    if 'high_confluence' in et: mask &= (df['confluence'] >= params.get('min_confluence', 0))
    return mask

def apply_stage2_filters(df, params):
    mask = pd.Series(True, index=df.index)
    if params.get('min_atrp') is not None: mask &= (df['atrp'] >= params['min_atrp'])
    if params.get('max_atrp') is not None and params['max_atrp'] < 999: mask &= (df['atrp'] <= params['max_atrp'])
    if params.get('min_volume_shares') is not None: mask &= (df['volume'] >= params['min_volume_shares'])
    if params.get('streak_min') is not None: mask &= (df['streak'] <= params['streak_min'])
    if params.get('streak_max') is not None: mask &= (df['streak'] >= -params['streak_max'])
    return mask

def rank_and_select(day_data, params):
    sort_col = params.get('sort_by', 'confluence')
    top_n = params.get('top_n', 10)
    if len(day_data) == 0: return day_data
    day_data = day_data.copy()
    day_data['_rank'] = day_data.groupby('date')[sort_col].rank(ascending=False, method='first', na_option='bottom')
    selected = day_data[day_data['_rank'] <= top_n].drop('_rank', axis=1)
    return selected

def apply_sl_tp(entry_prices, next_high, next_low, next_close, stop_loss=None, take_profit=None):
    returns = (next_close - entry_prices) / entry_prices
    if stop_loss is not None:
        sl_price = entry_prices * (1 + stop_loss)
        sl_hit = next_low <= sl_price
        returns = np.where(sl_hit, stop_loss, returns)
    if take_profit is not None:
        tp_price = entry_prices * (1 + take_profit)
        tp_hit = next_high >= tp_price
        if stop_loss is not None:
            sl_price = entry_prices * (1 + stop_loss)
            sl_hit = next_low <= sl_price
            tp_hit = tp_hit & ~sl_hit
        returns = np.where(tp_hit, take_profit, returns)
    return returns

def compute_daily_portfolio(df, params):
    mask = apply_entry_filters(df, params)
    eligible = df[mask].copy()
    if params.get('min_atrp') is not None or params.get('max_atrp') is not None or params.get('min_volume_shares') is not None:
        stage2_mask = apply_stage2_filters(eligible, params)
        eligible = eligible[stage2_mask]
    if len(eligible) == 0:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    selected = rank_and_select(eligible, params)
    if len(selected) == 0:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    trade_returns = apply_sl_tp(selected['price'].values, selected['next_high'].values, selected['next_low'].values, selected['next_close'].values, stop_loss=params.get('stop_loss_pct'), take_profit=params.get('take_profit_pct'))
    selected = selected.copy()
    selected['trade_return'] = trade_returns
    daily = selected.groupby('date')['trade_return'].mean()
    return daily, selected.set_index('date')['trade_return']
