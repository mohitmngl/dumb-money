import subprocess, sys, os
os.chdir(r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')
proc = subprocess.Popen(
    [sys.executable, '-c',
     'from dumbmoney.app import app, create_app; create_app(); app.run(host="0.0.0.0", port=8474, debug=False)'],
    stdout=open('server_out.log', 'w'),
    stderr=open('server_err.log', 'w'),
    creationflags=0x08000000)
print(f'PID={proc.pid}')
