import json,time
from pathlib import Path
import requests
messages=[{'role':'user','content':'Remember the code word birch.\n'+('This line is filler for testing a longer prompt.\n'*24)+'\nWhat is the code word? Reply with only that word.'}]
results=[]
for name in ('multiple_prompt_chunks','conversation_reuse'):
 start=time.monotonic()
 r=requests.post('http://127.0.0.1:8080/v1/chat/completions',json={'model':'strata-m10-coder-iq1_m','messages':messages,'temperature':0,'max_tokens':8,'reasoning_effort':'none'},timeout=900)
 result={'case':name,'elapsed_s':time.monotonic()-start,'http_status':r.status_code,'response':r.json()}
 results.append(result)
 Path('/models/strata-work/logs/context-smoke-8gpu.json').write_text(json.dumps(results,indent=2))
 print(json.dumps(result),flush=True); r.raise_for_status()
 answer=result['response']['choices'][0]['message']['content']
 assert answer.strip().lower().rstrip('.')=='birch',answer
 messages+=[{'role':'assistant','content':answer},{'role':'user','content':'Repeat the code word once more. Reply with only that word.'}]
assert results[0]['response']['usage']['prompt_tokens']>128
assert results[1]['response']['usage']['prompt_tokens_details']['cached_tokens']>0
