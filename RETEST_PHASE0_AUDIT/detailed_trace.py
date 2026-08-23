"""Phase 0: Detailed trace to understand stale scores and event states."""
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

load_model()
model = get_model()

# Get top 15 scores from DB
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("""
    SELECT symbol, old_swing_retest_score 
    FROM stats 
    WHERE old_swing_retest_score > 0 
    ORDER BY old_swing_retest_score DESC 
    LIMIT 15
""")
top_scores = c.fetchall()
conn.close()

print(f"Top {len(top_scores)} scores from DB:")
for sym, score in top_scores:
    print(f"  {sym}: {score}")

def detailed_trace(sym):
    """Detailed trace for one symbol."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT date, open, high, low, close, volume FROM bars "
        "WHERE timeframe='1Day' AND symbol=? ORDER BY date",
        conn, params=(sym,)
    )
    c = conn.cursor()
    c.execute("SELECT old_swing_retest_score, last_updated FROM stats WHERE symbol=?", (sym,))
    stats_row = c.fetchone()
    conn.close()
    
    db_score = stats_row[0] if stats_row else None
    db_updated = stats_row[1] if stats_row else None
    
    dates = df['date'].astype(str).tolist()
    o = df['open'].astype(float).values
    h = df['high'].astype(float).values
    l = df['low'].astype(float).values
    close = df['close'].astype(float).values
    v = df['volume'].astype(float).values
    
    score_fn = make_score_fn(model)
    result = fold_symbol(h, l, close, o, v, dates, "US", sym, score_fn=score_fn)
    
    # Find the event that produced the DB score
    # The DB score is the LAST non-null score in the series
    scores = result.current_scores
    latest_non_null_idx = -1
    latest_non_null_score = None
    for i in range(len(scores) - 1, -1, -1):
        if not np.isnan(scores[i]):
            latest_non_null_idx = i
            latest_non_null_score = scores[i]
            break
    
    # Find all events and their latest state
    events_info = []
    for ev in result.events:
        evt = {
            'event_id': ev.event_id,
            'stage': ev.stage,
            'breakout_date': ev.breakout_date,
            'confirm_date': ev.confirm_date,
            'original_score': ev.original_score,
            'resolution_date': ev.resolution_date,
            'outcome': ev.outcome,
            'reason': ev.reason,
        }
        events_info.append(evt)
    
    # Find the event that matches the DB score
    matching_event = None
    if db_score is not None and db_score > 0:
        for ev in result.events:
            if ev.original_score is not None and abs(ev.original_score - db_score) < 0.5:
                matching_event = ev
                break
    
    trace = {
        'symbol': sym,
        'db_score': db_score,
        'db_updated': db_updated,
        'latest_non_null_score': float(latest_non_null_score) if latest_non_null_score else None,
        'latest_non_null_idx': latest_non_null_idx,
        'latest_state': result.states[-1],
        'n_events': len(result.events),
        'n_zones': len(result.zones),
        'matching_event_id': matching_event.event_id if matching_event else None,
        'matching_event_stage': matching_event.stage if matching_event else None,
        'matching_event_score': matching_event.original_score if matching_event else None,
        'events': events_info[-5:],  # Last 5 events
        'recent_state': result.states[-10:],
        'recent_scores': [float(x) if not np.isnan(x) else None for x in scores[-10:]],
    }
    
    return trace

# Trace top 15
all_traces = []
for sym, score in top_scores:
    print(f"\n=== Detailed trace: {sym} (DB score={score}) ===")
    trace = detailed_trace(sym)
    all_traces.append(trace)
    print(f"  Latest score: {trace['latest_non_null_score']}")
    print(f"  Latest state: {trace['latest_state']}")
    print(f"  Matching event: {trace['matching_event_id']} (stage={trace['matching_event_stage']}, score={trace['matching_event_score']})")
    print(f"  Recent states: {trace['recent_state']}")
    print(f"  Recent scores: {trace['recent_scores']}")

# Save
with open(os.path.join(OUTPUT_DIR, 'detailed_traces.json'), 'w') as f:
    json.dump(all_traces, f, indent=2, default=str)

print(f"\nDetailed traces saved to {OUTPUT_DIR}/detailed_traces.json")

# Also check: how many symbols have stale scores?
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("""
    SELECT COUNT(*) FROM stats s
    WHERE s.old_swing_retest_score > 0
    AND NOT EXISTS (
        SELECT 1 FROM (
            SELECT current_scores[t] as score, states[t] as state
            FROM (SELECT * FROM stats WHERE old_swing_retest_score > 0)
        ) sub
        WHERE sub.score IS NOT NULL AND sub.state = 'SIGNAL_GENERATED'
    )
""")
# This query is complex; let's do it differently
c.execute("SELECT COUNT(*) FROM stats WHERE old_swing_retest_score > 0")
total_with_score = c.fetchone()[0]
print(f"\nTotal symbols with DB score > 0: {total_with_score}")

# Check how many have NULL in current fold
conn.close()
