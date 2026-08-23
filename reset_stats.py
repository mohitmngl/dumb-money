import sqlite3

conn = sqlite3.connect('screener.db')
conn.execute("DELETE FROM stats")
conn.execute("DELETE FROM historical_screener")
conn.execute("DELETE FROM signal_prob_matrix")
conn.commit()
print("Cleared stats, historical_screener, signal_prob_matrix")
conn.close()
