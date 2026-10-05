"""Reproducible M10 HTTP benchmarks with streamed latency and GPU/guest telemetry.

Run on the GPU guest with its Strata venv. Each output directory is new, owns one
localhost server, and retains requests, responses, config, logs and telemetry.
No model downloads or system configuration changes are made by this script.
"""
import argparse
import csv
import datetime
import json
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time

import psutil
import requests

PROMPTS = {
    "code": "Write a Python function that merges two sorted lists into one sorted list without using sorted(). Include a docstring and three assert-based examples. Explain its time complexity briefly.",
    "prose": "Explain in four detailed paragraphs how a refrigerator moves heat from inside to outside. Cover the compressor, condenser, expansion valve and evaporator. Use plain language.",
    "swedish": "Förklara på svenska hur en värmepump fungerar. Skriv fyra tydliga stycken om köldmedium, kompressor, värmeväxlare och varför utomhustemperaturen påverkar effektiviteten.",
}


def write_json(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def telemetry(out, stop, phase):
    fields = "index,temperature.gpu,power.draw,memory.used,utilization.gpu,clocks.current.sm,clocks.current.memory"
    with (out / "telemetry.jsonl").open("w") as f:
        psutil.cpu_percent()
        while not stop.is_set():
            row = {"time": time.time(), "phase": phase[0], "cpu_percent": psutil.cpu_percent(),
                   "mem_available_bytes": psutil.virtual_memory().available,
                   "swap_used_bytes": psutil.swap_memory().used}
            try:
                r = subprocess.run(["nvidia-smi", "--query-gpu=" + fields, "--format=csv,noheader,nounits"],
                                   capture_output=True, text=True, timeout=10, check=True)
                row["gpus"] = [dict(zip(fields.split(","), vals)) for vals in
                               csv.reader(r.stdout.splitlines(), skipinitialspace=True)]
                row["engine_rss_bytes"] = sum(p.info["memory_info"].rss for p in
                    psutil.process_iter(["name", "memory_info"]) if p.info["name"] == "strata" and p.info["memory_info"])
            except (subprocess.SubprocessError, psutil.Error) as exc:
                row["telemetry_error"] = str(exc)
            f.write(json.dumps(row) + "\n"); f.flush()
            stop.wait(2)


def request(base, payload):
    start = time.monotonic()
    first = None
    content, reasoning, events = [], [], []
    final = None
    done = False
    with requests.post(base + "/v1/chat/completions", json=dict(payload, stream=True), stream=True,
                       timeout=(10, 1800)) as r:
        r.raise_for_status()
        for line in r.iter_lines(chunk_size=1):
            if not line.startswith(b"data: "):
                continue
            data = line[6:]
            if data == b"[DONE]":
                done = True
                break
            chunk = json.loads(data)
            if "error" in chunk:
                raise RuntimeError(chunk["error"])
            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {})
                text = delta.get("content") or ""
                thought = delta.get("reasoning_content") or ""
                if text or thought:
                    elapsed = time.monotonic() - start
                    if first is None:
                        first = elapsed
                    events.append({"elapsed_s": elapsed, "content_chars": len(text), "reasoning_chars": len(thought)})
                    content.append(text); reasoning.append(thought)
            if chunk.get("usage") or chunk.get("timings"):
                final = chunk
    if not done or final is None or not final.get("timings"):
        raise RuntimeError("Incomplete stream or missing engine timings")
    return {"wall_s": time.monotonic() - start, "first_token_s": first, "content": "".join(content),
            "reasoning": "".join(reasoning), "final": final, "events": events}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--port", type=int, default=8096)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--max-new", type=int, default=192)
    ap.add_argument("--needle-lines", type=int, nargs="*", default=[48, 144])
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    cfg = json.loads(a.config.read_text())
    cfg["log"] = str(a.out / "engine.log")
    cfg["host"], cfg["port"], cfg["open_browser"] = "127.0.0.1", a.port, False
    write_json(a.out / "config.json", cfg)
    write_json(a.out / "manifest.json", {"started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "argv": sys.argv, "vm_memory_bytes": psutil.virtual_memory().total,
               "logical_cpus": psutil.cpu_count(), "prompts": PROMPTS})
    base = f"http://127.0.0.1:{a.port}"
    # Refuse an occupied port before starting an engine that might allocate all the VRAM.
    import socket
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", a.port)) == 0:
            raise RuntimeError(f"Port {a.port} is already occupied")
    stop, phase = threading.Event(), ["startup"]
    monitor = threading.Thread(target=telemetry, args=(a.out, stop, phase), daemon=True)
    monitor.start()
    rows, server = [], None
    status = {"state": "starting", "results": []}
    write_json(a.out / "status.json", status)
    with (a.out / "server.log").open("w") as log:
        try:
            started = time.monotonic()
            server = subprocess.Popen([sys.executable, "-u", "-m", "serve.server", "--engine", "strata",
                "--config", str(a.out / "config.json"), "--host", "127.0.0.1", "--port", str(a.port)],
                cwd=cfg.get("cwd"), stdout=log, stderr=subprocess.STDOUT)
            (a.out / "server.pid").write_text(str(server.pid))
            while time.monotonic() - started < 1800:
                if server.poll() is not None:
                    raise RuntimeError(f"Server exited with {server.returncode}; inspect engine.log")
                try:
                    r = requests.get(base + "/health", timeout=2)
                    if r.ok and r.json().get("loaded"):
                        break
                except requests.RequestException:
                    pass
                time.sleep(2)
            else:
                raise RuntimeError("Server did not become ready in 30 minutes")
            status["startup_s"] = time.monotonic() - started
            jobs = [("warmup", -1, "Count from one to ten in English.", 32)]
            for repeat in range(a.repeats):
                jobs.extend((name, repeat, prompt, a.max_new) for name, prompt in PROMPTS.items())
            for lines in a.needle_lines:
                prompt = "Remember the code word birch.\n" + "This line is filler for testing a longer prompt.\n" * lines
                jobs.append((f"needle_{lines}", 0, prompt + "\nWhat is the code word? Reply with only that word.", 16))
            for name, repeat, prompt, limit in jobs:
                phase[0] = f"{name}/{repeat}"
                payload = {"model": cfg.get("model_name", "strata"), "temperature": 0,
                           "max_tokens": limit, "reasoning_effort": "none", "messages": [
                           {"role": "system", "content": f"Benchmark case {name}, repetition {repeat}. Follow the user's instructions."},
                           {"role": "user", "content": prompt}]}
                status.update(state="request", current=phase[0]); write_json(a.out / "status.json", status)
                row = {"case": name, "repeat": repeat, "request": payload, **request(base, payload)}
                if name.startswith("needle_"):
                    row["correct"] = row["content"].strip().lower().rstrip(".") == "birch"
                    if not row["correct"]:
                        raise RuntimeError(f"Needle check failed: {row['content']!r}")
                rows.append(row)
                with (a.out / "requests.jsonl").open("a") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                short = {"case": name, "repeat": repeat, "first_token_s": row["first_token_s"],
                         "wall_s": row["wall_s"], "timings": row["final"]["timings"]}
                status["results"].append(short)
                write_json(a.out / "status.json", status)
                print(json.dumps(short), flush=True)
            status["medians"] = {name: statistics.median(r["final"]["timings"]["predicted_per_second"]
                for r in rows if r["case"] == name) for name in PROMPTS}
            status.update(state="complete", current=None)
        except BaseException as exc:
            status.update(state="failed", error=str(exc))
            raise
        finally:
            if server is not None and server.poll() is None:
                phase[0] = "shutdown"
                server.terminate()
                try:
                    server.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    status["shutdown_error"] = "SIGTERM timed out; server left for inspection"
            stop.set(); monitor.join(timeout=12)
            write_json(a.out / "status.json", status)


if __name__ == "__main__":
    main()
