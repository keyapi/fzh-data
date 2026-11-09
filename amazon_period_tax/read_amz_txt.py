# -*- coding: utf-8 -*-
"""读取账期桶内 Amazon 结算 .txt（Colab「税账期TXT 挂载Gdrive」同源逻辑 + 渠道账号规范名）。"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
_DING = _REPO / "dingtalk" / "dingtalk_oa_approval"
if str(_DING) not in sys.path:
    sys.path.insert(0, str(_DING))

from amz_txt_naming import account_prefix_from_stem, preprocess_stem  # noqa: E402
from channel_canonical import canonical_account  # noqa: E402

DEFAULT_EXCLUDE_FOLDERS = ("杨鹏瑶", "贾晓林", "尹天强")


def check_for_issues(lines: list[str]) -> bool:
    if not lines:
        return False
    header_tabs = lines[0].count("\t")
    for line in lines[1:]:
        if line.count("\t") > header_tabs:
            return True
    return False


def fix_issues_in_txt(lines: list[str]) -> list[str]:
    if not lines:
        return lines
    header_tabs = lines[0].count("\t")
    fixed_lines = [lines[0]]
    for line in lines[1:]:
        if line.count("\t") > header_tabs:
            reverse_index_1 = line[::-1].find("\t")
            reverse_index_2 = line[::-1].find("\t", reverse_index_1 + 1)
            reverse_index_3 = line[::-1].find("\t", reverse_index_2 + 1)
            if reverse_index_3 != -1:
                correct_index_3 = len(line) - reverse_index_3 - 1
                line = line[:correct_index_3] + line[correct_index_3 + 1 :]
        fixed_lines.append(line)
    return fixed_lines


def _account_from_filename(file_name: str) -> str:
    stem = preprocess_stem(Path(file_name).stem)
    raw = account_prefix_from_stem(stem)
    if not raw.upper().startswith("AMZ"):
        legacy = re.sub(r"\s*[-–]\s*", "-", file_name).split("-")[0].strip()
        legacy = re.sub(r"\d+$", "", legacy)
        raw = legacy
    return canonical_account(raw) or raw


def convert_amz_last2letter_upper(x: str) -> str:
    x = str(x or "")
    if x[:3].upper() == "AMZ":
        return x[:3].upper() + x[3:-2] + x[-2:].upper()
    return x


def read_amz_txt_file(file_path: Path, *, repair_dir: Path | None = None) -> pd.DataFrame | None:
    file_name = file_path.name
    if not (file_name.upper().startswith("AMZ") and file_name.lower().endswith(".txt")):
        return None
    orig_path = file_path
    if_file_with_issue = False
    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = file_path.read_text(encoding="latin-1")
    lines = text.splitlines(keepends=True)
    if not lines:
        return None
    if check_for_issues(lines):
        if_file_with_issue = True
        fixed_lines = fix_issues_in_txt(lines)
        repair_dir = repair_dir or (file_path.parent / "自动修复sku")
        repair_dir.mkdir(parents=True, exist_ok=True)
        fixed_name = file_name.replace(".txt", "_自动修复sku.txt")
        fixed_path = repair_dir / fixed_name
        fixed_path.write_text("".join(fixed_lines), encoding="utf-8")
        file_path = fixed_path
        file_name = fixed_name

    df = pd.read_csv(file_path, sep="\t")
    for col in ("total-amount", "amount"):
        if col in df.columns:
            df[col] = df[col].map(
                lambda x: float(str(x).replace(",", "."))
                if isinstance(x, str) and "," in str(x)
                else (float(x) if pd.notna(x) and str(x).strip() != "" else x)
            )
    if "currency" in df.columns and df["currency"].notnull().any():
        df["currency"] = df["currency"].ffill()

    account = _account_from_filename(orig_path.name)
    account = convert_amz_last2letter_upper(account)

    if if_file_with_issue:
        sub_folder = orig_path.parent.name
        parent_folder = orig_path.parent.parent.name
    else:
        sub_folder = file_path.parent.name
        parent_folder = file_path.parent.parent.name

    df.insert(0, "父文件夹名", parent_folder)
    df.insert(1, "子文件夹名", sub_folder)
    df.insert(2, "文件名", file_name)
    df.insert(3, "渠道账号", account)
    return df


def read_bucket_amz_txts(
    bucket_dir: Path,
    *,
    exclude_folders: tuple[str, ...] = DEFAULT_EXCLUDE_FOLDERS,
    include_folders: tuple[str, ...] | None = None,
    repair_dir: Path | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """扫描桶下一级人名文件夹。返回 (合并 df, 报告行)。

    repair_dir：tab 修复缓存目录，默认 ``{bucket_dir}/.repair_cache``（不写人名文件夹/自动修复sku）。
    """
    reports: list[str] = []
    dfs: list[pd.DataFrame] = []
    if not bucket_dir.is_dir():
        raise FileNotFoundError(bucket_dir)
    cache = repair_dir if repair_dir is not None else (bucket_dir / ".repair_cache")
    subfolders = [p for p in bucket_dir.iterdir() if p.is_dir()]
    if exclude_folders:
        subfolders = [p for p in subfolders if p.name not in exclude_folders]
    if include_folders:
        subfolders = [p for p in subfolders if p.name in include_folders]

    for sub in sorted(subfolders):
        for f in sorted(sub.iterdir()):
            if not f.is_file() or not f.name.lower().endswith(".txt"):
                continue
            if not f.name.upper().startswith("AMZ"):
                continue
            try:
                df = read_amz_txt_file(f, repair_dir=cache)
            except Exception as e:
                reports.append(f"FAIL {sub.name}/{f.name}: {e}")
                continue
            if df is not None and not df.empty:
                dfs.append(df)
                reports.append(f"OK {sub.name}/{f.name} rows={len(df)} acct={df['渠道账号'].iloc[0]}")

    if not dfs:
        return pd.DataFrame(), reports
    return pd.concat(dfs, axis=0, ignore_index=True, sort=False), reports
