"""Summarize saved run_benchmark.py outputs without contacting the model server."""
import argparse
import json
from pathlib import Path
import statistics


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", type=Path, nargs="+")
    a = ap.parse_args()
    for root in a.runs:
        status = json.loads((root / "status.json").read_text())
        requests_path = root / "requests.jsonl"
        rows = [json.loads(s) for s in requests_path.read_text().splitlines()] if requests_path.exists() else []
        tele = [json.loads(s) for s in (root / "telemetry.jsonl").read_text().splitlines()]
        cfg = json.loads((root / "config.json").read_text())
        active = cfg.get("gpu", 0)
        active = [active] if isinstance(active, int) else active
        report = {"run": root.name, "state": status["state"], "startup_s": status.get("startup_s"),
                  "gpu_indices": active, "cases": {}, "telemetry_samples": len(tele)}
        for name in dict.fromkeys(r["case"] for r in rows):
            selected = [r for r in rows if r["case"] == name]
            rates = [r["final"]["timings"]["predicted_per_second"] for r in selected]
            prompt = [r["final"]["timings"]["prompt_per_second"] for r in selected]
            samples = [t for t in tele if t["phase"].split("/")[0] == name]
            gpus = [g for t in samples for g in t.get("gpus", []) if int(g["index"]) in active]

            def numbers(key):
                vals = []
                for g in gpus:
                    try:
                        vals.append(float(g[key]))
                    except (ValueError, KeyError):
                        pass
                return vals

            totals, all_totals = [], []
            for t in samples:
                if not t.get("gpus"):
                    continue
                try:
                    totals.append(sum(float(g["power.draw"]) for g in t.get("gpus", [])
                                      if int(g["index"]) in active))
                    all_totals.append(sum(float(g["power.draw"]) for g in t["gpus"]))
                except ValueError:
                    pass
            report["cases"][name] = {
                "requests": len(selected), "decode_tps_median": statistics.median(rates),
                "decode_tps_min": min(rates), "decode_tps_max": max(rates),
                "prompt_tps_median": statistics.median(prompt),
                "first_token_s_median": statistics.median(r["first_token_s"] for r in selected),
                "completion_tokens": [r["final"]["usage"]["completion_tokens"] for r in selected],
                "finish_reasons": [r["final"]["choices"][0]["finish_reason"] for r in selected],
                "max_temperature_c": max(numbers("temperature.gpu"), default=None),
                "max_vram_used_mib": max(numbers("memory.used"), default=None),
                "active_gpu_power_w_mean": statistics.mean(totals) if totals else None,
                "all_gpu_power_w_mean": statistics.mean(all_totals) if all_totals else None,
                "vm_cpu_percent_mean": statistics.mean(t["cpu_percent"] for t in samples) if samples else None,
            }
        report["min_available_ram_gib"] = min(t["mem_available_bytes"] for t in tele) / 2**30
        report["max_swap_used_bytes"] = max(t["swap_used_bytes"] for t in tele)
        (root / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))


if __name__ == "__main__":
    main()
