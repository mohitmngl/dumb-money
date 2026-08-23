import json
import time
import logging
import threading
import numpy as np
import pandas as pd
from datetime import datetime
from dumbmoney.db import get_db
from dumbmoney.indicators import supertrend, weighted_alpha, accel, prob_up, next_day_return, streak_vectorized, atrp, combined_ohlc

logger = logging.getLogger(__name__)

_ss_state = {"status": "idle", "phase": "", "progress": "", "cancel_requested": False}
_lock = threading.Lock()


def get_ss_status():
    with _lock:
        return dict(_ss_state)


def generate_string_strategies(market="US"):
    """Generate thousands of string strategies from cartesian product of filter/sort/params."""
    conn = get_db(market)
    try:
        stats = pd.read_sql("SELECT * FROM stats WHERE price > 0 AND (asset_class IS NULL OR LOWER(asset_class)='stock')", conn)
        if stats.empty:
            return []

        hs_cols_list = ["symbol", "date", "next_day_return", "atr_crossed_above", "atr_signal", "atr_streak", "weighted_alpha", "streak"]
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(historical_screener)").fetchall()}
        if "confluence" in existing_cols:
            hs_cols_list.append("confluence")
        hs_cols = ", ".join(hs_cols_list)
        hs_cache = pd.read_sql(
            f"SELECT {hs_cols} FROM historical_screener ORDER BY symbol, date", conn
        )
        if "confluence" not in hs_cache.columns:
            hs_cache["confluence"] = 0

        stats_prepared, hs_pivot = preprocess_for_combos(stats, hs_cache)

        strategies = []
        filter_combos = [
            {"name": "ST_Cross_Up", "atr_signal": 1},
            {"name": "ST_Cross_Down_ReversalWatch", "atr_signal": -1, "accel_crossed_up": 1},
            {"name": "ST_Uptrend", "atr_streak_gt": 0},
            {"name": "ST_StrongUptrend", "atr_streak_gt": 5},
            {"name": "Accel_Cross_Up", "accel_crossed_up": 1},
            {"name": "Accel_Up", "accel_signal": 1},
            {"name": "WA_Above50", "min_wa": 50},
            {"name": "WA_Above20", "min_wa": 20},
            {"name": "WA_Above0", "min_wa": 0},
            {"name": "WA_Rebound", "min_wa": -10, "accel_signal": 1},
            {"name": "Prob_High", "min_prob_1d": 55},
            {"name": "Prob_VeryHigh", "min_prob_1d": 60},
            {"name": "ST_Up_Accel_Up", "atr_signal": 1, "accel_signal": 1},
            {"name": "ST_Cross_Accel_Cross", "atr_signal": 1, "accel_crossed_up": 1},
            {"name": "High_Confluence", "min_confluence": 60},
            {"name": "VeryHigh_Confluence", "min_confluence": 75},
            {"name": "Momentum_Streak", "min_streak": 3},
            {"name": "Fresh_Momentum", "min_streak": 1, "accel_crossed_up": 1},
            {"name": "ST_Cross_HighWA", "atr_signal": 1, "min_wa": 20},
            {"name": "All_Signals", "atr_signal": 1, "accel_signal": 1, "min_wa": 10},
            {"name": "Accel_Cross_HighWA", "accel_crossed_up": 1, "min_wa": 20},
        ]
        sort_fields = ["weighted_alpha", "prob_up_1d", "prob_up_5d", "confluence", "streak", "ai_overall_score", "change_pct", "volume"]
        sort_dirs = ["desc", "asc"]
        top_ns = [3, 5, 8, 10, 15, 20, 30, 50]
        st_params = [(7, 1.0), (10, 1.0), (10, 2.0), (14, 1.0), (14, 1.5), (14, 2.0), (21, 1.0), (21, 2.0)]

        import itertools
        combos = list(itertools.product(filter_combos, sort_fields, sort_dirs, top_ns, st_params))
        total_combos = len(combos)

        for idx, (filt, sort_f, sort_dir, top_n, (st_p, st_m)) in enumerate(combos):
            if _ss_state.get("cancel_requested"):
                break

            _ss_state["phase"] = f"Combo {idx+1}/{total_combos}..."
            name = f"{filt['name']}_{sort_f}_{sort_dir}_top{top_n}_ST{st_p}x{st_m}"

            filtered = _apply_string_rules(stats_prepared, filt, sort_f, top_n, sort_dir)
            if not filtered:
                continue

            metrics = _backtest_string(filtered, hs_pivot, st_p, st_m)

            strategies.append({
                "name": name,
                "strategy_type": "string_screener",
                "filter_json": json.dumps(filt),
                "sort_field": sort_f,
                "sort_dir": sort_dir,
                "top_n": top_n,
                "st_period": st_p,
                "st_multiplier": st_m,
                "total_entries": metrics["total_entries"],
                "win_rate": metrics["win_rate"],
                "avg_1d_return": metrics["avg_1d_return"],
                "median_1d_return": metrics["median_1d_return"],
                "std_1d_return": metrics["std_1d_return"],
                "max_1d_gain": metrics["max_1d_gain"],
                "max_1d_loss": metrics["max_1d_loss"],
                "max_consecutive_wins": metrics["max_consecutive_wins"],
                "max_consecutive_losses": metrics["max_consecutive_losses"],
                "sharpe_1d": metrics["sharpe_1d"],
                "prob_up_1d": metrics["prob_up_1d"],
                "prob_up_1pct": metrics["prob_up_1pct"],
                "prob_up_2pct": metrics["prob_up_2pct"],
                "prob_down_2pct": metrics["prob_down_2pct"],
                "prob_up_after_st_cross": metrics["prob_up_after_st_cross"],
                "prob_up_after_wa_high": metrics["prob_up_after_wa_high"],
                "current_symbols": ",".join([r["symbol"] for r in filtered]),
                "current_count": len(filtered),
                "is_random": 0,
            })

        for i in range(min(50, len(strategies))):
            random_syms = stats_prepared.sample(n=min(10, len(stats_prepared)))["symbol"].tolist()
            metrics = _backtest_string(
                [{"symbol": s} for s in random_syms],
                hs_pivot, 14, 1.0
            )
            strategies.append({
                "name": f"Random_Baseline_{i+1}",
                "strategy_type": "string_screener",
                "filter_json": json.dumps({"random": True}),
                "sort_field": "random",
                "sort_dir": "desc",
                "top_n": len(random_syms),
                "st_period": 14,
                "st_multiplier": 1.0,
                "total_entries": metrics["total_entries"],
                "win_rate": metrics["win_rate"],
                "avg_1d_return": metrics["avg_1d_return"],
                "median_1d_return": metrics["median_1d_return"],
                "std_1d_return": metrics["std_1d_return"],
                "max_1d_gain": metrics["max_1d_gain"],
                "max_1d_loss": metrics["max_1d_loss"],
                "max_consecutive_wins": metrics["max_consecutive_wins"],
                "max_consecutive_losses": metrics["max_consecutive_losses"],
                "sharpe_1d": metrics["sharpe_1d"],
                "prob_up_1d": metrics["prob_up_1d"],
                "prob_up_1pct": metrics["prob_up_1pct"],
                "prob_up_2pct": metrics["prob_up_2pct"],
                "prob_down_2pct": metrics["prob_down_2pct"],
                "prob_up_after_st_cross": 50,
                "prob_up_after_wa_high": 50,
                "current_symbols": ",".join(random_syms),
                "current_count": len(random_syms),
                "is_random": 1,
            })

        return strategies
    finally:
        conn.close()


def preprocess_for_combos(stats_df, hs_cache):
    """Pre-fill NaN in stats_df and pivot hs_cache into (dates x symbols) matrix.
    Call ONCE before the combo loop. Returns (stats_prepared, hs_pivot)."""
    fill_cols = ["atr_streak", "weighted_alpha", "prob_up_1d", "streak", "confluence",
                 "atr_signal", "accel_crossed_up", "accel_signal"]
    stats_prepared = stats_df.copy()
    for col in fill_cols:
        if col in stats_prepared.columns:
            stats_prepared[col] = stats_prepared[col].fillna(0)

    hs_pivot = hs_cache.pivot_table(
        index="date", columns="symbol", values="next_day_return", aggfunc="mean"
    )
    hs_pivot._sym_to_idx = {s: i for i, s in enumerate(hs_pivot.columns)}
    hs_pivot._matrix = hs_pivot.values.astype(np.float64)
    cross_pivot = hs_cache.pivot_table(
        index="date", columns="symbol", values="atr_crossed_above", aggfunc="max"
    )
    hs_pivot._crossed_above = cross_pivot.values.astype(np.float64)

    return stats_prepared, hs_pivot


def _apply_string_rules(stats_prepared, rules, sort_field, top_n, sort_dir="desc"):
    """Filter stats using numpy boolean mask (no DataFrame copy), nlargest/nsmallest."""
    n = len(stats_prepared)
    mask = np.ones(n, dtype=bool)

    if "atr_signal" in rules:
        mask &= stats_prepared["atr_signal"].values == rules["atr_signal"]
    if "accel_crossed_up" in rules:
        mask &= stats_prepared["accel_crossed_up"].values == rules["accel_crossed_up"]
    if "accel_signal" in rules:
        mask &= stats_prepared["accel_signal"].values == rules["accel_signal"]
    if "atr_streak_gt" in rules:
        mask &= stats_prepared["atr_streak"].values > rules["atr_streak_gt"]
    if "min_wa" in rules:
        mask &= stats_prepared["weighted_alpha"].values >= rules["min_wa"]
    if "min_prob_1d" in rules:
        mask &= stats_prepared["prob_up_1d"].values >= rules["min_prob_1d"]
    if "min_streak" in rules:
        mask &= stats_prepared["streak"].values >= rules["min_streak"]
    if "min_confluence" in rules:
        mask &= stats_prepared["confluence"].values >= rules["min_confluence"]

    filtered = stats_prepared.iloc[mask]
    if filtered.empty:
        return []

    actual_n = min(top_n, len(filtered))
    if sort_field not in filtered.columns:
        return filtered.head(top_n).to_dict("records")

    if sort_dir == "asc":
        result = filtered.nsmallest(actual_n, sort_field)
    else:
        result = filtered.nlargest(actual_n, sort_field)

    return result.to_dict("records")


def _backtest_string(symbols_data, hs_pivot, st_period=14, st_mult=1.0):
    """Backtest using pre-pivoted matrix. O(1) column selection, vectorized numpy."""
    metrics = {
        "total_entries": 0, "win_rate": 0, "avg_1d_return": 0, "median_1d_return": 0,
        "std_1d_return": 0, "max_1d_gain": 0, "max_1d_loss": 0,
        "max_consecutive_wins": 0, "max_consecutive_losses": 0, "sharpe_1d": 0,
        "prob_up_1d": 0, "prob_up_1pct": 0, "prob_up_2pct": 0, "prob_down_2pct": 0,
        "prob_up_after_st_cross": 50, "prob_up_after_wa_high": 50
    }
    if not symbols_data:
        return metrics

    if hasattr(hs_pivot, "_sym_to_idx"):
        sym_to_idx = hs_pivot._sym_to_idx
        matrix = hs_pivot._matrix
        col_indices = [sym_to_idx[s["symbol"]] for s in symbols_data if s["symbol"] in sym_to_idx]
        if not col_indices:
            return metrics
        sub = matrix[:, col_indices]
        valid_counts = np.sum(~np.isnan(sub), axis=1)
        min_count = len(col_indices) * 0.5
        with np.errstate(all="ignore"):
            daily_means = np.nanmean(sub, axis=1)
        keep = (valid_counts >= min_count) & ~np.isnan(daily_means)
        returns = daily_means[keep]

        if hasattr(hs_pivot, "_crossed_above"):
            sub_cross = hs_pivot._crossed_above[:, col_indices]
            cross_signal = np.nanmax(sub_cross, axis=1) > 0.5
            cross_signal_filtered = cross_signal[keep]
            cross_returns = returns[cross_signal_filtered]
            if len(cross_returns) > 0:
                metrics["prob_up_after_st_cross"] = round(float((cross_returns > 0).sum() / len(cross_returns) * 100), 2)
            else:
                metrics["prob_up_after_st_cross"] = 50
    else:
        syms = [s["symbol"] for s in symbols_data]
        basket_hs = hs_pivot[hs_pivot["symbol"].isin(syms)].copy()
        if basket_hs.empty:
            return metrics
        daily_returns = []
        cross_mask_list = []
        dates = sorted(basket_hs["date"].unique())
        for date in dates:
            day_data = basket_hs[basket_hs["date"] == date]
            if len(day_data) < len(syms) * 0.5:
                continue
            has_cross = float(day_data["atr_crossed_above"].fillna(0).sum() > 0)
            avg_return = day_data["next_day_return"].mean()
            if not np.isnan(avg_return):
                daily_returns.append(avg_return)
                cross_mask_list.append(has_cross)
        returns = np.array(daily_returns) if daily_returns else np.array([])
        cross_mask = np.array(cross_mask_list) if cross_mask_list else np.zeros(0, dtype=bool)
        if len(returns) > 0 and cross_mask.any():
            cross_returns = returns[cross_mask]
            metrics["prob_up_after_st_cross"] = round(float((cross_returns > 0).sum() / len(cross_returns) * 100), 2)
        else:
            metrics["prob_up_after_st_cross"] = 50

    if len(returns) == 0:
        return metrics

    n = len(returns)
    pos = returns > 0
    mean_r = float(returns.mean())
    std_r = float(returns.std())

    metrics["total_entries"] = n
    metrics["win_rate"] = round(float(pos.sum() / n * 100), 2)
    metrics["avg_1d_return"] = round(mean_r, 4)
    metrics["median_1d_return"] = round(float(np.median(returns)), 4)
    metrics["std_1d_return"] = round(std_r, 4)
    metrics["max_1d_gain"] = round(float(returns.max()), 4)
    metrics["max_1d_loss"] = round(float(returns.min()), 4)
    metrics["sharpe_1d"] = round(float(mean_r / (std_r + 1e-10)), 4)
    metrics["prob_up_1d"] = round(float(pos.sum() / n * 100), 2)
    metrics["prob_up_1pct"] = round(float((returns > 1).sum() / n * 100), 2)
    metrics["prob_up_2pct"] = round(float((returns > 2).sum() / n * 100), 2)
    metrics["prob_down_2pct"] = round(float((returns < -2).sum() / n * 100), 2)

    boundaries = np.diff(pos.astype(np.int8))
    change_idx = np.flatnonzero(boundaries)
    run_lengths = np.diff(np.concatenate(([-1], change_idx, [n - 1])))
    run_values = pos[np.concatenate(([0], change_idx + 1))]
    win_runs = run_lengths[run_values]
    loss_runs = run_lengths[~run_values]
    metrics["max_consecutive_wins"] = int(win_runs.max()) if len(win_runs) > 0 else 0
    metrics["max_consecutive_losses"] = int(loss_runs.max()) if len(loss_runs) > 0 else 0

    return metrics


def run_string_backtest(market="US"):
    with _lock:
        if _ss_state["status"] == "running":
            return False
        _ss_state["status"] = "running"
        _ss_state["cancel_requested"] = False
        threading.Thread(target=_ss_worker, args=(market,), daemon=True).start()
    return True


def cancel_string_backtest():
    with _lock:
        _ss_state["cancel_requested"] = True
        _ss_state["status"] = "cancelling"
    return True


def _ss_worker(market):
    try:
        _ss_state["phase"] = "Generating strategies..."
        _ss_state["progress_pct"] = 0
        strategies = generate_string_strategies(market)
        _ss_state["phase"] = f"Saving {len(strategies)} strategies..."

        if strategies:
            conn = get_db(market)
            try:
                conn.execute("DELETE FROM ss_strategies WHERE is_random=0")
                batch = []
                for s in strategies:
                    batch.append((
                        s["name"], s["strategy_type"], s["filter_json"], s["sort_field"],
                        s["sort_dir"], s["top_n"], s["st_period"], s["st_multiplier"],
                        s["total_entries"], s["win_rate"], s["avg_1d_return"],
                        s["median_1d_return"], s["std_1d_return"], s["max_1d_gain"],
                        s["max_1d_loss"], s["max_consecutive_wins"], s["max_consecutive_losses"],
                        s["sharpe_1d"], s["prob_up_1d"], s["prob_up_1pct"],
                        s["prob_up_2pct"], s["prob_down_2pct"],
                        s["prob_up_after_st_cross"], s["prob_up_after_wa_high"],
                        datetime.utcnow().strftime("%Y-%m-%d"), s["current_count"],
                        s["current_symbols"], s["is_random"]
                    ))
                    if len(batch) >= 500:
                        conn.executemany(
                            """INSERT OR REPLACE INTO ss_strategies (
                                name, strategy_type, filter_json, sort_field, sort_dir, top_n,
                                st_period, st_multiplier, total_entries, win_rate, avg_1d_return,
                                median_1d_return, std_1d_return, max_1d_gain, max_1d_loss,
                                max_consecutive_wins, max_consecutive_losses, sharpe_1d,
                                prob_up_1d, prob_up_1pct, prob_up_2pct, prob_down_2pct,
                                prob_up_after_st_cross, prob_up_after_wa_high,
                                current_date, current_count, current_symbols, is_random
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            batch)
                        batch.clear()
                if batch:
                    conn.executemany(
                        """INSERT OR REPLACE INTO ss_strategies (
                            name, strategy_type, filter_json, sort_field, sort_dir, top_n,
                            st_period, st_multiplier, total_entries, win_rate, avg_1d_return,
                            median_1d_return, std_1d_return, max_1d_gain, max_1d_loss,
                            max_consecutive_wins, max_consecutive_losses, sharpe_1d,
                            prob_up_1d, prob_up_1pct, prob_up_2pct, prob_down_2pct,
                            prob_up_after_st_cross, prob_up_after_wa_high,
                            current_date, current_count, current_symbols, is_random
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        batch)
                conn.commit()
            finally:
                conn.close()

        _ss_state["status"] = "complete"
        _ss_state["phase"] = f"Done: {len(strategies)} strategies"
    except Exception as e:
        _ss_state["status"] = "error"
        _ss_state["phase"] = str(e)
        logger.error(f"String backtest error: {e}")


def get_strategies(market="US", page=1, per_page=50, sort="sharpe_1d", sort_dir="desc", search="",
                   min_win=None, min_prob=None, min_avg=None, min_entries=None, hide_random=False):
    conn = get_db(market)
    try:
        where = "1=1"
        params = []
        if search:
            where += " AND name LIKE ?"
            params.append(f"%{search}%")
        if min_win not in (None, ""):
            where += " AND COALESCE(win_rate, 0) >= ?"
            params.append(float(min_win))
        if min_prob not in (None, ""):
            where += " AND COALESCE(prob_up_1d, 0) >= ?"
            params.append(float(min_prob))
        if min_avg not in (None, ""):
            where += " AND COALESCE(avg_1d_return, 0) >= ?"
            params.append(float(min_avg))
        if min_entries not in (None, ""):
            where += " AND COALESCE(total_entries, 0) >= ?"
            params.append(int(min_entries))
        if hide_random:
            where += " AND COALESCE(is_random, 0) = 0"

        total = conn.execute(f"SELECT COUNT(*) FROM ss_strategies WHERE {where}", params).fetchone()[0]

        allowed_sorts = {"sharpe_1d", "win_rate", "avg_1d_return", "prob_up_1d", "prob_up_after_st_cross", "total_entries",
                         "median_1d_return", "max_1d_gain", "max_consecutive_wins", "prob_up_1pct",
                         "prob_up_2pct", "prob_down_2pct", "current_count", "name"}
        if sort not in allowed_sorts:
            sort = "sharpe_1d"
        direction = "DESC" if sort_dir == "desc" else "ASC"

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"SELECT * FROM ss_strategies WHERE {where} ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
            params + [per_page, offset]
        ).fetchall()

        return {"strategies": [dict(r) for r in rows], "total": total, "page": page, "per_page": per_page}
    finally:
        conn.close()


def get_strategy_detail(strategy_id, market="US"):
    conn = get_db(market)
    try:
        strategy = conn.execute("SELECT * FROM ss_strategies WHERE id=?", (strategy_id,)).fetchone()
        entries = conn.execute(
            "SELECT * FROM ss_entries WHERE strategy_id=? ORDER BY date", (strategy_id,)
        ).fetchall()
        return {
            "strategy": dict(strategy) if strategy else None,
            "entries": [dict(e) for e in entries]
        }
    finally:
        conn.close()


def get_current_basket(strategy_id, market="US"):
    conn = get_db(market)
    try:
        strat = conn.execute("SELECT current_symbols FROM ss_strategies WHERE id=?", (strategy_id,)).fetchone()
        if not strat or not strat[0]:
            return []
        symbols = strat[0].split(",")
        rows = conn.execute(
            "SELECT symbol, price, change_pct, weighted_alpha, atr_signal, prob_up_1d, streak FROM stats WHERE symbol IN ({})".format(
                ",".join(["?"] * len(symbols))), symbols
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
