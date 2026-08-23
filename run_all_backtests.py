"""
FINAL: Big-to-small candle order. 1M batches. Max history. Saves each result.
"""
import sys, os, time, json, logging, gc
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', handlers=[logging.StreamHandler()])
logger = logging.getLogger("run_all")

from intraday_backtest.config import init_db, get_db, MAX_DAYS_BACK
from intraday_backtest.data import get_top_liquid_symbols, get_bar_dates, get_cached_bars
from intraday_backtest.backtest import run_backtest, _sanitize_for_json
from intraday_backtest.metrics import compute_all_metrics
from datetime import datetime, timedelta, timezone

N_BATCHES = 1_000_000
CAPITAL = 10000.0

# Big to small candles
TIMEFRAME_ORDER = ["1Day", "1Hour", "30Min", "15Min", "5Min", "1Min"]

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_results.json")

def save_results(all_results):
    with open(RESULTS_FILE, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

def build_price_matrix(used_symbols, timestamps, tf):
    cached = get_cached_bars(used_symbols, tf)
    price_matrix, final_syms = [], []
    for sym in used_symbols:
        if sym not in cached:
            continue
        sym_prices = {row[0]: row[1] for row in cached[sym]}
        col = [sym_prices.get(ts, 0) for ts in timestamps]
        if sum(1 for p in col if p > 0) >= len(col) * 0.9:
            last_good = 0
            for i, p in enumerate(col):
                if p > 0:
                    last_good = p
                elif last_good > 0:
                    col[i] = last_good
            if all(p > 0 for p in col):
                price_matrix.append(col)
                final_syms.append(sym)
    return price_matrix, final_syms

def main():
    init_db()
    symbols = get_top_liquid_symbols(200)
    logger.info(f"Symbols: {len(symbols)}")

    all_results = {}

    for tf in TIMEFRAME_ORDER:
        logger.info(f"\n{'='*50}")
        logger.info(f"  {tf} — 1M batches, max history")
        logger.info(f"{'='*50}")

        try:
            days_back = MAX_DAYS_BACK.get(tf, 3650)

            t0 = time.time()
            timestamps, used_syms = get_bar_dates(symbols, tf, days_back=days_back)
            t_get = time.time() - t0

            if len(timestamps) < 20:
                logger.warning(f"  SKIP: Only {len(timestamps)} timestamps")
                all_results[tf] = {"error": f"Only {len(timestamps)} timestamps"}
                save_results(all_results)
                continue

            logger.info(f"  Timestamps: {len(timestamps)} ({t_get:.1f}s)")

            t0 = time.time()
            pm, fsyms = build_price_matrix(used_syms, timestamps, tf)
            t_build = time.time() - t0

            if len(fsyms) < 10:
                logger.warning(f"  SKIP: Only {len(fsyms)} symbols with data")
                all_results[tf] = {"error": f"Only {len(fsyms)} symbols"}
                save_results(all_results)
                continue

            import numpy as np
            pm = np.array(pm).T
            n_stocks = min(200, len(fsyms))
            fsyms = fsyms[:n_stocks]
            pm = pm[:, :n_stocks]
            valid = np.all(pm > 0, axis=1)
            timestamps = [timestamps[i] for i in range(len(timestamps)) if valid[i]]
            pm = pm[valid]

            logger.info(f"  Matrix: {n_stocks} stocks x {len(timestamps)} candles ({t_build:.1f}s)")

            t0 = time.time()
            result = run_backtest(
                symbols=fsyms, timestamps=timestamps, price_matrix=pm,
                timeframe=tf, n_batches=N_BATCHES, capital=CAPITAL,
                margin=1, charges=False,
            )
            t_bt = time.time() - t0

            logger.info(f"  Backtest: {t_bt:.0f}s ({t_bt/len(timestamps)*1000:.0f}ms/candle)")

            metrics = compute_all_metrics(result, CAPITAL)
            result["metrics"] = metrics

            b = metrics.get("basic", {})
            r = metrics.get("risk", {})
            d = metrics.get("distribution", {})

            logger.info(f"  Return: {b.get('total_return_pct')} | Sharpe: {r.get('sharpe_ratio',0):.4f} | MaxDD: {r.get('max_drawdown_pct')} | WinRate: {d.get('win_rate_pct')} | PF: {d.get('profit_factor')} | Equity: ${b.get('final_equity',0):,.2f}")

            conn = get_db()
            conn.execute(
                """INSERT INTO saved_results
                   (timeframe, n_stocks, n_batches, capital, margin, charges, days_back,
                    candles_processed, total_return_pct, sharpe_ratio, max_drawdown_pct,
                    win_rate_pct, profit_factor, n_signals_avg, result_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (tf, n_stocks, N_BATCHES, CAPITAL, 1, 0, days_back,
                 b.get("candles_processed", 0), b.get("total_return", 0),
                 r.get("sharpe_ratio", 0), r.get("max_drawdown", 0),
                 d.get("win_rate", 0), d.get("profit_factor", 0),
                 result.get("n_signals_avg", 0),
                 json.dumps(_sanitize_for_json(metrics)))
            )
            conn.commit()
            conn.close()

            all_results[tf] = {
                "status": "ok", "candles": len(timestamps), "stocks": n_stocks,
                "return_pct": b.get("total_return_pct"), "sharpe": r.get("sharpe_ratio", 0),
                "max_dd": r.get("max_drawdown_pct"), "win_rate": d.get("win_rate_pct"),
                "pf": d.get("profit_factor"), "equity": b.get("final_equity"),
                "time_s": t_bt, "ms_per_candle": t_bt/len(timestamps)*1000,
            }

        except Exception as e:
            logger.exception(f"  FAILED: {e}")
            all_results[tf] = {"error": str(e)}

        save_results(all_results)
        gc.collect()

    logger.info("\n" + "="*60)
    logger.info("SUMMARY")
    logger.info("="*60)
    for tf in TIMEFRAME_ORDER:
        r = all_results.get(tf, {})
        if "error" in r:
            logger.info(f"  {tf}: ERROR - {r['error']}")
        else:
            logger.info(f"  {tf}: {r['candles']} candles | {r['return_pct']} | Sharpe {r['sharpe']:.4f} | DD {r['max_dd']} | Win {r['win_rate']} | PF {r['pf']} | {r['time_s']:.0f}s ({r['ms_per_candle']:.0f}ms/c)")

    save_results(all_results)
    logger.info("DONE")

if __name__ == "__main__":
    main()
