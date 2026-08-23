import numpy as np
from collections import defaultdict


def compute_all_metrics(result, capital=10000.0):
    """Compute comprehensive strategy metrics from backtest result.

    Returns dict with all metrics grouped by category.
    """
    eq_curve = result.get("equity_curve", [])
    candle_rets = result.get("candle_returns", [])
    final_equity = result.get("final_equity", capital)
    margin = result.get("margin", 1)
    charges = result.get("charges", False)
    timeframe = result.get("timeframe", "15Min")

    if not eq_curve:
        return _empty_metrics(capital, timeframe, margin, charges)

    equities = np.array([e["equity"] for e in eq_curve])
    timestamps = [e["timestamp"] for e in eq_curve]
    returns = np.array(candle_rets) if candle_rets else np.array([0.0])

    # === BASIC METRICS ===
    total_return = (final_equity - capital) / capital
    n_candles = len(returns)

    # Timeframe-based candle count estimates
    candles_per_day = _candles_per_day(timeframe)
    total_trading_days = n_candles / candles_per_day if candles_per_day > 0 else 1
    years = total_trading_days / 252.0

    cagr = ((final_equity / capital) ** (1 / max(years, 0.001))) - 1 if years > 0 else 0

    avg_candle_return = float(np.mean(returns)) if len(returns) > 0 else 0
    avg_daily_return = avg_candle_return * candles_per_day
    avg_weekly_return = avg_daily_return * 5
    avg_monthly_return = avg_daily_return * 21
    avg_yearly_return = avg_daily_return * 252

    # Compounding return per candle
    if len(returns) > 0:
        compounding_per_candle = (np.prod(1 + returns)) ** (1.0 / len(returns)) - 1
    else:
        compounding_per_candle = 0
    compounding_per_day = (1 + compounding_per_candle) ** candles_per_day - 1
    compounding_per_week = (1 + compounding_per_day) ** 5 - 1
    compounding_per_month = (1 + compounding_per_day) ** 21 - 1
    compounding_per_year = (1 + compounding_per_day) ** 252 - 1

    # === RISK METRICS ===
    sharpe = _sharpe_ratio(returns, candles_per_day)
    sortino = _sortino_ratio(returns, candles_per_day)
    calmar = _calmar_ratio(equities, capital, years)
    max_dd, max_dd_duration, max_dd_start, max_dd_end = _max_drawdown(equities, timestamps)
    volatility = float(np.std(returns)) * np.sqrt(candles_per_day) if len(returns) > 1 else 0

    # === DISTRIBUTION METRICS ===
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    n_wins = len(wins)
    n_losses = len(losses)
    total_trades = n_wins + n_losses

    win_rate = n_wins / total_trades if total_trades > 0 else 0
    avg_win = float(np.mean(wins)) if n_wins > 0 else 0
    avg_loss = float(np.mean(losses)) if n_losses > 0 else 0
    best_candle = float(np.max(returns)) if len(returns) > 0 else 0
    worst_candle = float(np.min(returns)) if len(returns) > 0 else 0
    profit_factor = (np.sum(wins) / abs(np.sum(losses))) if n_losses > 0 and np.sum(losses) != 0 else float('inf')
    payoff_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

    max_consec_wins, max_consec_losses = _consecutive_streaks(returns)

    # === TIME-BASED RETURNS ===
    daily_returns = _aggregate_returns(returns, candles_per_day)
    weekly_returns = _aggregate_returns(returns, candles_per_day * 5)
    monthly_returns = _aggregate_returns(returns, candles_per_day * 21)

    # === DRAWDOWN SERIES ===
    drawdowns = _drawdown_series(equities)

    result_dict = {
        "basic": {
            "total_return": round(total_return * 100, 4),
            "total_return_pct": f"{total_return*100:.2f}%",
            "final_equity": round(final_equity, 2),
            "initial_capital": capital,
            "cagr_pct": f"{cagr*100:.2f}%",
            "cagr": round(cagr * 100, 4),
            "candles_processed": n_candles,
            "trading_days": round(total_trading_days, 1),
            "years": round(years, 3),
        },
        "returns": {
            "avg_candle_return_pct": f"{avg_candle_return*100:.6f}%",
            "avg_daily_return_pct": f"{avg_daily_return*100:.4f}%",
            "avg_weekly_return_pct": f"{avg_weekly_return*100:.4f}%",
            "avg_monthly_return_pct": f"{avg_monthly_return*100:.4f}%",
            "avg_yearly_return_pct": f"{avg_yearly_return*100:.2f}%",
            "compounding_per_candle_pct": f"{compounding_per_candle*100:.6f}%",
            "compounding_per_day_pct": f"{compounding_per_day*100:.4f}%",
            "compounding_per_week_pct": f"{compounding_per_week*100:.4f}%",
            "compounding_per_month_pct": f"{compounding_per_month*100:.4f}%",
            "compounding_per_year_pct": f"{compounding_per_year*100:.2f}%",
        },
        "risk": {
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "calmar_ratio": round(calmar, 4),
            "max_drawdown_pct": f"{max_dd*100:.2f}%",
            "max_drawdown": round(max_dd * 100, 4),
            "max_drawdown_duration_candles": max_dd_duration,
            "max_drawdown_start": max_dd_start,
            "max_drawdown_end": max_dd_end,
            "annual_volatility_pct": f"{volatility*100:.2f}%",
            "annual_volatility": round(volatility * 100, 4),
        },
        "distribution": {
            "win_rate_pct": f"{win_rate*100:.2f}%",
            "win_rate": round(win_rate * 100, 4),
            "n_wins": n_wins,
            "n_losses": n_losses,
            "total_trades": total_trades,
            "avg_win_pct": f"{avg_win*100:.6f}%",
            "avg_loss_pct": f"{avg_loss*100:.6f}%",
            "best_candle_pct": f"{best_candle*100:.4f}%",
            "worst_candle_pct": f"{worst_candle*100:.4f}%",
            "profit_factor": round(profit_factor, 4),
            "payoff_ratio": round(payoff_ratio, 4),
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
        },
        "timeframe": {
            "timeframe": timeframe,
            "candles_per_day": candles_per_day,
            "margin": margin,
            "charges": charges,
        },
        "per_candle_returns": [round(r * 100, 6) for r in returns.tolist()],
        "daily_returns": [round(r * 100, 4) for r in daily_returns],
        "weekly_returns": [round(r * 100, 4) for r in weekly_returns],
        "monthly_returns": [round(r * 100, 4) for r in monthly_returns],
        "equity_timestamps": timestamps,
        "equity_values": [round(e, 2) for e in equities.tolist()],
        "drawdowns": [round(d * 100, 4) for d in drawdowns],
    }

    return result_dict


def _candles_per_day(timeframe):
    """Number of regular-session candles per trading day."""
    mapping = {
        "1Min": 390,
        "5Min": 78,
        "15Min": 26,
        "30Min": 13,
        "1Hour": 7,
        "1Day": 1,
    }
    return mapping.get(timeframe, 26)


def _sharpe_ratio(returns, candles_per_day, risk_free_rate=0.0):
    if len(returns) < 2:
        return 0.0
    mean = np.mean(returns)
    std = np.std(returns, ddof=1)
    if std == 0:
        return 0.0
    annualized = (mean - risk_free_rate / candles_per_day) / std * np.sqrt(candles_per_day)
    return float(annualized)


def _sortino_ratio(returns, candles_per_day, risk_free_rate=0.0):
    if len(returns) < 2:
        return 0.0
    mean = np.mean(returns)
    downside = returns[returns < 0]
    if len(downside) == 0:
        return float('inf') if mean > 0 else 0.0
    downside_std = np.std(downside, ddof=1)
    if downside_std == 0:
        return 0.0
    annualized = (mean - risk_free_rate / candles_per_day) / downside_std * np.sqrt(candles_per_day)
    return float(annualized)


def _calmar_ratio(equities, capital, years):
    if years < 0.01:
        return 0.0
    total_ret = (equities[-1] / capital) - 1
    max_dd, _, _, _ = _max_drawdown(equities, None)
    if max_dd == 0:
        return float('inf') if total_ret > 0 else 0.0
    return float(total_ret / max_dd / max(years, 0.01))


def _max_drawdown(equities, timestamps):
    if len(equities) < 2:
        return 0.0, 0, None, None
    peak = equities[0]
    max_dd = 0.0
    dd_start = 0
    dd_end = 0
    current_dd_start = 0

    for i in range(len(equities)):
        if equities[i] >= peak:
            peak = equities[i]
            current_dd_start = i
        dd = (peak - equities[i]) / peak
        if dd > max_dd:
            max_dd = dd
            dd_start = current_dd_start
            dd_end = i

    start_ts = timestamps[dd_start] if timestamps and dd_start < len(timestamps) else None
    end_ts = timestamps[dd_end] if timestamps and dd_end < len(timestamps) else None
    return float(max_dd), dd_end - dd_start, start_ts, end_ts


def _drawdown_series(equities):
    if len(equities) < 1:
        return []
    peak = equities[0]
    drawdowns = []
    for e in equities:
        peak = max(peak, e)
        dd = (peak - e) / peak if peak > 0 else 0
        drawdowns.append(dd)
    return drawdowns


def _consecutive_streaks(returns):
    max_wins = max_losses = 0
    current_wins = current_losses = 0
    for r in returns:
        if r > 0:
            current_wins += 1
            current_losses = 0
        elif r < 0:
            current_losses += 1
            current_wins = 0
        else:
            current_wins = 0
            current_losses = 0
        max_wins = max(max_wins, current_wins)
        max_losses = max(max_losses, current_losses)
    return max_wins, max_losses


def _aggregate_returns(returns, period_len):
    """Aggregate per-candle returns into period returns."""
    if period_len <= 0 or len(returns) == 0:
        return []
    periods = []
    for i in range(0, len(returns), period_len):
        chunk = returns[i:i + period_len]
        if len(chunk) > 0:
            period_ret = np.prod(1 + chunk) - 1
            periods.append(float(period_ret))
    return periods


def _empty_metrics(capital, timeframe, margin, charges):
    return {
        "basic": {"total_return": 0, "final_equity": capital, "initial_capital": capital,
                  "cagr": 0, "candles_processed": 0, "trading_days": 0, "years": 0},
        "returns": {k: "0%" for k in ["avg_candle_return_pct", "avg_daily_return_pct",
                                        "avg_weekly_return_pct", "avg_monthly_return_pct",
                                        "avg_yearly_return_pct"]},
        "risk": {"sharpe_ratio": 0, "sortino_ratio": 0, "max_drawdown_pct": "0%", "annual_volatility_pct": "0%"},
        "distribution": {"win_rate_pct": "0%", "profit_factor": 0, "total_trades": 0},
        "timeframe": {"timeframe": timeframe, "margin": margin, "charges": charges},
    }
