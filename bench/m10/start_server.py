"""Stage a prepared M10 model, then serve it on localhost with local logs.

Run with Strata's server venv. The process becomes serve.server after staging,
so its PID and signals refer to the server. This does not install a boot service.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "data", "dest", "runtime"):
        ap.add_argument("--" + name, type=Path, required=True)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--drop-source-cache", action="store_true")
    ap.add_argument("--api-key-file", type=Path,
                    help="read the API key from a private file rather than the process command line")
    a = ap.parse_args()
    api_key = a.api_key_file.read_text().strip() if a.api_key_file else None
    if api_key == "":
        ap.error("API key file is empty")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", a.port)) == 0:
            ap.error(f"localhost port {a.port} is already occupied")
    runtime = a.runtime.resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    config = runtime / "server.json"
    subprocess.run([sys.executable, str(Path(__file__).with_name("stage_config.py")),
        "--config", str(a.config.resolve()), "--data", str(a.data.resolve()),
        "--dest", str(a.dest.resolve()), "--out", str(runtime / "staged.json"),
        *(["--drop-source-cache"] if a.drop_source_cache else [])], check=True)
    cfg = json.loads((runtime / "staged.json").read_text())
    cfg.update(host="127.0.0.1", port=a.port, open_browser=False, log=str(runtime / "engine.log"))
    if api_key is not None:
        cfg["api_key"] = api_key
    config.touch(mode=0o600, exist_ok=True)
    config.chmod(0o600)
    config.write_text(json.dumps(cfg, indent=2) + "\n")
    os.chdir(cfg["cwd"])
    (runtime / "server.pid").write_text(str(os.getpid()) + "\n")
    os.execv(sys.executable, [sys.executable, "-u", "-m", "serve.server", "--engine", "strata",
                             "--config", str(config), "--host", "127.0.0.1", "--port", str(a.port)])


if __name__ == "__main__":
    main()
