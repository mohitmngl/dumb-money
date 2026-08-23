import time
import json
from datetime import datetime
from . import db
from . import data

POSITION_NOTIONAL = 100
MAX_POSITIONS = 10
MIN_VOLUME = 100000
MIN_BARS = 15

def get_entry_signals(stocks_data, volume_map=None):
    entries = []
    for sym, info in stocks_data.items():
        if info is None:
            continue
        daily_vol = 0
        if volume_map and sym in volume_map:
            daily_vol = volume_map[sym]
        elif info['last_volume'] > 0:
            daily_vol = info['last_volume'] * 390

        if info['direction'] == 1 and daily_vol >= MIN_VOLUME:
            entries.append({
                'symbol': sym,
                'price': info['last_close'],
                'stop': info['supertrend'],
                'target': info['last_close'] + 2 * (info['last_close'] - info['supertrend']),
                'atr': info['atr'],
                'atrp': info['atrp'],
                'volume': daily_vol,
                'distance': info['last_close'] - info['supertrend']
            })
    entries.sort(key=lambda x: x['distance'] / max(x['atr'], 0.01), reverse=True)
    return entries

def get_exit_signals(open_positions, stocks_data, live_prices=None):
    exits = []
    for pos in open_positions:
        sym = pos['symbol']
        exit_reason = None
        current_price = None

        if live_prices and sym in live_prices:
            current_price = live_prices[sym]['price']

        if sym in stocks_data and stocks_data[sym] is not None:
            info = stocks_data[sym]
            if current_price is None:
                current_price = info['last_close']
            if info['direction'] == -1:
                exit_reason = 'supertrend_cross'

        if current_price is None:
            continue

        if current_price >= pos['target_price']:
            exit_reason = 'target_hit'

        if current_price < pos['stop_price']:
            exit_reason = 'stop_hit'

        if exit_reason:
            pnl = (current_price - pos['entry_price']) * pos['qty']
            exits.append({
                'position_id': pos['id'],
                'symbol': sym,
                'exit_price': current_price,
                'exit_reason': exit_reason,
                'pnl': pnl,
                'entry_price': pos['entry_price'],
                'stop': pos['stop_price'],
                'target': pos['target_price']
            })
    return exits

def execute_entries(entries, open_count):
    import time as _time
    slots = MAX_POSITIONS - open_count
    if slots <= 0:
        return []
    executed = []
    for entry in entries[:slots]:
        sym = entry['symbol']
        existing = db.get_open_positions()
        if any(p['symbol'] == sym for p in existing):
            continue
        try:
            result = data.fire_order(sym, POSITION_NOTIONAL, 'buy')
            order_id = result.get('id')

            filled_price = float(result.get('filled_avg', 0)) if result.get('filled_avg') else 0
            filled_qty = float(result.get('filled_qty', 0)) if result.get('filled_qty') else 0

            if filled_qty == 0 and order_id:
                for _ in range(5):
                    _time.sleep(1)
                    status = data.get_order(order_id)
                    filled_price = float(status.get('filled_avg', 0)) if status.get('filled_avg') else 0
                    filled_qty = float(status.get('filled_qty', 0)) if status.get('filled_qty') else 0
                    if filled_qty > 0:
                        break

            if filled_qty == 0:
                filled_qty = POSITION_NOTIONAL / entry['price']
            if filled_price == 0:
                filled_price = entry['price']

            stop = entry['stop']
            target = entry['target']

            db.open_position(
                symbol=sym,
                entry_price=filled_price,
                stop_price=stop,
                target_price=target,
                qty=filled_qty,
                notional=POSITION_NOTIONAL,
                order_id=result.get('id')
            )
            executed.append({
                'symbol': sym,
                'price': filled_price,
                'qty': filled_qty,
                'stop': stop,
                'target': target,
                'order_id': result.get('id')
            })
            print(f"    BUY {sym}: {filled_qty:.4f} @ ${filled_price:.2f} | stop=${stop:.2f} target=${target:.2f}")
        except Exception as e:
            print(f"    BUY {sym} FAILED: {e}")
    return executed

def execute_exits(exits):
    executed = []
    for exit in exits:
        sym = exit['symbol']
        try:
            pos = None
            for p in db.get_open_positions():
                if p['id'] == exit['position_id']:
                    pos = p
                    break
            if not pos:
                continue

            sell_qty = abs(pos['qty'])
            body = {
                'symbol': sym,
                'qty': str(sell_qty),
                'side': 'sell',
                'type': 'market',
                'time_in_force': 'day'
            }
            result = data.api_post('/v2/orders', body)

            exit_price = float(result.get('filled_avg', exit['exit_price'])) if result and result.get('filled_avg') else exit['exit_price']
            pnl = (exit_price - pos['entry_price']) * pos['qty']

            db.close_position(
                position_id=pos['id'],
                exit_price=exit_price,
                exit_reason=exit['exit_reason'],
                pnl=pnl
            )
            executed.append({
                'symbol': sym,
                'exit_price': exit_price,
                'reason': exit['exit_reason'],
                'pnl': pnl
            })
            emoji = "+" if pnl >= 0 else ""
            print(f"    SELL {sym}: ${exit_price:.2f} | {exit['exit_reason']} | PnL: {emoji}${pnl:.2f}")
        except Exception as e:
            print(f"    SELL {sym} FAILED: {e}")
    return executed
