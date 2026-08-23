import requests, sys
sys.path.insert(0, '.')
from dumbmoney.config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL

headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_API_SECRET}

# Fetch more assets to find ETFs
all_assets = []
params = {"status": "active", "asset_class": "us_equity", "page_size": 100}
for _ in range(10):
    resp = requests.get(f"{ALPACA_BASE_URL}/v2/assets", headers=headers, params=params)
    data = resp.json()
    if not data:
        break
    all_assets.extend(data)
    params["page_token"] = data[-1].get("id", "")
    if not params.get("page_token"):
        break

print(f"Total assets fetched: {len(all_assets)}")

# Check class values
from collections import Counter
class_counts = Counter(a.get("class", "MISSING") for a in all_assets)
print(f"\nClass values: {dict(class_counts)}")

# Find ETFs by name
etfs = [a for a in all_assets if "etf" in a.get("name", "").lower()]
print(f"\nETFs found by name: {len(etfs)}")
for a in etfs[:20]:
    print(f"  {a['symbol']}: class={a.get('class')}, name={a.get('name','')[:60]}")

# Check if there's an 'attributes' field with more info
if all_assets and 'attributes' in all_assets[0]:
    attrs = set()
    for a in all_assets:
        if a.get('attributes'):
            attrs.update(a['attributes'].keys() if isinstance(a['attributes'], dict) else [a['attributes']])
    print(f"\nAttributes found: {attrs}")

# Show a sample of what class= returns for different asset types
print("\n=== Sample: non-ETF names with 'fund' or 'trust' ===")
for a in all_assets:
    name = a.get("name", "").lower()
    if ("fund" in name or "trust" in name or "etf" in name) and a.get("symbol", "").isalpha():
        print(f"  {a['symbol']}: class={a.get('class')}, name={a.get('name','')[:60]}")
