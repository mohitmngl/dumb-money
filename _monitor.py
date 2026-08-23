"""Monitor background processes: index creation and India rebuild."""
import subprocess, time, os, sys

def get_process(pid):
    try:
        import psutil
        p = psutil.Process(pid)
        return p
    except:
        pass
    try:
        out = subprocess.check_output(["powershell", "-Command",
            f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | Select-Object ProcessId,WorkingSet64,CPU"])
        return out.decode().strip()
    except:
        return None

idx_pid = 28344
in_pid = 28112
idx_log = "_create_index.py"
in_log = "_india_rebuild.py"

while True:
    status = []
    for name, pid, log in [("IDX", idx_pid, idx_log), ("INDIA", in_pid, in_log)]:
        out = subprocess.run(["powershell", "-Command",
            f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | Select-Object ProcessId,WorkingSet64,CPU,CreationDate; "
            f"if($p){{Write-Output \"$($p.ProcessId)|$($p.WorkingSet64)|$($p.CPU)|$($p.CreationDate)\"}}else{{Write-Output \"DEAD\"}}"],
            capture_output=True, text=True, timeout=10)
        line = out.stdout.strip()
        if line == "DEAD":
            status.append(f"[{time.strftime('%H:%M:%S')}] {name}({pid}): FINISHED/DEAD")
        else:
            parts = line.split("|")
            ws = int(parts[1]) // 1024 // 1024 if len(parts) > 1 else 0
            cpu = parts[2] if len(parts) > 2 else "?"
            status.append(f"[{time.strftime('%H:%M:%S')}] {name}({pid}): MEM={ws}MB CPU={cpu}s")
    print("\n".join(status))
    sys.stdout.flush()
    time.sleep(60)
