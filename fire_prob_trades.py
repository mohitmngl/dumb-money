import json, urllib.request, time

HEADERS = {'APCA-API-KEY-ID': 'PKUPBR7N6SS6NQUJ4U24NO7GEO', 'APCA-API-SECRET-KEY': 'BFGrUckWUymMRYVe9kkrz1V2zVLXeoxBU7Kr5K54Cfsq'}

def api(method, path, body=None):
    url = f'https://paper-api.alpaca.markets{path}'
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, headers=HEADERS, data=data, method=method)
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())

trades = [
    {"symbol": "V",   "notional": "500", "side": "buy"},
    {"symbol": "XOM", "notional": "500", "side": "buy"},
]

print("=== FIRING 15-MIN PROBABILITY TRADES ===")
for t in trades:
    body = {
        "symbol": t["symbol"],
        "notional": t["notional"],
        "side": t["side"],
        "type": "market",
        "time_in_force": "day"
    }
    try:
        o = api('POST', '/v2/orders', body)
        print(f"  BUY {t['symbol']} ${t['notional']}: order={o['id'][:8]}.. status={o['status']} filled_avg={o.get('filled_avg','pending')}")
    except Exception as e:
        print(f"  BUY {t['symbol']} FAILED: {e}")

time.sleep(2)

# Check fill status
print("\n=== ORDER STATUS ===")
orders = api('GET', '/v2/orders?status=open&status=filled')
for o in orders:
    if o['symbol'] in ['V', 'XOM']:
        print(f"  {o['symbol']} {o['side']} notional=${o.get('notional','?')} status={o['status']} filled_avg={o.get('filled_avg','?')} filled_qty={o.get('filled_qty','?')}")

print("\n=== POSITIONS ===")
positions = api('GET', '/v2/positions')
for p in positions:
    print(f"  {p['symbol']}: qty={p['qty']} avg_entry={p['avg_entry_price']} mkt_val=${p['market_value']} pnl=${p['unrealized_pl']}")

acct = api('GET', '/v2/account')
print(f"\n  BP remaining: ${acct['buying_power']}")
