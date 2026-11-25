# -*- coding: utf-8 -*-
"""Release manifest verification: correct hashes pass, one tampered artifact
rejects the whole batch (v2.1 A4 immutable release)."""
import hashlib
import json
from pathlib import Path

import pytest

from supply_copilot.release_manifest import (
    FROZEN_RELEASE,
    ReleaseVerificationError,
    verify_release,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_release(tmp_path: Path, *, status="ready_for_B", immutable=True,
                  artifacts=None) -> tuple[Path, dict]:
    """Build a synthetic release directory and return (dir, pins)."""
    root = tmp_path / "release"
    root.mkdir()
    files = artifacts or {
        "snapshot_v2.json": b'{"schema_version": "supply-workbench-snapshot-v2", "rows": []}',
        "baseline_v2.json": b'{"schema_version": "supply-workbench-baseline-v2", "rows": []}',
        "snapshot_v2_schema.md": b"# schema\n",
        "decide_usnj.json": b'{"rows": []}',
    }
    bound = {}
    for name, data in files.items():
        path = root / name
        path.write_bytes(data)
        bound[name] = {"role": "test", "sha256": _sha(path),
                       "size": path.stat().st_size, "file": name}
    manifest = {
        "schema_version": "supply-release-manifest-v1",
        "release_id": "20261125T095418+0800",
        "display_version": "v2.1.0-20261125",
        "status": status,
        "immutable": immutable,
        "parent_bundle": "b" * 64,
        "artifacts": bound,
    }
    (root / "release_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    pins = {name: _sha(root / name) for name in bound}
    pins["release_manifest.json"] = _sha(root / "release_manifest.json")
    return root, pins


def test_correct_hashes_pass(tmp_path):
    root, pins = _make_release(tmp_path)
    out = verify_release(root, pins=pins)
    assert out["release_id"] == "20261125T095418+0800"
    assert out["display_version"] == "v2.1.0-20261125"
    assert out["parent_bundle"] == "b" * 64
    assert set(out["artifacts"]) >= {"snapshot_v2.json", "baseline_v2.json"}
    assert out["artifacts"]["snapshot_v2.json"]["sha256"] == pins["snapshot_v2.json"]


def test_tampered_snapshot_rejects_whole_batch(tmp_path):
    root, pins = _make_release(tmp_path)
    (root / "snapshot_v2.json").write_bytes(b'{"tampered": true}')
    with pytest.raises(ReleaseVerificationError) as exc:
        verify_release(root, pins=pins)
    assert "snapshot_v2.json sha256" in str(exc.value)
    # Nothing partially verified is returned.
    assert not hasattr(exc.value, "artifacts")


def test_tampered_manifest_rejected_by_pin(tmp_path):
    root, pins = _make_release(tmp_path)
    manifest = json.loads((root / "release_manifest.json").read_text(encoding="utf-8"))
    manifest["display_version"] = "v9.9.9-forged"
    (root / "release_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ReleaseVerificationError) as exc:
        verify_release(root, pins=pins)
    assert "release_manifest.json sha256" in str(exc.value)


def test_missing_artifact_rejected(tmp_path):
    root, pins = _make_release(tmp_path)
    (root / "baseline_v2.json").unlink()
    with pytest.raises(ReleaseVerificationError) as exc:
        verify_release(root, pins=pins)
    assert "baseline_v2.json missing" in str(exc.value)


def test_unbound_required_artifact_rejected(tmp_path):
    root, pins = _make_release(tmp_path)
    manifest = json.loads((root / "release_manifest.json").read_text(encoding="utf-8"))
    del manifest["artifacts"]["baseline_v2.json"]
    (root / "release_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    pins["release_manifest.json"] = _sha(root / "release_manifest.json")
    with pytest.raises(ReleaseVerificationError) as exc:
        verify_release(root, pins=pins)
    assert "does not bind baseline_v2.json" in str(exc.value)


def test_status_and_immutable_are_enforced(tmp_path):
    root, pins = _make_release(tmp_path, status="draft", immutable=False)
    with pytest.raises(ReleaseVerificationError) as exc:
        verify_release(root, pins=pins)
    text = str(exc.value)
    assert "'ready_for_B'" in text and "immutable is not true" in text


def test_all_failures_collected_not_first_only(tmp_path):
    root, pins = _make_release(tmp_path)
    (root / "snapshot_v2.json").write_bytes(b"x")
    (root / "baseline_v2.json").write_bytes(b"y")
    with pytest.raises(ReleaseVerificationError) as exc:
        verify_release(root, pins=pins)
    assert len(exc.value.failures) >= 2


def test_frozen_constants_match_brief():
    assert FROZEN_RELEASE == {
        "release_manifest.json":
            "e357e766e7a6d56e6b28583f9322fe3eb8b48d22b3945b09375364310e00e71a",
        "snapshot_v2.json":
            "5ea2fd3aabaa00e3e6b80d1915ee1366db90d9d5db11b42002157879fff01dd7",
        "baseline_v2.json":
            "1330179fc314b8699dac94e48b21458b25ec0e855d3ae0990ad8d82586783028",
        "snapshot_v2_schema.md":
            "94470493c97e8dd357ed2695e83f772b0239b2b0df88c4274f5375a6d246772a",
    }


REAL_RELEASE = Path(
    "D:/Work/fzh-order-store/analysis/workbench-latest-20261124/"
    "releases/20261125T095418+0800")


@pytest.mark.skipif(not REAL_RELEASE.is_dir(), reason="frozen release not on this machine")
def test_real_frozen_release_verifies():
    out = verify_release(REAL_RELEASE)
    assert out["release_id"] == "20261125T095418+0800"
    assert out["display_version"] == "v2.1.0-20261125"
    assert out["artifacts"]["snapshot_v2.json"]["path"].name == "snapshot_v2.json"
