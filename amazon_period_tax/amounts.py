# -*- coding: utf-8 -*-
"""金额解析（严格版）：空值 → None；非空非法/Inf → 报错；小数/千分位按**声明格式**处理。

背景（见 reports/gate_audit_20261120.md R04/O06）：旧实现有三套口径 —
txt 用 ``float(str.replace(",", "."))``（``1,234`` 变 1.234）、OA/Tax/附加费用
``to_numeric(errors="coerce").fillna(0)``（非空文本静默变 0）、verify 另有一套。
这里统一成一个可声明的解析器：

- 空单元格（``None``/``NaN``/``pd.NA``/``""``/``"nan"`` 等哨兵）→ ``None``，由调用方决定
  该列是否允许空（费用列允许空，另有显式门禁）。
- 非空但非法（``abc``/``Inf``/``NaN`` 字符串/歧义逗号）→ ``ValueError``，不再静默变 0。
- 默认 ``decimal_separator="."``：``1,234`` = 1234；``1,5`` 这类既可能是小数逗号也可能是
  千分位写错的写法 → 抛错（表格数据不猜区域格式）。
- ``decimal_separator="auto"``（Amazon 结算 txt 用）：按**单元格**判定——``1,234`` = 1234
  （任务口径），恰好两位小数的 ``0,04``/``109,24`` 按小数逗号解析，其余含逗号写法报错。
  实测同一份欧洲站 txt 里 ``0,04`` 与 ``-16.64`` 会混着出现，所以不能按文件一刀切。
"""
from __future__ import annotations

import decimal
import math
import numbers
import re
import unicodedata
from typing import Iterable

import pandas as pd

# 空值哨兵：pandas 旧版本 astype(str) 会把 NA 变成这些字符串，不能只判 ""。
BLANK_TOKENS = frozenset({"", "nan", "none", "<na>", "nat", "null"})

# 点小数 + 逗号千分位：1,234 / 1,234.56 / -12,345.6
_THOUSANDS_DOT = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")
# 普通数值（允许科学计数）
_PLAIN = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
# 小数逗号且恰好两位小数：0,04 / 109,24 / -1234,50（Amazon 欧洲站导出）
_COMMA_DEC2 = re.compile(r"^[+-]?\d+,\d{2}$")


def is_blank_value(value) -> bool:
    """单值判空：NA/NaT/空串/``nan``/``None``/``<NA>`` 等哨兵都算空。"""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().lower() in BLANK_TOKENS
    return False


def is_blank(series: pd.Series) -> pd.Series:
    """列判空：``isna()`` 或 strip 后命中哨兵列表（O04 漏 NaN 的直接修法）。"""
    s = series if isinstance(series, pd.Series) else pd.Series(series)
    try:
        stripped = s.astype(str).str.strip().str.lower()
        sentinel = stripped.isin(BLANK_TOKENS)
    except Exception:  # pragma: no cover - 非标量列（list 等）走 isna
        sentinel = pd.Series(False, index=s.index)
    return s.isna() | sentinel


def infer_decimal_format(values: Iterable) -> str:
    """统计一批原始金额里出现过的写法（用于报告/追溯，不做解析决策）。

    返回 ``+`` 连接的标签，如 ``comma`` / ``dot`` / ``thousands`` / ``comma+dot``。
    实测 Amazon 欧洲站同一份 txt 会混用：绝大多数行 ``0,04``（小数逗号），
    「Base fee / Tax on fee」几行却是 ``-16.64``（点小数），所以**不能按文件一刀切**。
    """
    kinds: set[str] = set()
    for value in values:
        if isinstance(value, str):
            s = unicodedata.normalize("NFKC", value).strip()
            if is_blank_value(s):
                continue
            if "," in s:
                if _THOUSANDS_DOT.match(s):
                    kinds.add("thousands")
                elif _COMMA_DEC2.match(s):
                    kinds.add("comma")
                else:
                    kinds.add("ambiguous")
            elif "." in s:
                kinds.add("dot")
            else:
                kinds.add("int")
        elif isinstance(value, numbers.Real) and not isinstance(value, bool):
            kinds.add("dot")
    return "+".join(sorted(kinds))


def parse_amount_strict(value, *, decimal_separator: str = ".") -> float | None:
    """严格金额解析：空 → ``None``；非空非法/Inf → ``ValueError``。

    ``decimal_separator``：
    - ``"."``（默认，OA/表格式数据）：``1,234`` = 1234；``1,5``/``1,23`` 这类含逗号但
      不符合千分位的写法一律报错（表格不是 Amazon 导出，不猜区域格式）。
    - ``"auto"``（Amazon 结算 txt）：按**单元格**判定——``1,234`` 千分位；
      恰好两位小数的 ``0,04`` 是小数逗号；其余含逗号写法（``1,5``/``1,2345``）报错。
    """
    if is_blank_value(value):
        return None
    if isinstance(value, bool):
        raise ValueError("布尔值不是金额")
    if isinstance(value, decimal.Decimal):
        if not value.is_finite():
            raise ValueError(f"金额非有限值: {value!r}")
        return float(value)
    if isinstance(value, numbers.Real):
        f = float(value)
        if not math.isfinite(f):
            raise ValueError(f"金额非有限值: {value!r}")
        return f
    if not isinstance(value, str):
        raise ValueError(f"不支持的金额类型 {type(value).__name__}: {value!r}")

    s = unicodedata.normalize("NFKC", str(value)).strip()
    if s == "":
        return None
    if decimal_separator == ".":
        if "," in s:
            if not _THOUSANDS_DOT.match(s):
                # 例：1,5（小数逗号？千分位写错？）；1,23；1,2,3
                raise ValueError(f"含逗号但不符合千分位格式，区域格式歧义: {value!r}")
            s = s.replace(",", "")
    elif decimal_separator == "auto":
        if "," in s:
            if _THOUSANDS_DOT.match(s):
                s = s.replace(",", "")
            elif _COMMA_DEC2.match(s):
                s = s.replace(",", ".")
            else:
                raise ValueError(f"逗号写法歧义（既非千分位也非两位小数逗号）: {value!r}")
    else:
        raise ValueError(f"未知 decimal_separator={decimal_separator!r}")

    if not _PLAIN.match(s):
        raise ValueError(f"金额非法: {value!r}")
    try:
        f = float(s)
    except ValueError:  # pragma: no cover - 正则已挡住
        raise ValueError(f"金额非法: {value!r}") from None
    if not math.isfinite(f):
        raise ValueError(f"金额非有限值: {value!r}")
    return f


def parse_amounts_frame(
    df: pd.DataFrame,
    columns: Iterable[str],
    *,
    label: str,
    row_key: str = "审批编号",
    decimal_separator: str = ".",
) -> dict[str, pd.Series]:
    """按列严格解析，聚合所有失败后一次性抛错（带行号/行键，便于定位）。

    返回 ``{列名: float Series}``（空单元格为 NaN，由调用方 fillna(0)）。
    """
    cols = [c for c in columns if c in df.columns]
    parsed: dict[str, pd.Series] = {}
    problems: list[str] = []
    keys = df[row_key] if row_key in df.columns else None
    for col in cols:
        vals: list[float | None] = []
        for pos, (idx, raw) in enumerate(zip(df.index, df[col])):
            try:
                vals.append(parse_amount_strict(raw, decimal_separator=decimal_separator))
            except ValueError as e:
                key = keys.iloc[pos] if keys is not None else idx
                where = f"行{pos + 2}" + (f"({row_key}={key})" if keys is not None else "")
                problems.append(f"{col} {where} 原值={raw!r}: {e}")
                vals.append(None)
        parsed[col] = pd.Series(vals, index=df.index, dtype="float64")
    if problems:
        head = "; ".join(problems[:10])
        more = f"（另有 {len(problems) - 10} 处）" if len(problems) > 10 else ""
        raise ValueError(f"{label} 金额解析失败 {len(problems)} 处: {head}{more}")
    return parsed
