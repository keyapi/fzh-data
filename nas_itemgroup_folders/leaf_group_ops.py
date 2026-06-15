# -*- coding: utf-8 -*-
"""叶子组 NAS 文件夹操作 — 轻量精准工具，不扫全盘。

用法:
  uv run python nas_itemgroup_folders/leaf_group_ops.py status                # 查看12个叶子组当前状态
  uv run python nas_itemgroup_folders/leaf_group_ops.py create LGKS0220        # 创建指定叶子组+子文件夹
  uv run python nas_itemgroup_folders/leaf_group_ops.py move LGKS0220          # 移动KS子文件夹进叶子组
  uv run python nas_itemgroup_folders/leaf_group_ops.py verify LGKS0220        # 验证叶子组目录结构
  uv run python nas_itemgroup_folders/leaf_group_ops.py setup LGKS0220         # create + move 一步到位
  uv run python nas_itemgroup_folders/leaf_group_ops.py setup --all            # 全部12个
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_NAS_API = _DIR.parent / "NAS_API"
sys.path.insert(0, str(_DIR.parent))

from NAS_API.synology import _load_dotenv, get_nas  # noqa: E402

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

_load_dotenv([_NAS_API / ".env", _DIR / ".env"])
TARGET = os.getenv("NAS_TARGET_FOLDER", "/产品信息")
SUBS = os.getenv("SUB_FOLDERS", "调研报告,设计稿,图片,视频").split(",")

# ── 12 叶子组定义 (model_id: {name, children}) ─────────────

LEAF_GROUPS = {
    "LGKS0220": {"name": "可组合扶手沙发", "children": ["KS0220", "KS0245", "KS0246"]},
    "LGKS0238": {"name": "儿童泡沫攀岩块类", "children": ["KS0240", "KS0241", "KS0242", "KS0243", "KS0238"]},
    "LGKS0334": {"name": "几何链条抱枕", "children": ["KS0334", "KS0335", "KS0336"]},
    "LGKS0369": {"name": "逗号组合沙发", "children": ["KS0369", "KS0378", "KS0379"]},
    "LGKS0387": {"name": "复古造型大体量沙发", "children": ["KS0387", "KS0391", "KS0392", "KS0393"]},
    "LGKS0407": {"name": "游乐场懒人沙发模块", "children": ["KS0407", "KS0408", "KS0409", "KS0410"]},
    "LGKS0459": {"name": "户外托盘垫", "children": ["KS0459", "KS0460", "KS0461", "KS0462", "KS0493", "KS0494"]},
    "LGKS0489": {"name": "床头软装组合", "children": ["KS0489", "KS0490", "KS0491"]},
    "LGKS0496": {"name": "户外托盘垫印花款类", "children": ["KS0496", "KS0497", "KS0498", "KS0499"]},
    "LGKS0502": {"name": "自由模块沙发", "children": ["KS0502", "KS0503", "KS0504", "KS0505", "KS0506", "KS0507", "KS0508"]},
    "LGKS0511": {"name": "歌剧院床头靠枕套装", "children": ["KS0511", "KS0518", "KS0519"]},
    "LGKS0525": {"name": "组合式户外沙发", "children": ["KS0525", "KS0526", "KS0527"]},
}


# ── Helpers ────────────────────────────────────────────────

def _get_nas():
    nas = get_nas()
    if not nas.available or not nas._fl:
        print("[error] NAS 不可达，请确认 VPN 已连接。")
        sys.exit(1)
    return nas._fl


def _leaf_folder(mid: str) -> str:
    lg = LEAF_GROUPS[mid]
    return f"{TARGET}/{mid}_{lg['name']}"


def _list_root_dirs(fl) -> dict[str, str]:
    """返回 /产品信息 下所有文件夹名 → path 的映射。"""
    items = fl.get_file_list(TARGET, limit=5000, additional="")
    if not items.get("success"):
        return {}
    return {
        f["name"]: f["path"]
        for f in items["data"]["files"]
        if f["isdir"]
    }


# ── Commands ───────────────────────────────────────────────

def cmd_status(mid: str | None = None):
    """查看叶子组文件夹当前状态。"""
    fl = _get_nas()
    dirs = _list_root_dirs(fl)

    groups = {mid: LEAF_GROUPS[mid]} if mid else LEAF_GROUPS
    for lg_id in groups:
        lg = groups[lg_id]
        folder_name = f"{lg_id}_{lg['name']}"
        leaf_exists = folder_name in dirs

        # Check children
        children_status = []
        for child_mid in lg["children"]:
            # Find child folder by prefix
            matches = [n for n in dirs if n.startswith(f"{child_mid}_")]
            if matches:
                child_path = dirs[matches[0]]
                children_status.append(f"{child_mid} @ {child_path}")
            else:
                children_status.append(f"{child_mid} 不存在")

        status = "存在" if leaf_exists else "缺失"
        print(f"{lg_id} ({lg['name']}): {status}")
        if leaf_exists:
            # Check sub-folders
            leaf_path = dirs[folder_name]
            sub_items = fl.get_file_list(leaf_path, limit=50, additional="")
            if sub_items.get("success"):
                sub_names = [f["name"] for f in sub_items["data"]["files"] if f["isdir"]]
                missing_subs = [s for s in SUBS if s not in sub_names]
                child_here = [f["name"] for f in sub_items["data"]["files"] if f["isdir"] and f["name"] not in SUBS]
                print(f"  子文件夹: {'全' if not missing_subs else '缺' + str(missing_subs)}")
                if child_here:
                    print(f"  已移入子节点: {child_here}")
        for cs in children_status:
            print(f"  {cs}")
        print()


def cmd_create(mid: str):
    """创建叶子组文件夹 + 4 个标准子文件夹。"""
    fl = _get_nas()
    lg = LEAF_GROUPS[mid]
    leaf_name = f"{mid}_{lg['name']}"
    leaf_path = f"{TARGET}/{leaf_name}"

    # Check if already exists
    dirs = _list_root_dirs(fl)
    if leaf_name in dirs:
        print(f"[skip] {leaf_path} 已存在")
    else:
        r = fl.create_folder(TARGET, leaf_name, force_parent=True)
        if r.get("success"):
            print(f"[OK] 创建 {leaf_path}")
        else:
            print(f"[FAIL] 创建 {leaf_path}: {r}")
            return

    # Sub-folders
    for sub in SUBS:
        sub_path = f"{leaf_path}/{sub}"
        r = fl.create_folder(leaf_path, sub, force_parent=True)
        if r.get("success"):
            print(f"[OK] 创建 {sub_path}")
        else:
            code = r.get("error", {}).get("code", -1)
            if code == 408:  # already exists
                print(f"[skip] {sub_path} 已存在")
            else:
                print(f"[FAIL] 创建 {sub_path}: {r}")


def cmd_move(mid: str):
    """将 KS 子文件夹从根移到叶子组下。"""
    fl = _get_nas()
    lg = LEAF_GROUPS[mid]
    leaf_name = f"{mid}_{lg['name']}"
    leaf_path = f"{TARGET}/{leaf_name}"

    dirs = _list_root_dirs(fl)
    if leaf_name not in dirs:
        print(f"[error] {leaf_path} 不存在，请先 create")
        return

    for child_mid in lg["children"]:
        matches = [n for n in dirs if n.startswith(f"{child_mid}_")]
        if not matches:
            print(f"[skip] {child_mid}_* 在根目录不存在，可能已移动")
            continue

        child_name = matches[0]
        src = dirs[child_name]
        dst_path = f"{leaf_path}/{child_name}"

        # Check if already at destination
        sub_items = fl.get_file_list(leaf_path, limit=50, additional="")
        existing = set()
        if sub_items.get("success"):
            existing = {f["name"] for f in sub_items["data"]["files"]}

        if child_name in existing:
            print(f"[skip] {child_name} 已在目标位置")
            continue

        r = fl.start_copy_move(
            path=[src], dest_folder_path=leaf_path,
            overwrite=False, remove_src=True,
        )
        if isinstance(r, str) and "FileStation" in r:
            print(f"[OK] 移动 {src} -> {dst_path}")
        else:
            print(f"[FAIL] 移动 {src}: {r}")


def cmd_verify(mid: str):
    """验证叶子组目录结构完整性。"""
    fl = _get_nas()
    lg = LEAF_GROUPS[mid]
    leaf_name = f"{mid}_{lg['name']}"
    leaf_path = f"{TARGET}/{leaf_name}"

    dirs = _list_root_dirs(fl)
    if leaf_name not in dirs:
        print(f"[FAIL] {leaf_path} 不存在")
        return

    items = fl.get_file_list(leaf_path, limit=50, additional="size,time")
    if not items.get("success"):
        print(f"[FAIL] 无法读取 {leaf_path}")
        return

    sub_names = {f["name"]: f["isdir"] for f in items["data"]["files"]}
    print(f"{leaf_path}/")
    for sub in SUBS:
        mark = "+" if sub in sub_names else "✗ 缺失"
        print(f"  [{mark}] {sub}/")
    for child_mid in lg["children"]:
        matches = [n for n in sub_names if n.startswith(f"{child_mid}_")]
        if matches:
            print(f"  [{'+'}] {matches[0]}/")
        else:
            print(f"  [✗ 缺失] {child_mid}_*/")


def cmd_setup(mid: str):
    """create + move 一步到位。"""
    print(f"=== {mid} {LEAF_GROUPS[mid]['name']} ===")
    cmd_create(mid)
    cmd_move(mid)
    print()
    cmd_verify(mid)


# ── CLI ────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("用法: leaf_group_ops.py <command> [leaf_group_id]")
        print("命令: status | create | move | verify | setup")
        print("       status          查看全部12个状态")
        print("       setup LGKS0220  创建+移动 指定叶子组")
        print("       setup --all      全部12个")
        sys.exit(1)

    cmd = args[0]

    if cmd == "status":
        cmd_status(None)

    elif cmd == "setup" and "--all" in args:
        for lg_id in LEAF_GROUPS:
            cmd_setup(lg_id)
        print("\n=== 全部完成，最终状态 ===")
        cmd_status(None)

    elif cmd in ("create", "move", "verify", "setup", "status"):
        mid = args[1] if len(args) > 1 else None
        if not mid and cmd != "status":
            print(f"请指定 leaf_group_id (如 LGKS0220)")
            sys.exit(1)
        if mid and mid not in LEAF_GROUPS:
            print(f"未知叶子组: {mid}，可选: {', '.join(LEAF_GROUPS)}")
            sys.exit(1)
        {"create": cmd_create, "move": cmd_move, "verify": cmd_verify, "setup": cmd_setup, "status": lambda m: cmd_status(m)}[cmd](mid)

    else:
        print(f"未知命令: {cmd}")
