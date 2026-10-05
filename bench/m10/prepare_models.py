"""Prepare the two full-model M10 experiments using setup's pinned downloads.

Requires existing Coder files, MTP runtime, a venv and the pinned gguf-py dependency.
Uses the same shared PLE shard as setup. Keeps downloaded files and packs resumable.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import setup


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--state", type=Path, required=True)
    a = ap.parse_args()

    def stage(name, **details):
        obj = {"stage": name, "time": datetime.datetime.now(datetime.timezone.utc).isoformat(), **details}
        temp = a.state.with_suffix(".tmp")
        temp.write_text(json.dumps(obj, indent=2) + "\n"); temp.replace(a.state)
        print(name, flush=True)

    try:
        for family, model, tag in (("qwen", "IQ3_S", "qwen-iq3_s"),
                                   ("unsloth", "UD-Q4_K_XL", "unsloth-ud-q4_k_xl")):
            fam = setup.FAMILIES[family]
            folder = a.data / "models" / tag
            folder.mkdir(parents=True, exist_ok=True)
            shards = [folder / setup.model_file(fam, model, i)
                      for i in range(1, setup.MODELS[model].get("shards", fam.get("shards", 2)) + 1)]
            for i, shard in enumerate(shards, 1):
                stage("Downloading", model=tag, shard=shard.name)
                if family == "qwen" and i == 2 and not shard.exists():
                    other = a.data / "models/coder-iq1_m/Qwen3.8-Flash-Next-GSQ-RCO-IQ1_M-00002-of-00002.gguf"
                    if setup.done(other) and setup.whole_shard(other):
                        os.link(other, shard)
                        setup.mark(shard, "Shared PLE shard with Coder, as in setup.py")
                setup.download(fam["hf"].format(q=model) + shard.name, shard)
            stage("Checking shards", model=tag)
            setup.check_shards(shards)
            for shard in shards:
                if shard.name in fam.get("sha256", {}):
                    setup.verify_sha256(shard, *fam["sha256"][shard.name])
            pack = a.data / "packs" / tag
            stage("Packing", model=tag)
            subprocess.run([sys.executable, str(ROOT / "tools/iq_pack.py"), "--gguf", str(shards[0]),
                            "--out", str(pack), *fam.get("pack_args", [])], check=True, cwd=ROOT)
            (pack / "m10-ready.json").write_text(json.dumps({"family": family, "model": model,
                "shards": [str(p) for p in shards], "prepared_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}, indent=2))
            stage("Model ready", model=tag)
        stage("All full-model packs ready")
    except BaseException as exc:
        stage("Failed", error=str(exc))
        raise


if __name__ == "__main__":
    main()
