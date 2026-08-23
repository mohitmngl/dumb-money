import time
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_bot import db
from trading_bot import data
from trading_bot import engine

SCAN_INTERVAL = 60
UNIVERSE_REFRESH_INTERVAL = 3600
DEFAULT_UNIVERSE = [
    'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AMD','NFLX','BABA',
    'SPY','QQQ','JPM','V','UNH','MA','JNJ','WMT','PG','XOM',
    'HD','COST','ABBV','MRK','PEP','KO','AVGO','LLY','CRM','TMO',
    'ACN','ORCL','NKE','ADBE','TXN','QCOM','INTC','CSCO','PFE','DIS',
    'PYPL','UBER','SQ','COIN','PLTR','SOFI','RIVN','LCID','HOOD','RBLX',
    'AAOI','ABSI','AXTI','BE','BFLY','BMNG','BTDR','CBRS','FCEL','FLNC',
    'FRMI','MSTZ','MXL','NBIZ','NVTS','OUST','PENG','POET','RXT','SLS',
    'SNXX','SOXL','SPCH','TE','WOLF','WYFI'
]

def get_universe():
    cached = db.get_universe()
    if cached:
        return [s for s, v in cached]

    last = db.get_setting('last_universe_refresh')
    if last:
        try:
            elapsed = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
            if elapsed < UNIVERSE_REFRESH_INTERVAL:
                return cached if cached else DEFAULT_UNIVERSE
        except:
            pass

    try:
        print("  Refreshing universe from Alpaca...")
        assets = data.api_get('/v2/assets?status=active&asset_class=us_equity')
        stocks = [a for a in assets if a.get('class') == 'us_equity' and a.get('tradable')]
        snapshots = data.get_snapshots([a['symbol'] for a in stocks[:200]])

        universe = []
        for a in stocks[:200]:
            sym = a['symbol']
            snap = snapshots.get(sym, {})
            vol = snap.get('dailyBar', {}).get('v', 0)
            if vol and vol > 0:
                universe.append((sym, vol))

        universe.sort(key=lambda x: x[1], reverse=True)
        top = universe[:50]

        if top:
            db.update_universe(top)
            db.set_setting('last_universe_refresh', datetime.now().isoformat())
            print(f"  Universe: {len(top)} stocks (top volume)")
            return [s for s, v in top]
    except Exception as e:
        print(f"  Universe refresh failed: {e}")

    return DEFAULT_UNIVERSE

def run_cycle(cycle_num, universe):
    t0 = time.time()
    now = datetime.now()
    print(f"\n[{now.strftime('%H:%M:%S')}] Cycle #{cycle_num}")

    clock = data.get_clock()
    if not clock.get('is_open', False):
        print(f"  Market closed. Next open: {clock.get('next_open')}")
        return False

    open_positions = db.get_open_positions()
    open_count = len(open_positions)
    print(f"  Open positions: {open_count}/{engine.MAX_POSITIONS}")
    for p in open_positions:
        print(f"    {p['symbol']}: entry=${p['entry_price']:.2f} stop=${p['stop_price']:.2f} target=${p['target_price']:.2f}")

    print(f"  Fetching 1-min bars for {len(universe)} stocks...")
    t1 = time.time()
    stocks_data = data.fetch_1min_bars_batch(universe, limit=50)
    t2 = time.time()
    print(f"  Got bars for {len(stocks_data)} stocks in {t2-t1:.1f}s")

    live_prices = {}
    pos_syms = [p['symbol'] for p in open_positions]
    try:
        live_prices = data.fetch_latest_trades(pos_syms if pos_syms else universe[:10])
        print(f"  Live prices: {len(live_prices)} stocks")
    except Exception as e:
        print(f"  Live price fetch failed: {e}")

    analyzed = {}
    for sym, bars in stocks_data.items():
        result = data.analyze_stock(bars)
        if result:
            if sym in live_prices:
                result['last_close'] = live_prices[sym]['price']
            result['symbol'] = sym
            analyzed[sym] = result

    for sym in pos_syms:
        if sym not in analyzed and sym in live_prices:
            analyzed[sym] = {
                'symbol': sym,
                'last_close': live_prices[sym]['price'],
                'direction': 0,
                'supertrend': 0,
                'atr': 0,
                'atrp': 0,
                'last_volume': 0,
                'crossed_above': False,
                'crossed_below': False
            }

    print(f"  Analyzed: {len(analyzed)} stocks")

    for sym, info in list(analyzed.items())[:5]:
        dir_str = "BULL" if info.get('direction', 0) == 1 else "BEAR" if info.get('direction', 0) == -1 else "FLAT"
        live = live_prices.get(sym, {}).get('price', 0)
        print(f"    {sym}: live=${live:.2f} bar=${info.get('last_close',0):.2f} ST=${info.get('supertrend',0):.2f} [{dir_str}]")

    volume_map = {s: v for s, v in db.get_universe()}

    exits = engine.get_exit_signals(open_positions, analyzed, live_prices)
    if exits:
        print(f"\n  EXIT SIGNALS ({len(exits)}):")
        exit_results = engine.execute_exits(exits)
    else:
        exit_results = []

    open_count = db.get_open_count()
    entries = engine.get_entry_signals(analyzed, volume_map)
    bullish = [e for e in entries if e['distance'] > 0]
    if bullish:
        print(f"\n  ENTRY SIGNALS ({len(bullish)} bullish, {min(len(bullish), engine.MAX_POSITIONS - open_count)} slots):")
        entry_results = engine.execute_entries(bullish, open_count)
    else:
        entry_results = []

    elapsed = time.time() - t0
    print(f"\n  Cycle time: {elapsed:.1f}s | Entries: {len(entry_results)} | Exits: {len(exit_results)}")
    return True

def print_summary():
    trades = db.get_trades(limit=20)
    if not trades:
        print("\n  No trades yet.")
        return

    total_pnl = sum(t['pnl'] or 0 for t in trades)
    wins = sum(1 for t in trades if (t['pnl'] or 0) > 0)
    losses = sum(1 for t in trades if (t['pnl'] or 0) < 0)
    avg_dur = sum(t['duration_sec'] or 0 for t in trades) / len(trades) if trades else 0

    print(f"\n{'='*60}")
    print(f"  TRADING SUMMARY (last {len(trades)} trades)")
    print(f"{'='*60}")
    print(f"  Total PnL: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}")
    print(f"  Win/Loss: {wins}W / {losses}L ({wins/(wins+losses)*100:.0f}% win rate)" if (wins+losses) > 0 else "  Win/Loss: 0/0")
    print(f"  Avg Duration: {avg_dur:.0f}s ({avg_dur/60:.1f}min)")
    print(f"\n  Recent trades:")
    for t in trades[:10]:
        pnl = t['pnl'] or 0
        emoji = "+" if pnl >= 0 else ""
        dur = t['duration_sec'] or 0
        print(f"    {t['symbol']:>6} {t['entry_time'][:19]} -> {t['exit_time'][:19] if t['exit_time'] else 'OPEN'} | {t['exit_reason']:>15} | {emoji}{pnl:.2f} | {dur:.0f}s")
    print(f"{'='*60}")

def main():
    print("=" * 60)
    print("  HFT TRADING BOT - 1-MIN SCALPER")
    print("  SuperTrend(14,3) on 1-min bars")
    print(f"  Position: ${engine.POSITION_NOTIONAL} | Max: {engine.MAX_POSITIONS}")
    print(f"  Entry: Price > SuperTrend | Exit: Price < SuperTrend or 2x RR")
    print(f"  Scan interval: {SCAN_INTERVAL}s")
    print("=" * 60)

    db.init_db()

    clock = data.get_clock()
    print(f"  Market: {'OPEN' if clock.get('is_open') else 'CLOSED'}")
    acct = data.get_account()
    print(f"  Equity: ${acct.get('equity', '0')} | BP: ${acct.get('buying_power', '0')}")

    universe = get_universe()
    print(f"  Universe: {len(universe)} stocks")

    cycle = 0
    while True:
        cycle += 1
        t_cycle = time.time()
        try:
            if cycle % 30 == 0:
                print_summary()

            if cycle % 60 == 0:
                universe = get_universe()

            running = run_cycle(cycle, universe)
            if not running:
                print(f"  Market closed. Sleeping 60s...")
                time.sleep(60)
                continue

            elapsed = time.time() - t_cycle
            wait = max(0, SCAN_INTERVAL - elapsed)
            if wait > 0:
                time.sleep(wait)

        except KeyboardInterrupt:
            print("\n  Stopping bot...")
            break
        except Exception as e:
            print(f"\n  ERROR: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(10)

    print_summary()

if __name__ == '__main__':
    main()
