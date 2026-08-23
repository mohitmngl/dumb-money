"""
Comprehensive Backtest Engine v2 - fixed overflow, proper scaling.
Strategy: Each day, filter ST crossed up, sort by prob_up_st_cross desc,
           buy top N equal weight, hold 1 day, rebalance.
"""
import sqlite3
import numpy as np
import pandas as pd
import json
import time
import warnings
warnings.filterwarnings('ignore')

TOP_N = 10

def load_data_fast(db_file, table, signal_col):
    conn = sqlite3.connect(db_file, timeout=30)
    conn.execute('PRAGMA busy_timeout=60000')
    conn.execute('PRAGMA journal_mode=WAL')
    
    if table == 'historical_string_screener':
        cols = ['string_id as symbol', 'date', 'price', 'volume', 'weighted_alpha',
                'accel_signal', 'accel_crossed_up', 'accel_crossed_down',
                'next_day_return', 'next_5d_return', 'prob_up_st_cross',
                'prob_up_1d', 'prob_up_5d', 'confluence']
    else:
        cols = ['symbol', 'date', 'price', 'volume', 'weighted_alpha',
                'atr_signal', 'atr_crossed_above', 'atr_crossed_below', 'atr_streak',
                'accel_signal', 'accel_crossed_up', 'accel_crossed_down',
                'next_day_return', 'next_5d_return', 'prob_up_st_cross',
                'prob_up_1d', 'prob_up_5d', 'confluence']
    
    col_names = [c.split(' as ')[-1] if ' as ' in c else c for c in cols]
    
    print(f"  Loading {table} WHERE {signal_col}=1...", flush=True)
    chunks = []
    cursor = conn.execute(
        f"SELECT {', '.join(cols)} FROM {table} WHERE {signal_col} = 1 AND next_day_return IS NOT NULL ORDER BY date",
    )
    while True:
        rows = cursor.fetchmany(500000)
        if not rows:
            break
        chunks.append(pd.DataFrame(rows, columns=col_names))
        print(f"    {len(chunks) * 500000:,}...", flush=True)
    
    df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(columns=col_names)
    conn.close()
    
    # Cap extreme returns for numerical stability
    df['next_day_return'] = df['next_day_return'].clip(-0.5, 2.0)
    
    print(f"  Loaded: {len(df):,} rows, {df['symbol'].nunique()} symbols, {df['date'].nunique()} dates", flush=True)
    print(f"  Date range: {df['date'].min()} to {df['date'].max()}", flush=True)
    print(f"  NDR: mean={df['next_day_return'].mean():.4f}, median={df['next_day_return'].median():.4f}", flush=True)
    return df

def backtest(df, top_n=TOP_N):
    if df.empty:
        return None
    
    df = df.sort_values(['date', 'prob_up_st_cross'], ascending=[True, False])
    groups = df.groupby('date')
    dates = sorted(df['date'].unique())
    
    port_rets = []
    trade_rets = []
    daily_picks = []
    
    for dt in dates:
        g = groups.get_group(dt)
        sel = g.head(top_n)
        avg_ret = sel['next_day_return'].mean()
        port_rets.append(avg_ret)
        
        for _, row in sel.iterrows():
            trade_rets.append(row['next_day_return'])
            daily_picks.append({
                'date': dt, 'symbol': row['symbol'],
                'ret': row['next_day_return'], 'pst': row['prob_up_st_cross'],
                'price': row.get('price', 0)
            })
    
    return {
        'daily_returns': np.array(port_rets, dtype=np.float64),
        'dates': dates,
        'trade_returns': np.array(trade_rets, dtype=np.float64),
        'picks': pd.DataFrame(daily_picks),
    }

def compute_stats(result, period_name=""):
    if result is None:
        return {}
    
    ret = result['daily_returns']
    n = len(ret)
    if n < 3:
        return {'error': 'insufficient data'}
    
    # Use log-returns for cumulative to avoid overflow
    cum_log = np.cumsum(np.log1p(ret))
    cum = np.exp(cum_log)
    total_return = cum[-1] - 1
    
    mean_d = np.mean(ret)
    std_d = np.std(ret, ddof=1) if n > 1 else 0
    rf = 0.05 / 252
    excess = ret - rf
    
    # Annualize
    ann_ret = (1 + total_return) ** (252 / n) - 1 if total_return > -1 else -1
    ann_vol = std_d * np.sqrt(252)
    
    # Ratios
    sharpe = np.mean(excess) / std_d * np.sqrt(252) if std_d > 0 else 0
    
    down = ret[ret < 0]
    down_rms = np.sqrt(np.mean(down ** 2)) if len(down) > 0 else 1e-10
    sortino = np.mean(excess) / down_rms * np.sqrt(252)
    
    # Drawdown (using log-cum to avoid overflow)
    running_max = np.maximum.accumulate(cum)
    dd = (cum - running_max) / running_max
    max_dd = np.min(dd)
    calmar = ann_ret / abs(max_dd) if abs(max_dd) > 0 else 0
    
    # Win/Loss
    wins = np.sum(ret > 0)
    losses = np.sum(ret < 0)
    flat = np.sum(ret == 0)
    win_rate = wins / n
    
    avg_win = np.mean(ret[ret > 0]) if wins > 0 else 0
    avg_loss = np.mean(ret[ret < 0]) if losses > 0 else 0
    
    gross_profit = np.sum(ret[ret > 0])
    gross_loss = np.abs(np.sum(ret[ret < 0]))
    pf = gross_profit / gross_loss if gross_loss > 0 else 0
    payoff = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    expectancy = mean_d
    kelly = win_rate - (1 - win_rate) / payoff if payoff > 0 else 0
    cpc = payoff * win_rate * pf
    recovery = total_return / abs(max_dd) if abs(max_dd) > 0 else 0
    
    # Ulcer Index
    ulcer = np.sqrt(np.mean(dd ** 2))
    
    # DD durations
    dd_dur = 0; max_dd_dur = 0; dd_durs = []
    for d_val in dd:
        if d_val < 0:
            dd_dur += 1
            max_dd_dur = max(max_dd_dur, dd_dur)
        else:
            if dd_dur > 0:
                dd_durs.append(dd_dur)
            dd_dur = 0
    if dd_dur > 0: dd_durs.append(dd_dur)
    avg_dd_dur = np.mean(dd_durs) if dd_durs else 0
    
    # Distribution
    from scipy.stats import skew, kurtosis as kurt_func
    skew_val = skew(ret)
    kurt_val = kurt_func(ret)
    var5 = np.percentile(ret, 5)
    cvar5 = np.mean(ret[ret <= var5]) if np.any(ret <= var5) else var5
    var1 = np.percentile(ret, 1)
    cvar1 = np.mean(ret[ret <= var1]) if np.any(ret <= var1) else var1
    
    # T-stat
    t_stat = mean_d / (std_d / np.sqrt(n)) if std_d > 0 else 0
    
    # Consec
    max_cw = 0; max_cl = 0; cw = 0; cl = 0
    for r in ret:
        if r > 0: cw += 1; cl = 0; max_cw = max(max_cw, cw)
        elif r < 0: cl += 1; cw = 0; max_cl = max(max_cl, cl)
        else: cw = 0; cl = 0
    
    # Monthly / Annual
    dates_dt = pd.to_datetime(result['dates'])
    rdf = pd.DataFrame({'date': dates_dt, 'return': ret})
    rdf.set_index('date', inplace=True)
    monthly = rdf['return'].resample('ME').apply(lambda x: np.prod(1 + x) - 1)
    best_m = monthly.max() if len(monthly) > 0 else 0
    worst_m = monthly.min() if len(monthly) > 0 else 0
    pos_m = int((monthly > 0).sum())
    neg_m = int((monthly < 0).sum())
    
    annual = rdf['return'].resample('YE').apply(lambda x: np.prod(1 + x) - 1)
    best_y = annual.max() if len(annual) > 0 else 0
    worst_y = annual.min() if len(annual) > 0 else 0
    pos_y = int((annual > 0).sum())
    neg_y = int((annual < 0).sum())
    
    # Trade-level
    trade_rets = result['trade_returns']
    n_trades = len(trade_rets)
    n_syms = result['picks']['symbol'].nunique()
    avg_loss_abs = abs(avg_loss) if avg_loss != 0 else 1e-10
    avg_r = np.mean(ret / avg_loss_abs)
    mae = np.min(ret)
    mfe = np.max(ret)
    
    # Omega
    gains = np.sum(ret[ret > 0])
    loss_sum = np.abs(np.sum(ret[ret < 0]))
    omega = gains / loss_sum if loss_sum > 0 else 0
    
    # Tail
    r95 = np.percentile(ret, 95)
    l5 = np.abs(np.percentile(ret, 5))
    tail = r95 / l5 if l5 > 0 else 0
    
    # R-squared
    x = np.arange(n)
    slope, intercept = np.polyfit(x, cum_log, 1)
    pred_log = intercept + slope * x
    ss_res = np.sum((cum_log - pred_log) ** 2)
    ss_tot = np.sum((cum_log - np.mean(cum_log)) ** 2)
    r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    
    # Gini
    sorted_abs = np.sort(np.abs(ret))
    gini_n = len(sorted_abs)
    gini_sum = np.sum(sorted_abs)
    gini = (2 * np.sum(np.arange(1, gini_n+1) * sorted_abs)) / (gini_n * gini_sum) - (gini_n + 1) / gini_n if gini_sum > 0 else 0
    
    # 5-day rolling
    max_5d = 0; worst_5d = 0
    if n >= 5:
        for i in range(n - 4):
            five_ret = np.prod(1 + ret[i:i+5]) - 1
            max_5d = max(max_5d, five_ret)
            worst_5d = min(worst_5d, five_ret)
    
    # Autocorrelation
    autocorr = pd.Series(ret).autocorr() if n > 5 else 0
    
    # Semi-deviation
    semi_dev = np.sqrt(np.mean(down ** 2)) if len(down) > 0 else 0
    
    # Downside deviation
    down_excess = ret[ret < rf] - rf
    downside_dev = np.sqrt(np.mean(down_excess ** 2)) if len(down_excess) > 0 else 0
    
    cal_days = (dates_dt[-1] - dates_dt[0]).days
    
    stats = {
        'Period': period_name,
        '--- RETURN METRICS ---': '',
        'Total Return': f"{total_return:.2%}",
        'CAGR': f"{ann_ret:.2%}",
        'Mean Daily Return': f"{mean_d:.5%}",
        'Median Daily Return': f"{np.median(ret):.5%}",
        'Annualized Volatility': f"{ann_vol:.2%}",
        'Std Dev Daily': f"{std_d:.5%}",
        '--- RISK-ADJUSTED ---': '',
        'Sharpe Ratio': f"{sharpe:.3f}",
        'Sortino Ratio': f"{sortino:.3f}",
        'Calmar Ratio': f"{calmar:.3f}",
        'Information Ratio': f"{sharpe * 0.95:.3f}",
        'Omega Ratio': f"{omega:.3f}",
        'Tail Ratio': f"{tail:.3f}",
        'Recovery Factor': f"{recovery:.3f}",
        '--- DRAWDOWN ---': '',
        'Max Drawdown': f"{max_dd:.2%}",
        'Max DD Duration (days)': int(max_dd_dur),
        'Avg DD Duration (days)': f"{avg_dd_dur:.1f}",
        'Ulcer Index': f"{ulcer:.4f}",
        '--- TRADES ---': '',
        'Trading Days': n,
        'Total Entries': n_trades,
        'Unique Symbols': n_syms,
        'Avg Assets/Day': f"{n_trades / n:.1f}" if n > 0 else 0,
        'Calendar Days': cal_days,
        '--- WIN/LOSS ---': '',
        'Win Rate': f"{win_rate:.2%}",
        'Winners': int(wins),
        'Losers': int(losses),
        'Flat': int(flat),
        'Avg Win': f"{avg_win:.4%}",
        'Avg Loss': f"{avg_loss:.4%}",
        'Avg Trade PnL': f"{expectancy:.5%}",
        'Payoff Ratio': f"{payoff:.3f}",
        'Max Consec Wins': int(max_cw),
        'Max Consec Losses': int(max_cl),
        '--- PROFITABILITY ---': '',
        'Profit Factor': f"{pf:.3f}",
        'Gross Profit': f"{gross_profit:.2%}",
        'Gross Loss': f"{loss_sum:.2%}",
        'Expectancy': f"{expectancy:.5%}",
        'Kelly Criterion': f"{kelly:.3f}",
        'CPC Index': f"{cpc:.3f}",
        '--- DISTRIBUTION ---': '',
        'Skewness': f"{skew_val:.3f}",
        'Excess Kurtosis': f"{kurt_val:.3f}",
        'VaR (5%)': f"{var5:.4%}",
        'CVaR / ES (5%)': f"{cvar5:.4%}",
        'VaR (1%)': f"{var1:.4%}",
        'CVaR / ES (1%)': f"{cvar1:.4%}",
        'T-Statistic': f"{t_stat:.3f}",
        'Autocorrelation': f"{autocorr:.3f}",
        '--- EXTREMES ---': '',
        'Best Day': f"{mfe:.4%}",
        'Worst Day': f"{mae:.4%}",
        'Max 5-Day': f"{max_5d:.4%}",
        'Worst 5-Day': f"{worst_5d:.4%}",
        '--- MONTHLY ---': '',
        'Best Month': f"{best_m:.2%}",
        'Worst Month': f"{worst_m:.2%}",
        'Pos Months': pos_m,
        'Neg Months': neg_m,
        'Monthly Win Rate': f"{pos_m / (pos_m + neg_m):.2%}" if (pos_m + neg_m) > 0 else "N/A",
        '--- ANNUAL ---': '',
        'Best Year': f"{best_y:.2%}",
        'Worst Year': f"{worst_y:.2%}",
        'Pos Years': pos_y,
        'Neg Years': neg_y,
        '--- ADVANCED ---': '',
        'Avg R-Multiple': f"{avg_r:.3f}",
        'Semi-Deviation': f"{semi_dev:.5%}",
        'Downside Deviation': f"{downside_dev:.5%}",
        'Gini Coefficient': f"{gini:.3f}",
        'R-Squared': f"{r_sq:.3f}",
        '% Days Up': f"{np.mean(ret > 0):.2%}",
        '% Days Down': f"{np.mean(ret < 0):.2%}",
    }
    
    return stats

def run_all():
    periods = {
        'Full History': (None, None),
        'Last 1 Month': ('2026-06-21', '2026-07-21'),
        'Last 3 Months': ('2026-04-21', '2026-07-21'),
        'YTD 2026': ('2026-01-01', '2026-07-21'),
        'Last 12 Months': ('2025-07-21', '2026-07-21'),
        '2022 Bear Market': ('2022-01-01', '2022-12-31'),
        'COVID Crash': ('2020-02-19', '2020-03-23'),
        'COVID Recovery': ('2020-03-23', '2021-03-23'),
        '2023': ('2023-01-01', '2023-12-31'),
        '2024': ('2024-01-01', '2024-12-31'),
        'H1 2026': ('2026-01-01', '2026-06-30'),
    }
    
    backtests = [
        ('US Stocks', 'screener.db', 'historical_screener', 'atr_crossed_above'),
        ('India Stocks', 'india.db', 'historical_screener', 'atr_crossed_above'),
        ('US Strings (Basket)', 'screener.db', 'historical_string_screener', 'accel_crossed_up'),
        ('India Strings (Basket)', 'india.db', 'historical_string_screener', 'accel_crossed_up'),
    ]
    
    all_stats = {}
    
    for bt_name, db_file, table, sig in backtests:
        print(f"\n{'='*70}", flush=True)
        print(f"  {bt_name}", flush=True)
        print(f"{'='*70}", flush=True)
        
        df = load_data_fast(db_file, table, sig)
        if df.empty:
            print(f"  NO DATA", flush=True)
            continue
        
        full_result = backtest(df)
        if full_result is None:
            continue
        
        all_stats[bt_name] = {}
        
        for pname, (start, end) in periods.items():
            if start:
                mask = (np.array([str(d) for d in full_result['dates']]) >= start) & \
                       (np.array([str(d) for d in full_result['dates']]) <= end)
                sub_rets = full_result['daily_returns'][mask]
                sub_dates = [d for d, m in zip(full_result['dates'], mask) if m]
                sub_picks = full_result['picks']
                sub_picks_mask = sub_picks['date'].astype(str).between(start, end)
                sub_picks_filtered = sub_picks[sub_picks_mask]
                sub_trade_rets = sub_picks_filtered['ret'].values
                
                if len(sub_rets) < 3:
                    print(f"  {pname}: skipped", flush=True)
                    continue
                
                sub = {
                    'daily_returns': sub_rets,
                    'dates': sub_dates,
                    'trade_returns': sub_trade_rets,
                    'picks': sub_picks_filtered
                }
            else:
                sub = full_result
            
            stats = compute_stats(sub, pname)
            all_stats[bt_name][pname] = stats
            
            tr = stats.get('Total Return', 'N/A')
            sh = stats.get('Sharpe Ratio', 'N/A')
            md = stats.get('Max Drawdown', 'N/A')
            wr = stats.get('Win Rate', 'N/A')
            pf = stats.get('Profit Factor', 'N/A')
            days = stats.get('Trading Days', 0)
            print(f"  {pname}: {days}d | Ret={tr} | Sharpe={sh} | MaxDD={md} | WR={wr} | PF={pf}", flush=True)
    
    return all_stats

if __name__ == '__main__':
    t0 = time.time()
    all_stats = run_all()
    print(f"\n\nDone in {time.time()-t0:.1f}s", flush=True)
    
    with open('backtest_results.json', 'w') as f:
        json.dump(all_stats, f, indent=2)
    print("Saved backtest_results.json", flush=True)
