import json,subprocess,time
from pathlib import Path
r=Path('/home/bjwl/strata-dev/long-context')
def mem():
 d={k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
 return {'available_bytes':d['MemAvailable'],'swap_used_bytes':d['SwapTotal']-d['SwapFree']}
before=mem();assert before['available_bytes']>20*2**30,before
result={'started':time.time(),'before':before}
try:
 subprocess.run(['swapoff','/swap.img'],check=True,timeout=180)
finally:
 active=Path('/proc/swaps').read_text()
 if '/swap.img' not in active: subprocess.run(['swapon','/swap.img'],check=True,timeout=30)
 result.update(after=mem(),finished=time.time())
 (r/'swap-reset.json').write_text(json.dumps(result,indent=2)+'\n')
print(result,flush=True)
