"""Download one experimental quantization at a pinned revision, checking its SHA256.

Uses a Hugging Face API manifest saved before the run. Partial files are resumable;
completed files receive a SHA256 marker. This does not add support to the engine.
"""
import argparse
import datetime
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import time
import urllib.request


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', type=Path, required=True)
    ap.add_argument('--variant', choices=['Q8_0', 'BF16'], required=True)
    ap.add_argument('--dest', type=Path, required=True)
    ap.add_argument('--state', type=Path, required=True)
    a = ap.parse_args()
    manifest = json.loads(a.manifest.read_text())
    files = [f for f in manifest['files'] if f['rfilename'].startswith(a.variant + '/')]
    if not files:
        ap.error('No files for variant')
    a.dest.mkdir(parents=True, exist_ok=True)
    a.state.parent.mkdir(parents=True, exist_ok=True)
    completed = []
    start = time.monotonic()

    def state(stage, **extra):
        row = {'stage': stage, 'variant': a.variant, 'revision': manifest['revision'],
               'time': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'elapsed_s': time.monotonic() - start, 'completed': completed, **extra}
        temp = a.state.with_suffix('.tmp')
        temp.write_text(json.dumps(row, indent=2) + '\n'); temp.replace(a.state)

    needed = 0
    for f in files:
        dest = a.dest / Path(f['rfilename']).name
        partial = dest.with_suffix(dest.suffix + '.part')
        needed += max(0, f['size'] - (dest.stat().st_size if dest.exists() else
                                    partial.stat().st_size if partial.exists() else 0))
    if needed + 2 * 1024**3 > shutil.disk_usage(a.dest).free:
        raise RuntimeError('Insufficient space for all shards plus 2 GiB margin')
    try:
        for f in files:
            dest = a.dest / Path(f['rfilename']).name
            partial = dest.with_suffix(dest.suffix + '.part')
            marker = dest.with_suffix(dest.suffix + '.sha256')
            expected = f['lfs']['sha256']
            if dest.exists():
                if dest.stat().st_size == f['size'] and marker.exists() and marker.read_text().strip() == expected:
                    completed.append(dest.name); continue
                raise RuntimeError(f'Existing file is not a verified download: {dest}')
            digest = hashlib.sha256()
            have = 0
            if partial.exists():
                state('hashing_partial', file=dest.name)
                with partial.open('rb') as src:
                    while chunk := src.read(8 * 1024**2):
                        digest.update(chunk); have += len(chunk)
            if have > f['size']:
                raise RuntimeError(f'Partial file exceeds expected size: {partial}')
            url = f"https://huggingface.co/{manifest['repo']}/resolve/{manifest['revision']}/{f['rfilename']}"
            for attempt in range(30):
                if have == f['size']:
                    break
                try:
                    request = urllib.request.Request(url, headers={'Range': f'bytes={have}-',
                                                                  'User-Agent': 'strata-m10-experiment'})
                    with urllib.request.urlopen(request, timeout=60) as response:
                        if have and response.status != 206:
                            raise RuntimeError('Server ignored resume range; partial preserved')
                        if response.status == 206 and not response.headers.get('Content-Range', '').startswith(f'bytes {have}-'):
                            raise RuntimeError('Unexpected response range')
                        last = 0
                        with partial.open('ab' if have else 'wb') as output:
                            while chunk := response.read(8 * 1024**2):
                                if have + len(chunk) > f['size']:
                                    raise RuntimeError('Response exceeds pinned size')
                                output.write(chunk); digest.update(chunk); have += len(chunk)
                                if time.monotonic() - last > 5:
                                    state('downloading', file=dest.name, bytes=have, total_bytes=f['size'])
                                    last = time.monotonic()
                    if have != f['size']:
                        raise OSError('Truncated response')
                except (OSError, http.client.HTTPException) as exc:
                    state('retrying', file=dest.name, bytes=have, attempt=attempt + 1, error=str(exc))
                    time.sleep(10)
            if have != f['size'] or partial.stat().st_size != f['size'] or digest.hexdigest() != expected:
                raise RuntimeError(f'Size/SHA256 mismatch; partial retained: {partial}')
            partial.replace(dest)
            marker.write_text(expected + '\n')
            completed.append(dest.name)
            state('verified', file=dest.name, bytes=have)
            print('Verified', dest.name, have, flush=True)
        state('complete')
    except BaseException as exc:
        state('failed', error=str(exc))
        raise


if __name__ == '__main__':
    main()
