"""Health check for the Telegram assistant container.

The assistant writes a heartbeat file periodically; this verifies it is
fresh so Docker HEALTHCHECK can confirm the assistant is alive.
"""
import os
import sys
import time
from pathlib import Path


HEARTBEAT_FILE = os.getenv("ASSISTANT_HEARTBEAT_FILE", "/app/data/assistant.heartbeat")
MAX_STALE_SECONDS = int(os.getenv("HEALTHCHECK_MAX_STALE_SECONDS", "90"))


def main() -> int:
    hb = Path(HEARTBEAT_FILE)
    if not hb.exists():
        print("ASSISTANT HEALTHCHECK FAIL: heartbeat file not found")
        return 1

    try:
        age = time.time() - os.path.getmtime(hb)
    except OSError as e:
        print(f"ASSISTANT HEALTHCHECK FAIL: cannot stat heartbeat: {e}")
        return 1

    if age > MAX_STALE_SECONDS:
        print(f"ASSISTANT HEALTHCHECK FAIL: heartbeat stale ({int(age)}s old)")
        return 1

    print(f"ASSISTANT HEALTHCHECK OK: heartbeat {int(age)}s old")
    return 0


if __name__ == "__main__":
    sys.exit(main())
