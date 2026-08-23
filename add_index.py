import sqlite3
conn = sqlite3.connect('screener.db')
print("Creating index...")
conn.execute("CREATE INDEX IF NOT EXISTS idx_bars_tf_date ON bars(timeframe, date)")
conn.commit()
print("Done")
conn.close()
