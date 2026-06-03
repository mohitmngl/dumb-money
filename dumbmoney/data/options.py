"""
Try to fetch options chain data from Alpaca and other free sources.
"""
import requests
import json
from datetime import datetime

ALPACA_OPTIONS_URL = "https://paper-api.alpaca.markets/v2/options/contracts"
ALPACA_QUOTES_URL = "https://paper-api.alpaca.markets/v2/options/quotes"
HEADERS = {
    "APCA-API-KEY-ID": "PKZPJMK5TL4UKT4TTDO5ELNM3B",
    "APCA-API-SECRET-KEY": "6GF5J7dXTztrqK7uQZkvHxXcayWP9pFxgqpRXvqrLTra",
}

def get_option_chain(symbol):
    """Fetch options chain for a symbol."""
    try:
        # First try to get contracts (Alpaca options API)
        params = {
            "underlying_symbols": symbol,
            "status": "active",
            "limit": 50
        }
        resp = requests.get(ALPACA_OPTIONS_URL, headers=HEADERS, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            contracts = data.get("option_contracts", [])
            if contracts:
                # Get quotes for these contracts
                symbols_str = ",".join([c["symbol"] for c in contracts[:50]])
                quotes_resp = requests.get(ALPACA_QUOTES_URL, headers=HEADERS, params={"symbols": symbols_str, "feed": "indicative"}, timeout=10)
                quotes = {}
                if quotes_resp.status_code == 200:
                    for q in quotes_resp.json().get("quotes", []):
                        quotes[q["symbol"]] = q

                result = []
                for c in contracts:
                    q = quotes.get(c["symbol"], {})
                    entry = {
                        "contract": c["symbol"],
                        "type": c["type"],
                        "strike": c["strike_price"],
                        "expiration": c["expiration_date"],
                        "bid": q.get("bid_price"),
                        "ask": q.get("ask_price"),
                        "last": q.get("last_price"),
                        "volume": q.get("volume"),
                        "open_interest": q.get("open_interest"),
                        "implied_vol": q.get("implied_volatility"),
                    }
                    result.append(entry)

                # Group by expiration
                chains = {}
                for e in result:
                    exp = e["expiration"]
                    if exp not in chains:
                        chains[exp] = {"expiration": exp, "calls": [], "puts": []}
                    if e["type"] == "call":
                        chains[exp]["calls"].append(e)
                    else:
                        chains[exp]["puts"].append(e)

                return {"status": "ok", "chains": list(chains.values())}
    except Exception as e:
        pass

    return {"status": "unavailable", "message": "Options data not available for " + symbol}
