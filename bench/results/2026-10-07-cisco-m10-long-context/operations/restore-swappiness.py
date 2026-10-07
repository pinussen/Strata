import json,time
from pathlib import Path
r=Path('/home/bjwl/strata-dev/long-context');end=time.monotonic()+14400
while time.monotonic()<end:
 p=r/'final-service-validation.json'
 if p.exists() and json.loads(p.read_text()).get('health',{}).get('loaded'): break
 time.sleep(5)
sysctl=Path('/proc/sys/vm/swappiness');current=int(sysctl.read_text())
old=json.loads((r/'swappiness-adjustment.json').read_text())['previous_swappiness']
if current==1: sysctl.write_text(str(old)+'\n')
(r/'swappiness-restoration.json').write_text(json.dumps({'time':time.time(),'before_restore':current,'restored_swappiness':int(sysctl.read_text()),'original':old},indent=2)+'\n')
