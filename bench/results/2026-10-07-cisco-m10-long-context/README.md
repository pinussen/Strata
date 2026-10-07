# Q4 and Q8 through 64K context on Cisco M10

Both variants complete the 16K, 32K and 64K input sequences and pass all six exact retrieval
checks each. At 63,960 input tokens, Q4 starts answering after **23 min 45 s** and Q8 after
**29 min 43 s**. A follow-up using that history starts after **8.29 / 8.55 s** respectively.
Large documents fit, but their initial reading time is substantial on this hardware.

**Q4 is restored at `http://192.168.3.73:8080` with 65,536 context and the existing API key.**
All main measurements and LAN checks are complete. The free-text summaries still contain some factual or
instruction-following errors; this is a capacity/latency test, not a general quality ranking.

## Main results

Seconds to first streamed text, with the model already loaded. Every run has a fixed
**65,536-token capacity**; 16K/32K/64K label the input-size targets. Each row is one sequence.

| Model | Input target | Actual initial input | Initial reply, s | Inventory follow-up, s | Swedish follow-up, s | Swedish decode, tok/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q4 | 16K | 14,812 | 335.12 | 7.44 | 13.08 | 5.3 |
| Q4 | 32K | 31,224 | 691.76 | 7.67 | 13.11 | 5.5 |
| Q4 | 64K | 63,960 | 1,424.93 | 8.29 | 13.32 | 5.2 |
| Q8 | 16K | 14,812 | 428.77 | 8.19 | 11.01 | 4.8 |
| Q8 | 32K | 31,224 | 850.51 | 8.33 | 10.74 | 4.8 |
| Q8 | 64K | 63,960 | 1,783.32 | 8.55 | 10.98 | 4.7 |

Cold-prompt throughput is 44.2 / 45.2 / 44.9 tok/s for Q4 and 34.6 / 36.7 / 35.9 for Q8.
Q8's initial waits are 23–28% longer in these cases. Its Swedish follow-up starts sooner,
so Q8 is not slower on every latency measure. Generation is measured on each variant's
own Swedish answer; those texts differ.

All initial requests have zero reused tokens. Inventory follow-ups reuse **14,846 / 31,258 /
63,994 tokens** and read only **55 new tokens**, identically for both variants. Swedish
follow-ups reuse **14,944 / 31,356 / 64,092** and read **94 new tokens**. All replies finish
with `stop`; none reaches its output cap. Input token counts match the count endpoint.

[CSV: all 18 measured requests](metrics.csv) · [Q4 per-case statistics](q4-64k/summary.json) ·
[Q8 per-case statistics](q8-64k/summary.json) · [protocol validation](protocol-validation.json).
Full inputs, outputs, streaming event times, configuration, runner source and engine/server
logs are retained in [Q4](q4-64k/) and [Q8](q8-64k/).

## What the checks establish

The synthetic maintenance ledger has distinct numbered records and special facts near the
start, midpoint and end. The first question retrieves three access words. The second asks
for three inventory quantities, absent from the previous answer, and their sum. All **12
exact JSON checks** pass. The third request asks for a Swedish handover note of 100–130 words.

Manual, unblinded review finds:

- Both 16K Swedish summaries confuse record numbers 000–333 with station identifiers,
  which actually range from 000 to 136.
- Q8's 32K summary gives the correct quantities and record range, but has 98 words.
- Q8's 64K summary asserts that ordinary operations have no inventory withdrawals. The
  source only says no replacement was requested; the stronger claim is not established.
- All six Swedish summaries have the correct three quantities and total. Some add
  operational advice beyond the ledger and contain minor Swedish grammar errors.

Whitespace word counts are Q4 **127 / 105 / 120**, Q8 **117 / 98 / 112**.
[Q4 review](q4-64k/manual-review.json) and [Q8 review](q8-64k/manual-review.json) retain the
case notes. The harness's `functional_pass` covers exact retrieval, stream completion and
prefix reuse; it does not grade summary semantics. Most input text follows a repeated record
format. Varied documents or large source trees can have different throughput and accuracy.

## Hardware, settings and method

Cisco UCSC-C240-M5SX, two Xeon Gold 6248R processors; VM 104 with **600 GiB configured RAM**
(~590 GiB usable), 24 vCPUs and eight independent **Tesla M10 8 GiB GPUs**, SM50. CUDA 12.2,
driver 535.309.01. Q4 is Unsloth UD-Q4_K_XL and Q8 is Unsloth Q8_0 of the same full model.
Model provenance and pack conversion details are in the
[previous precision report](../2026-10-06-cisco-m10-q8-bf16/README.md).

Layer split 6/12/18/24/30/36/42, **int8 KV**, prefill 128, speculative window 2,
16 pool workers, 1,536 MiB GPU reserve, temperature 0 and **thinking disabled**.
No KV streaming is requested. The existing packs and unchanged engine binary are used;
[runtime hashes](runtime-sha256.txt) identify it. At 64K, the GPU expert caches hold 14,409
Q4 or 8,479 Q8 expert slots according to the engine logs.

One warmup and nine requests per model, input sizes in ascending order. Each input targets
its nominal size minus 1,536 tokens, leaving room for replies and follow-ups. Exact counting
sizes the input before inference; actual inference counts are checked afterward. All ten
message payloads match across variants, including assistant history. Only the request's
model identifier differs. The JSON answers are identical; the Swedish answers differ.

Each size has one sequence, not a latency distribution. Expert caches can adapt across
requests. "Cold" means no reused conversation tokens, not cold model files. The initial
[16K-capacity Q4 smoke test](q4-16k/summary.json) is separate: 333.82 s initial text, 7.42 s
inventory follow-up and 5.3 tok/s Swedish generation. Its four requests are not pooled into
the fixed-64K comparison.

## Memory and loading

Two-second telemetry, peaks across each whole main run:

| Observation | Q4 | Q8 |
| --- | ---: | ---: |
| Maximum engine RSS, GiB | 102.08 | 173.83 |
| Minimum available guest RAM, GiB | 70.25 | 26.58 |
| Maximum usage on any one GPU, MiB | 7,118 | 7,226 |
| Maximum GPU temperature, °C | 67 | 59 |

RSS includes mapped files and must not be added again to file-cache/tmpfs usage. The unused
BF16 model's **329.72 GiB** of tmpfs files stays present throughout. Other staged copies differ
between runs, so available RAM is not an isolated measure of model requirements. Per-request,
per-GPU peaks are in the summaries; sampled peaks can miss short transients.

Q4 uses tmpfs files and starts in 72.13 s. Q8 uses NAS sources, a resident expert arena and a
locked PLE mapping. Its PLE shard is first read in **462.69 s**, then startup takes **1,254.21 s**.
Those loading times reflect different storage states and are separate from request latency.
No model downloads or other inference engines run during the measurements.

Q4's observed swap allocation stays at 3.785 MiB; swap-I/O counters were not collected for Q4.
During Q8 loading, allocation reaches **879.48 MiB**. VM `vm.swappiness` is temporarily changed
from 60 to 1, and `/swap.img` is cycled to return those pages to RAM before timed requests.
During the sampled Q8 request period, swap-in is **0 bytes**, swap-out is **851,968 bytes
(0.8125 MiB)**, and allocation ranges from **39.73 to 40.50 MiB**. This is not a zero-swap run.
See [adjustment](swappiness-adjustment.json), [reset](swap-reset.json),
[request-period counter summary](q8-system-summary.json) and
[raw counters](q8-system-counters.jsonl). The extra counter monitor starts partway through
startup; standard telemetry covers the whole run. Q4 used the original swappiness setting. The [restoration record](swappiness-restoration.json)
confirms that the VM is back at its original value of 60.

Q4's engine `read_bytes` counter is unchanged during inference. Q8's increases 4.36 MiB
between the warmup sample and first long-prompt sample, then remains unchanged. These are
process counters, not total machine I/O measurements.

## Storage and operation

Before Q8, two disposable Q4 staged shards (**57.24 GiB**) are replaced with links to their
unchanged NAS originals. Source size and modification time must match the staging manifest;
those staging entries are invalidated to force real RAM copies on restoration. Original
Q4/Q8 files and all BF16 files are preserved. The [preparation record](q8-memory-preparation.json)
and [Q8 cache release](q8-cache-release.json) record these steps. The scripts in
[operations/](operations/) are one-time execution records, not general installation tools.

All four Q4 GGUF shards are real RAM copies again, with their expected total size; no NAS
symlinks remain. The eight BF16 shards are preserved. The final service has one engine,
71.47 GiB available guest RAM and 3,141,632 bytes allocated swap at the recorded snapshot.
[Operating state](final-operating-state.json) records these checks.

[Service validation](final-service-validation.json) confirms a completed arithmetic reply,
HTTP 401 without the key and HTTP 400 for a 63,960-token prompt plus a 4,096-token answer
budget. [The check from outside the GPU guest](external-lan-check.json) confirms the web UI,
authenticated API and loaded 64K model are reachable from the workspace.

The selected Q4 service configuration is
`/home/bjwl/strata-dev/bench-configs/unsloth-ud-q4_k_xl-8gpu-64k.json`.
[Key-free source configurations](source-configs/) retain both variants' settings.
Use [the handoff](../../../docs/M10_LOCAL_HANDOFF.md) for the authenticated LAN launcher.
The 65,536-token limit includes all messages and new output; leave room for continued dialogue.
Keep the same running model and conversation prefix to reuse history. Restarting the model
or changing an early prefix can require reading it again. Choose **Thinking: Off** to match
these measurements.

To run the benchmark on an idle GPU guest with its Strata venv:

```bash
python bench/m10/run_context_benchmark.py \
  --config /path/to/key-free-model-config.json \
  --out /path/to/new-output-directory \
  --context 65536 --prompt-contexts 16384 32768 65536
python bench/m10/summarize_context.py /path/to/new-output-directory
```

It owns a localhost-only server on port 8096 and refuses an occupied port. Stop other GPU
inference first. Credentials are never copied into benchmark artifacts. To verify the saved
main runs and regenerate the CSV:

```bash
python bench/results/2026-10-07-cisco-m10-long-context/validate_results.py
```
