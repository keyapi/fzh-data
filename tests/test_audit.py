"""P0 审计头 / bundle_id / 本地校验 / 选包 的离线测试。"""

import hashlib
import json
import os
import time
from pathlib import Path

import pandas as pd

from supply_copilot import audit


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #
def write_parquet(path: Path, rows: int) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"id": range(rows)}).to_parquet(path, index=False)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def make_version_dir(root: Path, kind: str, version: str, as_of: str) -> Path:
    target = root / kind / version
    target.mkdir(parents=True)
    (target / "manifest.json").write_text(
        json.dumps({"version": version, "as_of": as_of}), encoding="utf-8")
    return target


def set_mtime(path: Path, epoch: float) -> None:
    os.utime(path, (epoch, epoch))


# --------------------------------------------------------------------------- #
# bundle_id
# --------------------------------------------------------------------------- #
def test_bundle_id_is_stable_and_order_independent():
    first = audit.build_bundle_meta(
        tool={"version": "0.1.0"}, engine={"rule_version": "autoets_m3_naive@t5"})
    reordered = audit.build_bundle_meta(
        engine={"rule_version": "autoets_m3_naive@t5"}, tool={"version": "0.1.0"})
    assert audit.bundle_id(first) == audit.bundle_id(reordered)
    assert audit.bundle_id(first) == audit.bundle_id(first)

    digest = audit.bundle_id(first)
    assert len(digest) == 64
    assert all(ch in "0123456789abcdef" for ch in digest)


def test_bundle_id_differs_when_content_differs():
    base = audit.build_bundle_meta(tool={"version": "0.1.0"})
    changed = audit.build_bundle_meta(tool={"version": "0.1.1"})
    assert audit.bundle_id(base) != audit.bundle_id(changed)


def test_build_bundle_meta_defaults_none_and_copies_axes():
    tool = {"version": "0.1.0"}
    meta = audit.build_bundle_meta(tool=tool)
    assert meta["tool"] == {"version": "0.1.0"}
    for axis in ("engine", "policy", "data", "live", "forecast", "computed_at"):
        assert meta[axis] is None, axis
    assert set(meta) == set(audit.AXES) | {"computed_at"}

    tool["version"] = "mutated"
    assert meta["tool"]["version"] == "0.1.0"


# --------------------------------------------------------------------------- #
# verify_local
# --------------------------------------------------------------------------- #
def build_fixture(root: Path):
    pack_payload = b"pack-bytes"
    pack_file = root / "data" / "D6.xlsx"
    pack_file.parent.mkdir(parents=True)
    pack_file.write_bytes(pack_payload)
    pack = {"version": "2026-11-13.1", "as_of": "2026-11-13",
            "files": [{"path": "data/D6.xlsx", "sha256": sha_bytes(pack_payload)}]}

    hist_dir = root / "history" / "2026-10-26.1"
    hist_sha = write_parquet(hist_dir / "en_orders.parquet", 5)
    history = {"version": "2026-10-26.1", "as_of": "2026-10-26",
               "files": [{"name": "en_orders.parquet", "sha256": hist_sha, "rows": 5}]}

    orders_dir = root / "orders" / "orders-2026-11-22.1"
    orders_sha = write_parquet(orders_dir / "orders_unified.parquet", 3)
    orders = {"version": "orders-2026-11-22.1", "as_of": "2026-11-22",
              "files": [{"name": "orders_unified.parquet", "sha256": orders_sha, "rows": 3}]}
    return pack, history, orders, pack_file, hist_dir, orders_dir


def test_verify_local_ok(tmp_path):
    pack, history, orders, *_ = build_fixture(tmp_path)
    result = audit.verify_local(
        tmp_path, pack_manifest=pack, history_manifest=history, orders_manifest=orders)
    assert result["ok"] is True
    assert result["issues"] == []
    assert result["checked"] == 3


def test_verify_local_reports_sha_mismatch(tmp_path):
    pack, history, orders, pack_file, *_ = build_fixture(tmp_path)
    pack_file.write_bytes(b"tampered")
    result = audit.verify_local(
        tmp_path, pack_manifest=pack, history_manifest=history, orders_manifest=orders)
    assert result["ok"] is False
    issue = next(i for i in result["issues"] if i["scope"] == "pack")
    assert issue["file"] == "data/D6.xlsx"
    assert issue["expected"] == pack["files"][0]["sha256"]
    assert issue["actual"] == sha_bytes(b"tampered")


def test_verify_local_reports_missing_file(tmp_path):
    pack, history, orders, _pack_file, hist_dir, _orders_dir = build_fixture(tmp_path)
    (hist_dir / "en_orders.parquet").unlink()
    result = audit.verify_local(
        tmp_path, pack_manifest=pack, history_manifest=history, orders_manifest=orders)
    assert result["ok"] is False
    issue = next(i for i in result["issues"] if i["scope"] == "history")
    assert issue == {"scope": "history", "file": "en_orders.parquet",
                     "expected": "文件存在", "actual": "缺失"}


def test_verify_local_reports_rows_mismatch(tmp_path):
    pack, history, orders, _pack_file, _hist_dir, orders_dir = build_fixture(tmp_path)
    # 重写订单文件：sha 与新内容一致，但 manifest 里的 rows 仍是旧值
    new_sha = write_parquet(orders_dir / "orders_unified.parquet", 7)
    orders["files"][0]["sha256"] = new_sha
    result = audit.verify_local(
        tmp_path, pack_manifest=pack, history_manifest=history, orders_manifest=orders)
    issue = next(i for i in result["issues"] if i["scope"] == "orders")
    assert issue["expected"] == 3
    assert issue["actual"] == 7


def test_verify_local_accepts_manifest_paths(tmp_path):
    pack, history, orders, *_ = build_fixture(tmp_path)
    manifests = {}
    for name, manifest in (("pack", pack), ("history", history), ("orders", orders)):
        path = tmp_path / f"{name}_manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        manifests[name] = path
    result = audit.verify_local(
        tmp_path,
        pack_manifest=manifests["pack"],
        history_manifest=manifests["history"],
        orders_manifest=manifests["orders"])
    assert result["ok"] is True


# --------------------------------------------------------------------------- #
# select_current
# --------------------------------------------------------------------------- #
def test_select_current_picks_version_not_mtime(tmp_path):
    make_version_dir(tmp_path, "orders", "orders-2026-11-21.1", "2026-11-21")
    newer = make_version_dir(tmp_path, "orders", "orders-2026-11-22.1", "2026-11-22")

    # 旧版本目录被"后拷入"，mtime 更新得更晚
    future = time.time() + 10_000
    old_dir = tmp_path / "orders" / "orders-2026-11-21.1"
    set_mtime(old_dir, future)
    set_mtime(old_dir / "manifest.json", future)

    assert audit.select_current(tmp_path, "orders") == newer

    # history 同口径
    make_version_dir(tmp_path, "history", "2026-10-20.1", "2026-10-20")
    hist_new = make_version_dir(tmp_path, "history", "2026-10-26.1", "2026-10-26")
    set_mtime(tmp_path / "history" / "2026-10-20.1", future)
    assert audit.select_current(tmp_path, "history") == hist_new


def test_select_current_uses_same_day_sequence(tmp_path):
    make_version_dir(tmp_path, "orders", "orders-2026-11-22.1", "2026-11-22")
    later = make_version_dir(tmp_path, "orders", "orders-2026-11-22.2", "2026-11-22")
    assert audit.select_current(tmp_path, "orders") == later


def test_select_current_none_or_pack_layout(tmp_path):
    assert audit.select_current(tmp_path, "orders") is None
    assert audit.select_current(tmp_path, "history") is None
    assert audit.select_current(tmp_path, "pack") is None

    (tmp_path / "data").mkdir()
    (tmp_path / "manifest.json").write_text(
        json.dumps({"version": "2026-11-13.1"}), encoding="utf-8")
    assert audit.select_current(tmp_path, "pack") == tmp_path / "data"


def test_select_current_rejects_unknown_kind(tmp_path):
    try:
        audit.select_current(tmp_path, "forecast")
    except ValueError as exc:
        assert "manifest_kind" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("未知 kind 应抛 ValueError")


# --------------------------------------------------------------------------- #
# format_header
# --------------------------------------------------------------------------- #
def test_format_header_contains_bundle_id_and_as_of():
    meta = audit.build_bundle_meta(
        tool={"version": "0.1.0", "git_sha": "abcdef1234567"},
        data={"as_of": "2026-11-13", "pack": {"version": "2026-11-13.1"}},
        forecast={"run_id": "run-001", "as_of": "2026-11-13"})
    text = audit.format_header(meta)
    lines = text.splitlines()
    assert 2 <= len(lines) <= 4
    assert audit.bundle_id(meta) in text
    assert "2026-11-13" in text
    assert "bundle_id:" in lines[0]
    assert "as_of:" in lines[1]


def test_format_header_warns_when_data_is_stale():
    meta = audit.build_bundle_meta(
        data={"as_of": "2026-11-01"}, computed_at="2026-11-20T10:00:00")
    lines = audit.format_header(meta).splitlines()
    assert len(lines) <= 4
    assert any("新鲜度" in line for line in lines)


def test_format_header_does_not_guess_missing_as_of():
    meta = audit.build_bundle_meta(tool={"version": "0.1.0"})
    text = audit.format_header(meta)
    assert "as_of: 未声明" in text
    assert 2 <= len(text.splitlines()) <= 4
