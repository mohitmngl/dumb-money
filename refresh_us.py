import sys, time
sys.path.insert(0, r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')
t0 = time.time()

from dumbmoney.refresh import run_refresh, get_refresh_status

print(f'[{time.time()-t0:.0f}s] Starting US refresh...', flush=True)
run_refresh('US')

# Wait for refresh to complete
while True:
    time.sleep(10)
    status = get_refresh_status('US')
    s = status.get('status', 'unknown')
    phase = status.get('phase', '')
    step = status.get('step_name', '')
    pct = status.get('overall_pct', 0)
    elapsed = int(time.time() - t0)
    print(f'[{elapsed}s] {s} - {phase} - {step} ({pct:.0f}%)', flush=True)
    if s != 'running':
        print(f'[{elapsed}s] Refresh finished: {s}', flush=True)
        break
    if elapsed > 3600:
        print(f'[{elapsed}s] Timeout - stopping', flush=True)
        break

print(f'[{time.time()-t0:.0f}s] DONE', flush=True)
