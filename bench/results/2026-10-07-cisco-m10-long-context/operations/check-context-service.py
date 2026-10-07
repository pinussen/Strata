"""Validate the restored authenticated LAN service without another long prefill."""
import json
from pathlib import Path
import sys
import time
import requests
sys.path.insert(0,'/home/bjwl/Strata/bench/m10')
from run_benchmark import request, write_json
root=Path('/home/bjwl/strata-dev/long-context')
while not (root/'restoration-launcher.pid').exists(): time.sleep(5)
base='http://192.168.3.73:8080'
headers={'Authorization':'Bearer '+Path('/home/bjwl/strata-dev/service/api-key').read_text().strip()}
started=time.monotonic()
while time.monotonic()-started < 2400:
    try:
        h=requests.get(base+'/health',headers=headers,timeout=5)
        if h.ok and h.json().get('loaded'): break
    except requests.RequestException: pass
    time.sleep(5)
else: raise RuntimeError('Restored service did not become ready')
result={'health':h.json()}
write_json(root/'final-service-validation.json',result)
assert h.json()['max_context']==65536,h.json()
r=requests.get(base+'/v1/models',timeout=10)
result['unauthenticated_models_status']=r.status_code
assert r.status_code==401,r.status_code
rows=[json.loads(line) for line in (root/'q4-64k/requests.jsonl').read_text().splitlines()]
large=next(r['request'] for r in rows if r['case']=='64k/cold_retrieval')
large=dict(large,max_tokens=4096,stream=False)
r=requests.post(base+'/v1/chat/completions',json=large,headers=headers,timeout=60)
result['over_budget']={'status':r.status_code,'body':r.json()}
write_json(root/'final-service-validation.json',result)
assert r.status_code==400, result['over_budget']
body={'model':'strata','messages':[{'role':'user','content':'What is 17 times 19? Reply with only the number.'}],
      'reasoning_effort':'none','temperature':0,'max_tokens':16}
row=request(base,body,headers=headers)
result['arithmetic']=row
result['complete']=row['content'].strip()=='323' and row['final']['choices'][0]['finish_reason']=='stop'
write_json(root/'final-service-validation.json',result)
assert result['complete'],row['content']
print('Authenticated Q4 64K service verified; excess context budget rejected; arithmetic correct.',flush=True)
