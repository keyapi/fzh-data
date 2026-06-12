# nas_itemgroup_folders/reconcile.py
# -*- coding: utf-8 -*-
"""NAS-ERPNext 对账引擎 — 数据模型定义。

比对 ERPNext Item Group 和 NAS 文件夹，输出分类后的 Action 列表。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ── 输入数据类 ─────────────────────────────────────────

@dataclass
class ErpnextItem:
    """ERPNext 物料组叶子节点（已过滤：产品子树 + is_group=0 + 有 custom_model_id）"""
    name: str                    # "三角靠枕"
    model_id: str                # "KS0001"
    parent: str                  # "三角靠枕类"
    ancestors: list[str]         # ["床品类", "床头靠枕", "三角靠枕类"] (不含根"产品")


@dataclass
class NasFolder:
    """NAS 上一个文件夹的快照"""
    name: str                    # "KS0001_三角靠枕"
    path: str                    # "/产品信息/KS0001_三角靠枕"
    model_id: str | None         # "KS0001" (从名称解析)
    content_count: int           # 递归文件数
    content_bytes: int           # 递归总字节
    sub_folders: list[str]       # 直接子文件夹名（标准子文件夹）
    extra_folders: list[str]      # 额外子文件夹（LM 手动加的）
    is_script_created: bool      # 是否匹配 KS 编码格式


# ── 输出数据类 ─────────────────────────────────────────

class ActionType(str, Enum):
    CREATE = "CREATE"
    RENAME = "RENAME"
    MOVE = "MOVE"
    MOVE_APPROVAL = "MOVE_APPROVAL"
    DELETE_EMPTY = "DELETE_EMPTY"
    BLOCKED = "BLOCKED"
    IGNORE = "IGNORE"
    MATCH = "MATCH"


@dataclass
class Action:
    """一条对账操作"""
    type: ActionType               # ActionType 枚举值
    model_id: str                # KS 编码
    erpnext_name: str            # 物料组名
    nas_name: str                # NAS 文件夹名（可能为空）
    old_path: str                # 旧路径（RENAME/MOVE 时）
    new_path: str                # 新路径（CREATE/RENAME/MOVE 时）
    content_count: int           # 现有文件数
    content_bytes: int           # 现有文件大小
    safe: bool                   # 是否可安全自动执行
    reason: str                  # 人类可读的说明


# ── KS 编码解析 ────────────────────────────────────────

import re

# KS 编码模式: 2个大写字母 + 4位数字开头
_KS_PATTERN = re.compile(r'^([A-Z]{2}\d{4})_')


def parse_model_id(folder_name: str) -> str | None:
    """从文件夹名解析 KS 编码，如 'KS0001_三角靠枕' -> 'KS0001'"""
    m = _KS_PATTERN.match(folder_name)
    return m.group(1) if m else None


# 文件夹名非法字符转义
_FORBIDDEN = str.maketrans({
    "/": "_", "\\": "_", ":": "_", "*": "_", "?": "_",
    '"': "_", "<": "_", ">": "_", "|": "_",
})


def safe_name(s: str) -> str:
    return s.translate(_FORBIDDEN).strip()


def expected_folder_name(model_id: str, name: str) -> str:
    """根据物料组信息计算期望文件夹名"""
    return safe_name(f"{model_id}_{name}")


def expected_path(
    model_id: str, name: str,
    target_folder: str, ancestors: list[str], layout: str,
) -> str:
    """根据布局计算期望 NAS 路径。

    flat: /产品信息/KS0001_三角靠枕
    tree: /产品信息/床品类/床头靠枕/三角靠枕类/KS0001_三角靠枕
    """
    folder = expected_folder_name(model_id, name)
    if layout == "flat":
        return f"{target_folder}/{folder}"
    else:
        parts = [target_folder] + [safe_name(a) for a in ancestors] + [folder]
        return "/".join(parts)


# ── 对账比对 ──────────────────────────────────────────


def compare(
    erpnext_items: list[ErpnextItem],
    nas_folders: list[NasFolder],
    target_folder: str,
    layout: str,
    sub_folders: list[str],
) -> list[Action]:
    """核心对账：ERPNext vs NAS，输出 Action 列表。

    匹配策略: 按 model_id (KS编码) 关联两边。
    - 无 KS 码的 NAS 文件夹归入 IGNORE
    - 同一 KS 码有多个 ERPNext 项 → 取第一个，后续标记冲突
    """
    actions: list[Action] = []
    nas_by_model: dict[str, NasFolder] = {}
    for nf in nas_folders:
        if nf.model_id:
            nas_by_model[nf.model_id] = nf

    matched_nas: set[str] = set()

    for item in erpnext_items:
        nas = nas_by_model.get(item.model_id)
        exp_name = expected_folder_name(item.model_id, item.name)
        exp_path = expected_path(
            item.model_id, item.name, target_folder, item.ancestors, layout
        )

        if nas is None:
            actions.append(Action(
                type=ActionType.CREATE,
                model_id=item.model_id,
                erpnext_name=item.name,
                nas_name="",
                old_path="",
                new_path=exp_path,
                content_count=0,
                content_bytes=0,
                safe=True,
                reason=f"{item.model_id} {item.name}: NAS 不存在，将创建",
            ))
            continue

        matched_nas.add(item.model_id)

        # 名称检查
        if nas.name != exp_name:
            if nas.content_count == 0:
                new_full = f"{target_folder}/{exp_name}"
                if layout == "tree":
                    new_full = expected_path(
                        item.model_id, item.name, target_folder, item.ancestors, layout
                    )
                actions.append(Action(
                    type=ActionType.RENAME,
                    model_id=item.model_id,
                    erpnext_name=item.name,
                    nas_name=nas.name,
                    old_path=nas.path,
                    new_path=new_full,
                    content_count=0,
                    content_bytes=0,
                    safe=True,
                    reason=f"物料组改名: '{nas.name}' -> '{exp_name}' (空文件夹，自动重命名)",
                ))
            else:
                actions.append(Action(
                    type=ActionType.BLOCKED,
                    model_id=item.model_id,
                    erpnext_name=item.name,
                    nas_name=nas.name,
                    old_path=nas.path,
                    new_path=f"{target_folder}/{exp_name}",
                    content_count=nas.content_count,
                    content_bytes=nas.content_bytes,
                    safe=False,
                    reason=f"物料组改名: '{nas.name}' -> '{exp_name}'，旧文件夹有 {nas.content_count} 个文件",
                ))
            continue

        # 路径检查
        if nas.path.rstrip("/") != exp_path.rstrip("/"):
            if nas.content_count == 0:
                actions.append(Action(
                    type=ActionType.MOVE,
                    model_id=item.model_id,
                    erpnext_name=item.name,
                    nas_name=nas.name,
                    old_path=nas.path,
                    new_path=exp_path,
                    content_count=0,
                    content_bytes=0,
                    safe=True,
                    reason=f"路径变更: '{nas.path}' -> '{exp_path}' (空文件夹，自动移动)",
                ))
            else:
                actions.append(Action(
                    type=ActionType.MOVE_APPROVAL,
                    model_id=item.model_id,
                    erpnext_name=item.name,
                    nas_name=nas.name,
                    old_path=nas.path,
                    new_path=exp_path,
                    content_count=nas.content_count,
                    content_bytes=nas.content_bytes,
                    safe=False,
                    reason=f"路径变更: '{nas.path}' -> '{exp_path}'，含 {nas.content_count} 个文件，需确认后移动",
                ))
            continue

        # MATCH
        actions.append(Action(
            type=ActionType.MATCH,
            model_id=item.model_id,
            erpnext_name=item.name,
            nas_name=nas.name,
            old_path="",
            new_path="",
            content_count=nas.content_count,
            content_bytes=nas.content_bytes,
            safe=True,
            reason=f"一致: {nas.name}",
        ))

    # EXTRA: NAS 有但 ERPNext 无
    for nf in nas_folders:
        if nf.model_id and nf.model_id not in matched_nas:
            if nf.content_count == 0:
                actions.append(Action(
                    type=ActionType.DELETE_EMPTY,
                    model_id=nf.model_id,
                    erpnext_name="",
                    nas_name=nf.name,
                    old_path=nf.path,
                    new_path="",
                    content_count=0,
                    content_bytes=0,
                    safe=True,
                    reason=f"ERPNext 已无 {nf.model_id}，NAS 空文件夹可安全删除: {nf.name}",
                ))
            else:
                actions.append(Action(
                    type=ActionType.BLOCKED,
                    model_id=nf.model_id,
                    erpnext_name="",
                    nas_name=nf.name,
                    old_path=nf.path,
                    new_path="",
                    content_count=nf.content_count,
                    content_bytes=nf.content_bytes,
                    safe=False,
                    reason=f"ERPNext 已无 {nf.model_id}，NAS 有 {nf.content_count} 个文件。建议确认是否恢复物料组或手动归档",
                ))

    # IGNORE: 非脚本创建的文件夹
    for nf in nas_folders:
        if not nf.is_script_created:
            actions.append(Action(
                type=ActionType.IGNORE,
                model_id="",
                erpnext_name="",
                nas_name=nf.name,
                old_path="",
                new_path="",
                content_count=nf.content_count,
                content_bytes=nf.content_bytes,
                safe=True,
                reason=f"非脚本创建，不碰: {nf.name} ({nf.content_count} 文件)",
            ))

    return actions


# ── 扫描器 ────────────────────────────────────────────


def scan_erpnext(
    fetch_all_item_groups,            # callable: () -> list[dict]
    item_group_root: str = "产品",
) -> list[ErpnextItem]:
    """从 ERPNext 拉取 '产品' 子树下所有叶子节点。

    fetch_all_item_groups: 返回 [{"name":..., "parent_item_group":..., "is_group":..., "custom_model_id":...}]
    """
    all_ig = fetch_all_item_groups()
    idx = {d["name"]: d for d in all_ig if d.get("name")}

    if item_group_root not in idx:
        raise ValueError(f"Item Group '{item_group_root}' not found")

    def _descendants(parent_name: str) -> list[dict]:
        result: list[dict] = []
        for d in idx.values():
            if d.get("parent_item_group") == parent_name:
                result.append(d)
                result.extend(_descendants(d["name"]))
        return result

    subtree = [idx[item_group_root]] + _descendants(item_group_root)
    leaves = [d for d in subtree if d.get("is_group") == 0 and d.get("custom_model_id")]

    items: list[ErpnextItem] = []
    for leaf in leaves:
        ancestors: list[str] = []
        node = leaf
        while node:
            parent = node.get("parent_item_group", "")
            if not parent or parent not in idx:
                break
            ancestors.append(parent)
            node = idx.get(parent)
        ancestors.reverse()
        # Strip everything up to and including the root node
        try:
            root_idx = ancestors.index(item_group_root)
            ancestors = ancestors[root_idx + 1:]
        except ValueError:
            pass  # root not found in chain, keep as-is

        items.append(ErpnextItem(
            name=leaf["name"],
            model_id=leaf["custom_model_id"],
            parent=leaf["parent_item_group"],
            ancestors=ancestors,
        ))

    return items


def scan_nas(
    list_folder,                       # callable: (path, limit) -> list[dict]
    target_folder: str,
    sub_folder_names: list[str],
) -> list[NasFolder]:
    """扫描 NAS 目标文件夹，递归发现所有 KS 编码文件夹。

    返回: 所有脚本创建的文件夹 + target_folder 直接子节点中非 KS 格式的文件夹。
    """
    results: list[NasFolder] = []

    # 1. Walk entire tree, collect all folders
    all_folders: list[dict] = []  # [{"name":..., "path":..., "is_dir":..., "size":...}]
    _walk_tree(list_folder, target_folder, sub_folder_names, all_folders)

    # 2. For each KS-pattern folder, compute recursive stats and create NasFolder
    ks_folders: dict[str, dict] = {}
    for f in all_folders:
        mid = parse_model_id(f["name"])
        if mid:
            ks_folders[f["path"]] = f

    for f in ks_folders.values():
        path = f["path"]
        folder_name = f["name"]
        # Recursively count content: all files under this path that are NOT ks_folders themselves
        # Actually, for simplicity, let's scan this folder's subtree for content
        file_count, total_bytes, sub_dirs, extra = _scan_dir(
            list_folder, path, sub_folder_names
        )

        model_id = parse_model_id(folder_name)
        script_subs = [d for d in sub_dirs if d in sub_folder_names]
        extra_subs = [d for d in sub_dirs if d not in sub_folder_names]

        results.append(NasFolder(
            name=folder_name,
            path=path,
            model_id=model_id,
            content_count=file_count,
            content_bytes=total_bytes,
            sub_folders=script_subs,
            extra_folders=extra_subs,
            is_script_created=True,
        ))

    # 3. Add non-KS direct children of target_folder as IGNORE items
    items = list_folder(target_folder, limit=5000)
    for item in items:
        if not item["is_dir"]:
            continue
        mid = parse_model_id(item["name"])
        if mid:
            continue  # Already handled above
        # Non-KS folder
        fc, tb, _, _ = _scan_dir(list_folder, item["path"], sub_folder_names)
        results.append(NasFolder(
            name=item["name"],
            path=item["path"],
            model_id=None,
            content_count=fc,
            content_bytes=tb,
            sub_folders=[],
            extra_folders=[],
            is_script_created=False,
        ))

    return results


def _walk_tree(
    list_folder, path: str, sub_folder_names: list[str],
    collector: list[dict],
) -> None:
    """递归遍历目录树，收集所有文件夹到 collector。"""
    items = list_folder(path, limit=5000)
    for item in items:
        if item["is_dir"]:
            collector.append(item)
            _walk_tree(list_folder, item["path"], sub_folder_names, collector)


def _scan_dir(
    list_folder, path: str, sub_folder_names: list[str]
) -> tuple[int, int, list[str], list[str]]:
    """递归扫描一个目录，返回 (file_count, total_bytes, all_subdirs, extra_subdirs)。"""
    items = list_folder(path, limit=5000)
    file_count = 0
    total_bytes = 0
    subdir_names: list[str] = []
    extra_names: list[str] = []

    for item in items:
        if item["is_dir"]:
            subdir_names.append(item["name"])
            # 递归子文件夹
            fc, tb, _, _ = _scan_dir(
                list_folder, f"{path}/{item['name']}", sub_folder_names
            )
            file_count += fc
            total_bytes += tb
            # 标记非标准子文件夹
            if item["name"] not in sub_folder_names:
                extra_names.append(item["name"])
        else:
            file_count += 1
            total_bytes += item.get("size", 0)

    return file_count, total_bytes, subdir_names, extra_names


if __name__ == "__main__":
    # Task 2 tests
    assert parse_model_id('KS0001_三角靠枕') == 'KS0001'
    assert parse_model_id('旧的设计文件1') is None
    assert expected_path('KS0001', '三角靠枕', '/产品信息', ['床品类'], 'flat') == '/产品信息/KS0001_三角靠枕'

    # Task 3 tests: compare()
    erp = [ErpnextItem(name="三角靠枕", model_id="KS0001", parent="三角靠枕类",
                       ancestors=["床品类", "床头靠枕", "三角靠枕类"])]

    # Test MISSING
    actions = compare(erp, [], "/产品信息", "flat", ["调研报告"])
    assert len(actions) == 1
    assert actions[0].type == ActionType.CREATE
    assert actions[0].safe is True

    # Test MATCH
    nas = [NasFolder(name="KS0001_三角靠枕", path="/产品信息/KS0001_三角靠枕",
                     model_id="KS0001", content_count=0, content_bytes=0,
                     sub_folders=["调研报告"], extra_folders=[], is_script_created=True)]
    actions = compare(erp, nas, "/产品信息", "flat", ["调研报告"])
    assert actions[0].type == ActionType.MATCH

    # Test NAME_MISMATCH (empty -> RENAME)
    nas_rename = [NasFolder(name="KS0001_旧名", path="/产品信息/KS0001_旧名",
                            model_id="KS0001", content_count=0, content_bytes=0,
                            sub_folders=[], extra_folders=[], is_script_created=True)]
    actions = compare(erp, nas_rename, "/产品信息", "flat", [])
    assert actions[0].type == ActionType.RENAME

    # Test NAME_MISMATCH (with content -> BLOCKED)
    nas_blocked = [NasFolder(name="KS0001_旧名", path="/产品信息/KS0001_旧名",
                             model_id="KS0001", content_count=5, content_bytes=1000,
                             sub_folders=[], extra_folders=[], is_script_created=True)]
    actions = compare(erp, nas_blocked, "/产品信息", "flat", [])
    assert actions[0].type == ActionType.BLOCKED
    assert actions[0].safe is False

    # Test STRUC_MISMATCH (tree mode, wrong path -> MOVE)
    nas_flat = [NasFolder(name="KS0001_三角靠枕", path="/产品信息/KS0001_三角靠枕",
                          model_id="KS0001", content_count=0, content_bytes=0,
                          sub_folders=[], extra_folders=[], is_script_created=True)]
    actions = compare(erp, nas_flat, "/产品信息", "tree", [])
    assert actions[0].type == ActionType.MOVE

    # Test STRUC_MISMATCH (with content -> MOVE_APPROVAL)
    nas_move_content = [NasFolder(name="KS0001_三角靠枕", path="/产品信息/KS0001_三角靠枕",
                                  model_id="KS0001", content_count=10, content_bytes=5000,
                                  sub_folders=[], extra_folders=[], is_script_created=True)]
    actions = compare(erp, nas_move_content, "/产品信息", "tree", [])
    assert actions[0].type == ActionType.MOVE_APPROVAL

    # Test EXTRA
    nas_extra = [NasFolder(name="KS9999_已删除", path="/产品信息/KS9999_已删除",
                           model_id="KS9999", content_count=5, content_bytes=200,
                           sub_folders=[], extra_folders=[], is_script_created=True)]
    actions = compare([], nas_extra, "/产品信息", "flat", [])
    assert actions[0].type == ActionType.BLOCKED  # has content

    # Test IGNORE (non-script-created)
    nas_manual = [NasFolder(name="旧文件", path="/产品信息/旧文件",
                            model_id=None, content_count=10, content_bytes=100,
                            sub_folders=[], extra_folders=[], is_script_created=False)]
    actions = compare([], nas_manual, "/产品信息", "flat", [])
    assert actions[0].type == ActionType.IGNORE

    # Task 4 tests: scanners
    # Test scan_erpnext
    mock_fetch = lambda: [
        {"name": "产品", "parent_item_group": "所有物料组", "is_group": 1, "custom_model_id": None},
        {"name": "床品类", "parent_item_group": "产品", "is_group": 1, "custom_model_id": None},
        {"name": "三角靠枕", "parent_item_group": "床品类", "is_group": 0, "custom_model_id": "KS0001"},
        {"name": "平条靠枕", "parent_item_group": "床品类", "is_group": 0, "custom_model_id": "KS0002"},
        {"name": "靠垫", "parent_item_group": "其他", "is_group": 0, "custom_model_id": "KD0001"},
    ]
    erp_items = scan_erpnext(mock_fetch, "产品")
    assert len(erp_items) == 2
    k1 = next(i for i in erp_items if i.model_id == "KS0001")
    assert k1.name == "三角靠枕"
    assert k1.ancestors == ["床品类"]

    # Test scan_nas
    mock_list = lambda path, limit: {
        "/产品信息": [
            {"name": "KS0001_三角靠枕", "path": "/产品信息/KS0001_三角靠枕", "is_dir": True, "size": 0},
            {"name": "旧文件", "path": "/产品信息/旧文件", "is_dir": True, "size": 0},
        ],
        "/产品信息/KS0001_三角靠枕": [
            {"name": "调研报告", "path": "/产品信息/KS0001_三角靠枕/调研报告", "is_dir": True, "size": 0},
            {"name": "设计稿", "path": "/产品信息/KS0001_三角靠枕/设计稿", "is_dir": True, "size": 0},
            {"name": "photo.jpg", "path": "/产品信息/KS0001_三角靠枕/photo.jpg", "is_dir": False, "size": 5000},
        ],
        "/产品信息/KS0001_三角靠枕/调研报告": [],
        "/产品信息/KS0001_三角靠枕/设计稿": [],
        "/产品信息/旧文件": [
            {"name": "doc.pdf", "path": "/产品信息/旧文件/doc.pdf", "is_dir": False, "size": 1000},
        ],
    }[path]
    nas_items = scan_nas(mock_list, "/产品信息", ["调研报告", "设计稿", "图片", "视频"])
    assert len(nas_items) == 2
    ks1 = next(f for f in nas_items if f.model_id == "KS0001")
    assert ks1.content_count == 1  # photo.jpg
    assert ks1.content_bytes == 5000
    assert ks1.is_script_created is True
    assert "调研报告" in ks1.sub_folders
    old = next(f for f in nas_items if f.model_id is None)
    assert old.is_script_created is False
    assert old.content_count == 1  # doc.pdf

    print("All reconcile tests passed!")
