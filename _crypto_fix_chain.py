"""Crypto repair chain: refresh bars -> deep history backfill -> stats (ABORT if 0) -> historical rebuild -> live columns."""
import sys, logging
from multiprocessing import freeze_support

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler("crypto_fix_chain.log"), logging.StreamHandler()])
    log = logging.getLogger("crypto-fix")
    sys.path.insert(0, ".")

    from dumbmoney.data_crypto import (
        get_all_symbols, download_candles, TIMEFRAMES,
        backfill_history, update_live_columns,
    )
    from dumbmoney.engine import compute_crypto_stats_batch, update_crypto_historical_screener
    from concurrent.futures import ThreadPoolExecutor, as_completed

    symbols = get_all_symbols()
    log.info(f"[1/5] forward refresh {len(symbols)} symbols x {len(TIMEFRAMES)} timeframes")
    jobs = [(s, tf) for tf in TIMEFRAMES for s in symbols]
    n_bars = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(download_candles, s, tf, TIMEFRAMES[tf]) for s, tf in jobs]
        for i, f in enumerate(as_completed(futs), 1):
            try:
                n_bars += f.result()
            except Exception as e:
                log.warning(f"  refresh job failed: {e}")
            if i % 400 == 0:
                log.info(f"  refresh {i}/{len(jobs)} (+{n_bars} bars)")
    log.info(f"[1/5] refresh done (+{n_bars} bars)")

    log.info("[2/5] backward history backfill (1d/1w to API floor)")
    def bprog(pct, msg):
        if int(pct) % 40 == 0:
            log.info(f"  backfill {pct:.0f}% {msg}")
    added = backfill_history(progress_callback=bprog)
    log.info(f"[2/5] backfill done (+{added} older bars)")

    log.info("[3/5] crypto stats recompute (ATR 2x)")
    n = compute_crypto_stats_batch(progress_callback=lambda d, t: None)
    if n == 0:
        log.error("stats recompute returned 0 symbols - ABORTING (would leave stale live table)")
        return
    log.info(f"[3/5] stats done: {n} symbols")

    log.info("[4/5] crypto historical rebuild (force, includes backfilled dates)")
    state = {"pct": -1}
    def hprog(pct, msg):
        p = int(pct)
        if p != state["pct"] and p % 10 == 0:
            state["pct"] = p
            log.info(f"  hist {p}% {msg}")
    update_crypto_historical_screener(force_rebuild=True, progress_callback=hprog)
    log.info("[4/5] historical done")

    n = update_live_columns()
    log.info(f"[5/5] live columns updated for {n} symbols")
    log.info("CRYPTO FIX CHAIN DONE")

if __name__ == "__main__":
    freeze_support()
    main()
