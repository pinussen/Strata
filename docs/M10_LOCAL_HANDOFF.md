# M10 local Codex handoff

Branch: `m10-port`

Start here after cloning the fork on the Cisco server.

The server is now inventoried in [M10_HARDWARE.md](M10_HARDWARE.md). Use the existing Ubuntu GPU guest (VM 104),
not the Proxmox host. All eight GPUs are sm_50; earlier versions of this handoff incorrectly said sm_52.
The [bring-up report](../bench/results/2026-10-05-cisco-m10/README.md) contains tested one-, two-, four- and
eight-GPU configurations. Keep their explicit `--vram-reserve-mib 1536`: the default reserve loaded the model
on one GPU but failed when the first request instantiated the CUDA graph.

## Full-model operating configuration

The [full-model report](../bench/results/2026-10-05-cisco-m10-large-models/README.md) records the 83.6 GB IQ3_S
and 111.3 GB Unsloth Q4 tests. The subsequent [Q8/BF16 experiment](../bench/results/2026-10-06-cisco-m10-q8-bf16/README.md)
increased VM 104 to 600 GiB configured RAM (~590 GiB usable). The interactive configuration uses Q4,
eight 8 GiB CUDA devices, a **65,536-token context**, int8 KV and speculative window 2. One GPU is a measured alternative
for faster generation from short questions, at the cost of slower prompt processing.

In the completed 4K Q8/BF16 comparison, Q8 runs in Strata at 4.75–5.60 tok/s across the tested
generation cases; full BF16 runs in the separate llama.cpp reference engine at 2.63–2.65 tok/s.
Native Strata BF16 remains unsupported. Q8 source files and its pack remain on NAS; BF16's
354 GB of files remain under `/mnt/strata-large/models/unsloth-bf16` in RAM and are lost at
reboot. Q4 is the restored interactive default. Raw replies, timings, validation and telemetry
are saved in the comparison report; those October 6 timed runs used zero observed guest swap.
The newer long-context experiment documents its separate swap observations and temporary preparation settings.

The [long-context report](../bench/results/2026-10-07-cisco-m10-long-context/README.md) verifies both Q4 and Q8
with 14,812, 31,224 and 63,960 input tokens and continued conversations. At the largest input, Q4/Q8 first
text takes 23 min 45 s / 29 min 43 s; the inventory follow-up starts after 8.29 / 8.55 s. Q4 remains the
interactive default. Keep the conversation prefix to reuse history and leave room for further messages:
the 65,536-token limit includes both input and new output. These are single synthetic-ledger sequences,
with thinking off; free summaries still have some errors.

Connect to the guest with `ssh bjwl@192.168.3.73`. From `/home/bjwl/Strata`, start the prepared model with:

```bash
/home/bjwl/strata-dev/venv/bin/python -u bench/m10/start_server.py \
  --config /home/bjwl/strata-dev/bench-configs/unsloth-ud-q4_k_xl-8gpu-64k.json \
  --data /models/strata-work/data \
  --dest /mnt/strata-ram/data \
  --runtime /home/bjwl/strata-dev/service \
  --host 192.168.3.73 \
  --drop-source-cache \
  --api-key-file /home/bjwl/strata-dev/service/api-key
```

Check whether port 8080 already has the server before starting another instance. The launcher refuses an
occupied port. Stop the existing server by its recorded PID in `/home/bjwl/strata-dev/service/server.pid`
after checking that PID still belongs to `serve.server`. For the one-GPU alternative, use
`unsloth-ud-q4_k_xl-1gpu-base.json`; this retains the earlier 4,096-token context. Larger contexts were
measured on eight GPUs. Stop the old server and wait for its engine to exit before switching.

The dedicated `/mnt/strata-ram` tmpfs (256 GiB cap) survives logout. It is mounted from fstab after boot, but contains no files
until staging runs again. A cold copy of the model from NAS takes many minutes. The launcher skips already
staged unchanged files and releases redundant source cache before loading. Original model files stay on NAS.
This is a manually launched server, not a boot service. Its logs are `service/server.log` and `service/engine.log`.
For unattended shell use, redirect output to `service/server.log` and run the launcher with `nohup`.

At the user's request, the server now binds to `192.168.3.73:8080` for direct LAN access and requires
the existing private API key. Open `http://192.168.3.73:8080` and enter that key under About > Settings.
The guest key is `/home/bjwl/strata-dev/service/api-key`; the workspace copy is
`/home/bjwl/.config/strata-m10-cisco/api-key`. Never commit either key or the generated `service/server.json`.
The launcher defaults to localhost and refuses a non-localhost bind without `--api-key-file`.

Select Thinking: Off to match the non-thinking benchmarks; the web app defaults to high thinking.
The OpenAI-compatible API base is `http://192.168.3.73:8080/v1`.
For an optional localhost SSH forward, the remote target is now the guest's LAN address:

```bash
ssh -N -L 127.0.0.1:8080:192.168.3.73:8080 \
  -o ExitOnForwardFailure=yes bjwl@192.168.3.73
```

## 1. Capture the machine

Run:

```bash
git checkout m10-port
nvidia-smi
nvidia-smi topo -m
lscpu
grep -m1 '^flags' /proc/cpuinfo
free -h
cat /etc/os-release
nvcc --version || true
```

Save the output before making further source changes.

The measured hardware target is eight Tesla M10 / Maxwell devices, compute capability 5.0.

## 2. Use CUDA 12.x

CUDA 13 removed Maxwell offline compilation/library support.  NVIDIA documents Maxwell as supported throughout CUDA 12.x, including CUDA 12.9.

If several toolkits are installed, point CMake explicitly at the CUDA 12 nvcc.

## 3. First configure: compile only for one architecture

```bash
/home/bjwl/strata-dev/venv/bin/cmake -S . -B /home/bjwl/strata-dev/build-m10 -G Ninja \
  -DSTRATA_ENABLE_CUDA=ON \
  -DSTRATA_EXPERIMENTAL_SM50=ON \
  -DCMAKE_CUDA_ARCHITECTURES=50 \
  -DSTRATA_BUILD_TESTS=ON \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.2/bin/nvcc \
  -DSTRATA_GGML_DIR=/home/bjwl/strata-dev/deps/llama.cpp-3cf03257f219afbe7334045ff7c6a06ac68c627d \
  -DIQ_FIXTURE_PYTHON=/home/bjwl/strata-dev/venv/bin/python
```

Adjust the nvcc path to the installed CUDA 12.x toolkit.

The first objective is simply to get a complete configure/build error inventory.

## 4. Build with readable logs

```bash
set -o pipefail
/home/bjwl/strata-dev/venv/bin/cmake --build /home/bjwl/strata-dev/build-m10 -j 1 2>&1 | tee m10-build.log
```

Use `-j 1` for the first failure pass so diagnostics are not interleaved.  After fixing compile errors, normal parallel builds are fine.

Classify failures before editing:

- unsupported Maxwell intrinsic;
- unsupported CUDA library operation/type;
- architecture guard missing;
- resource/launch assumption;
- unrelated host compiler problem.

Prefer one compatibility wrapper per missing feature over repeated per-kernel patches.

## 5. Run tests before the model

After the engine builds:

```bash
/home/bjwl/strata-dev/venv/bin/ctest --test-dir /home/bjwl/strata-dev/build-m10 -N
```

Check that tests are registered, then build and run the selected CUDA parity/kernel targets with `ctest -R`.
Some tests require model fixtures or newer GPU instructions; an unfiltered run is not a Maxwell validation suite.
Record every failure and skip, and fix correctness before performance.

## 6. Device smoke test

Use one visible M10 GPU:

```bash
CUDA_VISIBLE_DEVICES=0 /home/bjwl/strata-dev/build-m10/strata-device --selftest
```

Confirm:

- Tesla M10 name;
- compute capability 5.0;
- expected usable/free VRAM;
- no `no kernel image` / illegal-instruction error.

## 7. First model run

Keep the first run deliberately small:

- one GPU;
- short context;
- small prefill chunk;
- no optional accelerator paths;
- existing CPU fallback.

The purpose is to discover the next correctness blocker, not to produce a useful speed number.

## 8. Memory bring-up

Once one-GPU inference reaches decode, test the split memory features:

- `STRATA_STAGE_TRIM=1`;
- explicit layer split;
- reduced `--prefill`;
- short context.

Record free VRAM before/after weights, prompt buffers and expert cache.

## 9. Scale gradually

Only after one-GPU correctness:

1. two M10 devices;
2. four;
3. eight.

Use explicit split points first.  Do not debug Maxwell and auto-placement at the same time.

For every stage count record:

- split points;
- VRAM per device;
- expert cache count;
- CPU expert/cache misses;
- prompt tok/s;
- decode tok/s.

## 10. Feed results back into the branch

Commit:

- `m10-build.log` only if reasonably small, otherwise summarize it;
- hardware inventory;
- first compiler blockers;
- parity failures;
- measured memory layout.

Update `docs/M10_CODE_AUDIT.md` and `docs/M10_PORTING_PLAN.md` as facts replace assumptions.

## Likely first code issue

The hardware probe compiled and ran synchronized warp shuffle/barrier operations on all eight GPUs.
Do not replace these intrinsics merely because they have `_sync` in their names. Each kernel must still meet
Maxwell's participation and convergence rules. The initial code review also found that the runtime architecture
gate and BF16-to-FP32 GEMM fallback needed to recognize the new Maxwell flag.

See `docs/M10_CODE_AUDIT.md` for the complete pre-hardware audit.
