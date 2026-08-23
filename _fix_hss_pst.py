"""Fast HSS prob_up_st_cross fix using PRIMARY KEY lookups.
Computes all values via numpy, then updates using (string_id, date) PK."""
import sys, time, sqlite3
import numpy as np
sys.path.insert(0, '.')
from dumbmoney.db import get_db

def fix_market(market):
    db_file = 'screener.db' if market == 'US' else 'india.db'
    conn = sqlite3.connect(db_file, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA cache_size=-2000000")
    t0 = time.time()

    # 1. Load composition
    rows = conn.execute(
        "SELECT sc.string_id, sc.symbol, sc.weight FROM string_constituents sc "
        "JOIN string_universe su ON sc.string_id = su.string_id WHERE su.market = ?", (market,)
    ).fetchall()
    sid_map = {}
    sym_set = set()
    for string_id, symbol, weight in rows:
        sid_map.setdefault(string_id, []).append((symbol, weight))
        sym_set.add(symbol)
    sids = sorted(sid_map.keys())
    sym_list = sorted(sym_set)
    sym_idx = {s: i for i, s in enumerate(sym_list)}
    sid_idx = {s: i for i, s in enumerate(sids)}
    print(f"[{market}] {len(sids)} strings, {len(sym_list)} symbols ({time.time()-t0:.1f}s)", flush=True)

    # 2. Build weight matrix
    MAX_CONS = max(len(v) for v in sid_map.values())
    idx_arr = np.zeros((len(sids), MAX_CONS), dtype=np.int32)
    wn_arr = np.zeros((len(sids), MAX_CONS), dtype=np.float64)
    n_cons = np.zeros(len(sids), dtype=np.int32)
    for si, sid in enumerate(sids):
        cons = sid_map[sid]
        nc = len(cons)
        n_cons[si] = nc
        for j, (sym, wt) in enumerate(cons):
            idx_arr[si, j] = sym_idx[sym]
        abs_w = np.array([abs(wt) for _, wt in cons], dtype=np.float64)
        wsum = abs_w.sum()
        if wsum > 0:
            wn_arr[si, :nc] = abs_w / wsum

    # 3. Get HSS (string_id, date) pairs using cursor (avoid loading all into memory)
    print(f"[{market}] Loading HSS (string_id, date) pairs...", flush=True)
    hss_pairs = []
    cur = conn.execute("SELECT string_id, date FROM historical_string_screener")
    while True:
        batch = cur.fetchmany(1000000)
        if not batch:
            break
        hss_pairs.extend(batch)
    del cur
    print(f"[{market}] {len(hss_pairs):,} HSS pairs ({time.time()-t0:.1f}s)", flush=True)

    # Build (string_id, date) → index mapping
    sid_date_to_hss_idx = {}
    all_dates_set = set()
    for i, (sid, dt) in enumerate(hss_pairs):
        sid_date_to_hss_idx[(sid, dt)] = i
        all_dates_set.add(dt)
    dates = sorted(all_dates_set)
    date_idx = {d: i for i, d in enumerate(dates)}
    n_dates = len(dates)
    print(f"[{market}] {n_dates} unique dates ({time.time()-t0:.1f}s)", flush=True)

    # 4. Load HS pst using cursor (faster than pandas)
    print(f"[{market}] Loading HS pst...", flush=True)
    hs_pst = np.full((len(sym_list), n_dates), 50.0, dtype=np.float64)
    cur = conn.execute("SELECT symbol, date, prob_up_st_cross FROM historical_screener")
    loaded = 0
    while True:
        batch = cur.fetchmany(500000)
        if not batch:
            break
        for sym, dt, pst in batch:
            si = sym_idx.get(sym)
            di = date_idx.get(dt)
            if si is not None and di is not None:
                hs_pst[si, di] = pst if pst is not None else 50.0
        loaded += len(batch)
        print(f"[{market}] HS loaded {loaded:,} ({time.time()-t0:.1f}s)", flush=True)
    del cur
    print(f"[{market}] HS pivot ready ({time.time()-t0:.1f}s)", flush=True)

    # 5. Matrix multiply
    print(f"[{market}] Computing basket pst...", flush=True)
    gathered = hs_pst[idx_arr]
    mask = np.arange(MAX_CONS) < n_cons[:, None]
    masked = np.where(mask[:, :, None], gathered, 0.0)
    basket_pst = np.einsum('ijk,ij->ik', masked, wn_arr)
    print(f"[{market}] Computed ({time.time()-t0:.1f}s)", flush=True)

    # 6. Build PK-based UPDATE tuples
    print(f"[{market}] Building update list...", flush=True)
    updates = []
    for sid, dt in hss_pairs:
        si = sid_idx.get(sid)
        di = date_idx.get(dt)
        if si is not None and di is not None:
            val = float(basket_pst[si, di])
            updates.append((round(val, 4), sid, dt))
    print(f"[{market}] {len(updates):,} updates ({time.time()-t0:.1f}s)", flush=True)

    # 7. Bulk PK update
    print(f"[{market}] Applying updates...", flush=True)
    conn.execute("PRAGMA cache_size=-4000000")
    BATCH = 100000
    t1 = time.time()
    for i in range(0, len(updates), BATCH):
        conn.executemany(
            "UPDATE historical_string_screener SET prob_up_st_cross = ? "
            "WHERE string_id = ? AND date = ?", updates[i:i+BATCH])
        conn.commit()
        if (i // BATCH) % 10 == 0:
            pct = min(i + BATCH, len(updates))
            print(f"[{market}] {pct:,}/{len(updates):,} ({time.time()-t1:.1f}s)", flush=True)
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.close()
    print(f"[{market}] DONE in {time.time()-t0:.1f}s", flush=True)

if __name__ == "__main__":
    fix_market("US")
    fix_market("INDIA")
