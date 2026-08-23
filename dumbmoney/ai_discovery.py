import json
import time
import logging
import threading
from datetime import datetime
from dumbmoney.db import get_db

logger = logging.getLogger(__name__)

_ai_state = {"status": "idle", "progress": "", "cancel_requested": False}
_lock = threading.Lock()


def get_ai_status():
    with _lock:
        return dict(_ai_state)


def generate_rule_strategies(market="US"):
    """Auto-generate rule strategies and backtest them."""
    conn = get_db(market)
    try:
        stats = conn.execute("SELECT * FROM stats WHERE price > 0 ORDER BY weighted_alpha DESC").fetchall()
        if not stats:
            return []

        strategies = []
        rule_templates = [
            {"name": "ST_Cross_Up", "rules": json.dumps({"atr_signal": 1}), "sort": "weighted_alpha"},
            {"name": "ST_Cross_Up_HighWA", "rules": json.dumps({"atr_signal": 1, "min_wa": 20}), "sort": "prob_up_1d"},
            {"name": "Accel_Up", "rules": json.dumps({"accel_signal": 1}), "sort": "weighted_alpha"},
            {"name": "Accel_Cross_Up", "rules": json.dumps({"accel_crossed_up": 1}), "sort": "prob_up_1d"},
            {"name": "ST_Up_Accel_Up", "rules": json.dumps({"atr_signal": 1, "accel_signal": 1}), "sort": "confluence"},
            {"name": "High_Confluence", "rules": json.dumps({"min_confluence": 60}), "sort": "confluence"},
            {"name": "Prob_Up_High", "rules": json.dumps({"min_prob_1d": 60}), "sort": "prob_up_1d"},
            {"name": "Momentum_Screener", "rules": json.dumps({"min_streak": 3, "min_wa": 10}), "sort": "streak"},
        ]

        for template in rule_templates:
            rules = json.loads(template["rules"])
            filtered = _apply_rules(stats, rules, template["sort"], 10)

            if filtered:
                batch_date = datetime.utcnow().strftime("%Y-%m-%d")
                symbols_str = ",".join([r["symbol"] for r in filtered])
                avg_ret = sum(r.get("next_day_return", 0) for r in filtered) / len(filtered) if filtered else 0
                win_count = sum(1 for r in filtered if r.get("next_day_return", 0) > 0)
                win_rate = (win_count / len(filtered) * 100) if filtered else 0

                conn.execute(
                    """INSERT OR REPLACE INTO ai_discovered_portfolios
                       (name, rules, score, win_rate, avg_return, total_batches, created_at, last_updated)
                       VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                    (template["name"], template["rules"],
                     round(win_rate, 2), round(win_rate, 2), round(avg_ret, 4),
                     datetime.utcnow().isoformat(), datetime.utcnow().isoformat())
                )
                portfolio_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                conn.execute(
                    """INSERT OR REPLACE INTO ai_discovered_batches
                       (portfolio_id, batch_date, symbols, avg_return_7d, avg_return_14d, avg_return_30d)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (portfolio_id, batch_date, symbols_str, round(avg_ret, 4), round(avg_ret, 4), round(avg_ret, 4))
                )

                strategies.append({
                    "name": template["name"],
                    "rules": template["rules"],
                    "score": round(win_rate, 2),
                    "symbols": [r["symbol"] for r in filtered]
                })

        conn.commit()
        return strategies
    finally:
        conn.close()


def _apply_rules(stats_rows, rules, sort_field, top_n):
    """Apply filter rules to stats rows and return top N."""
    filtered = []
    for row in stats_rows:
        r = dict(row)
        match = True
        if "atr_signal" in rules and (r.get("atr_signal") or 0) != rules["atr_signal"]:
            match = False
        if "min_wa" in rules and (r.get("weighted_alpha") or 0) < rules["min_wa"]:
            match = False
        if "max_wa" in rules and (r.get("weighted_alpha") or 0) > rules["max_wa"]:
            match = False
        if "accel_signal" in rules and (r.get("accel_signal") or 0) != rules["accel_signal"]:
            match = False
        if "accel_crossed_up" in rules and (r.get("accel_crossed_up") or 0) != rules["accel_crossed_up"]:
            match = False
        if "min_confluence" in rules and (r.get("confluence") or 0) < rules["min_confluence"]:
            match = False
        if "min_prob_1d" in rules and (r.get("prob_up_1d") or 0) < rules["min_prob_1d"]:
            match = False
        if "min_streak" in rules and (r.get("streak") or 0) < rules["min_streak"]:
            match = False
        if "min_price" in rules and (r.get("price") or 0) < rules["min_price"]:
            match = False
        if match:
            filtered.append(r)

    def _sort_val(x, field):
        v = x.get(field)
        return v if v is not None else 0

    filtered.sort(key=lambda x: _sort_val(x, sort_field), reverse=True)

    return filtered[:top_n]


def get_discovered_portfolios(market="US"):
    conn = get_db(market)
    try:
        rows = conn.execute(
            "SELECT * FROM ai_discovered_portfolios ORDER BY score DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_discovered_detail(portfolio_id, market="US"):
    conn = get_db(market)
    try:
        portfolio = conn.execute(
            "SELECT * FROM ai_discovered_portfolios WHERE id=?", (portfolio_id,)
        ).fetchone()
        batches = conn.execute(
            "SELECT * FROM ai_discovered_batches WHERE portfolio_id=? ORDER BY batch_date",
            (portfolio_id,)
        ).fetchall()
        return {
            "portfolio": dict(portfolio) if portfolio else None,
            "batches": [dict(b) for b in batches]
        }
    finally:
        conn.close()


def run_ai_discovery(market="US"):
    with _lock:
        if _ai_state["status"] == "running":
            return False
        _ai_state["status"] = "running"
        _ai_state["cancel_requested"] = False
        threading.Thread(target=_ai_worker, args=(market,), daemon=True).start()
    return True


def kill_ai_discovery():
    with _lock:
        _ai_state["cancel_requested"] = True
        _ai_state["status"] = "cancelling"
    return True


def _ai_worker(market):
    try:
        _ai_state["progress"] = "Generating strategies..."
        strategies = generate_rule_strategies(market)
        _ai_state["progress"] = f"Completed {len(strategies)} strategies"
        _ai_state["status"] = "complete"
    except Exception as e:
        _ai_state["status"] = "error"
        _ai_state["progress"] = str(e)
        logger.error(f"AI discovery error: {e}")


def save_rule_portfolio(name, category, filter_rules, sort_method, top_n, market="US"):
    conn = get_db(market)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO rule_portfolios (name, category, filter_rules, sort_method, top_n)
               VALUES (?, ?, ?, ?, ?)""",
            (name, category, json.dumps(filter_rules), sort_method, top_n)
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        stats = conn.execute("SELECT * FROM stats WHERE price > 0").fetchall()
        rules = filter_rules if isinstance(filter_rules, dict) else json.loads(filter_rules)
        filtered = _apply_rules([dict(s) for s in stats], rules, sort_method, top_n)

        if filtered:
            batch_date = datetime.utcnow().strftime("%Y-%m-%d")
            symbols_str = ",".join([r["symbol"] for r in filtered])
            avg_ret = sum(r.get("next_day_return", 0) for r in filtered) / len(filtered)
            win_count = sum(1 for r in filtered if r.get("next_day_return", 0) > 0)
            win_rate = (win_count / len(filtered) * 100) if filtered else 0

            conn.execute(
                "INSERT INTO rule_batches (portfolio_id, batch_date, symbols, basket_value, next_day_return) VALUES (?,?,?,?,?)",
                (pid, batch_date, symbols_str, 100.0, round(avg_ret, 4))
            )
            conn.execute(
                "INSERT OR REPLACE INTO rule_portfolio_stats (portfolio_id, win_rate, avg_return, sharpe, total_batches, prob_up_1d, updated_at) VALUES (?,?,?,?,?,?,?)",
                (pid, round(win_rate, 2), round(avg_ret, 4), 0, 1, round(win_rate, 2), datetime.utcnow().isoformat())
            )
        conn.commit()
        return pid
    finally:
        conn.close()
