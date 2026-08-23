"""Write a launcher that starts _fix_hss_pst.py with proper logging."""
import subprocess, sys, os

log_path = os.path.join(os.path.dirname(__file__), '_fix_hss_pst.log')
script_path = os.path.join(os.path.dirname(__file__), '_fix_hss_pst.py')

# Find python
python_exe = sys.executable
if 'ipopt312' not in python_exe:
    # Prefer ipopt312 env for numpy
    python_exe = r"C:\Users\Admin\miniforge3\envs\ipopt312\python.exe"

print(f"Launching {script_path} with {python_exe}, logging to {log_path}")
proc = subprocess.Popen(
    [python_exe, '-u', script_path],
    stdout=open(log_path, 'w', buffering=1),
    stderr=subprocess.STDOUT,
    cwd=os.path.dirname(__file__),
    creationflags=subprocess.CREATE_NO_WINDOW
)
print(f"PID: {proc.pid}")
