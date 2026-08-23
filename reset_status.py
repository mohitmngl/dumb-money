import sqlite3
for db in [r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db', r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\india.db']:
    try:
        conn = sqlite3.connect(db)
        conn.execute("UPDATE settings SET value='idle' WHERE key='refresh_status'")
        conn.commit()
        conn.close()
        print(f'Reset {db}')
    except Exception as e:
        print(f'Error {db}: {e}')
