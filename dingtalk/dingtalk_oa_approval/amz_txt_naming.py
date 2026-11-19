# -*- coding: utf-8 -*-
"""Amazon 结算 txt 文件名统一化（钉钉/NAS/Colab 共用口径）。"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from channel_canonical import canonical_account
from parse import parse_amz_channel

# 钉钉/Windows 重复上传后缀；(1) 不参与账期语义，归档名去掉
_DUP_SUFFIX = re.compile(r"\(\d+\)$")


def preprocess_stem(stem: str) -> str:
    s = re.sub(r"\s+", "", stem or "")
    s = _DUP_SUFFIX.sub("", s)
    # Colab/脚本无法稳定识别的写法 → 表上渠道账号连写
    s = re.sub(r"(?i)AMZStrusery-US", "AMZStruseryUS", s)
    s = re.sub(r"(?i)AMZStrusery-([A-Z]{2})(?=-|$)", r"AMZStrusery\1", s)
    return s


def _pad_ymd(y: int, mo: int, d: int) -> str | None:
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _year_for_mmdd(mm: int, y_hint: int, mo_hint: int | None) -> int:
    """只有 MMDD 时补年份：跨年（解析月 > 账期月）归上一年。

    例：hint=2026-10, `-0930` → 2026-09-30；hint=2026-01, `-1231` → 2025-12-31。
    """
    if mo_hint and mm > mo_hint:
        return y_hint - 1
    return y_hint


def settlement_date_from_stem(stem: str, hint_ym: str = "") -> str | None:
    """从文件名解析结算结束日 YYYY-MM-DD。"""
    s = preprocess_stem(stem)
    y_hint = int(hint_ym[:4]) if hint_ym and len(hint_ym) >= 4 else 2026
    mo_hint = int(hint_ym[5:7]) if hint_ym and len(hint_ym) >= 7 else None

    m = re.search(r"(20\d{2})[-._](\d{1,2})[-._](\d{1,2})", s)
    if m:
        return _pad_ymd(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = re.search(r"(20\d{2})(\d{2})(\d{2})$", s)
    if m:
        return _pad_ymd(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = re.search(r"-(\d{4})$", s)
    if m:
        mm, dd = int(m.group(1)[:2]), int(m.group(1)[2:])
        hit = _pad_ymd(_year_for_mmdd(mm, y_hint, mo_hint), mm, dd)
        if hit:
            return hit

    m = re.search(r"-(\d{1,2})[.\-](\d{1,2})$", s)
    if m:
        mm, dd = int(m.group(1)), int(m.group(2))
        return _pad_ymd(_year_for_mmdd(mm, y_hint, mo_hint), mm, dd)

    amz = parse_amz_channel(s + ".txt")
    if amz and amz.get("date_raw"):
        dr = str(amz["date_raw"])
        m = re.search(r"(20\d{2})[-._]?(\d{1,2})[-._]?(\d{1,2})", dr)
        if m:
            return _pad_ymd(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.search(r"(\d{1,2})[.\-](\d{1,2})", dr)
        if m:
            mm, dd = int(m.group(1)), int(m.group(2))
            return _pad_ymd(_year_for_mmdd(mm, y_hint, mo_hint), mm, dd)
    return None


def account_prefix_from_stem(stem: str) -> str:
    s = preprocess_stem(stem)
    for pat in (
        r"-20\d{2}[-._]\d{1,2}[-._]\d{1,2}$",
        r"-20\d{6}$",
        r"-\d{4}$",
        r"-\d{1,2}[.\-]\d{1,2}$",
    ):
        s = re.sub(pat, "", s, flags=re.I)
    return s


def propose_txt_name(
    old_name: str, hint_ym: str = "", existing: set[str] | None = None
) -> tuple[str | None, str]:
    """返回 (规范文件名或 None, 说明)。

    ``existing``：同目录下已有文件名集合（含即将被占用的目标名）。目标已存在时返回
    ``(None, "目标已存在")`` —— 绝不覆盖别人已归档的同名 txt。
    """
    if not (old_name or "").lower().endswith(".txt"):
        return None, "非txt"
    stem = Path(old_name).stem
    acct_raw = account_prefix_from_stem(stem)
    if not acct_raw.upper().startswith("AMZ"):
        return None, "非AMZ前缀"
    canon = canonical_account(acct_raw)
    if not canon:
        return None, "无法映射渠道账号"
    dt = settlement_date_from_stem(stem, hint_ym=hint_ym)
    if not dt:
        return None, "无法解析结算日"
    new_name = f"{canon}-{dt}.txt"
    if new_name == old_name:
        return new_name, "已规范"
    if existing and new_name.casefold() in {n.casefold() for n in existing}:
        return None, "目标已存在"
    return new_name, "需重命名"
