#!/bin/bash
set -eu
n="$1"
cd /home/bjwl/Strata
printf '%s\n' "$$" > "/home/bjwl/strata-dev/server-${n}gpu.pid"
exec /home/bjwl/strata-dev/venv/bin/python -u -m serve.server --engine strata --config "/home/bjwl/strata-dev/strata-m10-${n}gpu.json" --host 127.0.0.1 --port 8080 > "/models/strata-work/logs/server-${n}gpu.log" 2>&1
