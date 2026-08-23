import requests, time

for i in range(30):
    time.sleep(20)
    try:
        r = requests.get('http://127.0.0.1:8474/api/refresh/status', timeout=30)
        s = r.json()
        step = s.get('step', '?')
        msg = s.get('message', '')
        pct = s.get('overall_pct', 0)
        syms = s.get('symbols_done', 0)
        status = s.get('status', '?')
        print(f'[{pct:.1f}%] Step {step}: {msg} ({syms} syms) status={status}')
        if status == 'idle':
            break
    except Exception as e:
        print(f'Error: {e}')
