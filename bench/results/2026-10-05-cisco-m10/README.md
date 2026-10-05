# Cisco Tesla M10 bring-up (2026-10-05)

Hardware and paths: [M10_HARDWARE.md](../../../docs/M10_HARDWARE.md).
Source: `m10-port`, baseline `064bf96`, with the SM50 compatibility changes in this working tree.

Subsequent full-model benchmarks and the current server configuration are in the
[full-model report](../2026-10-05-cisco-m10-large-models/README.md).

This is an initial correctness check. It is not a throughput benchmark or a claim that every engine path works.

## Build and kernel checks

CUDA 12.2.140, GCC 11.4, CMake 3.31.10 and Ninja 1.10.1. Release build, architecture `50`,
`STRATA_EXPERIMENTAL_SM50=ON`, tests enabled. The pinned llama.cpp dependency is
`3cf03257f219afbe7334045ff7c6a06ac68c627d`.

- Engine and selected parity executables built successfully (`-j6`).
- `strata-device --selftest` passed separately on each of the eight M10 GPUs.
- 27 selected CTest cases passed on physical GPU 4, including IQ fixture preparation.
- Six real CMake configure cases passed: SM50 rejected without an opt-in or with SM60 alone; SM50, SM60,
  SM70 and SM75 accepted with their intended options. These run as two Python unittest methods.
- Setup checks passed: 20 older-GPU tests and five `ExperimentalSm60` cases.

The [raw logs](data/) retain the individual test names and durations. The second parity run initially skipped
two IQ cases because the fixture script could not find `gguf-py`. Both passed when rerun with
`PYTHONPATH` pointing to the pinned dependency's `gguf-py` directory; see `parity-m10-iq.log`.

The BF16 parity reference on Maxwell widens the inputs on the CPU and uses cuBLAS SGEMM. It checks the GPU's
BF16 widening independently, including sliced activations, beta accumulation and padded output rows.

Configure as in [M10_LOCAL_HANDOFF.md](../../../docs/M10_LOCAL_HANDOFF.md), then build the selected targets:

```bash
ninja -C /home/bjwl/strata-dev/build-m10 -j6 strata strata-device \
  gemm_bf16_parity native_expert_parity mmvq_multi_parity iq_multi_parity \
  router_top10_parity qsa_parity shared_expert_parity native_grouped_parity \
  gr_parity gdn_parity gdn_rec_parity quantize_act_parity rope_parity \
  kv_q8_parity route_window_parity qsa_topk_parity iq_parity
CUDA_VISIBLE_DEVICES=4 \
PYTHONPATH=/home/bjwl/strata-dev/deps/llama.cpp-3cf03257f219afbe7334045ff7c6a06ac68c627d/gguf-py \
  /home/bjwl/strata-dev/venv/bin/ctest --test-dir /home/bjwl/strata-dev/build-m10 \
  --output-on-failure --timeout 180 \
  -R '^(cuda_device_selftest|gemm_bf16_parity|native_expert_parity_.*|mmvq_multi_parity|iq_multi_parity|router_top10_parity|qsa_parity|shared_expert_parity|native_grouped_parity|gr_parity|gdn_parity|gdn_rec_parity|quantize_act_parity|rope_parity|kv_q8_parity|route_window_parity|qsa_topk_parity|iq_parity(_fixtures)?)$'
STRATA_TEST_CMAKE=/home/bjwl/strata-dev/venv/bin/cmake \
STRATA_TEST_NVCC=/usr/local/cuda-12.2/bin/nvcc python3 tools/test_cuda_arch_configure.py
```

## Model validation

Coder GSQ-RCO IQ1_M was downloaded at revision `5348543e0147355ac9cbcb031184a3546350988e` and prepared with
the repository's `iq_pack.py`, tokenizer exporter and MTP tools. MTP tensors were verified against the pinned
SHA256 values. Runtime: 4,096-token context, int8 KV, prefill 128, spec 2, 16 pool workers, fused prompt experts
disabled. The engine selected AVX2 CPU experts on the Xeon; its log says "no AVX-512", although the actual missing
feature for the fast path is VBMI.

The initial one-GPU server loaded with 324 MiB free but its first request failed at CUDA graph instantiation:
`verify: instantiate: out of memory`. The default 700 MiB reserve was insufficient in this configuration.
All subsequent runs explicitly reserve 1,536 MiB with `--vram-reserve-mib`, reducing the expert cache.
The one-GPU server then loaded with 1,159 MiB free and completed every request. Its append-only engine log
also retains the initial failure; separate `initial-oom` files preserve that attempt.

Each configuration received the same three greedy, non-thinking requests: arithmetic, a code word in supplied
conversation history, and a Python `add(a, b)` function. All 12 replies matched the expected text exactly:
`4`, `pinecone`, and the function returning `a + b`. All completed normally with HTTP 200.

| GPUs | Explicit split points | Correct replies | GPU memory used after the three requests (MiB, device order) |
| --- | --- | --- | --- |
| 1 | none | 3/3 | 7632 |
| 2 | 24 | 3/3 | 7295, 7300 |
| 4 | 12,24,36 | 3/3 | 7102, 7034, 7034, 7141 |
| 8 | 6,12,18,24,30,36,42 | 3/3 | 3894, 3771, 3957, 3976, 4320, 4087, 4083, 5846 |

On eight GPUs, a further 296-token prompt crossed the 128-token prefill boundary and returned the correct code
word, `birch`. A follow-up returned `birch` again and reused 298 of its 325 prompt tokens. This checks several
prompt chunks and restoration of the conversation state across all eight stages.

These are short smoke checks, not a quality evaluation or a sustained speed comparison. For the 18-token code
reply alone, the server reported 7.4, 7.4, 6.7 and 6.5 decode tokens/s on one, two, four and eight GPUs respectively.
There was one observation per configuration, no repeated benchmark. More cards did not improve that short case.
Long contexts, long-running stability and automatic split placement remain untested.

The first cold start read 23.42 GiB of expert data from NFS at 0.11 GiB/s and took about 250 seconds before
cache preparation. Subsequent starts used the OS file cache and reached HTTP readiness in roughly 20-30 seconds.
The PLE table was touched into RAM but not locked because of the guest's `mlock` limit. No swap was in use during
the observed cold load. These conditions must accompany any future performance comparison.

## Reproduce the model checks

The [data directory](data/) contains the exact runtime JSON files, request scripts, responses, engine logs and
memory readings. Paths are specific to this VM. With no other test server running, use:

```bash
/home/bjwl/strata-dev/venv/bin/python -u /home/bjwl/strata-dev/run_stage.py 8
```

`run_stage.py` starts the server, waits for readiness and sends the three requests. It leaves the server running
for inspection. To stop that instance cleanly, send SIGTERM to the PID recorded in
`/home/bjwl/strata-dev/server-8gpu.pid` before starting another configuration. The longer check is
`/home/bjwl/strata-dev/context_smoke.py` against the running eight-GPU server.

At the end of bring-up, the eight-GPU test server remains on **VM 104's `127.0.0.1:8080`**. It was started for
testing, not installed as a boot service. Models are under `/models/strata-work/data`; scripts and configurations
under `/home/bjwl/strata-dev`. The previous `llama-server.service` remains disabled as recorded in the hardware note.
