"""Trace the specific events that produced the DB scores for top stocks."""
import sqlite3
import pandas as pd
import numpy as np
import json
import os
import sys

sys.path.insert(0, r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')

from dumbmoney.retest_engine import (
    fold_symbol, load_model, get_model, make_score_fn
)
import dumbmoney.retest_config as cfg

DB_PATH = r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db'
OUTPUT_DIR = r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\RETEST_PHASE0_AUDIT'

os.makedirs(OUTPUT_DIR, exist_ok=True)

load_model()
model = get_model()

# Top 5 symbols with their DB scores
TOP_SYMBOLS = [
    ('SONO', 66.38),
    ('GLBE', 57.82),
    ('SCI', 47.5),
    ('LILA', 43.3),
    ('SOLV', 43.0),
]

def trace_event_for_db_score(sym, db_score):
    """Find which event produced the DB score and why it wasn't cleared."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT date, open, high, low, close, volume FROM bars "
        "WHERE timeframe='1Day' AND symbol=? ORDER BY date",
        conn, params=(sym,)
    )
    conn.close()
    
    dates = df['date'].astype(str).tolist()
    o = df['open'].astype(float).values
    h = df['high'].astype(float).values
    l = df['low'].astype(float).values
    close = df['close'].astype(float).values
    v = df['volume'].astype(float).values
    
    score_fn = make_score_fn(model)
    result = fold_symbol(h, l, close, o, v, dates, "US", sym, score_fn=score_fn)
    
    # Find events matching the DB score
    matching = []
    for ev in result.events:
        if ev.original_score is not None and abs(ev.original_score - db_score) < 1.0:
            matching.append({
                'event_id': ev.event_id,
                'stage': ev.stage,
                'breakout_date': ev.breakout_date,
                'confirm_date': ev.confirm_date,
                'original_score': ev.original_score,
                'outcome': ev.outcome,
                'reason': ev.reason,
                'entry': float(ev.entry) if not np.isnan(ev.entry) else None,
                'signal_atr': float(ev.signal_atr) if not np.isnan(ev.signal_atr) else None,
                'breakout_level': float(ev.breakout_level) if not np.isnan(ev.breakout_level) else None,
                'breakout_idx': ev.breakout_idx,
                'confirm_idx': ev.confirm_idx,
                'resolution_idx': ev.resolution_idx,
            })
    
    # Also check: which index in current_scores matches the DB score?
    scores = result.current_scores
    score_indices = []
    for i, s in enumerate(scores):
        if s is not None and not np.isnan(s) and abs(float(s) - db_score) < 1.0:
            score_indices.append({
                'idx': i,
                'date': dates[i] if i < len(dates) else None,
                'score': float(s),
                'state': result.states[i],
            })
    
    return {
        'symbol': sym,
        'db_score': db_score,
        'matching_events': matching,
        'score_indices': score_indices,
        'total_events': len(result.events),
        'latest_state': result.states[-1],
        'latest_score': float(scores[-1]) if not np.isnan(scores[-1]) else None,
    }

# Trace all top 5
all_traces = []
for sym, db_score in TOP_SYMBOLS:
    print(f"\n=== Tracing {sym} (DB score={db_score}) ===")
    trace = trace_event_for_db_score(sym, db_score)
    all_traces.append(trace)
    
    print(f"  Matching events: {len(trace['matching_events'])}")
    for ev in trace['matching_events']:
        print(f"    {ev['event_id']}: stage={ev['stage']}, breakout={ev['breakout_date']}, confirm={ev['confirm_date']}, score={ev['original_score']:.2f}, outcome={ev['outcome']}")
    
    print(f"  Score indices in series: {len(trace['score_indices'])}")
    for si in trace['score_indices'][-5:]:
        print(f"    idx={si['idx']}, date={si['date']}, score={si['score']:.2f}, state={si['state']}")
    
    print(f"  Latest: state={trace['latest_state']}, score={trace['latest_score']}")

# Save
with open(os.path.join(OUTPUT_DIR, 'event_score_traces.json'), 'w') as f:
    json.dump(all_traces, f, indent=2, default=str)

print(f"\nTraces saved to {OUTPUT_DIR}/event_score_traces.json")
