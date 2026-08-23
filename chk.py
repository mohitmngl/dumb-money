import urllib.request, json
r = urllib.request.urlopen('http://localhost:8474/api/string-screener/backtest/status', timeout=5)
print(json.dumps(json.loads(r.read()), indent=2))
