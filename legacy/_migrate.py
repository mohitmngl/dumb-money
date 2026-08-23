"""Run db migrations to add prob_up_st_cross column."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dumbmoney.db import _init_db, US_DB, INDIA_DB

print("Running migrations on US DB...")
_init_db(US_DB)
print("Running migrations on India DB...")
_init_db(INDIA_DB)
print("Done")
