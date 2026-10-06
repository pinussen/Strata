# Q4, Q8 and BF16 on the Cisco M10 server

Both requested higher-precision variants run successfully. Q8 works in Strata after adding
Q8_0 PLE row decoding; BF16 runs in the separate llama.cpp reference engine. Full BF16
inference is not implemented in Strata. These are precision variants of the same full
Qwen3.8-Flash-Next model, not models with different parameter counts.

On this machine, Q4 remains the interactive default. Q8 is 9–13% slower in the measured
Strata generation cases and takes more memory. With identical reference-engine settings,
BF16 generates about 2.64 tok/s versus Q8's 4.52–4.66 and Q4's 4.74–4.77. All functional
checks pass, but these few prompts do not establish a general quality ranking.

## Hardware and method

Cisco UCSC-C240-M5SX, two Xeon Gold 6248R processors and eight independent 8 GiB Tesla M10
CUDA devices (SM50). The host has 692 GiB usable RAM. VM 104 was increased from 256 to
**600 GiB configured RAM**, approximately **590 GiB usable**, retaining 24 vCPUs and one
exposed NUMA node. CUDA 12.2 and driver 535.309.01 were unchanged. See
[VM configuration](vm-104-config.txt) and [hardware notes](../../../docs/M10_HARDWARE.md).

The common reference engine is llama.cpp at `3cf03257f219afbe7334045ff7c6a06ac68c627d`,
compiled for SM50. All three runs use CPU routed experts and PLE, dense layers split across
eight GPUs, 4,096 context, F16 KV, batch/ubatch 128, 16 decode threads, 24 prompt threads,
no speculative decoding, no prompt reuse and no thinking. Downloads and other inference
engines are stopped during measurements.

[Launch settings](reference-settings-comparison.json) match except for model path.
[All 13 request payloads](reference-request-comparison.json) match across variants;
`cache_n` is always zero. Code/English/Swedish each have two replies capped at 192 tokens.
The other requests are warmup, three code-word checks, arithmetic and complete Swedish/Python
answers. Capped replies finish with `length`; they are not treated as completed answers.
Generated Python is saved, manually reviewed, then tested separately.

## Common reference-engine results

Generation medians, tokens/s:

| Case | Q4 | Q8_0 | BF16 |
| --- | ---: | ---: | ---: |
| Code | 4.756 | 4.517 | 2.633 |
| English | 4.769 | 4.656 | 2.639 |
| Swedish | 4.737 | 4.526 | 2.647 |

Time to first streamed text, seconds; medians for the repeated short cases:

| Case | Q4 | Q8_0 | BF16 |
| --- | ---: | ---: | ---: |
| Code, 64 prompt tokens | 11.23 | 13.49 | 21.47 |
| English, 64 prompt tokens | 11.22 | 13.64 | 21.22 |
| Swedish, 83 prompt tokens | 12.50 | 15.12 | 23.99 |
| Code word, 582 prompt tokens | 65.05 | 78.91 | 132.36 |
| Code word, 1,639 prompt tokens | 173.88 | 208.39 | 306.69 |
| Code word, 3,905 prompt tokens | 403.17 | 497.19 | 804.81 |

The longest BF16 prompt therefore waits about 13.4 minutes for its answer. It fits in RAM,
but long-prompt latency is a practical limit with these settings and this hardware.

| Memory/startup observation | Q4 | Q8_0 | BF16 |
| --- | ---: | ---: | ---: |
| Startup after staging/cache warming, s | 12.02 | 18.47 | 28.85 |
| Maximum observed engine RSS, GiB | 108.55 | 180.22 | 333.49 |
| Minimum available guest RAM, GiB | 437.79 | 416.07 | 143.37 |
| Maximum observed GPU temperature, °C | 44 | 44 | 42 |
| Observed guest swap during benchmark, bytes | 0 | 0 | 0 |

Q4 and BF16 files are in tmpfs. Q8 files are on NAS and were scanned to warm the client cache
before launch, taking 63.06 seconds; much was already cached from downloading. These are warm-memory inference measurements, not
cold network-loading measurements. All three engines' disk-read counters remain unchanged
after warmup; small startup/warmup reads are retained in the counter comparison above.
RSS includes mapped model files and is not additional to their tmpfs/cache allocation.
Other staged models differ between runs, so available RAM is not an isolated model-memory
measurement. GPU power in telemetry is not total server power.

Raw requests, responses, exact runner source, server logs, per-case summaries and two-second
telemetry are retained under [Q4](reference-q4/status.json), [Q8](reference-q8/status.json)
and [BF16](reference-bf16/status.json). The reference version string says commit unknown
because source was built from a pinned archive; [binary hashes](reference-binary-sha256.txt)
identify the actual build.

## Functional checks

All three reference variants return the correct code word at 582, 1,639 and 3,905 prompt
tokens, answer `17 × 19` correctly and finish the complete Swedish and Python responses
normally. Each reviewed `merge_sorted` function passes the same 107 cases: sorted output,
retained duplicates, unchanged inputs and a new result list. The saved validators and results
are in each run directory. All three add Markdown fences despite the instruction to return
only Python code.

The Swedish replies are readable. Q4's short answer mixes increased house heat loss into
its efficiency explanation; Q8 and BF16 mention compressor work and defrosting. These are
individual examples, not sufficient evidence of a model-quality advantage. Greedy generation
can still differ across formats and engines because numerical rounding and routing differ.

## Strata Q4 versus Q8

Both [Q4](strata-q4-600g/status.json) and [Q8](strata-q8/status.json) complete nine requests
on the expanded VM. Settings match: eight GPUs, int8 KV, 4,096 context, prefill 128,
speculative window 2, the same MTP draft model, 16 pool threads and 1,536 MiB GPU reserve.
Q4 uses staged tmpfs files; Q8 uses the warm NAS cache. No downloads run during either test.

| Case | Q4 decode tok/s | Q8 decode tok/s | Q4 first text, s | Q8 first text, s |
| --- | ---: | ---: | ---: | ---: |
| Code, median of two | 6.40 | 5.60 | 8.32 | 9.10 |
| English, median of two | 5.65 | 5.15 | 8.40 | 9.08 |
| Swedish, median of two | 5.25 | 4.75 | 12.56 | 10.19 |
| Code word, 582 prompt tokens | — | — | 22.95 | 23.05 |
| Code word, 1,639 prompt tokens | — | — | 38.52 | 42.80 |

Both code-word checks pass in both runs. The six long replies intentionally hit their
192-token cap. Swedish first-text latency is lower with Q8 in this run, so not every Q8
latency measure is worse. Q4/Q8 startup takes 94.28/102.18 seconds and maximum observed
engine RSS is 101.50/173.29 GiB. Neither run uses guest swap; Q8 reaches at most 49°C on
the GPUs and retains at least 242.76 GiB available guest RAM.

The larger Q8 experts reduce combined GPU cache capacity from 14,755 to 8,687 slots.
The first code reply's cache hit rate falls from 89.7% to 75.7%; draft acceptance also differs.
[Q4 cache/draft records](strata-q4-600g/cache-and-draft.json) and
[Q8 records](strata-q8/cache-and-draft.json) retain each request. These observations do not
isolate any one cause of the speed difference. The native expert arena can coexist with file
cache, so RSS alone is not total system memory use.

Q8 packing retains native experts and PLE but converts small dense tensors to Strata's forms:
96 exact and 364 rounded conversions, recorded in `pack-q8.log`. This and the different
inference settings are reasons to keep Strata results separate from the reference comparison.
The [previous 256 GiB VM results](../2026-10-05-cisco-m10-large-models/README.md) are also a
separate experiment; this report includes a fresh Q4 baseline on the 600 GiB VM.

## Model provenance and storage

[Download manifest](download-manifest.json): `unsloth/Qwen3.8-Flash-Next-GGUF`, revision
`766911a6b7369840a91dbcd95f9f997acaab6cd6`, with pinned size/SHA256 per file. The existing
Q4 shards match that revision ([Q4 check](q4-revision-check.json)). All Q8 and BF16 shards
were downloaded and SHA256-verified. Sizes below exclude the separate MTP model and packs.

| Variant | Main GGUF shards | Bytes | GiB |
| --- | ---: | ---: | ---: |
| Q4 UD-Q4_K_XL | 4 | 111,334,654,784 | 103.7 |
| Q8_0 | 6 | 188,225,033,248 | 175.3 |
| BF16 | 8 | 354,029,930,496 | 329.7 |

[Tensor inventory](tensor-inventory.json) covers every Q8/BF16 shard header. Both have the
same 1,224 tensor names and shapes ([shape comparison](tensor-shape-comparison.json));
[architecture/tokenizer metadata](metadata-comparison.json) also matches Q4. Q8/BF16 PLE
storage is 54.4/102.4 GB, and routed-expert storage is 128.3/241.6 GB respectively.

Q8 is retained on NAS at `/models/strata-work/data/models/unsloth-q8_0`. BF16 is in
**temporary RAM storage** at `/mnt/strata-large/models/unsloth-bf16` and will be lost at
reboot. The NAS lacks space for both alongside existing models; original Q4, IQ3 and Coder
files remain. The tmpfs caps are 256 GiB for `/mnt/strata-ram` and 400 GiB for
`/mnt/strata-large`; caps do not reserve RAM and combined usage must fit the guest.
Both mounts use mode 0700, owner bjwl, and nosuid,nodev,noexec. Host/guest backups are
`/root/strata-bringup-backup/104.conf.before-q8-bf16` and
`/root/strata-bringup-backup/fstab.before-q8-bf16` respectively.

During BF16 download, the guest briefly swapped about 3 GiB while unused Q8 source cache
was still resident. After Q8 benchmarks finished, that cache was released with
`POSIX_FADV_DONTNEED` and `/swap.img` was turned off and back on to bring pages into RAM.
`q8-cache-release.json` and `swap-reset.log` record this. BF16 then completed its benchmark
with zero observed swap. No model files or permanent swap settings were removed.

## Implementation and validation

The PLE reader now handles Q8_0 (170 bytes per 160-value row) and BF16 (320 bytes). Its maximum
raw row buffer is increased accordingly. `ple_native_parity` compares against ggml using
synthetic rows with page crossings, mmap/direct/locked-mmap, single reads and batched paths.
Real Q8 PLE passes mmap and direct checks; real BF16 passes mmap checks. tmpfs refuses
O_DIRECT, so that test uses `--mmap-only`. The failed direct attempt is retained in
`ple-tmpfs-parity.log`; it is a storage-mode constraint, not a decoding mismatch.

The new CTest passes, as does the existing generic PLE reader selftest. The old fixture-based
`ple_parity` could not run because its fixtures are absent; this is not a claim that the
entire CTest suite passed. Q8 CPU/GPU expert parity passes. The eight Python tests cover
stream termination/finish handling and resumable download/range/checksum behavior.
Previous summary values remain unchanged in the compatibility check.

Full native BF16 remains unsupported: its expert parity baseline fails the activation-buffer
size check, and GPU expert plus native output-head dispatch lack BF16 paths. Adding the PLE
reader does not resolve those limits. See `native-bf16-baseline.log` and the
[code audit](../../../docs/M10_CODE_AUDIT.md). [Build hashes](strata-build-sha256.txt) record
the tested Strata binary and changed PLE sources.

## Interactive handoff

Q4 is restored at `http://192.168.3.73:8080`, using the existing private API key. The
[final access check](final-access-check.json) records unauthenticated rejection, authenticated access and a correct arithmetic
reply. Credentials and generated service configuration are excluded from this report.
The service is manually launched, not a boot service; both RAM stores must be restaged after
reboot. Start/stop instructions and private key file locations are in
[the local handoff](../../../docs/M10_LOCAL_HANDOFF.md).
