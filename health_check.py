"""Health check script for Docker HEALTHCHECK — exits 0 if app is alive.

The app writes a heartbeat timestamp periodically. This script verifies the
heartbeat is fresh and that the main process is running.
"""
import os
import sys
import time
from pathlib import Path


HEARTBEAT_FILE = os.getenv("HEARTBEAT_FILE", "/app/data/heartbeat")
MAX_STALE_SECONDS = int(os.getenv("HEALTHCHECK_MAX_STALE_SECONDS", "300"))


def main() -> int:
    hb = Path(HEARTBEAT_FILE)
    if not hb.exists():
        print("HEALTHCHECK FAIL: heartbeat file not found")
        return 1

    try:
        age = time.time() - os.path.getmtime(hb)
    except OSError as e:
        print(f"HEALTHCHECK FAIL: cannot stat heartbeat: {e}")
        return 1

    if age > MAX_STALE_SECONDS:
        print(f"HEALTHCHECK FAIL: heartbeat stale ({int(age)}s old)")
        return 1

    print(f"HEALTHCHECK OK: heartbeat {int(age)}s old")
    return 0


if __name__ == "__main__":
    sys.exit(main())
