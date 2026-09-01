#!/usr/bin/env python3
"""Check C-drive health for the Cursor + Synology Drive disk-drain issue.

Run: uv run python scripts/check_cursor_cdrive_health.py

Checks three signals that preceded the 2026-08-28~09-01 C-drive depletion:
  1. C: free space low
  2. state.vscdb / its WAL oversized (known Cursor bloat bug)
  3. Synology Drive continuous-backup staging dirs (the actual drain)
Exit code 1 when any warning fires; useful for periodic checks.
"""

import os
import shutil
import sys
from pathlib import Path


def gb(n: int) -> str:
    return f"{n / 1024**3:.2f} GB"


def main() -> int:
    problems: list[str] = []

    # 1. C: free space
    try:
        total, used, free = shutil.disk_usage("C:\\")
        print(f"[C:] free {gb(free)} / total {gb(total)}")
        if free < 10 * 1024**3:
            problems.append("C: free < 10GB")
    except OSError as e:
        print(f"[C:] error: {e}")

    # 2. state.vscdb and its WAL (WAL ballooning = something rewriting the DB)
    gs = Path(os.environ.get("APPDATA", "")) / "Cursor" / "User" / "globalStorage"
    for name in ("state.vscdb", "state.vscdb-wal"):
        f = gs / name
        if f.is_file():
            size = f.stat().st_size
            print(f"[cursor] {name}: {gb(size)}")
            if size > 20 * 1024**3:
                problems.append(f"{name} > 20GB")
        else:
            print(f"[cursor] {name}: not found")

    # 3. Synology Drive continuous-backup staging dirs
    syn = Path(os.environ.get("LOCALAPPDATA", "")) / "SynologyDrive" / "temp"
    if syn.is_dir():
        for working in syn.glob("*/.SynologyWorkingDirectory"):
            size = sum(p.stat().st_size for p in working.rglob("*") if p.is_file())
            print(f"[synology] {working}: {gb(size)}")
            if size > 5 * 1024**3:
                problems.append(f"Synology staging {working} > 5GB")
    else:
        print("[synology] temp dir not found")

    print()
    if problems:
        print("WARNINGS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: Cursor C-drive health fine")
    return 0


if __name__ == "__main__":
    sys.exit(main())
