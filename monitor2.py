import requests, time

time.sleep(8)
try:
    r = requests.get('http://127.0.0.1:8474/api/health', timeout=10)
    print('Health:', r.status_code)
except Exception as e:
    print('Health error:', e)

try:
    r = requests.post('http://127.0.0.1:8474/api/refresh', json={'market': 'US'}, timeout=10)
    print('Refresh:', r.status_code, r.text[:100])
except Exception as e:
    print('Refresh error:', e)

# Monitor
for i in range(60):
    time.sleep(30)
    try:
        r = requests.get('http://127.0.0.1:8474/api/refresh/status', timeout=30)
        s = r.json()
        step = s.get('step', '?')
        msg = s.get('message', '')
        pct = s.get('overall_pct', 0)
        syms = s.get('symbols_done', 0)
        status = s.get('status', '?')
        print(f'[{pct:.1f}%] Step {step}: {msg} ({syms} syms) status={status}')
        if status == 'idle' and pct > 50:
            break
    except Exception as e:
        print(f'Error: {e}')
