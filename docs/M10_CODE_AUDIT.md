# Tesla M10 / Maxwell sm_52 static audit

Status: source audit completed without M10 hardware.  The branch now has an opt-in `STRATA_EXPERIMENTAL_SM52` CMake path and setup recognition.  Nothing in this document claims that the engine has compiled or run on Maxwell yet.

## What already helps us

Several existing low-architecture paths are directly useful:

- `include/strata/kernels/dp4a.hpp` already emulates `__dp4a` for `__CUDA_ARCH__ < 610`.  Maxwell sm_52 therefore takes the software dot-product path automatically.
- The same header already removes `__nanosleep` below sm_70.
- `native_qsa_score.cu` uses ordered FP32 FMA below sm_80 instead of TF32 MMA.
- `qsa_prompt_attn.cu` has host-side fallback selection for devices below sm_70; Maxwell should return to the older FP32 prompt-attention path rather than launch the Volta/Turing MMA kernels.
- Ampere-only `cp.async` paths found in `fused_gr.cu`, `prefill/kernels.cu`, `prefill/moe_fused*.cu` and prompt attention are compile-time guarded at sm_80.
- Hopper cluster instructions and `__match_any_sync` in the cluster selector are guarded at sm_90.

This means the source is already much closer to Maxwell-compatible than a runtime written only for recent tensor-core GPUs.

## Items that need the first sm_52 compiler run

The largest remaining source-wide uncertainty is the family of CUDA warp intrinsics:

- `__shfl_sync`
- `__shfl_xor_sync`
- `__shfl_down_sync`
- `__shfl_up_sync`
- `__syncwarp`

They occur throughout decode, routing, attention, expert and sampling kernels.  CUDA 12.x still targets sm_52, but the exact compilation/semantics of these modern spellings on Maxwell must be established by nvcc rather than guessed.

If nvcc rejects any of them, add a central compatibility header mapping the synchronized forms to the legacy Maxwell shuffle intrinsics.  Do not patch dozens of call sites independently.

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

The first hardware probe must capture CPU flags.  If the CPU has AVX2 but lacks the full AVX-512/VNNI/VBMI set, measure the existing fallback before writing a new CPU kernel.

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

- `STRATA_EXPERIMENTAL_SM52=ON` added as a separate CMake opt-in.
- architecture floor can reach sm_52 only with that flag.
- CUDA 13 is rejected for the Maxwell flag.
- setup can recognize an opted-in Tesla M10 / sm_52.
- local engine builds select the Maxwell CMake definition instead of the Pascal/Volta one.
- setup unit tests include M10 cases.

## Do not do yet

Until the first compile/runtime logs exist, avoid:

- Maxwell-specific kernel rewrites;
- new CPU expert kernels;
- changes to generic layer-split algorithms;
- performance claims;
- merging the Maxwell flag into upstream's SM60 option.

The compiler output and first parity failures should determine the next patch.
