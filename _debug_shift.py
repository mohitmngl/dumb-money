import urllib.request, json

data = json.loads(urllib.request.urlopen("http://localhost:8474/api/screener?market=US&per_page=5&sort=weighted_alpha&sort_dir=desc").read())

print("API response columns for first 5 rows:")
print(f"{'Symbol':<8} {'WA':>12} {'Volume':>10} {'Streak':>8} {'Confluence':>10}")
print("-" * 60)
for r in data["data"]:
    print(f"{r['symbol']:<8} {r['weighted_alpha']:>12} {r['volume']:>10} {r['streak']:>8} {r['confluence']:>10}")

print()
print("Now let me check if sorted by WA desc, the WA values should be descending:")
was = [r['weighted_alpha'] for r in data["data"]]
print(f"WA values: {was}")
print(f"Is sorted desc: {was == sorted(was, reverse=True)}")
