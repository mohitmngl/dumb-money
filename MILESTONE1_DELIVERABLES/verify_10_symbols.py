"""Quick verification of 10 manual symbols."""
import os
import sys
import sqlite3

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dumbmoney.config import US_DB, INDIA_DB
from dumbmoney.db import get_db

SYMBOLS = ["SONO", "GLBE", "SCI", "LILA", "SOLV", "AAPL", "MU", "NVDA", "JNJ", "WMT"]

print("=" * 80)
print("MANUAL VERIFICATION - 10 SYMBOLS")
print("=" * 80)

for market, db_path in [("US", US_DB), ("INDIA", INDIA_DB)]:
    print(f"\n{market} Market:")
    print("-" * 80)
    
    conn = get_db(market)
    
    for symbol in SYMBOLS:
        # Check if symbol exists in this market
        row = conn.execute("SELECT old_swing_retest_score FROM stats WHERE symbol=?", (symbol,)).fetchone()
        if row is None:
            continue
            
        db_score = row[0]
        
        # Get latest bar date
        bar_row = conn.execute(
            "SELECT MAX(date) FROM bars WHERE timeframe='1Day' AND symbol=?", (symbol,)
        ).fetchone()
        latest_bar_date = bar_row[0] if bar_row and bar_row[0] else "N/A"
        
        print(f"{symbol:8} | DB Score: {str(db_score):8} | Latest Bar: {latest_bar_date}")
    
    conn.close()

print("\n" + "=" * 80)
print("VERIFICATION COMPLETE")
print("=" * 80)
