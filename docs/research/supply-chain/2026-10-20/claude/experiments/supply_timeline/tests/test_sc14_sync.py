import hashlib
import json
import os
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SC14 = ROOT / "sc14"
SOURCE = SC14 / "SOURCE.json"


def normalized_sha256(path: Path) -> tuple[int, str]:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return data.count(b"\n"), hashlib.sha256(data).hexdigest()


class Sc14SyncTest(unittest.TestCase):
    def setUp(self):
        self.source = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_pinned_hashes(self):
        for name, expected in self.source["files"].items():
            lines, digest = normalized_sha256(SC14 / name)
            self.assertEqual(lines, expected["lines"], name)
            self.assertEqual(digest, expected["sha256_lf"], name)

    def test_canonical_matches_if_present(self):
        canonical = Path(os.environ.get("SC14_CANONICAL_DIR", ROOT.parent / "sc14"))
        if not canonical.is_dir():
            self.skipTest(f"canonical sc14 not checked out at {canonical}")
        for name in self.source["files"]:
            self.assertEqual(
                normalized_sha256(SC14 / name),
                normalized_sha256(canonical / name),
                f"{name} drifted from {canonical}",
            )


if __name__ == "__main__":
    unittest.main()
