"""Recompute crypto stats + historical screener so r_squared gets populated.

One-off: crypto-v3 added r_squared to both compute paths; this backfills the
existing tables. Safe to re-run (idempotent, INSERT OR REPLACE).
"""
import multiprocessing
import sys


def main():
    from dumbmoney.engine import compute_crypto_stats_batch, update_crypto_historical_screener

    def prog(done, total):
        if isinstance(total, int):
            print(f"[stats] {done}/{total}", flush=True)
        else:
            print(f"[hist] {done}% {total}", flush=True)

    n = compute_crypto_stats_batch(progress_callback=prog)
    print(f"STATS DONE: {n} rows", flush=True)

    update_crypto_historical_screener(force_rebuild=True, progress_callback=prog)
    print("HIST DONE", flush=True)

    import sqlite3
    c = sqlite3.connect("file:crypto.db?mode=ro", uri=True)
    tot, nn = c.execute("SELECT COUNT(*), SUM(r_squared != 0) FROM crypto_stats").fetchone()
    htot, hnn = c.execute("SELECT COUNT(*), SUM(r_squared != 0) FROM crypto_historical_screener").fetchone()
    print(f"VERIFY stats: {nn}/{tot} nonzero r2 | hist: {hnn}/{htot} nonzero r2", flush=True)
    c.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
