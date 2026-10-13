"""Controllable protocol fixture. Production never imports or selects this worker."""

import json
import os
import sys
import time

if "--fail-load" in sys.argv:
    sys.exit(1)
if "--slow-load" in sys.argv:
    time.sleep(10)
print(json.dumps({"type": "ready", "active_bytes": 1234, "cache_bytes": 0}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    if request["fields"][0]["text"] == "slow":
        time.sleep(10)
    if request["fields"][0]["text"] == "crash":
        sys.exit(7)
    print(
        json.dumps(
            {
                "status": "completed",
                "pid": os.getpid(),
                "active_bytes": 1234,
                "fields": [
                    {"id": f["id"], "text": f["text"].replace("utilize", "use"), "status": "rewritten"}
                    for f in request["fields"]
                ],
            }
        ),
        flush=True,
    )
