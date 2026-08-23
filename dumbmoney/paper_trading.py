import json
import logging
from datetime import datetime
from dumbmoney.db import get_db
from dumbmoney.data_us import place_paper_order, get_positions, get_account

logger = logging.getLogger(__name__)


def get_paper_strategies(market="US"):
    conn = get_db(market)
    try:
        rows = conn.execute("SELECT * FROM paper_strategies ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_paper_strategy(name, rules, num_stocks=10, allocation_type="equal", rebalance_time="09:35", market="US"):
    conn = get_db(market)
    try:
        conn.execute(
            """INSERT INTO paper_strategies (name, rules, num_stocks, allocation_type, rebalance_time)
               VALUES (?, ?, ?, ?, ?)""",
            (name, json.dumps(rules), num_stocks, allocation_type, rebalance_time)
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def update_paper_strategy(strategy_id, name=None, rules=None, num_stocks=None, active=None, market="US"):
    conn = get_db(market)
    try:
        if name:
            conn.execute("UPDATE paper_strategies SET name=? WHERE id=?", (name, strategy_id))
        if rules is not None:
            conn.execute("UPDATE paper_strategies SET rules=? WHERE id=?", (json.dumps(rules), strategy_id))
        if num_stocks is not None:
            conn.execute("UPDATE paper_strategies SET num_stocks=? WHERE id=?", (num_stocks, strategy_id))
        if active is not None:
            conn.execute("UPDATE paper_strategies SET active=? WHERE id=?", (active, strategy_id))
        conn.commit()
    finally:
        conn.close()


def delete_paper_strategy(strategy_id, market="US"):
    conn = get_db(market)
    try:
        conn.execute("DELETE FROM paper_strategies WHERE id=?", (strategy_id,))
        conn.execute("DELETE FROM paper_trades WHERE strategy_id=?", (strategy_id,))
        conn.commit()
    finally:
        conn.close()


def activate_strategy(strategy_id, market="US"):
    conn = get_db(market)
    try:
        strategy = conn.execute("SELECT * FROM paper_strategies WHERE id=?", (strategy_id,)).fetchone()
        if not strategy:
            return {"error": "Strategy not found"}

        strategy = dict(strategy)
        rules = json.loads(strategy["rules"])
        num_stocks = strategy["num_stocks"]

        stats = conn.execute(
            """SELECT symbol, price, weighted_alpha, prob_up_1d, confluence FROM stats
               WHERE price > 0 ORDER BY weighted_alpha DESC LIMIT ?""",
            (num_stocks * 2,)
        ).fetchall()

        selected = []
        for s in stats:
            s = dict(s)
            match = True
            if "min_wa" in rules and s.get("weighted_alpha", 0) < rules["min_wa"]:
                match = False
            if "min_prob_1d" in rules and s.get("prob_up_1d", 0) < rules["min_prob_1d"]:
                match = False
            if "min_confluence" in rules and s.get("confluence", 0) < rules["min_confluence"]:
                match = False
            if match:
                selected.append(s)
            if len(selected) >= num_stocks:
                break

        if not selected:
            return {"error": "No stocks match the rules"}

        account = get_account()
        equity = account.get("equity", 0)
        per_stock = equity / num_stocks if num_stocks > 0 else 0

        orders_placed = []
        for stock in selected:
            price = stock.get("price", 0)
            if price > 0:
                qty = int(per_stock / price)
                if qty > 0:
                    order = place_paper_order(stock["symbol"], qty, "buy")
                    if order:
                        orders_placed.append({
                            "symbol": stock["symbol"],
                            "qty": qty,
                            "side": "buy",
                            "price": price,
                            "alpaca_order_id": order.get("id", "")
                        })
                        conn.execute(
                            """INSERT INTO paper_trades
                               (strategy_id, symbol, side, qty, price, filled_at, alpaca_order_id)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (strategy_id, stock["symbol"], "buy", qty, price,
                             datetime.utcnow().isoformat(), order.get("id", ""))
                        )

        conn.execute(
            "UPDATE paper_strategies SET active=1, last_rebalanced=? WHERE id=?",
            (datetime.utcnow().isoformat(), strategy_id)
        )
        conn.commit()
        return {"orders": orders_placed, "selected": [s["symbol"] for s in selected]}
    finally:
        conn.close()


def pause_strategy(strategy_id, market="US"):
    conn = get_db(market)
    try:
        conn.execute("UPDATE paper_strategies SET active=0 WHERE id=?", (strategy_id,))
        conn.commit()
    finally:
        conn.close()


def get_paper_positions():
    return get_positions()


def get_paper_trades(strategy_id=None, market="US"):
    conn = get_db(market)
    try:
        if strategy_id:
            rows = conn.execute(
                "SELECT * FROM paper_trades WHERE strategy_id=? ORDER BY filled_at DESC LIMIT 100",
                (strategy_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM paper_trades ORDER BY filled_at DESC LIMIT 100"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def rebalance_now(strategy_id, market="US"):
    return activate_strategy(strategy_id, market)
