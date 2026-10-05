import json, sys, time
from pathlib import Path
import requests
n = int(sys.argv[1])
out = Path(f'/models/strata-work/logs/smoke-{n}gpu.json')
cases = [
 ('arithmetic', [{'role':'user','content':'What is 2 + 2? Reply with only the number.'}], 16),
 ('conversation', [{'role':'user','content':'Remember this code word: pinecone.'}, {'role':'assistant','content':'I will remember pinecone.'}, {'role':'user','content':'What was the code word? Reply with only the code word.'}], 16),
 ('code', [{'role':'user','content':'Write a Python function named add that returns the sum of a and b. Reply with only the function.'}], 64),
]
results = []
for name, messages, limit in cases:
 start = time.monotonic()
 r = requests.post('http://127.0.0.1:8080/v1/chat/completions', json={'model':'strata-m10-coder-iq1_m', 'messages':messages, 'max_tokens':limit, 'temperature':0, 'reasoning_effort':'none'}, timeout=900)
 result = {'case':name, 'elapsed_s':time.monotonic()-start, 'http_status':r.status_code, 'response':r.json()}
 results.append(result)
 out.write_text(json.dumps(results, indent=2))
 print(json.dumps(result), flush=True)
 r.raise_for_status()
