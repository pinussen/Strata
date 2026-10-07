"""Run on M10 with its venv. No answers/model-order printed; mapping sealed until review.

Stages: prepare (stop interactive Q4, remove verified NAS-backed replicas only),
run (two sequential localhost servers), export (anonymous pairs), restore (Q4).
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

import psutil
import requests

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/bjwl/Strata')
DEV = Path('/home/bjwl/strata-dev')
WORK = DEV / 'blind-quality-20261007'
SOURCE = Path('/models/strata-work/data')
STAGED = Path('/mnt/strata-ram/data')
BF16 = Path('/mnt/strata-large/models/unsloth-bf16')
sys.path.insert(0, str(ROOT / 'bench/m10'))
from run_benchmark import request, write_json

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def inventory():
    return {str(p):dict(size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns,
                        sha256=p.read_text().strip() if p.suffix=='.sha256' else None)
            for p in sorted(BF16.iterdir()) if p.is_file()}

def log_change(action, **kw):
    with (WORK/'changes.jsonl').open('a') as f:
        f.write(json.dumps(dict(time=time.time(),action=action,**kw))+'\n')

def stop_server(pid):
    p=psutil.Process(pid)
    if 'serve.server' not in p.cmdline():
        raise RuntimeError('Recorded PID is not serve.server')
    children=p.children(recursive=True)
    p.terminate()
    gone,alive=psutil.wait_procs([p]+children,timeout=50)
    if alive:
        raise RuntimeError('Server/engine did not exit; no force kill performed')

def prepare():
    WORK.mkdir(exist_ok=False)
    write_json(WORK/'bf16-before.json',inventory())
    write_json(WORK/'memory-before.json',dict(psutil.virtual_memory()._asdict(),swap=psutil.swap_memory()._asdict()))
    shutil.copy2(DEV/'service/server.json',WORK/'interactive-private.json')
    (WORK/'interactive-private.json').chmod(0o600)
    pid=int((DEV/'service/server.pid').read_text())
    stop_server(pid)
    log_change('stop_interactive_server',pid=pid)
    # Stager's manifest is the provenance of these disposable copies. Never touch BF16.
    manifest=json.loads((STAGED/'.strata-staged.json').read_text())
    targets=sorted((STAGED/'models/unsloth-ud-q4_k_xl').glob('*.gguf'))
    if len(targets)!=4:
        raise RuntimeError('Expected exactly four staged Q4 GGUF shards')
    for p in targets:
        rel=str(p.relative_to(STAGED)); src=SOURCE/rel; st=src.stat()
        sig=dict(source=str(src),size=st.st_size,mtime_ns=st.st_mtime_ns)
        if manifest.get(rel)!=sig or p.stat().st_size!=st.st_size:
            raise RuntimeError('Staged provenance mismatch: '+rel)
    for p in targets:
        src=SOURCE/p.relative_to(STAGED)
        log_change('remove_disposable_q4_replica',path=str(p),restore_from=str(src),bytes=p.stat().st_size,
                   verification='source exists; size and source mtime match staging manifest; copy size matches')
        p.unlink()
    if inventory()!=json.loads((WORK/'bf16-before.json').read_text()):
        raise RuntimeError('BF16 inventory changed')
    write_json(WORK/'memory-prepared.json',dict(psutil.virtual_memory()._asdict(),swap=psutil.swap_memory()._asdict()))
    configs={}
    for model,path in [('Q4',DEV/'bench-configs/unsloth-ud-q4_k_xl-8gpu-base.json'),
                       ('Q8',DEV/'q8-bf16/strata-q8-source.json')]:
        cfg=json.loads(path.read_text())
        # MTP uses the same already staged small runtime on both sides.
        cfg['args'][cfg['args'].index('--mtp')+1]=str(STAGED/'mtp/rt')
        cfg.update(host='127.0.0.1',port=8097,model_name='blind-model',open_browser=False)
        cfg.pop('api_key',None)
        configs[model]=cfg
    def neutral(c):
        c=json.loads(json.dumps(c)); c.pop('log',None); c.pop('tokenizer',None)
        for flag in ['--pack','--native']:
            c['args'][c['args'].index(flag)+1]='MODEL'
        return c
    if neutral(configs['Q4'])!=neutral(configs['Q8']):
        raise RuntimeError('Non-model settings differ')
    order=['Q4','Q8']
    secrets.SystemRandom().shuffle(order)
    suite=json.loads((HERE/'suite.json').read_text())
    key={'order':order,'pairs':{c['id']:secrets.choice([0,1]) for c in suite}}
    write_json(WORK/'key-private.json',key); (WORK/'key-private.json').chmod(0o600)
    write_json(WORK/'configs-private.json',configs)
    (WORK/'commitment.sha256').write_text(digest(WORK/'key-private.json')+'\n')
    print('Prepared; BF16 unchanged; mapping committed by SHA256.',flush=True)

def monitor(out,stop,phase,server):
    with (out/'telemetry.jsonl').open('w') as f:
        while not stop.is_set():
            vm=psutil.virtual_memory(); sw=psutil.swap_memory()
            row=dict(time=time.time(),phase=phase[0],ram_total_bytes=vm.total,
                     ram_available_bytes=vm.available,ram_used_bytes=vm.used,
                     swap_used_bytes=sw.used,swap_sin_bytes=sw.sin,swap_sout_bytes=sw.sout)
            try:
                procs=[psutil.Process(server.pid)]+psutil.Process(server.pid).children(recursive=True)
                row['rss_bytes']=sum(p.memory_info().rss for p in procs)
                row['engine_rss_bytes']=sum(p.memory_info().rss for p in procs if p.name()=='strata')
                row['read_bytes']=sum(p.io_counters().read_bytes for p in procs)
                r=subprocess.run(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu,temperature.gpu',
                    '--format=csv,noheader,nounits'],capture_output=True,text=True,check=True,timeout=8)
                row['gpus']=[dict(zip(['index','memory_mib','utilization_percent','temperature_c'],map(float,x)))
                             for x in csv.reader(r.stdout.splitlines(),skipinitialspace=True)]
            except (psutil.Error,subprocess.SubprocessError) as e:
                row['error']=str(e)
            f.write(json.dumps(row)+'\n'); f.flush()
            stop.wait(2)

def run():
    configs=json.loads((WORK/'configs-private.json').read_text())
    key=json.loads((WORK/'key-private.json').read_text())
    suite=json.loads((HERE/'suite.json').read_text())
    base='http://127.0.0.1:8097'
    for block,model in enumerate(key['order']):
        out=WORK/f'block-{block}';out.mkdir(exist_ok=False)
        cfg=configs[model];cfg['log']=str(out/'engine.log')
        write_json(out/'config.json',cfg)
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',8097))==0:raise RuntimeError('Port occupied')
        status=dict(state='loading',block=block,complete=0)
        write_json(WORK/'status.json',status)
        log=(out/'server.log').open('w')
        server=subprocess.Popen([sys.executable,'-u','-m','serve.server','--engine','strata',
             '--config',str(out/'config.json'),'--host','127.0.0.1','--port','8097'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        stop=threading.Event();phase=['startup']
        thread=threading.Thread(target=monitor,args=(out,stop,phase,server),daemon=True);thread.start()
        try:
            deadline=time.monotonic()+2400
            while time.monotonic()<deadline:
                if server.poll() is not None:raise RuntimeError('Server failed loading')
                try:
                    if requests.get(base+'/health',timeout=2).json().get('loaded'):break
                except requests.RequestException:pass
                time.sleep(2)
            else:raise RuntimeError('Load timeout')
            # Warmup is not a scored prompt; deliberately distinct from all 32 cases.
            phase[0]='warmup'
            payload=dict(model='blind-model',temperature=0,seed=20261007,reasoning_effort='none',
                         max_tokens=32,messages=[dict(role='user',content='Svara endast: Klar för provet.')])
            write_json(out/'warmup.json',request(base,payload))
            for case in suite:
                # Fail before a scored request if the prepared context cannot contain its budget.
                system=f"Prov {case['id']}. Följ användarens instruktioner. Ange osäkerhet när underlag saknas."
                payload=dict(model='blind-model',temperature=0,seed=20261007,reasoning_effort='none',
                    max_tokens=case['max_tokens'],messages=[dict(role='system',content=system),dict(role='user',content=case['prompt'])])
                phase[0]=case['id']
                status.update(state='request',case=case['id']);write_json(WORK/'status.json',status)
                row=dict(id=case['id'],request=payload,**request(base,payload))
                write_json(out/f"{case['id']}.json",row)
                status['complete']+=1;write_json(WORK/'status.json',status)
                print(json.dumps(dict(block=block,complete=status['complete'])),flush=True)
            status['state']='block_complete';write_json(WORK/'status.json',status)
        finally:
            phase[0]='shutdown'
            if server.poll() is None:stop_server(server.pid)
            stop.set();thread.join(timeout=12);log.close()
        # Release only NAS-backed cache for the completed model, never any BF16 pages.
        native=Path(cfg['args'][cfg['args'].index('--native')+1])
        for p in sorted(native.parent.glob('*.gguf')):
            with p.open('rb') as f:os.posix_fadvise(f.fileno(),0,0,os.POSIX_FADV_DONTNEED)
        log_change('advise_drop_completed_model_source_cache',paths=[str(p) for p in sorted(native.parent.glob('*.gguf'))])
    write_json(WORK/'status.json',dict(state='complete',pairs=len(suite)))

def export():
    suite=json.loads((HERE/'suite.json').read_text())
    key=json.loads((WORK/'key-private.json').read_text())
    out=WORK/'blind';out.mkdir(exist_ok=False)
    for c in suite:
        records=[json.loads((WORK/f'block-{b}'/f"{c['id']}.json").read_text()) for b in range(2)]
        a=key['pairs'][c['id']]
        pair=dict(id=c['id'],category=c['category'],prompt=c['prompt'],
                  A=dict(content=records[a]['content'],reasoning=records[a]['reasoning']),
                  B=dict(content=records[1-a]['content'],reasoning=records[1-a]['reasoning']))
        write_json(out/f"{c['id']}.json",pair)
    print('Anonymous pairs exported, without timings or model identifiers.',flush=True)

def restore():
    if list(p for p in psutil.process_iter(['name']) if p.info['name']=='strata'):
        raise RuntimeError('Engine still running')
    # Exact saved interactive config remains private. Stage missing replicas from NAS.
    subprocess.run([sys.executable,str(ROOT/'bench/m10/stage_config.py'),
      '--config',str(DEV/'bench-configs/unsloth-ud-q4_k_xl-8gpu-base.json'),
      '--data',str(SOURCE),'--dest',str(STAGED),'--out',str(WORK/'restaged.json'),'--drop-source-cache'],check=True)
    log_change('restore_q4_replicas_from_nas',destination=str(STAGED/'models/unsloth-ud-q4_k_xl'))
    cfgpath=DEV/'service/server.json'
    if cfgpath.read_bytes()!=(WORK/'interactive-private.json').read_bytes():
        raise RuntimeError('Interactive config changed externally; not overwriting')
    log=(DEV/'service/server.log').open('a')
    p=subprocess.Popen([sys.executable,'-u','-m','serve.server','--engine','strata','--config',str(cfgpath),
        '--host','192.168.3.73','--port','8080'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    (DEV/'service/server.pid').write_text(str(p.pid)+'\n')
    log_change('restart_original_interactive_server',pid=p.pid,config_unchanged=True)
    before=json.loads((WORK/'bf16-before.json').read_text());after=inventory()
    write_json(WORK/'bf16-after.json',after)
    if before!=after:raise RuntimeError('BF16 inventory mismatch')
    print('Original Q4 restarted; BF16 inventory unchanged.',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','run','export','restore'])
    globals()[parser.parse_args().stage]()
