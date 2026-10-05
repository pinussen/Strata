# M10 experiments

These scripts use an already built engine, prepared models and the server's Python environment.
They do not install drivers or change the VM. See [the measured hardware](../../docs/M10_HARDWARE.md) and
[results](../results/2026-10-05-cisco-m10-large-models/README.md) for the exact machine and limitations.

`prepare_models.py` downloads and packs the full IQ3_S and Unsloth UD-Q4_K_XL variants from setup's pinned
sources. It reuses the existing Coder PLE shard and MTP runtime. Set `STRATA_GGUF_PY` to the pinned llama.cpp
`gguf-py` directory. Its state JSON distinguishes downloading, checking, packing and completion.

`stage_config.py` copies the files referenced by one configuration to local storage and writes a separate
configuration pointing to the copies. Native GGUF sibling shards are included. A size/mtime manifest avoids
copying unchanged files again; this is not a checksum verification tool. Use previously verified downloads.
VM 104 uses a dedicated tmpfs at `/mnt/strata-ram`; ordinary user files in `/dev/shm` disappeared at logout.
Staging requires sufficient RAM and tmpfs space and must be repeated after a reboot. The
engine's working RAM and GPU allocations are additional to the staged files.
For RAM staging on Linux, `--drop-source-cache` advises the OS to discard the now redundant source file cache
after copying. This leaves the files unchanged. The first Q4 start on VM 104 otherwise spent several minutes
compacting memory for the engine's transparent huge pages despite substantial reclaimable file cache.

Example on VM 104, from the repo root:

```bash
python3 bench/m10/stage_config.py \
  --config /home/bjwl/strata-dev/bench-configs/unsloth-ud-q4_k_xl-8gpu-base.json \
  --data /models/strata-work/data \
  --dest /mnt/strata-ram/data \
  --out /home/bjwl/strata-dev/bench-configs/unsloth-ud-q4_k_xl-8gpu-base-tmpfs.json \
  --drop-source-cache
/home/bjwl/strata-dev/venv/bin/python bench/m10/run_benchmark.py \
  --config /home/bjwl/strata-dev/bench-configs/unsloth-ud-q4_k_xl-8gpu-base-tmpfs.json \
  --out /home/bjwl/strata-dev/bench/unsloth-ud-q4_k_xl-8gpu-fresh-tmpfs
```

Use a new output directory for each run and run only one benchmark server at a time. The runner starts and
stops its own localhost server on port 8096. It records streamed replies, timings, configuration, its own
source, logs and two-second telemetry. Requests use greedy non-thinking generation. `--repeats`, `--max-new`
and `--needle-lines` control duration; defaults are two repetitions of each 192-token prose/code task and two
longer code-word prompts. A missing stream terminator, engine error or wrong code word fails the run visibly.

Summarize completed or partial runs without starting a server:

```bash
python3 bench/m10/summarize.py /home/bjwl/strata-dev/bench/<run>
```

Keep the state and error alongside partial results. Output caps, background downloads, storage placement,
cache warmth and startup time matter when comparing runs. GPU power is not whole-system power. These few
prompts are performance and sanity checks, not a model-quality evaluation.

`start_server.py` provides the same staging step for interactive use, then replaces itself with the localhost
server. Run it with the server venv, specifying `--config`, `--data`, `--dest` and a local `--runtime` directory
for its generated config and engine log. Port 8080 is the default. It refuses an occupied port before staging.
It also accepts `--drop-source-cache` for the RAM-backed setup.
Pass `--api-key-file` to read a key from a private file; the generated server config is mode 0600. Following
[AI_SETUP.md](../../docs/AI_SETUP.md), use an API key before putting even an SSH tunnel in front of the server.
Stop the previous engine before switching models; enough destination space is required for the selected
model's files. This launcher does not create a boot service.

`check_live_server.py` records complete arithmetic, Swedish and Python responses, a prompt close to 4K tokens,
and a follow-up that must reuse the prompt cache. It accepts `--api-key-file`; credentials are not recorded in
the results. Generated Python is saved for review and never executed by this checker.
