"""Compare GGUF variants using one pinned llama.cpp server and saved raw streams.

CPU experts and PLE, dense layers split across eight M10 GPUs. Models must already
be staged. Binds only to localhost; saves complete model replies without executing
any generated code. This is a reference-engine result, not a Strata result.
"""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import threading
import time

import psutil
import requests
from run_benchmark import PROMPTS, telemetry, write_json


def request(base, payload):
    started_unix, start = time.time(), time.monotonic()
    first, finish, final, done = None, None, None, False
    content, reasoning, events, chunks = [], [], [], []
    with requests.post(base + '/v1/chat/completions', json=payload, stream=True,
                       timeout=(10, 1800)) as response:
        response.raise_for_status()
        for line in response.iter_lines(chunk_size=1):
            if not line.startswith(b'data: '):
                continue
            if line[6:] == b'[DONE]':
                done = True
                break
            chunk = json.loads(line[6:])
            chunks.append(chunk)
            if 'error' in chunk:
                raise RuntimeError(chunk['error'])
            for choice in chunk.get('choices', []):
                finish = choice.get('finish_reason') or finish
                delta = choice.get('delta', {})
                text = delta.get('content') or ''
                thought = delta.get('reasoning_content') or ''
                if text or thought:
                    elapsed = time.monotonic() - start
                    if first is None:
                        first = elapsed
                    content.append(text)
                    reasoning.append(thought)
                    events.append(dict(elapsed_s=elapsed, content_chars=len(text), reasoning_chars=len(thought)))
            if chunk.get('timings'):
                final = chunk
    if not done or final is None or not final.get('usage') or finish is None:
        raise RuntimeError('Incomplete stream, usage, finish reason or engine timings missing')
    return dict(started_unix=started_unix, wall_s=time.monotonic()-start,
                first_token_s=first, content=''.join(content), reasoning=''.join(reasoning),
                finish_reason=finish, final=final, events=events, raw_chunks=chunks)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--server', type=Path, required=True)
    ap.add_argument('--model', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--variant', required=True)
    ap.add_argument('--source-revision', required=True)
    ap.add_argument('--port', type=int, default=8097)
    ap.add_argument('--repeats', type=int, default=2)
    ap.add_argument('--smoke', action='store_true')
    a = ap.parse_args()
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', a.port)) == 0:
            raise RuntimeError('Benchmark port is occupied')
    a.out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, a.out / 'runner.py')
    shutil.copyfile(Path(__file__).with_name('run_benchmark.py'), a.out / 'run_benchmark.py')
    cmd = [str(a.server), '--model', str(a.model), '--host', '127.0.0.1', '--port', str(a.port),
           '--ctx-size', '4096', '--batch-size', '128', '--ubatch-size', '128',
           '--threads', '16', '--threads-batch', '24', '--parallel', '1',
           '--n-gpu-layers', '99', '--cpu-moe', '--override-tensor', 'per_layer_token_embd.weight=CPU',
           '--split-mode', 'layer', '--tensor-split', '1,1,1,1,1,1,1,1', '--fit', 'off',
           '--load-mode', 'mmap', '--no-repack', '--lazy-mode', 'off',
           '--flash-attn', 'off', '--cache-type-k', 'f16', '--cache-type-v', 'f16',
           '--reasoning-budget', '0', '--reasoning', 'off', '--jinja', '--no-cache-prompt', '--no-context-shift',
           '--chat-template-kwargs', '{"enable_thinking":false}', '--perf']
    write_json(a.out / 'manifest.json', dict(engine='llama.cpp', source_revision=a.source_revision,
               variant=a.variant, started=datetime.datetime.now(datetime.timezone.utc).isoformat(),
               argv=sys.argv, command=cmd, vm_memory_bytes=psutil.virtual_memory().total,
               logical_cpus=psutil.cpu_count(), gpu_indices=list(range(8)), prompts=PROMPTS))
    base = f'http://127.0.0.1:{a.port}'
    stop, phase = threading.Event(), ['startup']
    monitor = threading.Thread(target=telemetry, args=(a.out, stop, phase, ('llama-server',)), daemon=True)
    monitor.start()
    rows, server = [], None
    status = dict(state='starting', results=[])
    write_json(a.out / 'status.json', status)
    try:
        with (a.out / 'server.log').open('w') as log:
            start = time.monotonic()
            server = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            (a.out / 'server.pid').write_text(str(server.pid))
            while time.monotonic() - start < 1800:
                if server.poll() is not None:
                    raise RuntimeError(f'Server exited with {server.returncode}; inspect server.log')
                try:
                    if requests.get(base + '/health', timeout=2).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(2)
            else:
                raise RuntimeError('Startup exceeded 30 minutes')
            status['startup_s'] = time.monotonic() - start
            jobs = [('warmup', -1, 'Count from one to ten in English.', 32)]
            if not a.smoke:
                for repeat in range(a.repeats):
                    jobs.extend((name, repeat, prompt, 192) for name, prompt in PROMPTS.items())
                for lines in (48, 144, 350):
                    jobs.append((f'needle_{lines}', 0, 'Remember the code word birch.\n' +
                        'This line is filler for testing a longer prompt.\n' * lines +
                        '\nWhat is the code word? Reply with only that word.', 16))
                jobs.extend([
                    ('arithmetic', 0, 'What is 17 times 19? Reply with only the number.', 16),
                    ('swedish_complete', 0, 'Svara på svenska med högst fyra meningar: Varför brukar en '
                     'luftvärmepump bli mindre effektiv när det är kallare utomhus?', 256),
                    ('python_complete', 0, 'Return only Python code defining merge_sorted(a, b). '
                     'Merge two sorted lists without sorted(), keep duplicates, and do not change the input lists. '
                     'No imports, no input/output, no examples.', 512)])
            for name, repeat, prompt, limit in jobs:
                phase[0] = f'{name}/{repeat}'
                payload = dict(model='benchmark', temperature=0, seed=1, max_tokens=limit,
                    stream=True, stream_options={'include_usage': True}, cache_prompt=False,
                    reasoning_effort='none', messages=[
                        dict(role='system', content=f"Benchmark case {name}, repetition {repeat}. Follow the user's instructions."),
                        dict(role='user', content=prompt)])
                status.update(state='request', current=phase[0])
                write_json(a.out / 'status.json', status)
                row = dict(case=name, repeat=repeat, request=payload, **request(base, payload))
                if name.startswith('needle_'):
                    row['correct'] = row['content'].strip().lower().rstrip('.') == 'birch'
                elif name == 'arithmetic':
                    row['correct'] = row['content'].strip() == '323'
                if name.endswith('_complete'):
                    row['complete'] = row['finish_reason'] == 'stop'
                if name == 'python_complete':
                    (a.out / 'generated-python.txt').write_text(row['content'])
                rows.append(row)
                with (a.out / 'requests.jsonl').open('a') as f:
                    f.write(json.dumps(row, ensure_ascii=False) + '\n')
                short = {key: row[key] for key in ('case', 'repeat', 'first_token_s', 'wall_s', 'finish_reason')}
                short['timings'] = row['final']['timings']
                for key in ('correct', 'complete'):
                    if key in row:
                        short[key] = row[key]
                status['results'].append(short)
                write_json(a.out / 'status.json', status)
                print(json.dumps(short), flush=True)
            status['medians'] = {name: statistics.median(r['final']['timings']['predicted_per_second']
                for r in rows if r['case'] == name) for name in PROMPTS if any(r['case'] == name for r in rows)}
            status.update(state='complete', current=None,
                checks_passed=all(r.get('correct', True) and r.get('complete', True) for r in rows))
    except BaseException as exc:
        status.update(state='failed', error=str(exc))
        raise
    finally:
        if server is not None and server.poll() is None:
            phase[0] = 'shutdown'
            server.terminate()
            try:
                server.wait(timeout=45)
            except subprocess.TimeoutExpired:
                status['shutdown_error'] = 'SIGTERM timed out; server left for inspection'
        stop.set()
        monitor.join(timeout=12)
        write_json(a.out / 'status.json', status)


if __name__ == '__main__':
    main()
