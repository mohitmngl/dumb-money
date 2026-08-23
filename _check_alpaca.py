import urllib.request, json

ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
API_KEY = "PKUPBR7N6SS6NQUJ4U24NO7GEO"
API_SECRET = "6UKhjX29hsu57vp6utqZHYmwUV5hmjNcJPPTJiYZDCM"

headers = {"APCA-API-KEY-ID": API_KEY, "APCA-API-SECRET-KEY": API_SECRET}
req = urllib.request.Request(f"{ALPACA_BASE_URL}/v2/assets?status=active&asset_class=us_equity&page_size=5", headers=headers)
data = json.loads(urllib.request.urlopen(req).read())

print("=== Alpaca API response field names for first 5 assets ===")
if data:
    print("Keys:", list(data[0].keys()))
    print()
    for a in data[:5]:
        print(f"  {a.get('symbol')}: class={a.get('class')}, asset_class={a.get('asset_class')}, name={a.get('name','')[:50]}")
    
    print("\n=== Now check ETFs ===")
    req2 = urllib.request.Request(f"{ALPACA_BASE_URL}/v2/assets?status=active&asset_class=us_equity&page_size=20", headers=headers)
    data2 = json.loads(urllib.request.urlopen(req2).read())
    for a in data2[:20]:
        print(f"  {a.get('symbol')}: class={a.get('class')}, name={a.get('name','')[:60]}")
else:
    print("No data returned")
