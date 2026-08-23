import os, json, numpy as np, pandas as pd

def aggregate_oos(folds):
    valid = [f for f in folds if f['oos_metrics'] and f['oos_metrics'].get('valid')]
    if not valid: return {}
    wrs = [f['oos_metrics']['win_rate'] for f in valid]
    rets = [f['oos_metrics']['total_return'] for f in valid]
    dds = [f['oos_metrics']['max_drawdown'] for f in valid]
    r2s = [f['oos_metrics']['r_squared'] for f in valid]
    sharpes = [f['oos_metrics']['sharpe'] for f in valid]
    pfs = [f['oos_metrics']['profit_factor'] for f in valid]
    n_trades = [f['oos_metrics']['n_trades'] for f in valid]
    return {'n_folds': len(valid), 'avg_win_rate': np.mean(wrs), 'avg_return': np.mean(rets), 'avg_max_dd': np.mean(dds), 'avg_r_squared': np.mean(r2s), 'avg_sharpe': np.mean(sharpes), 'avg_profit_factor': np.mean(pfs), 'total_trades': sum(n_trades), 'min_win_rate': np.min(wrs), 'max_win_rate': np.max(wrs), 'fold_win_rates': wrs, 'fold_returns': rets}

def parameter_stability(folds):
    valid = [f for f in folds if f['best_params']]
    if not valid: return {}
    from collections import Counter
    stability = {}
    param_keys = valid[0]['best_params'].keys()
    for key in param_keys:
        values = [str(f['best_params'].get(key, 'None')) for f in valid]
        counts = Counter(values); total = len(values)
        entropy = -sum((c / total) * np.log2(c / total) for c in counts.values() if c > 0)
        max_entropy = np.log2(len(counts)) if len(counts) > 1 else 1
        stability[key] = {'most_common': counts.most_common(1)[0], 'entropy': round(entropy, 3), 'stability_score': round(1 - entropy / max_entropy, 3) if max_entropy > 0 else 1.0}
    return stability

def print_summary(folds, agg, stability):
    print('')
    print('=' * 70)
    print('WALK-FORWARD OPTIMIZATION RESULTS')
    print('=' * 70)
    print('')
    print('--- OOS Aggregate (%d folds) ---' % agg.get('n_folds', 0))
    print('  Avg Win Rate:     %.2f%% (min: %.2f%%, max: %.2f%%)' % (agg.get('avg_win_rate', 0) * 100, agg.get('min_win_rate', 0) * 100, agg.get('max_win_rate', 0) * 100))
    print('  Avg Return:       %.2f%%' % (agg.get('avg_return', 0) * 100))
    print('  Avg Max Drawdown: %.2f%%' % (agg.get('avg_max_dd', 0) * 100))
    print('  Avg R-squared:    %.3f' % agg.get('avg_r_squared', 0))
    print('  Avg Sharpe:       %.2f' % agg.get('avg_sharpe', 0))
    print('  Avg Profit Factor: %.2f' % agg.get('avg_profit_factor', 0))
    print('  Total Trades:     %d' % agg.get('total_trades', 0))
    print('')
    print('--- Per-Fold Win Rates ---')
    for i, wr in enumerate(agg.get('fold_win_rates', [])):
        bar = '#' * int(wr * 50)
        print('  Fold %2d: %.1f%% %s' % (i + 1, wr * 100, bar))
    print('')
    print('--- Parameter Stability ---')
    for key, info in sorted(stability.items(), key=lambda x: -x[1]['stability_score']):
        print('  %-25s stability=%.2f  top=%s (%d times)' % (key, info['stability_score'], info['most_common'][0], info['most_common'][1]))
    print('')
    print('--- Best Parameters (most common) ---')
    for key, info in sorted(stability.items()): print('  %s: %s' % (key, info['most_common'][0]))
    print('')
    print('--- Per-Fold Details ---')
    for f in folds:
        oos = f.get('oos_metrics', {})
        if oos and oos.get('valid'):
            print('  Fold %d [%s -> %s]: WR=%.1f%% Ret=%.2f%% DD=%.2f%% Sharpe=%.2f' % (f['fold'] + 1, f['test_start'], f['test_end'], oos['win_rate'] * 100, oos['total_return'] * 100, oos['max_drawdown'] * 100, oos['sharpe']))
        else: print('  Fold %d: No valid OOS result' % (f['fold'] + 1))

def save_results(folds, agg, stability, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    summary = {'aggregate': agg, 'stability': stability, 'folds': [{k: v for k, v in f.items() if k != 'oos_metrics'} for f in folds]}
    with open(os.path.join(output_dir, 'wfo_summary.json'), 'w') as f: json.dump(summary, f, indent=2, default=str)
    _generate_equity_html(folds, agg, output_dir)
    print('')
    print('Results saved to: %s' % output_dir)

def _generate_equity_html(folds, agg, output_dir):
    valid = [f for f in folds if f['oos_metrics'] and f['oos_metrics'].get('valid')]
    if not valid: return
    dates = [f['test_end'] for f in valid]
    win_rates = [f['oos_metrics']['win_rate'] * 100 for f in valid]
    returns = [f['oos_metrics']['total_return'] * 100 for f in valid]
    drawdowns = [f['oos_metrics']['max_drawdown'] * 100 for f in valid]
    dates_json = json.dumps(dates)
    wr_json = json.dumps(win_rates)
    ret_json = json.dumps(returns)
    dd_json = json.dumps([-d for d in drawdowns])
    avg_wr = agg.get('avg_win_rate', 0) * 100
    avg_ret = agg.get('avg_return', 0) * 100
    avg_dd = agg.get('avg_max_dd', 0) * 100
    avg_sharpe = agg.get('avg_sharpe', 0)
    avg_r2 = agg.get('avg_r_squared', 0)
    parts = []
    parts.append('<!DOCTYPE html><html><head><meta charset="utf-8"><title>US WFO Results</title>')
    parts.append('<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>')
    parts.append('<style>')
    parts.append('body{font-family:sans-serif;margin:20px;background:#1a1a2e;color:#eee}')
    parts.append('h1{text-align:center}')
    parts.append('.chart{width:100%;height:350px}')
    parts.append('.stats{display:flex;justify-content:center;gap:20px;margin:20px 0;flex-wrap:wrap}')
    parts.append('.card{background:#16213e;border-radius:10px;padding:12px 20px;text-align:center;min-width:150px;border:1px solid #333}')
    parts.append('.card .lbl{font-size:11px;color:#888}')
    parts.append('.card .val{font-size:22px;font-weight:bold}')
    parts.append('.green{color:#2ecc71}.blue{color:#3498db}')
    parts.append('</style></head><body>')
    parts.append('<h1>US Market BTST Walk-Forward Optimization</h1>')
    parts.append('<div class="stats">')
    parts.append('<div class="card"><div class="lbl">Avg Win Rate</div><div class="val green">%.1f%%</div></div>' % avg_wr)
    parts.append('<div class="card"><div class="lbl">Avg Return</div><div class="val green">%.1f%%</div></div>' % avg_ret)
    parts.append('<div class="card"><div class="lbl">Avg Max DD</div><div class="val">%.1f%%</div></div>' % avg_dd)
    parts.append('<div class="card"><div class="lbl">Avg Sharpe</div><div class="val blue">%.2f</div></div>' % avg_sharpe)
    parts.append('<div class="card"><div class="lbl">Avg R-squared</div><div class="val blue">%.3f</div></div>' % avg_r2)
    parts.append('</div>')
    parts.append('<div id="c1" class="chart"></div>')
    parts.append('<div id="c2" class="chart"></div>')
    parts.append('<script>')
    parts.append('Plotly.newPlot("c1",[{x:%s,y:%s,name:"Win Rate",type:"scatter",mode:"lines+markers",line:{color:"#2ecc71",width:2}}],{title:"OOS Win Rate by Fold",paper_bgcolor:"#1a1a2e",plot_bgcolor:"#16213e",xaxis:{title:"Fold",gridcolor:"#333",color:"#aaa"},yaxis:{title:"Win Rate %%",gridcolor:"#333",color:"#aaa"}});' % (dates_json, wr_json))
    parts.append('Plotly.newPlot("c2",[{x:%s,y:%s,name:"Return %%",type:"bar",marker:{color:"#3498db"}},{x:%s,y:%s,name:"Max DD %%",type:"bar",marker:{color:"#e74c3c"}}],{title:"OOS Return vs Drawdown by Fold",barmode:"group",paper_bgcolor:"#1a1a2e",plot_bgcolor:"#16213e",xaxis:{title:"Fold",gridcolor:"#333",color:"#aaa"},yaxis:{title:"%%",gridcolor:"#333",color:"#aaa"},legend:{bgcolor:"#16213e",font:{color:"#eee"}}});' % (dates_json, ret_json, dates_json, dd_json))
    parts.append('</script></body></html>')
    html = ''.join(parts)
    with open(os.path.join(output_dir, 'wfo_equity.html'), 'w') as f:
        f.write(html)