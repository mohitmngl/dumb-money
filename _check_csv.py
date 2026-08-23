import csv, io, urllib.request

req = urllib.request.Request(
    "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    headers={"User-Agent": "Mozilla/5.0"}
)
resp = urllib.request.urlopen(req, timeout=15)
data = resp.read().decode("utf-8")
reader = csv.reader(io.StringIO(data))
header = next(reader)
print("Headers:", header)
for i, row in enumerate(reader):
    if i < 3:
        print(f"Row {i}: {row}")
