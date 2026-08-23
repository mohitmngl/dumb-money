"""Deep-history chain (main guard required for Windows spawn):
waits for post_cleanup_rebuild "ALL DONE" -> string-table cleanup ->
India full-history download (period1=0) -> US backfill-to-2016 ->
INDIA+US historical force rebuilds + signal matrices."""
import os, subprocess, sys, time, logging
from multiprocessing import freeze_support

def wait_all_done(timeout_s=8 * 3600):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with open("post_cleanup_rebuild.log", "r", encoding="utf-8", errors="ignore") as f:
                if "ALL DONE" in f.read():
                    return True
        except FileNotFoundError:
            pass
        time.sleep(120)
    return False

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler("deep_history.log"), logging.StreamHandler()])
    log = logging.getLogger("deep-hist")

    log.info("waiting for main chain (post_cleanup_rebuild) to finish...")
    if not wait_all_done():
        log.error("main chain did not finish within 8h; aborting deep-history chain")
        return
    log.info("main chain finished")

    # 1) leftover string-table cleanup (idempotent)
    log.info("[1/5] fast string cleanup")
    try:
        subprocess.run([sys.executable, "_fast_string_cleanup.py"], check=True, timeout=7200)
    except Exception as e:
        log.error(f"cleanup failed: {e}")

    from dumbmoney.db import get_db
    from dumbmoney.engine import update_historical_screener, update_signal_prob_matrix

    def prog(pct, msg):
        p = int(pct)
        if p % 10 == 0:
            log.info(f"  {p}% {msg}")

    # 2) INDIA full history (period1=0 after data_india edit)
    log.info("[2/5] india full-history download")
    try:
        from dumbmoney.data_india import download_bars_india
        conn = get_db("INDIA")
        try:
            syms = [r[0] for r in conn.execute(
                "SELECT DISTINCT symbol FROM bars WHERE timeframe='1Day'").fetchall()]
        finally:
            conn.close()
        log.info(f"  downloading {len(syms)} india symbols with period1=0")
        download_bars_india(symbols=sorted(syms), start_date=None,
                            progress_callback=lambda d, t: log.info(f"  india dl {d}/{t}") if d % 500 == 0 else None)
    except Exception as e:
        log.error(f"india download failed: {e}")

    # 3) US deep backfill to 2016 via allow_backfill grouping
    log.info("[3/5] us backfill-to-2016 download")
    try:
        from dumbmoney.refresh import _download_us_bars_incremental
        _download_us_bars_incremental("US", allow_backfill=True)
        log.info("  us backfill download done")
    except Exception as e:
        log.error(f"us backfill failed: {e}")

    # 4)+5) historical force rebuilds (include the older dates) + signal matrices
    for market in ("INDIA", "US"):
        dbf = "india.db" if market == "INDIA" else "screener.db"
        log.info(f"[4/5] [{market}] historical force rebuild (deep dates)")
        try:
            update_historical_screener(market, progress_callback=prog, force_rebuild=True)
            update_signal_prob_matrix(market, progress_callback=prog)
            log.info(f"[{market}] historical + matrix done ({dbf})")
        except Exception as e:
            log.error(f"[{market}] historical rebuild failed: {e}")

    log.info("DEEP HISTORY ALL DONE")

if __name__ == "__main__":
    freeze_support()
    main()
