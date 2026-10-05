# Cisco M10 test platform

Measured on 2026-10-05. The original M10 plan assumed compute capability 5.2. Both NVML and a CUDA runtime
probe report **5.0** on all eight devices in this machine. Build for `sm_50`.

| Component | Observed configuration |
| --- | --- |
| Host | Cisco UCSC-C240-M5SX, Proxmox, Debian 13.3, kernel 6.17.13-1-pve |
| Host processors | Two Xeon Gold 6248R, 48 physical cores / 96 threads total |
| Host memory | 692 GiB reported by `free -h` |
| GPU assignment | Eight Tesla M10 devices, passed through with `vfio-pci` to VM 104 |
| Guest | Ubuntu 22.04.5, 24 vCPU, CPU type `host`, 128 GiB configured RAM (~125 GiB usable) |
| Guest CPU features | AVX2, AVX-512 F/BW/DQ/VL and VNNI; no AVX-512 VBMI flag |
| GPU memory | 8,192 MiB per device; 8,127 MiB free before loading an application |
| NVIDIA driver | 535.309.01 |
| CUDA compiler | 12.2.140, `/usr/local/cuda-12.2/bin/nvcc` |
| Host compiler | GCC 11.4.0 |
| Build tools | CMake 3.31.10 in `/home/bjwl/strata-dev/venv`; Ninja 1.10.1 |

The table records the initial bring-up. The subsequent
[full-model experiments](../bench/results/2026-10-05-cisco-m10-large-models/README.md) increased VM 104 to
256 GiB configured RAM (~251 GiB usable), retaining 24 vCPUs. Their measurements record this separately. The guest now has a dedicated 128 GiB-cap tmpfs at
`/mnt/strata-ram` for model copies; its files must be restaged after reboot. The persistent source remains on NFS.

The guest exposes one NUMA node. Its `nvidia-smi topo -m` reports PHB for every pair, which does not describe
the host's two-socket topology: host PCI devices `60:00.0` through `63:00.0` are behind one PCIe switch,
and `b1:00.0` through `b4:00.0` behind another. Revisit placement and CPU affinity before comparing speed.

## Working directories

- Source: `/home/bjwl/Strata`, branch `m10-port`, starting commit `064bf96` plus the working changes.
- Local build: `/home/bjwl/strata-dev/build-m10`.
- Local pinned llama.cpp source: `/home/bjwl/strata-dev/deps/llama.cpp-3cf03257f219afbe7334045ff7c6a06ac68c627d`.
- Models and packs: `/models/strata-work/data` on the existing NFS mount.
- Logs and inventory: `/models/strata-work/logs`.

The guest root filesystem had only 7.1 GiB free before preparation. Large model files stay on NFS;
small source/build files use the local disk because unpacking thousands of files on NFS was slow.
Monitor local free space during builds. NFS model loading is not an SSD performance measurement.

## Baseline checks and reversible changes

The pre-existing `llama-server.service` occupied GPUs 0-3. It was stopped and disabled; its binaries and
model files were retained. VM memory increased from 32,600 to 131,072 MiB and vCPU count from 16 to 24.
The original Proxmox VM configuration and guest service files are saved under `/root/strata-bringup-backup`
on the host and guest respectively. No NVIDIA driver or CUDA toolkit upgrade was needed.

A standalone CUDA 12.2 program compiled with `-arch=sm_50` passed on **8/8 GPUs** after the VM restart.
It checks allocation, host/device copying, `__shfl_xor_sync` and `__syncwarp` with a full, converged warp.
This establishes basic CUDA operation, not Strata kernel parity or model quality. The program and its logs
are saved with the inventory. Engine build, parity and model results are in the
[bring-up report](../bench/results/2026-10-05-cisco-m10/README.md).
