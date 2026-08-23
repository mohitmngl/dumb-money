"""Phase 0 Read-Only Reconciliation: Compare DB scores vs current engine scores."""
import sqlite3
import pandas as pd
import numpy as np
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')

from dumbmoney.retest_engine import (
    fold_symbol, load_model, get_model, make_score_fn
)
import dumbmoney.retest_config as cfg

DB_PATH = r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db'
OUTPUT_DIR = r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\RETEST_PHASE0_AUDIT'

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load model
load_model()
model = get_model()
print(f"Model loaded: {model.tree_count_} trees")

# Get all non-null scores
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("""
    SELECT symbol, old_swing_retest_score, last_updated 
    FROM stats 
    WHERE old_swing_retest_score IS NOT NULL AND old_swing_retest_score > 0
    ORDER BY old_swing_retest_score DESC
""")
rows = c.fetchall()
conn.close()

print(f"Total symbols with non-null DB score: {len(rows)}")

# Classify each symbol
results = []
classification_counts = {
    'MATCH': 0,
    'STALE_DB_SCORE': 0,
    'MISSING_DB_SCORE': 0,
    'VALUE_MISMATCH': 0,
    'MODEL_UNAVAILABLE': 0,
    'DATA_INSUFFICIENT': 0,
    'COMPUTATION_ERROR': 0,
}

for sym, db_score, db_updated in rows:
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql(
            "SELECT date, open, high, low, close, volume FROM bars "
            "WHERE timeframe='1Day' AND symbol=? ORDER BY date",
            conn, params=(sym,)
        )
        conn.close()
        
        if len(df) < 60:
            classification = 'DATA_INSUFFICIENT'
            classification_counts[classification] += 1
            results.append({
                'symbol': sym,
                'db_score': db_score,
                'db_updated': db_updated,
                'engine_score': None,
                'engine_state': None,
                'classification': classification,
                'n_bars': len(df),
            })
            continue
        
        dates = df['date'].astype(str).tolist()
        o = df['open'].astype(float).values
        h = df['high'].astype(float).values
        l = df['low'].astype(float).values
        close = df['close'].astype(float).values
        v = df['volume'].astype(float).values
        
        score_fn = make_score_fn(model)
        result = fold_symbol(h, l, close, o, v, dates, "US", sym, score_fn=score_fn)
        
        # Find latest non-null score and its state
        scores = result.current_scores
        latest_non_null_idx = -1
        latest_non_null_score = None
        latest_state = None
        latest_event_id = None
        
        for i in range(len(scores) - 1, -1, -1):
            if not np.isnan(scores[i]):
                latest_non_null_idx = i
                latest_non_null_score = scores[i]
                latest_state = result.states[i]
                # Find matching event
                for ev in result.events:
                    if ev.confirm_idx == i or (ev.signal_date and ev.signal_date == dates[i]):
                        latest_event_id = ev.event_id
                        break
                break
        
        # Check if DB score matches latest engine score
        if latest_non_null_score is None:
            # Engine says NULL, DB has value
            if db_score is not None:
                # Check if there's an older matching score
                matching_events = [ev for ev in result.events 
                                  if ev.original_score is not None 
                                  and abs(ev.original_score - db_score) < 1.0]
                if matching_events:
                    classification = 'STALE_DB_SCORE'
                else:
                    classification = 'MISSING_DB_SCORE'
            else:
                classification = 'MISSING_DB_SCORE'
        else:
            engine_score = float(latest_non_null_score)
            if abs(engine_score - db_score) < 0.5:
                classification = 'MATCH'
            else:
                classification = 'VALUE_MISMATCH'
        
        classification_counts[classification] += 1
        
        # Get event details
        events_info = []
        for ev in result.events[-3:]:  # Last 3 events
            events_info.append({
                'event_id': ev.event_id,
                'stage': ev.stage,
                'breakout_date': ev.breakout_date,
                'confirm_date': ev.confirm_date,
                'original_score': ev.original_score,
                'outcome': ev.outcome,
            })
        
        results.append({
            'symbol': sym,
            'db_score': db_score,
            'db_updated': db_updated,
            'engine_score': float(latest_non_null_score) if latest_non_null_score else None,
            'engine_state': latest_state,
            'engine_event_id': latest_event_id,
            'n_bars': len(df),
            'classification': classification,
            'recent_events': events_info,
        })
        
    except Exception as e:
        classification = 'COMPUTATION_ERROR'
        classification_counts[classification] += 1
        results.append({
            'symbol': sym,
            'db_score': db_score,
            'db_updated': db_updated,
            'engine_score': None,
            'engine_state': None,
            'classification': classification,
            'error': str(e),
        })

# Save reconciliation
output_path = os.path.join(OUTPUT_DIR, 'RETEST_CURRENT_SCORE_RECONCILIATION.csv')
df_results = pd.DataFrame(results)
df_results.to_csv(output_path, index=False)
print(f"\nReconciliation saved to {output_path}")

# Print summary
print("\n=== CLASSIFICATION SUMMARY ===")
for cls, count in sorted(classification_counts.items(), key=lambda x: -x[1]):
    print(f"  {cls}: {count}")

print(f"\nTotal: {len(results)}")

# Save detailed JSON
json_path = os.path.join(OUTPUT_DIR, 'RETEST_RECONCILIATION_DETAILED.json')
with open(json_path, 'w') as f:
    json.dump({
        'classification_counts': classification_counts,
        'total': len(results),
        'timestamp': datetime.utcnow().isoformat(),
        'results': results,
    }, f, indent=2, default=str)

print(f"Detailed results saved to {json_path}")
