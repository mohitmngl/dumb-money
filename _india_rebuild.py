"""Trigger India basket historical rebuild."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dumbmoney.basket_screener import update_historical_string_screener
print(f"[{time.strftime('%H:%M:%S')}] Starting India basket rebuild...")
sys.stdout.flush()
update_historical_string_screener("INDIA", force_rebuild=True, date_limit=500)
print(f"[{time.strftime('%H:%M:%S')}] India rebuild complete!")
