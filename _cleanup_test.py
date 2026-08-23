import sqlite3
c = sqlite3.connect("screener.db", timeout=60)
test_sids = [f"LS{i:06d}" for i in range(1, 21)]
n = c.execute(f"DELETE FROM historical_string_screener WHERE string_id IN ({','.join(['?']*20)})", test_sids).rowcount
c.commit()
print(f"Deleted {n} rows")
c.close()
