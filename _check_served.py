import urllib.request

# Fetch the actual rendered page
resp = urllib.request.urlopen("http://localhost:8474/screener?market=US")
html = resp.read().decode('utf-8')

# Find the heat-pill rendering code
lines = html.split('\n')
for i, line in enumerate(lines):
    if 'heat-pill' in line:
        print(f"Line {i+1}: {line.strip()}")
print()

# Check if it's on a span or td
if 'span class="heat-pill"' in html:
    print("OK: heat-pill is on <span>")
elif "cls = 'heat-pill'" in html or 'cls="heat-pill"' in html:
    print("BUG: heat-pill class is being set on td directly")
else:
    print("heat-pill reference found but unclear where")

# Also check the streak rendering
for i, line in enumerate(lines):
    if "col.key === 'streak'" in line:
        print(f"\nStreak rendering (line {i+1}): {line.strip()}")
