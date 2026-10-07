"""Checks anonymous answers. Run only after manual review of generated Python.

No generated shell/Ansible/Terraform operations are executed. Python is run with
an import allowlist, manual inspection, resource limits and a scrubbed environment.
This is not a security sandbox for adversarial Python.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent

def python_source(text):
    blocks=re.findall(r'```(?:python|py)?\s*\n(.*?)```',text,re.S)
    return '\n\n'.join(blocks) if blocks else text.strip()

def check_safe(source):
    tree=ast.parse(source)
    forbidden={'open','exec','eval','compile','__import__','input','breakpoint','globals','locals',
               'getattr','setattr','delattr','vars','help','exit','quit'}
    for n in ast.walk(tree):
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            names=[a.name for a in n.names] if isinstance(n,ast.Import) else [n.module]
            if any(x not in {'heapq','re','collections','typing','bisect'} for x in names):
                raise ValueError('Unapproved import')
        if isinstance(n,ast.Name) and (n.id in forbidden or n.id.startswith('__')):
            raise ValueError('Unapproved builtin/name')
        if isinstance(n,ast.Attribute) and n.attr.startswith('__'):
            raise ValueError('Unapproved attribute')
    return tree

HARNESS='''
import copy, json, random, resource, sys
resource.setrlimit(resource.RLIMIT_CPU,(3,3))
resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
resource.setrlimit(resource.RLIMIT_FSIZE,(1024**2,1024**2))
source=open(sys.argv[1]).read()
spec=json.load(open(sys.argv[2]))
scope={}
exec(compile(source,'<anonymous-answer>','exec'),scope)
fn=scope[spec['function']]
failures=[]; passed=0
def trial(args,expected=None,error=False):
    global passed
    original=copy.deepcopy(args)
    try:
        got=fn(*args)
        if error: raise AssertionError('expected ValueError')
        if json.loads(json.dumps(got)) != expected:
            raise AssertionError('got '+repr(got)+' expected '+repr(expected))
        if spec.get('unchanged') and args != original:
            raise AssertionError('mutated inputs')
        passed+=1
    except ValueError:
        if error:passed+=1
        else:failures.append(dict(args=original,error='unexpected ValueError'))
    except Exception as e:failures.append(dict(args=original,error=repr(e)))
for args,expected in spec['cases']:trial(args,expected)
for s in spec.get('errors',[]):trial([s],error=True)
for args in spec.get('error_args',[]):trial(args,error=True)
r=random.Random(741)
name=spec['function']
if name=='window_counts':
    for _ in range(100):
        xs=sorted(r.randrange(-10,20) for _ in range(r.randrange(30)))
        w=r.randrange(1,9)
        expected=[sum(t-w < x <= t for x in xs[:i+1]) for i,t in enumerate(xs)]
        trial([xs,w],expected)
if name=='merge_intervals':
    for _ in range(100):
        xs=[sorted([r.randrange(-12,13),r.randrange(-12,13)]) for _ in range(r.randrange(15))]
        # independent connected-component closure of intersecting intervals
        groups=[list(x) for x in xs]
        changed=True
        while changed:
            changed=False
            for i in range(len(groups)):
                for j in range(i+1,len(groups)):
                    a,b=groups[i],groups[j]
                    if max(a[0],b[0])<=min(a[1],b[1]):
                        groups[i]=[min(a[0],b[0]),max(a[1],b[1])]
                        groups.pop(j);changed=True;break
                if changed:break
        trial([xs],sorted(groups))
if name=='topo':
    import itertools
    for _ in range(35):
        nodes=list('abcde')[:r.randrange(1,6)]
        edges=[(u,v) for u in nodes for v in nodes if u!=v and r.random()<.14]
        if edges: edges.append(edges[0])
        valid=[list(p) for p in itertools.permutations(nodes)
               if all(p.index(u)<p.index(v) for u,v in edges)]
        trial([nodes,edges],min(valid) if valid else None,error=not valid)
if name=='parse_size':
    for unit,mult in [('B',1),('KiB',1024),('MiB',1048576)]:
        for n in [0,1,17,10**30]:trial([str(n)+unit],n*mult)
print(json.dumps(dict(passed=passed,failed=len(failures),failures=failures),ensure_ascii=False))
'''

def code_check(text,spec):
    source=python_source(text)
    try:check_safe(source)
    except (ValueError,SyntaxError) as e:return dict(error=str(e),passed=0,failed=1)
    with tempfile.TemporaryDirectory(prefix='m10-blind-code-') as tmp:
        p=Path(tmp);(p/'answer.py').write_text(source);(p/'spec.json').write_text(json.dumps(spec));(p/'harness.py').write_text(HARNESS)
        try:
            r=subprocess.run([sys.executable,'-I',str(p/'harness.py'),str(p/'answer.py'),str(p/'spec.json')],
                cwd=p,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},capture_output=True,text=True,timeout=6)
            if r.returncode:return dict(error=r.stderr[-2000:],passed=0,failed=1,returncode=r.returncode)
            return dict(json.loads(r.stdout.splitlines()[-1]),source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                        extra_stdout='\n'.join(r.stdout.splitlines()[:-1]))
        except subprocess.TimeoutExpired:return dict(error='time limit',passed=0,failed=1)

def text_checks(id,text):
    out={'word_count':len(text.split())}
    if id in ['17','20']:
        lo,hi=(60,85) if id=='17' else (70,100)
        out['word_limit_ok']=lo<=out['word_count']<=hi
    if id=='17':out['exact_ending_ok']=text.rstrip().endswith('Tack för ditt tålamod.')
    if id=='19':
        out['word_limit_ok']=out['word_count']<=65
        out['three_bullets_ok']=len(re.findall(r'^\s*[-*•]\s',text,re.M))==3
    if id in ['21','24','25']:
        expected={
          '21':dict(owner='Åsa',ports=[80,443,8080],tls=True,note=None),
          '24':dict(ticket='INC-741',severity='high'),
          '25':dict(owner='Mira',retry_limit=6,region='eu-north',support_code='BJÖRK-27')}[id]
        try:
            obj=json.loads(text)
            out['strict_json_valid']=True
            out['expected_values_ok']=obj==expected
            if id=='21':
                out['key_order_ok']=isinstance(obj,dict) and list(obj)==list(expected)
                out['types_ok']=isinstance(obj,dict) and type(obj.get('tls')) is bool and obj.get('note') is None
        except (ValueError,TypeError):out.update(strict_json_valid=False,expected_values_ok=False)
    if id in ['22','23']:
        expected={'22':'name;port\nepsilon;8000\ndelta;9090\nzeta;443\ngamma;8443',
                  '23':'B -> D -> A -> C -> E\nKontrollerat: 5 steg'}[id]
        out['exact_output_ok']=text.strip()==expected
    if id=='18':
        answers=re.findall(r'^\s*[1-6][.)]\s+(.*)',text,re.M)
        out['six_sentences_ok']=len(answers)==6
        expected=['De som arbetar natt får rapporten först.','Vi skickade rapporten till dem.',
                  'Teknikern bad dem att vänta.','De hade redan startat om tjänsten.',
                  'Mellan dig och dem finns ett avtal.','Jag tror att de har rätt.']
        out['exact_sentences_ok']=answers==expected
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run-reviewed-code',action='store_true');args=ap.parse_args()
    suite=json.loads((HERE/'suite.json').read_text());results={}
    for case in suite:
        pair=json.loads((HERE/'blind'/f"{case['id']}.json").read_text());results[case['id']]={}
        for label in ['A','B']:
            text=pair[label]['content'];checks=text_checks(case['id'],text)
            if case['code_tests'] and args.run_reviewed_code:
                checks['code']=code_check(text,case['code_tests'])
            results[case['id']][label]=checks
    (HERE/'automatic-checks.json').write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(results,ensure_ascii=False))

if __name__=='__main__':main()
