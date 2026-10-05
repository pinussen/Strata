# Tesla M10 / Maxwell sm_50 static audit

Updated 2026-10-05 after the first hardware build. The engine compiles with CUDA 12.2 for sm_50 on the
[Cisco test platform](M10_HARDWARE.md). Strata's device selftest passes on all eight GPUs; 27 selected CTest
cases pass, including fixture preparation. Three short model requests produce the same correct text with one,
two, four and eight GPUs, using explicit splits and a 1,536 MiB VRAM reserve. See the
[bring-up report](../bench/results/2026-10-05-cisco-m10/README.md) for results and limits.

## What already helps us

Several existing low-architecture paths are directly useful:

- `include/strata/kernels/dp4a.hpp` already emulates `__dp4a` for `__CUDA_ARCH__ < 610`.  Maxwell sm_50 therefore takes the software dot-product path automatically.
- The same header already removes `__nanosleep` below sm_70.
- `native_qsa_score.cu` uses ordered FP32 FMA below sm_80 instead of TF32 MMA.
- `qsa_prompt_attn.cu` has host-side fallback selection for devices below sm_70; Maxwell should return to the older FP32 prompt-attention path rather than launch the Volta/Turing MMA kernels.
- Ampere-only `cp.async` paths found in `fused_gr.cu`, `prefill/kernels.cu`, `prefill/moe_fused*.cu` and prompt attention are compile-time guarded at sm_80.
- Hopper cluster instructions and `__match_any_sync` in the cluster selector are guarded at sm_90.

This means the source is already much closer to Maxwell-compatible than a runtime written only for recent tensor-core GPUs.

## Warp intrinsics

The initial static audit questioned these CUDA warp intrinsics:

- `__shfl_sync`
- `__shfl_xor_sync`
- `__shfl_down_sync`
- `__shfl_up_sync`
- `__syncwarp`

The sm_50 engine build accepts them without wrappers. A small full-warp shuffle/barrier probe passes on all
eight cards, and the first selected kernel tests pass. This does not establish that every divergent call site
is correct; preserve and test the pre-Volta participation and convergence requirements.

## Files with architecture-specific assembly

These were inspected specifically because they contain instructions Maxwell cannot execute.

### Safe by existing guards, subject to compile verification

- `src/kernels/cuda/native_qsa_score.cu`
  - `ldmatrix` / TF32 `mma.sync` only at sm_80+.
  - pre-sm_80 path is FP32 FMA.
- `src/kernels/cuda/qsa_prompt_attn.cu`
  - Ampere/Turing/Volta matrix paths are architecture-gated.
  - host selector returns `false` below sm_70 so the old attention path is used.
- `src/kernels/cuda/qsa_select.cu`
  - Hopper cluster assembly is sm_90+.
  - `__match_any_sync` found in the cluster implementation is inside that sm_90+ guarded region.
- `src/kernels/cuda/fused_gr.cu`
  - `cp.async` is sm_80+ guarded.
- `src/prefill/kernels.cu`
  - `cp.async` has a pre-sm_80 fallback.
- `src/prefill/moe_fused.cu`
- `src/prefill/moe_fused_iq.cu`
  - tensor-core / `ldmatrix` / `cp.async` implementation is sm_80+ guarded.

### Expected hot spot

`include/strata/kernels/dp4a.hpp` makes correctness possible below sm_61, but emulated DP4A may be one of the largest Maxwell performance costs.  Do not optimize it until the full engine runs and profiling confirms it.

## CPU side

Do not assume the Cisco CPU can use Strata's fastest expert kernels.  The source has generic/ggml fallbacks and older-CPU build support, while the custom fast path uses newer AVX-512 features.

The guest has AVX2 and AVX-512/VNNI, but no VBMI flag. Measure the selected fallback before writing a new CPU kernel.

## 8 GiB device memory

The existing multi-GPU documentation already treats 8 GiB as the lower bound for a split participant, but M10 is exactly on that edge.

Bring-up should therefore start with:

- short context;
- explicit layer splits;
- `STRATA_STAGE_TRIM=1`;
- reduced `--prefill` if required;
- no optional GPU features until baseline inference fits.

The last stage also owns the output head and draft layer, so equal layer counts may not produce equal free VRAM.

## Multi-GPU

No eight-GPU rewrite is planned initially.  Current Strata already accepts more than three stage devices; exhaustive split search becomes proportional placement beyond three.

Validate in this order:

1. one M10 GPU;
2. two GPUs with explicit split;
3. four GPUs;
4. all eight GPUs;
5. only then evaluate auto placement.

## Source changes already made on this branch

- `STRATA_EXPERIMENTAL_SM50=ON` added as a separate CMake opt-in.
- architecture floor can reach sm_50 only with that flag.
- CUDA 13 is rejected for the Maxwell flag.
- setup can recognize an opted-in Tesla M10 / sm_50.
- local engine builds select the Maxwell CMake definition instead of the Pascal/Volta one.
- setup unit tests include M10 cases.
- the runtime device gate recognizes SM50, instead of continuing to require SM60 or SM75.
- the exact BF16-to-FP32 GEMM path is included in Maxwell builds as well as Pascal builds.
- the BF16 parity test uses host-widened reference inputs and cuBLAS SGEMM below sm_70, because those cards do
  not support the test's previous BF16 cuBLAS reference. Beta accumulation, sliced inputs and padded output rows pass.
- a CUDA 12 configure matrix checks rejection of SM50 without its own flag and acceptance of SM50, SM60, SM70
  and SM75 through their intended options.

## Do not do yet

Until model runs and profiles establish a need, avoid:

- Maxwell-specific kernel rewrites;
- new CPU expert kernels;
- changes to generic layer-split algorithms;
- performance claims;
- merging the Maxwell flag into upstream's SM60 option.

The next patch should follow any failures observed during model inference.
