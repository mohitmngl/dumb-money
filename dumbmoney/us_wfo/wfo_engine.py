"""Core walk-forward optimization engine with staged optimization."""
import numpy as np, pandas as pd
from itertools import product
from strategies import ENTRY_TYPES, apply_entry_filters, apply_stage2_filters, rank_and_select, compute_daily_portfolio

def compute_fitness(daily_returns, per_trade_returns, min_trades=30):
    n_trades = len(per_trade_returns)
    n_days = len(daily_returns)
    if n_trades < min_trades:
        return {'fitness': -9999, 'valid': False, 'n_trades': n_trades}
    win_rate = (per_trade_returns > 0).mean()
    total_return = (1 + daily_returns).prod() - 1
    n_years = max(n_days / 252.0, 0.01)
    ann_return = (1 + total_return) ** (1 / n_years) - 1 if total_return > -1 else -1
    cumulative = (1 + daily_returns).cumprod()
    peak = cumulative.cummax()
    dd = (cumulative - peak) / peak
    max_dd = abs(dd.min())
    gross_profit = per_trade_returns[per_trade_returns > 0].sum()
    gross_loss = abs(per_trade_returns[per_trade_returns < 0].sum())
    pf = gross_profit / max(gross_loss, 1e-10)
    calmar = ann_return / max(max_dd, 1e-6)
    dr_std = daily_returns.std()
    sharpe = (daily_returns.mean() / dr_std * np.sqrt(252)) if dr_std > 0 else 0
    x = np.arange(len(cumulative))
    slope, intercept = np.polyfit(x, cumulative.values, 1)
    predicted = slope * x + intercept
    ss_res = np.sum((cumulative.values - predicted) ** 2)
    ss_tot = np.sum((cumulative.values - np.mean(cumulative.values)) ** 2)
    r_squared = max(1 - ss_res / ss_tot, 0) if ss_tot > 0 else 0
    daily_wr = (daily_returns > 0).mean()
    wr_score = min(win_rate * 100, 100)
    if win_rate >= 0.90: wr_score = 90 + (win_rate - 0.90) * 100
    return_score = min(max(calmar, 0) * 5, 100)
    linearity_score = r_squared * 100
    pf_score = min(pf * 5, 100)
    sharpe_score = min(max(sharpe, 0) * 10, 100)
    consistency_score = daily_wr * 100
    raw = 0.30 * wr_score + 0.25 * return_score + 0.20 * linearity_score + 0.10 * pf_score + 0.10 * sharpe_score + 0.05 * consistency_score
    trade_rel = 1 / (1 + np.exp(-0.015 * (n_trades - 200)))
    wr_mod = 0.5 + 0.5 * (win_rate / 0.90) if win_rate < 0.90 else 1.0 + 0.3 * ((win_rate - 0.90) / 0.10)
    coverage = min(n_trades / max(n_days, 1), 1.0)
    cov_mod = max(0.5, coverage)
    fitness = raw * trade_rel * wr_mod * cov_mod
    return {'fitness': fitness, 'valid': True, 'n_trades': n_trades, 'win_rate': win_rate, 'total_return': total_return, 'annualized_return': ann_return, 'max_drawdown': max_dd, 'r_squared': r_squared, 'profit_factor': pf, 'calmar': calmar, 'sharpe': sharpe, 'daily_win_rate': daily_wr}

def generate_stage1_combos():
    alphas = [0]; probs = [55, 70]; confls = [20, 50]
    sorts = ['confluence', 'weighted_alpha', 'prob_up_1d']; top_ns = [5, 10, 15]
    combos = []
    for et in ENTRY_TYPES:
        for wa in alphas:
            for pu in probs:
                for co in confls:
                    for so in sorts:
                        for tn in top_ns:
                            combos.append({'entry_type': et, 'min_weighted_alpha': wa, 'min_prob_up_1d': pu, 'min_confluence': co, 'sort_by': so, 'sort_ascending': False, 'top_n': tn})
    return combos

def generate_stage2_combos(base):
    atrp_mins = [0.5, 1.0, 2.0]; atrp_maxs = [8.0, 12.0, 999.0]
    vol_mins = [500000, 1000000, 2000000]; streak_mins = [None, -3, -2]; streak_maxs = [None, 2, 3]
    combos = []
    for am in atrp_mins:
        for aM in atrp_maxs:
            for vm in vol_mins:
                for smin in streak_mins:
                    for smax in streak_maxs:
                        p = base.copy()
                        p.update({'min_atrp': am, 'max_atrp': aM, 'min_volume_shares': vm, 'streak_min': smin, 'streak_max': smax})
                        combos.append(p)
    return combos

def generate_stage3_combos(base):
    stop_losses = [None, -0.01, -0.02, -0.03, -0.05]
    take_profits = [None, 0.01, 0.02, 0.03, 0.05]
    combos = []
    for sl in stop_losses:
        for tp in take_profits:
            p = base.copy(); p['stop_loss_pct'] = sl; p['take_profit_pct'] = tp; combos.append(p)
    return combos

def evaluate_combo(df, params, min_trades=30):
    daily, trades = compute_daily_portfolio(df, params)
    return compute_fitness(daily, trades, min_trades=min_trades)

def run_wfo(data, train_start, train_end, test_start, test_end, min_trades=30):
    train_data = data[(data['date'] >= train_start) & (data['date'] < train_end)].copy()
    test_data = data[(data['date'] >= test_start) & (data['date'] <= test_end)].copy()
    if len(train_data) == 0 or len(test_data) == 0: return None, None, None
    stage1 = generate_stage1_combos()
    s1_results = []
    for params in stage1:
        metrics = evaluate_combo(train_data, params, min_trades=min_trades)
        if metrics['valid']: s1_results.append((params, metrics))
    s1_results.sort(key=lambda x: x[1]['fitness'], reverse=True)
    s1_top5 = [r[0] for r in s1_results[:5]]
    if not s1_top5: return None, None, None
    stage2 = []
    for base in s1_top5: stage2.extend(generate_stage2_combos(base))
    s2_results = []
    for params in stage2:
        metrics = evaluate_combo(train_data, params, min_trades=min_trades)
        if metrics['valid']: s2_results.append((params, metrics))
    s2_results.sort(key=lambda x: x[1]['fitness'], reverse=True)
    s2_top5 = [r[0] for r in s2_results[:5]]
    if not s2_top5: s2_top5 = s1_top5[:1]
    stage3 = []
    for base in s2_top5: stage3.extend(generate_stage3_combos(base))
    s3_results = []
    for params in stage3:
        metrics = evaluate_combo(train_data, params, min_trades=min_trades)
        if metrics['valid']: s3_results.append((params, metrics))
    s3_results.sort(key=lambda x: x[1]['fitness'], reverse=True)
    if not s3_results: return None, None, None
    best_params, train_metrics = s3_results[0]
    oos_metrics = evaluate_combo(test_data, best_params, min_trades=max(min_trades // 3, 5))
    return best_params, train_metrics, oos_metrics

def run_full_wfo(data, initial_train_months=6, test_window_months=1, step_months=1, min_trades=30, progress_callback=None):
    dates = sorted(data['date'].unique())
    n_dates = len(dates)
    train_days = initial_train_months * 21
    test_days = test_window_months * 21
    step_days = step_months * 21
    folds = []; fold_idx = 0
    while train_days + (fold_idx + 1) * step_days + test_days <= n_dates:
        train_start = dates[0]
        train_end_idx = train_days + fold_idx * step_days
        test_start_idx = train_end_idx
        test_end_idx = min(test_start_idx + test_days, n_dates - 1)
        if train_end_idx >= n_dates or test_start_idx >= n_dates: break
        train_end = dates[train_end_idx]; test_start = dates[test_start_idx]; test_end = dates[test_end_idx]
        if progress_callback: progress_callback(fold_idx, str(train_start), str(train_end), str(test_start), str(test_end))
        best_params, train_m, oos_m = run_wfo(data, train_start, train_end, test_start, test_end, min_trades=min_trades)
        folds.append({'fold': fold_idx, 'train_start': str(train_start), 'train_end': str(train_end), 'test_start': str(test_start), 'test_end': str(test_end), 'best_params': best_params, 'train_metrics': train_m, 'oos_metrics': oos_m})
        fold_idx += 1
    return folds