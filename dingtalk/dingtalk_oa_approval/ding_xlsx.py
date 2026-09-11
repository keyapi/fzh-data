# -*- coding: utf-8 -*-
"""销售收款确认单 Excel：读两行表头、展开销售账户、21 位审批编号当文本。

路径一律走 DINGTALK_OA_WORK / 环境变量，不要把本机人名目录写进 git。
原先仓库外 patch_july_2026.py 里被其它脚本 import 的部分收在这里。
"""
from __future__ import annotations

import os
import warnings
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from parse import ym
from paths import OA_WORK

warnings.filterwarnings("ignore", message="Workbook contains no default style")

RECEIPT_PREFIX = "收款账户"


def work_file(env_key: str, fallback_name: str) -> Path:
    raw = os.environ.get(env_key, "").strip()
    if raw:
        return Path(raw)
    return OA_WORK / fallback_name


# 方法 2 用的跨月导出（发起 7/4–9/8）；文件名可改，目录必须来自 DINGTALK_OA_WORK
F2 = work_file(
    "DINGTALK_OA_F2_XLSX",
    "Amazon&新平台成本 20260704-20260908 销售收款确认单-20260909145945.xlsx",
)
OUT_JULY = work_file(
    "DINGTALK_OA_JULY_METHOD2_XLSX",
    "Amazon&新平台成本 20260704-20260803 销售收款确认单-20260909补迟交_方法2剔除8月9月账期.xlsx",
)


def id_text(v) -> str:
    """21 位审批编号必须当文本。已经变成 float 的无法还原，原样转成最短十进制。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, int):
        return str(v)
    s = str(v).strip()
    if s.lower() in {"", "nan", "none"}:
        return ""
    if "e+" in s.lower() or "e-" in s.lower():
        try:
            return f"{int(float(s))}"
        except ValueError:
            return s
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def read_dingtalk_xlsx(path: Path) -> pd.DataFrame:
    """找到含「账期日期」的表头行再读。aflow 导出常见第 1 行列名、第 2 行子表头。"""
    xp = pd.ExcelFile(path)
    frames = []
    for sn in xp.sheet_names:
        hdr = xp.parse(sn, header=None, nrows=8)
        hr_i = None
        for i in range(min(8, len(hdr))):
            row = [str(x).strip() if pd.notna(x) else "" for x in hdr.iloc[i]]
            if "账期日期" in row:
                hr_i = i
                break
        if hr_i is None:
            continue
        df = xp.parse(sn, header=hr_i)
        if "账期日期" not in df.columns:
            continue
        df = df[df["账期日期"].notna()].copy()
        if df.empty:
            continue
        df["_sheet"] = sn
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def flatten_sale_account(row: pd.Series) -> tuple[str, str]:
    platform = str(row.get("选择平台", "")).strip()
    preferred = []
    if platform == "亚马逊":
        preferred = [c for c in row.index if str(c).startswith("AMZ") and str(c).endswith("账户")]
        preferred.append("亚马逊注册账户")
    elif platform == "新平台":
        preferred = ["新平台销售账户", "Walmart账户", "Allegro账户", "HOME24账户", "Mano账户", "Kaufland账户"]
    elif platform == "独立站":
        preferred = ["独立站账户"]
    for c in preferred:
        if c in row.index and pd.notna(row.get(c)):
            v = str(row[c]).strip()
            if v and v.lower() != "nan":
                return v, c
    for c in row.index:
        cs = str(c)
        if not cs.endswith("账户") or cs.startswith(RECEIPT_PREFIX):
            continue
        if pd.notna(row.get(c)):
            v = str(row[c]).strip()
            if v and v.lower() != "nan":
                return v, cs
    return "", ""


def flatten_receipt(row: pd.Series) -> str:
    parts = []
    for c in row.index:
        if not str(c).startswith(RECEIPT_PREFIX):
            continue
        if pd.notna(row.get(c)):
            v = str(row[c]).strip()
            if v and v.lower() != "nan":
                parts.append(f"{c}={v}")
    return " | ".join(parts)


def bucket_month(d) -> str:
    """发起日所在提交窗 → YYYY-MM（4 号起算该月）。"""
    if d is None or pd.isna(d):
        return ""
    if d.day >= 4:
        return f"{d.year:04d}-{d.month:02d}"
    y, m = d.year, d.month - 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def window_end(z: str) -> pd.Timestamp:
    y, m = int(z[:4]), int(z[5:7]) + 1
    if m == 13:
        y, m = y + 1, 1
    return pd.Timestamp(y, m, 3)


def classify(z: str, b: str, initiated) -> tuple[str, object]:
    if not z or not b:
        return "未知", None
    if z < b:
        end = window_end(z)
        days = None
        if initiated is not None and not pd.isna(initiated):
            days = int((initiated.normalize() - end).days)
        return "迟交", days
    if z > b:
        return "早交", None
    return "正常", None


def unique_key(r: pd.Series) -> str:
    """迟交挪动登记唯一键：审批编号|账期日期|销售账户|销售额。"""
    acct = str(r.get("销售账户_展开") or "").strip()
    if not acct:
        acct, _ = flatten_sale_account(r)
    amt = r.get("销售额", r.get("应收账款", r.get("应收金额", "")))
    d = pd.to_datetime(r.get("账期日期"), errors="coerce")
    ds = d.strftime("%Y-%m-%d") if pd.notna(d) else ""
    return "|".join([id_text(r.get("审批编号", "")), ds, acct, str(amt).strip()])


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["账期月"] = out["账期日期"].map(ym)
    out["发起"] = pd.to_datetime(out["发起时间"], errors="coerce")
    out["完成"] = pd.to_datetime(out.get("完成时间"), errors="coerce") if "完成时间" in out.columns else pd.NaT
    acct = out.apply(flatten_sale_account, axis=1)
    out["销售账户_展开"] = [a for a, _ in acct]
    out["销售账户来源列"] = [s for _, s in acct]
    out["收款账户_展开"] = out.apply(flatten_receipt, axis=1)
    out["提交桶"] = out["发起"].map(bucket_month)
    cls = [classify(z, b, i) for z, b, i in zip(out["账期月"], out["提交桶"], out["发起"])]
    out["提交分类"] = [c for c, _ in cls]
    out["迟交天数"] = [d for _, d in cls]
    out["_key"] = out.apply(unique_key, axis=1)
    return out


def exclude_keys(df: pd.DataFrame, keys: set[str]) -> pd.DataFrame:
    if df.empty or not keys:
        return df
    col = df["_key"] if "_key" in df.columns else df.apply(unique_key, axis=1)
    return df[~col.isin(keys)].copy()


def cell(v) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (ValueError, TypeError):
        pass
    if isinstance(v, pd.Timestamp):
        if v.hour or v.minute or v.second:
            return v.strftime("%Y-%m-%d %H:%M:%S")
        return v.strftime("%Y-%m-%d")
    if isinstance(v, datetime):
        if v.hour or v.minute or v.second:
            return v.strftime("%Y-%m-%d %H:%M:%S")
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.isoformat()
    return str(v).strip()
