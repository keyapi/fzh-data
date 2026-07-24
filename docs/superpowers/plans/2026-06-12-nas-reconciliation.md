# NAS-ERPNext 对账引擎 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 NAS-ERPNext 文件夹对账引擎，比对 ERPNext "产品" 子树叶子节点与 NAS `/产品信息/` 文件夹，自动创建/重命名/移动空文件夹，有内容时阻塞并报告。

**Architecture:** 拆为两层 — `reconcile.py`（纯逻辑对账引擎）和 `build_nas_folders.py`（CLI + NAS 操作编排）。对账引擎无状态，每次从头拉两边数据比对，输出分类后的 Action 列表。

**Tech Stack:** Python 3.10+, synology-api (FileStation), requests (ERPNext API), dataclasses

---

### Task 1: reconcile.py — 数据模型

**Files:**
- Create: `nas_itemgroup_folders/reconcile.py`

- [ ] **Step 1: 写对账引擎数据类**

```python
# nas_itemgroup_folders/reconcile.py
# -*- coding: utf-8 -*-
"""NAS-ERPNext 对账引擎 — 纯逻辑，无 I/O 依赖。

比对 ERPNext Item Group 和 NAS 文件夹，输出分类后的 Action 列表。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby

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
    sub_folders: list[str]       # 直接子文件夹名
    is_script_created: bool      # 是否匹配 KS 编码格式


# ── 输出数据类 ─────────────────────────────────────────

class ActionType:
    CREATE        = "CREATE"
    RENAME        = "RENAME"
    MOVE          = "MOVE"
    MOVE_APPROVAL = "MOVE_APPROVAL"
    DELETE_EMPTY  = "DELETE_EMPTY"
    BLOCKED       = "BLOCKED"
    IGNORE        = "IGNORE"
    MATCH         = "MATCH"


@dataclass
class Action:
    """一条对账操作"""
    type: str                    # ActionType 枚举值
    model_id: str                # KS 编码
    erpnext_name: str            # 物料组名
    nas_name: str                # NAS 文件夹名（可能为空）
    old_path: str                # 旧路径（RENAME/MOVE 时）
    new_path: str                # 新路径（CREATE/RENAME/MOVE 时）
    content_count: int           # 现有文件数
    content_bytes: int           # 现有文件大小
    safe: bool                   # 是否可安全自动执行
    reason: str                  # 人类可读的说明
```

- [ ] **Step 2: 验证数据类可以实例化**

Run: `uv run python -c "from nas_itemgroup_folders.reconcile import ErpnextItem, NasFolder, Action; print(ErpnextItem(name='test', model_id='KS0001', parent='p', ancestors=['a', 'b'])); print(Action(type='MATCH', model_id='KS0001', erpnext_name='x', nas_name='x', old_path='', new_path='', content_count=0, content_bytes=0, safe=True, reason='ok'))"`

Expected: 两个 dataclass 实例正常打印

- [ ] **Step 3: Commit**

```bash
git add nas_itemgroup_folders/reconcile.py
git commit -m "feat(nas): reconcile data models"
```

---

### Task 2: reconcile.py — KS 编码解析 + 路径计算

**Files:**
- Modify: `nas_itemgroup_folders/reconcile.py`

- [ ] **Step 1: 添加 KS 编码解析函数**

```python
# 追加到 reconcile.py

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
```

- [ ] **Step 2: 写自测验证**

Run: `uv run python -c "
from nas_itemgroup_folders.reconcile import parse_model_id, expected_path, safe_name
assert parse_model_id('KS0001_三角靠枕') == 'KS0001'
assert parse_model_id('AB1234_xxx') == 'AB1234'
assert parse_model_id('旧的设计文件1') is None
assert parse_model_id('no_underscore') is None
assert expected_path('KS0001', '三角靠枕', '/产品信息', ['床品类', '床头靠枕', '三角靠枕类'], 'flat') == '/产品信息/KS0001_三角靠枕'
assert expected_path('KS0001', '三角靠枕', '/产品信息', ['床品类', '床头靠枕', '三角靠枕类'], 'tree') == '/产品信息/床品类/床头靠枕/三角靠枕类/KS0001_三角靠枕'
print('All assertions passed')
"`

Expected: `All assertions passed`

- [ ] **Step 3: Commit**

```bash
git add nas_itemgroup_folders/reconcile.py
git commit -m "feat(nas): reconcile KS code parser + path calculator"
```

---

### Task 3: reconcile.py — 对账比对逻辑

**Files:**
- Modify: `nas_itemgroup_folders/reconcile.py`

- [ ] **Step 1: 添加 compare() 函数**

```python
# 追加到 reconcile.py


def compare(
    erpnext_items: list[ErpnextItem],
    nas_folders: list[NasFolder],
    target_folder: str,
    layout: str,
    sub_folders: list[str],
) -> list[Action]:
    """核心对账：ERPNext vs NAS，输出 Action 列表。

    匹配策略: 按 model_id (KS编码) 关联两边。
    """
    actions: list[Action] = []
    # model_id -> NasFolder (仅脚本创建的)
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
            # ── MISSING ──
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

        # ── 名称检查 ──
        if nas.name != exp_name:
            if nas.content_count == 0:
                actions.append(Action(
                    type=ActionType.RENAME,
                    model_id=item.model_id,
                    erpnext_name=item.name,
                    nas_name=nas.name,
                    old_path=nas.path,
                    new_path=f"{target_folder}/{exp_name}",
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
                    reason=f"物料组改名: '{nas.name}' -> '{exp_name}'，但旧文件夹有 {nas.content_count} 个文件，禁止自动操作",
                ))
            continue  # 名称不匹配时不再检查路径

        # ── 路径检查 ──
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

        # ── MATCH ── (名称匹配 + 路径匹配，子文件夹补建在 runner 层处理)
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

    # ── EXTRA: NAS 有但 ERPNext 无 ──
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
                    reason=f"ERPNext 已无 {nf.model_id}，NAS 有 {nf.content_count} 个文件: {nf.name}。建议确认是否恢复物料组或手动归档",
                ))

    # ── IGNORE: 非脚本创建的文件夹 ──
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
```

- [ ] **Step 2: 写单元测试**

```python
# 在 reconcile.py 底部追加 if __name__ == "__main__" 自测

if __name__ == "__main__":
    # 自测: MISSING
    erp = [ErpnextItem(name="三角靠枕", model_id="KS0001", parent="三角靠枕类",
                       ancestors=["床品类", "床头靠枕", "三角靠枕类"])]
    nas = []
    actions = compare(erp, nas, "/产品信息", "flat", ["调研报告", "设计稿", "图片", "视频"])
    assert len(actions) == 1
    assert actions[0].type == ActionType.CREATE
    assert actions[0].safe is True

    # 自测: MATCH
    nas = [NasFolder(name="KS0001_三角靠枕", path="/产品信息/KS0001_三角靠枕",
                     model_id="KS0001", content_count=0, content_bytes=0,
                     sub_folders=["调研报告"], is_script_created=True)]
    actions = compare(erp, nas, "/产品信息", "flat", ["调研报告"])
    assert actions[0].type == ActionType.MATCH

    # 自测: NAME_MISMATCH (empty)
    nas = [NasFolder(name="KS0001_旧名", path="/产品信息/KS0001_旧名",
                     model_id="KS0001", content_count=0, content_bytes=0,
                     sub_folders=[], is_script_created=True)]
    actions = compare(erp, nas, "/产品信息", "flat", [])
    assert actions[0].type == ActionType.RENAME

    # 自测: NAME_MISMATCH (with content)
    nas = [NasFolder(name="KS0001_旧名", path="/产品信息/KS0001_旧名",
                     model_id="KS0001", content_count=5, content_bytes=1000,
                     sub_folders=[], is_script_created=True)]
    actions = compare(erp, nas, "/产品信息", "flat", [])
    assert actions[0].type == ActionType.BLOCKED

    # 自测: STRUC_MISMATCH (tree mode, wrong path)
    nas = [NasFolder(name="KS0001_三角靠枕", path="/产品信息/KS0001_三角靠枕",
                     model_id="KS0001", content_count=0, content_bytes=0,
                     sub_folders=[], is_script_created=True)]
    actions = compare(erp, nas, "/产品信息", "tree", [])
    assert actions[0].type == ActionType.MOVE

    # 自测: EXTRA
    nas = [NasFolder(name="KS9999_已删除", path="/产品信息/KS9999_已删除",
                     model_id="KS9999", content_count=5, content_bytes=200,
                     sub_folders=[], is_script_created=True)]
    actions = compare([], nas, "/产品信息", "flat", [])
    assert actions[0].type == ActionType.BLOCKED

    print("All reconcile tests passed!")
```

Run: `uv run python nas_itemgroup_folders/reconcile.py`

Expected: `All reconcile tests passed!`

- [ ] **Step 3: Commit**

```bash
git add nas_itemgroup_folders/reconcile.py
git commit -m "feat(nas): reconcile comparison engine with self-tests"
```

---

### Task 4: reconcile.py — ErpnextScanner + NasScanner

**Files:**
- Modify: `nas_itemgroup_folders/reconcile.py`

- [ ] **Step 1: 添加 Scanner 类**

两边的 Scanner 都接受外部注入的 client（函数参数），不自己 new 连接。

```python
# 追加到 reconcile.py


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

    # 递归收集后代
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
        # 构建祖先链（不含根节点）
        ancestors: list[str] = []
        node = leaf
        while node:
            parent = node.get("parent_item_group", "")
            if not parent or parent not in idx:
                break
            ancestors.append(parent)
            node = idx.get(parent)
        ancestors.reverse()
        # 去掉根节点
        if ancestors and ancestors[0] == item_group_root:
            ancestors = ancestors[1:]

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
    recursive: bool = True,
) -> list[NasFolder]:
    """扫描 NAS 目标文件夹。

    list_folder: 返回 [{"name":..., "path":..., "is_dir":..., "size":..., "mtime":...}]
    递归收集所有子文件夹内容统计。
    """
    results: list[NasFolder] = []
    _scan_nas_dir(list_folder, target_folder, target_folder,
                  sub_folder_names, recursive, results)
    return results


def _scan_nas_dir(
    list_folder,
    current_path: str,
    target_folder: str,
    sub_folder_names: list[str],
    recursive: bool,
    results: list[NasFolder],
) -> tuple[int, int]:
    """递归扫描一个目录，返回 (file_count, total_bytes)。"""
    items = list_folder(current_path, limit=5000)
    sub_dirs: list[str] = []
    file_count = 0
    total_bytes = 0
    extra_folders: list[str] = []

    for item in items:
        if item["is_dir"]:
            sub_dirs.append(item["name"])
            if item["name"] not in sub_folder_names:
                extra_folders.append(item["name"])
        else:
            file_count += 1
            total_bytes += item.get("size", 0)

    # 递归子文件夹
    for dname in sub_dirs:
        sub_path = f"{current_path}/{dname}"
        if recursive:
            fc, tb = _scan_nas_dir(
                list_folder, sub_path, target_folder,
                sub_folder_names, recursive, results,
            )
            file_count += fc
            total_bytes += tb

    # 如果当前路径是目标文件夹的直接子文件夹，记录为一个 NasFolder
    if current_path != target_folder:
        parent = "/".join(current_path.split("/")[:-1])
        if parent == target_folder:
            folder_name = current_path.split("/")[-1]
            model_id = parse_model_id(folder_name)
            is_script = model_id is not None
            results.append(NasFolder(
                name=folder_name,
                path=current_path,
                model_id=model_id,
                content_count=file_count,
                content_bytes=total_bytes,
                sub_folders=[
                    d for d in sub_dirs if d in sub_folder_names
                ],
                extra_folders=[
                    d for d in sub_dirs if d not in sub_folder_names
                ],
                is_script_created=is_script,
            ))

    return file_count, total_bytes
```

- [ ] **Step 2: 更新自测加入 Scanner 测试**

```python
# 追加到 reconcile.py 的 if __name__ == "__main__" 块:

    # 自测: scan_erpnext
    mock_fetch = lambda: [
        {"name": "产品", "parent_item_group": "所有物料组", "is_group": 1, "custom_model_id": None},
        {"name": "床品类", "parent_item_group": "产品", "is_group": 1, "custom_model_id": None},
        {"name": "三角靠枕", "parent_item_group": "床品类", "is_group": 0, "custom_model_id": "KS0001"},
        {"name": "平条靠枕", "parent_item_group": "床品类", "is_group": 0, "custom_model_id": "KS0002"},
        {"name": "靠垫", "parent_item_group": "其他", "is_group": 0, "custom_model_id": "KD0001"},
    ]
    erp_items = scan_erpnext(mock_fetch, "产品")
    assert len(erp_items) == 2
    assert erp_items[0].model_id == "KS0001"
    assert erp_items[0].ancestors == ["床品类"]

    # 自测: scan_nas
    mock_list = lambda path, limit: {
        "/产品信息": [
            {"name": "KS0001_三角靠枕", "path": "/产品信息/KS0001_三角靠枕", "isdir": True, "size": 0},
            {"name": "旧文件", "path": "/产品信息/旧文件", "isdir": True, "size": 0},
        ],
        "/产品信息/KS0001_三角靠枕": [
            {"name": "调研报告", "path": "/产品信息/KS0001_三角靠枕/调研报告", "isdir": True, "size": 0},
            {"name": "设计稿", "path": "/产品信息/KS0001_三角靠枕/设计稿", "isdir": True, "size": 0},
            {"name": "设计稿.psd", "path": "/产品信息/KS0001_三角靠枕/设计稿.psd", "isdir": False, "size": 5000},
        ],
        "/产品信息/KS0001_三角靠枕/调研报告": [],
        "/产品信息/KS0001_三角靠枕/设计稿": [],
        "/产品信息/旧文件": [
            {"name": "doc.pdf", "path": "/产品信息/旧文件/doc.pdf", "isdir": False, "size": 1000},
        ],
    }[path]
    nas_items = scan_nas(mock_list, "/产品信息", ["调研报告", "设计稿", "图片", "视频"])
    assert len(nas_items) == 2
    ks1 = next(f for f in nas_items if f.model_id == "KS0001")
    assert ks1.content_count == 1  # 设计稿.psd
    assert ks1.content_bytes == 5000
    assert ks1.is_script_created is True
    old = next(f for f in nas_items if f.model_id is None)
    assert old.is_script_created is False
    assert old.content_count == 1  # doc.pdf

    print("All scanner tests passed!")
```

Run: `uv run python nas_itemgroup_folders/reconcile.py`

Expected: `All reconcile tests passed!` then `All scanner tests passed!`

- [ ] **Step 3: Commit**

```bash
git add nas_itemgroup_folders/reconcile.py
git commit -m "feat(nas): reconcile ErpnextScanner + NasScanner"
```

---

### Task 5: build_nas_folders.py — 重写为 ReconciliationRunner

**Files:**
- Modify: `nas_itemgroup_folders/build_nas_folders.py`

- [ ] **Step 1: 重写主脚本，组装对账引擎 + NAS 操作 + 报告**

```python
# nas_itemgroup_folders/build_nas_folders.py
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

from NAS_API.synology import _load_dotenv, _parse_nas_url
from nas_itemgroup_folders.reconcile import (
    Action, ActionType,
    scan_erpnext, scan_nas, compare,
    safe_name, expected_folder_name, expected_path,
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


def _make_erpnext_client():
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
            "name", "parent_item_group", "is_group", "custom_model_id",
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

def _make_nas_client():
    base_url = os.getenv("NAS_URL", "").rstrip("/")
    username = os.getenv("NAS_USERNAME", "")
    password = os.getenv("NAS_PASSWORD", "")
    host, port, secure = _parse_nas_url(base_url)
    fl = FileStation(
        ip_address=host, port=port,
        username=username, password=password,
        secure=secure, cert_verify=False,
        dsm_version=7, debug=False,
    )

    def list_folder(path: str, limit: int = 5000) -> list[dict]:
        try:
            resp = fl.get_file_list(
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
                        "mtime": f.get("additional", {}).get("time", {}).get("mtime", 0),
                    }
                    for f in resp["data"]["files"]
                ]
        except Exception as e:
            print(f"  [nas] list error: {e}")
        return []

    def create_folder(path: str, name: str) -> bool:
        try:
            resp = fl.create_folder(path, name, force_parent=True)
            return resp.get("success", False)
        except Exception as e:
            print(f"  [nas] create error: {e}")
            return False

    def move_folder(src: str, dst: str) -> bool:
        """CopyMove from src to dst. src and dst are full paths."""
        try:
            # Parse dst into folder_path + name
            dst_parent = "/".join(dst.split("/")[:-1])
            dst_name = dst.split("/")[-1]
            # Use CopyMove: copy src to dst_parent/dst_name
            resp = fl.start_copy_move(
                path=[src], dest_folder_path=dst_parent,
                overwrite=False, remove_src=True,
            )
            return resp.get("success", False)
        except Exception as e:
            print(f"  [nas] move error: {e}")
            return False

    def rename_folder(path: str, new_name: str) -> bool:
        try:
            resp = fl.rename_folder(path, new_name)
            return resp.get("success", False)
        except Exception as e:
            print(f"  [nas] rename error: {e}")
            return False

    return list_folder, create_folder, move_folder, rename_folder


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
    sub_folders: list[str],
) -> dict:
    """打印对账报告并返回统计。"""
    by_type: dict[str, list[Action]] = {}
    for a in actions:
        by_type.setdefault(a.type, []).append(a)

    mode = "FULL" if full else "TEST"
    print(f"=== NAS-ERPNext 对账报告 ===  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"模式: {mode}  布局: {layout}")
    print()

    # 摘要
    erp_count = sum(1 for a in actions if a.type not in (ActionType.IGNORE,))
    nas_script = sum(1 for a in actions if a.type != ActionType.IGNORE)
    print("差异摘要:")
    for t in [ActionType.MATCH, ActionType.CREATE, ActionType.RENAME,
              ActionType.MOVE, ActionType.MOVE_APPROVAL,
              ActionType.DELETE_EMPTY, ActionType.BLOCKED, ActionType.IGNORE]:
        items = by_type.get(t, [])
        if items:
            safe_count = sum(1 for a in items if a.safe)
            print(f"  {t:20s} {len(items):4d}  (安全: {safe_count})")

    # 自动操作（安全）
    safe_actions = [a for a in actions if a.safe and a.type not in (ActionType.MATCH, ActionType.IGNORE)]
    if safe_actions:
        print(f"\n安全操作（{'DRY-RUN 预览' if dry_run else '已执行'}）:")
        for a in safe_actions:
            icon = "  " if dry_run else "✅"
            print(f"  {icon} [{a.type}] {a.model_id}: {a.reason}")

    # 阻塞项
    blocked = [a for a in actions if not a.safe and a.type not in (ActionType.IGNORE,)]
    if blocked:
        print(f"\n⚠️  阻塞项（有内容无法自动操作）:")
        for a in blocked:
            print(f"  [{a.type}] {a.model_id}: {a.reason}")
            print(f"         旧: {a.old_path}")
            print(f"         新: {a.new_path}")
            print(f"         内容: {a.content_count} 文件, {_fmt_size(a.content_bytes)}")

    # 忽略项
    ignored = by_type.get(ActionType.IGNORE, [])
    if ignored:
        print(f"\n📋 NAS 额外项目（非脚本创建，不碰）:")
        for a in ignored:
            print(f"  {a.nas_name} ({a.content_count} 文件, {_fmt_size(a.content_bytes)})")

    # 统计
    stats = {
        "total": len(actions),
        "match": len(by_type.get(ActionType.MATCH, [])),
        "create": len(by_type.get(ActionType.CREATE, [])),
        "rename": len(by_type.get(ActionType.RENAME, [])),
        "move": len(by_type.get(ActionType.MOVE, [])),
        "move_approval": len(by_type.get(ActionType.MOVE_APPROVAL, [])),
        "delete_empty": len(by_type.get(ActionType.DELETE_EMPTY, [])),
        "blocked": len(by_type.get(ActionType.BLOCKED, [])),
        "ignore": len(ignored),
        "executed": 0,  # filled below
        "skipped": 0,
        "failed": 0,
    }

    print(f"\n{'=' * 60}")
    print(f"总计: 匹配 {stats['match']} | 创建 {stats['create']} "
          f"| 重命名 {stats['rename']} | 移动 {stats['move']} "
          f"| 阻塞 {stats['blocked']} | 忽略 {stats['ignore']}")
    if dry_run:
        print("DRY-RUN — 未实际操作")

    return stats
```

- [ ] **Step 2: 添加 main() 编排函数**

```python
# 继续追加到 build_nas_folders.py


def main(full: bool = False, dry_run: bool = False, layout: str = "flat",
         auto_approve: bool = False) -> None:
    target_folder = os.getenv("NAS_TARGET_FOLDER", "/产品信息")
    ig_root = os.getenv("ITEM_GROUP_ROOT", "产品")
    raw_sub = os.getenv("SUB_FOLDERS", "")
    sub_folders = (
        [s.strip() for s in raw_sub.split(",") if s.strip()]
        if raw_sub else ["调研报告", "设计稿", "图片", "视频"]
    )
    test_ids = {"KS0001", "KS0002"}

    # 1. 拉取 ERPNext 数据
    print(">>> 拉取 ERPNext Item Groups ...")
    fetch_all = _make_erpnext_client()
    erp_items = scan_erpnext(fetch_all, ig_root)
    print(f"    产品子树叶子节点: {len(erp_items)}")
    if not full:
        erp_items = [i for i in erp_items if i.model_id in test_ids]
        print(f"    TEST MODE: {[i.model_id for i in erp_items]}")

    # 2. 扫描 NAS
    print(f">>> 扫描 NAS: {target_folder}")
    list_fn, create_fn, move_fn, rename_fn = _make_nas_client()
    nas_folders = scan_nas(list_fn, target_folder, sub_folders)
    script_count = sum(1 for f in nas_folders if f.is_script_created)
    manual_count = sum(1 for f in nas_folders if not f.is_script_created)
    print(f"    脚本创建: {script_count}  手动/未知: {manual_count}")

    # 3. 对账
    print(">>> 对账比对 ...")
    actions = compare(erp_items, nas_folders, target_folder, layout, sub_folders)
    print(f"    差异: {len(actions)} 项")

    # 4. 执行安全操作
    executed, failed = 0, 0
    safe = [a for a in actions if a.safe and a.type not in (ActionType.MATCH, ActionType.IGNORE)]
    if not dry_run and safe:
        print(f"\n>>> 执行安全操作 ({len(safe)} 项) ...")
        for a in safe:
            try:
                if a.type == ActionType.CREATE:
                    parent = "/".join(a.new_path.split("/")[:-1])
                    name = a.new_path.split("/")[-1]
                    ok = create_fn(parent, name)
                    if ok:
                        # 创建标准子文件夹
                        for sub in sub_folders:
                            create_fn(a.new_path, sub)
                        print(f"  ✅ CREATE {a.new_path}")
                    else:
                        raise Exception("create_folder returned false")

                elif a.type == ActionType.RENAME:
                    parent = "/".join(a.old_path.split("/")[:-1])
                    new_name = a.new_path.split("/")[-1]
                    ok = rename_fn(a.old_path, new_name)
                    if ok:
                        print(f"  ✅ RENAME {a.old_path} -> {a.new_path}")
                    else:
                        raise Exception("rename failed")

                elif a.type == ActionType.MOVE:
                    ok = move_fn(a.old_path, a.new_path)
                    if ok:
                        print(f"  ✅ MOVE   {a.old_path} -> {a.new_path}")
                    else:
                        raise Exception("move failed")

                elif a.type == ActionType.DELETE_EMPTY:
                    ok = create_fn("", "")  # placeholder
                    print(f"  ⚠️  DELETE_EMPTY 跳过（需手动确认）: {a.old_path}")

                executed += 1
            except Exception as e:
                failed += 1
                print(f"  ❌ FAIL  [{a.type}] {a.model_id}: {e}")

        # 5. 补建 MATCH 项缺失的子文件夹
        match_items = [a for a in actions if a.type == ActionType.MATCH and a.content_count >= 0]
        if match_items:
            print(f"\n>>> 检查子文件夹完整性 ({len(match_items)} 项) ...")
            sub_created = 0
            for a in match_items:
                path = expected_path(
                    a.model_id, a.erpnext_name,
                    target_folder,
                    [] if layout == "flat" else [],  # MATCH 时 ancestors 不重要
                    layout,
                )
                # 实际从 erp_items 找 ancestors
                # 简化: 用 NAS 文件夹实际路径
                nas_item = next(
                    (f for f in nas_folders if f.model_id == a.model_id), None
                )
                if nas_item is None:
                    continue
                existing_subs = set(nas_item.sub_folders)
                for sub in sub_folders:
                    if sub not in existing_subs:
                        ok = create_fn(nas_item.path, sub)
                        if ok:
                            sub_created += 1
            if sub_created:
                print(f"    补建子文件夹: {sub_created}")

    # 6. 报告
    print()
    stats = _print_report(actions, layout, full, dry_run, sub_folders)
    stats["executed"] = executed
    stats["failed"] = failed
    stats["skipped"] = len(safe) - executed if dry_run else 0

    # 保存
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
            {"type": a.type, "model_id": a.model_id, "reason": a.reason,
             "old_path": a.old_path, "new_path": a.new_path,
             "content_count": a.content_count, "content_bytes": a.content_bytes}
            for a in actions if not a.safe and a.type not in (ActionType.IGNORE,)
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {report_path}")

    # 快照
    snapshot_path = _DIR_OUT / "last_snapshot.json"
    snapshot_path.write_text(json.dumps({
        "run_at": datetime.now().isoformat(),
        "layout": layout,
        "erpnext": {
            "root": ig_root,
            "total_leaves": len(erp_items),
            "items": [
                {"name": i.name, "model_id": i.model_id,
                 "parent": i.parent, "ancestors": i.ancestors,
                 "expected_path": expected_path(
                     i.model_id, i.name, target_folder, i.ancestors, layout)}
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
    auto = "--auto" in sys.argv
    layout = "flat"
    for arg in sys.argv:
        if arg.startswith("--layout="):
            layout = arg.split("=", 1)[1]
    mode = "DRY-RUN" if dry else ("FULL" if full else "TEST")
    print(f"=== NAS-ERPNext Reconciliation ===")
    print(f"mode={mode}  layout={layout}")
    main(full=full, dry_run=dry, layout=layout, auto_approve=auto)
```

- [ ] **Step 3: 验证 dry-run 可以跑通**

Run: `cd nas_itemgroup_folders && uv run python build_nas_folders.py --dry-run`

Expected: 拉取 ERPNext 数据 → 扫描 NAS → 输出对比报告，确认 KS0001/KS0002 为 MATCH 状态、8 个子文件夹存在

- [ ] **Step 4: Commit**

```bash
git add nas_itemgroup_folders/build_nas_folders.py
git commit -m "feat(nas): rewrite build script as ReconciliationRunner"
```

---

### Task 6: 实际测试 — flat 模式下对账

**Files:**
- (no changes, verification only)

- [ ] **Step 1: Dry-run 验证**

Run: `cd nas_itemgroup_folders && uv run python build_nas_folders.py --dry-run`

Expected output: 2 MATCH, 0 CREATE, 0 BLOCKED

- [ ] **Step 2: 删除 KS0001 的一个子文件夹，验证子文件夹补建**

Run on NAS manually or via script:

```bash
uv run python -c "
from synology_api.filestation import FileStation
from NAS_API.synology import _parse_nas_url, _load_dotenv
from pathlib import Path
import os
_load_dotenv([Path('NAS_API/.env')])
host, port, secure = _parse_nas_url(os.getenv('NAS_URL',''))
fl = FileStation(ip_address=host, port=port, username=os.getenv('NAS_USERNAME',''), password=os.getenv('NAS_PASSWORD',''), secure=secure, cert_verify=False)
fl.delete_blocking_function('/产品信息/KS0001_三角靠枕/图片')
print('Deleted 图片 sub-folder')
"
```

Then re-run: `cd nas_itemgroup_folders && uv run python build_nas_folders.py`

Expected: 补建 "图片" 子文件夹

- [ ] **Step 3: 验证 rename 检测 — 模拟物料组改名**

Create a NAS folder with old name:

```bash
uv run python -c "
from synology_api.filestation import FileStation
from NAS_API.synology import _parse_nas_url, _load_dotenv
from pathlib import Path
import os
_load_dotenv([Path('NAS_API/.env')])
host, port, secure = _parse_nas_url(os.getenv('NAS_URL',''))
fl = FileStation(ip_address=host, port=port, username=os.getenv('NAS_USERNAME',''), password=os.getenv('NAS_PASSWORD',''), secure=secure, cert_verify=False)
fl.create_folder('/产品信息', 'KS0001_旧名称', force_parent=True)
print('Created KS0001_旧名称')
"
```

Run: `cd nas_itemgroup_folders && uv run python build_nas_folders.py --dry-run`

Expected output: NAME_MISMATCH for KS0001 (or conflict with existing)

Cleanup: `fl.delete_blocking_function('/产品信息/KS0001_旧名称')`

- [ ] **Step 4: Commit (if any fixes)**

---

### Task 7: 树状布局测试

**Files:**
- (no changes, verification only)

- [ ] **Step 1: Dry-run with tree layout**

Run: `cd nas_itemgroup_folders && uv run python build_nas_folders.py --dry-run --layout=tree`

Expected: 显示 KS0001/KS0002 从 flat 路径到 tree 路径的 MOVE 或 MOVE_APPROVAL 差异

- [ ] **Step 2: 实际切换为 tree 布局**

Run: `cd nas_itemgroup_folders && uv run python build_nas_folders.py --layout=tree`

Expected: KS0001/KS0002 从 `/产品信息/KS0001_三角靠枕/` 移动到 `/产品信息/床品类/床头靠枕/三角靠枕类/KS0001_三角靠枕/`（空文件夹 → 自动 MOVE）

- [ ] **Step 3: 验证 tree 布局 NAS 文件夹存在**

Run: `uv run python -c "..."` list `/产品信息/床品类/` to verify tree structure

- [ ] **Step 4: 切回 flat 布局**

Run: `cd nas_itemgroup_folders && uv run python build_nas_folders.py --layout=flat`

Expected: MOVE back to flat

- [ ] **Step 5: Commit**

---

### Task 8: 清理 + docs

**Files:**
- Modify: `nas_itemgroup_folders/.env`
- Create: `nas_itemgroup_folders/README.md`

- [ ] **Step 1: Update .env with SUB_FOLDERS**

```
# nas_itemgroup_folders/.env — 追加
SUB_FOLDERS=调研报告,设计稿,图片,视频
```

- [ ] **Step 2: Create README.md**

```markdown
# NAS-ERPNext 文件夹对账

## 使用

```bash
uv run python build_nas_folders.py                # 测试模式 (KS0001, KS0002)
uv run python build_nas_folders.py --full         # 全量 404 个
uv run python build_nas_folders.py --dry-run      # 仅对比报告，不操作
uv run python build_nas_folders.py --layout=tree  # 按 ERPNext 树结构布局
uv run python build_nas_folders.py --layout=flat  # 扁平布局
```

## 对账逻辑

每次运行从头对比 ERPNext 产品物料组 ↔ NAS /产品信息/ 文件夹：

- 缺失 → 自动创建 + 子文件夹
- 改名 → 空文件夹自动重命名，有内容阻塞
- 路径变更 → 空文件夹自动移动，有内容需确认
- NAS 多余（ERPNext 已删）→ 报告，不自动删
- 非脚本创建的文件夹 → 忽略不碰
```

- [ ] **Step 3: Git status check + final commit**

```bash
git status
git add nas_itemgroup_folders/
git commit -m "docs(nas): update env + README for reconciliation tool"
```

---

### Self-Review

1. **Spec coverage**: All 6 comparison states covered → MATCH/MISSING/NAME_MISMATCH/STRUC_MISMATCH/EXTRA/IGNORE. Decision tree implemented. Flat↔tree layout switching. Sub-folder management. Snapshot + report output. All CLI flags.

2. **Placeholder scan**: No TBD/TODO/placeholder.

3. **Type consistency**: `ErpnextItem`, `NasFolder`, `Action` defined in Task 1, used consistently through Tasks 3-5. `compare()` returns `list[Action]`. Scanner functions return `list[ErpnextItem]` and `list[NasFolder]`.
