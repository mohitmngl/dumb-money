"""US BTST Walk-Forward Optimization - main entry point."""
import sys, os, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prepare_data import load_us_data, load_us_data_smoke
from wfo_engine import run_full_wfo
from reporting import aggregate_oos, parameter_stability, print_summary, save_results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="US Market BTST Walk-Forward Optimization")
    parser.add_argument("--smoke", action="store_true", help="Run smoke test: 3 months, 100 stocks")
    parser.add_argument("--full", action="store_true", help="Run full WFO: 2 years, all non-OTC stocks")
    parser.add_argument("--output-dir", default=None, help="Output directory for results")
    args = parser.parse_args()

    if args.smoke:
        print("=" * 70)
        print("US WFO SMOKE TEST: 3 months, 100 stocks")
        print("=" * 70)
        t0 = time.time()
        data = load_us_data_smoke()
        print("Data load time: %.1fs" % (time.time() - t0))

        def progress_cb(fold, tr_s, tr_e, te_s, te_e):
            print("  Fold %d: train %s -> %s, test %s -> %s" % (fold + 1, tr_s, tr_e, te_s, te_e))

        t1 = time.time()
        folds = run_full_wfo(data, initial_train_months=1, test_window_months=1, min_trades=5, progress_callback=progress_cb)
        print("WFO time: %.1fs" % (time.time() - t1))

        agg = aggregate_oos(folds)
        stability = parameter_stability(folds)
        print_summary(folds, agg, stability)

        out = args.output_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "us_wfo_results", "smoke")
        save_results(folds, agg, stability, out)

    elif args.full:
        print("=" * 70)
        print("US WFO FULL: 2 years, all non-OTC stocks")
        print("=" * 70)
        t0 = time.time()
        data = load_us_data()
        print("Data load time: %.1fs" % (time.time() - t0))

        def progress_cb(fold, tr_s, tr_e, te_s, te_e):
            print("  Fold %d: train %s -> %s, test %s -> %s" % (fold + 1, tr_s, tr_e, te_s, te_e))

        t1 = time.time()
        # Use top 300 stocks by dollar volume for practical full run
        top_stocks = data.groupby('symbol')['dollar_volume'].mean().sort_values(ascending=False).head(300).index.tolist()
        data_top = data[data['symbol'].isin(top_stocks)].copy()
        print('  Top 300 stocks: %d rows' % len(data_top))
        folds = run_full_wfo(data_top, initial_train_months=6, test_window_months=1, step_months=3, min_trades=20, progress_callback=progress_cb)
        print("WFO time: %.1fs" % (time.time() - t1))

        agg = aggregate_oos(folds)
        stability = parameter_stability(folds)
        print_summary(folds, agg, stability)

        out = args.output_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "us_wfo_results", "full")
        save_results(folds, agg, stability, out)

    else:
        print("No mode selected. Use --smoke or --full.")
        print("Example: python us_wfo/run.py --smoke")
        sys.exit(1)


if __name__ == "__main__":
    main()
