import urllib.request, json
data = json.loads(urllib.request.urlopen("http://localhost:8474/api/screener?market=US&per_page=3").read())
for row in data["data"]:
    print(f"Symbol: {row['symbol']}")
    print(f"  volume: {row['volume']} (type: {type(row['volume']).__name__})")
    print(f"  streak: {row['streak']} (type: {type(row['streak']).__name__})")
    print(f"  weighted_alpha: {row['weighted_alpha']}")
    print(f"  prob_up_1d: {row['prob_up_1d']}")
    print(f"  prob_up_5d: {row['prob_up_5d']}")
    print(f"  confluence: {row['confluence']}")
    print()
