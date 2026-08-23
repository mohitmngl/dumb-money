"""String backtest v6 - Per-date iteration using existing date index.
Each single-date query is fast (~0s). Process all dates one by one."""
import sqlite3, numpy as np, pandas as pd, json, time, warnings, sys, os
warnings.filterwarnings('ignore')
from scipy.stats import skew, kurtosis as kurt_func
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

TOP_N = 10
OUTPUT_DIR = 'backtest_charts'
os.makedirs(OUTPUT_DIR, exist_ok=True)

def run_bt(db_file, bt_name):
    print('\n=== ' + bt_name + ' ===', flush=True)
    t0 = time.time()
    conn = sqlite3.connect(db_file, timeout=60)
    conn.execute('PRAGMA busy_timeout=120000')
    conn.execute('PRAGMA journal_mode=WAL')

    # Get all distinct dates first (fast with idx_hss_date)
    print('  Getting all dates...', flush=True)
    all_dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM historical_string_screener ORDER BY date"
    ).fetchall()]
    print('  ' + str(len(all_dates)) + ' total dates (' + str(int(time.time()-t0)) + 's)', flush=True)

    # Process each date
    all_daily = []
    t1 = time.time()
    for i, dt in enumerate(all_dates):
        rows = conn.execute(
            "SELECT next_day_return, prob_up_st_cross "
            "FROM historical_string_screener "
            "WHERE date = ? AND accel_crossed_up = 1 "
            "AND next_day_return IS NOT NULL "
            "AND prob_up_st_cross IS NOT NULL AND prob_up_st_cross > 0 "
            "ORDER BY prob_up_st_cross DESC LIMIT " + str(TOP_N),
            (dt,)
        ).fetchall()
        if rows:
            avg_ret = np.mean([r[0] for r in rows]) / 100.0  # stored as pct
            all_daily.append((dt, avg_ret))
        if (i + 1) % 200 == 0:
            elapsed = int(time.time() - t1)
            print('  Processed ' + str(i+1) + '/' + str(len(all_dates)) + ' dates (' + str(elapsed) + 's)', flush=True)

    conn.close()
    elapsed = int(time.time() - t0)
    print('  Total processed: ' + str(len(all_daily)) + ' days (' + str(elapsed) + 's)', flush=True)

    dates_list = [d[0] for d in all_daily]
    ret = np.array([d[1] for d in all_daily], dtype=float)
    ret = np.clip(ret, -0.5, 2.0)

    print('  Mean daily: ' + str(np.mean(ret)) + ', Median: ' + str(np.median(ret)), flush=True)
    return ret, dates_list

def calc_stats(ret, dates_list, pname=''):
    n = len(ret)
    if n < 3: return {}
    cum_log = np.cumsum(np.log1p(ret))
    cum = np.exp(cum_log)
    tr = float(cum[-1] - 1)
    md_val = float(np.mean(ret))
    sd = float(np.std(ret, ddof=1))
    rf = 0.05 / 252; ex = ret - rf
    ann_ret = float((1 + tr) ** (252 / n) - 1) if tr > -1 else -1
    ann_vol = float(sd * np.sqrt(252))
    sharpe = float(np.mean(ex) / sd * np.sqrt(252)) if sd > 0 else 0
    down = ret[ret < 0]
    drms = float(np.sqrt(np.mean(down ** 2))) if len(down) > 0 else 1e-10
    sortino = float(np.mean(ex) / drms * np.sqrt(252))
    rm = np.maximum.accumulate(cum); dd_arr = (cum - rm) / rm; mdd = float(np.min(dd_arr))
    calmar = float(ann_ret / abs(mdd)) if abs(mdd) > 0 else 0
    w = int(np.sum(ret > 0)); l = int(np.sum(ret < 0)); wr = float(w / n)
    aw = float(np.mean(ret[ret > 0])) if w > 0 else 0
    al = float(np.mean(ret[ret < 0])) if l > 0 else 0
    gp = float(np.sum(ret[ret > 0])); gl = float(np.abs(np.sum(ret[ret < 0])))
    pf = float(gp / gl) if gl > 0 else 0
    po = float(abs(aw / al)) if al != 0 else 0
    kelly_val = float(wr - (1 - wr) / po) if po > 0 else 0
    cpc = float(po * wr * pf)
    rec = float(tr / abs(mdd)) if abs(mdd) > 0 else 0
    ulcer = float(np.sqrt(np.mean(dd_arr ** 2)))
    ddu = 0; mddu = 0; dds = []
    for d_val in dd_arr:
        if d_val < 0: ddu += 1; mddu = max(mddu, ddu)
        else:
            if ddu > 0: dds.append(ddu)
            ddu = 0
    if ddu > 0: dds.append(ddu)
    addu = float(np.mean(dds)) if dds else 0
    sk = float(skew(ret)); ku = float(kurt_func(ret))
    v5 = float(np.percentile(ret, 5)); c5 = float(np.mean(ret[ret <= v5])) if np.any(ret <= v5) else v5
    v1 = float(np.percentile(ret, 1)); c1 = float(np.mean(ret[ret <= v1])) if np.any(ret <= v1) else v1
    ts = float(md_val / (sd / np.sqrt(n))) if sd > 0 else 0
    mcw = 0; mcl = 0; cw = 0; cl2 = 0
    for r in ret:
        if r > 0: cw += 1; cl2 = 0; mcw = max(mcw, cw)
        elif r < 0: cl2 += 1; cw = 0; mcl = max(mcl, cl2)
        else: cw = 0; cl2 = 0
    dates_dt = pd.to_datetime(dates_list)
    rdf = pd.DataFrame({'date': dates_dt, 'return': ret}); rdf.set_index('date', inplace=True)
    mo = rdf['return'].resample('ME').apply(lambda x: np.prod(1 + x) - 1)
    bm = float(mo.max()) if len(mo) > 0 else 0; wm = float(mo.min()) if len(mo) > 0 else 0
    pm = int((mo > 0).sum()); nm = int((mo < 0).sum())
    yr = rdf['return'].resample('YE').apply(lambda x: np.prod(1 + x) - 1)
    by = float(yr.max()) if len(yr) > 0 else 0; wy = float(yr.min()) if len(yr) > 0 else 0
    py_cnt = int((yr > 0).sum()); ny = int((yr < 0).sum())
    avg_loss_abs = abs(al) if al != 0 else 1e-10; avg_r = float(np.mean(ret / avg_loss_abs))
    mae = float(np.min(ret)); mfe = float(np.max(ret))
    gains = float(np.sum(ret[ret > 0])); lsum = float(np.abs(np.sum(ret[ret < 0])))
    omega = float(gains / lsum) if lsum > 0 else 0
    r95 = float(np.percentile(ret, 95)); l5 = float(np.abs(np.percentile(ret, 5)))
    tail = float(r95 / l5) if l5 > 0 else 0
    x_arr = np.arange(n); sl_val, ic = np.polyfit(x_arr, cum_log, 1); pl_arr = ic + sl_val * x_arr
    ssr = float(np.sum((cum_log - pl_arr) ** 2)); sst = float(np.sum((cum_log - np.mean(cum_log)) ** 2))
    rsq = float(1 - ssr / sst) if sst > 0 else 0
    sa_arr = np.sort(np.abs(ret)); gn = len(sa_arr); gs_val = float(np.sum(sa_arr))
    gini = float((2 * np.sum(np.arange(1, gn + 1) * sa_arr)) / (gn * gs_val) - (gn + 1) / gn) if gs_val > 0 else 0
    sd2 = float(np.sqrt(np.mean(down ** 2))) if len(down) > 0 else 0
    dex = ret[ret < rf] - rf; ddv = float(np.sqrt(np.mean(dex ** 2))) if len(dex) > 0 else 0
    autocorr = float(pd.Series(ret).autocorr()) if n > 5 else 0
    max5 = 0.0; worst5 = 0.0
    if n >= 5:
        for i in range(n - 4):
            f5 = float(np.prod(1 + ret[i:i + 5]) - 1); max5 = max(max5, f5); worst5 = min(worst5, f5)
    cal_days = int((dates_dt[-1] - dates_dt[0]).days)
    monthly_returns = {}
    for dt_idx, row in mo.items():
        monthly_returns[dt_idx.strftime('%Y-%m')] = float(row)
    yearly_returns = {}
    for dt_idx, row in yr.items():
        yearly_returns[dt_idx.strftime('%Y')] = float(row)
    return {
        'Period': pname, 'Total Return': '{:.2%}'.format(tr), 'CAGR': '{:.2%}'.format(ann_ret),
        'Mean Daily Return': '{:.5%}'.format(md_val), 'Median Daily Return': '{:.5%}'.format(float(np.median(ret))),
        'Annualized Volatility': '{:.2%}'.format(ann_vol), 'Std Dev Daily': '{:.5%}'.format(sd),
        'Sharpe Ratio': '{:.3f}'.format(sharpe), 'Sortino Ratio': '{:.3f}'.format(sortino),
        'Calmar Ratio': '{:.3f}'.format(calmar), 'Omega Ratio': '{:.3f}'.format(omega),
        'Tail Ratio': '{:.3f}'.format(tail), 'Recovery Factor': '{:.3f}'.format(rec),
        'Max Drawdown': '{:.2%}'.format(mdd), 'Max DD Duration': mddu, 'Avg DD Duration': '{:.1f}'.format(addu),
        'Ulcer Index': '{:.4f}'.format(ulcer), 'Trading Days': n, 'Calendar Days': cal_days,
        'Win Rate': '{:.2%}'.format(wr), 'Winners': w, 'Losers': l,
        'Avg Win': '{:.4%}'.format(aw), 'Avg Loss': '{:.4%}'.format(al),
        'Payoff Ratio': '{:.3f}'.format(po), 'Max Consec Wins': mcw, 'Max Consec Losses': mcl,
        'Profit Factor': '{:.3f}'.format(pf), 'Gross Profit': '{:.2%}'.format(gp), 'Gross Loss': '{:.2%}'.format(gl),
        'Expectancy': '{:.5%}'.format(md_val), 'Kelly Criterion': '{:.3f}'.format(kelly_val), 'CPC Index': '{:.3f}'.format(cpc),
        'Skewness': '{:.3f}'.format(sk), 'Kurtosis': '{:.3f}'.format(ku),
        'VaR 5%': '{:.4%}'.format(v5), 'CVaR 5%': '{:.4%}'.format(c5),
        'VaR 1%': '{:.4%}'.format(v1), 'CVaR 1%': '{:.4%}'.format(c1),
        'T-Statistic': '{:.3f}'.format(ts), 'Autocorr': '{:.3f}'.format(autocorr),
        'Best Day': '{:.4%}'.format(mfe), 'Worst Day': '{:.4%}'.format(mae),
        'Max 5-Day': '{:.4%}'.format(max5), 'Worst 5-Day': '{:.4%}'.format(worst5),
        'Best Month': '{:.2%}'.format(bm), 'Worst Month': '{:.2%}'.format(wm),
        'Pos Months': pm, 'Neg Months': nm, 'Best Year': '{:.2%}'.format(by), 'Worst Year': '{:.2%}'.format(wy),
        'Pos Years': py_cnt, 'Neg Years': ny, 'Avg R-Multiple': '{:.3f}'.format(avg_r),
        'Semi-Deviation': '{:.5%}'.format(sd2), 'Downside Deviation': '{:.5%}'.format(ddv),
        'Gini': '{:.3f}'.format(gini), 'R-Squared': '{:.3f}'.format(rsq),
        'monthly_returns': monthly_returns, 'yearly_returns': yearly_returns,
    }

def generate_charts(bt_name, ret, dates_list, all_period_stats):
    dates_dt = pd.to_datetime(dates_list)
    cum = np.cumprod(1 + ret)

    fig, axes = plt.subplots(3, 2, figsize=(18, 16))
    fig.suptitle(bt_name + ' - ST Crossed Up Strategy (Top ' + str(TOP_N) + ' by P(Up) ST)', fontsize=16, fontweight='bold')

    ax = axes[0, 0]
    ax.plot(dates_dt, cum, 'b-', linewidth=1)
    ax.set_title('Equity Curve (log scale)')
    ax.set_yscale('log')
    ax.set_ylabel('Cumulative Return')
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    ax = axes[0, 1]
    rm = np.maximum.accumulate(cum)
    dd = (cum - rm) / rm
    ax.fill_between(dates_dt, dd * 100, 0, alpha=0.5, color='red')
    ax.set_title('Drawdown')
    ax.set_ylabel('Drawdown %')
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    ax = axes[1, 0]
    ax.hist(ret, bins=100, alpha=0.7, color='steelblue', edgecolor='white')
    ax.axvline(x=0, color='red', linestyle='--', alpha=0.5)
    ax.axvline(x=np.mean(ret), color='green', linestyle='--', alpha=0.8, label='Mean: ' + '{:.4%}'.format(np.mean(ret)))
    ax.set_title('Daily Return Distribution')
    ax.set_xlabel('Daily Return')
    ax.legend()
    ax.grid(True, alpha=0.3)

    ax = axes[1, 1]
    rdf = pd.DataFrame({'date': dates_dt, 'return': ret})
    rdf.set_index('date', inplace=True)
    monthly = rdf['return'].resample('ME').apply(lambda x: np.prod(1 + x) - 1)
    colors = ['green' if x > 0 else 'red' for x in monthly.values]
    ax.bar(range(len(monthly)), monthly.values * 100, color=colors, alpha=0.7, width=0.8)
    ax.set_title('Monthly Returns')
    ax.set_ylabel('Return %')
    tick_positions = range(0, len(monthly), max(1, len(monthly) // 10))
    ax.set_xticks(list(tick_positions))
    ax.set_xticklabels([monthly.index[i].strftime('%Y-%m') for i in tick_positions], rotation=45)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='black', linewidth=0.5)

    ax = axes[2, 0]
    if len(ret) > 252:
        roll_mean = pd.Series(ret).rolling(252).mean()
        roll_std = pd.Series(ret).rolling(252).std()
        roll_sharpe = (roll_mean - 0.05/252) / roll_std * np.sqrt(252)
        ax.plot(dates_dt, roll_sharpe, 'purple', linewidth=1)
        ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)
        ax.axhline(y=1, color='green', linestyle='--', alpha=0.5, label='Sharpe=1')
        ax.set_title('Rolling 1Y Sharpe Ratio')
        ax.legend()
    else:
        ax.text(0.5, 0.5, 'Insufficient data for rolling Sharpe', ha='center', va='center', transform=ax.transAxes)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    ax = axes[2, 1]
    ax.axis('off')
    full_stats = all_period_stats.get('Full History', {})
    table_data = [
        ['Metric', 'Value'],
        ['Total Return', full_stats.get('Total Return', 'N/A')],
        ['CAGR', full_stats.get('CAGR', 'N/A')],
        ['Sharpe Ratio', full_stats.get('Sharpe Ratio', 'N/A')],
        ['Sortino Ratio', full_stats.get('Sortino Ratio', 'N/A')],
        ['Max Drawdown', full_stats.get('Max Drawdown', 'N/A')],
        ['Calmar Ratio', full_stats.get('Calmar Ratio', 'N/A')],
        ['Win Rate', full_stats.get('Win Rate', 'N/A')],
        ['Profit Factor', full_stats.get('Profit Factor', 'N/A')],
        ['Trading Days', full_stats.get('Trading Days', 'N/A')],
    ]
    table = ax.table(cellText=table_data, loc='center', cellLoc='center', colWidths=[0.4, 0.3])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.5)
    for i in range(len(table_data)):
        for j in range(len(table_data[0])):
            cell = table[i, j]
            if i == 0:
                cell.set_facecolor('#4472C4')
                cell.set_text_props(color='white', fontweight='bold')
            elif i % 2 == 0:
                cell.set_facecolor('#D9E2F3')
    ax.set_title('Key Statistics (Full History)', fontweight='bold', pad=20)

    plt.tight_layout()
    fig_path = os.path.join(OUTPUT_DIR, bt_name.replace(' ', '_') + '_charts.png')
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.close()
    print('  Saved: ' + fig_path, flush=True)
    return fig_path

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

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else 'all'

    all_results = {}
    chart_files = []

    for bname, dbf in [('US Strings', 'screener.db'), ('India Strings', 'india.db')]:
        if target != 'all' and target != bname:
            continue
        ret, dates_list = run_bt(dbf, bname)

        all_results[bname] = {}
        for pname, (s, e) in periods.items():
            if s:
                da = np.array(dates_list); mask = (da >= s) & (da <= e)
                sr = ret[mask]; sd = [d for d, m in zip(dates_list, mask) if m]
            else:
                sr = ret; sd = dates_list
            if len(sr) < 3: continue
            st = calc_stats(sr, sd, pname)
            all_results[bname][pname] = st
            print('  ' + pname + ': ' + str(st.get('Trading Days', '?')) + 'd Ret=' + str(st.get('Total Return', '?')) + ' Sharpe=' + str(st.get('Sharpe Ratio', '?')) + ' MaxDD=' + str(st.get('Max Drawdown', '?')) + ' WR=' + str(st.get('Win Rate', '?')), flush=True)

        chart_path = generate_charts(bname, ret, dates_list, all_results[bname])
        chart_files.append(chart_path)

    # Merge with all existing results (preserve all backtests)
    merged = {}
    for f_name in ['backtest_results.json', 'backtest_results_all.json']:
        if os.path.exists(f_name):
            with open(f_name) as f:
                merged.update(json.load(f))
    merged.update(all_results)

    with open('backtest_results_all.json', 'w') as f:
        json.dump(merged, f, indent=2, default=str)
    print('\nSaved backtest_results_all.json', flush=True)
    print('Charts: ' + str(chart_files), flush=True)
