"""Delta Exchange WebSocket manager.

Subscribes to public ticker + candlestick channels for live market data,
and optional private channels (positions, orders) when API keys are set.
Stores latest ticker state in module-level dict for API endpoints to consume.
"""
import json
import logging
import threading
import time

import websocket

from dumbmoney.config import (
    DELTA_API_KEY, DELTA_API_SECRET,
    DELTA_PUBLIC_WS_URL, DELTA_WS_URL,
)

logger = logging.getLogger(__name__)

# Thread-safe live ticker cache
_live_tickers = {}
_lock = threading.Lock()

# WebSocket instances
_pub_ws = None
_priv_ws = None
_pub_running = False
_priv_running = False


def get_live_ticker(symbol):
    """Get latest cached ticker for a symbol."""
    with _lock:
        return _live_tickers.get(symbol, {})


def get_all_live_tickers():
    """Get all cached tickers."""
    with _lock:
        return dict(_live_tickers)


def _on_public_message(ws, message):
    """Parse and cache ticker/candlestick messages from public WS."""
    global _live_tickers
    try:
        data = json.loads(message)
        msg_type = data.get("type", "")
        if msg_type == "ticker" and "v" in data:
            payload = data["v"]
            with _lock:
                for item in payload if isinstance(payload, list) else [payload]:
                    sym = item.get("symbol", "")
                    if sym:
                        _live_tickers[sym] = {
                            "symbol": sym,
                            "close": float(item.get("close", 0)),
                            "open": float(item.get("open", 0)),
                            "high": float(item.get("high", 0)),
                            "low": float(item.get("low", 0)),
                            "volume": float(item.get("volume", 0)),
                            "oi": float(item.get("oi", 0)),
                            "oi_value": float(item.get("oi_value", 0)),
                            "funding_rate": float(item.get("funding_rate", 0)),
                            "mark_price": float(item.get("mark_price", 0)),
                            "change_pct": float(item.get("ltp_change_24h", 0)),
                            "bid": float(item.get("quotes", {}).get("best_bid", 0)),
                            "ask": float(item.get("quotes", {}).get("best_ask", 0)),
                        }
        elif msg_type.startswith("candlestick_") and "v" in data:
            # Candlestick update - store in _live_candles if needed
            pass
    except Exception as e:
        logger.debug(f"Public WS message parse error: {e}")


def _on_public_error(ws, error):
    logger.warning(f"Public WS error: {error}")


def _on_public_close(ws, close_status_code, close_msg):
    global _pub_running
    _pub_running = False
    logger.info("Public WS closed. Reconnecting in 5s...")
    time.sleep(5)
    _start_public()


def _on_public_open(ws):
    global _pub_running
    _pub_running = True
    logger.info("Public WS connected")
    # Subscribe to ticker for all perpetuals
    ws.send(json.dumps({
        "type": "subscribe",
        "payload": {"channels": [{"name": "ticker", "symbols": ["all"]}]}
    }))
    # Subscribe to 1m candlesticks
    ws.send(json.dumps({
        "type": "subscribe",
        "payload": {"channels": [{"name": "candlestick_1m", "symbols": ["all"]}]}
    }))


def _start_public():
    global _pub_ws
    _pub_ws = websocket.WebSocketApp(
        DELTA_PUBLIC_WS_URL,
        on_open=_on_public_open,
        on_message=_on_public_message,
        on_error=_on_public_error,
        on_close=_on_public_close,
    )
    _pub_ws.run_forever(ping_interval=30, ping_timeout=10)


def _on_private_message(ws, message):
    try:
        data = json.loads(message)
        msg_type = data.get("type", "")
        # Private channels: positions, orders, margins, fills
        logger.debug(f"Private WS: {msg_type}")
    except Exception:
        pass


def _on_private_error(ws, error):
    logger.warning(f"Private WS error: {error}")


def _on_private_close(ws, close_status_code, close_msg):
    global _priv_running
    _priv_running = False
    logger.info("Private WS closed. Reconnecting in 10s...")
    time.sleep(10)
    if DELTA_API_KEY:
        _start_private()


def _on_private_open(ws):
    global _priv_running
    _priv_running = True
    logger.info("Private WS connected")
    # Authenticate
    timestamp = str(int(time.time()))
    sig_data = "GET" + timestamp + "/v2/positions" + "" + ""
    import hashlib, hmac
    signature = hmac.new(
        DELTA_API_SECRET.encode(), sig_data.encode(), hashlib.sha256
    ).hexdigest()
    ws.send(json.dumps({
        "type": "key-auth",
        "payload": {
            "api-key": DELTA_API_KEY,
            "signature": signature,
            "timestamp": timestamp,
        }
    }))
    # Subscribe to private channels after auth
    def send_subs(ws_ref):
        time.sleep(2)
        ws_ref.send(json.dumps({
            "type": "subscribe",
            "payload": {"channels": [
                {"name": "positions", "symbols": ["all"]},
                {"name": "orders", "symbols": ["all"]},
            ]}
        }))
    threading.Thread(target=send_subs, args=(ws,), daemon=True).start()


def _start_private():
    global _priv_ws
    _priv_ws = websocket.WebSocketApp(
        DELTA_WS_URL,
        on_open=_on_private_open,
        on_message=_on_private_message,
        on_error=_on_private_error,
        on_close=_on_private_close,
    )
    _priv_ws.run_forever(ping_interval=30, ping_timeout=10)


def start():
    """Start both public and private WebSocket threads."""
    t1 = threading.Thread(target=_start_public, daemon=True)
    t1.name = "crypto_ws_public"
    t1.start()

    if DELTA_API_KEY and DELTA_API_SECRET:
        t2 = threading.Thread(target=_start_private, daemon=True)
        t2.name = "crypto_ws_private"
        t2.start()
        logger.info("Crypto WebSocket started (public + private)")
    else:
        logger.info("Crypto WebSocket started (public only, no API keys)")


def is_connected():
    return _pub_running or _priv_running
