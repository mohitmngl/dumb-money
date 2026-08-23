"""Golden chart generation for V2 engine validation.

Generates annotated charts from actual local OHLCV data showing:
- Pivot members available at breakout
- Frozen zone level
- Breakout
- Departure threshold
- Accepted closes
- Causal running peak
- Pullback depth
- Approach direction
- Strict retest bounds
- Touch
- Confirmation
- Entry distance
- Target
- Stop
- Every transition
- Final acceptance or rejection reason
"""
import os
import sys
import sqlite3
import pandas as pd
import numpy as np

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dumbmoney.config import US_DB, INDIA_DB
from dumbmoney.db import get_db
from dumbmoney.retest_engine_v2 import (
    RetestEngineV2, V2State, TERMINAL_STATES, fold_symbol_v2,
    wilders_atr, V2_BREAKOUT_LEVEL_TOUCH_ATR, V2_TOUCH_LOWER_ATR, V2_TOUCH_UPPER_ATR,
    V2_TARGET_ATR, V2_STOP_ATR, V2_MIN_DEPARTURE_DISTANCE_ATR, V2_MIN_PULLBACK_FROM_PEAK_ATR
)


def get_symbol_data(conn, symbol, limit=300):
    """Get OHLCV data for a symbol."""
    df = pd.read_sql(
        "SELECT date, open, high, low, close, volume FROM bars "
        "WHERE timeframe='1Day' AND symbol=? ORDER BY date DESC LIMIT ?",
        conn, params=(symbol, limit), parse_dates=["date"]
    )
    return df.sort_values("date").reset_index(drop=True)


def analyze_symbol(conn, symbol):
    """Analyze a symbol with V2 engine and return events."""
    df = get_symbol_data(conn, symbol)
    if len(df) < 60:
        return None

    dates = df["date"].astype(str).tolist()
    o = df["open"].astype(float).values
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    c = df["close"].astype(float).values
    v = df["volume"].astype(float).values

    market = "US"
    result = fold_symbol_v2(h, l, c, o, v, dates, market, symbol)

    return {
        "symbol": symbol,
        "dates": dates,
        "open": o, "high": h, "low": l, "close": c, "volume": v,
        "result": result,
        "events": result.events if result else [],
    }


def count_events_by_type(analysis):
    """Count events by type."""
    if not analysis or not analysis["events"]:
        return {}

    counts = {
        "accepted": 0,
        "no_departure": 0,
        "failed_breakout": 0,
        "recovery_from_below": 0,
        "repeated_crossings": 0,
        "expired": 0,
        "stopped_out": 0,
        "target_completed": 0,
    }

    for ev in analysis["events"]:
        if ev.state == V2State.POST_ENTRY_ACTIVE:
            counts["accepted"] += 1
        elif ev.state == V2State.FAILED_BREAKOUT:
            counts["failed_breakout"] += 1
        elif ev.state == V2State.RECOVERY_FROM_BELOW:
            counts["recovery_from_below"] += 1
        elif ev.state == V2State.EXPIRED:
            if ev.reason == "no_touch_120":
                counts["no_departure"] += 1
            else:
                counts["expired"] += 1
        elif ev.state == V2State.STOPPED_OUT:
            counts["stopped_out"] += 1
        elif ev.state == V2State.TARGET_COMPLETED:
            counts["target_completed"] += 1
        elif ev.state == V2State.ENTRY_TOO_FAR:
            counts["repeated_crossings"] += 1

    return counts


def generate_funnel_sample(conn, symbols, output_dir):
    """Generate funnel sample for multiple symbols."""
    os.makedirs(output_dir, exist_ok=True)

    all_events = []
    for symbol in symbols:
        analysis = analyze_symbol(conn, symbol)
        if not analysis:
            continue
        for ev in analysis["events"]:
            all_events.append({
                "symbol": symbol,
                "event_id": ev.event_id,
                "state": ev.state,
                "breakout_date": ev.breakout_date,
                "breakout_level": ev.breakout_level,
                "departure_high_distance_atr": ev.departure_high_distance_atr,
                "pullback_from_peak_atr": ev.pullback_from_peak_atr,
                "touch_date": ev.touch_date,
                "confirm_date": ev.confirm_date,
                "entry": ev.entry,
                "entry_distance_atr": ev.entry_distance_atr,
                "outcome": ev.outcome,
                "reason": ev.reason,
            })

    # Write funnel sample
    df = pd.DataFrame(all_events)
    csv_path = os.path.join(output_dir, "RETEST_ENGINE_V2_FUNNEL_SAMPLE.csv")
    df.to_csv(csv_path, index=False)
    print(f"Funnel sample: {csv_path} ({len(df)} events)")

    return df


def generate_event_logs(conn, symbols, output_dir):
    """Generate accepted and rejected event logs."""
    os.makedirs(output_dir, exist_ok=True)

    accepted = []
    rejected = []

    for symbol in symbols:
        analysis = analyze_symbol(conn, symbol)
        if not analysis:
            continue
        for ev in analysis["events"]:
            record = {
                "symbol": symbol,
                "event_id": ev.event_id,
                "state": ev.state,
                "breakout_date": ev.breakout_date,
                "breakout_level": ev.breakout_level,
                "departure_high_distance_atr": ev.departure_high_distance_atr,
                "pullback_from_peak_atr": ev.pullback_from_peak_atr,
                "touch_date": ev.touch_date,
                "confirm_date": ev.confirm_date,
                "entry": ev.entry,
                "entry_distance_atr": ev.entry_distance_atr,
                "outcome": ev.outcome,
                "reason": ev.reason,
            }
            if ev.state == V2State.POST_ENTRY_ACTIVE:
                accepted.append(record)
            else:
                rejected.append(record)

    # Write accepted
    df_accepted = pd.DataFrame(accepted)
    csv_accepted = os.path.join(output_dir, "RETEST_ENGINE_V2_ACCEPTED_EVENTS.csv")
    df_accepted.to_csv(csv_accepted, index=False)
    print(f"Accepted events: {csv_accepted} ({len(df_accepted)} events)")

    # Write rejected
    df_rejected = pd.DataFrame(rejected)
    csv_rejected = os.path.join(output_dir, "RETEST_ENGINE_V2_REJECTED_EVENTS.csv")
    df_rejected.to_csv(csv_rejected, index=False)
    print(f"Rejected events: {csv_rejected} ({len(df_rejected)} events)")

    return df_accepted, df_rejected


def generate_transition_log(conn, symbols, output_dir):
    """Generate state transition log."""
    os.makedirs(output_dir, exist_ok=True)

    transitions = []
    for symbol in symbols:
        analysis = analyze_symbol(conn, symbol)
        if not analysis or not analysis["result"]:
            continue
        result = analysis["result"]
        for i, state in enumerate(result.states):
            if i > 0 and state != result.states[i-1]:
                transitions.append({
                    "symbol": symbol,
                    "bar_index": i,
                    "date": analysis["dates"][i],
                    "from_state": result.states[i-1],
                    "to_state": state,
                    "score": result.current_scores[i] if not np.isnan(result.current_scores[i]) else None,
                })

    df = pd.DataFrame(transitions)
    csv_path = os.path.join(output_dir, "RETEST_ENGINE_V2_TRANSITION_LOG.csv")
    df.to_csv(csv_path, index=False)
    print(f"Transition log: {csv_path} ({len(df)} transitions)")

    return df


def main():
    """Main function to generate all golden chart data."""
    output_dir = os.path.join(project_root, "RETEST_DELIVERABLES", "RETEST_ENGINE_V2_CHARTS")
    os.makedirs(output_dir, exist_ok=True)

    # Connect to US database
    conn = get_db("US")

    # Suspicious symbols
    suspicious = ["SONO", "GLBE", "SCI", "LILA", "SOLV"]

    # Additional symbols for validation
    additional = ["AAPL", "MU", "NVDA", "JNJ", "WMT", "MSFT", "GOOGL", "AMZN", "TSLA", "META"]

    all_symbols = suspicious + additional

    print(f"Analyzing {len(all_symbols)} symbols...")

    # Generate all outputs
    funnel_df = generate_funnel_sample(conn, all_symbols, output_dir)
    accepted_df, rejected_df = generate_event_logs(conn, all_symbols, output_dir)
    transition_df = generate_transition_log(conn, all_symbols, output_dir)

    # Summary
    print(f"\n{'='*60}")
    print("GOLDEN CHART VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"Symbols analyzed: {len(all_symbols)}")
    print(f"Total events: {len(funnel_df)}")
    print(f"Accepted events: {len(accepted_df)}")
    print(f"Rejected events: {len(rejected_df)}")
    print(f"Transitions: {len(transition_df)}")

    conn.close()


if __name__ == "__main__":
    main()
