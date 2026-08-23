import sqlite3
conn = sqlite3.connect('screener.db')
conn.execute("DROP TABLE IF EXISTS bars")
conn.commit()
conn.execute("""CREATE TABLE IF NOT EXISTS bars (
  symbol TEXT, timeframe TEXT, date TEXT,
  open REAL, high REAL, low REAL, close REAL, volume INTEGER,
  PRIMARY KEY (symbol, timeframe, date))""")
conn.execute("CREATE INDEX IF NOT EXISTS idx_bars_sym_tf_date ON bars(symbol, timeframe, date)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_bars_tf_date ON bars(timeframe, date)")
conn.commit()
print("bars table recreated fresh")
conn.close()
