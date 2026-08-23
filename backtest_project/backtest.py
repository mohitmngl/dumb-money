import numpy as np
from .indicators import compute_supertrend, find_st_crosses

class Trade:
    def __init__(self, symbol, entry_price, entry_index, stop, target, size=100):
        self.symbol = symbol
        self.entry_price = entry_price
        self.entry_index = entry_index
        self.stop = stop
        self.target = target
        self.size = size
        self.exit_price = None
        self.exit_index = None
        self.exit_reason = None
        self.pnl = 0
        self.return_pct = 0

    def close(self, exit_price, exit_index, reason):
        self.exit_price = exit_price
        self.exit_index = exit_index
        self.exit_reason = reason
        self.pnl = (exit_price - self.entry_price) / self.entry_price * self.size
        self.return_pct = (exit_price - self.entry_price) / self.entry_price * 100

class BacktestEngine:
    def __init__(self, all_bars, max_trades=500, invest_per_trade=100):
        self.all_bars = all_bars
        self.max_trades = max_trades
        self.invest_per_trade = invest_per_trade

    def _prepare_st(self, bars):
        closes = [b['c'] for b in bars]
        highs = [b['h'] for b in bars]
        lows = [b['l'] for b in bars]
        st, direction, atr = compute_supertrend(highs, lows, closes, period=14, multiplier=3.0)
        return closes, highs, lows, st, direction, atr

    def run_individual(self, strategy_name, bars_dict):
        trades = []
        for sym, bars in bars_dict.items():
            closes, highs, lows, st, direction, atr = self._prepare_st(bars)
            if st is None:
                continue
            crosses = find_st_crosses(closes, st, direction)
            cross_ups = [c for c in crosses if c['type'] == 'cross_up']
            for cross in cross_ups:
                if len(trades) >= self.max_trades:
                    break
                idx = cross['index']
                if idx >= len(closes) - 1:
                    continue
                entry_price = closes[idx]
                stop = st[idx]
                risk = entry_price - stop
                if risk <= 0:
                    continue
                target = entry_price + 2 * risk

                trade = self._simulate_exit(
                    sym, entry_price, idx, stop, target, closes, highs, lows, st, direction, strategy_name
                )
                if trade:
                    trades.append(trade)
        return trades[:self.max_trades]

    def _simulate_exit(self, sym, entry_price, entry_idx, stop, target, closes, highs, lows, st, direction, strategy):
        n = len(closes)
        trade = Trade(sym, entry_price, entry_idx, stop, target, self.invest_per_trade)

        for i in range(entry_idx + 1, min(entry_idx + 50, n)):
            if strategy == 'next_candle':
                trade.close(closes[i], i, 'next_candle')
                return trade

            elif strategy == 'stop_only':
                if lows[i] <= stop:
                    trade.close(stop, i, 'stop_hit')
                    return trade
                if direction[i] == -1 and i > entry_idx + 1:
                    trade.close(closes[i], i, 'st_cross_down')
                    return trade

            elif strategy == 'target_only':
                if highs[i] >= target:
                    trade.close(target, i, 'target_hit')
                    return trade
                if direction[i] == -1 and i > entry_idx + 1:
                    trade.close(closes[i], i, 'st_cross_down')
                    return trade

            elif strategy == 'stop_and_target':
                if lows[i] <= stop:
                    trade.close(stop, i, 'stop_hit')
                    return trade
                if highs[i] >= target:
                    trade.close(target, i, 'target_hit')
                    return trade
                if direction[i] == -1 and i > entry_idx + 1:
                    trade.close(closes[i], i, 'st_cross_down')
                    return trade

            elif strategy == 'rebalance_1x':
                risk = entry_price - stop
                tp1 = entry_price + risk
                sl1 = stop
                if highs[i] >= tp1:
                    trade.close(tp1, i, '1x_profit')
                    return trade
                if lows[i] <= sl1:
                    trade.close(sl1, i, '1x_loss')
                    return trade
                if direction[i] == -1 and i > entry_idx + 1:
                    trade.close(closes[i], i, 'st_cross_down')
                    return trade

        trade.close(closes[min(entry_idx + 49, n-1)], min(entry_idx + 49, n-1), 'timeout')
        return trade

    def run_basket(self, strategy_name, bars_dict, basket_size=10):
        all_syms = list(bars_dict.keys())
        np.random.seed(42)
        np.random.shuffle(all_syms)

        baskets = [all_syms[i:i+basket_size] for i in range(0, len(all_syms), basket_size)]
        basket_trades = []

        for basket_syms in baskets:
            if len(basket_syms) < basket_size // 2:
                continue
            per_stock_data = {}
            for sym in basket_syms:
                if sym not in bars_dict:
                    continue
                bars = bars_dict[sym]
                closes, highs, lows, st, direction, atr = self._prepare_st(bars)
                if st is None:
                    continue
                crosses = find_st_crosses(closes, st, direction)
                cross_ups = [c for c in crosses if c['type'] == 'cross_up']
                if cross_ups:
                    per_stock_data[sym] = (closes, highs, lows, st, direction, cross_ups)

            if not per_stock_data:
                continue

            basket_trades.extend(
                self._simulate_basket(strategy_name, per_stock_data, basket_syms)
            )

        return basket_trades[:self.max_trades]

    def _simulate_basket(self, strategy, per_stock_data, basket_syms):
        trades = []
        stock_entries = []
        for sym, (closes, highs, lows, st, direction, cross_ups) in per_stock_data.items():
            for cross in cross_ups:
                idx = cross['index']
                if idx >= len(closes) - 1:
                    continue
                entry_price = closes[idx]
                stop = st[idx]
                risk = entry_price - stop
                if risk <= 0:
                    continue
                stock_entries.append({
                    'sym': sym, 'entry_idx': idx, 'entry_price': entry_price,
                    'stop': stop, 'target': entry_price + 2 * risk,
                    'closes': closes, 'highs': highs, 'lows': lows,
                    'st': st, 'direction': direction
                })

        stock_entries.sort(key=lambda x: x['entry_idx'])
        if not stock_entries:
            return []

        max_idx = max(e['entry_idx'] for e in stock_entries)
        min_idx = min(e['entry_idx'] for e in stock_entries)

        if strategy == 'basket_exit':
            active = []
            exited = []
            entry_map = {}
            for e in stock_entries:
                entry_map.setdefault(e['sym'], []).append(e)

            sim_closes = {}
            sim_dirs = {}
            for sym in basket_syms:
                if sym in per_stock_data:
                    c, h, l, st, d, _ = per_stock_data[sym]
                    sim_closes[sym] = c
                    sim_dirs[sym] = d

            current_entries = {}
            for e in stock_entries:
                sym = e['sym']
                if sym in current_entries:
                    continue
                current_entries[sym] = e
                t = Trade(sym, e['entry_price'], e['entry_idx'], e['stop'], e['target'], self.invest_per_trade)
                active.append(t)

            n = max(len(v) for v in sim_closes.values()) if sim_closes else 0
            for i in range(min_idx + 1, min(min_idx + 100, n)):
                exit_now = False
                for t in active:
                    if t.exit_price is not None:
                        continue
                    sym = t.symbol
                    if sym not in sim_closes:
                        continue
                    c = sim_closes[sym]
                    d = sim_dirs[sym]
                    if i >= len(c):
                        continue
                    if strategy == 'basket_exit':
                        if c[i] < t.stop or (d[i] == -1 and i > t.entry_index + 1):
                            exit_now = True
                            break
                        if c[i] >= t.target:
                            exit_now = True
                            break
                if exit_now:
                    for t in active:
                        if t.exit_price is None:
                            sym = t.symbol
                            if sym in sim_closes and i < len(sim_closes[sym]):
                                t.close(sim_closes[sym][i], i, 'basket_exit')
                    break

            for t in active:
                if t.exit_price is None:
                    last_i = min(min_idx + 99, n - 1)
                    t.close(t.entry_price, last_i, 'timeout')
                trades.append(t)

        elif strategy == 'rebalance_basket':
            active = {}
            for e in stock_entries:
                sym = e['sym']
                if sym in active:
                    continue
                t = Trade(sym, e['entry_price'], e['entry_idx'], e['stop'], e['target'], self.invest_per_trade)
                active[sym] = t

            sim_closes = {}
            sim_dirs = {}
            sim_highs = {}
            sim_lows = {}
            for sym in basket_syms:
                if sym in per_stock_data:
                    c, h, l, st, d, _ = per_stock_data[sym]
                    sim_closes[sym] = c
                    sim_dirs[sym] = d
                    sim_highs[sym] = h
                    sim_lows[sym] = l

            n = max(len(v) for v in sim_closes.values()) if sim_closes else 0
            for i in range(min_idx + 1, min(min_idx + 100, n)):
                to_close = []
                for sym, t in active.items():
                    if t.exit_price is not None:
                        continue
                    if sym not in sim_closes or i >= len(sim_closes[sym]):
                        continue
                    c = sim_closes[sym]
                    h = sim_highs[sym]
                    lo = sim_lows[sym]
                    d = sim_dirs[sym]
                    risk = t.entry_price - t.stop
                    tp1 = t.entry_price + risk

                    if h[i] >= tp1:
                        t.close(tp1, i, '1x_profit')
                        to_close.append(sym)
                    elif lo[i] <= t.stop:
                        t.close(t.stop, i, '1x_loss')
                        to_close.append(sym)
                    elif d[i] == -1 and i > t.entry_index + 1:
                        t.close(c[i], i, 'st_cross_down')
                        to_close.append(sym)

            for sym, t in active.items():
                if t.exit_price is None:
                    t.close(t.entry_price, min(min_idx + 99, n - 1), 'timeout')
                trades.append(t)

        return trades
