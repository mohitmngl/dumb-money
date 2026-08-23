import sqlite3

conn = sqlite3.connect('screener.db')

def classify_asset(sym, name):
    name_lower = (name or "").lower()
    sym_upper = sym.upper()

    # Known ETF tickers (exact match only)
    etf_exact_syms = {
        "SPY", "QQQ", "IVV", "VOO", "DIA", "USO", "GLD", "SLV",
        "TLT", "TBT", "HYG", "LQD", "MBB", "VNQ", "EWJ", "EWW",
        "EFA", "VWO", "FXI", "KWEB", "GDX", "GDXJ",
        "XLF", "XLE", "XLU", "XLK", "XLB", "XLP", "XLI", "XLY", "XLRE",
        "ARKK", "ARKG", "ARKF", "ARKW", "ARKQ", "ARKB", "ARKX",
        "SOXX", "SMH", "IWM", "MDY", "EEM", "VEA", "VGK",
        "IWO", "IWF", "IWD", "IWB", "IEF", "SHY",
        "AGG", "BND", "SCHD", "VYM", "HDV", "DGRO", "SCHX",
        "VTI", "VXUS", "BNDX", "IEFA", "IEMG",
        "SPHD", "SPLV", "NOBL", "VIG", "SCHV", "MTUM", "QUAL",
        "RPV", "RPG", "VLUE", "USMV",
        "XME", "XHB", "XRT", "XOP", "XBI", "XSD",
        "ITA", "PPA", "VIS", "IYC", "IYK", "IYH", "IYZ",
        "IYR", "IYJ", "IYM", "IYE", "IAU", "GLDM", "SGOL",
        "DBC", "PDBC", "UVIX", "VXX", "VIXY",
        "UGL", "GLL", "ZSL", "AGQ", "SIVR",
        "UUP", "UDN", "FXE", "FXY", "FXB", "FXA", "FXC",
        "BIL", "SHV", "VGSH", "SGOV", "VBIL",
        "URNM", "URNJ", "URA",
        "VAW", "VB", "VBK", "VBR", "VCR", "VDC", "VEGI",
        "VEGN", "VEU", "VFLO", "VFQY", "VFVA", "VGIT",
        "VGLT", "VGSR", "VGUS", "TOTL", "TIPX", "TUA",
        "UYLD", "BITO", "IBIT", "GBTC", "ETHE",
    }

    if sym_upper in etf_exact_syms:
        return "etf"

    cef_keywords = ["closed-end", "closed end"]
    for kw in cef_keywords:
        if kw in name_lower:
            return "cef"

    etf_name_patterns = [
        " etf", "etf ", " index fund", " index etf",
    ]
    for pat in etf_name_patterns:
        if pat in name_lower:
            return "etf"

    # Fund company prefixes that only appear in ETF/fund names
    etf_company_prefixes = [
        "spdr ", "ishares ", "proshares ", "first trust ",
        "global x ", "flexshares ", "powershares ", "rydex ",
        "dimensional ", "wisdomtree ",
    ]
    for kw in etf_company_prefixes:
        if name_lower.startswith(kw) or (" " + kw) in name_lower:
            return "etf"

    # Catch-all: name ends with "Fund" + something or specific patterns
    if name_lower.endswith(" fund") and any(w in name_lower for w in ["income", "growth", "value", "total return", "short", "ultra", "long"]):
        return "cef"

    return "stock"

rows = conn.execute("SELECT symbol, name, asset_class FROM assets").fetchall()

updated = 0
changes = []
for sym, name, old_class in rows:
    new_class = classify_asset(sym, name)
    if new_class != old_class:
        conn.execute("UPDATE assets SET asset_class = ? WHERE symbol = ?", (new_class, sym))
        updated += 1
        changes.append((sym, name, old_class, new_class))

conn.commit()

print(f"Total assets: {len(rows)}")
print(f"Updated: {updated}")

print("\n=== New asset_class distribution ===")
for r in conn.execute("SELECT asset_class, COUNT(*) FROM assets GROUP BY asset_class ORDER BY COUNT(*) DESC"):
    print(f"  {r[0]}: {r[1]}")

print("\n=== False positive checks ===")
# Check MARK, LOVLQ are now stock
for s in ["MARK", "LOVLQ", "TRMK", "TRST"]:
    r = conn.execute("SELECT symbol, name, asset_class FROM assets WHERE symbol=?", (s,)).fetchone()
    if r:
        print(f"  {r[0]}: {r[2]} ({r[1]})")

print("\n=== Sample ETFs ===")
for r in conn.execute("SELECT symbol, name, asset_class FROM assets WHERE asset_class='etf' ORDER BY symbol LIMIT 25"):
    print(f"  {r[0]}: {r[1]}")

print("\n=== Sample CEFs ===")
for r in conn.execute("SELECT symbol, name, asset_class FROM assets WHERE asset_class='cef' LIMIT 10"):
    print(f"  {r[0]}: {r[1]}")

print("\n=== Sample Stocks (should be real stocks) ===")
for r in conn.execute("SELECT symbol, name, asset_class FROM assets WHERE asset_class='stock' ORDER BY RANDOM() LIMIT 15"):
    print(f"  {r[0]}: {r[1]}")

print("\n=== Changes ===")
for sym, name, old, new in changes[:30]:
    print(f"  {sym}: {old} -> {new} ({name})")
if len(changes) > 30:
    print(f"  ... and {len(changes) - 30} more")

conn.close()
