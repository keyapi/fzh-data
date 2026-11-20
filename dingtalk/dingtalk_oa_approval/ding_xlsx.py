# -*- coding: utf-8 -*-
"""销售收款确认单 Excel：读两行表头、展开销售账户、21 位审批编号当文本。

路径一律走 DINGTALK_OA_WORK / 环境变量，不要把本机人名目录写进 git。
原先仓库外 patch_july_2026.py 里被其它脚本 import 的部分收在这里。
"""
from __future__ import annotations

import numbers
import os
import re
import warnings
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
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


_ID_21 = re.compile(r"^\d{21}$")


def id_status(v) -> str:
    """审批编号可信度：``ok`` / ``missing`` / ``corrupted`` / ``other``。

    Excel 把 21 位编号读成 float 后只剩 15~17 位有效数字，任何「整数化」都是
    **伪恢复**（D01）。这种值标记 ``corrupted``，由导出层阻断，绝不猜一个看似
    21 位的数字。
    """
    if v is None:
        return "missing"
    if isinstance(v, bool):
        return "other"
    # Excel 数值单元格：>=16 位必然超出 IEEE754 精确整数范围（2^53≈9e15），
    # 21 位编号读成 int/float 时低位已丢，禁止当作原值。
    if isinstance(v, numbers.Integral):
        return "corrupted" if abs(int(v)) >= 10**15 else "ok"
    if isinstance(v, numbers.Real):
        if pd.isna(v):
            return "missing"
        f = float(v)
        if not f.is_integer():
            return "corrupted"
        return "corrupted" if abs(f) >= 1e15 else "ok"
    s = str(v).strip()
    if s.lower() in {"", "nan", "none"}:
        return "missing"
    if _ID_21.fullmatch(s):
        return "ok"
    if s.endswith(".0") and s[:-2].isdigit():
        return "ok"  # 整数写成浮点但未丢位（仅 <=15 位可精确表示）
    if "e+" in s.lower() or "e-" in s.lower():
        return "corrupted"
    return "other"


def id_text(v) -> str:
    """21 位审批编号必须当文本。已经变成 float 的**不伪造**恢复，原样转字符串。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, int):
        return str(v)
    s = str(v).strip()
    if s.lower() in {"", "nan", "none"}:
        return ""
    if "e+" in s.lower() or "e-" in s.lower():
        # 浮点科学计数法已丢精度，禁止 f"{int(float(s))}" 伪恢复成 21 位。
        return s
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def read_dingtalk_xlsx_records(path: Path) -> tuple[pd.DataFrame, dict]:
    """读 aflow/钉钉导出，**保留**缺日期行并逐条记录 sheet 级失败。

    返回 ``(df, report)``：

    - ``df`` 含所有有「账期日期」表头 sheet 的数据行；**缺日期/非法日期的行也保留**
      （D01 要求读取阶段不得丢有金额行），由调用方按 ``账期月`` 分区。
    - ``report`` 含 ``sheets`` / ``failed``（无表头、缺日期列、读取异常的 sheet，
      逐条带原因和行数）/ ``rows_failed`` / ``corrupted_ids``。
    """
    xp = pd.ExcelFile(path)
    frames: list[pd.DataFrame] = []
    failed: list[dict] = []
    corrupted: list[dict] = []
    for sn in xp.sheet_names:
        try:
            hdr = xp.parse(sn, header=None, nrows=8)
        except Exception as exc:  # noqa: BLE001 - 读不到就是失败，逐条保留
            failed.append(
                {"sheet": sn, "reason": f"parse_error:{type(exc).__name__}", "rows": _sheet_row_count(xp, sn)}
            )
            continue
        hr_i = None
        for i in range(min(8, len(hdr))):
            row = [str(x).strip() if pd.notna(x) else "" for x in hdr.iloc[i]]
            if "账期日期" in row:
                hr_i = i
                break
        if hr_i is None:
            rows = _sheet_row_count(xp, sn)
            if rows:
                failed.append({"sheet": sn, "reason": "no_header(无『账期日期』表头)", "rows": rows})
            continue
        try:
            df = xp.parse(sn, header=hr_i)
        except Exception as exc:  # noqa: BLE001
            failed.append(
                {"sheet": sn, "reason": f"parse_error:{type(exc).__name__}", "rows": _sheet_row_count(xp, sn)}
            )
            continue
        if "账期日期" not in df.columns:
            rows = int(df.dropna(how="all").shape[0]) if not df.empty else 0
            if rows:
                failed.append({"sheet": sn, "reason": "missing_date_column", "rows": rows})
            continue
        df = df.dropna(how="all").copy()
        if df.empty:
            continue
        df["_sheet"] = sn
        if "审批编号" in df.columns:
            for i, v in df["审批编号"].items():
                if id_status(v) == "corrupted":
                    corrupted.append({"sheet": sn, "row": int(i) + 2, "value": str(v)})
        frames.append(df)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    report = {
        "sheets": list(xp.sheet_names),
        "failed": failed,
        "rows_failed": int(sum(f["rows"] for f in failed)),
        "corrupted_ids": corrupted,
        "corrupted_id_rows": len(corrupted),
    }
    return out, report


def _sheet_row_count(xp: pd.ExcelFile, sheet: str) -> int:
    """失败 sheet 的行数（非空行，含标题行）——用于 N→M 的「读取失败」计数。"""
    try:
        raw = xp.parse(sheet, header=None)
        return int(raw.dropna(how="all").shape[0])
    except Exception:  # noqa: BLE001
        return 0


def read_dingtalk_xlsx(path: Path) -> pd.DataFrame:
    """向后兼容入口：只返回有日期的行。新的守恒路径请用 ``read_dingtalk_xlsx_records``。"""
    df, _report = read_dingtalk_xlsx_records(path)
    if df.empty:
        return df
    return df[df["账期日期"].notna()].copy()


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


def norm_amount(v) -> str:
    """金额规范化。Excel 读进来可能是 int / float / str，`0` 与 `0.0` 必须归一到同一个键。"""
    s = "" if v is None else str(v).strip()
    if s.lower() in {"", "nan", "none"}:
        return ""
    try:
        d = Decimal(s).normalize()
    except (InvalidOperation, ValueError):
        return s
    try:
        if d == d.to_integral_value():
            return str(d.quantize(Decimal(1)))
    except InvalidOperation:
        return s
    return format(d, "f")


def norm_date(v) -> str:
    d = pd.to_datetime(v, errors="coerce")
    return d.strftime("%Y-%m-%d") if pd.notna(d) else ""


def build_key(pid, period_date, account, amount) -> str:
    """迟交挪动登记唯一键：`审批编号|账期日期|销售账户|销售额`。

    登记表侧和导出侧**必须**调同一个函数，否则金额/日期写法差一点就会静默漏剔除。
    """
    return "|".join([id_text(pid), norm_date(period_date), str(account or "").strip(), norm_amount(amount)])


def pick_amount(r) -> str:
    """唯一键里的金额口径：销售额优先，其次应收账款 / 应收金额。空单元格视为缺失。"""
    for col in ("销售额", "应收账款", "应收金额"):
        v = r.get(col)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        s = str(v).strip()
        if s and s.lower() not in {"nan", "none"}:
            return v
    return ""


def unique_key(r: pd.Series) -> str:
    """迟交挪动登记唯一键：审批编号|账期日期|销售账户|销售额。"""
    acct = str(r.get("销售账户_展开") or "").strip()
    if not acct:
        acct, _ = flatten_sale_account(r)
    return build_key(r.get("审批编号", ""), r.get("账期日期"), acct, pick_amount(r))


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
