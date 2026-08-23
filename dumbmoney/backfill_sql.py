"""Pure-SQL backfill of ai_matrix, ai_overall_score, ai_conclusion, confluence.

All computation happens inside SQLite — no Python pandas, no per-symbol loops,
no tuple building. Two SQL statements do everything:

  1. CREATE TEMP TABLE _bf — bar features via SQL window functions (RSI, SMA, vol)
  2. UPDATE historical_screener FROM _bf — sigmoid formula in pure SQL

Estimated time: 2-5 minutes vs 5+ hours for the Python approach.
"""

import argparse
import sqlite3
import time

TANH = "({x} > 20 OR {x} < -20)"  # guard placeholder — inlined below

def tanh_sql(expr):
    return (
        f"(CASE WHEN {expr} > 20 THEN 1.0 "
        f"WHEN {expr} < -20 THEN -1.0 "
        f"ELSE (EXP(2.0*({expr})) - 1.0) / (EXP(2.0*({expr})) + 1.0) END)"
    )

SIGMOID_SQL = "(1.0 / (1.0 + EXP(-({expr}))))"

CREATE_BF = """
DROP TABLE IF EXISTS _bf;
CREATE TEMP TABLE _bf AS
WITH base AS (
    SELECT symbol, date, close, high, low, volume,
        AVG(close) OVER w20 AS sma20,
        AVG(close) OVER w50 AS sma50,
        AVG(CAST(volume AS REAL)) OVER w5 AS vol_avg5,
        AVG(CAST(volume AS REAL)) OVER w20 AS vol_avg20,
        MAX(high) OVER w20 AS h20,
        MIN(low) OVER w20 AS l20
    FROM bars
    WHERE timeframe = '1Day'
    WINDOW w20 AS (PARTITION BY symbol ORDER BY date ROWS 19 PRECEDING),
           w50 AS (PARTITION BY symbol ORDER BY date ROWS 49 PRECEDING),
           w5 AS  (PARTITION BY symbol ORDER BY date ROWS 4 PRECEDING)
),
with_delta AS (
    SELECT *,
        close - LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS delta
    FROM base
),
with_gains AS (
    SELECT *,
        MAX(COALESCE(delta, 0), 0) AS gain,
        MAX(COALESCE(-delta, 0), 0) AS loss
    FROM with_delta
),
with_rsi AS (
    SELECT *,
        AVG(gain) OVER (PARTITION BY symbol ORDER BY date ROWS 13 PRECEDING) AS avg_gain,
        AVG(loss) OVER (PARTITION BY symbol ORDER BY date ROWS 13 PRECEDING) AS avg_loss
    FROM with_gains
)
SELECT symbol, date, close, sma20, sma50, h20, l20,
    CASE WHEN avg_loss = 0 THEN 50.0
         ELSE 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    END AS rsi,
    CASE WHEN vol_avg20 > 0 THEN vol_avg5 / vol_avg20 ELSE 1.0 END AS vol_ratio,
    CASE WHEN volume > 3.0 * vol_avg20 THEN 1 ELSE 0 END AS vol_spike
FROM with_rsi;
"""


def build_update_sql():
    s = "historical_screener"
    wa_norm = tanh_sql(f"{s}.weighted_alpha / 15.0")
    streak_amp = f"(1.0 + 0.3 * {tanh_sql(f'{s}.streak / 3.0')})"
    wa_component = f"({wa_norm} * {streak_amp})"
    trend_component = f"({s}.atr_signal + {s}.accel_signal) * 0.5"
    rsi_component = "(bf.rsi - 50.0) / 20.0"
    D = f"(({wa_component} + {trend_component} + {rsi_component}) / 3.0)"
    any_cross = f"({s}.atr_crossed_above | {s}.atr_crossed_below | {s}.accel_crossed_up | {s}.accel_crossed_down)"
    boost = f"(1.0 + 0.5 * ({any_cross}))"
    raw_cross = f"({s}.atr_signal + {s}.accel_signal)"
    X = f"({raw_cross} * 0.5 * {boost})"

    log_ratio = f"(LN(MAX(bf.vol_ratio, 0.01)))"
    spike_impulse = "(0.3 * bf.vol_spike)"
    V = tanh_sql(f"(({log_ratio} + {spike_impulse}) * 2.0)")

    oversold = SIGMOID_SQL.format(expr="(50.0 - bf.rsi) / 10.0")
    vol_confirm = SIGMOID_SQL.format(expr=f"({s}.atrp - 3.0) / 1.5")
    B = f"(({oversold} * {vol_confirm}) * 2.0 - 1.0)"

    p_clipped = f"(MAX(1e-6, MIN(1.0 - 1e-6, {s}.prob_up_1d / 100.0)))"
    P = f"(LN({p_clipped} / (1.0 - {p_clipped})))"

    z_base = f"(1.20 * {D} + 0.40 * {X} + 0.35 * {V} + 0.25 * {B} + 0.30 * {P})"

    ma_bias = (
        f"(CASE WHEN bf.sma20 > 0 AND bf.sma50 > 0 "
        f"THEN 0.15 * {tanh_sql('(bf.sma20 - bf.sma50) / (0.05 * bf.sma50 + 1e-9)')} "
        f"ELSE 0 END)"
    )

    rng_valid = "(CASE WHEN bf.h20 > bf.l20 AND bf.close > 0 THEN 1 ELSE 0 END)"
    pos = f"(CASE WHEN bf.h20 > bf.l20 AND bf.close > 0 THEN (bf.close - bf.l20) / (bf.h20 - bf.l20 + 1e-9) ELSE 0 END)"
    range_hint = f"(0.10 * ({pos} - 0.5) * 2.0)"
    aligned = f"(({s}.weighted_alpha > 0 AND {pos} > 0.5) OR ({s}.weighted_alpha < 0 AND {pos} < 0.5))"
    price_adj = f"(CASE WHEN {rng_valid} AND {aligned} THEN {range_hint} WHEN {rng_valid} AND NOT {aligned} THEN -{range_hint} * 0.5 ELSE 0 END)"

    z_full = f"({z_base} + {ma_bias} + {price_adj})"
    ai_matrix_expr = f"ROUND(100.0 / (1.0 + EXP(-MAX(-500.0, MIN(500.0, {z_full})))), 2)"

    conclusion_expr = (
        f"(CASE WHEN {ai_matrix_expr} > 60 THEN 'BUY' "
        f"WHEN {ai_matrix_expr} < 40 THEN 'SELL' "
        f"ELSE 'HOLD' END)"
    )

    conf_atr = f"(CASE WHEN {s}.atr_signal = 1 THEN 25.0 WHEN {s}.atr_signal = -1 THEN -10.0 ELSE 0.0 END)"
    conf_accel = f"(CASE WHEN {s}.accel_signal = 1 THEN 25.0 WHEN {s}.accel_signal = -1 THEN -10.0 ELSE 0.0 END)"
    conf_wa = f"(CASE WHEN {s}.weighted_alpha > 50 THEN 25.0 WHEN {s}.weighted_alpha > 20 THEN 15.0 WHEN {s}.weighted_alpha > 0 THEN 5.0 ELSE -5.0 END)"
    conf_streak = f"(CASE WHEN {s}.streak >= 3 THEN 15.0 WHEN {s}.streak >= 1 THEN 5.0 ELSE 0.0 END)"
    conf_prob = f"(CASE WHEN {s}.prob_up_1d > 60 THEN 10.0 WHEN {s}.prob_up_1d > 55 THEN 5.0 ELSE 0.0 END)"
    confluence_expr = f"MAX(0.0, MIN(100.0, {conf_atr} + {conf_accel} + {conf_wa} + {conf_streak} + {conf_prob}))"

    return f"""
UPDATE historical_screener SET
    ai_matrix = {ai_matrix_expr},
    ai_overall_score = {ai_matrix_expr},
    ai_conclusion = {conclusion_expr},
    confluence = {confluence_expr}
FROM _bf bf
WHERE historical_screener.symbol = bf.symbol
  AND historical_screener.date = bf.date;
"""


def backfill(market="US", limit_symbols=None):
    db = "screener.db" if market == "US" else "india.db"
    conn = sqlite3.connect(db, timeout=300)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=300000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-200000")
        conn.execute("PRAGMA wal_autocheckpoint=0")

        print(f"[{market}] Dropping secondary indexes...")
        conn.execute("DROP INDEX IF EXISTS idx_hs_sym_date")
        conn.execute("DROP INDEX IF EXISTS idx_hs_date")
        conn.commit()

        total = conn.execute("SELECT COUNT(*) FROM historical_screener").fetchone()[0]
        print(f"[{market}] historical_screener: {total:,} rows")

        t0 = time.time()

        print(f"[{market}] Step 1: Computing bar features via SQL window functions...")
        conn.execute("DROP TABLE IF EXISTS _bf")
        for stmt in CREATE_BF.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
        bf_count = conn.execute("SELECT COUNT(*) FROM _bf").fetchone()[0]
        elapsed = time.time() - t0
        print(f"[{market}] Step 1 done: {bf_count:,} bar feature rows in {elapsed:.1f}s")

        print(f"[{market}] Step 2: Computing sigmoid scores in pure SQL...")
        t1 = time.time()
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bf ON _bf(symbol, date)")
        conn.commit()

        update_sql = build_update_sql()
        conn.execute(update_sql)
        conn.commit()
        elapsed2 = time.time() - t1
        print(f"[{market}] Step 2 done in {elapsed2:.1f}s")

        print(f"[{market}] Recreating indexes...")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hs_sym_date ON historical_screener(symbol, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hs_date ON historical_screener(date)")
        from dumbmoney.engine import HISTORICAL_SCREENER_VERSION
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('historical_screener_version', ?)",
            (HISTORICAL_SCREENER_VERSION,),
        )
        conn.execute("PRAGMA wal_autocheckpoint=1000")
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            try:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception:
                pass
        conn.commit()

        counts = dict(conn.execute(
            "SELECT ai_conclusion, COUNT(*) FROM historical_screener GROUP BY ai_conclusion"
        ).fetchall())
        filled = conn.execute(
            "SELECT COUNT(*) FROM historical_screener WHERE ai_matrix IS NOT NULL AND ai_matrix != '' AND CAST(ai_matrix AS REAL) > 0"
        ).fetchone()[0]
        total_time = time.time() - t0
        print(f"[{market}] DONE in {total_time:.1f}s ({total_time/60:.1f} min)")
        print(f"[{market}] ai_matrix filled: {filled:,} / {total:,}")
        print(f"[{market}] conclusions: {counts}")
        print(f"[{market}] throughput: {total/total_time:.0f} rows/s")
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="Pure-SQL backfill of historical_screener scores")
    ap.add_argument("--market", default="US", choices=["US", "INDIA"])
    ap.add_argument("--all-markets", action="store_true")
    args = ap.parse_args()
    markets = ["US", "INDIA"] if args.all_markets else [args.market]
    for mkt in markets:
        backfill(mkt)


if __name__ == "__main__":
    main()
