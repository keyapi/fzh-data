import hashlib
import json
from pathlib import Path

import pytest

from supply_copilot import history


def make_manifest(tmp_path: Path):
    payloads = {"en_orders.parquet": b"orders", "demand_netting.parquet": b"netting"}
    manifest = {"version": "2026-10-26.1", "as_of": "2026-10-26", "files": []}
    for name, data in payloads.items():
        manifest["files"].append({"name": name, "sha256": hashlib.sha256(data).hexdigest(),
                                  "bytes": len(data), "rows": 1})
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, payloads


class Resp:
    def __init__(self, content, status=200):
        self.content = content
        self.status_code = status


def test_pull_history_verifies_and_skips_existing(tmp_path, monkeypatch):
    mpath, payloads = make_manifest(tmp_path)
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        name = url.split("name=")[-1]
        return Resp(payloads[name])

    monkeypatch.setattr(history, "token_headers", lambda env_file=None: {})
    monkeypatch.setattr(history.requests, "get", fake_get)
    root = tmp_path / "root"
    info = history.pull_history(root, manifest=manifest)
    assert len(info["downloaded"]) == 2
    target = history.history_dir(root, manifest["version"])
    assert (target / "en_orders.parquet").read_bytes() == b"orders"
    assert all("/api/method/key_test.demand_collaboration.history_download.get" in u for u in calls)

    again = history.pull_history(root, manifest=manifest)
    assert again["downloaded"] == []


def test_pull_history_403_raises(tmp_path, monkeypatch):
    mpath, payloads = make_manifest(tmp_path)
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    monkeypatch.setattr(history, "token_headers", lambda env_file=None: {})
    monkeypatch.setattr(history.requests, "get", lambda *a, **k: Resp(b"", status=403))
    with pytest.raises(SystemExit) as exc:
        history.pull_history(tmp_path / "root", manifest=manifest)
    assert "403" in str(exc.value)


def test_status_reports_missing_and_mismatch(tmp_path):
    mpath, payloads = make_manifest(tmp_path)
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    root = tmp_path / "root"
    target = history.history_dir(root, manifest["version"])
    target.mkdir(parents=True)
    (target / "en_orders.parquet").write_bytes(b"tampered")
    result = history.status(root, manifest=manifest)
    assert result["status"] == "incomplete"
    assert result["sha_mismatch"] == ["en_orders.parquet"]
    assert result["missing"] == ["demand_netting.parquet"]


def test_pull_orders_uses_orders_dir(tmp_path, monkeypatch):
    mpath, payloads = make_manifest(tmp_path)
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["version"] = "orders-2026-11-22.1"
    monkeypatch.setattr(history, "token_headers", lambda env_file=None: {})
    monkeypatch.setattr(history.requests, "get",
                        lambda url, headers=None, timeout=None: Resp(payloads[url.split("name=")[-1]]))
    root = tmp_path / "root"
    info = history.pull_orders(root, manifest=manifest)
    assert len(info["downloaded"]) == 2
    assert (root / "orders" / manifest["version"] / "en_orders.parquet").exists()
    assert history.orders_status(root, manifest=manifest)["status"] == "ok"
