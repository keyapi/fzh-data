import hashlib
import json
import os
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SC14 = ROOT / "sc14"
SOURCE = SC14 / "SOURCE.json"


def file_sha256(path: Path) -> tuple[int, str]:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return data.count(b"\n"), hashlib.sha256(data).hexdigest()


def canonical_dir():
    for candidate in (os.environ.get("SC14_CANONICAL_DIR"),
                      ROOT / "local" / "sc14_canonical",
                      ROOT.parent / "sc14"):
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
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
        canonical = canonical_dir()
        if canonical is None:
            if os.environ.get("SC14_SYNC_REQUIRE") == "1":
                self.fail("SC14 canonical required but not available")
            self.skipTest("offline: canonical not available; run tests/run_canonical_tests.py")
        for name in self.source["files"]:
            self.assertEqual(
                file_sha256(SC14 / name),
                file_sha256(canonical / name),
                f"{name} drifted from {canonical}",
            )


if __name__ == "__main__":
    unittest.main()
