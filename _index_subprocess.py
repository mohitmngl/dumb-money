"""Run CREATE INDEX via subprocess with explicit timeout and output capture."""
import subprocess, sys, time, os
t0 = time.time()
cmd = ["C:/Users/Admin/miniforge3/envs/ipopt312/python.exe", "-u", "-c",
    "import sqlite3, time; c=sqlite3.connect('screener.db',timeout=1800); "
    "print('CONNECTED', flush=True); "
    "t0=time.time(); c.execute('CREATE INDEX IF NOT EXISTS idx_hss_date ON historical_string_screener(date)'); "
    f"print('DONE', time.time()-t0, flush=True); c.close()"]

print(f"[{time.strftime('%H:%M:%S')}] Running CREATE INDEX via subprocess...")
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=".", bufsize=1)
last_output = None
while True:
    ret = proc.poll()
    if ret is not None:
        out, err = proc.communicate()
        print(f"  stdout: {out.strip()}")
        print(f"  stderr: {err.strip()[:500]}")
        print(f"  returncode: {ret}")
        break
    # Check for new output
    line = proc.stdout.readline()
    if line:
        print(f"  > {line.strip()}")
        sys.stdout.flush()
    else:
        time.sleep(5)
        elapsed = time.time() - t0
        print(f"  ... {elapsed:.0f}s (still running)")
        sys.stdout.flush()
