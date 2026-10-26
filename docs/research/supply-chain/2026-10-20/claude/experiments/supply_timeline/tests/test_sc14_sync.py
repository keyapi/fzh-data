import hashlib
import json
import os
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SC14 = ROOT / "sc14"
SOURCE = SC14 / "SOURCE.json"
CANONICAL_REL = "docs/research/supply-chain/2026-10-20/claude/experiments/sc14"


def normalized_sha256(data: bytes) -> tuple[int, str]:
    data = data.replace(b"\r\n", b"\n")
    return data.count(b"\n"), hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> tuple[int, str]:
    return normalized_sha256(path.read_bytes())


def git_sha256(name: str):
    rel = f"{CANONICAL_REL}/{name}"
    for ref in ("origin/docs/jack-w1-channel", "docs/jack-w1-channel"):
        try:
            return normalized_sha256(
                subprocess.check_output(["git", "show", f"{ref}:{rel}"], cwd=ROOT, stderr=subprocess.DEVNULL))
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    try:
        subprocess.check_output(["git", "fetch", "--depth=1", "origin", "docs/jack-w1-channel"],
                                cwd=ROOT, stderr=subprocess.DEVNULL, timeout=60)
        return normalized_sha256(
            subprocess.check_output(["git", "show", f"FETCH_HEAD:{rel}"], cwd=ROOT, stderr=subprocess.DEVNULL))
    except Exception:
        return None


class Sc14SyncTest(unittest.TestCase):
    def setUp(self):
        self.source = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_pinned_hashes(self):
        for name, expected in self.source["files"].items():
            lines, digest = file_sha256(SC14 / name)
            self.assertEqual(lines, expected["lines"], name)
            self.assertEqual(digest, expected["sha256_lf"], name)

    def test_canonical_matches(self):
        canonical = Path(os.environ.get("SC14_CANONICAL_DIR", ROOT.parent / "sc14"))
        for name in self.source["files"]:
            expected = file_sha256(canonical / name) if canonical.is_dir() else git_sha256(name)
            if expected is None:
                if os.environ.get("SC14_SYNC_REQUIRE") == "1" or os.environ.get("GITHUB_ACTIONS"):
                    self.fail(f"SC14 canonical unavailable for {name}")
                self.skipTest("canonical sc14 not available (no dir, no git ref)")
            self.assertEqual(file_sha256(SC14 / name), expected, f"{name} drifted from canonical")


if __name__ == "__main__":
    unittest.main()
