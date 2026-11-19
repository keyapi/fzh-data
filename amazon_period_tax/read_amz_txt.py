# -*- coding: utf-8 -*-
"""读取账期桶内 Amazon 结算 .txt（Colab「税账期TXT 挂载Gdrive」同源逻辑 + 渠道账号规范名）。"""
from __future__ import annotations

import os
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
_PKG = Path(__file__).resolve().parent
_DING = _REPO / "dingtalk" / "dingtalk_oa_approval"
for _p in (_PKG, _DING):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from amz_txt_naming import account_prefix_from_stem, preprocess_stem  # noqa: E402
from bucket_meta import bucket_period_range  # noqa: E402
from channel_canonical import canonical_account  # noqa: E402

DEFAULT_EXCLUDE_FOLDERS = ("杨鹏瑶", "贾晓林", "尹天强")

# settlement-end-date 形如 ``2026-07-28 01:03:22 UTC``；部分国家站导出为 ``28.07.2026 01:03:22 UTC``
_DATE_YMD = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_DATE_DMY = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})")

_META_COLS = ("settlement-id", "settlement-end-date", "deposit-date")


def _parse_date_value(value: str | None) -> date | None:
    if not value:
        return None
    s = value.strip()
    m = _DATE_YMD.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = _DATE_DMY.match(s)
        if not m:
            return None
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def settlement_meta(text: str) -> dict:
    """解析 (settlement-id, settlement-end-date, deposit-date) 原始字符串。

    settlement-id 每行都有；两个日期只出现在首行（TransactionTotalAmount），缺失返回 None。
    """
    out = {"settlement_id": None, "settlement_end_raw": None, "deposit_raw": None}
    lines = text.splitlines()
    if not lines:
        return out
    header = lines[0].split("\t")
    idx = {name: (header.index(name) if name in header else None) for name in _META_COLS}
    id_idx = idx["settlement-id"] if idx["settlement-id"] is not None else 0
    end_idx, dep_idx = idx["settlement-end-date"], idx["deposit-date"]

    for line in lines[1:]:
        cols = line.split("\t")
        if out["settlement_id"] is None and len(cols) > id_idx and cols[id_idx].strip():
            out["settlement_id"] = cols[id_idx].strip()
        if out["settlement_end_raw"] is None and end_idx is not None and len(cols) > end_idx and cols[end_idx].strip():
            out["settlement_end_raw"] = cols[end_idx].strip()
        if out["deposit_raw"] is None and dep_idx is not None and len(cols) > dep_idx and cols[dep_idx].strip():
            out["deposit_raw"] = cols[dep_idx].strip()
        if out["settlement_id"] is not None and (
            (end_idx is None or out["settlement_end_raw"] is not None)
            and (dep_idx is None or out["deposit_raw"] is not None)
        ):
            break
    return out


def parse_settlement_meta(text: str) -> tuple[str | None, str | None]:
    """(settlement-id, settlement-end-date) 原始字符串。"""
    meta = settlement_meta(text)
    return meta["settlement_id"], meta["settlement_end_raw"]


def settlement_end_date(text: str) -> date | None:
    """内部 settlement-end-date → date；缺失或非法返回 None。"""
    return _parse_date_value(settlement_meta(text)["settlement_end_raw"])


def settlement_window_date(text: str) -> tuple[date | None, date | None, date | None]:
    """返回 (窗口判定日期, settlement_end_date, deposit_date)。

    账期桶是 OA 的「账期日期」4 号→次月 3 号窗口，对应 Amazon 结算的 **deposit-date**
    （打款日）。用 deposit-date 判定才不会把「7/20–8/3 结算、8/5 打款」的 8 月正常结算误判成跨期；
    deposit-date 缺失时退回 settlement-end-date。
    """
    meta = settlement_meta(text)
    end = _parse_date_value(meta["settlement_end_raw"])
    dep = _parse_date_value(meta["deposit_raw"])
    return (dep or end), end, dep


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


def read_amz_txt_file(
    file_path: Path, *, repair_dir: Path | None = None, text: str | None = None
) -> pd.DataFrame | None:
    file_name = file_path.name
    if not (file_name.upper().startswith("AMZ") and file_name.lower().endswith(".txt")):
        return None
    orig_path = file_path
    if_file_with_issue = False
    if text is None:
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
    stats_out: dict | None = None,
    period_range: tuple[date, date] | None = None,
    allow_out_of_period: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    """扫描桶下一级人名文件夹。返回 (合并 df, 报告行)。

    - 同一内容（md5 相同）的 txt 只读第一份，其余记 ``SKIP-DUP``（同一文件被多人上传是常态，
      不去重会把 Tax 多算一遍）。
    - 按 txt 内部 **deposit-date**（打款日；缺失退回 settlement-end-date）与桶名
      ``账期YYYYMMDD-YYYYMMDD`` 窗口比对：不在窗口内的记
      ``OUT-OF-PERIOD <rel> window=... end=... deposit=...`` 并**默认排除**（错放到别的账期桶的
      副本，会把 Tax 跨月重复计入）。``allow_out_of_period=True`` 可强制纳入。
    - 取不到内部日期的记 ``NO-PERIOD-DATE``，仍然纳入（宁可算上也不静默丢）。
    - repair_dir：tab 修复缓存目录，默认 ``{桶的父目录}/.repair_cache_{桶名}``，
      不写在桶内 —— 桶内任何目录都会被当成「人名文件夹」扫描。
    - 跳过 ``.`` 开头的目录（缓存/隐藏目录不是人名夹）。
    - ``stats_out``：若传入 dict，会被填入文件/行数对账数字。
    """
    import hashlib

    reports: list[str] = []
    dfs: list[pd.DataFrame] = []
    stats = {
        "bucket": bucket_dir.name,
        "files_total": 0,
        "files_used": 0,
        "files_dup": 0,
        "files_failed": 0,
        "files_out_of_period": 0,
        "files_no_period_date": 0,
        "rows_total": 0,
        "rows_mismatch": 0,
    }
    if not bucket_dir.is_dir():
        raise FileNotFoundError(bucket_dir)
    if period_range is None:
        period_range = bucket_period_range(bucket_dir.name)
    if period_range is None:
        reports.append(
            f"NO-PERIOD-BUCKET {bucket_dir.name}: 桶名不含账期YYYYMMDD-YYYYMMDD，未做内部结算日窗口校验"
        )
    start, end = period_range if period_range else (None, None)
    cache = repair_dir if repair_dir is not None else (bucket_dir.parent / f".repair_cache_{bucket_dir.name}")
    subfolders = [p for p in bucket_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if exclude_folders:
        subfolders = [p for p in subfolders if p.name not in exclude_folders]
    if include_folders:
        subfolders = [p for p in subfolders if p.name in include_folders]

    seen_md5: dict[str, str] = {}
    for sub in sorted(subfolders):
        for f in sorted(sub.iterdir()):
            if not f.is_file() or not f.name.lower().endswith(".txt"):
                continue
            if not f.name.upper().startswith("AMZ"):
                continue
            stats["files_total"] += 1
            rel = f"{sub.name}/{f.name}"
            try:
                raw = f.read_bytes()
            except OSError as e:
                stats["files_failed"] += 1
                reports.append(f"FAIL {rel}: {e}")
                continue
            try:
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")
            except Exception as e:  # pragma: no cover - decode 极少失败
                stats["files_failed"] += 1
                reports.append(f"FAIL {rel}: {e}")
                continue

            window_date, end_date, deposit_date = settlement_window_date(text)
            if start is not None and window_date is not None:
                if not (start <= window_date <= end):
                    stats["files_out_of_period"] += 1
                    reports.append(
                        f"OUT-OF-PERIOD {rel} window={window_date.isoformat()} "
                        f"end={end_date.isoformat() if end_date else '-'} "
                        f"deposit={deposit_date.isoformat() if deposit_date else '-'}"
                    )
                    if not allow_out_of_period:
                        continue
            elif start is not None and window_date is None:
                stats["files_no_period_date"] += 1
                reports.append(
                    f"NO-PERIOD-DATE {rel}（内部 settlement-end-date / deposit-date 缺失，无法校验账期窗口）"
                )

            md5 = hashlib.md5(raw).hexdigest()
            if md5 in seen_md5:
                stats["files_dup"] += 1
                reports.append(f"SKIP-DUP {rel} == {seen_md5[md5]}")
                continue
            seen_md5[md5] = rel
            try:
                df = read_amz_txt_file(f, repair_dir=cache, text=text)
            except Exception as e:
                stats["files_failed"] += 1
                reports.append(f"FAIL {rel}: {e}")
                continue
            if df is not None and not df.empty:
                expected_rows = max(len([ln for ln in text.splitlines() if ln.strip()]) - 1, 0)
                if expected_rows != len(df):
                    stats["rows_mismatch"] += 1
                    reports.append(
                        f"FAIL {rel} rows-mismatch file={expected_rows} parsed={len(df)}"
                    )
                dfs.append(df)
                stats["files_used"] += 1
                stats["rows_total"] += len(df)
                reports.append(f"OK {rel} rows={len(df)} acct={df['渠道账号'].iloc[0]}")

    reports.append(
        "SUMMARY files={files_total} used={files_used} dup={files_dup} failed={files_failed} "
        "out_of_period={files_out_of_period} no_period_date={files_no_period_date} "
        "rows_mismatch={rows_mismatch} rows={rows_total}".format(**stats)
    )
    if stats_out is not None:
        stats_out.update(stats)

    if not dfs:
        return pd.DataFrame(), reports
    return pd.concat(dfs, axis=0, ignore_index=True, sort=False), reports

