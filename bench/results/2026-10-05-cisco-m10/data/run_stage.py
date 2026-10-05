import json,subprocess,sys,time
from pathlib import Path
import requests
n=int(sys.argv[1]); root=Path('/home/bjwl/strata-dev'); logs=Path('/models/strata-work/logs')
server=subprocess.Popen(['bash',str(root/'start_smoke_server.sh'),str(n)])
start=time.monotonic()
for _ in range(240):
 if server.poll() is not None: raise SystemExit(f'Server exited: {server.returncode}')
 try:
  r=requests.get('http://127.0.0.1:8080/health',timeout=2)
  if r.ok and r.json().get('loaded'): break
 except requests.RequestException: pass
 time.sleep(5)
else: raise SystemExit('Server startup timed out')
print(f'Server {n} GPUs ready in {time.monotonic()-start:.1f} s',flush=True)
with (logs/f'smoke-{n}gpu-client.log').open('w') as f:
 r=subprocess.run([str(root/'venv/bin/python'),'-u',str(root/'smoke_client.py'),str(n)],stdout=f,stderr=subprocess.STDOUT)
with (logs/f'gpu-memory-{n}gpu.csv').open('w') as f:
 subprocess.run(['nvidia-smi','--query-gpu=index,name,memory.used,memory.free,utilization.gpu','--format=csv'],stdout=f,check=True)
print(f'Smoke exit: {r.returncode}',flush=True)
raise SystemExit(r.returncode)
