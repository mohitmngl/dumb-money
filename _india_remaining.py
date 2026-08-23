"""Continue India rebuild from string_id 15001 to 25000."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dumbmoney.basket_screener import update_historical_string_screener

print(f"[{time.strftime('%H:%M:%S')}] Starting India rebuild (remaining strings 15001-25000)...")
sys.stdout.flush()

string_ids = [f"S{i:06d}" for i in range(15001, 25001)]
print(f"  Strings to process: {len(string_ids)}")

update_historical_string_screener(
    "INDIA",
    only_strings=string_ids,
    force_rebuild=False,
    date_limit=500,
)

print(f"[{time.strftime('%H:%M:%S')}] India remaining strings rebuild complete!")
