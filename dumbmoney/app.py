import os
import sys
import json
import logging
import threading
import numpy as np
import pandas as pd
from flask import Flask, render_template, request, jsonify, Blueprint, g

from dumbmoney.config import FLASK_SECRET_KEY, FLASK_DEBUG, DB_PATHS
from dumbmoney.db import init_all_dbs, get_db, ensure_schema, migrate_nulls

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = FLASK_SECRET_KEY
app.config["DEBUG"] = FLASK_DEBUG

screener_bp = Blueprint("screener", __name__)
stock_bp = Blueprint("stock", __name__)
portfolio_bp = Blueprint("portfolio", __name__)
string_bp = Blueprint("string", __name__)
ai_bp = Blueprint("ai", __name__)
paper_bp = Blueprint("paper", __name__)
api_bp = Blueprint("api", __name__)
india_bp = Blueprint("india", __name__)
crypto_bp = Blueprint("crypto", __name__)

SCREENER_COLUMN_REFERENCE = [
    {"key": "symbol", "label": "Symbol", "current": "stats.symbol", "historical": "historical_screener.symbol", "meaning": "Ticker identifier."},
    {"key": "name", "label": "Name", "current": "stats.name", "historical": "assets.name", "meaning": "Asset name from the market universe."},
    {"key": "exchange", "label": "Exchange", "current": "stats.exchange", "historical": "assets.exchange", "meaning": "Listing exchange."},
    {"key": "asset_class", "label": "Type", "current": "stats.asset_class", "historical": "assets.asset_class", "meaning": "Asset class such as stock or ETF."},
    {"key": "price", "label": "Price", "current": "stats.price", "historical": "historical_screener.price", "meaning": "Current mode latest close; date mode close on the selected trading date."},
    {"key": "pre_change_pct", "label": "Pre %", "current": "stats.pre_change_pct", "historical": "NULL", "meaning": "Current US pre-market percent move when available; current-session only."},
    {"key": "post_change_pct", "label": "Post %", "current": "stats.post_change_pct", "historical": "NULL", "meaning": "Current US post-market percent move when available; current-session only."},
    {"key": "change_pct", "label": "Chg%", "current": "stats.change_pct", "historical": "historical_screener.change_pct", "meaning": "Close-to-previous-trading-close percent change for the row date."},
    {"key": "next_day_return", "label": "Next Day %", "current": "stats.next_day_return", "historical": "historical_screener.next_day_return", "meaning": "Current mode latest completed one-day realized return; date mode next trading close vs selected close."},
    {"key": "prob_up_1d", "label": "P(Up) 1D", "current": "stats.prob_up_1d", "historical": "historical_screener.prob_up_1d", "meaning": "Trailing probability that the next one-day close move was positive using data available as of the row date."},
    {"key": "prob_up_5d", "label": "P(Up) 5D", "current": "stats.prob_up_5d", "historical": "historical_screener.prob_up_5d", "meaning": "Trailing probability that the next five-day close move was positive using data available as of the row date."},
    {"key": "prob_up_1w", "label": "P(Up) 1W", "current": "stats.prob_up_1w", "historical": "historical_screener.prob_up_1w", "meaning": "Trailing probability that the next week (5 trading days) close move was positive using data available as of the row date."},
    {"key": "prob_up_1m", "label": "P(Up) 1M", "current": "stats.prob_up_1m", "historical": "historical_screener.prob_up_1m", "meaning": "Trailing probability that the next month (22 trading days) close move was positive using data available as of the row date."},
    {"key": "prob_up_st_cross", "label": "P(Up) ST Cross", "current": "stats.prob_up_st_cross", "historical": "historical_screener.prob_up_st_cross", "meaning": "Expanding-window probability that the next day closes higher after a 14d/2x ATR Trailing Stop bullish cross, using data available as of the row date."},
    {"key": "weighted_alpha", "label": "Wtd Alpha", "current": "stats.weighted_alpha", "historical": "historical_screener.weighted_alpha", "meaning": "Weighted price performance computed only from bars available as of the row date."},
    {"key": "volume", "label": "Volume", "current": "stats.volume", "historical": "historical_screener.volume", "meaning": "Daily bar volume for the row date; never signed."},
    {"key": "streak", "label": "Streak", "current": "stats.streak", "historical": "historical_screener.streak", "meaning": "Consecutive up or down close streak as of the row date."},
    {"key": "r_squared", "label": "R²", "current": "stats.r_squared", "historical": "historical_screener.r_squared", "meaning": "Signed R² of a linear fit on log(close) over the last 90 bars: +1 = perfectly straight uptrend, -1 = perfectly straight downtrend. Sort descending for the straightest uptrending charts."},
    {"key": "ath", "label": "ATH", "current": "stats.ath", "historical": "historical_screener.ath", "meaning": "All-time high: highest daily bar high from the first stored bar through the row date."},
    {"key": "atl", "label": "ATL", "current": "stats.atl", "historical": "historical_screener.atl", "meaning": "All-time low: lowest daily bar low from the first stored bar through the row date."},
    {"key": "confluence", "label": "Confluence", "current": "stats.confluence", "historical": "historical_screener.confluence", "meaning": "Combined technical score computed from row-date indicator values."},
    {"key": "ai_overall_score", "label": "AI Score", "current": "ai_analysis.overall_score", "historical": "historical_screener.ai_overall_score", "meaning": "Local vectorized score, not external generated text."},
    {"key": "ai_volume_profile_score", "label": "VP Score", "current": "ai_analysis.volume_profile_score", "historical": "historical_screener.ai_volume_profile_score", "meaning": "Local volume-profile score computed from available bars."},
    {"key": "ai_trendline_score", "label": "Trend Score", "current": "ai_analysis.trendline_score", "historical": "historical_screener.ai_trendline_score", "meaning": "Local trendline score computed from available bars."},
    {"key": "ai_sentiment_score", "label": "Sentiment", "current": "ai_analysis.sentiment_score", "historical": "historical_screener.ai_sentiment_score", "meaning": "Local sentiment/proxy score; historical mode uses stored row-date value."},
    {"key": "ai_conclusion", "label": "Conclusion", "current": "ai_analysis.conclusion", "historical": "historical_screener.ai_conclusion", "meaning": "BUY/HOLD/SELL label derived from local scores."},
    {"key": "ai_matrix", "label": "AI Matrix", "current": "ai_analysis.ai_matrix", "historical": "historical_screener.ai_matrix", "meaning": "Sigmoid-based directional prediction score 0-100. Higher = more likely next-day up."},
    {"key": "atr_signal", "label": "ATR Signal", "current": "stats.atr_signal", "historical": "historical_screener.atr_signal", "meaning": "ATR Trailing Stop direction: 1 above (bullish), -1 below (bearish), 0 neutral."},
    {"key": "atr_crossed_above", "label": "Cross Up", "current": "stats.atr_crossed_above", "historical": "historical_screener.atr_crossed_above", "meaning": "ATR Trailing Stop crossed from bearish to bullish on the row date."},
    {"key": "atr_crossed_below", "label": "Cross Down", "current": "stats.atr_crossed_below", "historical": "historical_screener.atr_crossed_below", "meaning": "ATR Trailing Stop crossed from bullish to bearish on the row date."},
    {"key": "atr_stop", "label": "ATR Stop 14x2", "current": "stats.atr_stop", "historical": "historical_screener.atr_stop", "meaning": "ATR Trailing Stop line using the app's current 14 period, 2.0 multiplier setup."},
    {"key": "atr_signal_w", "label": "ATR Signal W", "current": "stats.atr_signal_w", "historical": "historical_screener.atr_signal_w", "meaning": "Rolling weekly ATR Trailing Stop direction: 1 above, -1 below, 0 neutral."},
    {"key": "atr_crossed_above_w", "label": "Cross Up W", "current": "stats.atr_crossed_above_w", "historical": "historical_screener.atr_crossed_above_w", "meaning": "Rolling weekly ATR Trailing Stop crossed from bearish to bullish."},
    {"key": "atr_crossed_below_w", "label": "Cross Down W", "current": "stats.atr_crossed_below_w", "historical": "historical_screener.atr_crossed_below_w", "meaning": "Rolling weekly ATR Trailing Stop crossed from bullish to bearish."},
    {"key": "atr_stop_w", "label": "ATR Stop W", "current": "stats.atr_stop_w", "historical": "historical_screener.atr_stop_w", "meaning": "Rolling weekly ATR Trailing Stop line."},
    {"key": "atr_signal_m", "label": "ATR Signal M", "current": "stats.atr_signal_m", "historical": "historical_screener.atr_signal_m", "meaning": "Rolling monthly ATR Trailing Stop direction: 1 above, -1 below, 0 neutral."},
    {"key": "atr_crossed_above_m", "label": "Cross Up M", "current": "stats.atr_crossed_above_m", "historical": "historical_screener.atr_crossed_above_m", "meaning": "Rolling monthly ATR Trailing Stop crossed from bearish to bullish."},
    {"key": "atr_crossed_below_m", "label": "Cross Down M", "current": "stats.atr_crossed_below_m", "historical": "historical_screener.atr_crossed_below_m", "meaning": "Rolling monthly ATR Trailing Stop crossed from bullish to bearish."},
    {"key": "atr_stop_m", "label": "ATR Stop M", "current": "stats.atr_stop_m", "historical": "historical_screener.atr_stop_m", "meaning": "Rolling monthly ATR Trailing Stop line."},
    {"key": "atrp", "label": "ATR%", "current": "stats.atrp", "historical": "historical_screener.atrp", "meaning": "ATR percent as of the row date."},
    {"key": "accel_signal", "label": "Accel", "current": "stats.accel_signal", "historical": "historical_screener.accel_signal", "meaning": "Accel trend state: 1 up, -1 down, 0 neutral."},
    {"key": "accel_crossed_up", "label": "Accel Up", "current": "stats.accel_crossed_up", "historical": "historical_screener.accel_crossed_up", "meaning": "Accel crossed up on the row date."},
    {"key": "accel_crossed_down", "label": "Accel Down", "current": "stats.accel_crossed_down", "historical": "historical_screener.accel_crossed_down", "meaning": "Accel crossed down on the row date."},
    {"key": "st_bars_below", "label": "ATR Bars Below", "current": "stats.st_bars_below", "historical": "historical_screener.st_bars_below", "meaning": "Number of bars price stayed below ATR Trailing Stop before a cross-up."},
    {"key": "st_bars_above", "label": "ATR Bars Above", "current": "stats.st_bars_above", "historical": "historical_screener.st_bars_above", "meaning": "Number of bars price stayed above ATR Trailing Stop before a cross-down."},
    {"key": "accel_bars_below", "label": "Accel Bars Below", "current": "stats.accel_bars_below", "historical": "historical_screener.accel_bars_below", "meaning": "Number of bars price stayed below Accel before a cross-up."},
    {"key": "accel_bars_above", "label": "Accel Bars Above", "current": "stats.accel_bars_above", "historical": "historical_screener.accel_bars_above", "meaning": "Number of bars price stayed above Accel before a cross-down."},
    {"key": "marginable", "label": "Margin", "current": "stats.marginable", "historical": "assets.marginable", "meaning": "Can be traded on margin via Alpaca."},
    {"key": "shortable", "label": "Shortable", "current": "assets.shortable", "historical": "assets.shortable", "meaning": "Can be shorted via Alpaca."},
    {"key": "fractionable", "label": "Frac", "current": "stats.fractionable", "historical": "assets.fractionable", "meaning": "Broker/universe fractionable flag."},
    {"key": "profit_status", "label": "Profit", "current": "stats.profit_status", "historical": "stats.profit_status", "meaning": "Current earnings/profit status until a historical fundamentals table exists."},
    {"key": "last_updated", "label": "Updated", "current": "stats.last_updated", "historical": "historical_screener.date", "meaning": "Current mode stats update timestamp; date mode selected as-of date."},
]


@app.context_processor
def inject_market():
    market = "US"
    if request.path.startswith("/india"):
        market = "INDIA"
    elif request.path.startswith("/crypto"):
        market = "CRYPTO"
    other = "INDIA" if market == "US" else ("US" if market == "INDIA" else "CRYPTO")
    return {"market": market, "other_market": other}


@app.route("/")
def home():
    return render_template("screener.html", market="US")


@app.route("/india/")
def india_home():
    return render_template("screener.html", market="INDIA")


@app.route("/stock/<symbol>")
@app.route("/india/stock/<symbol>")
def stock_detail(symbol):
    market = "INDIA" if "/india/" in request.path else "US"
    return render_template("stock_detail.html", symbol=symbol, market=market)


@app.route("/portfolio")
def portfolio_list():
    return render_template("portfolio_list.html", market="US")


@app.route("/india/portfolio")
def india_portfolio_list():
    return render_template("portfolio_list.html", market="INDIA")


@app.route("/portfolio/<int:pid>")
@app.route("/india/portfolio/<int:pid>")
def portfolio_detail(pid):
    market = "INDIA" if "/india/" in request.path else "US"
    return render_template("portfolio_detail.html", pid=pid, market=market)


@app.route("/portfolio/<int:pid>/details")
@app.route("/india/portfolio/<int:pid>/details")
def portfolio_inside(pid):
    market = "INDIA" if "/india/" in request.path else "US"
    return render_template("portfolio_inside.html", pid=pid, market=market)


@app.route("/portfolio/overall")
@app.route("/india/portfolio/overall")
def portfolio_overall():
    market = "INDIA" if "/india/" in request.path else "US"
    return render_template("portfolio_overall.html", market=market)


@app.route("/portfolio/<int:pid>/string/<int:psid>")
@app.route("/india/portfolio/<int:pid>/string/<int:psid>")
def string_detail_from_portfolio(pid, psid):
    market = "INDIA" if "/india/" in request.path else "US"
    return render_template("string_detail_portfolio.html", pid=pid, psid=psid, market=market)


@app.route("/portfolio/ai-discovered")
@app.route("/india/portfolio/ai-discovered")
def ai_discovered_list():
    market = "INDIA" if "/india/" in request.path else "US"
    return render_template("ai_discovered_list.html", market=market)


@app.route("/portfolio/ai-discovered/<int:pid>")
@app.route("/india/portfolio/ai-discovered/<int:pid>")
def ai_discovered_detail(pid):
    market = "INDIA" if "/india/" in request.path else "US"
    return render_template("ai_discovered_detail.html", pid=pid, market=market)


def string_screener_detail(sid):
    market = "INDIA" if "/india/" in request.path else "US"
    return render_template("string_strategy_detail.html", sid=sid, market=market)


@app.route("/paper-trading")
def paper_trading():
    return render_template("paper_trading.html", market="US")


@app.route("/india/paper-trading")
def india_paper_trading():
    return render_template("paper_trading.html", market="INDIA")


@app.route("/vault")
def vault():
    from dumbmoney.vault_data import VAULT_STRATEGIES
    return render_template("vault.html", market="US", strategies=VAULT_STRATEGIES)


@app.route("/vault/<slug>")
def vault_strategy(slug):
    from dumbmoney.vault_data import VAULT_STRATEGIES
    strategy = next((s for s in VAULT_STRATEGIES if s["slug"] == slug), None)
    if not strategy:
        return "Strategy not found", 404
    return render_template("vault_strategy.html", market="US", strategy=strategy)


@app.route("/india/vault")
def india_vault():
    from dumbmoney.vault_data import VAULT_STRATEGIES
    return render_template("vault.html", market="INDIA", strategies=VAULT_STRATEGIES)


@app.route("/india/vault/<slug>")
def india_vault_strategy(slug):
    from dumbmoney.vault_data import VAULT_STRATEGIES
    strategy = next((s for s in VAULT_STRATEGIES if s["slug"] == slug), None)
    if not strategy:
        return "Strategy not found", 404
    return render_template("vault_strategy.html", market="INDIA", strategy=strategy)


@app.route("/settings")
def settings_page():
    return render_template("settings.html", market="US")


@app.route("/india/settings")
def india_settings_page():
    return render_template("settings.html", market="INDIA")


# ===========================================================================
# CRYPTO routes
# ===========================================================================

@app.route("/crypto/")
def crypto_home():
    return render_template("crypto_screener.html", market="CRYPTO")


@app.route("/crypto/stock/<symbol>")
def crypto_stock_detail(symbol):
    return render_template("stock_detail.html", symbol=symbol, market="CRYPTO")


@app.route("/crypto/portfolio")
def crypto_portfolio_list():
    return render_template("portfolio_list.html", market="CRYPTO")


@app.route("/crypto/portfolio/<int:pid>")
def crypto_portfolio_detail(pid):
    return render_template("portfolio_detail.html", pid=pid, market="CRYPTO")


@app.route("/crypto/paper-trading")
def crypto_paper_trading():
    from dumbmoney.data_crypto import get_all_symbols
    symbols = get_all_symbols()
    return render_template("crypto_paper_trading.html", market="CRYPTO", symbols=symbols)


# ===========================================================================
# CRYPTO API endpoints
# ===========================================================================

@crypto_bp.route("/api/crypto/products")
def api_crypto_products():
    from dumbmoney.crypto import get_crypto_products
    return jsonify(get_crypto_products())


@crypto_bp.route("/api/crypto/ticker")
def api_crypto_ticker():
    from dumbmoney.crypto_ws import get_all_live_tickers
    from dumbmoney.data_crypto import fetch_tickers
    tickers = get_all_live_tickers()
    if not tickers:
        tickers = fetch_tickers()
    return jsonify(tickers)


@crypto_bp.route("/api/crypto/ticker/<symbol>")
def api_crypto_ticker_single(symbol):
    from dumbmoney.crypto_ws import get_live_ticker
    from dumbmoney.data_crypto import fetch_tickers
    t = get_live_ticker(symbol)
    if not t:
        all_t = fetch_tickers()
        t = all_t.get(symbol, {})
    return jsonify(t)


@crypto_bp.route("/api/crypto/screener")
def api_crypto_screener():
    from dumbmoney.crypto import get_crypto_screener
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(max(1, int(request.args.get("per_page", 50))), 200)
    sort = request.args.get("sort", "volume")
    sort_dir = request.args.get("sort_dir", "desc")
    search = request.args.get("search", "")
    force = request.args.get("force", "0") == "1"
    date_cutoff = request.args.get("date_cutoff", "")
    args = {
        "min_price": request.args.get("min_price"),
        "max_price": request.args.get("max_price"),
        "min_change": request.args.get("min_change"),
        "max_change": request.args.get("max_change"),
        "min_wa": request.args.get("min_wa"),
        "max_wa": request.args.get("max_wa"),
        "min_streak": request.args.get("min_streak"),
        "min_volume": request.args.get("min_volume"),
        "atr_status": request.args.get("atr_status"),
        "atr_status_w": request.args.get("atr_status_w"),
        "atr_status_m": request.args.get("atr_status_m"),
        "accel_status": request.args.get("accel_status"),
        "min_st_bars_below": request.args.get("min_st_bars_below"),
        "min_st_bars_above": request.args.get("min_st_bars_above"),
        "min_accel_bars_below": request.args.get("min_accel_bars_below"),
        "min_accel_bars_above": request.args.get("min_accel_bars_above"),
        "min_oi": request.args.get("min_oi"),
        "min_funding_rate": request.args.get("min_funding_rate"),
    }
    result = get_crypto_screener(page=page, per_page=per_page, sort=sort, sort_dir=sort_dir,
                                  search=search, force=force, date_cutoff=date_cutoff, args=args)
    return jsonify(result)


@crypto_bp.route("/api/crypto/screener/columns")
def api_crypto_screener_columns():
    from dumbmoney.crypto import get_crypto_screener_columns
    return jsonify({"columns": get_crypto_screener_columns()})


@crypto_bp.route("/api/crypto/candles")
def api_crypto_candles():
    from dumbmoney.crypto import get_crypto_chart
    symbol = request.args.get("symbol", "BTCUSD")
    timeframe = request.args.get("timeframe", "1d")
    limit = min(int(request.args.get("limit", 500)), 2000)
    candles = get_crypto_chart(symbol, timeframe=timeframe, limit=limit)
    return jsonify(candles)


@crypto_bp.route("/api/crypto/download", methods=["POST"])
def api_crypto_download():
    """Trigger candle backfill for one resolution (threaded; poll
    /api/crypto/download/status)."""
    from dumbmoney.data_crypto import get_all_symbols, download_candles
    body = request.get_json() or {}
    resolution = body.get("resolution", "1d")
    days_back = int(body.get("days_back", 730))
    symbols = body.get("symbols") or get_all_symbols()
    total = len(symbols)

    def _persist(done):
        try:
            from dumbmoney.db import get_db as _gdb
            import json as _json
            c = _gdb("CRYPTO")
            c.execute("INSERT OR REPLACE INTO crypto_settings (key, value) VALUES ('download_progress', ?)",
                      (_json.dumps({"resolution": resolution, "done": done, "total": total}),))
            c.commit()
            c.close()
        except Exception:
            pass

    def _run():
        done = 0
        for sym in symbols:
            if _crypto_download_cancel.is_set():
                break
            try:
                download_candles(sym, resolution, days_back)
            except Exception as e:
                logger.warning(f"[CRYPTO] download {sym} {resolution}: {e}")
            done += 1
            if done % 5 == 0 or done == total:
                _persist(done)
        _persist(total)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"started": True, "total": total, "resolution": resolution})


@crypto_bp.route("/api/crypto/backfill-all", methods=["POST"])
def api_crypto_backfill_all():
    """Download all supported timeframes for all symbols (threaded)."""
    from dumbmoney.data_crypto import backfill_all_timeframes

    def _run():
        def progress(pct, msg):
            logger.info(f"[CRYPTO] backfill progress: {pct:.0f}% — {msg}")
        try:
            backfill_all_timeframes(progress_callback=progress)
        except Exception as e:
            logger.error(f"[CRYPTO] backfill-all failed: {e}", exc_info=True)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"started": True})


_crypto_download_cancel = threading.Event()
_crypto_refresh_thread = None
_crypto_refresh_cancel = threading.Event()


@crypto_bp.route("/api/crypto/refresh", methods=["POST"])
def api_crypto_refresh():
    """Start crypto backfill with progress tracking."""
    global _crypto_refresh_thread
    from dumbmoney.db import get_db as _get_db

    # Check if already running
    try:
        conn = _get_db("CRYPTO")
        row = conn.execute("SELECT value FROM crypto_settings WHERE key='refresh_status'").fetchone()
        conn.close()
        if row and row[0]:
            import json as _json
            st = _json.loads(row[0])
            if st.get("status") == "running":
                # Check if thread is actually alive (not a stale DB entry from crashed process)
                thread_alive = _crypto_refresh_thread and _crypto_refresh_thread.is_alive()
                if thread_alive:
                    return jsonify({"started": False, "error": "Already running"})
                # Stale status — clear it and allow new refresh
    except Exception:
        pass

    _crypto_refresh_cancel.clear()

    import time as _time
    import json as _json
    started_at = _time.time()
    _init_status = _json.dumps({
        "status": "running", "market": "CRYPTO",
        "step_detail": "Starting crypto refresh...",
        "phase": "", "overall_pct": 0,
        "symbols_total": 0, "symbols_done": 0,
        "elapsed_sec": 0, "eta_sec": 0, "started_at": started_at,
    })
    conn = _get_db("CRYPTO")
    conn.execute(
        "INSERT OR REPLACE INTO crypto_settings (key, value) VALUES ('refresh_status', ?)",
        (_init_status,),
    )
    conn.commit()
    conn.close()

    def _run():
        import time as _time
        import traceback as _tb
        from dumbmoney.data_crypto import get_all_symbols, download_candles, TIMEFRAMES

        try:
            conn = _get_db("CRYPTO")
            symbols = get_all_symbols()
            done_ops = 0
            started_at = _time.time()

            def _persist(status_dict):
                try:
                    c = _get_db("CRYPTO")
                    c.execute(
                        "INSERT OR REPLACE INTO crypto_settings (key, value) VALUES ('refresh_status', ?)",
                        (_json.dumps(status_dict),)
                    )
                    c.commit()
                    c.close()
                except Exception:
                    pass

            _persist({
                "status": "running", "market": "CRYPTO",
                "step_detail": "Downloading candles...",
                "phase": "", "overall_pct": 1,
                "symbols_total": len(symbols), "symbols_done": 0,
                "elapsed_sec": 0, "eta_sec": 0, "started_at": started_at,
            })

            # Build download tasks — only screener timeframes (1d, 1w)
            # Intraday (1m-6h) is downloaded on-demand for charts, not during refresh
            screener_tfs = {k: v for k, v in TIMEFRAMES.items() if k in ('1d', '1w')}
            tasks = []
            for tf, days in screener_tfs.items():
                for sym in symbols:
                    # Skip if latest bar is < 4 hours old (incremental refresh)
                    _ck = conn.execute(
                        "SELECT MAX(date) FROM crypto_bars WHERE symbol=? AND timeframe=?",
                        (sym, tf),
                    ).fetchone()
                    if _ck and _ck[0]:
                        try:
                            _latest = _ck[0]
                            if " " in _latest:
                                _ts = _time.mktime(_time.strptime(_latest, "%Y-%m-%d %H:%M:%S"))
                            else:
                                _ts = _time.mktime(_time.strptime(_latest, "%Y-%m-%d"))
                            if (_time.time() - _ts) < 14400:  # 4 hours
                                continue
                        except Exception:
                            pass
                    tasks.append((sym, tf, days))

            conn.close()

            total_ops = len(tasks)
            done_ops = 0
            _persist({
                "status": "running", "market": "CRYPTO",
                "step_detail": f"Downloading candles ({total_ops} tasks, parallel)...",
                "phase": "", "overall_pct": 1,
                "symbols_total": len(symbols), "symbols_done": 0,
                "elapsed_sec": 0, "eta_sec": 0, "started_at": started_at,
            })

            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {
                    executor.submit(download_candles, sym, tf, days): (sym, tf)
                    for sym, tf, days in tasks
                }
                for future in as_completed(futures):
                    if _crypto_refresh_cancel.is_set():
                        executor.shutdown(wait=False, cancel_futures=True)
                        _persist({"status": "cancelled", "market": "CRYPTO", "step_detail": "Cancelled"})
                        return
                    sym, tf = futures[future]
                    done_ops += 1
                    try:
                        future.result(timeout=30)
                    except Exception:
                        pass
                    elapsed = _time.time() - started_at
                    pct = done_ops / total_ops * 95
                    eta = (elapsed / done_ops * (total_ops - done_ops)) if done_ops > 0 else 0
                    if done_ops % 5 == 0 or done_ops == total_ops:
                        elapsed = _time.time() - started_at
                        pct = done_ops / total_ops * 95
                        eta = (elapsed / done_ops * (total_ops - done_ops)) if done_ops > 0 else 0
                        _persist({
                            "status": "running", "market": "CRYPTO",
                            "step_detail": f"Downloading candles ({done_ops}/{total_ops})",
                            "phase": f"{sym} {tf}",
                            "overall_pct": round(pct, 1),
                            "symbols_total": len(symbols),
                            "symbols_done": done_ops // len(screener_tfs),
                            "elapsed_sec": int(elapsed),
                            "eta_sec": int(eta),
                            "started_at": started_at,
                        })

            # Compute indicators
            _persist({
                "status": "running", "market": "CRYPTO",
                "step_detail": "Computing indicators...",
                "phase": "", "overall_pct": 95,
                "symbols_total": len(symbols), "symbols_done": 0,
                "elapsed_sec": int(_time.time() - started_at), "eta_sec": 30,
                "started_at": started_at,
            })

            from dumbmoney.engine import compute_crypto_stats_batch, update_crypto_historical_screener

            def _compute_progress(d, t):
                _persist({
                    "status": "running", "market": "CRYPTO",
                    "step_detail": f"Computing indicators: {t}",
                    "phase": t, "overall_pct": min(95 + d * 0.025, 97.5),
                    "symbols_total": len(symbols), "symbols_done": 0,
                    "elapsed_sec": int(_time.time() - started_at), "eta_sec": 30,
                    "started_at": started_at,
                })

            compute_crypto_stats_batch(only_symbols=symbols, progress_callback=_compute_progress)
            update_crypto_historical_screener(only_symbols=symbols, progress_callback=_compute_progress)
            # Merge live OI/funding/mark/bid-ask into crypto_stats
            try:
                from dumbmoney.data_crypto import update_live_columns
                update_live_columns()
            except Exception as e:
                logger.warning(f"[CRYPTO] live columns update failed: {e}")

            _persist({
                "status": "complete", "market": "CRYPTO",
                "step_detail": "Crypto backfill complete",
                "phase": "", "overall_pct": 100,
                "symbols_total": len(symbols), "symbols_done": len(symbols),
                "elapsed_sec": int(_time.time() - started_at), "eta_sec": 0,
                "started_at": started_at,
            })
        except Exception as e:
            logger.error(f"Crypto refresh error: {e}", exc_info=True)
            _persist({
                "status": "error", "market": "CRYPTO",
                "step_detail": f"Error: {e}",
                "phase": "", "overall_pct": 0,
                "symbols_total": 0, "symbols_done": 0,
                "elapsed_sec": 0, "eta_sec": 0,
                "started_at": started_at if 'started_at' in dir() else 0,
            })

    _crypto_refresh_thread = threading.Thread(target=_run, daemon=True)
    _crypto_refresh_thread.start()
    return jsonify({"started": True})


@crypto_bp.route("/api/crypto/refresh/status")
def api_crypto_refresh_status():
    """Get crypto refresh progress."""
    from dumbmoney.db import get_db as _get_db
    import json as _json
    try:
        conn = _get_db("CRYPTO")
        row = conn.execute("SELECT value FROM crypto_settings WHERE key='refresh_status'").fetchone()
        conn.close()
        if row and row[0]:
            d = _json.loads(row[0])
            # If thread is alive, force status to running even if DB row is stale
            if _crypto_refresh_thread and _crypto_refresh_thread.is_alive():
                if d.get("status") not in ("running",):
                    d["status"] = "running"
                    d["step_detail"] = d.get("step_detail") or "Processing..."
            return jsonify(d)
    except Exception:
        pass
    # No row in DB — check if thread is still alive
    if _crypto_refresh_thread and _crypto_refresh_thread.is_alive():
        return jsonify({
            "status": "running", "market": "CRYPTO",
            "step_detail": "Processing...", "phase": "", "overall_pct": 0,
            "symbols_total": 0, "symbols_done": 0,
            "elapsed_sec": 0, "eta_sec": 0,
        })
    return jsonify({
        "status": "idle", "market": "CRYPTO",
        "step_detail": "", "phase": "", "overall_pct": 0,
        "symbols_total": 0, "symbols_done": 0,
        "elapsed_sec": 0, "eta_sec": 0,
    })


@crypto_bp.route("/api/crypto/refresh/cancel", methods=["POST"])
def api_crypto_refresh_cancel():
    """Cancel crypto refresh."""
    _crypto_refresh_cancel.set()
    from dumbmoney.db import get_db as _get_db
    import json as _json
    try:
        conn = _get_db("CRYPTO")
        conn.execute(
            "INSERT OR REPLACE INTO crypto_settings (key, value) VALUES ('refresh_status', ?)",
            (_json.dumps({"status": "cancelled", "market": "CRYPTO", "step_detail": "Cancelled"}),)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    return jsonify({"cancelled": True})


@crypto_bp.route("/api/crypto/download/status")
def api_crypto_download_status():
    from dumbmoney.db import get_db
    conn = get_db("CRYPTO")
    try:
        row = conn.execute("SELECT value FROM crypto_settings WHERE key='download_progress'").fetchone()
        return jsonify(json.loads(row[0]) if row else {})
    finally:
        conn.close()


@crypto_bp.route("/api/crypto/positions")
def api_crypto_positions():
    from dumbmoney.data_crypto import get_positions
    try:
        positions = get_positions()
        return jsonify(positions if positions else [])
    except Exception:
        return jsonify([])


@crypto_bp.route("/api/crypto/balances")
def api_crypto_balances():
    from dumbmoney.data_crypto import get_balances
    try:
        balances = get_balances()
        return jsonify(balances if balances else [])
    except Exception:
        return jsonify([])


@crypto_bp.route("/api/crypto/order", methods=["POST"])
def api_crypto_order():
    """Place a Delta order. Accepts either product_id or symbol (resolved to its
    numeric product_id) and limit_price/stop_price (or legacy 'price' for limits)."""
    from dumbmoney.data_crypto import place_order, get_all_products
    body = request.get_json()
    side = body.get("side", "buy")
    qty = float(body.get("qty", 0))
    order_type = body.get("order_type", "market_order")
    limit_price = body.get("limit_price") or (body.get("price") if order_type == "limit_order" else None)
    stop_price = body.get("stop_price")
    leverage = body.get("leverage")

    product_id = body.get("product_id")
    if not product_id:
        symbol = str(body.get("symbol", "")).upper()
        products = {p.get("symbol", "").upper(): p for p in (get_all_products() or [])}
        prod = products.get(symbol)
        if not prod:
            return jsonify({"error": f"Unknown symbol {symbol}"}), 400
        product_id = prod.get("id") or prod.get("product_id")
    try:
        result = place_order(int(product_id), qty, side, order_type=order_type,
                             limit_price=limit_price, stop_price=stop_price, leverage=leverage)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@crypto_bp.route("/api/crypto/cancel-order", methods=["POST"])
def api_crypto_cancel_order():
    from dumbmoney.data_crypto import cancel_order, get_all_products
    body = request.get_json()
    order_id = body.get("order_id")
    product_id = body.get("product_id")
    if not product_id:
        symbol = str(body.get("symbol", "")).upper()
        products = {p.get("symbol", "").upper(): p for p in (get_all_products() or [])}
        prod = products.get(symbol)
        if not prod:
            return jsonify({"error": f"Unknown symbol {symbol}"}), 400
        product_id = prod.get("id") or prod.get("product_id")
    try:
        cancel_order(order_id, int(product_id))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500




@crypto_bp.route("/api/crypto/history")
def api_crypto_history():
    """Get trade history for the sidebar panel."""
    from dumbmoney.data_crypto import get_trade_history
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        return jsonify(get_trade_history(limit=limit))
    except Exception:
        return jsonify([])
@crypto_bp.route("/api/crypto/order-history")
def api_crypto_order_history():
    from dumbmoney.data_crypto import get_order_history
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify(get_order_history(limit=limit))




@crypto_bp.route("/api/crypto/account")
def api_crypto_account():
    """Get Delta account overview for the sidebar."""
    from dumbmoney.data_crypto import get_account_info
    try:
        return jsonify(get_account_info())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@crypto_bp.route("/api/crypto/close-all", methods=["POST"])
def api_crypto_close_all():
    """Close all open positions (authenticated)."""
    from dumbmoney.config import DELTA_API_KEY as _KEY
    if not _KEY:
        return jsonify({"error": "No API key configured"}), 400
    from dumbmoney.data_crypto import get_positions, place_order
    try:
        positions = get_positions() or []
        closed = 0
        for pos in positions:
            size = float(pos.get("size", 0) or 0)
            if size != 0:
                place_order(
                    int(pos.get("product_id")),
                    abs(size),
                    "buy" if size < 0 else "sell",
                    order_type="market_order",
                )
                closed += 1
        return jsonify({"closed": closed})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Crypto Portfolio APIs (separate from US/India since they use different data sources) ---

@crypto_bp.route("/api/crypto/portfolios")
def api_crypto_portfolios():
    from dumbmoney.db import get_db
    from dumbmoney.data_crypto import fetch_tickers
    conn = get_db("CRYPTO")
    try:
        tickers = fetch_tickers()
        rows = conn.execute("SELECT * FROM portfolios ORDER BY created_at DESC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            strings = conn.execute(
                "SELECT * FROM portfolio_strings WHERE portfolio_id=? ORDER BY created_at", (r["id"],)
            ).fetchall()
            str_list = []
            total_pnl = 0
            for s in strings:
                sd = dict(s)
                ep = sd.get("entry_price") or 0
                sym_rows = conn.execute(
                    "SELECT symbol, qty FROM portfolio_string_symbols WHERE portfolio_string_id=?", (sd["id"],)
                ).fetchall()
                entry_value = ep
                current_value = 0
                for sy in sym_rows:
                    t = tickers.get(sy["symbol"], {})
                    price = t.get("close", 0) or 0
                    qty = sy["qty"] or 0
                    current_value += price * qty
                rp_raw = sd.get("realised_pnl")
                rp = float(rp_raw) if rp_raw is not None and str(rp_raw) not in ('None', 'null', '') else 0.0
                up = current_value - entry_value if entry_value else 0
                sd["entry_value"] = entry_value
                sd["current_value"] = current_value
                sd["realised_pnl"] = rp
                sd["unrealised_pnl"] = up
                sd["pnl_pct"] = ((current_value / entry_value - 1) * 100) if entry_value else 0
                sd["num_stocks"] = len(sym_rows)
                total_pnl += rp + up
                str_list.append(sd)
            d["strings"] = str_list
            d["total_pnl"] = total_pnl
            d["num_strings"] = len(str_list)
            result.append(d)
        return jsonify(result)
    finally:
        conn.close()


@crypto_bp.route("/api/crypto/portfolio/<int:pid>/detail")
def api_crypto_portfolio_detail(pid):
    from dumbmoney.db import get_db
    from dumbmoney.data_crypto import fetch_tickers
    conn = get_db("CRYPTO")
    try:
        tickers = fetch_tickers()
        port = conn.execute("SELECT * FROM portfolios WHERE id=?", (pid,)).fetchone()
        if not port:
            return jsonify({"error": "Portfolio not found"}), 404
        pd_ = dict(port)
        strings = conn.execute(
            "SELECT * FROM portfolio_strings WHERE portfolio_id=? ORDER BY status='running' DESC, created_at DESC", (pid,)
        ).fetchall()
        pd_["strings"] = []
        booked_profit = 0
        running_value = 0
        running_invested = 0
        running_unrealised = 0
        closed_count = 0
        running_count = 0
        win_count = 0
        total_return_list = []

        for s in strings:
            sd = dict(s)
            sym_rows = conn.execute(
                "SELECT symbol, qty, weight FROM portfolio_string_symbols WHERE portfolio_string_id=?",
                (s["id"],)
            ).fetchall()
            sd["num_stocks"] = len(sym_rows)
            is_running = sd.get("status") != "closed"

            if sym_rows:
                sv = sum((tickers.get(x["symbol"], {}).get("close", 0) or 0) * float(x["qty"]) for x in sym_rows)
                sd["current_value"] = sv
                sd["total_value"] = sv
                entry_total = float(sd.get("entry_price") or 0)
                sd["entry_value"] = entry_total

                if is_running:
                    up = sv - entry_total
                    sd["unrealised_pnl"] = up
                    running_value += sv
                    running_invested += entry_total
                    running_unrealised += up
                    running_count += 1
                    if entry_total > 0:
                        total_return_list.append((sv / entry_total - 1) * 100)
                else:
                    rp_raw = sd.get("realised_pnl")
                    rp = float(rp_raw) if rp_raw is not None and str(rp_raw) not in ('None', 'null', '') else (sv - entry_total)
                    sd["realised_pnl"] = rp
                    sd["unrealised_pnl"] = 0
                    booked_profit += rp
                    closed_count += 1
                    if entry_total > 0:
                        total_return_list.append(rp / entry_total * 100)
                    if rp > 0:
                        win_count += 1
            else:
                sd["current_value"] = 0
                sd["entry_value"] = 0
                sd["unrealised_pnl"] = 0
                sd["realised_pnl"] = 0

            pd_["strings"].append(sd)

        total_invested = running_invested
        total_value = running_value + booked_profit
        total_pnl = running_unrealised + booked_profit
        today_pnl = running_unrealised  # simplified — no previous day tracking yet

        pd_["running_value"] = running_value
        pd_["booked_profit"] = booked_profit
        pd_["total_value"] = total_value
        pd_["total_invested"] = total_invested
        pd_["total_pnl"] = total_pnl
        pd_["today_pnl"] = today_pnl
        pd_["win_rate"] = round(win_count / closed_count * 100, 1) if closed_count > 0 else 0
        pd_["avg_return_pct"] = round(sum(total_return_list) / len(total_return_list), 2) if total_return_list else 0
        pd_["best_trade_pct"] = round(max(total_return_list), 2) if total_return_list else 0
        pd_["worst_trade_pct"] = round(min(total_return_list), 2) if total_return_list else 0
        pd_["closed_count"] = closed_count
        pd_["running_count"] = running_count

        return jsonify(pd_)
    finally:
        conn.close()


@crypto_bp.route("/api/crypto/settings", methods=["GET"])
def api_crypto_settings_get():
    from dumbmoney.db import get_db
    conn = get_db("CRYPTO")
    try:
        rows = conn.execute("SELECT key, value FROM crypto_settings").fetchall()
        return jsonify({r[0]: r[1] for r in rows})
    finally:
        conn.close()


@crypto_bp.route("/api/crypto/settings", methods=["POST"])
def api_crypto_settings_set():
    from dumbmoney.db import get_db
    body = request.get_json()
    conn = get_db("CRYPTO")
    try:
        for key, value in body.items():
            conn.execute(
                "INSERT OR REPLACE INTO crypto_settings (key, value) VALUES (?, ?)",
                (key, json.dumps(value) if isinstance(value, (dict, list)) else str(value))
            )
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


app.register_blueprint(crypto_bp, url_prefix="")


@api_bp.route("/screener")
def api_screener():
    market = request.args.get("market", "US")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = min(max(1, int(request.args.get("per_page", 50))), 500)
    except (TypeError, ValueError):
        per_page = 50
    sort = request.args.get("sort", "weighted_alpha")
    sort_dir = request.args.get("sort_dir") or request.args.get("order", "desc")
    search = request.args.get("search", "")
    exchange = request.args.get("exchange", "")
    asset_type = request.args.get("asset_type", "")
    timeframe = request.args.get("timeframe", "1Day")
    date_cutoff = request.args.get("date_cutoff", "")

    conn = get_db(market)
    try:
        if date_cutoff:
            return jsonify(_build_historical_query(conn, market, date_cutoff, search, exchange, asset_type,
                                                    sort, sort_dir, page, per_page, request.args))
        else:
            return jsonify(_build_stats_query(conn, market, search, exchange, asset_type,
                                               sort, sort_dir, page, per_page, request.args))
    finally:
        conn.close()


@api_bp.route("/screener/columns")
def api_screener_columns():
    return jsonify({"columns": SCREENER_COLUMN_REFERENCE})


def _leveraged_etf_sql(name_col="s.name", asset_col="s.asset_class"):
    """Multi-signal leveraged ETF detection: name patterns + asset class = etf.

    Broad detection covering: leverage ratios (2x/3x/4x/5x), ProShares families
    (UltraPro/Ultra/Short), Direxion Daily, and keywords (Leveraged/Inverse/Bear/Short).
    """
    name_patterns = (
        f"({name_col} LIKE '%2x%'"
        f" OR {name_col} LIKE '%3x%'"
        f" OR {name_col} LIKE '%4x%'"
        f" OR {name_col} LIKE '%5x%'"
        f" OR {name_col} LIKE '%2X%'"
        f" OR {name_col} LIKE '%3X%'"
        f" OR {name_col} LIKE '%4X%'"
        f" OR {name_col} LIKE '%5X%'"
        f" OR {name_col} LIKE '%UltraPro%'"
        f" OR {name_col} LIKE '%Ultra Bull%'"
        f" OR {name_col} LIKE '%Ultra Bear%'"
        f" OR {name_col} LIKE '%Ultra Short%'"
        f" OR {name_col} LIKE '%Ultra VIX%'"
        f" OR {name_col} LIKE '%ProShares Ultra%'"
        f" OR {name_col} LIKE '%ProShares Short%'"
        f" OR {name_col} LIKE '%Direxion Daily%'"
        f" OR {name_col} LIKE '%Leveraged%'"
        f" OR {name_col} LIKE '%Inverse%'"
        f" OR {name_col} LIKE '%Bear%'"
        f" OR {name_col} LIKE '%Short%')"
    )
    return f"({name_patterns} AND {asset_col} = 'etf')"


def _build_historical_query(conn, market, date_cutoff, search, exchange, asset_type,
                             sort, sort_dir, page, per_page, args):
    where = ["h.date = ?"]
    params = [date_cutoff]

    if search:
        where.append("(h.symbol LIKE ? OR a.name LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if exchange:
        where.append("a.exchange = ?")
        params.append(exchange)
    if asset_type:
        where.append("a.asset_class = ?")
        params.append(asset_type)

    min_price = args.get("min_price")
    max_price = args.get("max_price")
    if min_price:
        where.append("h.price >= ?")
        params.append(float(min_price))
    if max_price:
        where.append("h.price <= ?")
        params.append(float(max_price))

    min_volume = args.get("min_volume")
    if min_volume:
        where.append("h.volume >= ?")
        params.append(int(min_volume))

    min_change = args.get("min_change")
    max_change = args.get("max_change")
    if min_change:
        where.append("h.change_pct >= ?")
        params.append(float(min_change))
    if max_change:
        where.append("h.change_pct <= ?")
        params.append(float(max_change))

    min_wa = args.get("min_wa")
    max_wa = args.get("max_wa")
    if min_wa:
        where.append("h.weighted_alpha >= ?")
        params.append(float(min_wa))
    if max_wa:
        where.append("h.weighted_alpha <= ?")
        params.append(float(max_wa))

    min_streak = args.get("min_streak")
    if min_streak:
        where.append("h.streak >= ?")
        params.append(int(min_streak))

    atr_status = args.get("atr_status")
    if atr_status:
        if atr_status == "above":
            where.append("h.atr_signal = 1")
        elif atr_status == "below":
            where.append("h.atr_signal = -1")
        elif atr_status == "crossed-above":
            where.append("h.atr_crossed_above = 1")
        elif atr_status == "crossed-below":
            where.append("h.atr_crossed_below = 1")

    atr_status_w = args.get("atr_status_w")
    if atr_status_w:
        if atr_status_w == "above":
            where.append("h.atr_signal_w = 1")
        elif atr_status_w == "below":
            where.append("h.atr_signal_w = -1")
        elif atr_status_w == "crossed-above":
            where.append("h.atr_crossed_above_w = 1")
        elif atr_status_w == "crossed-below":
            where.append("h.atr_crossed_below_w = 1")

    atr_status_m = args.get("atr_status_m")
    if atr_status_m:
        if atr_status_m == "above":
            where.append("h.atr_signal_m = 1")
        elif atr_status_m == "below":
            where.append("h.atr_signal_m = -1")
        elif atr_status_m == "crossed-above":
            where.append("h.atr_crossed_above_m = 1")
        elif atr_status_m == "crossed-below":
            where.append("h.atr_crossed_below_m = 1")

    accel_status = args.get("accel_status")
    if accel_status:
        if accel_status == "up":
            where.append("h.accel_signal = 1")
        elif accel_status == "down":
            where.append("h.accel_signal = -1")
        elif accel_status == "crossed-up":
            where.append("h.accel_crossed_up = 1")
        elif accel_status == "crossed-down":
            where.append("h.accel_crossed_down = 1")

    fractionable = args.get("fractionable")
    if fractionable:
        where.append("a.fractionable = ?")
        params.append(1 if fractionable == "yes" else 0)
    shortable = args.get("shortable")
    if shortable:
        where.append("a.shortable = ?")
        params.append(1 if shortable == "yes" else 0)

    profit_status = args.get("profit_status")
    if profit_status and not date_cutoff:
        where.append("s.profit_status = ?")
        params.append(profit_status)

    leveraged = args.get("leveraged")
    if leveraged == "yes":
        where.append(_leveraged_etf_sql(name_col="a.name", asset_col="a.asset_class"))

    nifty500 = args.get("nifty500")
    if nifty500 == "yes" and market == "INDIA":
        where.append("h.symbol IN (SELECT symbol FROM nifty500_constituents WHERE ? >= from_date AND ? <= to_date)")
        params.extend([date_cutoff, date_cutoff])

    index_filter = args.get("index")
    if index_filter:
        india_map = {"nifty500": "nifty500_constituents", "nifty50": "nifty50_constituents", "fo": "fo_constituents"}
        us_map = {"sp500": "sp500_constituents", "nasdaq100": "nasdaq100_constituents", "russell2000": "russell2000_constituents", "dow30": "dow30_constituents"}
        table_map = india_map if market == "INDIA" else us_map
        tbl = table_map.get(index_filter)
        if tbl:
            where.append(f"h.symbol IN (SELECT symbol FROM {tbl} WHERE ? >= from_date AND ? <= to_date)")
            params.extend([date_cutoff, date_cutoff])

    min_st_bars_below = args.get("min_st_bars_below")
    if min_st_bars_below:
        where.append("h.st_bars_below >= ?")
        params.append(int(min_st_bars_below))
    min_st_bars_above = args.get("min_st_bars_above")
    if min_st_bars_above:
        where.append("h.st_bars_above >= ?")
        params.append(int(min_st_bars_above))
    min_accel_bars_below = args.get("min_accel_bars_below")
    if min_accel_bars_below:
        where.append("h.accel_bars_below >= ?")
        params.append(int(min_accel_bars_below))
    min_accel_bars_above = args.get("min_accel_bars_above")
    if min_accel_bars_above:
        where.append("h.accel_bars_above >= ?")
        params.append(int(min_accel_bars_above))

    where_str = " AND ".join(where)

    # crypto.db namespaces its tables (crypto_historical_screener) and keeps no
    # asset rows, so the assets join must not filter there.
    is_crypto = str(market).upper() == "CRYPTO"
    hs_table = "crypto_historical_screener" if is_crypto else "historical_screener"
    asset_join = ("LEFT JOIN assets a ON h.symbol = a.symbol" if is_crypto
                  else "JOIN assets a ON h.symbol = a.symbol")
    # Alpaca shortability only exists for US; other markets get NULL so the UI
    # renders '-' instead of a misleading "No".
    shortable_expr = "a.shortable" if str(market).upper() == "US" else "NULL as shortable"
    base_from = (f"FROM {hs_table} h "
                 f"{asset_join} "
                 f"LEFT JOIN stats s ON h.symbol = s.symbol "
                 f"WHERE {where_str}")
    # COUNT never needs the stats LEFT JOIN (profit_status is not filterable in date
    # mode, and a LEFT JOIN on the unique stats.symbol key cannot change the count).
    if "s." in where_str:
        count_from = base_from
    else:
        count_from = (f"FROM {hs_table} h "
                      f"{asset_join} "
                      f"WHERE {where_str}")

    direction = "DESC" if sort_dir == "desc" else "ASC"
    h_col_map = {"symbol": "h.symbol", "name": "a.name", "price": "h.price",
                 "change_pct": "h.change_pct", "weighted_alpha": "h.weighted_alpha",
                 "volume": "h.volume", "streak": "h.streak", "r_squared": "h.r_squared",
                 "ath": "h.ath", "atl": "h.atl",
                 "atr_signal": "h.atr_signal", "atr_stop": "h.atr_stop",
                 "atr_value": "h.atr_value", "atr_streak": "h.atr_streak",
                 "atrp": "h.atrp", "atr_crossed_above": "h.atr_crossed_above",
                 "atr_crossed_below": "h.atr_crossed_below",
                   "prob_up_1d": "h.prob_up_1d", "prob_up_5d": "h.prob_up_5d", "prob_up_st_cross": "h.prob_up_st_cross",
                  "prob_up_1w": "h.prob_up_1w", "prob_up_1m": "h.prob_up_1m",
                 "next_day_return": "h.next_day_return", "next_5d_return": "h.next_5d_return",
                 "confluence": "h.confluence",
                 "accel_a": "h.accel_a", "accel_base": "h.accel_base",
                 "accel_signal": "h.accel_signal", "accel_streak": "h.accel_streak",
                 "accel_crossed_up": "h.accel_crossed_up", "accel_crossed_down": "h.accel_crossed_down",
                 "ai_overall_score": "h.ai_overall_score", "ai_matrix": "h.ai_matrix",
                 "ai_bias": "h.ai_bias", "ai_conclusion": "h.ai_conclusion",
                 "exchange": "a.exchange", "asset_class": "a.asset_class",
                 "marginable": "a.marginable", "fractionable": "a.fractionable",
                 "shortable": "a.shortable",
                  "st_bars_below": "h.st_bars_below", "st_bars_above": "h.st_bars_above",
                  "accel_bars_below": "h.accel_bars_below", "accel_bars_above": "h.accel_bars_above",
                  "atr_signal_w": "h.atr_signal_w", "atr_stop_w": "h.atr_stop_w",
                   "atr_crossed_above_w": "h.atr_crossed_above_w", "atr_crossed_below_w": "h.atr_crossed_below_w",
                   "atr_streak_w": "h.atr_streak_w",
                   "atr_signal_m": "h.atr_signal_m", "atr_stop_m": "h.atr_stop_m",
                   "atr_crossed_above_m": "h.atr_crossed_above_m", "atr_crossed_below_m": "h.atr_crossed_below_m",
                   "atr_streak_m": "h.atr_streak_m"}
    sort_col = h_col_map.get(sort)
    if sort_col is None:
        sort_col = "h.weighted_alpha"
    # "<col> <dir> NULLS LAST" is row-identical to the old CASE-WHEN-NULL wrapper but
    # lets SQLite serve indexed sorts without a temp B-tree (verified on real DBs).
    order_clause = f"{sort_col} {direction} NULLS LAST"

    total = conn.execute(f"SELECT COUNT(*) {count_from}", params).fetchone()[0]
    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT h.symbol, h.price, h.volume, NULL as open, NULL as high, NULL as low, "
        f"h.change_pct, h.weighted_alpha, h.atrp, h.streak, h.r_squared, h.atr_value, h.atr_stop, h.atr_signal, "
        f"h.ath, h.atl, "
        f"h.atr_crossed_above, h.atr_crossed_below, h.atr_streak, h.atr_multiplier, "
        f"h.prob_up_1d, h.prob_up_5d, h.prob_up_st_cross, h.next_day_return, h.next_5d_return, h.confluence, "
        f"h.prob_up_1w, h.prob_up_1m, "
         f"h.accel_a, h.accel_base, h.accel_signal, h.accel_crossed_up, h.accel_crossed_down, "
         f"h.st_bars_below, h.st_bars_above, h.accel_bars_below, h.accel_bars_above, "
         f"h.atr_signal_w, h.atr_stop_w, h.atr_crossed_above_w, h.atr_crossed_below_w, h.atr_streak_w, "
         f"h.atr_signal_m, h.atr_stop_m, h.atr_crossed_above_m, h.atr_crossed_below_m, h.atr_streak_m, "
         f"s.profit_status, a.fractionable, a.marginable, {shortable_expr}, NULL as pre_price, NULL as pre_change_pct, "
        f"NULL as post_price, NULL as post_change_pct, h.date as last_updated, "
        f"h.ai_overall_score, h.ai_bias, h.ai_tech_score, h.ai_momentum_score, "
        f"h.ai_volume_score, h.ai_events_score, h.ai_volume_profile_score, "
        f"h.ai_trendline_score, h.ai_sentiment_score, h.ai_conclusion, h.ai_matrix, "
        f"a.name, a.exchange, a.asset_class "
        f"{base_from} ORDER BY {order_clause} LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    data = [dict(r) for r in rows]
    for d in data:
        d.setdefault("ai_overall_score", 0)
        d.setdefault("ai_bias", "neutral")
        d.setdefault("ai_tech_score", 0)
        d.setdefault("ai_volume_profile_score", 0)
        d.setdefault("ai_trendline_score", 0)
        d.setdefault("ai_sentiment_score", 0)
        d.setdefault("ai_conclusion", "HOLD")
        d.setdefault("ai_matrix", "")
        d.setdefault("name", "")
        d.setdefault("exchange", "")
        d.setdefault("asset_class", "")

    return {
        "data": data, "total": total, "page": page, "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page, "historical": True, "date": date_cutoff
    }


def _build_stats_query(conn, market, search, exchange, asset_type,
                        sort, sort_dir, page, per_page, args):

    where = ["1=1"]
    params = []

    if search:
        where.append("(s.symbol LIKE ? OR s.name LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if exchange:
        where.append("exchange = ?")
        params.append(exchange)
    if asset_type:
        where.append("asset_class = ?")
        params.append(asset_type)

    min_wa = args.get("min_wa")
    max_wa = args.get("max_wa")
    if min_wa:
        where.append("weighted_alpha >= ?")
        params.append(float(min_wa))
    if max_wa:
        where.append("weighted_alpha <= ?")
        params.append(float(max_wa))

    min_price = args.get("min_price")
    max_price = args.get("max_price")
    if min_price:
        where.append("price >= ?")
        params.append(float(min_price))
    if max_price:
        where.append("price <= ?")
        params.append(float(max_price))

    min_change = args.get("min_change")
    max_change = args.get("max_change")
    if min_change:
        where.append("change_pct >= ?")
        params.append(float(min_change))
    if max_change:
        where.append("change_pct <= ?")
        params.append(float(max_change))

    min_streak = args.get("min_streak")
    if min_streak:
        where.append("streak >= ?")
        params.append(int(min_streak))

    min_volume = args.get("min_volume")
    if min_volume:
        where.append("volume >= ?")
        params.append(int(min_volume))

    atr_status = args.get("atr_status")
    if atr_status:
        if atr_status == "above":
            where.append("atr_signal = 1")
        elif atr_status == "below":
            where.append("atr_signal = -1")
        elif atr_status == "crossed-above":
            where.append("atr_crossed_above = 1")
        elif atr_status == "crossed-below":
            where.append("atr_crossed_below = 1")

    atr_status_w = args.get("atr_status_w")
    if atr_status_w:
        if atr_status_w == "above":
            where.append("atr_signal_w = 1")
        elif atr_status_w == "below":
            where.append("atr_signal_w = -1")
        elif atr_status_w == "crossed-above":
            where.append("atr_crossed_above_w = 1")
        elif atr_status_w == "crossed-below":
            where.append("atr_crossed_below_w = 1")

    atr_status_m = args.get("atr_status_m")
    if atr_status_m:
        if atr_status_m == "above":
            where.append("atr_signal_m = 1")
        elif atr_status_m == "below":
            where.append("atr_signal_m = -1")
        elif atr_status_m == "crossed-above":
            where.append("atr_crossed_above_m = 1")
        elif atr_status_m == "crossed-below":
            where.append("atr_crossed_below_m = 1")

    accel_status = args.get("accel_status")
    if accel_status:
        if accel_status == "up":
            where.append("accel_signal = 1")
        elif accel_status == "down":
            where.append("accel_signal = -1")
        elif accel_status == "crossed-up":
            where.append("accel_crossed_up = 1")
        elif accel_status == "crossed-down":
            where.append("accel_crossed_down = 1")

    fractionable = args.get("fractionable")
    if fractionable:
        where.append("fractionable = ?")
        params.append(1 if fractionable == "yes" else 0)
    shortable = args.get("shortable")
    if shortable:
        where.append("s.shortable = ?")
        params.append(1 if shortable == "yes" else 0)

    profit_status = args.get("profit_status")
    if profit_status:
        where.append("profit_status = ?")
        params.append(profit_status)

    leveraged = args.get("leveraged")
    if leveraged == "yes":
        where.append(_leveraged_etf_sql(name_col="s.name", asset_col="s.asset_class"))

    nifty500 = args.get("nifty500")
    if nifty500 == "yes" and market == "INDIA":
        where.append("s.symbol IN (SELECT symbol FROM nifty500_constituents WHERE to_date = '9999-12-31')")

    index_filter = args.get("index")
    if index_filter:
        india_map = {"nifty500": "nifty500_constituents", "nifty50": "nifty50_constituents", "fo": "fo_constituents"}
        us_map = {"sp500": "sp500_constituents", "nasdaq100": "nasdaq100_constituents", "russell2000": "russell2000_constituents", "dow30": "dow30_constituents"}
        table_map = india_map if market == "INDIA" else us_map
        tbl = table_map.get(index_filter)
        if tbl:
            where.append(f"s.symbol IN (SELECT symbol FROM {tbl} WHERE to_date = '9999-12-31')")

    min_st_bars_below = args.get("min_st_bars_below")
    if min_st_bars_below:
        where.append("s.st_bars_below >= ?")
        params.append(int(min_st_bars_below))
    min_st_bars_above = args.get("min_st_bars_above")
    if min_st_bars_above:
        where.append("s.st_bars_above >= ?")
        params.append(int(min_st_bars_above))
    min_accel_bars_below = args.get("min_accel_bars_below")
    if min_accel_bars_below:
        where.append("s.accel_bars_below >= ?")
        params.append(int(min_accel_bars_below))
    min_accel_bars_above = args.get("min_accel_bars_above")
    if min_accel_bars_above:
        where.append("s.accel_bars_above >= ?")
        params.append(int(min_accel_bars_above))

    where_str = " AND ".join(where)

    # Filters only reference stats columns, so COUNT can skip the ai_analysis join
    # (LEFT JOIN on the unique ai_analysis.symbol key never changes the row count).
    if "a." in where_str:
        total = conn.execute(f"SELECT COUNT(*) FROM stats s LEFT JOIN ai_analysis a ON s.symbol=a.symbol WHERE {where_str}", params).fetchone()[0]
    else:
        total = conn.execute(f"SELECT COUNT(*) FROM stats s WHERE {where_str}", params).fetchone()[0]

    allowed_sorts = {
        "symbol", "name", "price", "change_pct", "weighted_alpha", "volume", "streak", "r_squared",
        "ath", "atl",
        "atr_signal", "atr_stop", "atr_value", "atr_streak", "atrp",
        "atr_crossed_above", "atr_crossed_below",
        "prob_up_1d", "prob_up_5d", "prob_up_st_cross", "prob_up_1w", "prob_up_1m",
        "next_day_return", "pre_price", "pre_change_pct", "post_price", "post_change_pct",
        "profit_status", "fractionable", "marginable", "shortable", "asset_class", "exchange", "confluence",
        "accel_a", "accel_base", "accel_signal", "accel_streak", "accel_crossed_up", "accel_crossed_down",
        "ai_overall_score", "ai_bias", "ai_tech_score", "ai_volume_profile_score",
        "ai_trendline_score", "ai_sentiment_score", "ai_conclusion", "ai_matrix",
        "st_bars_below", "st_bars_above", "accel_bars_below", "accel_bars_above",
        "atr_signal_w", "atr_stop_w", "atr_crossed_above_w", "atr_crossed_below_w", "atr_streak_w",
        "atr_signal_m", "atr_stop_m", "atr_crossed_above_m", "atr_crossed_below_m", "atr_streak_m"
    }
    if sort not in allowed_sorts:
        sort = "weighted_alpha"
    direction = "DESC" if sort_dir == "desc" else "ASC"

    ai_col_map = {
        "ai_overall_score": "a.overall_score",
        "ai_bias": "a.bias",
        "ai_tech_score": "a.tech_score",
        "ai_volume_profile_score": "a.volume_profile_score",
        "ai_trendline_score": "a.trendline_score",
        "ai_sentiment_score": "a.sentiment_score",
        "ai_conclusion": "a.conclusion",
        "ai_matrix": "a.ai_matrix",
    }
    # Alpaca shortability only exists for US; other markets get NULL so the UI
    # renders '-' instead of a misleading "No".
    shortable_expr = "s.shortable" if str(market).upper() == "US" else "NULL as shortable"
    sort_col = ai_col_map.get(sort) or f"s.{sort}"

    # "<col> <dir> NULLS LAST" is row-identical to the old CASE-WHEN-NULL wrapper but
    # lets SQLite use the stats indexes (idx_stats_wa etc.) instead of a temp B-tree.
    order_clause = f"{sort_col} {direction} NULLS LAST"

    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT s.symbol, s.name, s.price, s.volume, s.change_pct, "
        f"s.atrp, s.weighted_alpha, s.atr_signal, s.atr_stop, s.atr_value, s.atr_streak, "
        f"s.atr_crossed_above, s.atr_crossed_below, s.atr_multiplier, s.streak, s.r_squared, "
        f"s.ath, s.atl, "
        f"s.next_day_return, s.prob_up_1d, s.prob_up_5d, s.prob_up_st_cross, s.prob_up_1w, s.prob_up_1m, "
        f"s.pre_price, s.pre_change_pct, s.post_price, s.post_change_pct, "
        f"s.profit_status, s.fractionable, s.marginable, {shortable_expr}, s.asset_class, s.exchange, "
        f"s.last_updated, s.oldest_data, s.accel_a, s.accel_base, s.accel_signal, "
        f"s.accel_crossed_up, s.accel_crossed_down, s.accel_streak, s.confluence, "
         f"s.st_bars_below, s.st_bars_above, s.accel_bars_below, s.accel_bars_above, "
         f"s.atr_signal_w, s.atr_stop_w, s.atr_crossed_above_w, s.atr_crossed_below_w, s.atr_streak_w, "
         f"s.atr_signal_m, s.atr_stop_m, s.atr_crossed_above_m, s.atr_crossed_below_m, s.atr_streak_m, "
         f"a.overall_score as ai_overall_score, a.bias as ai_bias, "
        f"a.tech_score as ai_tech_score, a.momentum_score as ai_momentum_score, "
        f"a.volume_score as ai_volume_score, a.events_score as ai_events_score, "
        f"a.volume_profile_score as ai_volume_profile_score, "
        f"a.trendline_score as ai_trendline_score, a.sentiment_score as ai_sentiment_score, "
        f"a.conclusion as ai_conclusion, a.ai_matrix "
        f"FROM stats s LEFT JOIN ai_analysis a ON s.symbol=a.symbol "
        f"WHERE {where_str} ORDER BY {order_clause} LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    data = [dict(r) for r in rows]
    for d in data:
        d.setdefault("ai_overall_score", 0)
        d.setdefault("ai_bias", "neutral")
        d.setdefault("ai_tech_score", 0)
        d.setdefault("ai_volume_profile_score", 0)
        d.setdefault("ai_trendline_score", 0)
        d.setdefault("ai_sentiment_score", 0)
        d.setdefault("ai_conclusion", "HOLD")
        d.setdefault("ai_matrix", "")
    return {
        "data": data, "total": total, "page": page, "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page, "historical": False
    }


@api_bp.route("/stats")
def api_stats():
    market = request.args.get("market", "US")
    symbol = request.args.get("symbol")
    conn = get_db(market)
    try:
        if symbol:
            row = conn.execute("SELECT * FROM stats WHERE symbol=?", (symbol,)).fetchone()
            return jsonify(dict(row) if row else {})
        else:
            rows = conn.execute("SELECT * FROM stats LIMIT 500").fetchall()
            return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@api_bp.route("/market-breadth")
def api_market_breadth():
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        row = conn.execute("SELECT COUNT(*) as total FROM stats").fetchone()
        total = row["total"] if row else 0
        up = conn.execute("SELECT COUNT(*) as c FROM stats WHERE change_pct > 0").fetchone()["c"]
        down = conn.execute("SELECT COUNT(*) as c FROM stats WHERE change_pct < 0").fetchone()["c"]
        unchanged = total - up - down
        return jsonify({
            "total": total, "advancers": up, "decliners": down, "unchanged": unchanged,
            "pct_up": round(up / total * 100, 1) if total > 0 else 0
        })
    finally:
        conn.close()


@api_bp.route("/top-lists")
def api_top_lists():
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        gainers = [dict(r) for r in conn.execute(
            "SELECT symbol, name, price, change_pct FROM stats ORDER BY change_pct DESC LIMIT 10"
        ).fetchall()]
        by_volume = [dict(r) for r in conn.execute(
            "SELECT symbol, name, price, volume FROM stats ORDER BY volume DESC LIMIT 10"
        ).fetchall()]
        by_wa = [dict(r) for r in conn.execute(
            "SELECT symbol, name, price, weighted_alpha FROM stats ORDER BY weighted_alpha DESC LIMIT 10"
        ).fetchall()]
        return jsonify({"gainers": gainers, "by_volume": by_volume, "by_weighted_alpha": by_wa})
    finally:
        conn.close()


@api_bp.route("/exchanges")
def api_exchanges():
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        rows = conn.execute("SELECT DISTINCT exchange FROM stats WHERE exchange IS NOT NULL AND exchange != ''").fetchall()
        return jsonify([r["exchange"] for r in rows])
    finally:
        conn.close()


@api_bp.route("/hs-dates")
def api_hs_dates():
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        if market == "CRYPTO":
            # crypto.db keeps candles in crypto_bars (daily timeframe is '1d')
            rows = conn.execute(
                """
                WITH RECURSIVE d(dt) AS (
                  SELECT (SELECT MAX(date) FROM crypto_bars WHERE timeframe='1d')
                  UNION ALL
                  SELECT (SELECT MAX(date) FROM crypto_bars WHERE timeframe='1d' AND date < d.dt)
                  FROM d WHERE d.dt IS NOT NULL LIMIT 1461
                )
                SELECT dt AS date FROM d WHERE d.dt IS NOT NULL LIMIT 1460
                """
            ).fetchall()
        else:
            # Recursive "loose index scan": one indexed MAX() seek per distinct date via
            # idx_bars_tf_date instead of scanning the whole multi-million-row index
            # (measured 410ms -> 38ms on US, 3.6s -> 26ms on India).
            rows = conn.execute(
                """
                WITH RECURSIVE d(dt) AS (
                  SELECT (SELECT MAX(date) FROM bars WHERE timeframe='1Day')
                  UNION ALL
                  SELECT (SELECT MAX(date) FROM bars WHERE timeframe='1Day' AND date < d.dt)
                  FROM d WHERE d.dt IS NOT NULL LIMIT 366
                )
                SELECT dt AS date FROM d WHERE d.dt IS NOT NULL LIMIT 365
                """
            ).fetchall()
        return jsonify([r["date"] for r in rows])
    finally:
        conn.close()


@api_bp.route("/assets")
def api_assets():
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        rows = conn.execute("SELECT * FROM assets ORDER BY symbol").fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@api_bp.route("/stock/<symbol>")
def api_stock(symbol):
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        stats = conn.execute("SELECT * FROM stats WHERE symbol=?", (symbol,)).fetchone()
        analysis = conn.execute("SELECT * FROM ai_analysis WHERE symbol=?", (symbol,)).fetchone()
        events = conn.execute(
            "SELECT * FROM corporate_events WHERE symbol=? ORDER BY event_date DESC LIMIT 20", (symbol,)
        ).fetchall()
        return jsonify({
            "stats": dict(stats) if stats else {},
            "analysis": dict(analysis) if analysis else {},
            "events": [dict(e) for e in events]
        })
    finally:
        conn.close()


@api_bp.route("/stock/<symbol>/retest-score")
def api_stock_retest_score(symbol):
    """Retest score removed. Returns null."""
    return jsonify({"symbol": symbol, "old_swing_retest_score": None, "cached": False})


@api_bp.route("/retest/model-status")
def api_retest_model_status():
    """Retest model removed."""
    return jsonify({"status": "removed"})


@api_bp.route("/retest/backtest")
def api_retest_backtest():
    """Retest removed."""
    return jsonify({"error": "Retest removed"}), 404


@api_bp.route("/retest/populate-historical", methods=["POST"])
def api_retest_populate_historical():
    """Retest removed."""
    return jsonify({"status": "removed"})


@api_bp.route("/stock/<symbol>/bars")
def api_stock_bars(symbol):
    market = request.args.get("market", "US")
    timeframe = request.args.get("timeframe", "1Day")
    try:
        limit = int(request.args.get("limit", 200))
    except (ValueError, TypeError):
        limit = 200
    conn = get_db(market)
    try:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM bars WHERE symbol=? AND timeframe=? ORDER BY date DESC LIMIT ?",
            (symbol, timeframe, limit)
        ).fetchall()
        data = [dict(r) for r in reversed(rows)]
        return jsonify(data)
    finally:
        conn.close()


@api_bp.route("/stock/<symbol>/ohlc")
def api_stock_ohlc(symbol):
    market = request.args.get("market", "US")
    timeframe = request.args.get("timeframe", "1Day")
    try:
        limit = int(request.args.get("limit", 200))
    except (ValueError, TypeError):
        limit = 200
    conn = get_db(market)
    try:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date DESC LIMIT ?",
            (symbol, limit + 200)
        ).fetchall()
        data = [dict(r) for r in reversed(rows)]
        if timeframe != "1Day" and data:
            import pandas as pd
            df = pd.DataFrame(data)
            tf_map = {"1Week": "1W", "1Month": "1M", "1W": "1W", "1M": "1M"}
            rule = tf_map.get(timeframe, timeframe)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
            agg = df.resample(rule).agg({
                "open": "first", "high": "max", "low": "min",
                "close": "last", "volume": "sum"
            }).dropna(subset=["open"])
            agg["date"] = agg.index.strftime("%Y-%m-%d")
            data = agg.reset_index(drop=True)[["date", "open", "high", "low", "close", "volume"]].to_dict("records")
        data = data[-limit:]
        return jsonify(data)
    finally:
        conn.close()


@api_bp.route("/stock/<symbol>/supertrend")
def api_stock_supertrend(symbol):
    market = request.args.get("market", "US")
    timeframe = request.args.get("timeframe", "1Day")
    try:
        period = int(request.args.get("period", 14))
        multiplier = float(request.args.get("multiplier", 2.0))
    except (ValueError, TypeError):
        period, multiplier = 14, 2.0
    conn = get_db(market)
    try:
        rows = conn.execute(
            "SELECT date, open, high, low, close FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date",
            (symbol,)
        ).fetchall()
        if not rows:
            return jsonify({"daily": [], "weekly": [], "monthly": []})
        import pandas as pd
        from dumbmoney.indicators import atr_trailing_stop as compute_st
        from dumbmoney.indicators import compute_rolling_atr_batch
        df = pd.DataFrame([dict(r) for r in rows])

        daily_dates = df["date"].tolist()

        # Daily ATR Trailing Stop
        st_daily = compute_st(df, period=period, multiplier=multiplier)
        daily_result = []
        for i, (_, row) in enumerate(st_daily.iterrows()):
            daily_result.append({
                "date": df.iloc[i]["date"] if i < len(df) else "",
                "supertrend": round(float(row["supertrend"]), 4) if pd.notna(row["supertrend"]) else None,
                "trend": int(row["trend"]),
                "signal": int(row["signal"]),
                "stop": round(float(row["stop"]), 4) if pd.notna(row["stop"]) else None,
                "atr_value": round(float(row["atr_value"]), 4) if pd.notna(row["atr_value"]) else None,
            })

        # Anchored rolling weekly (5 sessions) - batch computation
        weekly_result = []
        if len(df) >= 7:
            try:
                dates_arr = df["date"].values
                opens_arr = df["open"].astype(float).values
                highs_arr = df["high"].astype(float).values
                lows_arr = df["low"].astype(float).values
                closes_arr = df["close"].astype(float).values
                wt, ws, wv, wsk, wca, wcb, wbl, wab = compute_rolling_atr_batch(
                    dates_arr, opens_arr, highs_arr, lows_arr, closes_arr, 5, period, multiplier
                )
                for i in range(len(dates_arr)):
                    if wt[i] != 0 or ws[i] != 0:
                        weekly_result.append({
                            "date": dates_arr[i],
                            "supertrend": round(float(ws[i]), 4) if ws[i] else None,
                            "trend": int(wt[i]),
                            "signal": int(wt[i]),
                            "stop": round(float(ws[i]), 4) if ws[i] else None,
                            "atr_value": round(float(wv[i]), 4) if wv[i] else None,
                        })
            except Exception:
                pass

        # Anchored rolling monthly (22 sessions) - batch computation
        monthly_result = []
        if len(df) >= 24:
            try:
                dates_arr = df["date"].values
                opens_arr = df["open"].astype(float).values
                highs_arr = df["high"].astype(float).values
                lows_arr = df["low"].astype(float).values
                closes_arr = df["close"].astype(float).values
                mt, ms, mv, msk, mca, mcb, mbl, mab = compute_rolling_atr_batch(
                    dates_arr, opens_arr, highs_arr, lows_arr, closes_arr, 22, period, multiplier
                )
                for i in range(len(dates_arr)):
                    if mt[i] != 0 or ms[i] != 0:
                        monthly_result.append({
                            "date": dates_arr[i],
                            "supertrend": round(float(ms[i]), 4) if ms[i] else None,
                            "trend": int(mt[i]),
                            "signal": int(mt[i]),
                            "stop": round(float(ms[i]), 4) if ms[i] else None,
                            "atr_value": round(float(mv[i]), 4) if mv[i] else None,
                        })
            except Exception:
                pass

        return jsonify({"daily": daily_result, "weekly": weekly_result, "monthly": monthly_result})
    finally:
        conn.close()


@api_bp.route("/stock/<symbol>/accel")
def api_stock_accel(symbol):
    market = request.args.get("market", "US")
    timeframe = request.args.get("timeframe", "1Day")
    conn = get_db(market)
    try:
        rows = conn.execute(
            "SELECT date, open, high, low, close FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date",
            (symbol,)
        ).fetchall()
        if not rows:
            return jsonify([])
        import pandas as pd
        from dumbmoney.indicators import accel as compute_accel
        df = pd.DataFrame([dict(r) for r in rows])
        if timeframe != "1Day":
            tf_map = {"1Week": "1W", "1Month": "1M", "1W": "1W", "1M": "1M"}
            rule = tf_map.get(timeframe, timeframe)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
            df = df.resample(rule).agg({
                "open": "first", "high": "max", "low": "min", "close": "last"
            }).dropna(subset=["open"])
            df["date"] = df.index.strftime("%Y-%m-%d")
            df = df.reset_index(drop=True)
        acc = compute_accel(df)
        result = []
        for i, (_, row) in enumerate(acc.iterrows()):
            result.append({
                "date": df.iloc[i]["date"] if i < len(df) else "",
                "accel_a": round(float(row["accel_a"]), 6) if pd.notna(row["accel_a"]) else None,
                "accel_base": round(float(row["accel_base"]), 6) if pd.notna(row["accel_base"]) else None,
                "signal": int(row["accel_signal"]),
                "crossed_up": int(row["accel_crossed_up"]),
                "crossed_down": int(row["accel_crossed_down"]),
            })
        return jsonify(result)
    finally:
        conn.close()


@api_bp.route("/stock/<symbol>/wa_history")
def api_stock_wa_history(symbol):
    market = request.args.get("market", "US")
    timeframe = request.args.get("timeframe", "1Day")
    try:
        limit = int(request.args.get("limit", 200))
    except (ValueError, TypeError):
        limit = 200
    conn = get_db(market)
    try:
        rows = conn.execute(
            "SELECT date, open, high, low, close FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date",
            (symbol,)
        ).fetchall()
        if not rows:
            return jsonify([])
        import pandas as pd
        from dumbmoney.indicators import weighted_alpha as compute_wa
        df = pd.DataFrame([dict(r) for r in rows])
        if timeframe != "1Day":
            tf_map = {"1Week": "1W", "1Month": "1M", "1W": "1W", "1M": "1M"}
            rule = tf_map.get(timeframe, timeframe)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
            df = df.resample(rule).agg({
                "open": "first", "high": "max", "low": "min", "close": "last"
            }).dropna(subset=["open"])
            df["date"] = df.index.strftime("%Y-%m-%d")
            df = df.reset_index(drop=True)
        wa = compute_wa(df)
        result = []
        for i, (_, row) in enumerate(wa.items()):
            val = float(row) if pd.notna(row) else 0.0
            result.append({
                "date": df.iloc[i]["date"] if i < len(df) else "",
                "weighted_alpha": round(val, 4),
            })
        result = result[-limit:]
        return jsonify(result)
    finally:
        conn.close()


def _combined_ohlc_for_symbols(conn, symbols, weights=None):
    if not symbols:
        return None
    import pandas as pd
    from dumbmoney.indicators import combined_ohlc
    all_data = {}
    for sym in symbols:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date",
            (sym,)
        ).fetchall()
        if rows:
            all_data[sym] = pd.DataFrame([dict(r) for r in rows])
    if not all_data:
        return None
    combined = combined_ohlc(all_data, weights=weights)
    return combined if combined is not None and not combined.empty else None


def _resample_ohlc(ohlc_df, timeframe):
    import pandas as pd
    if timeframe in ("1D", "daily", None):
        return ohlc_df
    df = ohlc_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    rule = {"1W": "W", "1M": "ME"}.get(timeframe, "W")
    agg = df.resample(rule).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum"
    }).dropna(subset=["open"])
    agg["date"] = agg.index.strftime("%Y-%m-%d")
    return agg.reset_index(drop=True)[["date", "open", "high", "low", "close", "volume"]]


def _accel_payload(df):
    if df is None or df.empty:
        return []
    import pandas as pd
    from dumbmoney.indicators import accel as compute_accel
    acc = compute_accel(df)
    result = []
    for i, (_, row) in enumerate(acc.iterrows()):
        result.append({
            "date": df.iloc[i]["date"] if i < len(df) else "",
            "accel_a": round(float(row["accel_a"]), 6) if pd.notna(row["accel_a"]) else None,
            "accel_base": round(float(row["accel_base"]), 6) if pd.notna(row["accel_base"]) else None,
            "signal": int(row["accel_signal"]),
            "crossed_up": int(row["accel_crossed_up"]),
            "crossed_down": int(row["accel_crossed_down"]),
        })
    return result


@api_bp.route("/stock/<symbol>/analysis")
def api_stock_analysis(symbol):
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        row = conn.execute("SELECT * FROM ai_analysis WHERE symbol=?", (symbol,)).fetchone()
        return jsonify(dict(row) if row else {})
    finally:
        conn.close()


@api_bp.route("/alpaca-news/<symbol>")
def api_alpaca_news(symbol):
    from dumbmoney.data_us import get_alpaca_news
    news = get_alpaca_news(symbol)
    return jsonify(news)


@api_bp.route("/news-search")
def api_news_search():
    query = request.args.get("q", "")
    from dumbmoney.data_us import get_news_search
    news = get_news_search(query)
    return jsonify(news)


@api_bp.route("/options/<symbol>")
def api_options(symbol):
    from dumbmoney.data_us import get_options_chain
    chain = get_options_chain(symbol)
    return jsonify(chain)


@api_bp.route("/live/prices")
def api_live_prices():
    symbols_str = request.args.get("symbols", "")
    if not symbols_str:
        return jsonify({})
    symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
    market = request.args.get("market", "US")
    if market == "US":
        from dumbmoney.data_us import get_live_prices
        return jsonify(get_live_prices(symbols))
    else:
        from dumbmoney.data_india import get_live_prices_india
        return jsonify(get_live_prices_india(symbols))


@api_bp.route("/refresh", methods=["POST"])
def api_refresh():
    data = request.json if request.is_json else {}
    market = (data or {}).get("market", "US") or request.args.get("market", "US")
    from dumbmoney.refresh import run_refresh
    success = run_refresh(market)
    return jsonify({"started": success})


@api_bp.route("/refresh/cancel", methods=["POST"])
def api_refresh_cancel():
    data = request.json if request.is_json else {}
    market = (data or {}).get("market", "US") or request.args.get("market", "US")
    from dumbmoney.refresh import cancel_refresh
    cancel_refresh(market)
    return jsonify({"cancelled": True})


@api_bp.route("/refresh/status")
def api_refresh_status():
    market = request.args.get("market", "US")
    from dumbmoney.refresh import get_refresh_status
    return jsonify(get_refresh_status(market))


_MARKET_STATS_CACHE = {}
_MARKET_STATS_TTL = 60  # seconds; heavy distinct-symbol counts only


@api_bp.route("/market-stats")
def api_market_stats():
    market = request.args.get("market", "US")
    from dumbmoney.db import get_db
    import json
    import time as _time
    from datetime import datetime, timedelta
    IST = timedelta(hours=5, minutes=30)
    if market == "CRYPTO":
        conn = get_db("CRYPTO")
        try:
            total_assets = conn.execute("SELECT COUNT(*) FROM crypto_products WHERE state='live'").fetchone()[0]
            oldest = conn.execute("SELECT MIN(date) FROM crypto_bars WHERE timeframe='1d'").fetchone()[0] or ""
            latest = conn.execute("SELECT MAX(date) FROM crypto_bars WHERE timeframe='1d'").fetchone()[0] or ""
            with_stats = conn.execute("SELECT COUNT(*) FROM crypto_stats WHERE price > 0").fetchone()[0]
            with_bars = conn.execute("SELECT COUNT(DISTINCT symbol) FROM crypto_bars WHERE timeframe='1d'").fetchone()[0]
            new_today = conn.execute("SELECT COUNT(DISTINCT symbol) FROM crypto_bars WHERE timeframe='1d' AND date=?", (latest,)).fetchone()[0] if latest else 0
            last_refresh = {}
            row = conn.execute("SELECT value FROM crypto_settings WHERE key='refresh_status'").fetchone()
            if row and row[0]:
                s = json.loads(row[0])
                ts = s.get("started_at", 0)
                finished = ""
                if ts:
                    finished = datetime.utcfromtimestamp(ts + 0).strftime("%Y-%m-%d %I:%M %p UTC")
                last_refresh = {"status": s.get("status", "idle"), "finished_at": finished,
                                "new_stocks": 0, "phase": s.get("phase", "")}
            return jsonify({
                "market": "CRYPTO", "total_assets": total_assets, "with_bars": with_bars,
                "with_stats": with_stats, "oldest_date": oldest, "latest_date": latest,
                "new_today": new_today, "last_refresh": last_refresh,
            })
        finally:
            conn.close()
    conn = get_db(market)
    try:
        total_assets = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        oldest = conn.execute("SELECT MIN(date) FROM bars WHERE timeframe='1Day'").fetchone()[0] or ""
        latest = conn.execute("SELECT MAX(date) FROM bars WHERE timeframe='1Day'").fetchone()[0] or ""
        with_stats = conn.execute("SELECT COUNT(*) FROM stats WHERE price > 0").fetchone()[0]

        # Distinct-symbol counts over the multi-million-row bars table are the only
        # expensive parts of this endpoint (COUNT(DISTINCT) scanned the whole index:
        # 5.2s US / 18s India). Use a recursive loose index scan over
        # idx_bars_tf_symbol plus a short TTL cache, since base.html hits this on
        # every page load.
        cached = _MARKET_STATS_CACHE.get(market)
        if cached and _time.time() - cached[0] < _MARKET_STATS_TTL and cached[1] == latest:
            with_bars, new_today = cached[2], cached[3]
        else:
            with_bars = conn.execute(
                """
                WITH RECURSIVE s(sym) AS (
                  SELECT (SELECT MIN(symbol) FROM bars WHERE timeframe='1Day')
                  UNION ALL
                  SELECT (SELECT MIN(symbol) FROM bars WHERE timeframe='1Day' AND symbol > s.sym)
                  FROM s WHERE s.sym IS NOT NULL
                )
                SELECT COUNT(*) FROM s WHERE sym IS NOT NULL
                """
            ).fetchone()[0]
            new_today = conn.execute(
                "SELECT COUNT(DISTINCT symbol) FROM bars WHERE timeframe='1Day' AND date = ?",
                (latest,)
            ).fetchone()[0] if latest else 0
            _MARKET_STATS_CACHE[market] = (_time.time(), latest, with_bars, new_today)

        last_refresh = {}
        row = conn.execute("SELECT value FROM settings WHERE key='refresh_status'").fetchone()
        if row and row[0]:
            s = json.loads(row[0])
            ts = s.get("started_at", 0)
            finished = ""
            if ts:
                finished = (datetime.utcfromtimestamp(ts) + IST).strftime("%Y-%m-%d %I:%M %p IST")
            last_refresh = {
                "status": s.get("status", "idle"),
                "finished_at": finished,
                "new_stocks": s.get("new_stocks_count", 0),
                "phase": s.get("phase", ""),
            }

        return jsonify({
            "market": market,
            "total_assets": total_assets,
            "with_bars": with_bars,
            "with_stats": with_stats,
            "oldest_date": oldest,
            "latest_date": latest,
            "new_today": new_today,
            "last_refresh": last_refresh,
        })
    finally:
        conn.close()


@api_bp.route("/settings/get")
def api_settings_get():
    market = request.args.get("market", "US")
    from dumbmoney.db import get_db
    import json
    conn = get_db(market)
    try:
        settings = {}
        for row in conn.execute("SELECT key, value FROM settings").fetchall():
            try:
                settings[row[0]] = json.loads(row[1])
            except Exception:
                settings[row[0]] = row[1]
        return jsonify(settings)
    finally:
        conn.close()


@api_bp.route("/settings/set", methods=["POST"])
def api_settings_set():
    data = request.json or {}
    market = data.get("market", "US")
    key = data.get("key", "")
    value = data.get("value", "")
    from dumbmoney.db import get_db
    import json
    conn = get_db(market)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, json.dumps(value))
        )
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@api_bp.route("/download-history", methods=["POST"])
def api_download_history():
    data = request.json if request.is_json else {}
    market = (data or {}).get("market", "US")
    from dumbmoney.refresh import run_refresh
    run_refresh(market)
    return jsonify({"started": True})


@api_bp.route("/download-status")
def api_download_status():
    market = request.args.get("market", "US")
    from dumbmoney.refresh import get_refresh_status
    return jsonify(get_refresh_status(market))


@api_bp.route("/download-assets", methods=["POST"])
def api_download_assets():
    data = request.json if request.is_json else {}
    market = (data or {}).get("market", "US")
    if market == "US":
        from dumbmoney.data_us import sync_assets
        n = sync_assets()
    else:
        from dumbmoney.data_india import sync_india_assets
        n = sync_india_assets()
    return jsonify({"synced": n})


@api_bp.route("/update-pre-post", methods=["POST"])
def api_update_pre_post():
    return jsonify({"status": "ok"})


@api_bp.route("/recompute-streaks", methods=["POST"])
def api_recompute_streaks():
    data = request.json if request.is_json else {}
    market = (data or {}).get("market", "US")
    from dumbmoney.engine import vectorized_stats_pass
    n = vectorized_stats_pass(market)
    return jsonify({"updated": n})


_historical_rebuild_threads = {}

@api_bp.route("/historical/rebuild", methods=["POST"])
def api_historical_rebuild():
    """Full rebuild of historical_screener + signal_prob_matrix.

    Runs in a background thread (it can take a long time on the big DBs);
    poll /api/historical/rebuild/status?market=X for progress. Only one
    rebuild per market at a time.
    """
    data = request.json if request.is_json else {}
    market = (data or {}).get("market", "US") or request.args.get("market", "US")
    force = bool((data or {}).get("force", True))
    market = "INDIA" if str(market).upper() == "INDIA" else "US"

    t = _historical_rebuild_threads.get(market)
    if t is not None and t.is_alive():
        return jsonify({"started": False, "error": "Rebuild already running", "market": market}), 409

    from dumbmoney.db import get_db
    conn = get_db(market)
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('historical_rebuild_status', ?)",
        ('{"status":"running","market":"' + market + '","progress":0,"message":"Starting full rebuild..."}',)
    )
    conn.commit()
    conn.close()

    def _worker():
        import json as _json
        from dumbmoney.engine import update_historical_screener, update_signal_prob_matrix
        def _prog(pct, msg):
            try:
                c = get_db(market)
                c.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('historical_rebuild_status', ?)",
                    (_json.dumps({"status": "running", "market": market, "progress": pct, "message": str(msg)}),)
                )
                c.commit()
                c.close()
            except Exception:
                pass
        try:
            update_historical_screener(market, progress_callback=_prog, force_rebuild=force)
            _prog(97, "Computing signal probability matrix...")
            update_signal_prob_matrix(market, progress_callback=_prog)
            c = get_db(market)
            c.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('historical_rebuild_status', ?)",
                ('{"status":"complete","market":"' + market + '","progress":100,"message":"Done"}',)
            )
            c.commit()
            c.close()
        except Exception as e:
            try:
                c = get_db(market)
                c.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('historical_rebuild_status', ?)",
                    ('{"status":"error","market":"' + market + '","progress":0,"message":"' + str(e).replace('"', "'") + '"}',)
                )
                c.commit()
                c.close()
            except Exception:
                pass

    thread = threading.Thread(target=_worker, daemon=True)
    _historical_rebuild_threads[market] = thread
    thread.start()
    return jsonify({"started": True, "market": market})


@api_bp.route("/historical/rebuild/status")
def api_historical_rebuild_status():
    import json as _json
    market = request.args.get("market", "US")
    market = "INDIA" if str(market).upper() == "INDIA" else "US"
    t = _historical_rebuild_threads.get(market)
    running = t is not None and t.is_alive()
    from dumbmoney.db import get_db
    conn = get_db(market)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key='historical_rebuild_status'").fetchone()
        status = _json.loads(row[0]) if row and row[0] else {"status": "idle", "market": market, "progress": 0, "message": ""}
    finally:
        conn.close()
    status["thread_alive"] = running
    return jsonify(status)


@api_bp.route("/health")
def api_health():
    return jsonify({"status": "ok"})


@api_bp.route("/settings/alpaca", methods=["GET", "POST"])
def api_settings_alpaca():
    if request.method == "POST":
        data = request.json
        from dumbmoney import config
        if "api_key" in data:
            config.ALPACA_API_KEY = data["api_key"]
        if "api_secret" in data:
            config.ALPACA_API_SECRET = data["api_secret"]
        if "base_url" in data:
            config.ALPACA_BASE_URL = data["base_url"]
        return jsonify({"updated": True})
    return jsonify({
        "api_key": "***" + (config.ALPACA_API_KEY[-4:] if len(config.ALPACA_API_KEY) > 4 else ""),
        "base_url": config.ALPACA_BASE_URL
    })


@api_bp.route("/portfolios")
def api_portfolios():
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        rows = conn.execute("SELECT * FROM portfolios ORDER BY created_at DESC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            strings = conn.execute(
                "SELECT * FROM portfolio_strings WHERE portfolio_id=? ORDER BY created_at", (r["id"],)
            ).fetchall()
            str_list = []
            total_pnl = 0
            for s in strings:
                sd = dict(s)
                ep = sd.get("entry_price") or 0
                syms = conn.execute(
                    "SELECT symbol, qty FROM portfolio_string_symbols WHERE portfolio_string_id=?", (sd["id"],)
                ).fetchall()
                # True entry cost: sum(qty x close on/before entry date); fall back
                # to the stored scalar when bars are missing.
                entry_value = 0.0
                entry_resolved = False
                for sy in syms:
                    if sd.get("entry_date"):
                        ebar = conn.execute(
                            "SELECT close FROM bars WHERE symbol=? AND date<=? ORDER BY date DESC LIMIT 1",
                            (sy["symbol"], sd["entry_date"])
                        ).fetchone()
                        if ebar and ebar["close"]:
                            entry_value += float(ebar["close"]) * (sy["qty"] or 0)
                            entry_resolved = True
                if not entry_resolved or entry_value <= 0:
                    entry_value = ep
                sd["entry_value_stored"] = ep
                current_value = 0
                prob_num = 0
                prob_den = 0
                chg_num = 0
                for sy in syms:
                    price_row = conn.execute(
                        "SELECT close FROM bars WHERE symbol=? ORDER BY date DESC LIMIT 1", (sy["symbol"],)
                    ).fetchone()
                    price = price_row["close"] if price_row else 0
                    qty = sy["qty"] or 0
                    current_value += price * qty
                    prob_row = conn.execute(
                        "SELECT prob_up_1d, change_pct FROM stats WHERE symbol=?", (sy["symbol"],)
                    ).fetchone()
                    prob = float(prob_row["prob_up_1d"] or 0) if prob_row else 0
                    chg = float(prob_row["change_pct"] or 0) if prob_row else 0
                    prob_num += prob * price * qty
                    prob_den += price * qty
                    chg_num += chg * price * qty
                rp_raw = sd.get("realised_pnl")
                rp = float(rp_raw) if rp_raw is not None and str(rp_raw) not in ('None', 'null', '') else 0.0
                up = current_value - entry_value if entry_value else 0
                sd["entry_value"] = entry_value
                sd["current_value"] = current_value
                sd["realised_pnl"] = rp
                sd["unrealised_pnl"] = up
                sd["pnl_pct"] = ((current_value / entry_value - 1) * 100) if entry_value else 0
                sd["num_stocks"] = len(syms)
                sd["prob_1up"] = round(prob_num / prob_den, 4) if prob_den > 0 else 0
                sd["change_pct"] = round(chg_num / prob_den, 4) if prob_den > 0 else 0
                total_pnl += rp + up
                str_list.append(sd)
            d["strings"] = str_list
            d["total_pnl"] = total_pnl
            d["num_strings"] = len(str_list)
            d["symbol_count"] = sum(s.get("num_stocks", 0) for s in str_list)
            result.append(d)
        return jsonify(result)
    finally:
        conn.close()


@api_bp.route("/portfolios/stats")
def api_portfolios_stats():
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        rows = conn.execute("SELECT * FROM portfolios ORDER BY created_at DESC").fetchall()
        total_invested = 0
        total_current = 0
        total_realised = 0
        total_unrealised = 0
        num_strings = 0
        prob_weight_sum = 0
        value_sum = 0
        for r in rows:
            strings = conn.execute(
                "SELECT * FROM portfolio_strings WHERE portfolio_id=?", (r["id"],)
            ).fetchall()
            for s in strings:
                sd = dict(s)
                num_strings += 1
                ep = sd.get("entry_price") or 0
                syms = conn.execute(
                    "SELECT symbol, qty FROM portfolio_string_symbols WHERE portfolio_string_id=?", (sd["id"],)
                ).fetchall()
                entry_value = ep
                total_invested += entry_value
                current_value = 0
                prob_sum = 0
                weight_sum = 0
                for sy in syms:
                    price_row = conn.execute(
                        "SELECT close FROM bars WHERE symbol=? ORDER BY date DESC LIMIT 1", (sy["symbol"],)
                    ).fetchone()
                    price = price_row["close"] if price_row else 0
                    qty = sy["qty"] or 0
                    current_value += price * qty
                    prob_row = conn.execute(
                        "SELECT prob_up_1d FROM stats WHERE symbol=?", (sy["symbol"],)
                    ).fetchone()
                    prob = float(prob_row["prob_up_1d"] or 0) if prob_row else 0
                    prob_sum += prob * price * qty
                    weight_sum += price * qty
                total_current += current_value
                rp_raw = sd.get("realised_pnl")
                rp = float(rp_raw) if rp_raw is not None and str(rp_raw) not in ('None', 'null', '') else 0.0
                up = current_value - entry_value if entry_value else 0
                total_realised += rp
                total_unrealised += up
                if weight_sum > 0:
                    prob_weight_sum += prob_sum
                    value_sum += weight_sum
        return jsonify({
            "total_invested": total_invested,
            "total_current": total_current,
            "total_pnl": total_realised + total_unrealised,
            "total_realised": total_realised,
            "total_unrealised": total_unrealised,
            "num_strings": num_strings,
            "prob_1up": round(prob_weight_sum / value_sum, 4) if value_sum > 0 else 0,
        })
    finally:
        conn.close()


@api_bp.route("/portfolios/ohlc")
def api_portfolios_ohlc():
    market = request.args.get("market", "US")
    limit = int(request.args.get("limit", 365))
    timeframe = request.args.get("timeframe", "1D")
    conn = get_db(market)
    try:
        rows = conn.execute("SELECT id FROM portfolios ORDER BY created_at DESC").fetchall()
        if not rows:
            return jsonify([])
        all_syms = {}
        for r in rows:
            strings = conn.execute("SELECT id FROM portfolio_strings WHERE portfolio_id=?", (r["id"],)).fetchall()
            for s in strings:
                syms = conn.execute(
                    "SELECT symbol, qty FROM portfolio_string_symbols WHERE portfolio_string_id=?", (s["id"],)
                ).fetchall()
                for sy in syms:
                    sym = sy["symbol"]
                    qty = sy["qty"] or 0
                    if sym in all_syms:
                        all_syms[sym] += qty
                    else:
                        all_syms[sym] = qty
        if not all_syms:
            return jsonify([])

        from datetime import date, timedelta
        days = limit * 7 if timeframe == "1W" else limit * 31 if timeframe == "1M" else limit + 10
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        placeholders = ",".join("?" * len(all_syms))
        sym_list = list(all_syms.keys())
        bars = conn.execute(
            f"SELECT symbol, date, open, high, low, close, volume FROM bars WHERE symbol IN ({placeholders}) AND date >= ? ORDER BY date",
            sym_list + [cutoff]
        ).fetchall()

        date_map = {}
        for b in bars:
            d = b["date"]
            qty = all_syms.get(b["symbol"], 0)
            if d not in date_map:
                date_map[d] = {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}
            date_map[d]["open"] += (b["open"] or 0) * qty
            date_map[d]["high"] += (b["high"] or 0) * qty
            date_map[d]["low"] += (b["low"] or 0) * qty
            date_map[d]["close"] += (b["close"] or 0) * qty
            date_map[d]["volume"] += (b["volume"] or 0)

        result = [{"time": d, "open": round(v["open"], 2), "high": round(v["high"], 2),
                    "low": round(v["low"], 2), "close": round(v["close"], 2), "volume": v["volume"]}
                   for d, v in sorted(date_map.items())]

        if timeframe not in ("1D", "daily", None) and result:
            import pandas as pd
            df = pd.DataFrame(result)
            df["time"] = pd.to_datetime(df["time"])
            df = df.set_index("time")
            rule = {"1W": "W", "1M": "ME"}.get(timeframe, "W")
            agg = df.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])
            agg["time"] = agg.index.strftime("%Y-%m-%d")
            result = [{"time": row["time"], "open": round(row["open"], 2), "high": round(row["high"], 2),
                        "low": round(row["low"], 2), "close": round(row["close"], 2), "volume": int(row["volume"])}
                       for _, row in agg.iterrows()]

        return jsonify(result[-limit:])
    finally:
        conn.close()


@api_bp.route("/portfolios/supertrend")
def api_portfolios_supertrend():
    market = request.args.get("market", "US")
    period = int(request.args.get("period", 14))
    multiplier = float(request.args.get("multiplier", 2.0))
    limit = int(request.args.get("limit", 500))

    ohlc = _portfolios_ohlc_all(market, limit=500, timeframe="1D")
    if not ohlc:
        return jsonify({"daily": [], "weekly": [], "monthly": []})

    import pandas as pd
    from dumbmoney.indicators import atr_trailing_stop
    from dumbmoney.indicators import compute_rolling_atr_batch

    df = pd.DataFrame(ohlc)
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c])

    st = atr_trailing_stop(df, period=period, multiplier=multiplier)
    st["time"] = df["time"].values
    daily_result = []
    for _, row in st.iterrows():
        daily_result.append({
            "time": row["time"],
            "value": round(float(row["supertrend"]), 2) if pd.notna(row["supertrend"]) else None,
            "signal": int(row["signal"]),
            "atr_value": round(float(row["atr_value"]), 4) if pd.notna(row.get("atr_value")) else None,
        })

    weekly_result = []
    if len(df) >= 7:
        try:
            dates_arr = df["time"].values
            opens_arr = df["open"].astype(float).values
            highs_arr = df["high"].astype(float).values
            lows_arr = df["low"].astype(float).values
            closes_arr = df["close"].astype(float).values
            wt, ws, wv, wsk, wca, wcb, wbl, wab = compute_rolling_atr_batch(
                dates_arr, opens_arr, highs_arr, lows_arr, closes_arr, 5, period, multiplier
            )
            for i in range(len(dates_arr)):
                if wt[i] != 0 or ws[i] != 0:
                    key = str(dates_arr[i])[:10]
                    weekly_result.append({"time": key, "value": round(float(ws[i]), 2) if ws[i] else None, "signal": int(wt[i]), "atr_value": round(float(wv[i]), 4) if wv[i] else None})
        except Exception:
            pass

    monthly_result = []
    if len(df) >= 24:
        try:
            dates_arr = df["time"].values
            opens_arr = df["open"].astype(float).values
            highs_arr = df["high"].astype(float).values
            lows_arr = df["low"].astype(float).values
            closes_arr = df["close"].astype(float).values
            mt, ms, mv, msk, mca, mcb, mbl, mab = compute_rolling_atr_batch(
                dates_arr, opens_arr, highs_arr, lows_arr, closes_arr, 22, period, multiplier
            )
            for i in range(len(dates_arr)):
                if mt[i] != 0 or ms[i] != 0:
                    key = str(dates_arr[i])[:10]
                    monthly_result.append({"time": key, "value": round(float(ms[i]), 2) if ms[i] else None, "signal": int(mt[i]), "atr_value": round(float(mv[i]), 4) if mv[i] else None})
        except Exception:
            pass

    return jsonify({"daily": daily_result[-limit:], "weekly": weekly_result[-limit:], "monthly": monthly_result[-limit:]})


def _portfolios_ohlc_all(market, limit=500, timeframe="1D"):
    conn = get_db(market)
    try:
        rows = conn.execute("SELECT id FROM portfolios ORDER BY created_at DESC").fetchall()
        if not rows:
            return []
        all_syms = {}
        for r in rows:
            strings = conn.execute("SELECT id FROM portfolio_strings WHERE portfolio_id=?", (r["id"],)).fetchall()
            for s in strings:
                syms = conn.execute(
                    "SELECT symbol, qty FROM portfolio_string_symbols WHERE portfolio_string_id=?", (s["id"],)
                ).fetchall()
                for sy in syms:
                    sym = sy["symbol"]
                    qty = sy["qty"] or 0
                    if sym in all_syms:
                        all_syms[sym] += qty
                    else:
                        all_syms[sym] = qty
        if not all_syms:
            return []
        placeholders = ",".join("?" * len(all_syms))
        sym_list = list(all_syms.keys())
        bars = conn.execute(
            f"SELECT symbol, date, open, high, low, close, volume FROM bars WHERE symbol IN ({placeholders}) ORDER BY date",
            sym_list
        ).fetchall()
        date_map = {}
        for b in bars:
            d = b["date"]
            qty = all_syms.get(b["symbol"], 0)
            if d not in date_map:
                date_map[d] = {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}
            date_map[d]["open"] += (b["open"] or 0) * qty
            date_map[d]["high"] += (b["high"] or 0) * qty
            date_map[d]["low"] += (b["low"] or 0) * qty
            date_map[d]["close"] += (b["close"] or 0) * qty
            date_map[d]["volume"] += (b["volume"] or 0)
        result = [{"time": d, "open": round(v["open"], 2), "high": round(v["high"], 2), "low": round(v["low"], 2), "close": round(v["close"], 2), "volume": v["volume"]} for d, v in sorted(date_map.items())]
        if timeframe not in ("1D", "daily", None) and result:
            import pandas as pd
            df = pd.DataFrame(result)
            df["time"] = pd.to_datetime(df["time"])
            df = df.set_index("time")
            rule = {"1W": "W", "1M": "ME"}.get(timeframe, "W")
            agg = df.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])
            agg["time"] = agg.index.strftime("%Y-%m-%d")
            result = [{"time": row["time"], "open": round(row["open"], 2), "high": round(row["high"], 2), "low": round(row["low"], 2), "close": round(row["close"], 2), "volume": int(row["volume"])} for _, row in agg.iterrows()]
        return result[-limit:]
    finally:
        conn.close()


@api_bp.route("/portfolios/equity_ohlc")
def api_portfolios_equity_ohlc():
    market = request.args.get("market", "US")
    limit = int(request.args.get("limit", 1000))
    timeframe = request.args.get("timeframe", "1D")
    conn = get_db(market)
    try:
        portfolios = conn.execute("SELECT id FROM portfolios ORDER BY created_at DESC").fetchall()
        if not portfolios:
            return jsonify([])

        string_data = []
        all_syms = set()
        for p in portfolios:
            strings = conn.execute(
                "SELECT id, entry_date, exit_date, status, entry_price, exit_price, realised_pnl FROM portfolio_strings WHERE portfolio_id=?",
                (p["id"],)
            ).fetchall()
            for s in strings:
                sd = dict(s)
                syms = conn.execute(
                    "SELECT symbol, qty FROM portfolio_string_symbols WHERE portfolio_string_id=?",
                    (sd["id"],)
                ).fetchall()
                sd["symbols"] = [{"symbol": x["symbol"], "qty": float(x["qty"])} for x in syms]
                for x in syms:
                    all_syms.add(x["symbol"])
                string_data.append(sd)

        if not all_syms:
            return jsonify([])

        placeholders = ",".join(["?"] * len(all_syms))
        sym_list = list(all_syms)
        rows = conn.execute(
            f"SELECT symbol, date, open, high, low, close FROM bars WHERE symbol IN ({placeholders}) ORDER BY date",
            sym_list
        ).fetchall()

        if not rows:
            return jsonify([])

        price_data = {}
        all_dates = set()
        for r in rows:
            dt, sym = r["date"], r["symbol"]
            all_dates.add(dt)
            if dt not in price_data:
                price_data[dt] = {}
            price_data[dt][sym] = {"open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])}

        sorted_dates = sorted(all_dates)
        equity_data = []
        cumulative_booked = 0

        for dt in sorted_dates:
            running_val = 0
            running_val_open = 0
            running_val_high = 0
            running_val_low = 0

            for sd in string_data:
                is_running = sd["status"] != "closed"
                entry_dt = sd["entry_date"]
                exit_dt = sd.get("exit_date")

                if is_running:
                    if entry_dt and dt >= entry_dt:
                        for sym_info in sd["symbols"]:
                            sym, qty = sym_info["symbol"], sym_info["qty"]
                            if sym in price_data.get(dt, {}):
                                p = price_data[dt][sym]
                                running_val += p["close"] * qty
                                running_val_open += p["open"] * qty
                                running_val_high += p["high"] * qty
                                running_val_low += p["low"] * qty
                else:
                    if exit_dt and dt >= exit_dt:
                        rp_raw = sd.get("realised_pnl")
                        rp = float(rp_raw) if rp_raw is not None and str(rp_raw) not in ('None', 'null', '') else 0.0
                        if rp == 0 and sd.get("entry_price") and sd.get("exit_price"):
                            rp = float(sd["exit_price"]) - float(sd["entry_price"])
                        cumulative_booked += rp
                    elif entry_dt and dt >= entry_dt and (not exit_dt or dt < exit_dt):
                        for sym_info in sd["symbols"]:
                            sym, qty = sym_info["symbol"], sym_info["qty"]
                            if sym in price_data.get(dt, {}):
                                p = price_data[dt][sym]
                                running_val += p["close"] * qty
                                running_val_open += p["open"] * qty
                                running_val_high += p["high"] * qty
                                running_val_low += p["low"] * qty

            total_close = running_val + cumulative_booked
            if total_close > 0 or running_val > 0:
                equity_data.append({
                    "time": dt,
                    "open": round(running_val_open + cumulative_booked, 2),
                    "high": round(max(running_val_open + cumulative_booked, running_val_high + cumulative_booked, total_close), 2),
                    "low": round(min(running_val_open + cumulative_booked, running_val_low + cumulative_booked, total_close), 2),
                    "close": round(total_close, 2),
                    "volume": 0
                })

        if timeframe not in ("1D", "daily", None) and equity_data:
            import pandas as pd
            df = pd.DataFrame(equity_data)
            df["time"] = pd.to_datetime(df["time"])
            df = df.set_index("time")
            rule = {"1W": "W", "1M": "ME"}.get(timeframe, "W")
            agg = df.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])
            agg["time"] = agg.index.strftime("%Y-%m-%d")
            equity_data = [{"time": row["time"], "open": round(row["open"], 2), "high": round(row["high"], 2), "low": round(row["low"], 2), "close": round(row["close"], 2), "volume": int(row["volume"])} for _, row in agg.iterrows()]

        return jsonify(equity_data[-limit:])
    finally:
        conn.close()


@api_bp.route("/portfolios", methods=["POST"])
def api_create_portfolio():
    data = request.json
    market = data.get("market", "US")
    name = data.get("name", "New Portfolio")
    conn = get_db(market)
    try:
        conn.execute("INSERT INTO portfolios (name) VALUES (?)", (name,))
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return jsonify({"id": pid, "name": name})
    finally:
        conn.close()


@api_bp.route("/portfolios/<int:pid>", methods=["DELETE"])
def api_delete_portfolio(pid):
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        conn.execute("DELETE FROM portfolios WHERE id=?", (pid,))
        conn.commit()
        return jsonify({"deleted": True})
    finally:
        conn.close()


@api_bp.route("/portfolio/add", methods=["POST"])
def api_portfolio_add():
    data = request.json
    market = data.get("market", "US")
    pid = data["portfolio_id"]
    symbol = data["symbol"]
    qty = data.get("qty", 0)
    avg_price = data.get("avg_price", 0)
    conn = get_db(market)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO portfolio_symbols (portfolio_id, symbol, qty, avg_price)
               VALUES (?, ?, ?, ?)""",
            (pid, symbol, qty, avg_price)
        )
        conn.commit()
        return jsonify({"added": True})
    finally:
        conn.close()


@api_bp.route("/portfolio/remove", methods=["POST"])
def api_portfolio_remove():
    data = request.json
    market = data.get("market", "US")
    pid = data["portfolio_id"]
    symbol = data["symbol"]
    conn = get_db(market)
    try:
        conn.execute("DELETE FROM portfolio_symbols WHERE portfolio_id=? AND symbol=?", (pid, symbol))
        conn.commit()
        return jsonify({"removed": True})
    finally:
        conn.close()


@api_bp.route("/portfolio/<int:pid>/ohlc")
@api_bp.route("/portfolios/<int:pid>/ohlc")
def api_portfolio_ohlc(pid):
    market = request.args.get("market", "US")
    limit = int(request.args.get("limit", 500))
    timeframe = request.args.get("timeframe", "1D")
    result = _portfolio_ohlc(pid, market, limit, timeframe)
    return jsonify(result)


def _portfolio_ohlc(pid, market, limit=500, timeframe="1D"):
    conn = get_db(market)
    try:
        symbols = []
        strings = conn.execute("SELECT id FROM portfolio_strings WHERE portfolio_id=?", (pid,)).fetchall()
        for s in strings:
            syms = conn.execute(
                "SELECT symbol, qty FROM portfolio_string_symbols WHERE portfolio_string_id=?", (s["id"],)
            ).fetchall()
            for x in syms:
                if x["symbol"] not in [s2["symbol"] for s2 in symbols]:
                    symbols.append({"symbol": x["symbol"], "qty": float(x["qty"])})
        if not symbols:
            return []
        sym_qty = {s["symbol"]: s["qty"] for s in symbols}
        sym_list = list(sym_qty.keys())
        placeholders = ",".join(["?"] * len(sym_list))
        rows = conn.execute(
            f"SELECT symbol, date, open, high, low, close, volume FROM bars WHERE symbol IN ({placeholders}) ORDER BY date",
            sym_list
        ).fetchall()
        if not rows:
            return []
        all_bars = {}
        for r in rows:
            dt = r["date"]
            if dt not in all_bars:
                all_bars[dt] = {"time": dt, "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}
            qty = sym_qty.get(r["symbol"], 1.0)
            all_bars[dt]["open"] += qty * float(r["open"])
            all_bars[dt]["high"] += qty * float(r["high"])
            all_bars[dt]["low"] += qty * float(r["low"])
            all_bars[dt]["close"] += qty * float(r["close"])
            all_bars[dt]["volume"] += int(r["volume"])
        result = []
        for dt in sorted(all_bars.keys()):
            b = all_bars[dt]
            result.append({
                "time": b["time"],
                "open": round(b["open"], 2),
                "high": round(b["high"], 2),
                "low": round(b["low"], 2),
                "close": round(b["close"], 2),
                "volume": b["volume"]
            })
        if timeframe not in ("1D", "daily", None) and result:
            import pandas as pd
            df = pd.DataFrame(result)
            df["time"] = pd.to_datetime(df["time"])
            df = df.set_index("time")
            rule = {"1W": "W", "1M": "ME"}.get(timeframe, "W")
            agg = df.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])
            agg["time"] = agg.index.strftime("%Y-%m-%d")
            result = [{"time": row["time"], "open": round(row["open"], 2), "high": round(row["high"], 2), "low": round(row["low"], 2), "close": round(row["close"], 2), "volume": int(row["volume"])} for _, row in agg.iterrows()]
        return result[-limit:]
    finally:
        conn.close()


@api_bp.route("/portfolio/<int:pid>/supertrend")
@api_bp.route("/portfolios/<int:pid>/supertrend")
def api_portfolio_supertrend(pid):
    market = request.args.get("market", "US")
    period = int(request.args.get("period", 14))
    multiplier = float(request.args.get("multiplier", 2.0))
    limit = int(request.args.get("limit", 500))
    timeframe = request.args.get("timeframe", "1D")

    ohlc = _portfolio_ohlc(pid, market, limit=500, timeframe="1D")
    if not ohlc:
        return jsonify({"daily": [], "weekly": [], "monthly": []})

    import pandas as pd
    from dumbmoney.indicators import atr_trailing_stop
    from dumbmoney.indicators import compute_rolling_atr_batch

    df = pd.DataFrame(ohlc)
    df["open"] = pd.to_numeric(df["open"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])
    df["close"] = pd.to_numeric(df["close"])

    # Daily ATR Trailing Stop
    st = atr_trailing_stop(df, period=period, multiplier=multiplier)
    st["time"] = df["time"].values
    daily_result = []
    for _, row in st.iterrows():
        daily_result.append({
            "time": row["time"],
            "value": round(float(row["supertrend"]), 2) if pd.notna(row["supertrend"]) else None,
            "signal": int(row["signal"]),
            "atr_value": round(float(row["atr_value"]), 4) if pd.notna(row.get("atr_value")) else None,
        })

    # Anchored rolling weekly (5 sessions) - batch computation
    weekly_result = []
    if len(df) >= 7:
        try:
            dates_arr = df["time"].values
            opens_arr = df["open"].astype(float).values
            highs_arr = df["high"].astype(float).values
            lows_arr = df["low"].astype(float).values
            closes_arr = df["close"].astype(float).values
            wt, ws, wv, wsk, wca, wcb, wbl, wab = compute_rolling_atr_batch(
                dates_arr, opens_arr, highs_arr, lows_arr, closes_arr, 5, period, multiplier
            )
            for i in range(len(dates_arr)):
                if wt[i] != 0 or ws[i] != 0:
                    key = str(dates_arr[i])[:10]
                    weekly_result.append({
                        "time": key,
                        "value": round(float(ws[i]), 2) if ws[i] else None,
                        "signal": int(wt[i]),
                        "atr_value": round(float(wv[i]), 4) if wv[i] else None,
                    })
        except Exception:
            pass

    # Anchored rolling monthly (22 sessions) - batch computation
    monthly_result = []
    if len(df) >= 24:
        try:
            dates_arr = df["time"].values
            opens_arr = df["open"].astype(float).values
            highs_arr = df["high"].astype(float).values
            lows_arr = df["low"].astype(float).values
            closes_arr = df["close"].astype(float).values
            mt, ms, mv, msk, mca, mcb, mbl, mab = compute_rolling_atr_batch(
                dates_arr, opens_arr, highs_arr, lows_arr, closes_arr, 22, period, multiplier
            )
            for i in range(len(dates_arr)):
                if mt[i] != 0 or ms[i] != 0:
                    key = str(dates_arr[i])[:10]
                    monthly_result.append({
                        "time": key,
                        "value": round(float(ms[i]), 2) if ms[i] else None,
                        "signal": int(mt[i]),
                        "atr_value": round(float(mv[i]), 4) if mv[i] else None,
                    })
        except Exception:
            pass

    return jsonify({"daily": daily_result[-limit:], "weekly": weekly_result[-limit:], "monthly": monthly_result[-limit:]})


@api_bp.route("/portfolio/<int:pid>/equity_ohlc")
def api_portfolio_equity_ohlc(pid):
    """Equity chart: reconstructs portfolio value over time from trade history.
    Running strings contribute market value, closed strings contribute booked profit."""
    market = request.args.get("market", "US")
    limit = int(request.args.get("limit", 1000))
    timeframe = request.args.get("timeframe", "1D")

    conn = get_db(market)
    try:
        # Get all strings with their symbols
        strings = conn.execute(
            "SELECT id, entry_date, exit_date, status, entry_price, exit_price, realised_pnl FROM portfolio_strings WHERE portfolio_id=?",
            (pid,)
        ).fetchall()
        if not strings:
            return jsonify([])

        # Build string data with symbols
        string_data = []
        all_syms = set()
        for s in strings:
            sd = dict(s)
            syms = conn.execute(
                "SELECT symbol, qty FROM portfolio_string_symbols WHERE portfolio_string_id=?",
                (sd["id"],)
            ).fetchall()
            sd["symbols"] = [{"symbol": x["symbol"], "qty": float(x["qty"])} for x in syms]
            for x in syms:
                all_syms.add(x["symbol"])
            string_data.append(sd)

        if not all_syms:
            return jsonify([])

        # Get all bars for these symbols
        placeholders = ",".join(["?"] * len(all_syms))
        sym_list = list(all_syms)
        rows = conn.execute(
            f"SELECT symbol, date, open, high, low, close FROM bars WHERE symbol IN ({placeholders}) ORDER BY date",
            sym_list
        ).fetchall()

        if not rows:
            return jsonify([])

        # Build price lookup: {date: {symbol: {open, high, low, close}}}
        price_data = {}
        all_dates = set()
        for r in rows:
            dt = r["date"]
            sym = r["symbol"]
            all_dates.add(dt)
            if dt not in price_data:
                price_data[dt] = {}
            price_data[dt][sym] = {
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"])
            }

        sorted_dates = sorted(all_dates)

        # Build equity curve
        equity_data = []
        cumulative_booked = 0

        for dt in sorted_dates:
            running_val = 0
            running_val_open = 0
            running_val_high = 0
            running_val_low = 0

            for sd in string_data:
                is_running = sd["status"] != "closed"
                entry_dt = sd["entry_date"]
                exit_dt = sd.get("exit_date")

                # Check if this string was active on this date
                if is_running:
                    # Active if date >= entry_date
                    if entry_dt and dt >= entry_dt:
                        for sym_info in sd["symbols"]:
                            sym = sym_info["symbol"]
                            qty = sym_info["qty"]
                            if sym in price_data.get(dt, {}):
                                p = price_data[dt][sym]
                                running_val += p["close"] * qty
                                running_val_open += p["open"] * qty
                                running_val_high += p["high"] * qty
                                running_val_low += p["low"] * qty
                else:
                    # Closed string: add booked profit from exit_date onwards
                    if exit_dt and dt >= exit_dt:
                        rp_raw = sd.get("realised_pnl")
                        rp = float(rp_raw) if rp_raw is not None and str(rp_raw) not in ('None', 'null', '') else 0.0
                        if rp == 0 and sd.get("entry_price") and sd.get("exit_price"):
                            rp = float(sd["exit_price"]) - float(sd["entry_price"])
                        cumulative_booked += rp
                    # While still active (entry_date <= dt < exit_date), contribute market value
                    elif entry_dt and dt >= entry_dt and (not exit_dt or dt < exit_dt):
                        for sym_info in sd["symbols"]:
                            sym = sym_info["symbol"]
                            qty = sym_info["qty"]
                            if sym in price_data.get(dt, {}):
                                p = price_data[dt][sym]
                                running_val += p["close"] * qty
                                running_val_open += p["open"] * qty
                                running_val_high += p["high"] * qty
                                running_val_low += p["low"] * qty

            total_close = running_val + cumulative_booked
            total_open = running_val_open + cumulative_booked
            total_high = running_val_high + cumulative_booked
            total_low = running_val_low + cumulative_booked

            if total_close > 0 or running_val > 0:
                equity_data.append({
                    "time": dt,
                    "open": round(total_open, 2),
                    "high": round(max(total_open, total_high, total_close), 2),
                    "low": round(min(total_open, total_low, total_close), 2),
                    "close": round(total_close, 2),
                    "volume": 0
                })

        # Resample for weekly/monthly if needed
        if timeframe not in ("1D", "daily", None) and equity_data:
            import pandas as pd
            df = pd.DataFrame(equity_data)
            df["time"] = pd.to_datetime(df["time"])
            df = df.set_index("time")
            rule = {"1W": "W", "1M": "ME"}.get(timeframe, "W")
            agg = df.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])
            agg["time"] = agg.index.strftime("%Y-%m-%d")
            equity_data = [{"time": row["time"], "open": round(row["open"], 2), "high": round(row["high"], 2), "low": round(row["low"], 2), "close": round(row["close"], 2), "volume": int(row["volume"])} for _, row in agg.iterrows()]

        return jsonify(equity_data[-limit:])
    finally:
        conn.close()


@api_bp.route("/portfolio/<int:pid>/accel")
@api_bp.route("/portfolios/<int:pid>/accel")
def api_portfolio_accel(pid):
    market = request.args.get("market", "US")
    limit = int(request.args.get("limit", 500))
    timeframe = request.args.get("timeframe", "1D")

    ohlc = _portfolio_ohlc(pid, market, limit=500, timeframe=timeframe)
    if not ohlc:
        return jsonify([])

    import pandas as pd
    from dumbmoney.indicators import accel

    df = pd.DataFrame(ohlc)
    df["open"] = pd.to_numeric(df["open"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])
    df["close"] = pd.to_numeric(df["close"])

    acc = accel(df)
    acc["time"] = df["time"].values
    result = []
    for _, row in acc.iterrows():
        result.append({
            "time": row["time"],
            "accel_a": round(float(row.get("accel_a", 0)), 4),
            "accel_base": round(float(row.get("accel_base", 0)), 4),
            "crossed_up": int(row.get("accel_crossed_up", 0)),
            "crossed_down": int(row.get("accel_crossed_down", 0))
        })
    return jsonify(result[-limit:])


@api_bp.route("/portfolios/groups")
def api_portfolio_groups():
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        rows = conn.execute("SELECT * FROM portfolio_groups ORDER BY created_at DESC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            members = conn.execute(
                "SELECT p.id, p.name FROM portfolio_group_members gm JOIN portfolios p ON gm.portfolio_id=p.id WHERE gm.group_id=?",
                (r["id"],)
            ).fetchall()
            d["portfolios"] = [dict(m) for m in members]
            result.append(d)
        return jsonify(result)
    finally:
        conn.close()


@api_bp.route("/portfolio/string/preview", methods=["POST"])
def api_portfolio_string_preview():
    data = request.json
    market = data.get("market", "US")
    raw = data.get("symbols", "")
    amount = data.get("amount")
    symbol_list = []

    for part in raw.replace("+", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "*" in part:
            parts = part.split("*", 1)
            sym = parts[0].strip().upper()
            try:
                qty = float(parts[1].strip())
            except (ValueError, IndexError):
                qty = 0
            symbol_list.append({"symbol": sym, "qty": qty})
        else:
            sym = part.strip().upper()
            if sym:
                symbol_list.append({"symbol": sym, "qty": 0})

    if not symbol_list:
        return jsonify({"error": "No valid symbols"}), 400

    conn = get_db(market)
    try:
        results = []
        for item in symbol_list:
            sym = item["symbol"]
            row = conn.execute(
                "SELECT name, price, volume, change_pct, weighted_alpha FROM stats WHERE symbol=?",
                (sym,)
            ).fetchone()
            if row:
                price = float(row["price"] or 0)
                name = row["name"] or sym
            else:
                bsym = sym.replace(".NS", "").replace(".BO", "")
                price = 0
                name = bsym
            item["price"] = price
            item["name"] = name
            results.append(item)

        has_qty = any(r["qty"] > 0 for r in results)
        if not has_qty and amount and amount > 0:
            for r in results:
                if r["price"] > 0:
                    r["qty"] = round(amount / r["price"]) if market == "INDIA" else round(amount / r["price"], 4)
                else:
                    r["qty"] = 0

        total_value = sum(r["price"] * r["qty"] for r in results if r["price"] > 0)
        return jsonify({"symbols": results, "total_value": total_value, "has_qty": has_qty})
    finally:
        conn.close()


@api_bp.route("/portfolio/string/add", methods=["POST"])
def api_portfolio_string_add():
    data = request.json
    market = data.get("market", "US")
    portfolio_id = data.get("portfolio_id")
    name = data.get("name", "")
    entry_date = data.get("entry_date")
    entry_price = data.get("entry_price")
    fractional = data.get("fractional", 0)
    symbols = data.get("symbols", [])

    if not portfolio_id or not entry_date or not symbols:
        return jsonify({"error": "portfolio_id, entry_date, and symbols required"}), 400

    conn = get_db(market)
    try:
        ep = float(entry_price) if entry_price else 0
        num_syms = len(symbols)

        def _entry_close(sym):
            bar = conn.execute(
                "SELECT close FROM bars WHERE symbol=? AND date<=? ORDER BY date DESC LIMIT 1",
                (sym, entry_date)
            ).fetchone()
            return float(bar["close"]) if bar and bar["close"] else 0.0

        has_explicit_qty = any(float(s.get("qty", 0) or 0) > 0 for s in symbols)
        if has_explicit_qty:
            # Respect the quantities typed in the string expression
            # (AAPL*10+MSFT*15 means 10 and 15 shares). Never normalize them
            # away — that used to make every string with the same entry amount
            # show identical values/holdings.
            corrected = []
            actual_cost = 0.0
            for s in symbols:
                sym = s.get("symbol", "").upper()
                qty = float(s.get("qty", 0) or 0)
                corrected.append((sym, qty, s.get("weight", 1.0), s.get("fractional_allowed", False)))
                entry_px = _entry_close(sym)
                if entry_px > 0:
                    actual_cost += qty * entry_px
                else:
                    px = s.get("price", 0) or 0
                    actual_cost += qty * float(px)
            if actual_cost > 0:
                ep = actual_cost
        elif ep > 0 and num_syms > 0:
            # No quantities given: split the entry amount equally per symbol
            per_stock = ep / num_syms
            corrected = []
            for s in symbols:
                sym = s.get("symbol", "").upper()
                entry_px = _entry_close(sym)
                corrected_qty = (per_stock / entry_px) if entry_px > 0 else 0.0
                corrected.append((sym, corrected_qty, s.get("weight", 1.0), s.get("fractional_allowed", False)))
        else:
            total_cost = 0
            for s in symbols:
                price = s.get("price", 0) or 0
                total_cost += float(s.get("qty", 0)) * float(price)
            ep = total_cost
            corrected = [(s.get("symbol", "").upper(), float(s.get("qty", 0)), s.get("weight", 1.0), s.get("fractional_allowed", False)) for s in symbols]

        cur = conn.execute(
            """INSERT INTO portfolio_strings (portfolio_id, name, entry_date, entry_price, fractional)
               VALUES (?, ?, ?, ?, ?)""",
            (portfolio_id, name, entry_date, round(ep, 2), 1 if fractional else 0)
        )
        psid = cur.lastrowid

        for sym, qty, weight, frac_allowed in corrected:
            if sym:
                conn.execute(
                    """INSERT INTO portfolio_string_symbols
                       (portfolio_string_id, symbol, qty, weight, fractional_allowed)
                       VALUES (?, ?, ?, ?, ?)""",
                    (psid, sym, qty, weight, frac_allowed)
                )
        conn.commit()

        string_row = conn.execute("SELECT * FROM portfolio_strings WHERE id=?", (psid,)).fetchone()
        return jsonify({"ok": True, "string": dict(string_row) if string_row else None})
    finally:
        conn.close()


@api_bp.route("/portfolio/string/close", methods=["POST"])
def api_portfolio_string_close():
    data = request.json
    market = data.get("market", "US")
    psid = data.get("portfolio_string_id")
    exit_date = data.get("exit_date")
    exit_price = data.get("exit_price")

    if not psid or not exit_date:
        return jsonify({"error": "portfolio_string_id and exit_date required"}), 400

    conn = get_db(market)
    try:
        # Get entry_price to calculate realised_pnl
        row = conn.execute("SELECT entry_price FROM portfolio_strings WHERE id=?", (psid,)).fetchone()
        entry_price = float(row["entry_price"] or 0) if row else 0
        ep = float(exit_price) if exit_price else 0
        realised_pnl = ep - entry_price

        conn.execute(
            "UPDATE portfolio_strings SET exit_date=?, exit_price=?, status='closed', realised_pnl=? WHERE id=?",
            (exit_date, exit_price, realised_pnl, psid)
        )
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@api_bp.route("/portfolio/string/reopen", methods=["POST"])
def api_portfolio_string_reopen():
    data = request.json
    market = data.get("market", "US")
    psid = data.get("portfolio_string_id")
    entry_date = data.get("entry_date")
    entry_price = data.get("entry_price")

    if not psid or not entry_date:
        return jsonify({"error": "portfolio_string_id and entry_date required"}), 400

    conn = get_db(market)
    try:
        conn.execute(
            "UPDATE portfolio_strings SET entry_date=?, entry_price=?, exit_date=NULL, exit_price=NULL, status='running' WHERE id=?",
            (entry_date, entry_price, psid)
        )
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@api_bp.route("/portfolio/string/edit", methods=["POST"])
def api_portfolio_string_edit():
    data = request.json
    market = data.get("market", "US")
    psid = data.get("portfolio_string_id")
    name = data.get("name")
    entry_date = data.get("entry_date")
    entry_price = data.get("entry_price")
    exit_date = data.get("exit_date")
    exit_price = data.get("exit_price")
    status = data.get("status")
    symbols = data.get("symbols")

    if not psid:
        return jsonify({"error": "portfolio_string_id required"}), 400

    conn = get_db(market)
    try:
        updates = []
        params = []
        if name is not None:
            updates.append("name=?")
            params.append(name)
        if entry_date is not None:
            updates.append("entry_date=?")
            params.append(entry_date)
        if entry_price is not None:
            updates.append("entry_price=?")
            params.append(entry_price)
        if exit_date is not None:
            updates.append("exit_date=?")
            params.append(exit_date)
        if exit_price is not None:
            updates.append("exit_price=?")
            params.append(exit_price)
        if status is not None:
            updates.append("status=?")
            params.append(status)
        # Recalculate realised_pnl if entry_price or exit_price changed
        if entry_price is not None or exit_price is not None:
            row = conn.execute("SELECT entry_price, exit_price, status FROM portfolio_strings WHERE id=?", (psid,)).fetchone()
            if row:
                ep_val = float(entry_price) if entry_price is not None else float(row["entry_price"] or 0)
                xp_val = float(exit_price) if exit_price is not None else float(row["exit_price"] or 0)
                st_val = status if status is not None else row["status"]
                if st_val == "closed" and ep_val and xp_val:
                    updates.append("realised_pnl=?")
                    params.append(xp_val - ep_val)
        if updates:
            params.append(psid)
            conn.execute(f"UPDATE portfolio_strings SET {','.join(updates)} WHERE id=?", params)
        if symbols is not None:
            conn.execute("DELETE FROM portfolio_string_symbols WHERE portfolio_string_id=?", (psid,))
            for s in symbols:
                sym = s.get("symbol", "").upper()
                qty = s.get("qty", 0)
                weight = s.get("weight", 1.0)
                frac_allowed = 1 if s.get("fractional_allowed", False) else 0
                if sym:
                    conn.execute(
                        """INSERT INTO portfolio_string_symbols
                           (portfolio_string_id, symbol, qty, weight, fractional_allowed)
                           VALUES (?, ?, ?, ?, ?)""",
                        (psid, sym, qty, weight, frac_allowed)
                    )
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@api_bp.route("/portfolio/<int:pid>/edit", methods=["POST"])
def api_portfolio_edit(pid):
    data = request.json
    market = data.get("market", "US")
    name = data.get("name")
    conn = get_db(market)
    try:
        if name is not None:
            conn.execute("UPDATE portfolios SET name=? WHERE id=?", (name, pid))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@api_bp.route("/portfolio/<int:pid>/reorder", methods=["POST"])
def api_portfolio_reorder(pid):
    data = request.json
    market = data.get("market", "US")
    order = data.get("order", [])
    conn = get_db(market)
    try:
        for i, psid in enumerate(order):
            conn.execute("UPDATE portfolio_strings SET sort_order=? WHERE id=? AND portfolio_id=?", (i, psid, pid))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@api_bp.route("/portfolio/<int:pid>/minichart")
def api_portfolio_minichart(pid):
    market = request.args.get("market", "US")
    limit = int(request.args.get("limit", 30))
    ohlc = _portfolio_ohlc(pid, market, limit=limit)
    return jsonify(ohlc)


@api_bp.route("/portfolio/string/<int:psid>/minichart")
def api_portfolio_string_minichart(psid):
    market = request.args.get("market", "US")
    limit = int(request.args.get("limit", 30))
    ohlc = _string_ohlc(psid, market, limit=limit)
    return jsonify(ohlc)


@api_bp.route("/portfolio/seed", methods=["POST"])
def api_portfolio_seed():
    data = request.json
    market = data.get("market", "US")
    conn = get_db(market)
    try:
        existing = conn.execute("SELECT COUNT(*) FROM portfolios").fetchone()[0]
        if existing > 0:
            return jsonify({"ok": True, "msg": "Already seeded"})

        samples = [
            {"name": "Tech Growth", "strings": [
                {"name": "FAANG Long", "symbols": [{"symbol": "META", "qty": 10}, {"symbol": "AAPL", "qty": 10}, {"symbol": "NFLX", "qty": 5}, {"symbol": "AMZN", "qty": 8}, {"symbol": "GOOGL", "qty": 7}]},
                {"name": "AI Bets", "symbols": [{"symbol": "NVDA", "qty": 15}, {"symbol": "MSFT", "qty": 10}, {"symbol": "PLTR", "qty": 20}]},
            ]},
            {"name": "Dividend Income", "strings": [
                {"name": "High Yield", "symbols": [{"symbol": "T", "qty": 50}, {"symbol": "VZ", "qty": 40}, {"symbol": "KO", "qty": 30}]},
                {"name": "REIT Play", "symbols": [{"symbol": "O", "qty": 25}, {"symbol": "AGNC", "qty": 40}]},
            ]},
            {"name": "Momentum Play", "strings": [
                {"name": "Breakout Pack", "symbols": [{"symbol": "TSLA", "qty": 8}, {"symbol": "AMD", "qty": 12}, {"symbol": "COIN", "qty": 10}]},
            ]},
        ]

        from datetime import date
        today = date.today().isoformat()

        for port in samples:
            cur = conn.execute("INSERT INTO portfolios (name) VALUES (?)", (port["name"],))
            pid = cur.lastrowid
            for i, string in enumerate(port["strings"]):
                syms = string["symbols"]
                total_cost = 0
                total_shares = 0
                for s in syms:
                    row = conn.execute("SELECT price FROM stats WHERE symbol=?", (s["symbol"],)).fetchone()
                    price = float(row[0]) if row and row[0] else 100.0
                    total_cost += price * s["qty"]
                    total_shares += s["qty"]
                scur = conn.execute(
                    "INSERT INTO portfolio_strings (portfolio_id, name, entry_date, entry_price, status, sort_order) VALUES (?,?,?,?,?,?)",
                    (pid, string["name"], today, round(total_cost, 2), "running", i)
                )
                psid = scur.lastrowid
                for s in syms:
                    conn.execute(
                        "INSERT INTO portfolio_string_symbols (portfolio_string_id, symbol, qty, weight, fractional_allowed) VALUES (?,?,?,?,?)",
                        (psid, s["symbol"], s["qty"], 1.0, 0)
                    )
        conn.commit()
        return jsonify({"ok": True, "msg": "Seeded 3 portfolios"})
    finally:
        conn.close()


@api_bp.route("/portfolio/string/<int:psid>", methods=["DELETE"])
def api_portfolio_string_delete(psid):
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        conn.execute("DELETE FROM portfolio_string_symbols WHERE portfolio_string_id=?", (psid,))
        conn.execute("DELETE FROM portfolio_strings WHERE id=?", (psid,))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@api_bp.route("/portfolio/<int:pid>/strings")
def api_portfolio_strings_list(pid):
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        strings = conn.execute(
            "SELECT * FROM portfolio_strings WHERE portfolio_id=? ORDER BY created_at DESC", (pid,)
        ).fetchall()
        result = []
        for s in strings:
            d = dict(s)
            syms = conn.execute(
                "SELECT symbol, qty, weight, fractional_allowed FROM portfolio_string_symbols WHERE portfolio_string_id=?",
                (s["id"],)
            ).fetchall()
            d["symbols"] = [dict(x) for x in syms]

            if d["symbols"]:
                placeholders = ",".join(["?"] * len(d["symbols"]))
                sym_list = [x["symbol"] for x in d["symbols"]]
                stats_rows = conn.execute(
                    f"SELECT symbol, price, change_pct, weighted_alpha FROM stats WHERE symbol IN ({placeholders})",
                    sym_list
                ).fetchall()
                stats_map = {r["symbol"]: dict(r) for r in stats_rows}

                entry_value = 0
                current_value = 0
                for x in d["symbols"]:
                    st = stats_map.get(x["symbol"], {})
                    price = float(st.get("price") or 0)
                    current_value += float(x["qty"]) * price

                if d.get("entry_price"):
                    entry_value = float(d["entry_price"])
                    if d.get("status") == "closed" and d.get("exit_price"):
                        exit_value = float(d["exit_price"])
                        d["realised_pnl"] = exit_value - entry_value
                        d["unrealised_pnl"] = 0
                    else:
                        d["realised_pnl"] = 0
                        d["unrealised_pnl"] = current_value - entry_value
                else:
                    d["realised_pnl"] = 0
                    d["unrealised_pnl"] = 0

                d["total_value"] = current_value
                d["num_stocks"] = len(d["symbols"])
            else:
                d["total_value"] = 0
                d["num_stocks"] = 0
                d["realised_pnl"] = 0
                d["unrealised_pnl"] = 0

            result.append(d)
        return jsonify(result)
    finally:
        conn.close()


@api_bp.route("/portfolio/string/<int:psid>/detail")
def api_portfolio_string_detail(psid):
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        s = conn.execute("SELECT * FROM portfolio_strings WHERE id=?", (psid,)).fetchone()
        if not s:
            return jsonify({"error": "String not found"}), 404
        d = dict(s)
        syms = conn.execute(
            "SELECT symbol, qty, weight, fractional_allowed FROM portfolio_string_symbols WHERE portfolio_string_id=?",
            (psid,)
        ).fetchall()
        d["symbols"] = [dict(x) for x in syms]

        if d["symbols"]:
            placeholders = ",".join(["?"] * len(d["symbols"]))
            sym_list = [x["symbol"] for x in d["symbols"]]
            stats_rows = conn.execute(
                f"""SELECT symbol, name, price, change_pct, volume, weighted_alpha,
                    atr_signal, atr_stop, atr_value, atr_streak, atr_multiplier,
                    streak, prob_up_1d, prob_up_5d, atrp, confluence,
                    accel_a, accel_base, accel_signal, accel_crossed_up, accel_crossed_down
                    FROM stats WHERE symbol IN ({placeholders})""",
                sym_list
            ).fetchall()
            stats_map = {r["symbol"]: dict(r) for r in stats_rows}

            for x in d["symbols"]:
                st = stats_map.get(x["symbol"], {})
                x["name"] = st.get("name", x["symbol"])
                x["price"] = float(st.get("price") or 0)
                x["change_pct"] = float(st.get("change_pct") or 0)
                x["weighted_alpha"] = float(st.get("weighted_alpha") or 0)
                x["atr_signal"] = int(st.get("atr_signal") or 0)
                x["streak"] = int(st.get("streak") or 0)
                x["prob_up_1d"] = float(st.get("prob_up_1d") or 0)
                x["atrp"] = float(st.get("atrp") or 0)
                x["volume"] = float(st.get("volume") or 0)
                x["current_price"] = x["price"]

            current_value = sum(x["price"] * float(x["qty"]) for x in d["symbols"] if x["price"] > 0)
            d["total_value"] = current_value
            d["current_value"] = current_value
            d["entry_value"] = float(d["entry_price"]) if d.get("entry_price") else 0

            total_weight = sum(float(x["price"]) * float(x["qty"]) for x in d["symbols"] if x["price"] > 0)
            if total_weight > 0:
                d["prob_1up"] = round(sum(x["prob_up_1d"] * float(x["price"]) * float(x["qty"]) for x in d["symbols"] if x["price"] > 0) / total_weight, 4)
                d["change_pct"] = round(sum(x["change_pct"] * float(x["price"]) * float(x["qty"]) for x in d["symbols"] if x["price"] > 0) / total_weight, 4)
            else:
                d["prob_1up"] = 0
                d["change_pct"] = 0

            if d.get("entry_price"):
                entry_total = float(d["entry_price"])
                total_qty = sum(float(x["qty"]) for x in d["symbols"]) or 1
                per_share_entry = entry_total / total_qty
                for x in d["symbols"]:
                    x["entry_price"] = per_share_entry
                    x["pnl"] = (x["price"] - per_share_entry) * float(x["qty"])
                    x["pnl_pct"] = ((x["price"] - per_share_entry) / per_share_entry * 100) if per_share_entry > 0 else 0
                if d.get("status") == "closed" and d.get("exit_price"):
                    exit_total = float(d["exit_price"])
                    d["realised_pnl"] = exit_total - entry_total
                    d["unrealised_pnl"] = 0
                else:
                    d["realised_pnl"] = 0
                    d["unrealised_pnl"] = current_value - entry_total
                d["pnl_pct"] = ((current_value / entry_total - 1) * 100) if entry_total > 0 else 0
            else:
                d["realised_pnl"] = 0
                d["unrealised_pnl"] = 0
                d["pnl_pct"] = 0
                for x in d["symbols"]:
                    x["entry_price"] = 0
        else:
            d["total_value"] = 0
            d["realised_pnl"] = 0
            d["unrealised_pnl"] = 0

        return jsonify(d)
    finally:
        conn.close()


@api_bp.route("/portfolio/string/<int:psid>/ohlc")
def api_portfolio_string_ohlc(psid):
    market = request.args.get("market", "US")
    limit = int(request.args.get("limit", 500))
    timeframe = request.args.get("timeframe", "1D")
    result = _string_ohlc(psid, market, limit, timeframe)
    return jsonify(result)


def _string_ohlc(psid, market, limit=500, timeframe="1D"):
    conn = get_db(market)
    try:
        syms = conn.execute(
            "SELECT symbol, qty, weight FROM portfolio_string_symbols WHERE portfolio_string_id=?",
            (psid,)
        ).fetchall()
        if not syms:
            return []

        valid_syms = []
        for s in syms:
            latest = conn.execute(
                "SELECT close FROM bars WHERE symbol=? ORDER BY date DESC LIMIT 1",
                (s["symbol"],)
            ).fetchone()
            if latest and float(latest["close"] or 0) > 0:
                valid_syms.append(s)
        if not valid_syms:
            return []

        all_bars = {}
        for s in valid_syms:
            rows = conn.execute(
                "SELECT date, open, high, low, close, volume FROM bars WHERE symbol=? ORDER BY date",
                (s["symbol"],)
            ).fetchall()
            for r in rows:
                dt = r["date"]
                if dt not in all_bars:
                    all_bars[dt] = {"time": dt, "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}
                qty = float(s["qty"])
                all_bars[dt]["open"] += qty * float(r["open"])
                all_bars[dt]["high"] += qty * float(r["high"])
                all_bars[dt]["low"] += qty * float(r["low"])
                all_bars[dt]["close"] += qty * float(r["close"])
                all_bars[dt]["volume"] += int(r["volume"])

        result = []
        for dt in sorted(all_bars.keys()):
            b = all_bars[dt]
            result.append({
                "time": b["time"],
                "open": round(b["open"], 2),
                "high": round(b["high"], 2),
                "low": round(b["low"], 2),
                "close": round(b["close"], 2),
                "volume": b["volume"]
            })
        if timeframe not in ("1D", "daily", None) and result:
            import pandas as pd
            df = pd.DataFrame(result)
            df["time"] = pd.to_datetime(df["time"])
            df = df.set_index("time")
            rule = {"1W": "W", "1M": "ME"}.get(timeframe, "W")
            agg = df.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])
            agg["time"] = agg.index.strftime("%Y-%m-%d")
            result = [{"time": row["time"], "open": round(row["open"], 2), "high": round(row["high"], 2), "low": round(row["low"], 2), "close": round(row["close"], 2), "volume": int(row["volume"])} for _, row in agg.iterrows()]
        return result[-limit:]
    finally:
        conn.close()


@api_bp.route("/portfolio/string/<int:psid>/supertrend")
def api_portfolio_string_supertrend(psid):
    market = request.args.get("market", "US")
    period = int(request.args.get("period", 14))
    multiplier = float(request.args.get("multiplier", 2.0))
    limit = int(request.args.get("limit", 500))

    ohlc = _string_ohlc(psid, market, limit=500, timeframe="1D")
    if not ohlc:
        return jsonify({"daily": [], "weekly": [], "monthly": []})

    import pandas as pd
    from dumbmoney.indicators import atr_trailing_stop
    from dumbmoney.indicators import compute_rolling_atr_batch

    df = pd.DataFrame(ohlc)
    df["open"] = pd.to_numeric(df["open"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])
    df["close"] = pd.to_numeric(df["close"])

    # Daily ATR Trailing Stop
    st = atr_trailing_stop(df, period=period, multiplier=multiplier)
    st["time"] = df["time"].values
    daily_result = []
    for _, row in st.iterrows():
        daily_result.append({
            "time": row["time"],
            "value": round(float(row["supertrend"]), 2) if pd.notna(row["supertrend"]) else None,
            "signal": int(row["signal"]),
            "atr_value": round(float(row["atr_value"]), 4) if pd.notna(row.get("atr_value")) else None,
        })

    # Anchored rolling weekly (5 sessions) - batch computation
    weekly_result = []
    if len(df) >= 7:
        try:
            dates_arr = df["time"].values
            opens_arr = df["open"].astype(float).values
            highs_arr = df["high"].astype(float).values
            lows_arr = df["low"].astype(float).values
            closes_arr = df["close"].astype(float).values
            wt, ws, wv, wsk, wca, wcb, wbl, wab = compute_rolling_atr_batch(
                dates_arr, opens_arr, highs_arr, lows_arr, closes_arr, 5, period, multiplier
            )
            for i in range(len(dates_arr)):
                if wt[i] != 0 or ws[i] != 0:
                    key = str(dates_arr[i])[:10]
                    weekly_result.append({
                        "time": key,
                        "value": round(float(ws[i]), 2) if ws[i] else None,
                        "signal": int(wt[i]),
                        "atr_value": round(float(wv[i]), 4) if wv[i] else None,
                    })
        except Exception:
            pass

    # Anchored rolling monthly (22 sessions) - batch computation
    monthly_result = []
    if len(df) >= 24:
        try:
            dates_arr = df["time"].values
            opens_arr = df["open"].astype(float).values
            highs_arr = df["high"].astype(float).values
            lows_arr = df["low"].astype(float).values
            closes_arr = df["close"].astype(float).values
            mt, ms, mv, msk, mca, mcb, mbl, mab = compute_rolling_atr_batch(
                dates_arr, opens_arr, highs_arr, lows_arr, closes_arr, 22, period, multiplier
            )
            for i in range(len(dates_arr)):
                if mt[i] != 0 or ms[i] != 0:
                    key = str(dates_arr[i])[:10]
                    monthly_result.append({
                        "time": key,
                        "value": round(float(ms[i]), 2) if ms[i] else None,
                        "signal": int(mt[i]),
                        "atr_value": round(float(mv[i]), 4) if mv[i] else None,
                    })
        except Exception:
            pass

    return jsonify({"daily": daily_result[-limit:], "weekly": weekly_result[-limit:], "monthly": monthly_result[-limit:]})


@api_bp.route("/portfolio/string/<int:psid>/accel")
def api_portfolio_string_accel(psid):
    market = request.args.get("market", "US")
    limit = int(request.args.get("limit", 500))
    timeframe = request.args.get("timeframe", "1D")

    ohlc = _string_ohlc(psid, market, limit=500, timeframe=timeframe)
    if not ohlc:
        return jsonify([])

    import pandas as pd
    from dumbmoney.indicators import accel

    df = pd.DataFrame(ohlc)
    df["open"] = pd.to_numeric(df["open"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])
    df["close"] = pd.to_numeric(df["close"])

    acc = accel(df)
    acc["time"] = df["time"].values
    result = []
    for _, row in acc.iterrows():
        result.append({
            "time": row["time"],
            "accel_a": round(float(row.get("accel_a", 0)), 4),
            "accel_base": round(float(row.get("accel_base", 0)), 4),
            "crossed_up": int(row.get("accel_crossed_up", 0)),
            "crossed_down": int(row.get("accel_crossed_down", 0))
        })
    return jsonify(result[-limit:])


@api_bp.route("/portfolio/string/<int:psid>/stats")
def api_portfolio_string_stats(psid):
    market = request.args.get("market", "US")
    ohlc = _string_ohlc(psid, market, limit=500)
    if not ohlc or len(ohlc) < 2:
        return jsonify({})

    import numpy as np
    closes = np.array([float(b["close"]) for b in ohlc])
    returns = np.diff(closes) / closes[:-1]
    returns = returns[~np.isnan(returns)]

    if len(returns) == 0:
        return jsonify({})

    total_days = len(closes)
    win_days = int(np.sum(returns > 0))
    loss_days = int(np.sum(returns < 0))
    win_rate = round(win_days / len(returns) * 100, 1) if len(returns) > 0 else 0

    avg_ret = float(np.mean(returns))
    std_ret = float(np.std(returns))
    sharpe = round(avg_ret / std_ret * np.sqrt(252), 3) if std_ret > 0 else 0

    neg_returns = returns[returns < 0]
    sortino = round(avg_ret / float(np.std(neg_returns)) * np.sqrt(252), 3) if len(neg_returns) > 0 and float(np.std(neg_returns)) > 0 else 0

    cum = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(cum)
    dd = (peak - cum) / peak
    max_dd = round(float(np.max(dd)) * 100, 1) if len(dd) > 0 else 0

    annual_return = round(float((closes[-1] / closes[0]) ** (252 / total_days) - 1) * 100, 1) if total_days > 1 and closes[0] > 0 else 0

    gains = returns[returns > 0]
    losses = returns[returns < 0]
    avg_win = round(float(np.mean(gains)) * 100, 2) if len(gains) > 0 else 0
    avg_loss = round(float(np.mean(losses)) * 100, 2) if len(losses) > 0 else 0

    profit_factor = round(float(np.sum(gains) / abs(np.sum(losses))), 2) if len(losses) > 0 and np.sum(losses) != 0 else 0

    max_streak_wins = 0
    max_streak_losses = 0
    streak = 0
    for r in returns:
        if r > 0:
            streak = streak + 1 if streak > 0 else 1
            max_streak_wins = max(max_streak_wins, streak)
        elif r < 0:
            streak = streak - 1 if streak < 0 else -1
            max_streak_losses = max(max_streak_losses, abs(streak))
        else:
            streak = 0

    volatility = round(std_ret * np.sqrt(252) * 100, 1)

    return jsonify({
        "total_days": total_days,
        "win_rate": win_rate,
        "avg_1d_return": round(avg_ret * 100, 3),
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "annual_return": annual_return,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "best_day": round(float(np.max(returns)) * 100, 2),
        "worst_day": round(float(np.min(returns)) * 100, 2),
        "max_streak_wins": max_streak_wins,
        "max_streak_losses": max_streak_losses,
        "volatility": volatility,
        "total_return": round(float((closes[-1] / closes[0] - 1) * 100), 2) if closes[0] > 0 else 0
    })


@api_bp.route("/portfolio/<int:pid>/detail")
def api_portfolio_full_detail(pid):
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        port = conn.execute("SELECT * FROM portfolios WHERE id=?", (pid,)).fetchone()
        if not port:
            return jsonify({"error": "Portfolio not found"}), 404
        pd_ = dict(port)

        strings = conn.execute(
            "SELECT * FROM portfolio_strings WHERE portfolio_id=? ORDER BY status='running' DESC, created_at DESC", (pid,)
        ).fetchall()
        pd_["strings"] = []
        booked_profit = 0
        running_value = 0
        running_invested = 0
        running_unrealised = 0
        running_prob_num = 0
        running_prob_den = 0
        running_chg_num = 0
        closed_count = 0
        running_count = 0
        win_count = 0
        total_return_pct_list = []

        for s in strings:
            sd = dict(s)
            syms = conn.execute(
                "SELECT symbol, qty, weight FROM portfolio_string_symbols WHERE portfolio_string_id=?",
                (s["id"],)
            ).fetchall()
            sd["num_stocks"] = len(syms)
            is_running = sd.get("status") != "closed"

            if syms:
                placeholders = ",".join(["?"] * len(syms))
                sym_list = [x["symbol"] for x in syms]
                stats_rows = conn.execute(
                    f"SELECT symbol, price, prob_up_1d, change_pct FROM stats WHERE symbol IN ({placeholders})", sym_list
                ).fetchall()
                stats_map = {r["symbol"]: dict(r) for r in stats_rows}

                sv = sum(stats_map.get(x["symbol"], {}).get("price", 0) * float(x["qty"]) for x in syms)
                sd["current_value"] = sv
                sd["total_value"] = sv

                # Day change weighted average
                total_weight = sum(stats_map.get(x["symbol"], {}).get("price", 0) * float(x["qty"]) for x in syms if stats_map.get(x["symbol"], {}).get("price", 0) > 0)
                if total_weight > 0:
                    sd["prob_1up"] = round(sum(stats_map.get(x["symbol"], {}).get("prob_up_1d", 0) * stats_map.get(x["symbol"], {}).get("price", 0) * float(x["qty"]) for x in syms if stats_map.get(x["symbol"], {}).get("price", 0) > 0) / total_weight, 4)
                    sd["change_pct"] = round(sum(stats_map.get(x["symbol"], {}).get("change_pct", 0) * stats_map.get(x["symbol"], {}).get("price", 0) * float(x["qty"]) for x in syms if stats_map.get(x["symbol"], {}).get("price", 0) > 0) / total_weight, 4)
                else:
                    sd["prob_1up"] = 0
                    sd["change_pct"] = 0

                entry_total = float(sd.get("entry_price") or 0)
                sd["entry_value"] = entry_total

                if is_running:
                    # Running string: unrealised P&L
                    sd["realised_pnl"] = 0
                    sd["unrealised_pnl"] = sv - entry_total if entry_total else 0
                    sd["pnl_pct"] = ((sv / entry_total - 1) * 100) if entry_total > 0 else 0
                    running_value += sv
                    running_invested += entry_total
                    running_unrealised += sd["unrealised_pnl"]
                    running_count += 1
                    if total_weight > 0:
                        running_prob_num += sd["prob_1up"] * sv
                        running_prob_den += sv
                        running_chg_num += sd["change_pct"] * sv
                else:
                    # Closed string: booked P&L from stored realised_pnl
                    rp_raw = sd.get("realised_pnl")
                    if rp_raw is None or str(rp_raw) in ('None', 'null', ''):
                        xp = float(sd.get("exit_price") or 0)
                        rp = xp - entry_total
                        sd["realised_pnl"] = rp
                    else:
                        rp = float(rp_raw)
                    sd["unrealised_pnl"] = 0
                    sd["pnl_pct"] = ((float(sd.get("exit_price") or 0) / entry_total - 1) * 100) if entry_total > 0 else 0
                    booked_profit += rp
                    closed_count += 1
                    if rp > 0:
                        win_count += 1
                    if entry_total > 0:
                        total_return_pct_list.append((float(sd.get("exit_price") or 0) / entry_total - 1) * 100)
            else:
                sd["total_value"] = 0
                sd["current_value"] = 0
                sd["realised_pnl"] = 0
                sd["unrealised_pnl"] = 0
                sd["entry_value"] = 0
                sd["pnl_pct"] = 0

            pd_["strings"].append(sd)

        # Broker-style totals
        total_value = running_value + booked_profit
        pd_["total_value"] = round(total_value, 2)
        pd_["booked_profit"] = round(booked_profit, 2)
        pd_["running_value"] = round(running_value, 2)
        pd_["running_invested"] = round(running_invested, 2)
        pd_["total_unrealised_pnl"] = round(running_unrealised, 2)
        pd_["total_realised_pnl"] = round(booked_profit, 2)
        pd_["total_pnl"] = round(booked_profit + running_unrealised, 2)
        pd_["num_strings"] = len(strings)
        pd_["running_strings"] = running_count
        pd_["closed_strings"] = closed_count

        # Total invested = only running strings
        pd_["total_invested"] = round(running_invested, 2)

        # Prob(Up) weighted by running string values
        pd_["prob_1up"] = round(running_prob_num / running_prob_den, 4) if running_prob_den > 0 else 0

        # Day change weighted by running string values only
        pd_["change_pct"] = round(running_chg_num / running_prob_den, 4) if running_prob_den > 0 else 0
        pd_["day_change"] = round((running_value * pd_["change_pct"] / 100) if pd_["change_pct"] else 0, 2)

        # Win rate
        pd_["win_rate"] = round((win_count / closed_count * 100), 1) if closed_count > 0 else 0

        # Trade stats
        if total_return_pct_list:
            import numpy as np
            returns_arr = np.array(total_return_pct_list)
            pd_["avg_return_pct"] = round(float(np.mean(returns_arr)), 2)
            pd_["median_return_pct"] = round(float(np.median(returns_arr)), 2)
            pd_["best_trade_pct"] = round(float(np.max(returns_arr)), 2)
            pd_["worst_trade_pct"] = round(float(np.min(returns_arr)), 2)
            # Sharpe (annualized, assuming monthly trades as rough estimate)
            if len(returns_arr) > 1 and float(np.std(returns_arr)) > 0:
                pd_["sharpe_ratio"] = round(float(np.mean(returns_arr) / np.std(returns_arr) * (12 ** 0.5)), 2)
            else:
                pd_["sharpe_ratio"] = 0
        else:
            pd_["avg_return_pct"] = 0
            pd_["median_return_pct"] = 0
            pd_["best_trade_pct"] = 0
            pd_["worst_trade_pct"] = 0
            pd_["sharpe_ratio"] = 0

        return jsonify(pd_)
    finally:
        conn.close()


@api_bp.route("/portfolio/string/validate", methods=["POST"])
def api_portfolio_string_validate():
    data = request.json
    market = data.get("market", "US")
    raw = data.get("symbols", "")

    parsed = []
    for part in raw.replace("+", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "*" in part:
            parts = part.split("*", 1)
            sym = parts[0].strip().upper()
            try:
                qty = float(parts[1].strip())
            except (ValueError, IndexError):
                qty = 0
            parsed.append({"symbol": sym, "qty": qty})
        else:
            sym = part.strip().upper()
            if sym:
                parsed.append({"symbol": sym, "qty": 0})

    if not parsed:
        return jsonify({"error": "No valid symbols parsed"}), 400

    conn = get_db(market)
    try:
        found = []
        not_found = []
        for item in parsed:
            row = conn.execute(
                "SELECT symbol, name, price, change_pct, volume, weighted_alpha FROM stats WHERE symbol=?",
                (item["symbol"],)
            ).fetchone()
            if row:
                item["name"] = row["name"] or item["symbol"]
                item["price"] = float(row["price"] or 0)
                item["change_pct"] = float(row["change_pct"] or 0)
                item["volume"] = float(row["volume"] or 0)
                item["weighted_alpha"] = float(row["weighted_alpha"] or 0)
                found.append(item)
            else:
                not_found.append(item["symbol"])

        return jsonify({"found": found, "not_found": not_found})
    finally:
        conn.close()


def api_string_ohlc(sid):
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        symbols = [r[0] for r in conn.execute(
            "SELECT symbol FROM string_symbols WHERE string_id=?", (sid,)
        ).fetchall()]
        if not symbols:
            return jsonify([])
        combined = _combined_ohlc_for_symbols(conn, symbols)
        if combined is None:
            return jsonify([])
        return jsonify(combined.to_dict("records") if not combined.empty else [])
    finally:
        conn.close()


def api_string_supertrend(sid):
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        symbols = [r[0] for r in conn.execute(
            "SELECT symbol FROM string_symbols WHERE string_id=?", (sid,)
        ).fetchall()]
        if not symbols:
            return jsonify([])
        combined = _combined_ohlc_for_symbols(conn, symbols)
        if combined is None:
            return jsonify([])
        import pandas as pd
        from dumbmoney.indicators import supertrend as compute_st
        st = compute_st(combined)
        result = []
        for i, (_, row) in enumerate(st.iterrows()):
            result.append({
                "date": combined.iloc[i]["date"] if i < len(combined) else "",
                "supertrend": round(float(row["supertrend"]), 4) if pd.notna(row["supertrend"]) else None,
                "trend": int(row["trend"]),
                "signal": int(row["signal"]),
            })
        return jsonify(result)
    finally:
        conn.close()


def api_string_accel(sid):
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        symbols = [r[0] for r in conn.execute(
            "SELECT symbol FROM string_symbols WHERE string_id=?", (sid,)
        ).fetchall()]
        combined = _combined_ohlc_for_symbols(conn, symbols)
        return jsonify(_accel_payload(combined))
    finally:
        conn.close()


@api_bp.route("/ai-discovered")
def api_ai_discovered():
    market = request.args.get("market", "US")
    from dumbmoney.ai_discovery import get_discovered_portfolios
    return jsonify(get_discovered_portfolios(market))


@api_bp.route("/ai-discovered/<int:pid>")
def api_ai_discovered_detail(pid):
    market = request.args.get("market", "US")
    from dumbmoney.ai_discovery import get_discovered_detail
    return jsonify(get_discovered_detail(pid, market))


@api_bp.route("/ai-discovered/run", methods=["POST"])
def api_ai_run():
    market = request.json.get("market", "US") if request.is_json else "US"
    from dumbmoney.ai_discovery import run_ai_discovery
    success = run_ai_discovery(market)
    return jsonify({"started": success})


@api_bp.route("/ai-discovered/kill", methods=["POST"])
def api_ai_kill():
    from dumbmoney.ai_discovery import kill_ai_discovery
    kill_ai_discovery()
    return jsonify({"killed": True})


@api_bp.route("/ai-discovered/status")
def api_ai_status():
    from dumbmoney.ai_discovery import get_ai_status
    return jsonify(get_ai_status())


@api_bp.route("/trigger-ai-analysis", methods=["POST"])
def api_trigger_ai():
    market = request.json.get("market", "US") if request.is_json else "US"
    from dumbmoney.engine import vectorized_stats_pass
    n = vectorized_stats_pass(market)
    return jsonify({"updated": n})


@api_bp.route("/paper/strategies")
def api_paper_strategies():
    market = request.args.get("market", "US")
    from dumbmoney.paper_trading import get_paper_strategies
    return jsonify(get_paper_strategies(market))


@api_bp.route("/paper/strategies", methods=["POST"])
def api_create_paper_strategy():
    data = request.json
    from dumbmoney.paper_trading import create_paper_strategy
    sid = create_paper_strategy(
        data["name"], data["rules"], data.get("num_stocks", 10),
        data.get("allocation_type", "equal"), data.get("rebalance_time", "09:35"),
        data.get("market", "US")
    )
    return jsonify({"id": sid})


@api_bp.route("/paper/strategies/<int:sid>/activate", methods=["POST"])
def api_activate_paper(sid):
    market = request.json.get("market", "US") if request.is_json else "US"
    from dumbmoney.paper_trading import activate_strategy
    result = activate_strategy(sid, market)
    return jsonify(result)


@api_bp.route("/paper/strategies/<int:sid>/pause", methods=["POST"])
def api_pause_paper(sid):
    market = request.json.get("market", "US") if request.is_json else "US"
    from dumbmoney.paper_trading import pause_strategy
    pause_strategy(sid, market)
    return jsonify({"paused": True})


@api_bp.route("/paper/positions")
def api_paper_positions():
    from dumbmoney.paper_trading import get_paper_positions
    return jsonify(get_paper_positions())


@api_bp.route("/paper/trades")
def api_paper_trades():
    market = request.args.get("market", "US")
    strategy_id = request.args.get("strategy_id")
    from dumbmoney.paper_trading import get_paper_trades
    return jsonify(get_paper_trades(strategy_id, market))


@api_bp.route("/basket-screener/columns")
def api_basket_screener_columns():
    from dumbmoney.basket_screener import STRING_COLUMN_REFERENCE
    return jsonify({"columns": STRING_COLUMN_REFERENCE})


@api_bp.route("/basket-screener/detail/<string_id>")
def api_basket_screener_detail(string_id):
    market = request.args.get("market", "US")
    from dumbmoney.basket_screener import get_string_detail
    detail = get_string_detail(string_id, market)
    if detail is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(detail)


def _basket_constituents(string_id, market):
    conn = get_db(market)
    try:
        rows = conn.execute(
            "SELECT symbol, weight FROM string_constituents WHERE string_id=?",
            (string_id,)).fetchall()
        return [(r[0], r[1]) for r in rows], conn
    except Exception:
        return [], conn


@api_bp.route("/basket-screener/<string_id>/ohlc")
def api_basket_ohlc(string_id):
    market = request.args.get("market", "US")
    limit = int(request.args.get("limit", 200))
    timeframe = request.args.get("timeframe", "1D")
    cons, conn = _basket_constituents(string_id, market)
    try:
        if not cons:
            return jsonify([])
        symbols = [c[0] for c in cons]
        raw_weights = {c[0]: c[1] for c in cons}
        all_data = {}
        for sym in symbols:
            rows = conn.execute(
                "SELECT date, open, high, low, close, volume FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date",
                (sym,)
            ).fetchall()
            if rows:
                all_data[sym] = pd.DataFrame([dict(r) for r in rows])
        if not all_data:
            return jsonify([])
        all_dates = set()
        for df in all_data.values():
            if "date" in df.columns:
                all_dates.update(df["date"].tolist())
            else:
                all_dates.update(df.index.tolist())
        all_dates = sorted(all_dates)
        basket_raw = pd.DataFrame({"date": all_dates}).set_index("date")
        for sym, df in all_data.items():
            if "date" in df.columns:
                df = df.set_index("date")
            w = raw_weights.get(sym, 0)
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    if col not in basket_raw.columns:
                        basket_raw[col] = 0.0
                    basket_raw[col] += df[col].reindex(basket_raw.index).ffill().fillna(0) * w
        basket_raw["volume"] = 0
        for sym, df in all_data.items():
            if "date" in df.columns:
                df = df.set_index("date")
            if "volume" in df.columns:
                basket_raw["volume"] += df["volume"].reindex(basket_raw.index).fillna(0).astype(int)
        basket_raw = basket_raw.reset_index()
        import numpy as np
        close_arr = basket_raw["close"].values.astype(np.float64)
        basket_min = np.nanmin(close_arr)
        basket_range = np.nanmax(close_arr) - basket_min
        if basket_range == 0:
            basket_range = 1.0
        norm = ((close_arr - basket_min) / basket_range) * 900.0 + 100.0
        for col in ["open", "high", "low", "close"]:
            raw = basket_raw[col].values.astype(np.float64)
            basket_raw[col] = ((raw - basket_min) / basket_range) * 900.0 + 100.0
        basket_raw = _resample_ohlc(basket_raw, timeframe)
        basket_raw = basket_raw.tail(limit)
        return jsonify([dict(r) for _, r in basket_raw.iterrows()])
    finally:
        conn.close()


@api_bp.route("/basket-screener/<string_id>/supertrend")
def api_basket_supertrend(string_id):
    market = request.args.get("market", "US")
    period = int(request.args.get("period", 14))
    multiplier = float(request.args.get("multiplier", 2.0))
    timeframe = request.args.get("timeframe", "1D")
    cons, conn = _basket_constituents(string_id, market)
    try:
        if not cons:
            return jsonify([])
        symbols = [c[0] for c in cons]
        raw_weights = {c[0]: c[1] for c in cons}
        all_data = {}
        for sym in symbols:
            rows = conn.execute(
                "SELECT date, open, high, low, close FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date",
                (sym,)
            ).fetchall()
            if rows:
                all_data[sym] = pd.DataFrame([dict(r) for r in rows])
        if not all_data:
            return jsonify([])
        all_dates = set()
        for df in all_data.values():
            if "date" in df.columns:
                all_dates.update(df["date"].tolist())
            else:
                all_dates.update(df.index.tolist())
        all_dates = sorted(all_dates)
        basket_raw = pd.DataFrame({"date": all_dates}).set_index("date")
        for sym, df in all_data.items():
            if "date" in df.columns:
                df = df.set_index("date")
            w = raw_weights.get(sym, 0)
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    if col not in basket_raw.columns:
                        basket_raw[col] = 0.0
                    basket_raw[col] += df[col].reindex(basket_raw.index).ffill().fillna(0) * w
        basket_raw = basket_raw.reset_index()
        import numpy as np
        close_arr = basket_raw["close"].values.astype(np.float64)
        basket_min = np.nanmin(close_arr)
        basket_range = np.nanmax(close_arr) - basket_min
        if basket_range == 0:
            basket_range = 1.0
        for col in ["open", "high", "low", "close"]:
            raw = basket_raw[col].values.astype(np.float64)
            basket_raw[col] = ((raw - basket_min) / basket_range) * 900.0 + 100.0
        basket_raw = _resample_ohlc(basket_raw, timeframe)
        from dumbmoney.indicators import supertrend as compute_st
        st = compute_st(basket_raw, period=period, multiplier=multiplier)
        result = []
        for i, (_, row) in enumerate(st.iterrows()):
            result.append({
                "date": basket_raw.iloc[i]["date"] if i < len(basket_raw) else "",
                "supertrend": round(float(row["supertrend"]), 4) if pd.notna(row["supertrend"]) else None,
                "trend": int(row["trend"]),
                "signal": int(row["signal"]),
                "stop": round(float(row["stop"]), 4) if pd.notna(row["stop"]) else None,
                "atr_value": round(float(row["atr_value"]), 4) if pd.notna(row["atr_value"]) else None,
            })
        return jsonify(result)
    finally:
        conn.close()


@api_bp.route("/basket-screener/<string_id>/accel")
def api_basket_accel(string_id):
    market = request.args.get("market", "US")
    timeframe = request.args.get("timeframe", "1D")
    cons, conn = _basket_constituents(string_id, market)
    try:
        if not cons:
            return jsonify([])
        symbols = [c[0] for c in cons]
        raw_weights = {c[0]: c[1] for c in cons}
        all_data = {}
        for sym in symbols:
            rows = conn.execute(
                "SELECT date, open, high, low, close FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date",
                (sym,)
            ).fetchall()
            if rows:
                all_data[sym] = pd.DataFrame([dict(r) for r in rows])
        if not all_data:
            return jsonify([])
        all_dates = set()
        for df in all_data.values():
            if "date" in df.columns:
                all_dates.update(df["date"].tolist())
            else:
                all_dates.update(df.index.tolist())
        all_dates = sorted(all_dates)
        basket_raw = pd.DataFrame({"date": all_dates}).set_index("date")
        for sym, df in all_data.items():
            if "date" in df.columns:
                df = df.set_index("date")
            w = raw_weights.get(sym, 0)
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    if col not in basket_raw.columns:
                        basket_raw[col] = 0.0
                    basket_raw[col] += df[col].reindex(basket_raw.index).ffill().fillna(0) * w
        basket_raw = basket_raw.reset_index()
        import numpy as np
        close_arr = basket_raw["close"].values.astype(np.float64)
        basket_min = np.nanmin(close_arr)
        basket_range = np.nanmax(close_arr) - basket_min
        if basket_range == 0:
            basket_range = 1.0
        for col in ["open", "high", "low", "close"]:
            raw = basket_raw[col].values.astype(np.float64)
            basket_raw[col] = ((raw - basket_min) / basket_range) * 900.0 + 100.0
        basket_raw = _resample_ohlc(basket_raw, timeframe)
        return jsonify(_accel_payload(basket_raw))
    finally:
        conn.close()


@api_bp.route("/basket-screener/<string_id>/stats")
def api_basket_stats(string_id):
    market = request.args.get("market", "US")
    cons, conn = _basket_constituents(string_id, market)
    try:
        if not cons:
            return jsonify({})
        symbols = [c[0] for c in cons]
        weights = {c[0]: c[1] for c in cons}
        wsum = sum(weights.values()) or 1.0
        weights = {k: v / wsum for k, v in weights.items()}
        ohlc_df = _combined_ohlc_for_symbols(conn, symbols, weights=weights)
        if ohlc_df is None or ohlc_df.empty:
            return jsonify({})
        import pandas as pd
        import numpy as np
        c = ohlc_df["close"].astype(float)
        returns = c.pct_change().dropna()
        if len(returns) < 2:
            return jsonify({})
        wins = returns[returns > 0]
        losses = returns[returns < 0]
        win_rate = len(wins) / len(returns) * 100
        avg_return = float(returns.mean()) * 100
        avg_win = float(wins.mean()) * 100 if len(wins) > 0 else 0
        avg_loss = float(losses.mean()) * 100 if len(losses) > 0 else 0
        profit_factor = abs(float(wins.sum()) / float(losses.sum())) if len(losses) > 0 and losses.sum() != 0 else 0
        sharpe = float(returns.mean() / (returns.std() + 1e-10)) * np.sqrt(252)
        sortino_denom = returns[returns < 0].std()
        sortino = float(returns.mean() / (sortino_denom + 1e-10)) * np.sqrt(252) if sortino_denom > 0 else 0
        cum = (1 + returns).cumprod()
        running_max = cum.cummax()
        drawdown = np.where(running_max > 0, (cum - running_max) / running_max, 0)
        max_dd = float(np.min(drawdown)) * 100
        best = float(returns.max()) * 100
        worst = float(returns.min()) * 100
        streak_w, streak_l = 0, 0
        max_streak_w, max_streak_l = 0, 0
        for r in returns:
            if r > 0:
                streak_w += 1; streak_l = 0
                max_streak_w = max(max_streak_w, streak_w)
            elif r < 0:
                streak_l += 1; streak_w = 0
                max_streak_l = max(max_streak_l, streak_l)
            else:
                streak_w = 0; streak_l = 0
        total_days = len(returns)
        cum_total = float((1 + returns).prod())
        if cum_total > 0:
            ann_ret = float((cum_total ** (252 / max(total_days, 1)) - 1)) * 100
        else:
            ann_ret = -100.0
        calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0

        volatility = float(returns.std()) * np.sqrt(252) * 100

        def _trend_view(window):
            if len(returns) < window:
                return {"return": 0, "win_rate": 50, "signal": "neutral", "strength": 0}
            w = returns.tail(window)
            cum_ret = float(((1 + w).prod() - 1) * 100)
            wr = float((w > 0).mean() * 100)
            avg_r = float(w.mean()) * 100
            vol = float(w.std()) * np.sqrt(252) * 100 if len(w) > 1 else 1
            score = 0
            if cum_ret > 2: score += 1
            elif cum_ret < -2: score -= 1
            if wr > 55: score += 1
            elif wr < 45: score -= 1
            if avg_r > 0.1: score += 1
            elif avg_r < -0.1: score -= 1
            signal = "BUY" if score >= 2 else ("SELL" if score <= -2 else "HOLD")
            return {"return": round(cum_ret, 2), "win_rate": round(wr, 1), "signal": signal, "strength": abs(score)}

        short = _trend_view(5)
        medium = _trend_view(20)
        long_v = _trend_view(60)

        monthly = {}
        if "date" in ohlc_df.columns:
            ohlc_df["date"] = pd.to_datetime(ohlc_df["date"])
            ohlc_df["month"] = ohlc_df["date"].dt.to_period("M")
            monthly_rets = ohlc_df.groupby("month")["close"].apply(lambda x: float((x.iloc[-1]/x.iloc[0]-1)*100) if len(x)>1 else 0)
            best_month = monthly_rets.idxmax()
            worst_month = monthly_rets.idxmin()
            pos_months = int((monthly_rets > 0).sum())
            total_months = len(monthly_rets)
        else:
            best_month = worst_month = None
            pos_months = total_months = 0

        insights = []
        if win_rate > 55: insights.append(f"Strong win rate of {win_rate:.1f}% — consistent edge.")
        elif win_rate < 45: insights.append(f"Win rate {win_rate:.1f}% below 50 — needs strong winners.")
        if sharpe > 1.5: insights.append(f"Excellent risk-adjusted return (Sharpe {sharpe:.2f}).")
        elif sharpe < 0: insights.append(f"Negative Sharpe ({sharpe:.2f}) — risk exceeds return.")
        if profit_factor > 1.5: insights.append(f"Profit factor {profit_factor:.2f} — wins outsize losses.")
        if max_dd < -20: insights.append(f"Max drawdown {max_dd:.1f}% — high risk profile.")
        if volatility > 40: insights.append(f"High annualized volatility ({volatility:.0f}%) — volatile basket.")
        elif volatility < 15: insights.append(f"Low volatility ({volatility:.0f}%) — stable basket.")
        if max_streak_w >= 5: insights.append(f"Best winning streak: {max_streak_w} consecutive days.")
        if short["signal"] == "BUY" and medium["signal"] == "BUY":
            insights.append("Aligned bullish across short and medium term.")
        if short["signal"] == "SELL" and medium["signal"] == "SELL":
            insights.append("Aligned bearish — caution advised.")

        return jsonify({
            "total_days": total_days,
            "win_rate": round(win_rate, 2),
            "avg_return": round(avg_return, 4),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "profit_factor": round(profit_factor, 2),
            "sharpe": round(sharpe, 2),
            "sortino": round(sortino, 2),
            "max_drawdown": round(max_dd, 2),
            "best_day": round(best, 2),
            "worst_day": round(worst, 2),
            "max_streak_wins": max_streak_w,
            "max_streak_losses": max_streak_l,
            "annual_return": round(ann_ret, 2),
            "calmar": round(calmar, 2),
            "volatility": round(volatility, 2),
            "short_term": short,
            "medium_term": medium,
            "long_term": long_v,
            "best_month": str(best_month) if best_month else None,
            "worst_month": str(worst_month) if worst_month else None,
            "positive_months": pos_months,
            "total_months": total_months,
            "insights": insights,
        })
    finally:
        conn.close()


import threading
_BUILD_PROGRESS = {}
_BUILD_LOCK = threading.Lock()

def _update_progress(market, pct, stage, detail="", elapsed=0, total_dates=0, done_dates=0, rows=0):
    _BUILD_PROGRESS[market] = {
        "pct": pct, "stage": stage, "detail": detail,
        "elapsed": round(elapsed, 1), "total_dates": total_dates,
        "done_dates": done_dates, "rows": rows,
        "eta": round((elapsed / max(done_dates, 1)) * (total_dates - done_dates), 1) if done_dates > 0 and total_dates > 0 else 0,
    }


@api_bp.route("/basket-screener/rebalance")
def api_basket_rebalance():
    market = request.args.get("market", "US")
    string_id = request.args.get("string_id", "")
    if not string_id:
        return jsonify({"error": "string_id required"}), 400

    conn = get_db(market)
    try:
        cons = conn.execute(
            "SELECT sc.symbol, sc.weight FROM string_constituents sc "
            "WHERE sc.string_id=?", (string_id,)
        ).fetchall()
        if not cons:
            return jsonify({"error": "String not found"}), 404

        symbols = [c[0] for c in cons]
        total_weight = sum(c[1] for c in cons)
        target_pct = {c[0]: (c[1] / total_weight * 100) if total_weight > 0 else 0 for c in cons}

        placeholders = ",".join("?" * len(symbols))
        stats_rows = conn.execute(
            f"SELECT symbol, price, change_pct, weighted_alpha, atr_signal, "
            f"prob_up_1d, atr_crossed_above, atr_crossed_below, accel_signal, "
            f"accel_crossed_up, accel_crossed_down FROM stats "
            f"WHERE symbol IN ({placeholders})", symbols
        ).fetchall()
        current = {r[0]: dict(r) for r in stats_rows}

        recommendations = []
        for sym, weight in cons:
            cur = current.get(sym, {})
            price = float(cur.get("price") or 0)
            chg = float(cur.get("change_pct") or 0)
            wa = float(cur.get("weighted_alpha") or 0)
            atr = int(cur.get("atr_signal") or 0)
            accel = int(cur.get("accel_signal") or 0)
            prob = float(cur.get("prob_up_1d") or 50)
            cross_up = bool(cur.get("atr_crossed_above"))
            cross_down = bool(cur.get("atr_crossed_below"))
            accel_up = bool(cur.get("accel_crossed_up"))
            accel_down = bool(cur.get("accel_crossed_down"))

            current_pct = target_pct.get(sym, 0)
            action = "HOLD"
            urgency = 0
            reasons = []

            if cross_down or accel_down:
                action = "REDUCE"
                urgency = 3
                reasons.append("SuperTrend/Accel cross down")
            elif atr == -1 and wa < 0:
                action = "REDUCE"
                urgency = 2
                reasons.append("Bearish trend + negative WA")
            elif prob < 40:
                action = "REDUCE"
                urgency = 1
                reasons.append(f"Low probability ({prob:.0f}%)")
            elif cross_up and accel_up:
                action = "ADD"
                urgency = 3
                reasons.append("Both SuperTrend & Accel crossed up")
            elif atr == 1 and accel == 1 and wa > 20:
                action = "ADD"
                urgency = 2
                reasons.append("Strong uptrend + high WA")
            elif prob > 60 and wa > 10:
                action = "ADD"
                urgency = 1
                reasons.append(f"High probability ({prob:.0f}%) + positive WA")
            else:
                action = "HOLD"
                reasons.append("No strong signal")

            recommendations.append({
                "symbol": sym, "weight": round(weight, 4),
                "current_pct": round(current_pct, 2),
                "price": price, "change_pct": round(chg, 2),
                "weighted_alpha": round(wa, 2),
                "atr_signal": atr, "accel_signal": accel,
                "prob_up_1d": round(prob, 2),
                "action": action, "urgency": urgency,
                "reasons": reasons,
            })

        recommendations.sort(key=lambda x: x["urgency"], reverse=True)
        adds = sum(1 for r in recommendations if r["action"] == "ADD")
        reduces = sum(1 for r in recommendations if r["action"] == "REDUCE")
        holds = sum(1 for r in recommendations if r["action"] == "HOLD")

        return jsonify({
            "string_id": string_id, "market": market,
            "recommendations": recommendations,
            "summary": {"adds": adds, "reduces": reduces, "holds": holds,
                        "total_stocks": len(recommendations)},
        })
    finally:
        conn.close()


# Page routes for the basket string screener (parallel to stock screener).

app.add_url_rule("/long-short-screener/", "long_short_screener_list",
                 lambda: render_template("basket_screener.html", market="US", long_short=True))
app.add_url_rule("/long-short-screener/string/<string_id>", "long_short_string_detail",
                 lambda string_id: render_template("string_detail_basket.html", string_id=string_id, market="US", long_short=True))


@api_bp.route("/long-short-screener")
def api_long_short_screener():
    market = request.args.get("market", "US")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    sort = request.args.get("sort", "weighted_alpha")
    sort_dir = request.args.get("sort_dir") or request.args.get("order", "desc")
    search = request.args.get("search", "")
    exchange = request.args.get("exchange", "")
    asset_type = request.args.get("asset_type", "")
    date_cutoff = request.args.get("date_cutoff", "")
    from dumbmoney.basket_screener import get_string_screener
    result = get_string_screener(market, page, per_page, sort, sort_dir, search, exchange,
                                 asset_type, date_cutoff, request.args, string_id_like="LS%")
    return jsonify(result)


@api_bp.route("/long-short-screener/generate", methods=["POST"])
def api_long_short_generate():
    """Full LS pipeline in a background thread: generate strings -> pivot cache ->
    current metrics -> historical rows. Poll /api/long-short-screener/progress."""
    data = request.json or {}
    market = data.get("market", "US")
    n = int(data.get("n", 25000))
    with _BUILD_LOCK:
        if _BUILD_PROGRESS.get(market, {}).get("stage") in ("universe", "cache", "metrics", "historical"):
            return jsonify({"error": "Already running"}), 409

    def _run():
        import time as _time
        t0 = _time.time()
        try:
            _update_progress(market, 0, "universe", "Generating long+short strings...")
            from dumbmoney.basket_screener import (
                generate_long_short_strings, compute_current_metrics,
                update_historical_string_screener, build_close_pivot_cache)
            count = generate_long_short_strings(market, n=n)
            _update_progress(market, 3, "cache", f"Generated {count} strings. Building close pivot cache...", elapsed=_time.time()-t0)
            build_close_pivot_cache(market)
            _update_progress(market, 8, "metrics", "Cache built. Computing current metrics...", elapsed=_time.time()-t0)
            compute_current_metrics(market)
            _update_progress(market, 12, "historical", "Metrics done. Building LS history (gross-exposure values)...", elapsed=_time.time()-t0)

            def _hist_progress(pct, detail):
                _update_progress(market, 10 + pct * 0.9, "historical", detail, elapsed=_time.time()-t0)

            update_historical_string_screener(market, force_rebuild=True,
                                              progress_callback=_hist_progress, string_id_like="LS%")
            _update_progress(market, 100, "done", f"Complete! {count} LS strings built.", elapsed=_time.time()-t0)
        except Exception as e:
            _update_progress(market, 0, "error", str(e), elapsed=_time.time()-t0)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"started": True, "market": market})


@api_bp.route("/long-short-screener/progress")
def api_long_short_progress():
    market = request.args.get("market", "US")
    return jsonify(_BUILD_PROGRESS.get(market, {"pct": 0, "stage": "idle", "detail": ""}))


# ── Leverage ETF Screener ─────────────────────────────────────────────────────

_LEV_BUILD_PROGRESS = {}
_LEV_BUILD_LOCK = threading.Lock()

def _update_lev_progress(market, pct, stage, detail="", elapsed=0, total_dates=0, done_dates=0, rows=0):
    _LEV_BUILD_PROGRESS[market] = {
        "pct": round(pct, 1), "stage": stage, "detail": detail,
        "elapsed": round(elapsed, 1), "total_dates": total_dates,
        "done_dates": done_dates, "rows": rows,
    }


@api_bp.route("/leverage-etf-screener")
def api_lev_screener():
    market = request.args.get("market", "US")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    sort = request.args.get("sort", "weighted_alpha")
    sort_dir = request.args.get("sort_dir") or request.args.get("order", "desc")
    search = request.args.get("search", "")
    date_cutoff = request.args.get("date_cutoff", "")
    from dumbmoney.leverage_etf_screener import get_lev_screener
    return jsonify(get_lev_screener(market, page, per_page, sort, sort_dir, search, date_cutoff, request.args))


@api_bp.route("/leverage-etf-screener/columns")
def api_lev_screener_columns():
    from dumbmoney.basket_screener import STRING_COLUMN_REFERENCE
    return jsonify({"columns": STRING_COLUMN_REFERENCE})


@api_bp.route("/leverage-etf-screener/detail/<string_id>")
def api_lev_detail(string_id):
    market = request.args.get("market", "US")
    from dumbmoney.leverage_etf_screener import get_lev_detail
    return jsonify(get_lev_detail(string_id, market))


@api_bp.route("/leverage-etf-screener/<string_id>/ohlc")
def api_lev_ohlc(string_id):
    market = request.args.get("market", "US")
    limit = int(request.args.get("limit", 500))
    timeframe = request.args.get("timeframe", "1Day")
    from dumbmoney.basket_screener import _load_composition, _load_close_pivot, _load_ohlc_pivots, _gather_einsum
    sids, sym_list, indices, weights = _load_composition(market, string_ids=[string_id])
    if not sids:
        return jsonify({"error": "String not found"}), 404
    _, dates, close = _load_close_pivot(market, sym_list)
    high, low, open_p = _load_ohlc_pivots(market, sym_list)
    if high is None:
        return jsonify({"error": "OHLC cache missing"}), 404
    V = _gather_einsum(close, indices, weights)
    H = _gather_einsum(high, indices, weights)
    L = _gather_einsum(low, indices, weights)
    O = _gather_einsum(open_p, indices, weights)
    n_dates = min(limit, len(dates))
    d = dates[-n_dates:]
    return jsonify({
        "dates": list(d),
        "open": [round(float(O[0, -n_dates + i]), 4) for i in range(n_dates)],
        "high": [round(float(H[0, -n_dates + i]), 4) for i in range(n_dates)],
        "low": [round(float(L[0, -n_dates + i]), 4) for i in range(n_dates)],
        "close": [round(float(V[0, -n_dates + i]), 4) for i in range(n_dates)],
    })


@api_bp.route("/leverage-etf-screener/<string_id>/supertrend")
def api_lev_supertrend(string_id):
    market = request.args.get("market", "US")
    period = int(request.args.get("period", 14))
    multiplier = float(request.args.get("multiplier", 2.0))
    limit = int(request.args.get("limit", 500))
    from dumbmoney.basket_screener import (
        _load_composition, _load_close_pivot, _load_ohlc_pivots,
        _gather_einsum, _compute_basket_ohlc, _compute_basket_indicators
    )
    sids, sym_list, indices, weights = _load_composition(market, string_ids=[string_id])
    if not sids:
        return jsonify({"error": "String not found"}), 404
    _, dates, close = _load_close_pivot(market, sym_list)
    high, low, open_p = _load_ohlc_pivots(market, sym_list)
    if high is None:
        return jsonify({"error": "OHLC cache missing"}), 404
    basket_ohlc = _compute_basket_ohlc(close, high, low, open_p, indices, weights)
    ind = _compute_basket_indicators(basket_ohlc, period=period, multiplier=multiplier)
    n_dates = min(limit, len(dates))
    d = dates[-n_dates:]
    return jsonify({
        "dates": list(d),
        "atr_signal": [int(ind["atr_signal"][0, -n_dates + i]) for i in range(n_dates)],
        "atr_stop": [round(float(ind["atr_stop"][0, -n_dates + i]), 4) for i in range(n_dates)],
        "atr_value": [round(float(ind["atr_value"][0, -n_dates + i]), 4) for i in range(n_dates)],
        "atr_crossed_above": [int(ind["atr_crossed_above"][0, -n_dates + i]) for i in range(n_dates)],
        "atr_crossed_below": [int(ind["atr_crossed_below"][0, -n_dates + i]) for i in range(n_dates)],
    })


@api_bp.route("/leverage-etf-screener/<string_id>/accel")
def api_lev_accel(string_id):
    market = request.args.get("market", "US")
    limit = int(request.args.get("limit", 500))
    from dumbmoney.basket_screener import (
        _load_composition, _load_close_pivot, _load_ohlc_pivots,
        _gather_einsum, _compute_basket_ohlc, _compute_basket_indicators
    )
    sids, sym_list, indices, weights = _load_composition(market, string_ids=[string_id])
    if not sids:
        return jsonify({"error": "String not found"}), 404
    _, dates, close = _load_close_pivot(market, sym_list)
    high, low, open_p = _load_ohlc_pivots(market, sym_list)
    if high is None:
        return jsonify({"error": "OHLC cache missing"}), 404
    basket_ohlc = _compute_basket_ohlc(close, high, low, open_p, indices, weights)
    ind = _compute_basket_indicators(basket_ohlc)
    n_dates = min(limit, len(dates))
    d = dates[-n_dates:]
    return jsonify({
        "dates": list(d),
        "accel_a": [round(float(ind["accel_a"][0, -n_dates + i]), 6) for i in range(n_dates)],
        "accel_base": [round(float(ind["accel_base"][0, -n_dates + i]), 6) for i in range(n_dates)],
        "accel_signal": [int(ind["accel_signal"][0, -n_dates + i]) for i in range(n_dates)],
    })


@api_bp.route("/leverage-etf-screener/<string_id>/stats")
def api_lev_stats(string_id):
    market = request.args.get("market", "US")
    conn = get_db(market)
    try:
        rows = conn.execute(
            "SELECT date, price, change_pct, next_day_return FROM historical_string_screener "
            "WHERE string_id=? ORDER BY date", (string_id,)).fetchall()
        if not rows:
            return jsonify({})
        prices = [r[1] for r in rows if r[1]]
        returns = [r[3] for r in rows if r[3] is not None]
        win_rate = sum(1 for r in returns if r > 0) / len(returns) * 100 if returns else 0
        avg_ret = sum(returns) / len(returns) if returns else 0
        import numpy as np
        std_ret = float(np.std(returns)) if returns else 0
        sharpe = (avg_ret / std_ret * (252 ** 0.5)) if std_ret > 0 else 0
        total_return = ((prices[-1] / prices[0] - 1) * 100) if prices and prices[0] > 0 else 0
        peak = prices[0] if prices else 0
        max_dd = 0
        for p in prices:
            if p > peak:
                peak = p
            dd = (peak - p) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        return jsonify({
            "total_entries": len(returns),
            "win_rate": round(win_rate, 2),
            "avg_1d_return": round(avg_ret, 4),
            "sharpe_1d": round(sharpe, 2),
            "total_return": round(total_return, 2),
            "max_drawdown": round(max_dd, 2),
        })
    finally:
        conn.close()


@api_bp.route("/leverage-etf-screener/progress")
def api_lev_progress():
    market = request.args.get("market", "US")
    return jsonify(_LEV_BUILD_PROGRESS.get(market, {"pct": 0, "stage": "idle", "detail": ""}))


@api_bp.route("/leverage-etf-screener/generate", methods=["POST"])
def api_lev_generate():
    data = request.json or {}
    market = data.get("market", "US")
    with _LEV_BUILD_LOCK:
        if _LEV_BUILD_PROGRESS.get(market, {}).get("stage") in ("universe", "cache", "metrics", "historical"):
            return jsonify({"error": "Already running"}), 409

    def _run():
        import time as _time
        t0 = _time.time()
        try:
            _update_lev_progress(market, 0, "universe", "Generating leveraged ETF universe...")
            from dumbmoney.leverage_etf_screener import (
                generate_leveraged_etf_universe, compute_leveraged_etf_current_metrics,
                update_leveraged_etf_historical)
            from dumbmoney.basket_screener import build_close_pivot_cache
            n = generate_leveraged_etf_universe(market, n=25000, force=True)
            _update_lev_progress(market, 3, "cache", f"Universe ready: {n} strings. Building cache...", elapsed=_time.time()-t0)
            build_close_pivot_cache(market)
            _update_lev_progress(market, 8, "metrics", "Cache built. Computing metrics...", elapsed=_time.time()-t0)
            compute_leveraged_etf_current_metrics(market)
            _update_lev_progress(market, 12, "historical", "Metrics done. Building historical...", elapsed=_time.time()-t0)

            def _hist_progress(pct, detail):
                elapsed = _time.time() - t0
                done_d, total_d = 0, 0
                if "dates" in detail:
                    try:
                        part = detail.split(":")[-1].strip().split(" ")[0]
                        done_d, total_d = [int(x) for x in part.split("/")]
                    except Exception:
                        pass
                _update_lev_progress(market, 10 + pct * 0.9, "historical", detail,
                                     elapsed=elapsed, total_dates=total_d, done_dates=done_d)

            update_leveraged_etf_historical(market, force_rebuild=True, progress_callback=_hist_progress)
            _update_lev_progress(market, 100, "done", f"Complete! {n} LEV strings built.", elapsed=_time.time()-t0)
        except Exception as e:
            _update_lev_progress(market, 0, "error", str(e), elapsed=_time.time()-t0)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"started": True, "market": market})


# Page routes for leverage ETF screener
app.add_url_rule("/leverage-etf-screener/", "lev_screener_list",
                 lambda: render_template("leverage_etf_screener.html", market="US"))
app.add_url_rule("/leverage-etf-screener/string/<string_id>", "lev_string_detail",
                 lambda string_id: render_template("lev_string_detail.html", string_id=string_id, market="US"))


app.register_blueprint(screener_bp)
app.register_blueprint(stock_bp)
app.register_blueprint(portfolio_bp)
app.register_blueprint(string_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(paper_bp)
app.register_blueprint(api_bp, url_prefix="/api")

# Intraday Agent Backtester (separate module)
from intraday_backtest.routes import bp as intraday_bp
app.register_blueprint(intraday_bp)

app.add_url_rule("/intraday-backtest/", "intraday_backtest_page",
                 lambda: render_template("intraday_backtest.html", market="US", other_market="INDIA"),
                 methods=["GET"])


def create_app():
    init_all_dbs()
    for db_path in DB_PATHS.values():
        ensure_schema(db_path)
        migrate_nulls(db_path)
    from dumbmoney.refresh import reset_stale_status
    reset_stale_status()
    # Sync crypto products if not already present
    try:
        from dumbmoney.db import get_db
        from dumbmoney.data_crypto import fetch_products, get_all_symbols
        conn = get_db("CRYPTO")
        count = conn.execute("SELECT COUNT(*) FROM crypto_products").fetchone()[0]
        if count == 0:
            fetch_products()
        conn.close()
    except Exception as e:
        logger.warning(f"Crypto product sync failed at startup: {e}")
    # Start WebSocket for live tickers
    try:
        from dumbmoney.crypto_ws import start as start_crypto_ws
        import threading
        threading.Thread(target=start_crypto_ws, daemon=True).start()
    except Exception as e:
        logger.warning(f"Crypto WebSocket failed to start: {e}")
    # Pre-compute crypto stats in background on startup
    try:
        import threading
        def _warm_crypto_stats():
            try:
                from dumbmoney.engine import compute_crypto_stats_batch
                compute_crypto_stats_batch()
            except Exception as e:
                logger.warning(f"Crypto stats batch compute failed: {e}")
            try:
                from dumbmoney.engine import update_crypto_historical_screener
                update_crypto_historical_screener()
            except Exception as e:
                logger.warning(f"Crypto historical screener build failed: {e}")
        threading.Thread(target=_warm_crypto_stats, daemon=True).start()
    except Exception as e:
        logger.warning(f"Crypto stats warmup failed: {e}")
    return app


if __name__ == "__main__":
    create_app()
    app.run(host="0.0.0.0", port=8474, debug=False)
