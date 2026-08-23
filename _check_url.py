import urllib.request

# Try different URLs
for url in ["http://localhost:8474/", "http://localhost:8474/screener/US", "http://localhost:8474/screener"]:
    try:
        resp = urllib.request.urlopen(url)
        print(f"OK: {url} -> {resp.status}")
        html = resp.read().decode('utf-8')
        if 'heat-pill' in html:
            lines = html.split('\n')
            for i, line in enumerate(lines):
                if 'heat-pill' in line:
                    print(f"  Line {i+1}: {line.strip()[:120]}")
        break
    except Exception as e:
        print(f"FAIL: {url} -> {e}")
