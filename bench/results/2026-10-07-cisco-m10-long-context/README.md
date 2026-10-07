# Q4 and Q8 with larger contexts on Cisco M10

**Measurement in progress, 2026-10-07.** The 16K Q4 smoke test below is complete.
The main comparison is running with a 65,536-token capacity and approximately 15K,
31K and 64K input tokens on both Q4 and Q8. Unfinished cases have no reported result.

## Completed 16K Q4 smoke test

| Case | Actual prompt tokens | Cached tokens | First text | Generation |
| --- | ---: | ---: | ---: | ---: |
| Retrieve facts at start, middle and end | 14,812 | 0 | 333.82 s | 6.6 tok/s |
| Follow-up: retrieve different facts and add inventory | 14,901 | 14,846 | 7.42 s | 6.6 tok/s |
| Follow-up: Swedish handover note | 15,038 | 14,944 | 13.02 s | 5.3 tok/s |

Both exact JSON retrieval checks pass, including all three inventory values and their
sum. All streams finish normally and the token-count endpoint matches actual inference
counts. The Swedish reply has 130 whitespace-separated words, but confuses record
numbers with station identifiers and adds an unsupported planning claim. See
[manual review](q4-16k/manual-review.json); a completed stream is not a semantic quality pass.

No disk reads were observed during inference. Sampled guest swap remained unchanged at
3,969,024 bytes; maximum GPU temperature was 64°C and minimum available RAM 70.63 GiB.
[Summary](q4-16k/summary.json), [full requests and responses](q4-16k/requests.jsonl),
[telemetry](q4-16k/telemetry.jsonl) and exact configuration/runner/logs are retained.

## Method

Same Cisco VM 104 as the [previous precision comparison](../2026-10-06-cisco-m10-q8-bf16/README.md):
600 GiB configured RAM (590 GiB usable), 24 vCPUs, eight independent Tesla M10 8 GiB devices,
CUDA 12.2 and SM50 build. Q4 means Unsloth UD-Q4_K_XL; Q8 means Unsloth Q8_0 of the same model.

Eight GPUs, layer split 6/12/18/24/30/36/42, int8 KV, prefill 128, speculative window 2,
16 pool workers, GPU reserve 1,536 MiB, greedy generation and thinking disabled. No model
or engine precision changes. No KV streaming is requested. The main comparison holds
capacity at 65,536 for every input size; the initial smoke test used capacity 16,384.

The deterministic synthetic maintenance ledger includes distinct numbered records and
special facts near its start, midpoint and end. Each input targets its context size minus
1,536 tokens, leaving room for replies and follow-ups. Exact token counting sizes the
input before inference; reported inference counts are checked against it. The first
request asks for three access words. The second asks for inventory values not present in
the previous reply and their sum. The third asks for a Swedish handover note.

Each size has one sequence, not a statistical latency distribution or a broad quality
benchmark. "Cold" means no reused conversation tokens, not cold model files. Cache reuse
is checked using the actual assistant replies as conversation history. Raw answers are
saved for manual review. The harness's `functional_pass` covers exact JSON retrieval,
normal stream completion and nonzero prefix reuse; it does not grade summary semantics.

Reproduce on the GPU guest using its venv:

```bash
python bench/m10/run_context_benchmark.py \
  --config /path/to/key-free-model-config.json \
  --out /path/to/new-output-directory \
  --context 65536 --prompt-contexts 16384 32768 65536
python bench/m10/summarize_context.py /path/to/new-output-directory
```

The runner owns a localhost-only server on port 8096 and refuses an occupied port. Stop
other GPU inference engines before running. Public/LAN service credentials are never
copied into benchmark artifacts.
