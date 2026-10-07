"""Guest supervisor: export if complete, then restore Q4 even after run failure."""
import json
from pathlib import Path
import subprocess
import sys
import time
import psutil

w=Path('/home/bjwl/strata-dev/blind-quality-20261007')
runner=Path('/home/bjwl/strata-dev/run_blind.py')
pid=int(sys.argv[1])
p=psutil.Process(pid)
if str(runner) not in p.cmdline() or 'run' not in p.cmdline():
    raise RuntimeError('Unexpected benchmark PID')
p.wait()
state=json.loads((w/'status.json').read_text())
if state.get('state')=='complete':
    subprocess.run([sys.executable,str(runner),'export'],check=True)
(w/'restore-status.json').write_text(json.dumps(dict(state='restoring',started_unix=time.time()))+'\n')
try:
    subprocess.run([sys.executable,str(runner),'restore'],check=True)
    (w/'restore-status.json').write_text(json.dumps(dict(state='server_started',ended_unix=time.time()))+'\n')
except Exception as e:
    (w/'restore-status.json').write_text(json.dumps(dict(state='failed',error=str(e)))+'\n')
    raise
