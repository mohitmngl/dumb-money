"""
Benchmark: SQLite -> numpy array loading strategies for _load_hist_metrics_chunk

Tests 5 approaches:
  A) Current: pd.read_sql_query batch + pandas column extraction
  B) sqlite3 cursor.fetchmany + np.fromiter (chunked)
  C) DuckDB sqlite_scan -> Arrow -> numpy (no data copy through SQLite)
  D) DuckDB SQL-side aggregation (einsum in SQL, no raw data to Python)
  E) Pure SQL pivoting with sqlite3 (no numpy until final step)
"""
import sys, os, time, sqlite3
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dumbmoney.db import get_db
from dumbmoney.basket_screener import HIST_COLS, HIST_TEXT_COLS

# ── Setup ──────────────────────────────────────────────────────────────────────
conn = get_db("US")
num_cols = [c for c in HIST_COLS if c not in HIST_TEXT_COLS]
cols_sql = ", ".join(num_cols)
print(f"Numeric columns: {len(num_cols)}")

# Get a representative sample: 500 symbols, 50 dates
test_date = conn.execute(
    "SELECT MAX(date) FROM historical_screener").fetchone()[0]
all_dates = [r[0] for r in conn.execute(
    "SELECT DISTINCT date FROM historical_screener ORDER BY date DESC LIMIT 50"
).fetchall()]
all_dates.sort()
n_dates = len(all_dates)

sample_syms = [r[0] for r in conn.execute(
    "SELECT DISTINCT symbol FROM historical_screener WHERE date=? LIMIT 500",
    (test_date,)).fetchall()]
n_sym = len(sample_syms)

print(f"Sample: {n_sym} symbols x {n_dates} dates = {n_sym*n_dates:,} target cells")
t0 = time.time()
row_count = conn.execute(
    "SELECT COUNT(*) FROM historical_screener WHERE date IN ({}) AND symbol IN ({})".format(
        ",".join("?"*n_dates), ",".join("?"*n_sym)),
    all_dates + sample_syms).fetchone()[0]
print(f"Rows in query: {row_count:,}  (setup: {time.time()-t0:.2f}s)")

date_idx = {d: i for i, d in enumerate(all_dates)}
sym_idx = {s: i for i, s in enumerate(sample_syms)}

# ── A) Current: pd.read_sql_query (baseline) ──────────────────────────────────
def approach_a_pd_read_sql():
    import pandas as pd
    raw = {c: np.zeros((n_sym, n_dates), dtype=np.float32) for c in num_cols}
    q = (f"SELECT symbol, date, {cols_sql} FROM historical_screener "
         f"WHERE date >= ? AND date <= ? AND symbol IN ({','.join('?'*n_sym)})")
    params = (all_dates[0], all_dates[-1]) + tuple(sample_syms)
    df = pd.read_sql_query(q, conn, params=params)

    si = df["symbol"].map(sym_idx).fillna(-1).astype(np.int32).values
    di = df["date"].map(date_idx).fillna(-1).astype(np.int32).values
    valid = (si >= 0) & (di >= 0)
    si_v, di_v = si[valid], di[valid]

    for col in num_cols:
        vals = df[col].to_numpy(dtype=np.float32, na_value=np.nan)
        vals_v = vals[valid]
        mask = np.isfinite(vals_v)
        raw[col][si_v[mask], di_v[mask]] = vals_v[mask]
    del df
    return raw

# ── B) sqlite3 cursor.fetchmany + np.fromiter ──────────────────────────────────
def approach_b_fetchmany():
    raw = {c: np.zeros((n_sym, n_dates), dtype=np.float32) for c in num_cols}
    q = (f"SELECT symbol, date, {cols_sql} FROM historical_screener "
         f"WHERE date >= ? AND date <= ? AND symbol IN ({','.join('?'*n_sym)})")
    params = (all_dates[0], all_dates[-1]) + tuple(sample_syms)
    cur = conn.cursor()
    cur.arraysize = 100000
    cur.execute(q, params)

    # Pre-build column buffers
    col_buffers = {c: [] for c in num_cols}
    sym_buf = []
    date_buf = []

    while True:
        rows = cur.fetchmany()
        if not rows:
            break
        for r in rows:
            si = sym_idx.get(r[0], -1)
            di = date_idx.get(r[1], -1)
            if si < 0 or di < 0:
                continue
            for ci, col in enumerate(num_cols):
                v = r[ci + 2]
                if v is not None:
                    raw[col][si, di] = float(v)

    return raw

# ── C) DuckDB sqlite_scan -> Arrow -> numpy ────────────────────────────────────
def approach_c_duckdb_arrow():
    try:
        import duckdb
        import pyarrow as pa
    except ImportError:
        print("  [SKIP] duckdb/pyarrow not installed")
        return None

    # Find DB path
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screener.db")
    if not os.path.exists(db_path):
        # Try to find it
        from dumbmoney import db as _dbmod
        db_path = getattr(_dbmod, 'DB_PATH', db_path)

    con = duckdb.connect()
    con.execute("INSTALL sqlite; LOAD sqlite;")

    sym_list_sql = ",".join(f"'{s}'" for s in sample_syms)
    date_list_sql = ",".join(f"'{d}'" for d in all_dates)

    cols_select = ", ".join(f'h."{c}"' for c in num_cols)
    q = f"""
        SELECT h.symbol, h.date, {cols_select}
        FROM sqlite_scan('{db_path}', 'historical_screener') h
        WHERE h.date >= '{all_dates[0]}' AND h.date <= '{all_dates[-1]}'
        AND h.symbol IN ({sym_list_sql})
    """

    t0 = time.time()
    arrow_tbl = con.execute(q).fetch_arrow_table()
    t_load = time.time() - t0

    raw = {c: np.zeros((n_sym, n_dates), dtype=np.float32) for c in num_cols}

    t0 = time.time()
    sym_arr = arrow_tbl.column("symbol").to_pylist()
    date_arr = arrow_tbl.column("date").to_pylist()

    si = np.array([sym_idx.get(s, -1) for s in sym_arr], dtype=np.int32)
    di = np.array([date_idx.get(d, -1) for d in date_arr], dtype=np.int32)
    valid = (si >= 0) & (di >= 0)
    si_v, di_v = si[valid], di[valid]

    for col in num_cols:
        vals = np.array(arrow_tbl.column(col).to_pylist(), dtype=np.float32)
        vals_v = vals[valid]
        mask = np.isfinite(vals_v)
        raw[col][si_v[mask], di_v[mask]] = vals_v[mask]

    t_proc = time.time() - t0
    print(f"  DuckDB load: {t_load:.2f}s, process: {t_proc:.2f}s")
    con.close()
    return raw

# ── D) DuckDB SQL-side pivot (server-side aggregation) ─────────────────────────
def approach_d_duckdb_sql_pivot():
    """
    Use DuckDB SQL to do the pivot + weighted aggregation in one shot.
    This avoids loading raw rows into Python entirely for the einsum part.
    """
    try:
        import duckdb
    except ImportError:
        print("  [SKIP] duckdb not installed")
        return None

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screener.db")
    if not os.path.exists(db_path):
        from dumbmoney import db as _dbmod
        db_path = getattr(_dbmod, 'DB_PATH', db_path)

    con = duckdb.connect()
    con.execute("INSTALL sqlite; LOAD sqlite;")

    sym_list_sql = ",".join(f"'{s}'" for s in sample_syms)
    date_list_sql = ",".join(f"'{d}'" for d in all_dates)

    # For each column, do a PIVOT in SQL: rows -> matrix
    # Then compute the einsum in numpy from the pivoted result
    # This is faster because DuckDB does the grouping/pivoting in C++
    raw = {}
    t0 = time.time()

    for col in num_cols:
        q = f"""
            PIVOT (
                SELECT symbol, date, "{col}"
                FROM sqlite_scan('{db_path}', 'historical_screener')
                WHERE date >= '{all_dates[0]}' AND date <= '{all_dates[-1]}'
                AND symbol IN ({sym_list_sql})
            )
            USING "{col}"
            GROUP BY symbol
            ORDER BY symbol
        """
        result = con.execute(q).fetchall()
        # result is list of tuples: (symbol, val_date1, val_date2, ...)
        mat = np.zeros((n_sym, n_dates), dtype=np.float32)
        for row in result:
            si = sym_idx.get(row[0], -1)
            if si < 0:
                continue
            for j in range(n_dates):
                v = row[j + 1]
                if v is not None:
                    mat[si, j] = float(v)
        raw[col] = mat

    t_total = time.time() - t0
    print(f"  DuckDB PIVOT total: {t_total:.2f}s ({len(num_cols)} columns)")
    con.close()
    return raw

# ── E) DuckDB: single-shot pivoted weighted sum (no numpy intermediate) ───────
def approach_e_duckdb_einsum_sql():
    """
    Compute weighted averages entirely in SQL.
    For each column: SELECT symbol, SUM(col * weight) / SUM(weight) ...
    This eliminates the 2D numpy array + einsum entirely.
    """
    try:
        import duckdb
    except ImportError:
        print("  [SKIP] duckdb not installed")
        return None

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screener.db")
    if not os.path.exists(db_path):
        from dumbmoney import db as _dbmod
        db_path = getattr(_dbmod, 'DB_PATH', db_path)

    con = duckdb.connect()
    con.execute("INSTALL sqlite; LOAD sqlite;")

    sym_list_sql = ",".join(f"'{s}'" for s in sample_syms)

    # Example: simple uniform weights across all dates
    # In real use, weights would be passed in. Here we demo the concept.
    # This approach returns per-symbol weighted sums directly from SQL.
    t0 = time.time()

    # Build a CTE with date-indexed weights (uniform for demo)
    weight_cases = "\n".join(
        f"WHEN date = '{d}' THEN {1.0/n_dates:.6f}"
        for d in all_dates
    )

    results = {}
    for col in num_cols:
        q = f"""
            WITH weighted AS (
                SELECT symbol, date, "{col}" AS val,
                    CASE {weight_cases} ELSE 0 END AS w
                FROM sqlite_scan('{db_path}', 'historical_screener')
                WHERE date >= '{all_dates[0]}' AND date <= '{all_dates[-1]}'
                AND symbol IN ({sym_list_sql})
            )
            SELECT symbol, SUM(val * w) AS weighted_sum, SUM(w) AS w_sum
            FROM weighted
            WHERE val IS NOT NULL
            GROUP BY symbol
            ORDER BY symbol
        """
        result = con.execute(q).fetchall()
        # Map to array
        arr = np.zeros(n_sym, dtype=np.float32)
        for row in result:
            si = sym_idx.get(row[0], -1)
            if si >= 0 and row[2] > 0:
                arr[si] = row[1] / row[2]
        results[col] = arr

    t_total = time.time() - t0
    print(f"  DuckDB SQL einsum total: {t_total:.2f}s ({len(num_cols)} columns)")
    con.close()
    return results

# ── F) Numba-accelerated scatter ───────────────────────────────────────────────
def approach_f_numba():
    try:
        from numba import njit, prange
    except ImportError:
        print("  [SKIP] numba not installed")
        return None

    q = (f"SELECT symbol, date, {cols_sql} FROM historical_screener "
         f"WHERE date >= ? AND date <= ? AND symbol IN ({','.join('?'*n_sym)})")
    params = (all_dates[0], all_dates[-1]) + tuple(sample_syms)
    rows = conn.execute(q, params).fetchall()

    # Convert to flat arrays
    n_rows = len(rows)
    si_arr = np.empty(n_rows, dtype=np.int64)
    di_arr = np.empty(n_rows, dtype=np.int64)
    for i, r in enumerate(rows):
        si_arr[i] = sym_idx.get(r[0], -1)
        di_arr[i] = date_idx.get(r[1], -1)

    valid = (si_arr >= 0) & (di_arr >= 0)
    si_v = si_arr[valid]
    di_v = di_arr[valid]

    # Extract numeric columns as 2D array
    data = np.empty((n_rows, len(num_cols)), dtype=np.float64)
    for ci, col in enumerate(num_cols):
        for i, r in enumerate(rows):
            v = r[ci + 2]
            data[i, ci] = float(v) if v is not None else np.nan

    data_v = data[valid]
    del data, rows

    @njit(parallel=True)
    def scatter_multi(si, di, vals, n_sym, n_dates, n_cols):
        out = np.zeros((n_sym, n_dates, n_cols), dtype=np.float32)
        for k in prange(len(si)):
            s, d = si[k], di[k]
            for c in range(n_cols):
                v = vals[k, c]
                if v == v:  # not NaN
                    out[s, d, c] = v
        return out

    t0 = time.time()
    cube = scatter_multi(si_v, di_v, data_v, n_sym, n_dates, len(num_cols))
    t_scatter = time.time() - t0

    raw = {}
    for ci, col in enumerate(num_cols):
        raw[col] = cube[:, :, ci]

    print(f"  Numba scatter: {t_scatter:.2f}s")
    return raw

# ── Run benchmarks ─────────────────────────────────────────────────────────────
RESULTS = {}

print("\n" + "="*70)
print("A) pd.read_sql_query (current)")
print("="*70)
t0 = time.time()
res_a = approach_a_pd_read_sql()
t_a = time.time() - t0
RESULTS['A_pd_read_sql'] = t_a
print(f"  Time: {t_a:.2f}s")

print("\n" + "="*70)
print("B) sqlite3 cursor.fetchmany")
print("="*70)
t0 = time.time()
res_b = approach_b_fetchmany()
t_b = time.time() - t0
RESULTS['B_fetchmany'] = t_b
print(f"  Time: {t_b:.2f}s")

print("\n" + "="*70)
print("C) DuckDB sqlite_scan -> Arrow -> numpy")
print("="*70)
t0 = time.time()
res_c = approach_c_duckdb_arrow()
t_c = time.time() - t0
if res_c is not None:
    RESULTS['C_duckdb_arrow'] = t_c
    print(f"  Time: {t_c:.2f}s")

print("\n" + "="*70)
print("D) DuckDB PIVOT (server-side pivot)")
print("="*70)
t0 = time.time()
res_d = approach_d_duckdb_sql_pivot()
t_d = time.time() - t0
if res_d is not None:
    RESULTS['D_duckdb_pivot'] = t_d
    print(f"  Time: {t_d:.2f}s")

print("\n" + "="*70)
print("E) DuckDB SQL-side weighted sum (no 2D array)")
print("="*70)
t0 = time.time()
res_e = approach_e_duckdb_einsum_sql()
t_e = time.time() - t0
if res_e is not None:
    RESULTS['E_duckdb_sql_einsum'] = t_e
    print(f"  Time: {t_e:.2f}s")

print("\n" + "="*70)
print("F) Numba-accelerated scatter")
print("="*70)
t0 = time.time()
res_f = approach_f_numba()
t_f = time.time() - t0
if res_f is not None:
    RESULTS['F_numba'] = t_f
    print(f"  Time: {t_f:.2f}s")

# ── Verify correctness ─────────────────────────────────────────────────────────
print("\n" + "="*70)
print("CORRECTNESS CHECK (against approach A)")
print("="*70)
test_col = num_cols[0]
for name, res in [('B', res_b), ('C', res_c), ('D', res_d), ('F', res_f)]:
    if res is None:
        continue
    match = np.allclose(res_a[test_col], res[test_col], equal_nan=True)
    print(f"  {name} matches A: {match}")

# ── Summary ────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("BENCHMARK SUMMARY")
print("="*70)
baseline = RESULTS.get('A_pd_read_sql', 1)
for name, t in sorted(RESULTS.items(), key=lambda x: x[1]):
    speedup = baseline / t if t > 0 else float('inf')
    bar = "█" * int(min(speedup, 30))
    print(f"  {name:30s}  {t:6.2f}s  {speedup:5.1f}x  {bar}")

conn.close()
