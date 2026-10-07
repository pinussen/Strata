"""Measure near-full contexts and follow-ups on one owned localhost Strata server.

Keeps the complete input/output, token counts, engine logs and two-second telemetry.
The synthetic maintenance ledger has distinct records and facts at three positions;
this checks retrieval and prefix reuse, not general long-document comprehension.
"""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time

import psutil
import requests

from run_benchmark import request, telemetry, write_json


def ledger(lines):
    facts = {
        0: "SPECIAL PROJECT ALPHA: access word cedar; replacement inventory 37 units.",
        lines // 2: "SPECIAL PROJECT BETA: access word quartz; replacement inventory 58 units.",
        lines - 1: "SPECIAL PROJECT GAMMA: access word otter; replacement inventory 91 units.",
    }
    records = []
    parts = ["pump", "filter", "valve", "sensor", "compressor", "controller", "fan"]
    for i in range(lines):
        if i in facts:
            records.append(facts[i])
        records.append(f"Routine record {i:05d}: station {i % 137:03d}, {parts[i % len(parts)]} inspected; "
                       f"temperature {16 + i % 19} C, service interval {30 + i % 61} days. "
                       "No replacement was requested. This is an ordinary maintenance record.")
    return "\n".join(records)


def messages(lines, context):
    return [{"role": "system", "content": f"Context benchmark capacity {context}. Read the ledger carefully. "
             "Use only the supplied records and follow the requested output format."},
            {"role": "user", "content": ledger(lines) + "\n\nReturn only a JSON object mapping "
             "ALPHA, BETA and GAMMA to their access words."}]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--context", type=int, required=True)
    ap.add_argument("--kv-resident", type=int, default=0)
    ap.add_argument("--port", type=int, default=8096)
    a = ap.parse_args()
    if a.context < 4096 or a.kv_resident < 0:
        ap.error("context must be >=4096 and kv-resident nonnegative")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", a.port)) == 0:
            raise RuntimeError("Benchmark port occupied")
    a.out.mkdir(parents=True, exist_ok=False)
    for source in (Path(__file__), Path(__file__).with_name("run_benchmark.py")):
        shutil.copyfile(source, a.out / source.name)
    cfg = json.loads(a.config.read_text())
    if cfg.get("api_key"):
        raise ValueError("Use a key-free benchmark config")
    args = cfg["args"]
    args[args.index("--max-context") + 1] = str(a.context)
    if "--kv-resident" in args:
        idx = args.index("--kv-resident")
        del args[idx:idx + 2]
    if a.kv_resident:
        args.extend(["--kv-resident", str(a.kv_resident)])
    cfg.update(host="127.0.0.1", port=a.port, open_browser=False, log=str(a.out / "engine.log"))
    write_json(a.out / "config.json", cfg)
    write_json(a.out / "manifest.json", {
        "started": datetime.datetime.now(datetime.timezone.utc).isoformat(), "argv": sys.argv,
        "vm_memory_bytes": psutil.virtual_memory().total, "logical_cpus": psutil.cpu_count(),
        "context_capacity": a.context, "input_target": a.context - 1536,
        "kv_resident": a.kv_resident, "repetitions": 1,
        "expected_words": {"ALPHA": "cedar", "BETA": "quartz", "GAMMA": "otter"},
        "expected_inventory": {"ALPHA": 37, "BETA": 58, "GAMMA": 91, "TOTAL": 186}})
    base = f"http://127.0.0.1:{a.port}"
    stop, phase = threading.Event(), ["startup"]
    monitor = threading.Thread(target=telemetry, args=(a.out, stop, phase), daemon=True)
    monitor.start()
    status = {"state": "starting", "results": []}
    write_json(a.out / "status.json", status)
    server = None

    def count(conversation):
        body = {"model": "strata", "system": conversation[0]["content"],
                "messages": conversation[1:], "thinking": {"type": "disabled"}}
        r = requests.post(base + "/v1/messages/count_tokens", json=body, timeout=60)
        r.raise_for_status()
        return r.json()["input_tokens"]

    def ask(name, conversation, limit, expected=None):
        phase[0] = name
        counted = count(conversation)
        if counted + limit > a.context:
            raise RuntimeError("Input/output budget exceeds configured context")
        payload = {"model": cfg.get("model_name", "strata"), "temperature": 0,
                   "reasoning_effort": "none", "max_tokens": limit, "messages": conversation}
        status.update(state="request", current=name, counted_prompt_tokens=counted)
        write_json(a.out / "pending-request.json", payload)
        write_json(a.out / "status.json", status)
        row = {"case": name, "counted_prompt_tokens": counted, "request": payload, **request(base, payload)}
        actual = row["final"]["usage"]["prompt_tokens"]
        row["token_count_matches"] = actual == counted
        row["finish_reason"] = row["final"]["choices"][0]["finish_reason"]
        if expected is not None:
            try:
                # Tolerate Markdown fences while retaining the raw answer for inspection.
                answer = row["content"].strip()
                if answer.startswith("```"):
                    answer = answer.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                row["correct"] = json.loads(answer) == expected
            except (ValueError, IndexError):
                row["correct"] = False
        with (a.out / "requests.jsonl").open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        brief = {k: row[k] for k in ("case", "first_token_s", "wall_s", "finish_reason", "token_count_matches")}
        brief.update(timings=row["final"]["timings"], correct=row.get("correct"))
        status["results"].append(brief)
        write_json(a.out / "status.json", status)
        print(json.dumps(brief), flush=True)
        if actual != counted:
            raise RuntimeError(f"Count endpoint/inference mismatch: {counted} vs {actual}")
        return row

    with (a.out / "server.log").open("w") as log:
        try:
            started = time.monotonic()
            server = subprocess.Popen([sys.executable, "-u", "-m", "serve.server", "--engine", "strata",
                "--config", str(a.out / "config.json"), "--host", "127.0.0.1", "--port", str(a.port)],
                cwd=cfg["cwd"], stdout=log, stderr=subprocess.STDOUT)
            (a.out / "server.pid").write_text(str(server.pid))
            while time.monotonic() - started < 1800:
                if server.poll() is not None:
                    raise RuntimeError(f"Server exited with {server.returncode}")
                try:
                    r = requests.get(base + "/health", timeout=2)
                    if r.ok and r.json().get("loaded"):
                        break
                except requests.RequestException:
                    pass
                time.sleep(2)
            else:
                raise RuntimeError("Server startup timeout")
            status["startup_s"] = time.monotonic() - started
            ask("warmup", [{"role": "system", "content": "Warmup."},
                {"role": "user", "content": "What is 17 times 19? Reply with only the number."}], 16)
            low, high = 3, a.context // 20
            while low < high:
                mid = (low + high + 1) // 2
                if count(messages(mid, a.context)) <= a.context - 1536:
                    low = mid
                else:
                    high = mid - 1
            conversation = messages(low, a.context)
            status["ledger_lines"] = low
            row = ask("cold_retrieval", conversation, 128,
                      {"ALPHA": "cedar", "BETA": "quartz", "GAMMA": "otter"})
            conversation += [{"role": "assistant", "content": row["content"]},
                {"role": "user", "content": "Now retrieve the replacement inventory of each SPECIAL PROJECT "
                 "from the original ledger and add them. Return only a JSON object with integer values for "
                 "ALPHA, BETA, GAMMA and TOTAL. Ignore ordinary maintenance records."}]
            row = ask("cached_inventory", conversation, 192,
                      {"ALPHA": 37, "BETA": 58, "GAMMA": 91, "TOTAL": 186})
            conversation += [{"role": "assistant", "content": row["content"]},
                {"role": "user", "content": "Skriv på svenska en sammanhängande överlämningsanteckning "
                 "på 100–130 ord till nästa servicetekniker. Sammanfatta de tre specialprojektens lagerbehov "
                 "och förklara hur de skiljer sig från de vanliga inspektionsposterna. "
                 "Hitta inte på några fakta som saknas i underlaget."}]
            ask("cached_swedish", conversation, 384)
            checks = status["results"]
            status["functional_pass"] = all(r["correct"] is not False and r["finish_reason"] == "stop"
                for r in checks) and all(r["timings"].get("cache_n", 0) > 0
                    for r in checks if r["case"].startswith("cached_"))
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
                    status["shutdown_error"] = "SIGTERM timeout; process left for inspection"
            stop.set()
            monitor.join(timeout=12)
            write_json(a.out / "status.json", status)


if __name__ == "__main__":
    main()
