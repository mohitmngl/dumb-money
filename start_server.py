import sys, time
sys.path.insert(0, '.')
print("Testing init_all_dbs...")
t0 = time.time()
from dumbmoney.db import init_all_dbs
init_all_dbs()
print(f"init_all_dbs done in {time.time()-t0:.1f}s")
print("Testing create_app...")
from dumbmoney.app import create_app
create_app()
print(f"create_app done in {time.time()-t0:.1f}s")
from dumbmoney.app import app
app.run(host="0.0.0.0", port=8474, debug=False)
