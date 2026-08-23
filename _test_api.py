"""Quick API test."""
import requests, json
base = "http://localhost:8474/api"
try:
    # Test main screener
    r = requests.get(f"{base}/screener?market=US", timeout=10)
    print(f"Screener: {r.status_code} ({'OK' if r.status_code==200 else 'FAIL'})")
    data = r.json()
    print(f"  rows: {len(data.get('rows', []))}, total: {data.get('total', '?')}")
except Exception as e:
    print(f"Screener error: {e}")

try:
    # Test string screener
    r = requests.get(f"{base}/string-screener?market=US", timeout=10)
    print(f"String: {r.status_code} ({'OK' if r.status_code==200 else 'FAIL'})")
    data = r.json()
    print(f"  rows: {len(data.get('rows', []))}, total: {data.get('total', '?')}")
except Exception as e:
    print(f"String error: {e}")

try:
    # Test market stats
    r = requests.get(f"{base}/market-stats?market=US", timeout=10)
    print(f"MarketStats: {r.status_code} ({'OK' if r.status_code==200 else 'FAIL'})")
    print(f"  {r.json()}")
except Exception as e:
    print(f"MarketStats error: {e}")
