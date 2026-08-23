import json, urllib.request, time

HEADERS = {'APCA-API-KEY-ID': 'PKUPBR7N6SS6NQUJ4U24NO7GEO', 'APCA-API-SECRET-KEY': 'BFGrUckWUymMRYVe9kkrz1V2zVLXeoxBU7Kr5K54Cfsq'}

def api(method, path, body=None):
    url = f'https://paper-api.alpaca.markets{path}'
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, headers=HEADERS, data=data, method=method)
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read()) if resp.read() else {}

# Close ALL positions
print("Closing all positions...")
try:
    api('DELETE', '/v2/positions')
    print("All positions closed.")
except Exception as e:
    print(f"Error: {e}")

time.sleep(2)

# Verify
positions = api('GET', '/v2/positions')
print(f"Remaining positions: {len(positions)}")

acct = api('GET', '/v2/account')
print(f"Equity: ${acct.get('equity', '0')} | BP: ${acct.get('buying_power', '0')}")
