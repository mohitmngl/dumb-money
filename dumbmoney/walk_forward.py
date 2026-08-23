"""
Walk-Forward Backtest: 4 ST Cross-Up Strategies on Nifty 500
=============================================================
Strategies:
  1. ST_chg1  - ST cross up, sort by change_pct desc, pick top 1
  2. ST_prob1 - ST cross up, sort by prob_up_st_cross desc, pick top 1
  3. ST_chg5  - ST cross up, sort by change_pct desc, pick top 5
  4. ST_prob5 - ST cross up, sort by prob_up_st_cross desc, pick top 5

Rules:
  - Buy at close on signal day, sell at close next trading day
  - Integer shares only (floor), no fractional
  - Stay in cash when no signal
  - $100,000 starting capital
"""

import sys
import os
import time
import json
import math
from datetime import datetime

import sqlite3
import pandas as pd
import numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'india.db')
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'walk_forward_results')


def load_data(start_date, end_date, stock_limit=None):
    """Load Nifty 500 hist_screener + bars close for walk-forward.

    Returns:
        signals_df: DataFrame with columns [symbol, date, change_pct, prob_up_st_cross]
                    Only rows where atr_crossed_above=1
        close_pivot: DataFrame index=date, columns=symbol, values=close
        trading_dates: sorted list of unique dates in range
        nifty500_syms: set of Nifty 500 symbols
    """
    conn = sqlite3.connect(DB_PATH)

    # Nifty 500 symbols
    n500 = pd.read_sql(
        "SELECT symbol FROM nifty500_constituents WHERE ? >= from_date AND ? <= to_date",
        conn, params=[start_date, end_date]
    )
    nifty500_syms = set(n500['symbol'].tolist())
    print("  Nifty 500 symbols in range: %d" % len(nifty500_syms))

    if stock_limit:
        nifty500_syms = set(sorted(nifty500_syms)[:stock_limit])
        print("  Limited to %d stocks for smoke test" % len(nifty500_syms))

    # Signal data: ST cross-up events
    placeholders = ','.join('?' * len(nifty500_syms))
    signals_df = pd.read_sql(
        """SELECT symbol, date, price, change_pct, prob_up_st_cross, next_day_return
           FROM historical_screener
           WHERE atr_crossed_above = 1
             AND date >= ? AND date <= ?
             AND symbol IN ({})""".format(placeholders),
        conn, params=[start_date, end_date] + sorted(nifty500_syms)
    )
    print("  Signal events (ST cross-up): %d" % len(signals_df))

    # Close prices for all Nifty 500 stocks
    bars_df = pd.read_sql(
        """SELECT symbol, date, close FROM bars
           WHERE timeframe='1Day' AND date >= ? AND date <= ?
             AND symbol IN ({})""".format(placeholders),
        conn, params=[start_date, end_date] + sorted(nifty500_syms)
    )
    conn.close()

    # Build close pivot
    close_pivot = bars_df.pivot_table(index='date', columns='symbol', values='close')
    close_pivot = close_pivot.sort_index()
    trading_dates = close_pivot.index.tolist()

    # Filter signals to only dates in our trading range
    signals_df = signals_df[signals_df['date'].isin(close_pivot.index)]
    print("  Trading dates: %d" % len(trading_dates))
    print("  Close pivot shape: %s" % str(close_pivot.shape))

    return signals_df, close_pivot, trading_dates, nifty500_syms


def run_walkforward(signals_df, close_pivot, trading_dates, top_n, sort_col, label,
                    capital=100000):
    """Run a single walk-forward strategy.

    Args:
        signals_df: ST cross-up events [symbol, date, change_pct, prob_up_st_cross]
        close_pivot: index=date, columns=symbol, values=close
        trading_dates: sorted list of dates
        top_n: number of stocks to pick (1 or 5)
        sort_col: column to sort by ('change_pct' or 'prob_up_st_cross')
        label: strategy name for output
        capital: starting capital

    Returns:
        dict with stats + trades list
    """
    date_to_idx = {d: i for i, d in enumerate(trading_dates)}
    signals_by_date = signals_df.groupby('date')

    equity = float(capital)
    peak_equity = equity
    max_dd = 0.0
    trades = []
    daily_returns = []

    for i, date in enumerate(trading_dates[:-1]):
        day_pnl = 0.0

        if date in signals_by_date.groups:
            day_signals = signals_by_date.get_group(date).copy()
            day_signals = day_signals.sort_values(sort_col, ascending=False)
            picks = day_signals.head(top_n)

            for _, row in picks.iterrows():
                sym = row['symbol']
                entry_price = close_pivot.at[date, sym] if sym in close_pivot.columns else np.nan

                next_date = trading_dates[i + 1]
                exit_price = close_pivot.at[next_date, sym] if sym in close_pivot.columns else np.nan

                if pd.isna(entry_price) or pd.isna(exit_price) or entry_price <= 0:
                    continue

                alloc = equity / top_n
                shares = int(math.floor(alloc / entry_price))
                if shares <= 0:
                    continue

                pnl = shares * (exit_price - entry_price)
                day_pnl += pnl

                trades.append({
                    'date': date,
                    'next_date': next_date,
                    'symbol': sym,
                    'entry_price': round(entry_price, 2),
                    'exit_price': round(exit_price, 2),
                    'shares': shares,
                    'pnl': round(pnl, 2),
                    'sort_val': round(float(row[sort_col]), 4),
                })

        equity += day_pnl
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
        if dd > max_dd:
            max_dd = dd

        if equity > 0:
            daily_returns.append(day_pnl / (equity - day_pnl) if (equity - day_pnl) > 0 else 0)
        else:
            daily_returns.append(0)

    # Stats
    total_return = (equity - capital) / capital * 100
    n_years = len(trading_dates) / 252.0
    cagr = ((equity / capital) ** (1 / n_years) - 1) * 100 if n_years > 0 and equity > 0 else 0

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0

    avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
    avg_loss = np.mean([abs(t['pnl']) for t in losses]) if losses else 0
    profit_factor = (sum(t['pnl'] for t in wins) / sum(abs(t['pnl']) for t in losses)
                     if losses and sum(abs(t['pnl']) for t in losses) > 0 else float('inf'))

    dr = np.array(daily_returns)
    sharpe = (np.mean(dr) / np.std(dr) * np.sqrt(252)) if np.std(dr) > 0 else 0

    result = {
        'label': label,
        'start_capital': capital,
        'final_capital': round(equity, 2),
        'total_return_pct': round(total_return, 2),
        'cagr_pct': round(cagr, 2),
        'max_drawdown_pct': round(max_dd * 100, 2),
        'total_trades': len(trades),
        'win_rate_pct': round(win_rate, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'profit_factor': round(profit_factor, 2),
        'sharpe': round(sharpe, 2),
        'trades': trades,
    }
    return result


def print_stats(r):
    """Print strategy stats."""
    print("  Starting Capital: $%s" % f"{r['start_capital']:,.0f}")
    print("  Final Capital:    $%s" % f"{r['final_capital']:,.0f}")
    print("  Total Return:     %.2f%%" % r['total_return_pct'])
    print("  CAGR:             %.2f%%" % r['cagr_pct'])
    print("  Max Drawdown:     %.2f%%" % r['max_drawdown_pct'])
    print("  Sharpe Ratio:     %.2f" % r['sharpe'])
    print("  Total Trades:     %d" % r['total_trades'])
    print("  Win Rate:         %.2f%%" % r['win_rate_pct'])
    print("  Avg Win:          $%s" % f"{r['avg_win']:,.2f}")
    print("  Avg Loss:         $%s" % f"{r['avg_loss']:,.2f}")
    print("  Profit Factor:    %.2f" % r['profit_factor'])


def run_smoke_test():
    """Smoke test: 3 months, 10 stocks, verify logic."""
    print("=" * 70)
    print("SMOKE TEST: 3 months, 10 Nifty 500 stocks")
    print("=" * 70)

    start = '2026-04-28'
    end = '2026-07-28'
    signals_df, close_pivot, trading_dates, syms = load_data(start, end, stock_limit=10)

    assert len(trading_dates) > 10, "Need at least 10 trading dates, got %d" % len(trading_dates)
    assert len(signals_df) > 0, "No signals found in smoke test period"

    # Show sample signals
    print("\n  Sample signals:")
    for _, row in signals_df.head(5).iterrows():
        print("    %s %s: chg=%.2f%%, prob_st=%.2f" % (
            row['symbol'], row['date'], row['change_pct'], row['prob_up_st_cross']))

    strategies = [
        ('ST_chg1', 1, 'change_pct'),
        ('ST_prob1', 1, 'prob_up_st_cross'),
        ('ST_chg5', 5, 'change_pct'),
        ('ST_prob5', 5, 'prob_up_st_cross'),
    ]

    results = []
    for label, top_n, sort_col in strategies:
        print("\n--- %s ---" % label)
        r = run_walkforward(signals_df, close_pivot, trading_dates, top_n, sort_col, label)
        print_stats(r)
        results.append(r)

        # Validate trades
        for t in r['trades']:
            assert t['shares'] > 0, "Shares must be > 0"
            assert isinstance(t['shares'], int), "Shares must be int"
            expected_pnl = t['shares'] * (t['exit_price'] - t['entry_price'])
            assert abs(t['pnl'] - round(expected_pnl, 2)) < 0.02, \
                "PnL mismatch: %f vs %f" % (t['pnl'], expected_pnl)
            assert t['symbol'] in syms, "Symbol %s not in universe" % t['symbol']

        if r['trades']:
            print("\n  First 5 trades:")
            for t in r['trades'][:5]:
                print("    %s %s: %d shares @ %.2f -> %.2f, PnL=$%.2f" % (
                    t['symbol'], t['date'], t['shares'], t['entry_price'],
                    t['exit_price'], t['pnl']))
            print("  Last 3 trades:")
            for t in r['trades'][-3:]:
                print("    %s %s: %d shares @ %.2f -> %.2f, PnL=$%.2f" % (
                    t['symbol'], t['date'], t['shares'], t['entry_price'],
                    t['exit_price'], t['pnl']))

    print("\n" + "=" * 70)
    print("SMOKE TEST PASSED - All assertions OK")
    print("=" * 70)
    return results


def run_full():
    """Full walk-forward: 2 years, all Nifty 500 stocks."""
    print("=" * 70)
    print("FULL WALK-FORWARD: 2 years, all Nifty 500 stocks")
    print("=" * 70)

    start = '2024-07-28'
    end = '2026-07-28'
    signals_df, close_pivot, trading_dates, syms = load_data(start, end)

    strategies = [
        ('ST_chg1', 1, 'change_pct'),
        ('ST_prob1', 1, 'prob_up_st_cross'),
        ('ST_chg5', 5, 'change_pct'),
        ('ST_prob5', 5, 'prob_up_st_cross'),
    ]

    results = []
    for label, top_n, sort_col in strategies:
        print("\n--- %s ---" % label)
        t0 = time.time()
        r = run_walkforward(signals_df, close_pivot, trading_dates, top_n, sort_col, label)
        elapsed = time.time() - t0
        print_stats(r)
        print("  Compute time: %.1fs" % elapsed)
        results.append(r)

    # Save trade logs
    os.makedirs(RESULTS_DIR, exist_ok=True)
    for r in results:
        trades_df = pd.DataFrame(r['trades'])
        csv_path = os.path.join(RESULTS_DIR, '%s_trades.csv' % r['label'])
        trades_df.to_csv(csv_path, index=False)
        print("\nSaved %s" % csv_path)

    # Comparison table
    print("\n" + "=" * 90)
    print("COMPARISON TABLE")
    print("=" * 90)
    header = "%-12s %12s %10s %10s %10s %8s %8s %8s %10s" % (
        "Strategy", "Final Cap", "Return%", "CAGR%", "MaxDD%", "Trades", "WinR%", "Sharpe", "ProfFact")
    print(header)
    print("-" * 90)
    for r in results:
        print("%-12s %12s %10.2f %10.2f %10.2f %8d %8.2f %8.2f %10.2f" % (
            r['label'],
            "$%s" % f"{r['final_capital']:,.0f}",
            r['total_return_pct'],
            r['cagr_pct'],
            r['max_drawdown_pct'],
            r['total_trades'],
            r['win_rate_pct'],
            r['sharpe'],
            r['profit_factor']))
    print("=" * 90)

    # Save summary JSON
    summary = []
    for r in results:
        s = {k: v for k, v in r.items() if k != 'trades'}
        summary.append(s)
    json_path = os.path.join(RESULTS_DIR, 'summary.json')
    with open(json_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print("\nSaved summary: %s" % json_path)

    return results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Walk-Forward Backtest')
    parser.add_argument('--smoke', action='store_true', help='Run smoke test only')
    parser.add_argument('--full', action='store_true', help='Run full walk-forward')
    args = parser.parse_args()

    if args.smoke:
        run_smoke_test()
    elif args.full:
        run_full()
    else:
        # Default: smoke test first, then full
        run_smoke_test()
        print("\n\n")
        run_full()
