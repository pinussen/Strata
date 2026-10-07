"""Summarize saved context benchmark requests and sampled memory/temperature."""
import argparse
import json
from pathlib import Path

from run_benchmark import write_json


def summarize(path):
    status = json.loads((path / "status.json").read_text())
    rows = [json.loads(line) for line in (path / "requests.jsonl").read_text().splitlines()]
    samples = [json.loads(line) for line in (path / "telemetry.jsonl").read_text().splitlines()]
    phases = {}
    for row in rows:
        timing = row["final"]["timings"]
        phases[row["case"]] = {
            "prompt_tokens": row["final"]["usage"]["prompt_tokens"],
            "new_prompt_tokens": timing["prompt_n"], "cached_tokens": timing.get("cache_n", 0),
            "first_token_s": row["first_token_s"], "wall_s": row["wall_s"],
            "prompt_tps": timing["prompt_per_second"],
            "completion_tokens": row["final"]["usage"]["completion_tokens"],
            "decode_tps": timing["predicted_per_second"],
            "finish_reason": row["finish_reason"], "correct": row.get("correct"),
            "token_count_matches": row["token_count_matches"],
        }
    gpus = [g for s in samples for g in s.get("gpus", [])]
    inference = [s for s in samples if s["phase"] not in ("startup", "shutdown")]
    reads = [s["engine_read_bytes"] for s in inference if "engine_read_bytes" in s]
    result = {
        "state": status["state"], "functional_pass": status.get("functional_pass"),
        "startup_s": status.get("startup_s"), "cases": phases,
        "max_engine_rss_gib": max(s.get("engine_rss_bytes", 0) for s in samples) / 2**30,
        "min_available_ram_gib": min(s["mem_available_bytes"] for s in samples) / 2**30,
        "min_swap_bytes": min(s["swap_used_bytes"] for s in samples),
        "max_swap_bytes": max(s["swap_used_bytes"] for s in samples),
        "max_gpu_used_mib": max(float(g["memory.used"]) for g in gpus),
        "max_gpu_temperature_c": max(float(g["temperature.gpu"]) for g in gpus),
        "engine_read_bytes_inference_delta": max(reads) - min(reads) if reads else None,
        "telemetry_samples": len(samples),
    }
    write_json(path / "summary.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, nargs="+")
    args = parser.parse_args()
    for run in args.run:
        print(json.dumps({"run": str(run), **summarize(run)}, ensure_ascii=False))
