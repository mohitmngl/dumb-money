"""Combined single-pass recompute of historical_screener AI/confluence columns.

WHY ONE PASS
------------
The running backfill_ai_matrix.py was fixing ONLY ai_matrix and leaving the old
component-score ai_overall_score and the stale (SELL-less) ai_conclusion untouched.
Every follow-up pass would re-read bars + historical per symbol-batch and re-pay the
I/O. This script kills the competing writer and recomputes everything in ONE pass:

  - ai_matrix        : sigmoid(0-100), byte-identical to engine._compute_historical_symbol_frame
  - ai_overall_score : now defined as ai_matrix (the old component score is wrong)
  - ai_conclusion    : derived from ai_matrix (>60 BUY, <40 SELL, else HOLD)
  - confluence       : recomputed vectorized from the existing correct as-of-date indicators

THROUGHPUT STRATEGY
-------------------
1. Kill the other single-writer so we own the SQLite lock.
2. Read historical_screener inputs ONCE (they are already correct as-of-date).
3. Stream bars in symbol-batches; compute rsi/sma20/50/vol_ratio/vol_spike/h20/l20
   with a single vectorized groupby.transform per batch (no per-symbol Python loop).
4. Merge on (symbol,date); compute all columns vectorized; write via ONE combined
   UPDATE per row, batched with executemany.
5. Drop the two secondary historical_screener indexes for the bulk write, recreate after.
6. WAL + synchronous=NORMAL + wal_autocheckpoint=0 + large cache; checkpoint at end.
7. US and India are separate DB files -> run as two independent processes.

ai_matrix needs bar-derived features (rsi, sma20/50, vol_ratio, vol_spike, h20, l20, close)
that are NOT stored in historical_screener, so bars MUST be read. We read bars exactly
once, in symbol-batches. Value columns that are already correct (atr_signal, accel_signal,
weighted_alpha, streak, atrp, prob_up_1d) come straight from historical_screener.

Usage:
    python -m dumbmoney.backfill_all_scores --market US --kill-pids 7364
    python -m dumbmoney.backfill_all_scores --market INDIA --kill-pids 9780
    python -m dumbmoney.backfill_all_scores --all-markets --kill-pids 7364,9780
"""

import argparse
import logging
import subprocess
import time

import numpy as np
import pandas as pd

from dumbmoney.db import get_db
from dumbmoney.engine import HISTORICAL_SCREENER_VERSION
from dumbmoney.indicators import rsi_wilder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("backfill_all_scores")

HIST_COLS = [
    "symbol", "date",
    "weighted_alpha", "streak", "atr_signal", "accel_signal",
    "atr_crossed_above", "atr_crossed_below",
    "accel_crossed_up", "accel_crossed_down",
    "atrp", "prob_up_1d",
]

UPDATE_SQL = (
    "UPDATE historical_screener "
    "SET ai_matrix=?, ai_overall_score=?, ai_conclusion=?, confluence=? "
    "WHERE symbol=? AND date=?"
)

SECONDARY_INDEXES = [
    "idx_hs_sym_date",
    "idx_hs_date",
]


def kill_pids(pids):
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            logger.info("Sent kill to PID %s", pid)
        except Exception as exc:  # pragma: no cover
            logger.warning("Could not kill PID %s: %s", pid, exc)


def _to_datestr(ts):
    try:
        return pd.to_datetime(ts).strftime("%Y-%m-%d")
    except Exception:
        return str(ts)[:10]


def compute_bar_features(bars):
    """Vectorized bar-level features for a symbol-batch, keyed by (symbol, date)."""
    bars = bars.sort_values(["symbol", "date"]).reset_index(drop=True)
    g = bars.groupby("symbol", sort=False)
    close = bars["close"].astype(float)
    high = bars["high"].astype(float)
    low = bars["low"].astype(float)
    vol = bars["volume"].astype(float)
    vol_avg20 = g["volume"].transform(lambda s: s.rolling(20, min_periods=1).mean())
    feat = pd.DataFrame({
        "symbol": bars["symbol"],
        "date": bars["date"],
        "rsi": g["close"].transform(lambda s: rsi_wilder(s, 14).fillna(50)).astype(float),
        "sma20": g["close"].transform(lambda s: s.rolling(20, min_periods=1).mean()).astype(float),
        "sma50": g["close"].transform(lambda s: s.rolling(50, min_periods=1).mean()).astype(float),
        "vol_ratio": (vol / vol_avg20.replace(0, np.nan))
        .replace([np.inf, -np.inf], np.nan).fillna(1.0).astype(float),
        "vol_spike": (vol > 3.0 * vol_avg20).fillna(False),
        "h20": g["high"].transform(lambda s: s.rolling(20, min_periods=1).max()).astype(float),
        "l20": g["low"].transform(lambda s: s.rolling(20, min_periods=1).min()).astype(float),
        "close": close,
    })
    return feat


def vectorized_confluence(atr_signal, accel_signal, wa, streak, prob):
    score = np.zeros(len(atr_signal), dtype=float)
    score += np.where(atr_signal == 1, 25.0, np.where(atr_signal == -1, -10.0, 0.0))
    score += np.where(accel_signal == 1, 25.0, np.where(accel_signal == -1, -10.0, 0.0))
    score += np.where(wa > 50, 25.0, np.where(wa > 20, 15.0, np.where(wa > 0, 5.0, -5.0)))
    score += np.where(streak >= 3, 15.0, np.where(streak >= 1, 5.0, 0.0))
    score += np.where(prob > 60, 10.0, np.where(prob > 55, 5.0, 0.0))
    return np.clip(score, 0.0, 100.0)


def compute_scores(hist, feat):
    """Return aligned numpy arrays: ai_matrix, ai_overall_score, ai_conclusion, confluence."""
    m = hist.merge(feat, on=["symbol", "date"], how="left")

    ffill = {
        "rsi": 50.0, "sma20": 0.0, "sma50": 0.0,
        "vol_ratio": 1.0, "h20": 0.0, "l20": 0.0, "close": 0.0,
    }
    for col, val in ffill.items():
        m[col] = m[col].fillna(val)
    m["vol_spike"] = m["vol_spike"].fillna(False).astype(bool)

    _clip = np.clip
    _tanh = np.tanh
    _log = np.log
    _sig = lambda x: 1.0 / (1.0 + np.exp(_clip(x, -500.0, 500.0)))

    rsi = m["rsi"].values.astype(float)
    wa = m["weighted_alpha"].fillna(0).values.astype(float)
    sk = m["streak"].fillna(0).values.astype(float)
    st_sig = m["atr_signal"].fillna(0).values.astype(float)
    ac_sig = m["accel_signal"].fillna(0).values.astype(float)
    st_xa = m["atr_crossed_above"].fillna(0).values.astype(bool)
    st_xb = m["atr_crossed_below"].fillna(0).values.astype(bool)
    ac_cu = m["accel_crossed_up"].fillna(0).values.astype(bool)
    ac_cd = m["accel_crossed_down"].fillna(0).values.astype(bool)
    at_vec = m["atrp"].fillna(0).values.astype(float)
    p1 = m["prob_up_1d"].fillna(50).values.astype(float)
    vr = m["vol_ratio"].values.astype(float)
    vs = m["vol_spike"].values.astype(bool)
    pr = m["close"].values.astype(float)
    hh = m["h20"].values.astype(float)
    ll = m["l20"].values.astype(float)
    s20 = m["sma20"].values.astype(float)
    s50 = m["sma50"].values.astype(float)

    wa_norm = _tanh(wa / 15.0)
    streak_amp = 1.0 + 0.3 * _tanh(sk / 3.0)
    wa_component = wa_norm * streak_amp
    trend_component = (st_sig + ac_sig) * 0.5
    rsi_component = (rsi - 50.0) / 20.0
    D = (wa_component + trend_component + rsi_component) / 3.0

    raw_cross = st_sig + ac_sig
    any_cross = st_xa | st_xb | ac_cu | ac_cd
    boost = 1.0 + 0.5 * any_cross.astype(float)
    X = raw_cross * 0.5 * boost

    log_ratio = _log(np.maximum(vr, 0.01))
    spike_impulse = 0.3 * vs.astype(float)
    V = _tanh((log_ratio + spike_impulse) * 2.0)

    oversold = _sig((50.0 - rsi) / 10.0)
    vol_confirm = _sig((at_vec - 3.0) / 1.5)
    B = oversold * vol_confirm * 2.0 - 1.0

    p_clipped = _clip(p1 / 100.0, 1e-6, 1.0 - 1e-6)
    P = np.log(p_clipped / (1.0 - p_clipped))

    z = 1.20 * D + 0.40 * X + 0.35 * V + 0.25 * B + 0.30 * P

    ma_valid = (s20 > 0) & (s50 > 0)
    z = np.where(ma_valid, z + 0.15 * _tanh((s20 - s50) / (0.05 * s50 + 1e-9)), z)

    rng_valid = (hh > ll) & (pr > 0)
    pos = np.where(rng_valid, (pr - ll) / (hh - ll + 1e-9), 0.0)
    range_hint = 0.10 * (pos - 0.5) * 2.0
    aligned = ((wa > 0) & (pos > 0.5)) | ((wa < 0) & (pos < 0.5))
    z = np.where(rng_valid & aligned, z + range_hint, z)
    z = np.where(rng_valid & ~aligned, z - range_hint * 0.5, z)

    ai_matrix = np.round(100.0 * _sig(z), 2)
    ai_overall_score = ai_matrix
    ai_conclusion = np.select(
        [ai_matrix > 60, ai_matrix < 40],
        ["BUY", "SELL"],
        default="HOLD",
    )
    confluence = vectorized_confluence(st_sig, ac_sig, wa, sk, p1)

    return ai_matrix, ai_overall_score, ai_conclusion, confluence, m["symbol"].values, m["date"].values


def backfill(market="US", sym_batch=400, update_chunk=100000, limit_symbols=None):
    conn = get_db(market)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=120000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-200000")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("PRAGMA foreign_keys=OFF")

        logger.info("[%s] Dropping secondary indexes for bulk write", market)
        for idx in SECONDARY_INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS {idx}")
        conn.commit()

        logger.info("[%s] Getting symbol list", market)
        sym_rows = conn.execute(
            "SELECT DISTINCT symbol FROM historical_screener"
        ).fetchall()
        symbols = [r[0] for r in sym_rows]
        if limit_symbols is not None:
            symbols = symbols[:limit_symbols]
        total = len(symbols)
        logger.info("[%s] Symbols to process: %d", market, total)

        updated_rows = 0
        t0 = time.time()

        for start in range(0, total, sym_batch):
            batch_syms = symbols[start:start + sym_batch]
            done = min(start + sym_batch, total)

            ph = ",".join("?" * len(batch_syms))
            hist = pd.read_sql(
                f"SELECT {', '.join(HIST_COLS)} FROM historical_screener "
                f"WHERE symbol IN ({ph}) ORDER BY symbol, date",
                conn, params=list(batch_syms),
            )
            if hist.empty:
                continue
            hist["date"] = hist["date"].map(_to_datestr)

            bars = pd.read_sql(
                f"SELECT symbol, date, open, high, low, close, volume "
                f"FROM bars WHERE timeframe='1Day' AND symbol IN ({ph}) "
                f"ORDER BY symbol, date",
                conn, params=list(batch_syms),
            )
            if bars.empty:
                continue
            bars["date"] = bars["date"].map(_to_datestr)

            feat = compute_bar_features(bars)
            ai_matrix, ai_overall, ai_concl, conf, syms, dates = compute_scores(hist, feat)

            rows = [
                (float(m_), float(o_), str(c_), float(cf), str(s_), str(d_))
                for m_, o_, c_, cf, s_, d_ in zip(
                    ai_matrix, ai_overall, ai_concl, conf, syms, dates
                )
            ]

            for j in range(0, len(rows), update_chunk):
                conn.executemany(UPDATE_SQL, rows[j:j + update_chunk])
            conn.commit()
            updated_rows += len(rows)

            elapsed = time.time() - t0
            rate = updated_rows / elapsed if elapsed > 0 else 0
            logger.info(
                "[%s] %d/%d symbols | rows=%d | %.0f rows/s | ETA %.1f min",
                market, done, total, updated_rows, rate,
                (total - done) / (done / elapsed / sym_batch) / 60 if done > 0 else 0,
            )

        logger.info("[%s] Recreating secondary indexes", market)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hs_sym_date ON historical_screener(symbol, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hs_date ON historical_screener(date)")
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
                logger.warning("[%s] WAL checkpoint deferred (server holds read lock)", market)
        conn.commit()

        final_counts = conn.execute(
            "SELECT ai_conclusion, COUNT(*) FROM historical_screener GROUP BY ai_conclusion"
        ).fetchall()
        logger.info("[%s] DONE. rows=%d conclusion=%s version=%s",
                    market, updated_rows, dict(final_counts), HISTORICAL_SCREENER_VERSION)
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="Combined single-pass recompute of historical_screener AI/confluence")
    ap.add_argument("--market", default="US", choices=["US", "INDIA"])
    ap.add_argument("--all-markets", action="store_true", help="run US then INDIA sequentially")
    ap.add_argument("--sym-batch", type=int, default=400, help="symbols per read/compute/update cycle")
    ap.add_argument("--update-chunk", type=int, default=100000, help="rows per executemany commit")
    ap.add_argument("--kill-pids", default="", help="comma-separated PIDs of competing backfills to kill")
    ap.add_argument("--limit-symbols", type=int, default=None, help="process only first N symbols (smoke test)")
    args = ap.parse_args()

    if args.kill_pids:
        kill_pids([p.strip() for p in args.kill_pids.split(",") if p.strip()])
        time.sleep(2)

    markets = ["US", "INDIA"] if args.all_markets else [args.market]
    for mkt in markets:
        backfill(
            market=mkt,
            sym_batch=args.sym_batch,
            update_chunk=args.update_chunk,
            limit_symbols=args.limit_symbols,
        )


if __name__ == "__main__":
    main()
