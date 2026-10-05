"""Save functional checks against an already running localhost M10 server.

Exercises complete replies, a prompt close to the configured 4K context limit,
and a follow-up using the same conversation. Does not start or stop the server.
Generated Python is saved for review; this script never executes model output.
"""
import argparse
import json
from pathlib import Path
import shutil
import threading

from run_benchmark import request, telemetry, write_json


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--api-key-file", type=Path)
    a = ap.parse_args()
    headers = ({"Authorization": "Bearer " + a.api_key_file.read_text().strip()}
               if a.api_key_file else None)
    a.out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, a.out / "checker.py")
    stop, phase = threading.Event(), ["checks"]
    monitor = threading.Thread(target=telemetry, args=(a.out, stop, phase), daemon=True)
    monitor.start()
    status = {"state": "running", "checks": []}
    write_json(a.out / "status.json", status)

    def ask(name, messages, limit):
        phase[0] = name
        payload = {"model": "strata", "temperature": 0, "reasoning_effort": "none",
                   "max_tokens": limit, "messages": messages}
        row = {"case": name, "request": payload,
               **request(f"http://127.0.0.1:{a.port}", payload, headers=headers)}
        with (a.out / "requests.jsonl").open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if row["final"]["choices"][0]["finish_reason"] != "stop":
            raise RuntimeError(f"{name}: incomplete answer")
        print(name, repr(row["content"]), row["final"]["timings"], flush=True)
        status["checks"].append({"case": name, "timings": row["final"]["timings"],
                                 "first_token_s": row["first_token_s"]})
        write_json(a.out / "status.json", status)
        return row

    def messages(prompt):
        return [{"role": "system", "content": "Live validation. Follow the user's instructions."},
                {"role": "user", "content": prompt}]

    try:
        row = ask("arithmetic", messages("What is 17 times 19? Reply with only the number."), 16)
        if row["content"].strip() != "323":
            raise RuntimeError("Arithmetic check failed")
        ask("swedish_complete", messages("Svara på svenska med högst fyra meningar: Varför brukar en "
            "luftvärmepump bli mindre effektiv när det är kallare utomhus?"), 256)
        row = ask("python_complete", messages("Return only Python code defining merge_sorted(a, b). "
            "Merge two sorted lists without sorted(), keep duplicates, and do not change the input lists. "
            "No imports, no input/output, no examples."), 512)
        (a.out / "generated-python.txt").write_text(row["content"])
        conversation = messages("Remember the code word birch.\n" +
            "This line is filler for testing a longer prompt.\n" * 350 +
            "\nWhat is the code word? Reply with only that word.")
        row = ask("near_4k_context", conversation, 16)
        if row["content"].strip().lower().rstrip(".") != "birch":
            raise RuntimeError("Near-4K code-word check failed")
        conversation += [{"role": "assistant", "content": row["content"]},
                         {"role": "user", "content": "Repeat the code word. Only the word."}]
        row = ask("context_reuse", conversation, 16)
        if row["content"].strip().lower().rstrip(".") != "birch":
            raise RuntimeError("Follow-up code-word check failed")
        if row["final"]["timings"].get("cache_n", 0) <= 0:
            raise RuntimeError("Follow-up did not reuse the prompt cache")
        status["state"] = "complete"
    except BaseException as exc:
        status.update(state="failed", error=str(exc))
        raise
    finally:
        stop.set(); monitor.join(timeout=12)
        write_json(a.out / "status.json", status)


if __name__ == "__main__":
    main()
