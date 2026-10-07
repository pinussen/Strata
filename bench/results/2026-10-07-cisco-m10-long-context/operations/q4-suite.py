import json, pathlib, subprocess, time, psutil
root=pathlib.Path('/home/bjwl/strata-dev/long-context')
while True:
    state=json.loads((root/'q4-16k/status.json').read_text())
    if state['state'] in ('complete','failed'): break
    time.sleep(5)
assert state['state']=='complete',state
for ctx in (65536,):
    assert not any(p.info['name']=='strata' and p.status()!=psutil.STATUS_ZOMBIE for p in psutil.process_iter(['name'])), 'Previous engine still alive'
    out=root/f'q4-{ctx//1024}k'
    cmd=['/home/bjwl/strata-dev/venv/bin/python','-u','/home/bjwl/Strata/bench/m10/run_context_benchmark.py','--config','/home/bjwl/strata-dev/q8-bf16/q4-staged.json','--out',str(out),'--context',str(ctx),'--prompt-contexts','16384','32768','65536']
    with (root/f'q4-{ctx//1024}k-driver.log').open('w') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
print('Q4 context suite complete',flush=True)
