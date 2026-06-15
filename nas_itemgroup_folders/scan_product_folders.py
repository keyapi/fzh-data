# -*- coding: utf-8 -*-
"""扫描 NAS /产品信息 下所有文件夹，统计文件数，支持变更追踪。

使用:
  uv run python nas_itemgroup_folders/scan_product_folders.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_DIR_OUT = _DIR / "out"
_DIR_OUT.mkdir(parents=True, exist_ok=True)
_NAS_API = _DIR.parent / "NAS_API"
sys.path.insert(0, str(_DIR.parent))

from NAS_API.synology import _load_dotenv, get_nas  # noqa: E402
from nas_itemgroup_folders.reconcile import parse_model_id  # noqa: E402

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

_load_dotenv([_NAS_API / ".env", _DIR / ".env"])

TARGET = os.getenv("NAS_TARGET_FOLDER", "/产品信息")


# ── Helpers ────────────────────────────────────────────────

def _fmt_size(size_bytes: int) -> str:
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.1f} GB"
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    if size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.1f} KB"
    return f"{size_bytes} B"


def _scan_folder(nas, path: str) -> dict:
    """递归扫描一个文件夹，返回 {file_count, total_bytes, last_modified}。"""
    file_count = 0
    total_bytes = 0
    last_modified = 0
    items = nas.get_file_list(path, limit=5000)
    for item in items:
        if item["is_dir"]:
            sub = _scan_folder(nas, f"{path}/{item['name']}")
            file_count += sub["file_count"]
            total_bytes += sub["total_bytes"]
            if sub["last_modified"] > last_modified:
                last_modified = sub["last_modified"]
        else:
            file_count += 1
            total_bytes += item.get("size", 0)
            mtime = item.get("mtime", 0)
            if mtime > last_modified:
                last_modified = mtime
    return {"file_count": file_count, "total_bytes": total_bytes, "last_modified": last_modified}


# ── Main ───────────────────────────────────────────────────

def main() -> None:
    print(f"=== /产品信息 文件夹扫描 ===  {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    nas = get_nas()
    if not nas.available:
        print("[error] NAS 不可达，请确认 VPN 已连接。")
        sys.exit(1)

    # 1. 列出 /产品信息 下所有直接子目录
    print(f">>> 扫描 {TARGET} ...")
    items = nas.get_file_list(TARGET, limit=5000)
    dirs = [i for i in items if i["is_dir"]]
    print(f"    发现 {len(dirs)} 个文件夹，正在统计文件...")

    # 2. 逐个递归扫描
    folders = []
    for i, d in enumerate(dirs):
        name = d["name"]
        path = d["path"]
        stats = _scan_folder(nas, path)
        mid = parse_model_id(name)
        mtime_str = (
            datetime.fromtimestamp(stats["last_modified"]).strftime("%Y-%m-%d %H:%M")
            if stats["last_modified"] else "-"
        )
        folders.append({
            "name": name,
            "path": path,
            "is_ks": mid is not None,
            "model_id": mid,
            "file_count": stats["file_count"],
            "total_bytes": stats["total_bytes"],
            "last_modified": stats["last_modified"],
            "last_modified_str": mtime_str,
        })
        if (i + 1) % 50 == 0:
            print(f"    {i + 1}/{len(dirs)} ...")

    # 3. 排序：有文件的排前面，同组按文件数降序
    folders.sort(key=lambda f: (-f["file_count"], f["name"]))

    # 4. 终端输出
    has_files = [f for f in folders if f["file_count"] > 0]
    empty = [f for f in folders if f["file_count"] == 0]
    total_files = sum(f["file_count"] for f in folders)
    total_bytes = sum(f["total_bytes"] for f in folders)

    print(f"\n文件夹数: {len(folders)}  有文件: {len(has_files)}  空: {len(empty)}")
    print(f"总文件数: {total_files}  总大小: {_fmt_size(total_bytes)}")

    # 表格：先列有文件的，再列前 20 个空的
    print(f"\n{'文件夹名':<40s} {'文件数':>6s}  {'大小':>10s}  {'最后修改':>16s}")
    print("-" * 78)
    for f in has_files:
        marker = " *" if not f["is_ks"] else ""
        print(f"{f['name'] + marker:<40s} {f['file_count']:>6d}  {_fmt_size(f['total_bytes']):>10s}  {f['last_modified_str']:>16s}")
    if empty:
        print(f"\n── 以下 {len(empty)} 个文件夹为空 ──")
        for f in empty[:30]:
            print(f"  {f['name']}")
        if len(empty) > 30:
            print(f"  ... 共 {len(empty)} 个空文件夹")

    # 5. 保存快照
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot = {
        "scanned_at": datetime.now().isoformat(),
        "target_folder": TARGET,
        "total_folders": len(folders),
        "folders_with_content": len(has_files),
        "folders_empty": len(empty),
        "total_files": total_files,
        "total_bytes": total_bytes,
        "folders": [
            {k: v for k, v in f.items() if k != "last_modified_str"}
            for f in folders
        ],
    }

    snapshot_path = _DIR_OUT / f"scan_{ts}.json"
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"\n快照: {snapshot_path}")

    # 6. 对比上次快照
    prev = _find_previous_snapshot(snapshot_path)
    if prev:
        _print_diff(prev, snapshot)

    print("\n完成。")


def _find_previous_snapshot(current: Path) -> dict | None:
    """找到最近一次非当前的 scan_*.json 快照。"""
    scans = sorted(
        [p for p in _DIR_OUT.glob("scan_*.json") if p != current],
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not scans:
        return None
    try:
        return json.loads(scans[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def _print_diff(prev: dict, curr: dict) -> None:
    """对比两次快照，打印变更摘要。"""
    prev_time = prev.get("scanned_at", "?").replace("T", " ")[:16]
    curr_time = curr.get("scanned_at", "?").replace("T", " ")[:16]

    prev_map = {f["path"]: f for f in prev["folders"]}
    curr_map = {f["path"]: f for f in curr["folders"]}

    prev_paths = set(prev_map.keys())
    curr_paths = set(curr_map.keys())

    new_folders = curr_paths - prev_paths
    deleted_folders = prev_paths - curr_paths
    common = prev_paths & curr_paths

    # 文件数变化
    increased = []
    decreased = []
    for p in common:
        delta = curr_map[p]["file_count"] - prev_map[p]["file_count"]
        if delta > 0:
            increased.append((curr_map[p]["name"], delta))
        elif delta < 0:
            decreased.append((curr_map[p]["name"], delta))

    print(f"\n>>> 对比上次扫描 ({prev_time})")
    changed = False

    if new_folders:
        changed = True
        new_with = [n for n in new_folders if curr_map[n]["file_count"] > 0]
        new_empty = [n for n in new_folders if curr_map[n]["file_count"] == 0]
        if new_with:
            print(f"  新增文件夹 (有文件): {len(new_with)}")
            for p in sorted(new_with, key=lambda x: -curr_map[x]["file_count"]):
                f = curr_map[p]
                print(f"    + {f['name']}  ({f['file_count']} 文件, {_fmt_size(f['total_bytes'])})")
        if new_empty:
            print(f"  新增文件夹 (空): {len(new_empty)}")

    if deleted_folders:
        changed = True
        print(f"  移除文件夹: {len(deleted_folders)}")
        for p in sorted(deleted_folders):
            f = prev_map[p]
            if f["file_count"] > 0:
                print(f"    - {f['name']}  (原有 {f['file_count']} 文件)")

    if increased:
        changed = True
        total_added = sum(d for _, d in increased)
        print(f"  文件增加 ({total_added} 个):")
        for name, delta in sorted(increased, key=lambda x: -x[1]):
            print(f"    {name}  +{delta}")

    if decreased:
        changed = True
        total_removed = sum(-d for _, d in decreased)
        print(f"  文件减少 ({total_removed} 个):")
        for name, delta in sorted(decreased, key=lambda x: x[1]):
            print(f"    {name}  {delta}")

    if not changed:
        print("  无变化。")

    # 汇总
    prev_total = prev.get("total_files", 0)
    curr_total = curr.get("total_files", 0)
    prev_bytes = prev.get("total_bytes", 0)
    curr_bytes = curr.get("total_bytes", 0)
    delta_files = curr_total - prev_total
    delta_bytes = curr_bytes - prev_bytes
    sign_f = "+" if delta_files >= 0 else ""
    sign_b = "+" if delta_bytes >= 0 else ""
    print(f"\n  汇总: {sign_f}{delta_files} 文件, {sign_b}{_fmt_size(abs(delta_bytes)) if delta_bytes < 0 else _fmt_size(delta_bytes)}")


if __name__ == "__main__":
    main()
