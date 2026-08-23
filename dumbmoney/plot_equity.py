"""Generate interactive HTML equity curve chart for the 3 winning walk-forward strategies."""

import os
import json
import pandas as pd
import numpy as np

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'walk_forward_results')
OUTPUT = os.path.join(RESULTS_DIR, 'equity_curves.html')
STARTING_CAPITAL = 100000

STRATEGIES = [
    ('ST_prob1', 'ST Prob (Pick 1)', '#2ecc71'),
    ('ST_prob5', 'ST Prob (Pick 5)', '#3498db'),
    ('ST_chg1',  'ST Chg% (Pick 1)', '#e74c3c'),
]


def build_equity_curve(label):
    """Build daily equity series from trade log CSV."""
    csv_path = os.path.join(RESULTS_DIR, '%s_trades.csv' % label)
    if not os.path.exists(csv_path):
        return None, None

    df = pd.read_sql if False else pd.read_csv(csv_path)
    if df.empty:
        return None, None

    # Group PnL by exit date (next_date) — that's when cash is realized
    daily_pnl = df.groupby('next_date')['pnl'].sum().sort_index()

    # Get all trading dates
    all_dates = sorted(set(df['date'].tolist() + df['next_date'].tolist()))

    # Build equity series
    equity = {}
    running = float(STARTING_CAPITAL)
    equity[all_dates[0]] = running

    pnl_by_exit = daily_pnl.to_dict()
    for d in all_dates:
        if d in pnl_by_exit:
            running += pnl_by_exit[d]
        equity[d] = round(running, 2)

    dates = sorted(equity.keys())
    values = [equity[d] for d in dates]
    return dates, values


def build_drawdown(dates, values):
    """Compute drawdown series."""
    dd = []
    peak = values[0]
    for v in values:
        if v > peak:
            peak = v
        dd.append(round((peak - v) / peak * 100, 2) if peak > 0 else 0)
    return dd


def generate_html():
    series_data = []
    dd_data = []

    for label, name, color in STRATEGIES:
        dates, values = build_equity_curve(label)
        if dates is None:
            continue
        dd = build_drawdown(dates, values)
        series_data.append({
            'name': name,
            'dates': dates,
            'values': values,
            'color': color,
            'final': values[-1],
            'return_pct': round((values[-1] - STARTING_CAPITAL) / STARTING_CAPITAL * 100, 2),
        })
        dd_data.append({
            'name': name,
            'dates': dates,
            'values': dd,
            'color': color,
        })

    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Walk-Forward Equity Curves</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         margin: 0; padding: 20px; background: #1a1a2e; color: #eee; }
  h1 { text-align: center; margin-bottom: 5px; }
  .subtitle { text-align: center; color: #888; margin-bottom: 20px; font-size: 14px; }
  .chart { width: 100%%; height: 500px; }
  .stats { display: flex; justify-content: center; gap: 30px; margin: 20px 0; flex-wrap: wrap; }
  .stat-card { background: #16213e; border-radius: 10px; padding: 15px 25px;
               text-align: center; min-width: 180px; border: 1px solid #333; }
  .stat-card .label { font-size: 12px; color: #888; margin-bottom: 4px; }
  .stat-card .value { font-size: 24px; font-weight: bold; }
  .stat-card .sub { font-size: 11px; color: #666; margin-top: 2px; }
  .green { color: #2ecc71; }
  .blue { color: #3498db; }
  .red { color: #e74c3c; }
</style>
</head>
<body>
<h1>Walk-Forward Backtest — Nifty 500 ST Cross-Up Strategies</h1>
<p class="subtitle">2 Years (Jul 2024 — Jul 2026) | $100,000 Starting Capital | Integer Shares Only | No Transaction Costs</p>

<div class="stats">
"""
    for s in series_data:
        cls = 'green' if s['return_pct'] > 50 else ('blue' if s['return_pct'] > 0 else 'red')
        html += f"""
  <div class="stat-card">
    <div class="label">{s['name']}</div>
    <div class="value {cls}">${s['final']:,.0f}</div>
    <div class="sub">{s['return_pct']:+.2f}% return</div>
  </div>"""

    html += """
</div>
<div id="equity" class="chart"></div>
<div id="drawdown" class="chart"></div>

<script>
"""

    # Equity curves
    html += "var equityTraces = [\n"
    for s in series_data:
        html += "  {x: %s, y: %s, name: '%s (%+.1f%%)', type: 'scatter', mode: 'lines',\n" % (
            json.dumps(s['dates']), json.dumps(s['values']),
            s['name'], s['return_pct'])
        html += "   line: {color: '%s', width: 2}},\n" % s['color']
    html += "];\n"

    # Baseline
    first_dates = series_data[0]['dates'] if series_data else []
    html += "equityTraces.push({x: %s, y: %s, name: 'Baseline $100K',\n" % (
        json.dumps(first_dates), json.dumps([100000] * len(first_dates)))
    html += "  line: {color: '#666', width: 1, dash: 'dash'}, mode: 'lines'});\n"

    # Drawdown curves
    html += "var ddTraces = [\n"
    for d in dd_data:
        html += "  {x: %s, y: %s, name: '%s', type: 'scatter', mode: 'lines',\n" % (
            json.dumps(d['dates']), json.dumps(d['values']), d['name'])
        html += "   line: {color: '%s', width: 1.5}, fill: 'tozeroy',\n" % d['color']
        html += "   fillcolor: '%s22'},\n" % d['color']
    html += "];\n"

    # Layouts
    html += """
var equityLayout = {
  title: {text: 'Equity Curves', font: {color: '#eee'}},
  paper_bgcolor: '#1a1a2e', plot_bgcolor: '#16213e',
  xaxis: {gridcolor: '#333', color: '#aaa'},
  yaxis: {title: 'Portfolio Value ($)', gridcolor: '#333', color: '#aaa',
          tickprefix: '$', tickformat: ',.0f'},
  legend: {bgcolor: '#16213e', bordercolor: '#333', font: {color: '#eee'}},
  margin: {t: 40, b: 40, l: 80, r: 20},
};

var ddLayout = {
  title: {text: 'Drawdown (%)', font: {color: '#eee'}},
  paper_bgcolor: '#1a1a2e', plot_bgcolor: '#16213e',
  xaxis: {gridcolor: '#333', color: '#aaa'},
  yaxis: {title: 'Drawdown %', gridcolor: '#333', color: '#aaa', autorange: 'reversed'},
  legend: {bgcolor: '#16213e', bordercolor: '#333', font: {color: '#eee'}},
  margin: {t: 40, b: 40, l: 80, r: 20},
};

Plotly.newPlot('equity', equityTraces, equityLayout, {responsive: true});
Plotly.newPlot('drawdown', ddTraces, ddLayout, {responsive: true});
</script>
</body>
</html>"""

    with open(OUTPUT, 'w') as f:
        f.write(html)
    print("Saved: %s" % OUTPUT)


if __name__ == '__main__':
    generate_html()
