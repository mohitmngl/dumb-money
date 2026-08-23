"""Phase 0: Read-only audit of top-scoring symbols to trace actual events."""
import sqlite3
import pandas as pd
import numpy as np
import json
import os
import sys

sys.path.insert(0, r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')

from dumbmoney.retest_engine import (
    fold_symbol, compute_retest_score_for_symbol, load_model, get_model,
    _event_to_feature_array, make_score_fn
)
import dumbmoney.retest_config as cfg

DB_PATH = r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db'
OUTPUT_DIR = r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\RETEST_PHASE0_AUDIT'

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load model
load_model()
model = get_model()
print(f"Model loaded: {model.tree_count_} trees")

# Top 5 stocks from current scores
TOP_SYMBOLS = ['SONO', 'GLBE', 'SCI', 'LILA', 'SOLV']

def trace_symbol(sym):
    """Trace the actual event for a symbol."""
    conn = sqlite3.connect(DB_PATH)
    
    # Get bars
    df = pd.read_sql(
        "SELECT date, open, high, low, close, volume FROM bars "
        "WHERE timeframe='1Day' AND symbol=? ORDER BY date",
        conn, params=(sym,)
    )
    conn.close()
    
    if len(df) < 100:
        return None
    
    dates = df['date'].astype(str).tolist()
    o = df['open'].astype(float).values
    h = df['high'].astype(float).values
    l = df['low'].astype(float).values
    c = df['close'].astype(float).values
    v = df['volume'].astype(float).values
    
    # Run fold with model
    score_fn = make_score_fn(model)
    result = fold_symbol(h, l, c, o, v, dates, "US", sym, score_fn=score_fn)
    
    # Get current score from DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT old_swing_retest_score FROM stats WHERE symbol=?", (sym,))
    db_score = c.fetchone()[0]
    conn.close()
    
    # Find the active event
    events = [e for e in result.events if e.confirm_idx >= 0 and e.signal_date]
    
    trace = {
        'symbol': sym,
        'total_bars': len(df),
        'db_score': db_score,
        'latest_score': float(result.current_scores[-1]) if len(result.current_scores) > 0 and not np.isnan(result.current_scores[-1]) else None,
        'latest_state': result.states[-1],
        'n_events': len(events),
        'n_zones': len(result.zones),
        'events': []
    }
    
    for ev in events:
        evt_trace = {
            'event_id': ev.event_id,
            'stage': ev.stage,
            'outocome': ev.outcome,
            'breakout_idx': ev.breakout_idx,
            'breakout_date': ev.breakout_date,
            'breakout_close': float(ev.breakout_close) if not np.isnan(ev.breakout_close) else None,
            'breakout_level': float(ev.breakout_level) if not np.isnan(ev.breakout_level) else None,
            'breakout_atr': float(ev.breakout_atr) if not np.isnan(ev.breakout_atr) else None,
            'confirm_idx': ev.confirm_idx,
            'confirm_date': ev.confirm_date,
            'confirm_close': float(ev.entry) if not np.isnan(ev.entry) else None,
            'signal_atr': float(ev.signal_atr) if not np.isnan(ev.signal_atr) else None,
            'original_score': ev.original_score,
            'zone_id': ev.zone_id,
            'reason': ev.reason,
        }
        
        # Get zone info
        for z in result.zones:
            if z.id == ev.zone_id:
                evt_trace['zone_level'] = float(z.level)
                evt_trace['zone_age_at_breakout'] = z.age(ev.breakout_idx)
                evt_trace['zone_pivots'] = [
                    {'idx': p.idx, 'date': p.date, 'price': float(p.price), 'prominence': float(p.prominence_atr) if p.prominence_atr else None}
                    for p in z.members
                ]
                break
        
        trace['events'].append(evt_trace)
    
    # Get recent bars for context
    trace['recent_bars'] = df.tail(30).to_dict('records')
    
    return trace

# Trace all top symbols
all_traces = []
for sym in TOP_SYMBOLS:
    print(f"\n=== Tracing {sym} ===")
    trace = trace_symbol(sym)
    if trace:
        all_traces.append(trace)
        print(f"  DB score: {trace['db_score']}")
        print(f"  Latest score: {trace['latest_score']}")
        print(f"  Latest state: {trace['latest_state']}")
        print(f"  Events: {trace['n_events']}")
        for ev in trace['events']:
            print(f"    Event {ev['event_id']}: stage={ev['stage']}, breakout={ev['breakout_date']}, confirm={ev['confirm_date']}, score={ev['original_score']}")

# Also trace one AAPL event if found
print("\n=== Tracing AAPL for positive reference ===")
trace = trace_symbol('AAPL')
if trace and trace['events']:
    all_traces.append(trace)
    print(f"  DB score: {trace['db_score']}")
    print(f"  Events: {trace['n_events']}")
    for ev in trace['events']:
        print(f"    Event {ev['event_id']}: stage={ev['stage']}, breakout={ev['breakout_date']}, confirm={ev['confirm_date']}, score={ev['original_score']}")

# Save traces
with open(os.path.join(OUTPUT_DIR, 'event_traces.json'), 'w') as f:
    json.dump(all_traces, f, indent=2, default=str)

print(f"\nTraces saved to {OUTPUT_DIR}/event_traces.json")
