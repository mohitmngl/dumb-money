import subprocess, sys, os, time

os.chdir(r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')
sys.path.insert(0, '.')

proc = subprocess.Popen(
    [sys.executable, 'run.py'],
    stdout=open('server_out.log', 'w'),
    stderr=open('server_err.log', 'w'),
    creationflags=0x08000000
)
print(f'Server PID={proc.pid}')

for i in range(60):
    time.sleep(5)
    try:
        import urllib.request
        urllib.request.urlopen('http://localhost:8474/', timeout=3)
        print(f'Server ready after {(i+1)*5}s')
        break
    except Exception:
        if i % 6 == 0:
            print(f'Waiting... {(i+1)*5}s')
else:
    print('Server failed to start')
    sys.exit(1)
