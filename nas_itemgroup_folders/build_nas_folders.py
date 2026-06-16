# -*- coding: utf-8 -*-
"""NAS-ERPNext 文件夹对账工具。

比对 ERPNext "产品" 子树叶子节点与 NAS 文件夹，
自动创建/重命名/移动空文件夹，有内容时阻塞报告。

使用:
  uv run python build_nas_folders.py              # 测试模式
  uv run python build_nas_folders.py --full       # 全量
  uv run python build_nas_folders.py --dry-run    # 仅对比
  uv run python build_nas_folders.py --layout tree   # 树状布局
  uv run python build_nas_folders.py --layout flat   # 扁平布局
"""

from __future__ import annotations

import json
import os
import sys
import time

# Force UTF-8 stdout on Windows (GBK terminal workaround)
sys.stdout.reconfigure(encoding="utf-8")
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from synology_api.filestation import FileStation

_DIR = Path(__file__).resolve().parent
_DIR_OUT = _DIR / "out"
_DIR_OUT.mkdir(parents=True, exist_ok=True)
_NAS_API = _DIR.parent / "NAS_API"
sys.path.insert(0, str(_DIR.parent))

from NAS_API.synology import _load_dotenv, _parse_nas_url  # noqa: E402
from nas_itemgroup_folders.reconcile import (  # noqa: E402
    Action, ActionType, Orphan,
    scan_erpnext, scan_nas, compare,
    expected_path, expected_folder_name, detect_orphans,
)

# ── .env ────────────────────────────────────────────────

_load_dotenv([
    _NAS_API / ".env",
    _DIR / ".env",
])


# ── ERPNext Client ──────────────────────────────────────

class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


def _make_erpnext_fetcher():
    """Returns a callable fetch_all_item_groups() for scan_erpnext()."""
    s = requests.Session()
    s.headers["Authorization"] = (
        f"token {os.getenv('ERP_API_KEY')}:{os.getenv('ERP_API_SECRET')}"
    )
    s.mount("https://", _NoExpectAdapter())
    s.mount("http://", _NoExpectAdapter())
    base_url = os.getenv("ERP_URL", "https://erpnext.vilavi.cn").rstrip("/")

    def fetch_all_item_groups() -> list[dict]:
        url = f"{base_url}/api/resource/Item Group"
        fields = json.dumps([
            "name", "parent_item_group", "is_group", "custom_model_id", "is_leaf_group",
        ])
        for attempt in range(3):
            try:
                resp = s.get(url, params={
                    "fields": fields, "limit_page_length": "0"
                }, timeout=(30, 60))
                resp.raise_for_status()
                return resp.json().get("data", [])
            except requests.RequestException as e:
                if attempt == 2:
                    raise
                time.sleep(3)
        return []

    return fetch_all_item_groups


# ── NAS Client ──────────────────────────────────────────

class _NasOps:
    """Thin wrapper bundling NAS read/write operations."""

    def __init__(self):
        base_url = os.getenv("NAS_URL", "").rstrip("/")
        username = os.getenv("NAS_USERNAME", "")
        password = os.getenv("NAS_PASSWORD", "")
        host, port, secure = _parse_nas_url(base_url)
        self._fl = FileStation(
            ip_address=host, port=port,
            username=username, password=password,
            secure=secure, cert_verify=False,
            dsm_version=7, debug=False,
        )

    def list_folder(self, path: str, limit: int = 5000) -> list[dict]:
        try:
            resp = self._fl.get_file_list(
                folder_path=path, limit=limit,
                additional="size,time",
            )
            if resp.get("success"):
                return [
                    {
                        "name": f.get("name"),
                        "path": f.get("path"),
                        "is_dir": f.get("isdir", False),
                        "size": f.get("additional", {}).get("size", 0),
                    }
                    for f in resp["data"]["files"]
                ]
        except Exception as e:
            print(f"  [nas] list error on {path}: {e}")
        return []

    def create_folder(self, folder_path: str, name: str) -> bool:
        try:
            resp = self._fl.create_folder(folder_path, name, force_parent=True)
            return resp.get("success", False)
        except Exception as e:
            print(f"  [nas] create error {folder_path}/{name}: {e}")
            return False

    def rename_folder(self, path: str, new_name: str) -> bool:
        try:
            resp = self._fl.rename_folder(path, new_name)
            return resp.get("success", False)
        except Exception as e:
            print(f"  [nas] rename error {path} -> {new_name}: {e}")
            return False

    def move_folder(self, src_path: str, dst_path: str) -> bool:
        """CopyMove src to dst. Returns True if task submitted successfully.
        The actual move executes asynchronously on NAS."""
        try:
            dst_parent = "/".join(dst_path.split("/")[:-1])
            resp = self._fl.start_copy_move(
                path=[src_path],
                dest_folder_path=dst_parent,
                overwrite=False,
                remove_src=True,
            )
            # start_copy_move returns a string with task ID on success
            if isinstance(resp, str) and "FileStation_" in resp:
                return True
            # Some versions return a dict
            if isinstance(resp, dict) and resp.get("success"):
                return True
            print(f"    [nas] unexpected move response: {resp}")
            return False
        except Exception as e:
            print(f"  [nas] move error {src_path} -> {dst_path}: {e}")
            return False


# ── Report ──────────────────────────────────────────────

def _fmt_size(size_bytes: int) -> str:
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.1f} GB"
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    if size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.1f} KB"
    return f"{size_bytes} B"


def _print_report(
    actions: list[Action], layout: str, full: bool, dry_run: bool,
    executed: int, failed: int, sub_created: int,
) -> dict:
    by_type: dict[str, list[Action]] = {}
    for a in actions:
        by_type.setdefault(a.type.value, []).append(a)

    mode = "FULL" if full else "TEST"
    print(f"\n=== NAS-ERPNext 对账报告 ===  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"模式: {mode}  布局: {layout}")

    print("\n差异摘要:")
    for t in [ActionType.MATCH, ActionType.CREATE, ActionType.RENAME,
              ActionType.MOVE, ActionType.MOVE_APPROVAL,
              ActionType.DELETE_EMPTY, ActionType.BLOCKED, ActionType.IGNORE]:
        items = by_type.get(t.value, [])
        if items:
            print(f"  {t.value:20s} {len(items):4d}")

    safe_actions = [a for a in actions if a.safe and a.type not in (ActionType.MATCH, ActionType.IGNORE)]
    if safe_actions:
        label = "DRY-RUN 预览" if dry_run else "已执行"
        print(f"\n安全操作（{label}）:")
        for a in safe_actions[:30]:
            icon = "  " if dry_run else "+"
            print(f"  {icon} [{a.type.value}] {a.model_id}: {a.reason}")
        if len(safe_actions) > 30:
            print(f"  ... 共 {len(safe_actions)} 项")

    blocked = [a for a in actions if not a.safe and a.type not in (ActionType.IGNORE,)]
    if blocked:
        print(f"\n!!! 阻塞项（有内容无法自动操作）:")
        for a in blocked[:20]:
            print(f"  [{a.type.value}] {a.model_id}: {a.reason}")
            if a.old_path:
                print(f"         旧: {a.old_path}")
            if a.new_path:
                print(f"         新: {a.new_path}")
            if a.content_count:
                print(f"         内容: {a.content_count} 文件, {_fmt_size(a.content_bytes)}")
        if len(blocked) > 20:
            print(f"  ... 共 {len(blocked)} 项")

    ignored = by_type.get(ActionType.IGNORE.value, [])
    if ignored:
        print(f"\nNAS 额外项目（非脚本创建，不碰）:")
        for a in ignored:
            print(f"  {a.nas_name} ({a.content_count} 文件, {_fmt_size(a.content_bytes)})")

    print(f"\n{'=' * 60}")
    print(f"执行: {executed} 成功, {failed} 失败  子文件夹补建: {sub_created}")
    if dry_run:
        print("DRY-RUN — 未实际操作")

    stats = {
        "total_actions": len(actions),
        "match": len(by_type.get(ActionType.MATCH.value, [])),
        "create": len(by_type.get(ActionType.CREATE.value, [])),
        "rename": len(by_type.get(ActionType.RENAME.value, [])),
        "move": len(by_type.get(ActionType.MOVE.value, [])),
        "move_approval": len(by_type.get(ActionType.MOVE_APPROVAL.value, [])),
        "blocked": len(by_type.get(ActionType.BLOCKED.value, [])),
        "ignore": len(ignored),
        "executed": executed,
        "failed": failed,
        "sub_folder_created": sub_created,
    }
    return stats


# ── Main ─────────────────────────────────────────────────

def main(full: bool = False, dry_run: bool = False, layout: str = "flat") -> None:
    target_folder = os.getenv("NAS_TARGET_FOLDER", "/产品信息")
    ig_root = os.getenv("ITEM_GROUP_ROOT", "产品")
    raw_sub = os.getenv("SUB_FOLDERS", "")
    sub_folders = (
        [s.strip() for s in raw_sub.split(",") if s.strip()]
        if raw_sub else ["调研报告", "设计稿", "图片", "视频"]
    )
    test_ids = {"KS0001", "KS0002"}

    # 1. Fetch ERPNext
    print(">>> 拉取 ERPNext Item Groups ...")
    fetch_all = _make_erpnext_fetcher()
    erp_items = scan_erpnext(fetch_all, ig_root)
    full_count = len(erp_items)
    # Collect valid intermediate group names (from ALL items, before test filter)
    valid_group_names: set[str] = set()
    valid_model_ids: set[str] = set()
    for item in erp_items:
        valid_model_ids.add(item.model_id)
        for a in item.ancestors:
            valid_group_names.add(a)
    if not full:
        erp_items = [i for i in erp_items if i.model_id in test_ids]
        print(f"    全部: {full_count} 叶子 | TEST MODE: {[i.model_id for i in erp_items]}")
    else:
        print(f"    产品子树叶子节点: {len(erp_items)}")

    # 2. Scan NAS
    print(f">>> 扫描 NAS: {target_folder}")
    nas_ops = _NasOps()
    nas_folders = scan_nas(nas_ops.list_folder, target_folder, sub_folders, valid_model_ids)
    script_count = sum(1 for f in nas_folders if f.is_script_created)
    manual_count = sum(1 for f in nas_folders if not f.is_script_created)
    print(f"    脚本创建: {script_count}  手动/未知: {manual_count}")

    # 3. Compare
    print(">>> 对账比对 ...")
    actions = compare(erp_items, nas_folders, target_folder, layout, sub_folders)
    print(f"    差异项: {len(actions)}")

    # 4. Execute safe actions
    executed, failed = 0, 0
    _created_parents: set[str] = set()
    safe = [a for a in actions if a.safe and a.type not in (ActionType.MATCH, ActionType.IGNORE)]

    # 排序: CREATE 优先 (叶子组 → KS), 再 MOVE → RENAME → DELETE
    _type_order = {ActionType.CREATE: 0, ActionType.MOVE: 1, ActionType.RENAME: 2, ActionType.DELETE_EMPTY: 3}
    safe.sort(key=lambda a: (
        _type_order.get(a.type, 99),
        0 if a.model_id.startswith("LGKS") else 1,  # 叶子组在同类操作中优先
    ))

    if not dry_run and safe:
        print(f"\n>>> 执行安全操作 ({len(safe)} 项) ...")
        for a in safe:
            try:
                if a.type == ActionType.CREATE:
                    parent = "/".join(a.new_path.split("/")[:-1])
                    name = a.new_path.split("/")[-1]
                    if not nas_ops.create_folder(parent, name):
                        raise Exception(f"create {parent}/{name} failed")
                    # Create sub-folders
                    for sub in sub_folders:
                        nas_ops.create_folder(a.new_path, sub)
                    print(f"  OK CREATE {a.new_path}")

                elif a.type == ActionType.RENAME:
                    if not nas_ops.rename_folder(a.old_path, a.new_path.split("/")[-1]):
                        raise Exception(f"rename {a.old_path} failed")
                    print(f"  OK RENAME {a.old_path} -> {a.new_path}")

                elif a.type == ActionType.MOVE:
                    # Ensure intermediate parent folders exist (skip target_folder itself)
                    dst_parent = "/".join(a.new_path.split("/")[:-1])
                    # Build paths from root, skipping parts that are already under target_folder
                    target_parts = target_folder.rstrip("/").split("/")
                    dst_parts = dst_parent.split("/")
                    for depth in range(len(target_parts), len(dst_parts)):
                        p = "/".join(dst_parts[:depth + 1])
                        if p and p not in _created_parents and p != target_folder:
                            nas_ops.create_folder(
                                "/".join(dst_parts[:depth]),
                                dst_parts[depth],
                            )
                            _created_parents.add(p)
                    if not nas_ops.move_folder(a.old_path, a.new_path):
                        raise Exception(f"move {a.old_path} failed")
                    print(f"  OK MOVE   {a.old_path} -> {a.new_path}")

                elif a.type == ActionType.DELETE_EMPTY:
                    print(f"  SKIP DELETE_EMPTY (需手动): {a.old_path}")

                executed += 1
            except Exception as e:
                failed += 1
                print(f"  !! FAIL [{a.type.value}] {a.model_id}: {e}")

    # 5. Sub-folder check for MATCH items
    sub_created = 0
    if not dry_run:
        match_items = [a for a in actions if a.type == ActionType.MATCH]
        if match_items:
            print(f"\n>>> 检查子文件夹完整性 ({len(match_items)} 项) ...")
            for a in match_items:
                nas_item = next(
                    (f for f in nas_folders if f.model_id == a.model_id), None
                )
                if nas_item is None:
                    continue
                existing_subs = set(nas_item.sub_folders)
                for sub in sub_folders:
                    if sub not in existing_subs:
                        if nas_ops.create_folder(nas_item.path, sub):
                            sub_created += 1
            if sub_created:
                print(f"    补建子文件夹: {sub_created}")

    # 6. Orphan detection
    orphan_cleaned = 0
    orphans = detect_orphans(
        nas_ops.list_folder, target_folder,
        valid_group_names, sub_folders, layout, valid_model_ids,
    )
    if orphans:
        print(f"\n>>> 孤儿文件夹检测 ({len(orphans)} 项) ...")
        for o in orphans:
            if o.content_count == 0 and not dry_run:
                try:
                    nas_ops._fl.delete_blocking_function(o.path)
                    print(f"  清理空孤儿: {o.path}")
                    orphan_cleaned += 1
                except Exception as e:
                    print(f"  清理失败: {o.path}: {e}")
            elif o.content_count == 0 and dry_run:
                print(f"  可清理空文件夹: {o.path}")
            else:
                print(f"  ⚠️  有内容，禁止清理: {o.path} ({o.content_count} 文件)")
    else:
        print("\n>>> 孤儿检测: 无")

    # 7. Report
    stats = _print_report(actions, layout, full, dry_run, executed, failed, sub_created)

    # Save JSON
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = _DIR_OUT / f"report_{ts}.json"
    report_path.write_text(json.dumps({
        "timestamp": ts,
        "target_folder": target_folder,
        "item_group_root": ig_root,
        "layout": layout,
        "full_mode": full,
        "dry_run": dry_run,
        "stats": stats,
        "blocked": [
            {"type": a.type.value, "model_id": a.model_id, "reason": a.reason,
             "old_path": a.old_path, "new_path": a.new_path,
             "content_count": a.content_count, "content_bytes": a.content_bytes}
            for a in actions if not a.safe and a.type not in (ActionType.IGNORE,)
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {report_path}")

    # Snapshot
    lg_folder_by_model: dict[str, str] = {}
    for i in erp_items:
        if i.is_leaf_group:
            lg_folder_by_model[i.model_id] = expected_folder_name(i.model_id, i.name)

    snapshot_path = _DIR_OUT / "last_snapshot.json"
    snapshot_path.write_text(json.dumps({
        "run_at": datetime.now().isoformat(),
        "layout": layout,
        "erpnext": {
            "root": ig_root,
            "total_leaves": full_count,
            "items": [
                {"name": i.name, "model_id": i.model_id,
                 "parent": i.parent, "ancestors": i.ancestors,
                 "is_leaf_group": i.is_leaf_group,
                 "expected_path": expected_path(
                     i.model_id, i.name, target_folder, i.ancestors, layout,
                     leaf_group_folder_name=lg_folder_by_model.get(i.leaf_group_model_id) if i.leaf_group_model_id else None,
                 )}
                for i in erp_items
            ],
        },
        "nas": {
            "target": target_folder,
            "script_created": [
                {"name": f.name, "path": f.path,
                 "content_count": f.content_count,
                 "content_bytes": f.content_bytes,
                 "sub_folders": f.sub_folders,
                 "extra_folders": f.extra_folders}
                for f in nas_folders if f.is_script_created
            ],
            "manual_or_unknown": [
                {"name": f.name, "path": f.path,
                 "content_count": f.content_count,
                 "content_bytes": f.content_bytes}
                for f in nas_folders if not f.is_script_created
            ],
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Snapshot: {snapshot_path}")


# ── CLI ─────────────────────────────────────────────────

if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    full = "--full" in sys.argv
    layout = "flat"
    for arg in sys.argv:
        if arg.startswith("--layout="):
            layout = arg.split("=", 1)[1]
    mode = "DRY-RUN" if dry else ("FULL" if full else "TEST")
    print(f"=== NAS-ERPNext Reconciliation ===")
    print(f"mode={mode}  layout={layout}")
    main(full=full, dry_run=dry, layout=layout)
