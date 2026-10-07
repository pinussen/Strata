"""One-time experiment driver: preserve NAS originals and all BF16 files."""
import json
import os
from pathlib import Path
import subprocess
import time
import psutil

root = Path('/home/bjwl/strata-dev/long-context')
while True:
    status = root / 'q4-64k/status.json'
    if status.exists():
        state = json.loads(status.read_text())
        if state['state'] in ('complete', 'failed'):
            break
    time.sleep(5)
assert state['state'] == 'complete', state
assert not any(p.info['name'] == 'strata' and p.status() != psutil.STATUS_ZOMBIE
               for p in psutil.process_iter(['name'])), 'Q4 engine still alive'
staging = Path('/mnt/strata-ram/data')
marker = json.loads((staging / '.strata-staged.json').read_text())
records = []
for shard in (3, 4):
    rel = f'models/unsloth-ud-q4_k_xl/Qwen3.8-Flash-Next-UD-Q4_K_XL-{shard:05d}-of-00004.gguf'
    copy = staging / rel
    info = marker[rel]
    source = Path(info['source'])
    assert source.is_file() and not copy.is_symlink()
    original_stat = source.stat()
    assert original_stat.st_size == info['size'] == copy.stat().st_size
    assert original_stat.st_mtime_ns == info['mtime_ns']
    assert str(source).startswith('/models/strata-work/data/')
    # These are only disposable staged duplicates; the verified NAS originals stay intact.
    copy.unlink()
    copy.symlink_to(source)
    records.append({'duplicate': str(copy), 'preserved_source': str(source), **info})
    # Force a real RAM copy during the final standard service restaging.
    marker.pop(rel)
(staging / '.strata-staged.json').write_text(json.dumps(marker, indent=2) + '\n')
report = {'reclaimed_q4_duplicates': records, 'bf16_unchanged': True,
          'available_gib_after_reclaim': psutil.virtual_memory().available / 2**30}
(root / 'q8-memory-preparation.json').write_text(json.dumps(report, indent=2) + '\n')
assert psutil.virtual_memory().available > 185 * 2**30, report
# Scan only Q8's PLE shard. Its RAM-mode mapping is then warm before the timed startup.
ple = Path('/models/strata-work/data/models/unsloth-q8_0/Qwen3.8-Flash-Next-Q8_0-00003-of-00006.gguf')
started = time.monotonic()
with ple.open('rb') as f:
    os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_SEQUENTIAL)
    total = 0
    while chunk := f.read(8 * 1024**2):
        total += len(chunk)
        if total % (1024**3) == 0:
            print(f'Q8 PLE warmup: {total / 2**30:.0f} GiB in {time.monotonic()-started:.0f} s', flush=True)
report.update(ple_bytes_read=total, ple_warmup_s=time.monotonic()-started,
              available_gib_after_ple_warmup=psutil.virtual_memory().available / 2**30)
(root / 'q8-memory-preparation.json').write_text(json.dumps(report, indent=2) + '\n')
cmd = ['/home/bjwl/strata-dev/venv/bin/python', '-u',
       '/home/bjwl/Strata/bench/m10/run_context_benchmark.py',
       '--config', '/home/bjwl/strata-dev/q8-bf16/strata-q8-source.json',
       '--out', str(root / 'q8-64k'), '--context', '65536',
       '--prompt-contexts', '16384', '32768', '65536', '--startup-timeout', '3600']
with (root / 'q8-64k-driver.log').open('w') as log:
    subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
print('Q8 context suite complete', flush=True)
