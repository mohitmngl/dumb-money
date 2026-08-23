import numpy as np

def compute_stats(trades, label=""):
    if not trades:
        return {'label': label, 'trades': 0}

    returns = [t.return_pct for t in trades]
    pnls = [t.pnl for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    total = len(returns)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = win_count / total * 100 if total > 0 else 0

    avg_return = np.mean(returns) if returns else 0
    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0

    profit_factor = abs(sum(wins)) / abs(sum(losses)) if losses and sum(losses) != 0 else float('inf')

    cumulative = np.cumsum(returns)
    peak = np.maximum.accumulate(cumulative)
    drawdown = cumulative - peak
    max_drawdown = drawdown.min() if len(drawdown) > 0 else 0

    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)
    else:
        sharpe = 0

    holding = [t.exit_index - t.entry_index for t in trades]
    avg_holding = np.mean(holding) if holding else 0

    reasons = {}
    for t in trades:
        r = t.exit_reason
        if r not in reasons:
            reasons[r] = {'count': 0, 'returns': []}
        reasons[r]['count'] += 1
        reasons[r]['returns'].append(t.return_pct)

    total_pnl = sum(pnls)

    return {
        'label': label,
        'trades': total,
        'win_rate': win_rate,
        'avg_return': avg_return,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'max_drawdown': max_drawdown,
        'sharpe': sharpe,
        'total_return': sum(returns),
        'total_pnl': total_pnl,
        'avg_holding': avg_holding,
        'exit_reasons': {k: {'count': v['count'], 'avg_return': np.mean(v['returns'])} for k, v in reasons.items()}
    }

def print_stats_table(all_results, timeframe):
    print(f"\n{'='*100}")
    print(f"  BACKTEST RESULTS: {timeframe} CANDLES")
    print(f"{'='*100}")
    header = f"{'STRATEGY':<25} {'TRADES':>7} {'WIN%':>7} {'AVG_RET':>9} {'AVG_WIN':>9} {'AVG_LOSS':>9} {'PF':>7} {'MAX_DD':>9} {'SHARPE':>8} {'TOTAL_PNL':>10}"
    print(header)
    print('-' * 100)

    for r in all_results:
        if r['trades'] == 0:
            print(f"{r['label']:<25} {'NO TRADES':>7}")
            continue
        pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float('inf') else "INF"
        print(f"{r['label']:<25} {r['trades']:>7} {r['win_rate']:>6.1f}% {r['avg_return']:>+8.3f}% {r['avg_win']:>+8.3f}% {r['avg_loss']:>+8.3f}% {pf_str:>7} {r['max_drawdown']:>+8.2f}% {r['sharpe']:>+7.2f} ${r['total_pnl']:>+9.2f}")

    print(f"\n  EXIT BREAKDOWN for each strategy:")
    for r in all_results:
        if r['trades'] == 0:
            continue
        print(f"\n  {r['label']}:")
        for reason, data in sorted(r['exit_reasons'].items(), key=lambda x: x[1]['count'], reverse=True):
            print(f"    {reason:<20}: {data['count']:>5} trades, avg return: {data['avg_return']:>+.3f}%")

    print(f"{'='*100}")

def print_comparison_table(individual_results, basket_results, timeframe):
    print(f"\n{'='*120}")
    print(f"  COMPARISON: INDIVIDUAL vs BASKET | {timeframe} CANDLES")
    print(f"{'='*120}")
    header = f"{'STRATEGY':<25} {'IND_TRADES':>11} {'IND_WIN%':>9} {'IND_PF':>8} {'IND_SHARPE':>11} {'BSK_TRADES':>11} {'BSK_WIN%':>9} {'BSK_PF':>8} {'BSK_SHARPE':>11}"
    print(header)
    print('-' * 120)

    for ind, bsk in zip(individual_results, basket_results):
        label = ind['label']
        it = ind.get('trades', 0)
        iw = ind.get('win_rate', 0)
        ipf = f"{ind.get('profit_factor', 0):.2f}" if ind.get('profit_factor', 0) != float('inf') else "INF"
        is_ = f"{ind.get('sharpe', 0):+.2f}"
        bt = bsk.get('trades', 0)
        bw = bsk.get('win_rate', 0)
        bpf = f"{bsk.get('profit_factor', 0):.2f}" if bsk.get('profit_factor', 0) != float('inf') else "INF"
        bs_ = f"{bsk.get('sharpe', 0):+.2f}"
        if it == 0 and bt == 0:
            print(f"{label:<25} {'NO DATA':>11}")
        else:
            print(f"{label:<25} {it:>11} {iw:>8.1f}% {ipf:>8} {is_:>11} {bt:>11} {bw:>8.1f}% {bpf:>8} {bs_:>11}")

    print(f"{'='*120}")
