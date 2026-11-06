#!/usr/bin/env python3
"""Fetch the canonical SC14 contract from the docs branch into local/ and run tests offline."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "local" / "sc14_canonical"
REL = "docs/research/supply-chain/2026-10-20/claude/experiments/sc14"
NAMES = ("contract.py", "test_contract.py")


def main() -> int:
    subprocess.run(["git", "fetch", "--depth=1", "origin", "docs/jack-w1-channel"], cwd=ROOT, check=True)
    DEST.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        data = subprocess.check_output(["git", "show", f"FETCH_HEAD:{REL}/{name}"], cwd=ROOT)
        (DEST / name).write_bytes(data)
    env = dict(os.environ, SC14_CANONICAL_DIR=str(DEST), SC14_SYNC_REQUIRE="1")
    return subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
