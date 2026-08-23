import requests, time

time.sleep(8)

try:
    r = requests.get('http://127.0.0.1:8474/api/health', timeout=10)
    print('Health:', r.status_code)
except Exception as e:
    print('Health error:', e)
    exit(1)

try:
    r = requests.post('http://127.0.0.1:8474/api/refresh', json={'market': 'US'}, timeout=10)
    print('Refresh:', r.status_code, r.text[:100])
except Exception as e:
    print('Refresh error:', e)

for i in range(120):
    time.sleep(15)
    try:
        r = requests.get('http://127.0.0.1:8474/api/refresh/status', timeout=15)
        s = r.json()
        step = s.get('step', '?')
        msg = s.get('message', '')
        pct = s.get('overall_pct', 0)
        syms = s.get('symbols_done', 0)
        status = s.get('status', '?')
        print('[%s%%] Step %s: %s (%s syms) status=%s' % (round(pct,1), step, msg, syms, status))
        if status == 'idle' and pct > 90:
            break
    except Exception as e:
        print('Error: %s' % e)
