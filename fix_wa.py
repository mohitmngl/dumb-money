"""Fix stats.weighted_alpha for symbols that should be rejected by the fitted formula."""

import sqlite3
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from clean_weighted_alpha_formula import weighted_alpha_from_closes

DBS = {
    "US": r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db",
    "INDIA": r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\india.db",
}

def fix_market(market):
    db = DBS[market]
    print(f"\nFixing {market}...")
    conn = sqlite3.connect(db, timeout=30)
    
    # Get all symbols with non-zero WA in stats
    rows = conn.execute("SELECT symbol, weighted_alpha FROM stats WHERE weighted_alpha != 0").fetchall()
    print(f"  Symbols with non-zero WA: {len(rows)}")
    
    fixed = 0
    for sym, current_wa in rows:
        closes = np.array(
            [r[0] for r in conn.execute(
                "SELECT close FROM bars WHERE symbol=? ORDER BY date ASC", (sym,)
            ).fetchall()], dtype=np.float64
        )
        if len(closes) < 300:
            continue
        
        try:
            wa = float(weighted_alpha_from_closes(closes, reject_split_like=True))
            # Check if it's wildly different
            if abs(wa - current_wa) > 50:
                print(f"  {sym}: {current_wa:.2f} -> {wa:.2f} (FIXED)")
                conn.execute("UPDATE stats SET weighted_alpha=? WHERE symbol=?", (wa, sym))
                conn.execute("UPDATE historical_screener SET weighted_alpha=? WHERE symbol=?", (wa, sym))
                fixed += 1
        except ValueError:
            # Should be rejected - set to 0
            if current_wa != 0:
                print(f"  {sym}: {current_wa:.2f} -> 0 (REJECTED - split)")
                conn.execute("UPDATE stats SET weighted_alpha=0 WHERE symbol=?", (sym,))
                conn.execute("UPDATE historical_screener SET weighted_alpha=0 WHERE symbol=?", (sym,))
                fixed += 1
    
    conn.commit()
    conn.close()
    print(f"  Fixed: {fixed}")

if __name__ == "__main__":
    for m in ["US", "INDIA"]:
        fix_market(m)
