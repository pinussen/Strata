# M10 full-model and sustained generation experiments

Started 2026-10-05 after the [initial bring-up](../2026-10-05-cisco-m10/README.md).
The full 111.3 GB Unsloth model runs on this machine, including with one 8 GiB GPU and CPU/RAM offload.
Eight GPUs improve longer-prompt processing; fewer GPUs produce these short-input replies faster.
The tables below report measurements, not projected performance. The authenticated eight-GPU Q4 server
is left running; see [access and restart instructions](../../../docs/M10_LOCAL_HANDOFF.md#full-model-operating-configuration).

## Objective and models

Test whether the Cisco server's RAM and eight Tesla M10 GPUs can serve the full model at a useful speed.
The previous Coder is expert-pruned: 256 experts per layer instead of 512. Its `IQ1_M` name should not be
interpreted as all retained weights being one bit: the retained experts use formats like IQ3_S.

The full [Qwen model card](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) describes 125B language-model parameters
(6B activated), plus 51B n-gram embedding parameters and 4B MTP parameters. These counts describe a sparse model,
not the computation of a dense 180B model on every token.

| Model | Download size | Role |
| --- | --- | --- |
| Coder GSQ-RCO IQ1_M | 58.4 GB | Pruned baseline already validated |
| Full GSQ-RCO IQ3_S | 83.6 GB | Every expert retained; compare with Coder |
| Full Unsloth UD-Q4_K_XL | 111.3 GB | Largest variant in this checkout's installer; mixed higher-bit weights |

Sizes and pinned revisions come from `setup.py`. The full IQ3_S shares its 28.8 GB PLE shard with Coder by hard link,
as setup does. The existing MTP runtime is reused. Unsloth's shards are checked against setup's pinned SHA256
values and packed with `--compat-bf16`. This does not establish a quality ranking between quantizations.

## Machine and method

The [hardware](../../../docs/M10_HARDWARE.md), CUDA 12.2 build and 24 vCPUs are unchanged. For this experiment,
GPU counts here mean independent 8 GiB CUDA devices: the eight devices occupy two physical M10 boards.
VM 104's configured RAM increased from **128 to 256 GiB** (~251 GiB usable), leaving ample host memory available.
The config before expansion is saved on Proxmox as
`/root/strata-bringup-backup/104.conf.after-initial-bringup`. This is different from the initial smoke-test rig's RAM.

[`bench/m10/run_benchmark.py`](../../../bench/m10/run_benchmark.py) starts an isolated localhost server, warms it,
then runs code, English prose and Swedish prose prompts twice, with a 192-token output cap. It records complete
streamed text, the engine's prompt/decode timings, wall time and time to first visible streamed content. Different
case/repetition system prefixes prevent whole-prompt cache reuse. Fixed prompts and greedy decoding do not
guarantee identical generated token sequences across these runs; this is not a fixed-token kernel benchmark. Replies hitting the cap are recorded as such.
Two code-word prompts exercise longer prefill, with 48 and 144 filler lines. These are performance and sanity
checks, not a general model-quality benchmark.

Every two seconds, telemetry records GPU temperature, power, clock frequencies, VRAM and utilization; guest CPU
utilization, available RAM, swap and the engine's RSS. Power figures cover GPUs only, not the server or NAS.
`STRATA_SPLIT_TIMING=1` records host-side stage timing. Its GPU-wait fields are zero on the fully resident,
zero-doorbell path, so they do not measure the GPU's kernel time. Keep startup and inference measurements
separate: models reside on NFS, and the early exploratory runs overlap downloading the next model.

Successful raw guest results: `/home/bjwl/strata-dev/bench/<run>/`; the failed NFS baseline is under
`/models/strata-work/bench/`. Download preparation state:
`/models/strata-work/logs/large-model-state.json`. Scripts fail visibly and retain partial results on error.

## Results

### NFS baseline: retained as a failed experiment

[`coder-8gpu-base/`](coder-8gpu-base/) completed the six 192-token requests, then the engine watchdog aborted
the 582-token needle prompt after 60 seconds without layer progress. Its stall report found a thread waiting
on file pages, no swap use and about 226,938 MiB available RAM. This run overlapped preparation/download of
the full models; it is not a clean throughput comparison. Cold startup took 982.7 seconds, including 517.3
seconds locking the PLE table.

Code decode was 5.9–6.1 tok/s; English prose 5.4–5.5; Swedish 3.3–5.4. The slow Swedish response had an
8.38-second gap between streamed text chunks. GPU clocks stayed at least 1,032 MHz during those Swedish
requests, and the highest recorded GPU temperature across the completed requests was 42°C. These observations
point to an I/O problem rather than establish a compute limit. The next runs stage model files in tmpfs and
write benchmark logs to the guest's local disk.

The saved Swedish responses contain mixed Swedish/Danish/English and the English explanation contains a
factual error about the compressor. UTF-8 in the actual saved requests/responses is intact (the guest-agent
display made it appear garbled). The short numeric/code smoke tests did not establish general answer quality.

### Full-model results

The initial completed runs below use copies in `/dev/shm/strata-data` and logs on the guest's local root disk. The original
files remain on NFS. The initial staging of IQ3_S took about five minutes (270.4 seconds for the cold PLE shard;
25.8 seconds for the already cached first shard), in addition to engine startup. Tmpfs copies are lost on reboot.
This extra staging RAM is an experiment choice, not a minimum RAM requirement for running from a local SSD.

Decode medians, in tokens/s, from two 192-token responses per case († one response per case):

| Model / GPUs / speculative window setting | Code | English prose | Swedish prose | 1,639-token prompt tok/s | Needle checks |
| --- | ---: | ---: | ---: | ---: | --- |
| Full IQ3_S / 8 / spec 2 | 6.20 | 5.70 | 5.45 | 64.2 | 2/2 |
| Full IQ3_S / 4 / spec 2 | 6.65 | 6.15 | 5.70 | 37.2 | 2/2 |
| Full IQ3_S / 8 / spec 4 | 6.50 | 5.20 | 4.85 | 64.3 | 2/2 |
| Full IQ3_S / 4 / spec 4 | 7.20 | 5.80 | 5.40 | 37.2 | 2/2 |
| Unsloth UD-Q4_K_XL / 8 / spec 2 | 6.45 | 5.85 | 5.45 | 43.2 | 2/2 |
| Unsloth UD-Q4_K_XL / 4 / spec 2 † | 7.10 | 6.60 | 6.00 | 24.8 | 2/2 |
| Unsloth UD-Q4_K_XL / 8 / spec 4 | 6.70 | 5.20 | 4.95 | 43.1 | 2/2 |
| Unsloth UD-Q4_K_XL / 2 / spec 2 † | 7.20 | 6.60 | 5.90 | not run | 1/1 (582 tokens) |
| Unsloth UD-Q4_K_XL / 1 / spec 2 † | 8.10 | 7.70 | 6.90 | not run | 1/1 (582 tokens) |
| Unsloth UD-Q4_K_XL / 1 / spec 2, confirmation | 7.85 | 7.35 | 6.85 | not run | not run |

For IQ3_S, the four-GPU run produces these short-input responses 5–8% faster, while eight GPUs process the longer prompt
faster. First streamed text for code/prose/Swedish respectively: 8.17/8.15/8.32 seconds on eight GPUs and
7.23/7.16/8.67 seconds on four. The 1,639-token needle takes 25.75 versus 44.31 seconds to first text.

Engine startup from staged files takes 62.1 seconds on eight GPUs and 38.1 seconds on four. Maximum observed
GPU temperature is 52°C in both runs; maximum per-device VRAM is 7,092 versus 7,233 MiB. The guest retains at
least 117 GiB available RAM. Its aggregate swap use reaches 215 MiB in the eight-GPU run and 437 MiB in the
four-GPU run, so these are not claims of zero swapping. The next model downloads in the background during
these exploratory runs. Per-request raw telemetry and answers are retained in the named run directories.

On eight GPUs, spec 4 improves the code case by 5% but reduces English/Swedish throughput by 9%/11%.
The six capped answers are not all bit-identical between spec settings (both code answers and the first
Swedish answer match; the other three differ). This is a comparison on fixed prompts and output lengths,
not on an identical generated token sequence. Keep spec 2 as the mixed-workload baseline.

Original configurations using NAS paths are saved in [source-configs/](source-configs/). The configurations
inside completed run directories record the paths and settings actually used.

Four-GPU spec 4 likewise favors code (7.1–7.3 tok/s), while spec 2 has better English/Swedish medians.

The separate `qwen-iq3_s-8gpu-prefill512-ram` screening run uses one repetition and a 32-token output cap,
so its decode numbers are not in the 192-token table. Increasing the prompt chunk from 128 to 512 reduces
prompt throughput from 38.2 to 25.5 tok/s at 582 tokens and from 64.2 to 56.8 tok/s at 1,639 tokens; both
code-word checks pass. Keep the 128-token chunk for these tested lengths on eight GPUs.

The larger Unsloth model is downloaded, verified against the pinned SHA256 values and packed; see
[preparation output](model-preparation.log). Its eight-GPU baseline completes all six capped responses and
both code-word checks. First text takes 8.25/8.13/12.28 seconds for code/English/Swedish, and 38.18 seconds for
the 1,639-token prompt. Maximum recorded GPU temperature is 51°C and per-device VRAM is 7,103 MiB. At least
64.8 GiB guest RAM remains available. Its four-GPU screening run is faster at generation but takes 66.29
seconds to first text for the longer prompt. No downloads run during these Q4 inference measurements.

One GPU gives the highest Q4 decode rate in the initial screening. Its 582-token prompt takes 59.67 seconds
to first text, versus about 22 seconds with eight GPUs (26.7 prompt tok/s). The eight-GPU configuration remains
the interactive default for longer questions. Short-input generation is a reason to try the saved one-GPU
configuration. Across the code/prose requests, aggregate telemetry for all eight installed GPUs averages about 107–109 W
with one selected GPU and about 164 W with all eight selected; the unused devices still consume idle power.
These figures exclude CPU, RAM, fans and NAS, and are not wall-plug energy measurements.

The data do not establish a kernel-level cause for the scaling: CPU utilization includes workers
that can wait, and host stage timings are not a GPU profiler.

All runs use a 4,096-token context, int8 KV cache, prompt chunks of 128, speculative window 2 unless marked,
and a 1,536 MiB VRAM reserve. MTP uses the same English draft vocabulary (40,525 tokens) in all runs;
Swedish throughput is therefore measured with that setting too. These are sequential, non-thinking text requests, not concurrent-user, image or
long-context qualification. A single passing code-word prompt is not evidence of general reasoning quality.

### Q4 startup and memory compaction

The first Q4 start takes 352.6 seconds after staging, including a memory-compaction stall while allocating the
71.73 GiB expert arena. Linux's memory-pressure `full avg10` reached 94%; 9,515 compaction stalls and 7,193 failures
were observed, increasing to 14,651/11,012 at the later check. The process had not read any disk bytes during
the inspected stage. The VM still retained redundant NFS source pages beside its 106 GiB tmpfs copy.

During startup, `POSIX_FADV_DONTNEED` was applied to the four original, already copied Q4 source files
([timestamps](drop-q4-source-cache.json)). This is a file-cache hint, not a file deletion. Guest free RAM rose
to about 78 GiB, process RSS grew from about 87 to 100 GiB over the next 13 seconds, and startup finished.
The following four-GPU start, with the copies already staged and that source cache released, takes 50.1 seconds.
These are different startup conditions; the difference is not an isolated GPU-count comparison.

[`stage_config.py`](../../../bench/m10/stage_config.py) and the interactive launcher now offer
`--drop-source-cache` after staging to avoid retaining that duplicate source cache. The source-file bytes stay
unchanged. The host's `local-lvm` has only about 14.3 GiB free, so a persistent local copy of the 111.3 GB model
does not fit on the existing SSD. No host disk or partition was changed.

### VM access

Direct SSH as `bjwl@192.168.3.73` works from the workspace. Proxmox is `root@192.168.3.125`.
After a timed-out guest-exec session, Proxmox's guest-agent calls stopped responding even though the guest
service was running. The channel recovered after a `guest-sync-delimited` exchange with the 0xFF sentinel,
as specified by the [QEMU guest-agent protocol](https://www.qemu.org/docs/master/interop/qemu-ga-ref.html).
Both `qm agent 104 ping` and `qm guest exec 104 --timeout 10 -- /bin/true` then passed. No reboot was needed.

### RAM staging that survives logout

After the initial runs finished, `/dev/shm/strata-data` disappeared when the last login session ended. The VM
had not rebooted. This matches the guest's [documented `RemoveIPC` cleanup policy](https://cgit.freedesktop.org/systemd/systemd/tree/man/logind.conf.xml?id=7f0a55d4325f7df91f91b3b818f61f97d78df14a); the timing is evidence for that cause,
not a traced deletion. The subsequent `unsloth-ud-q4_k_xl-1gpu-confirm-ram` attempt failed before loading the
engine because its staged tokenizer was missing. Its failure record is retained; it is not an inference failure.
The original NAS files and benchmark results remained intact.

A dedicated tmpfs now mounts at `/mnt/strata-ram`, with a 128 GiB size cap, owner `bjwl`, mode 0700 and
`nosuid,nodev,noexec`. Its `/etc/fstab` entry makes the mount available after reboot; the files still need to be
copied again after reboot. The previous fstab is saved on the guest at
`/root/strata-bringup-backup/fstab.before-strata-ram`. The global login cleanup policy was not changed.
See [the launcher instructions](../../../bench/m10/README.md) for staging and source-cache release.

The repeat on the dedicated mount (`unsloth-ud-q4_k_xl-1gpu-confirm-tmpfs`) completes two 192-token replies
per code/English/Swedish case, plus warmup. It confirms the one-GPU decode advantage at medians of
7.85/7.35/6.85 tok/s. Startup after staging takes 46.1 seconds; peak GPU temperature is 49°C, peak VRAM
7,627 MiB, minimum available guest RAM 68.2 GiB and peak guest swap use 1.8 MB. This run repeats no needles;
the earlier one-GPU screening retains the 582-token check. The new mount and source-cache release also avoid
the previous startup delay in this observed run. They do not guarantee that every future cold start takes 46 seconds.

## Server left running and final checks

The interactive server uses the full Unsloth UD-Q4_K_XL model on eight GPUs, with its files at
`/mnt/strata-ram/data`. Restaging records 968.5 seconds of file copying (~16 minutes) from NAS. After the
one-GPU confirmation, the eight-GPU server becomes ready in 64.1 seconds using the existing staged files.
Its PID is recorded at `/home/bjwl/strata-dev/service/server.pid`; [launch metadata](service/launch.json),
[sanitized configuration and binary hash](service/runtime-inventory.json), logs and access checks are retained.
It is not configured to start automatically after a reboot.

[Live checks](service-checks-8gpu/status.json) all complete normally, with these observations:

| Check | Result | First streamed text | Total request time |
| --- | --- | ---: | ---: |
| Arithmetic, 17 × 19 | `323` | 5.64 s | 6.20 s |
| Swedish explanation | Three complete Swedish sentences, 116 output tokens | 7.32 s | 27.81 s |
| Python merge function | Complete function, 129 output tokens | 8.39 s | 27.41 s |
| 3,896-token code-word prompt | `birch`; 50.6 prompt tok/s | 77.33 s | 77.62 s |
| Follow-up | `birch`; 3,898 cached tokens, 23 newly processed tokens | 3.67 s | 4.21 s |

The generated Python was reviewed before local execution. It passes
[107 functional cases](service-checks-8gpu/python-validation.json), covering empty lists, duplicates, negative
numbers, floats, unequal lengths and seeded random sorted lists, with input preservation checked. The response
uses Markdown fences despite the request for only Python code; these were removed for the functional test.
The Swedish response is readable, but includes increased house heat loss in an explanation of pump efficiency;
that is a heat-demand statement, not by itself an explanation of lower efficiency. These examples do not
establish broad answer quality or perfect instruction following.

During the live checks, peak recorded GPU temperature is 52°C, peak per-device VRAM 7,097 MiB and minimum
available guest RAM 64.6 GiB. Afterward, the engine uses 0.3% CPU over a three-second idle sample. No benchmark
or download process remains running. The original NAS models are retained and the guest's root filesystem has
5.8 GiB free; do not stage large persistent copies there.

[Access verification](service/access-checks.json) passes through the workspace's localhost SSH tunnel:
web page HTTP 200, authenticated `/v1/models` HTTP 200, unauthenticated `/v1/models` HTTP 401, and loaded health.
Use `http://127.0.0.1:8080` from the workspace machine. The key is in the private local file
`/home/bjwl/.config/strata-m10-cisco/api-key`; it is not in this report or repository. The API model ID is
`strata-m10-unsloth-ud-q4_k_xl`. The web app defaults to high thinking; select **Thinking: Off** to match these
non-thinking measurements. The API equivalent is `reasoning_effort: "none"`.

Remaining experiments: longer contexts, simultaneous requests, host NUMA/CPU placement, different worker
counts and GPU profiling. None is implied by the short functional and performance checks above.

## LAN access update — 2026-10-06

At the user's request, the existing eight-GPU Q4 server now binds directly to `192.168.3.73:8080`, with the
same API key required. The launcher supports `--host` and refuses a non-localhost address without an API key
file. The earlier localhost access records above describe the original benchmark session.

[Direct LAN verification](service/lan-access-checks.json), run from the workspace machine, confirms HTTP 200
for the web UI and authenticated API, HTTP 401 for the unauthenticated API, loaded health, and a complete
arithmetic answer (`323`). [Launch metadata](service/launch-lan.json) records the restarted instance.
The optional workspace localhost tunnel now forwards to the guest's LAN address. See the updated
[operating instructions](../../../docs/M10_LOCAL_HANDOFF.md#full-model-operating-configuration).
