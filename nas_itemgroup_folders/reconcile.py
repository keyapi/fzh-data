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
