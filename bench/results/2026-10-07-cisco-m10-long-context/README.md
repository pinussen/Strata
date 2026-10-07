# Q4 and Q8 with larger contexts on Cisco M10

**Q4 complete; Q8 complete through 32K and running 64K, 2026-10-07.** Q4 passes all six exact retrieval checks
at approximately 15K, 31K and 64K input tokens with a 65,536-token capacity. A new
64K input waits almost 24 minutes; a follow-up using that history starts in 8.3 seconds.
The LAN service is paused during measurement and will be restored with the verified larger context.

## Main comparison: capacity 65,536

Seconds to first streamed text. Each row is one sequence; model files are loaded before timing.

| Model | Size tested | Actual initial input | Initial reply, s | Inventory follow-up, s | Swedish follow-up, s | Swedish decode, tok/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q4 | 16K | 14,812 | 335.12 | 7.44 | 13.08 | 5.3 |
| Q4 | 32K | 31,224 | 691.76 | 7.67 | 13.11 | 5.5 |
| Q4 | 64K | 63,960 | 1,424.93 | 8.29 | 13.32 | 5.2 |
| Q8 | 16K | 14,812 | 428.77 | 8.19 | 11.01 | 4.8 |
| Q8 | 32K | 31,224 | 850.51 | 8.33 | 10.74 | 4.8 |
| Q8 | 64K | Pending | — | — | — | — |

Q4's initial inputs have zero reused tokens. The inventory follow-ups reuse 14,846,
31,258 and 63,994 tokens respectively and read only 55 new tokens. All three access-word
objects and all three inventory/sum objects match exactly. All replies finish normally.
The three Swedish replies have 127, 105 and 120 whitespace-separated words (requested:
100–130). At 16K, the summary confuses record and station numbers; the 32K and 64K
range claims match the ledger. See [manual review](q4-64k/manual-review.json).

The engine's sampled `read_bytes` counter is unchanged during Q4 inference. Swap allocation
stays at 3,969,024 bytes; this is not a swap-I/O-counter measurement. Maximum sampled engine
RSS is 102.08 GiB, minimum available RAM 70.25 GiB, maximum GPU usage 7,118 MiB on any one
GPU and maximum GPU temperature 67°C. [Per-case summary](q4-64k/summary.json) includes
individual GPU peaks. [Requests and responses](q4-64k/requests.jsonl) and
[telemetry](q4-64k/telemetry.jsonl) retain the full evidence.

## Q8 observations so far

All four completed JSON checks at 16K/32K pass. Q8's 16K Swedish summary makes the same
station/record-number mistake as Q4. Its 32K summary has the correct record range and
quantities, but is 98 words against a requested minimum of 100.
[Review](q8-64k/manual-review.json), [responses](q8-64k/requests.jsonl),
[partial summary](q8-64k/summary.json).

Q8's cold startup takes 1,254.21 s after 463 s of PLE pre-reading (exact pre-read time is
in the preparation record). This cannot be compared directly with Q4's already-staged
72.13 s startup: storage state differs. During Q8 loading, swap allocation grows to
879.48 MiB. VM `vm.swappiness` is temporarily lowered from 60 to 1, and `/swap.img` is
cycled to return those pages to RAM. Before the measured questions, swap allocation is
39.734 MiB; sampled swap-in/out counters do not change during the completed request
period. The original VM setting is scheduled for restoration with the LAN service.
See [policy adjustment](swappiness-adjustment.json), [swap reset](swap-reset.json) and
[system counters](q8-system-counters.jsonl). The counter monitor starts partway through
startup; the standard telemetry covers the whole run. All preparation changes occur before
the timed requests. Q4 used the original swappiness setting.

The engine `read_bytes` counter rises 4.36 MiB between the warmup sample and the first
long-prompt sample, then remains unchanged through the subsequent completed questions.
The Q8 64K result and final memory totals are still pending.

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
16 pool workers, GPU reserve 1,536 MiB, greedy generation and thinking disabled. The existing packs and unchanged engine binary are used; only capacity is enlarged. No KV streaming is requested. The main comparison holds
capacity at 65,536 for every input size; the initial smoke test used capacity 16,384.

The deterministic synthetic maintenance ledger includes distinct numbered records and
special facts near its start, midpoint and end. Each input targets its context size minus
1,536 tokens, leaving room for replies and follow-ups. Exact token counting sizes the
input before inference; reported inference counts are checked against it. The first
request asks for three access words. The second asks for inventory values not present in
the previous reply and their sum. The third asks for a Swedish handover note.

Each size has one sequence, in ascending order within one loaded model. Expert caches can
adapt across requests. This is not a statistical latency distribution or a broad quality
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

## Storage preparation

Q4 is measured from tmpfs. Before loading Q8, two disposable Q4 staged shards (57.24 GiB)
are replaced with links to their unchanged NAS originals; source size and modification
time must match the staging manifest. The staging entries are invalidated so the final
standard launcher will recreate real RAM copies. Original Q4/Q8 files and all BF16 files
are preserved. [Preparation record](q8-memory-preparation.json) records the released copies.
Q8 uses NAS sources with a RAM-resident expert arena and locked PLE mapping. Its PLE shard
is scanned before startup; loading/staging time is separate from request latency.
