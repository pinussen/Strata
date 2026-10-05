# Tesla M10 / Maxwell sm_50 porting plan

Hardware correction (2026-10-05): all eight passed-through Tesla M10 GPUs on the Cisco UCS C240 M5SX report
compute capability 5.0 through NVML and the CUDA runtime. The original plan incorrectly assumed 5.2.
Use `STRATA_EXPERIMENTAL_SM50` and `CMAKE_CUDA_ARCHITECTURES=50`; the old SM52 instructions do not target these GPUs.

Bring-up status: the engine builds; 27 selected CTest cases pass; three short model requests give the same correct
text on one, two, four and eight GPUs with explicit layer splits. The default VRAM reserve failed on the first
one-GPU request; the tested configurations use `--vram-reserve-mib 1536`. See the
[measured results and configurations](../bench/results/2026-10-05-cisco-m10/README.md).

Full-model follow-up: both 83.6 GB IQ3_S and 111.3 GB Unsloth Q4 run successfully. The latter was tested on
one, two, four and eight 8 GiB devices with 256 GiB guest RAM. See the
[full-model measurements](../bench/results/2026-10-05-cisco-m10-large-models/README.md) for decode/prefill
tradeoffs, storage fixes and remaining limits.

This document tracks the work needed to make Strata run experimentally on NVIDIA Tesla M10 cards (Maxwell, compute capability 5.0), with the initial target being a Cisco server containing multiple M10 boards.

The goal is **not** to make Strata a generic old-GPU runtime. The first target is to keep the current Qwen3.8-Flash-Next model architecture and make the existing CUDA engine work on sm_50 with as little divergence from upstream as possible.

## Hardware assumptions

A Tesla M10 board contains four independent Maxwell GPUs, each with 8 GiB VRAM. Two M10 boards therefore appear as eight CUDA devices with 8 GiB each. VRAM is not shared between devices.

Important consequences:

- every device is below Strata's current experimental CUDA floor of sm_60;
- CUDA 13 cannot be used for Maxwell, so the port must use a CUDA version that still supports sm_50;
- 8 GiB per device is tight, so dense weights, KV/session state, prompt buffers and expert cache must be budgeted carefully;
- multi-GPU layer splitting is preferable to tensor parallelism because Strata already transfers activations only between stages rather than synchronizing every layer.

## Success criteria

The work should be done in stages. Do not optimize everything at once.

1. Strata configures and compiles for sm_50.
2. CUDA kernel parity/self-tests run correctly on one M10 GPU.
3. A small real-model smoke test reaches inference on one M10 GPU without illegal-instruction or unsupported-operation failures.
4. A two-GPU explicit layer split works.
5. All eight M10 GPUs can participate in one model run.
6. The model is stable enough for repeatable benchmarks.
7. Only after correctness is established, optimize Maxwell-specific hot paths.

---

# Step-by-step plan

## Phase 0 - Record the exact test platform

Before changing code, record:

- Cisco server model;
- CPU model(s) and instruction sets;
- number of Tesla M10 boards and visible CUDA devices;
- GPU PCI bus topology from `nvidia-smi topo -m`;
- NVIDIA driver version;
- available host RAM;
- Linux distribution/kernel;
- installed CUDA toolkits;
- whether IOMMU/virtualization changes PCIe topology.

Commit the result as a small hardware note under `docs/` or `bench/results/`.

Reason: this port will depend heavily on PCIe topology, CPU fallback speed and the exact CUDA/toolchain limits.

## Phase 1 - Establish the CUDA/toolchain floor for sm_50

Starting point before this port:

- normal Strata CUDA builds require sm_75+;
- `STRATA_EXPERIMENTAL_SM60` lowers that floor to sm_60;
- `include/strata/kernels/dp4a.hpp` already provides a software fallback for `__dp4a` below sm_61 and avoids `__nanosleep` below sm_70;
- `CMakeLists.txt` still explicitly rejects architectures below sm_60.

Tasks:

1. Determine the newest CUDA toolkit that still compiles sm_50.
2. Add a **separate opt-in Maxwell flag**, for example:
   `STRATA_EXPERIMENTAL_SM50=ON`.
3. Keep `STRATA_EXPERIMENTAL_SM60` behavior unchanged.
4. Lower the CMake architecture floor to 50 only when the new flag is enabled.
5. Ensure no ready-made modern CUDA build changes behavior.
6. Add configure-time tests covering:
   - sm_50 without the flag -> rejected;
   - sm_50 with the flag -> accepted;
   - sm_60/sm_70 experimental path -> unchanged;
   - sm_75+ normal path -> unchanged.

Do **not** merge Maxwell into the existing SM60 flag initially. Keeping the paths separate makes regressions easier to isolate.

## Phase 2 - Compile-audit every CUDA kernel for sm_50

Build all CUDA translation units for sm_50 and collect failures rather than fixing them ad hoc.

Audit especially:

- `src/kernels/cuda/native_*.cu`
- `src/kernels/cuda/qsa*.cu`
- `src/kernels/cuda/s2_*.cu`
- `src/kernels/cuda/iq_kernels.cu`
- `src/kernels/cuda/router_top10.cu`
- `src/kernels/cuda/verify_kernels.cu`
- `src/core/device.cu`
- `src/core/remote_expert_opt.cu`
- `src/prefill/ggml_cuda_host.cu`

Classify each failure into:

A. instruction/intrinsic unavailable on Maxwell;
B. CUDA library API unsupported for sm_50;
C. tensor-core/BF16 path that needs an existing FP32/FP16 fallback;
D. launch/resource assumptions that exceed Maxwell limits;
E. compile-time architecture guard only.

Create a checklist from the actual compiler output. Avoid speculative rewrites before this inventory exists.

## Phase 3 - Add a Maxwell compatibility layer

Prefer centralized wrappers over scattered `#if __CUDA_ARCH__ < ...` changes.

The existing `dp4a.hpp` is the model to follow.

Likely work:

1. Reuse the software `dp4a` path already present for sm_50.
2. Reuse the spin-loop fallback already present for pre-Volta.
3. Identify any warp primitives whose old CUDA form requires an explicit compatibility wrapper.
4. Route BF16 operations through FP32/FP16 conversion paths where Maxwell lacks native BF16 support.
5. Ensure tensor-core code is completely compiled out for sm_50.
6. Check atomics, shuffle operations and shared-memory assumptions against sm_50.
7. Keep numerical behavior measurable and document any path that is not bit-identical.

All compatibility code should be opt-in through the Maxwell build and should not affect modern GPU binaries.

## Phase 4 - Get kernel parity tests running on one M10 GPU

Before loading the full model, make the existing CUDA tests the first runtime milestone.

Priority tests should cover:

- quantized GEMV / MMVQ paths;
- routed expert kernels;
- shared expert kernels;
- router top-10;
- QSA scoring/select;
- attention;
- verify/speculative kernels;
- host/GPU hand-off paths.

For every failing test:

1. reproduce on sm_50;
2. compare against the CPU/reference implementation;
3. fix correctness first;
4. record whether the result is bit-exact or tolerance-based.

A single M10 device passing the relevant tests is the gate for the next phase.

## Phase 5 - Audit CPU fallback on the Cisco host

Strata depends on CPU expert execution whenever a routed expert is not resident in GPU cache.

The current high-performance CPU expert code uses modern AVX-512/VNNI/VBMI paths that the Cisco server CPU may not provide.

Tasks:

1. identify the exact Cisco CPU model;
2. run Strata's CPU feature detection;
3. determine which existing fallback path is selected;
4. benchmark that path independently;
5. decide whether it is usable for cache misses.

Possible outcomes:

- **fast enough:** leave CPU code unchanged initially;
- **works but slow:** maximize GPU expert residency first, then optimize CPU later;
- **unsupported:** add an AVX2-compatible expert fallback or reuse an appropriate ggml kernel.

Do not start by writing a new CPU backend unless runtime testing proves it is necessary.

## Phase 6 - Make 8 GiB per GPU viable

Each M10 GPU has only 8 GiB, so memory budgeting is a first-class problem.

Measure on sm_50:

- stage-local dense weights;
- output head/draft layer on the last stage;
- KV/session state;
- verify window;
- prompt buffers;
- CUDA context/runtime overhead;
- remaining space for expert cache.

Important existing features to test:

- explicit `--layer-split`;
- `STRATA_STAGE_TRIM=1`, which allows each stage to keep only its own dense weights;
- smaller `--prefill` sizes to reduce prompt buffers;
- reduced context length for the initial bring-up.

The first goal is **fit and correctness**, not maximum context length.

If 8 GiB cannot fit a useful stage with current buffers, make buffer sizing configurable before redesigning kernels.

## Phase 7 - Validate two-GPU layer splitting

Do not jump directly from one device to eight.

First use two M10 GPU devices.

Tasks:

1. use an explicit layer split rather than `auto`;
2. verify each card loads only its intended stage where stage trimming is enabled;
3. verify activation hand-off through pinned host memory;
4. verify expert caches are per-stage;
5. run parity tests against a one-device/reference run where possible;
6. measure PCIe transfer overhead.

This isolates multi-device bugs from Maxwell bugs.

## Phase 8 - Scale from 2 -> 4 -> 8 GPUs

Strata's current split logic already supports more than three cards; documentation states that beyond three cards the auto placement becomes proportional instead of exhaustive.

Therefore the initial assumption is **not** that the split engine must be rewritten for eight GPUs.

Test progressively:

- 2 devices;
- 4 devices;
- 8 devices.

For each count record:

- selected/explicit layer boundaries;
- VRAM use per GPU;
- expert cache size per GPU;
- prompt tok/s;
- decode tok/s;
- CPU expert percentage;
- PCIe transfer volume;
- whether any stage becomes the bottleneck.

Only change the generic multi-GPU implementation if an actual scaling limit appears.

## Phase 9 - Improve automatic layer placement for identical 8 GiB devices

The existing auto-placement heuristic was primarily designed around a small number of heterogeneous GPUs.

After explicit 8-GPU splitting works:

1. measure whether the current proportional placement is sensible on eight identical M10 GPUs;
2. account for the extra last-stage head/draft memory;
3. account for stage-local dense-weight trimming;
4. bias splits to avoid starving any stage's expert cache;
5. add a deterministic M10-friendly auto result only if measurements show a benefit.

Explicit split points remain the correctness/reference mode.

## Phase 10 - Setup and device detection

Once the engine works by hand, integrate it into setup.

Required changes:

1. identify Maxwell sm_50 as experimental rather than simply unsupported;
2. require explicit opt-in;
3. choose the Maxwell-capable CUDA engine/toolkit;
4. preserve modern CUDA 13 behavior for sm_75+ systems;
5. allow multiple M10 CUDA devices to be selected together;
6. warn clearly about 8 GiB VRAM and expected reduced context/prefill values;
7. add setup unit tests for device selection and CUDA-version choice.

Do this only after a manual build is proven to work.

## Phase 11 - Benchmark before optimizing

Create a reproducible benchmark set using one fixed model/quant and fixed prompts.

Measure:

- one M10 GPU;
- two GPU devices;
- four GPU devices;
- eight GPU devices;
- prompt processing;
- decode;
- speculative/MTP acceptance;
- CPU expert share;
- power and stability if available.

Record results under `bench/results/` using the existing repository conventions.

The first useful result is not necessarily high tok/s. A stable eight-device run is already valuable.

## Phase 12 - Maxwell-specific optimization

Only optimize hot paths shown by profiling.

Likely candidates:

- emulated `dp4a`;
- quantized expert GEMV;
- QSA scoring/attention fallback;
- router;
- host-to-device expert streaming;
- stage hand-off overhead;
- CPU fallback misses.

Possible strategies:

- Maxwell-specific integer dot-product packing;
- wider vectorized loads;
- kernel fusion where register pressure permits;
- larger expert residency through tighter stage memory use;
- overlap transfers and computation more aggressively.

Every optimization needs an A/B benchmark and a parity check.

---

# Suggested implementation order

Use this order for commits so regressions stay easy to bisect:

1. documentation only;
2. `STRATA_EXPERIMENTAL_SM50` CMake/configure support;
3. compile-only Maxwell compatibility fixes;
4. sm_50 kernel parity fixes;
5. one-GPU runtime bring-up;
6. CPU fallback decision;
7. 8 GiB memory tuning;
8. two-GPU split;
9. four/eight-GPU validation;
10. setup integration;
11. profiling and optimization.

Avoid mixing correctness changes, setup changes and performance tuning in the same commit.

# Initial unknowns to resolve on hardware

These cannot be answered reliably from source inspection alone:

- exact CUDA toolkit version that is practical for the installed driver and sm_50;
- exact Cisco CPU and how usable the current CPU fallback is;
- actual free VRAM after CUDA context allocation on an M10;
- whether the current prompt buffers fit comfortably in 8 GiB;
- PCIe topology between all eight GPU devices;
- whether eight pipeline stages improve throughput or merely allow the model to fit;
- how much expert-cache miss traffic remains after stage trimming.

Those measurements should drive the next changes rather than assumptions.
