import json
import os
from pathlib import Path
import psutil
import subprocess
import time
root=Path('/home/bjwl/strata-dev/long-context')
while True:
    p=root/'q8-64k/status.json'
    if p.exists():
        s=json.loads(p.read_text())
        if s['state'] in ('complete','failed'): break
    time.sleep(5)
q4=json.loads((root/'q4-64k/status.json').read_text())
assert q4['state']=='complete' and q4['functional_pass'], q4
assert not any(p.info['name']=='strata' and p.status()!=psutil.STATUS_ZOMBIE
               for p in psutil.process_iter(['name'])), 'Benchmark engine still alive'
files=[]
for directory in ('models/unsloth-q8_0','packs/unsloth-q8_0'):
 for f in (Path('/models/strata-work/data')/directory).rglob('*'):
  if f.is_file():
   with f.open('rb') as handle: os.posix_fadvise(handle.fileno(),0,0,os.POSIX_FADV_DONTNEED)
   files.append(str(f))
(root/'q8-cache-release.json').write_text(json.dumps({'files':files,'available_gib':psutil.virtual_memory().available/2**30},indent=2)+'\n')
cmd=['/home/bjwl/strata-dev/venv/bin/python','-u','/home/bjwl/Strata/bench/m10/start_server.py',
 '--config',str(root/'q4-service-64k-source.json'),'--data','/models/strata-work/data',
 '--dest','/mnt/strata-ram/data','--runtime','/home/bjwl/strata-dev/service',
 '--host','192.168.3.73','--drop-source-cache','--api-key-file','/home/bjwl/strata-dev/service/api-key']
with (root/'service-restoration.log').open('w') as log:
 p=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(root/'restoration-launcher.pid').write_text(str(p.pid)+'\n')
print('Launched Q4 64K staging and authenticated LAN service:',p.pid,flush=True)
