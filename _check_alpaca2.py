import requests
import json
import sys
sys.path.insert(0, '.')
from dumbmoney.config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL

headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_API_SECRET}

# Check what Alpaca returns for assets
resp = requests.get(f"{ALPACA_BASE_URL}/v2/assets", headers=headers, params={"status": "active", "asset_class": "us_equity", "page_size": 10})
data = resp.json()

print("=== Alpaca response field names ===")
if data:
    print("Keys:", list(data[0].keys()))
    print()
    for a in data[:10]:
        sym = a.get('symbol', '?')
        cls = a.get('class', 'MISSING')
        asset_class = a.get('asset_class', 'MISSING')
        name = a.get('name', '')[:60]
        print(f"  {sym}: class={cls}, asset_class={asset_class}, name={name}")

# Also check ETFs specifically
print("\n=== ETFs from Alpaca ===")
resp2 = requests.get(f"{ALPACA_BASE_URL}/v2/assets", headers=headers, params={"status": "active", "asset_class": "etf", "page_size": 10})
data2 = resp2.json()
if data2:
    print(f"ETF count (first page): {len(data2)}")
    for a in data2[:10]:
        sym = a.get('symbol', '?')
        cls = a.get('class', 'MISSING')
        asset_class = a.get('asset_class', 'MISSING')
        name = a.get('name', '')[:60]
        print(f"  {sym}: class={cls}, asset_class={asset_class}, name={name}")
else:
    print("  No ETFs returned")
