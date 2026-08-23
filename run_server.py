import time
t = time.time()
print("Step 1: init_all_dbs...", flush=True)
from dumbmoney.db import init_all_dbs
init_all_dbs()
print(f"  done in {time.time()-t:.1f}s", flush=True)

t = time.time()
print("Step 2: ensure_schema...", flush=True)
from dumbmoney.db import ensure_schema, DB_PATHS
for db_path in DB_PATHS.values():
    ensure_schema(db_path)
print(f"  done in {time.time()-t:.1f}s", flush=True)

t = time.time()
print("Step 3: reset_stale_status...", flush=True)
from dumbmoney.refresh import reset_stale_status
reset_stale_status()
print(f"  done in {time.time()-t:.1f}s", flush=True)

print("Step 4: creating app...", flush=True)
from dumbmoney.app import app
print(f"  App created in {time.time()-t:.1f}s total", flush=True)
app.run(host="0.0.0.0", port=8474, debug=False)
