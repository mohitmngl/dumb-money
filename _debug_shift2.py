import urllib.request, json

data = json.loads(urllib.request.urlopen("http://localhost:8474/api/screener?market=US&per_page=3&sort=weighted_alpha&sort_dir=desc").read())

# Check exact keys returned
first = data["data"][0]
print("Keys in first row:", list(first.keys()))
print()
print("First 3 rows:")
for r in data["data"]:
    print(f"  {r['symbol']}: weighted_alpha={r.get('weighted_alpha')}, volume={r.get('volume')}, streak={r.get('streak')}, prob_up_1d={r.get('prob_up_1d')}, prob_up_5d={r.get('prob_up_5d')}, confluence={r.get('confluence')}")
