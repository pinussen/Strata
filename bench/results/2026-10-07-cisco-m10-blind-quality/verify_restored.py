"""Verify restored service without printing or exporting its credential."""
import json
from pathlib import Path
import socket
import sys
import time

import psutil
import requests

ROOT=Path('/home/bjwl/Strata')
DEV=Path('/home/bjwl/strata-dev')
WORK=DEV/'blind-quality-20261007'
sys.path.insert(0,str(ROOT/'bench/m10'))
from run_benchmark import request,write_json

cfg=json.loads((DEV/'service/server.json').read_text())
headers={'Authorization':'Bearer '+cfg['api_key']}
base='http://192.168.3.73:8080'
deadline=time.monotonic()+600
while time.monotonic()<deadline:
    try:
        r=requests.get(base+'/health',headers=headers,timeout=3)
        if r.ok and r.json().get('loaded'):break
    except requests.RequestException:pass
    time.sleep(2)
else:raise RuntimeError('Restored server not healthy in 10 minutes')
models=requests.get(base+'/v1/models',headers=headers,timeout=5)
models.raise_for_status()
unauth=requests.get(base+'/v1/models',timeout=5)
assert unauth.status_code in (401,403),'API authentication not enforced'
assert 'q4' in json.dumps(models.json()).lower(),'Unexpected interactive model'
assert (DEV/'service/server.json').read_bytes()==(WORK/'interactive-private.json').read_bytes()
with socket.socket() as s:
    s.settimeout(2);benchmark_port_closed=s.connect_ex(('127.0.0.1',8097))!=0
assert benchmark_port_closed
# New, separate service probe, not a repetition of any scored or warmup prompt.
payload=dict(model=cfg['model_name'],temperature=0,seed=20261007,reasoning_effort='none',
             max_tokens=16,messages=[dict(role='user',content='Svara endast med ordet återställd.')])
smoke=request(base,payload,headers=headers)
assert smoke['content'].strip(),'Empty response to restoration probe'
before=json.loads((WORK/'bf16-before.json').read_text())
after={}
for name in before:
    p=Path(name);st=p.stat()
    after[name]=dict(size=st.st_size,mtime_ns=st.st_mtime_ns,
                    sha256=p.read_text().strip() if p.suffix=='.sha256' else None)
assert before==after,'BF16 inventory changed'
write_json(WORK/'bf16-after.json',after)
check=dict(checked_unix=time.time(),health_status=r.status_code,health=r.json(),
           authenticated_models_status=models.status_code,models=models.json(),
           unauthenticated_models_status=unauth.status_code,
           original_private_config_unchanged=True,benchmark_port_closed=benchmark_port_closed,
           bf16_inventory_unchanged=True,smoke_request=payload,smoke_response=smoke,
           memory=psutil.virtual_memory()._asdict(),swap=psutil.swap_memory()._asdict(),
           server_pid=int((DEV/'service/server.pid').read_text()))
write_json(WORK/'final-access-check.json',check)
print(json.dumps({k:check[k] for k in ['health_status','authenticated_models_status',
       'unauthenticated_models_status','original_private_config_unchanged','benchmark_port_closed',
       'bf16_inventory_unchanged','server_pid']}))
