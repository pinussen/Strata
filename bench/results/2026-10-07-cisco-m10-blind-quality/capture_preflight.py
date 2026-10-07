"""Run on guest: provenance, token counts and machine inventory without credentials."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path('/home/bjwl/Strata')
WORK=Path('/home/bjwl/strata-dev/blind-quality-20261007')
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from serve.frontend import ChatTemplate
import strata_tokenizer as ST

cfgs=json.loads((WORK/'configs-private.json').read_text())
suite=json.loads(Path('/home/bjwl/strata-dev/suite.json').read_text())
report={}
for model,cfg in cfgs.items():
    p=Path(cfg['tokenizer']);v=json.loads((p/'vocab.json').read_text());tokens=[None]*len(v)
    for t,i in v.items():tokens[i]=t
    tok=ST.Tokenizer(tokens,(p/'merges.txt').read_text().split('\n'),json.loads((p/'token_type.json').read_text()))
    tpl=ChatTemplate(p/'chat_template.jinja');counts={}
    for c in suite:
        messages=[dict(role='system',content=f"Prov {c['id']}. Följ användarens instruktioner. Ange osäkerhet när underlag saknas."),dict(role='user',content=c['prompt'])]
        n=len(tok.encode(tpl.render(messages,reasoning_effort='none',enable_thinking=False),parse_special=True))
        counts[c['id']]=n
        assert n+c['max_tokens']<=4096,(c['id'],n)
    report[model]=dict(counts=counts,tokenizer_sha256={f:hashlib.sha256((p/f).read_bytes()).hexdigest()
                      for f in ['vocab.json','merges.txt','token_type.json','chat_template.jinja']})
(WORK/'context-preflight.json').write_text(json.dumps(report,indent=2)+'\n')
print('Both tokenizers checked; maximum prompt tokens:',*[max(r['counts'].values()) for r in report.values()])
commands={
 'git_head':['git','rev-parse','HEAD'], 'git_status':['git','status','--short'],
 'lscpu':['lscpu'], 'os':['cat','/etc/os-release'], 'memory':['cat','/proc/meminfo'],
 'gpus':['nvidia-smi','--query-gpu=index,name,uuid,memory.total,driver_version','--format=csv'],
 'topology':['nvidia-smi','topo','-m'], 'mounts':['findmnt','/mnt/strata-ram','/mnt/strata-large'],
 'build':['cat','/home/bjwl/strata-dev/build-m10/CMakeCache.txt']}
machine={k:subprocess.run(v,cwd=ROOT,text=True,capture_output=True).stdout for k,v in commands.items()}
files=['serve/server.py','serve/frontend.py','serve/chat_template.jinja','tools/strata_tokenizer.py',
       'src/program/generate.cpp','src/kernels/ngram.cpp','bench/m10/run_benchmark.py']
machine['sha256']={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
machine['sha256']['engine_binary']=hashlib.sha256(Path(cfgs['Q4']['exe']).read_bytes()).hexdigest()
machine['sha256']['suite.json']=hashlib.sha256(Path('/home/bjwl/strata-dev/suite.json').read_bytes()).hexdigest()
(WORK/'machine.json').write_text(json.dumps(machine,indent=2)+'\n')
