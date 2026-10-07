import json,time,pathlib,psutil
root=pathlib.Path('/home/bjwl/strata-dev/long-context')
with (root/'q8-system-counters.jsonl').open('w') as f:
 while True:
  state=json.loads((root/'q8-64k/status.json').read_text())
  swap=psutil.swap_memory(); net=psutil.net_io_counters()
  row={'time':time.time(),'state':state['state'],'phase':state.get('current'), 'swap_used_bytes':swap.used,'swap_in_bytes':swap.sin,'swap_out_bytes':swap.sout,'net_received_bytes_all_interfaces':net.bytes_recv,'available_ram_bytes':psutil.virtual_memory().available}
  f.write(json.dumps(row)+'\n');f.flush()
  if state['state'] in ('complete','failed'): break
  time.sleep(5)
