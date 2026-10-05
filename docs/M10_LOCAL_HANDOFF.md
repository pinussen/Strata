# M10 local Codex handoff

Branch: `m10-port`

Start here after cloning the fork on the Cisco server.

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

Expected hardware target is Tesla M10 / Maxwell compute capability 5.2, probably eight visible CUDA devices when two M10 boards are installed.

## 2. Use CUDA 12.x

CUDA 13 removed Maxwell offline compilation/library support.  NVIDIA documents Maxwell as supported throughout CUDA 12.x, including CUDA 12.9.

If several toolkits are installed, point CMake explicitly at the CUDA 12 nvcc.

## 3. First configure: compile only for one architecture

```bash
cmake -S . -B build-m10 \
  -DSTRATA_ENABLE_CUDA=ON \
  -DSTRATA_EXPERIMENTAL_SM52=ON \
  -DCMAKE_CUDA_ARCHITECTURES=52 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.9/bin/nvcc
```

Adjust the nvcc path to the installed CUDA 12.x toolkit.

The first objective is simply to get a complete configure/build error inventory.

## 4. Build with readable logs

```bash
cmake --build build-m10 -j 1 2>&1 | tee m10-build.log
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
ctest --test-dir build-m10 --output-on-failure
```

Then run the CUDA parity/kernel targets that exist in the configured tree.  Record the first failing test and fix correctness before performance.

## 6. Device smoke test

Use one visible M10 GPU:

```bash
CUDA_VISIBLE_DEVICES=0 ./build-m10/strata-device
```

Confirm:

- Tesla M10 name;
- compute capability 5.2;
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

The static audit found widespread synchronized warp intrinsics (`__shfl_*_sync`, `__syncwarp`).  If CUDA 12 nvcc does not accept their current use for sm_52, create a central pre-Volta compatibility wrapper and convert through that wrapper.  Do not scatter Maxwell conditionals across all kernels.

See `docs/M10_CODE_AUDIT.md` for the complete pre-hardware audit.
