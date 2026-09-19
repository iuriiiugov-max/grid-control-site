#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/crypto-control/backend/observer/runtime}"
SNAPSHOT="$ROOT/out/latest.json"

test -f "$SNAPSHOT"
python3 - "$SNAPSHOT" <<'PY'
import json, pathlib, sys, time
p=pathlib.Path(sys.argv[1])
d=json.loads(p.read_text(encoding="utf-8"))
assert d.get("observerVersion") == "0.6", d.get("observerVersion")
assert d.get("mode") in ("READ_ONLY_GET_ONLY_PROXY_REQUIRED","READ_ONLY_GET_ONLY")
assert d.get("snapshotId")
assert isinstance((d.get("timing") or {}).get("privateStateTtlSec"), int)
age=max(0,int(time.time()*1000)-int(d["capturedAtEpochMs"]))//1000
ttl=d["timing"]["privateStateTtlSec"]
assert age <= ttl, (age, ttl)
print("OBSERVER_VPS_SMOKE=PASS", d["snapshotId"], d.get("health",{}).get("status"), f"age={age}s")
PY
