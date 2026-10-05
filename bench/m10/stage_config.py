"""Copy one prepared model's files to local storage and rewrite its server config.

For M10 experiments, --dest /mnt/strata-ram/data isolates inference from NFS.
That path is a dedicated tmpfs mount on VM 104; /dev/shm can be cleaned at logout.
The destination must have room for the model, its pack and MTP runtime. These
copies are disposable; the source files and original config are never changed.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--drop-source-cache", action="store_true",
                    help="advise the OS to release the copied source files' page cache (Linux)")
    a = ap.parse_args()
    source, dest = a.data.resolve(), a.dest.resolve()
    if source == dest or source in dest.parents or dest in source.parents:
        ap.error("source and destination must be separate directory trees")
    if a.out.resolve() == a.config.resolve():
        ap.error("--out must preserve the original config")
    cfg = json.loads(a.config.read_text())
    roots = [Path(cfg["tokenizer"])]
    args = cfg["args"]
    for flag in ("--pack", "--mtp", "--native", "--ple-gguf"):
        if flag in args:
            p = Path(args[args.index(flag) + 1])
            # Native multi-shard GGUFs resolve their siblings by filename.
            roots.extend(p.parent.glob("*.gguf") if flag == "--native" else [p])
    files = set()
    for p in roots:
        if not p.is_absolute() or not p.exists():
            ap.error(f"missing or non-absolute model path: {p}")
        if p.is_dir():
            files.update(x for x in p.rglob("*") if x.is_file())
        else:
            files.add(p)
    dest.mkdir(parents=True, exist_ok=True)
    marker = dest / ".strata-staged.json"
    previous = json.loads(marker.read_text()) if marker.exists() else {}
    pending = []
    for p in sorted(files):
        rel = str(p.relative_to(source))
        q = dest / rel
        stat = p.stat()
        signature = {"source": str(p), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        if previous.get(rel) == signature and q.is_file() and q.stat().st_size == stat.st_size:
            continue
        pending.append((p, q, rel, signature))
    need = sum(signature["size"] for _, _, _, signature in pending)
    free = shutil.disk_usage(dest).free
    if need > free:
        raise RuntimeError(f"Need {need / 2**30:.1f} GiB free for staging; destination has {free / 2**30:.1f} GiB")
    for p, q, rel, signature in pending:
        q.parent.mkdir(parents=True, exist_ok=True)
        temp = q.with_name(q.name + ".staging")
        print(f"Copying {p} ({signature['size'] / 2**30:.2f} GiB)", flush=True)
        started = time.monotonic()
        with p.open("rb") as src, temp.open("wb") as dst:
            if hasattr(os, "posix_fadvise"):
                os.posix_fadvise(src.fileno(), 0, 0, os.POSIX_FADV_SEQUENTIAL)
            shutil.copyfileobj(src, dst, 8 * 1024**2)
        if temp.stat().st_size != signature["size"]:
            raise RuntimeError(f"Incomplete copy: {temp}")
        temp.replace(q)
        previous[rel] = signature
        marker_temp = marker.with_suffix(".tmp")
        marker_temp.write_text(json.dumps(previous, indent=2) + "\n")
        marker_temp.replace(marker)
        print(f"Copied in {time.monotonic() - started:.1f} s", flush=True)

    if a.drop_source_cache:
        if not hasattr(os, "posix_fadvise"):
            raise RuntimeError("--drop-source-cache requires posix_fadvise")
        for p in sorted(files):
            with p.open("rb") as src:
                os.posix_fadvise(src.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
        print("Released source file cache where the OS permits; files are unchanged", flush=True)

    def rewrite(value):
        if isinstance(value, str) and value.startswith(str(source) + "/"):
            return str(dest / Path(value).relative_to(source))
        if isinstance(value, dict):
            return {k: rewrite(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rewrite(v) for v in value]
        return value

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(rewrite(cfg), indent=2) + "\n")
    print(f"Staged config: {a.out}", flush=True)


if __name__ == "__main__":
    main()
