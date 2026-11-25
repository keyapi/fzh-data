# -*- coding: utf-8 -*-
"""Frozen release verification for the supply workbench (v2.1).

B renders **only** the artifacts named by ``release_manifest.json`` — never the
"newest file" in a directory, never a mix of runs. Every bound artifact is
checked against the manifest's sha256/size, the manifest itself is pinned to
the exact release frozen for this round, and the whole batch is rejected if a
single check fails (no partial render).

The pins below are the frozen ``v2.1.0-20261125`` release. A new release needs
a new pin set and a new ``display_version`` — that is what ``immutable`` means.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "supply-release-manifest-v1"
MANIFEST = "release_manifest.json"

# A's release 20261125T095418+0800 (frozen input for this round).
FROZEN_RELEASE = {
    "release_manifest.json": "e357e766e7a6d56e6b28583f9322fe3eb8b48d22b3945b09375364310e00e71a",
    "snapshot_v2.json": "5ea2fd3aabaa00e3e6b80d1915ee1366db90d9d5db11b42002157879fff01dd7",
    "baseline_v2.json": "1330179fc314b8699dac94e48b21458b25ec0e855d3ae0990ad8d82586783028",
    "snapshot_v2_schema.md": "94470493c97e8dd357ed2695e83f772b0239b2b0df88c4274f5375a6d246772a",
}

# Artifacts the page cannot render without. The decide source is verified when
# the manifest binds it, but is never displayed directly.
REQUIRED_ARTIFACTS = ("snapshot_v2.json", "baseline_v2.json", "snapshot_v2_schema.md")


class ReleaseVerificationError(ValueError):
    """One or more release checks failed; the whole batch must be rejected."""

    def __init__(self, failures, release_dir=None):
        self.failures = list(failures)
        where = f" ({release_dir})" if release_dir else ""
        super().__init__("release verification failed%s: %s" % (where, "; ".join(self.failures)))


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _short(value, n=12):
    text = "" if value is None else str(value)
    return text[:n] + "…" if len(text) > n else text


def verify_release(release_dir, pins=None) -> dict:
    """Verify ``release_dir`` and return the bound artifacts.

    ``pins`` maps file name -> expected sha256; it defaults to
    :data:`FROZEN_RELEASE`. Pass ``pins={}`` to verify only the manifest's
    internal consistency (useful for a newer release). Every failure is
    collected and raised as one :class:`ReleaseVerificationError`.
    """
    pins = dict(FROZEN_RELEASE if pins is None else pins)
    root = Path(release_dir)
    failures = []

    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        raise ReleaseVerificationError(["missing %s" % MANIFEST], root)

    if MANIFEST in pins:
        actual = sha256_file(manifest_path)
        if actual != pins[MANIFEST]:
            failures.append("%s sha256 %s != pinned %s" % (
                MANIFEST, _short(actual), _short(pins[MANIFEST])))

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReleaseVerificationError(["%s unreadable: %s" % (MANIFEST, exc)], root)

    if not isinstance(manifest, dict):
        raise ReleaseVerificationError(["%s is not a JSON object" % MANIFEST], root)

    if manifest.get("schema_version") != SCHEMA:
        failures.append("schema_version %r != %r" % (manifest.get("schema_version"), SCHEMA))
    if manifest.get("status") != "ready_for_B":
        failures.append("status %r != 'ready_for_B'" % (manifest.get("status"),))
    if manifest.get("immutable") is not True:
        failures.append("immutable is not true")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        failures.append("artifacts block missing/empty")
        artifacts = {}

    verified = {}
    for name, spec in artifacts.items():
        if not isinstance(spec, dict):
            failures.append("artifacts[%s] is not an object" % name)
            continue
        fname = spec.get("file") or name
        expected = spec.get("sha256")
        path = root / fname
        if not path.is_file():
            failures.append("%s missing" % fname)
            continue
        actual = sha256_file(path)
        if not expected:
            failures.append("%s has no sha256 in manifest" % fname)
            continue
        if actual != expected:
            failures.append("%s sha256 %s != manifest %s" % (
                fname, _short(actual), _short(expected)))
            continue
        size = spec.get("size")
        if isinstance(size, int) and path.stat().st_size != size:
            failures.append("%s size %d != manifest %d" % (fname, path.stat().st_size, size))
            continue
        if name in pins and expected != pins[name]:
            failures.append("%s manifest sha256 %s != pinned %s" % (
                fname, _short(expected), _short(pins[name])))
            continue
        verified[name] = {
            "path": path,
            "sha256": actual,
            "size": path.stat().st_size,
            "role": spec.get("role"),
        }

    for name in REQUIRED_ARTIFACTS:
        if name not in artifacts:
            failures.append("manifest does not bind %s" % name)

    if failures:
        raise ReleaseVerificationError(failures, root)

    return {
        "dir": root,
        "manifest": manifest,
        "manifest_sha256": pins.get(MANIFEST) or sha256_file(manifest_path),
        "release_id": manifest.get("release_id"),
        "display_version": manifest.get("display_version"),
        "parent_bundle": manifest.get("parent_bundle"),
        "artifacts": verified,
    }
