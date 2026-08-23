"""Fast incremental update: compute bars_at_side from existing signal columns."""
import sqlite3
import numpy as np
import sys, time
sys.path.insert(0, r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt")
from dumbmoney.indicators import bars_at_side

def patch_market(db_path, market):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-200000")

    syms = [r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM historical_screener"
    ).fetchall()]
    print(f"[{market}] {len(syms)} symbols to patch")

    done = 0
    t0 = time.time()
    batch = []
    for sym in syms:
        rows = conn.execute(
            "SELECT rowid, atr_signal, accel_signal FROM historical_screener WHERE symbol=? ORDER BY date",
            (sym,)
        ).fetchall()
        if not rows:
            done += 1
            continue

        rowids = [r[0] for r in rows]
        atr_sig = np.array([r[1] for r in rows], dtype=np.int32)
        ac_sig = np.array([r[2] for r in rows], dtype=np.int32)

        st_bas = bars_at_side(atr_sig)
        ac_bas = bars_at_side(ac_sig)

        for i, rid in enumerate(rowids):
            st_bb = int(st_bas[i]) if atr_sig[i] == 1 else 0
            st_ba = int(st_bas[i]) if atr_sig[i] == -1 else 0
            ac_bb = int(ac_bas[i]) if ac_sig[i] == 1 else 0
            ac_ba = int(ac_bas[i]) if ac_sig[i] == -1 else 0
            batch.append((st_bb, st_ba, ac_bb, ac_ba, rid))

        done += 1
        if done % 200 == 0:
            conn.executemany(
                "UPDATE historical_screener SET st_bars_below=?, st_bars_above=?, accel_bars_below=?, accel_bars_above=? WHERE rowid=?",
                batch
            )
            conn.commit()
            batch = []
            elapsed = time.time() - t0
            rate = done / elapsed
            eta = (len(syms) - done) / rate if rate > 0 else 0
            nz = sum(1 for b in batch if any(x > 0 for x in b[:4]))
            print(f"[{market}] {done}/{len(syms)} ({done*100//len(syms)}%) {elapsed:.0f}s elapsed, ETA {eta:.0f}s")

    if batch:
        conn.executemany(
            "UPDATE historical_screener SET st_bars_below=?, st_bars_above=?, accel_bars_below=?, accel_bars_above=? WHERE rowid=?",
            batch
        )
        conn.commit()

    elapsed = time.time() - t0
    nz = conn.execute(
        "SELECT COUNT(*) FROM historical_screener WHERE st_bars_below>0 OR st_bars_above>0 OR accel_bars_below>0 OR accel_bars_above>0"
    ).fetchone()[0]
    print(f"[{market}] DONE in {elapsed:.0f}s, {nz} rows with non-zero bars_at_side")
    conn.close()

if __name__ == "__main__":
    patch_market(r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\india.db", "INDIA")
