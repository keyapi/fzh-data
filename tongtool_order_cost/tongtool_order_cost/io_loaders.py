# -*- coding: utf-8 -*-
"""订单 / 规则 / 汇率加载。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .engine_170 import COEFF_COLS, REF_COLS


def _read_csv_flexible(path: Path) -> pd.DataFrame:
    with open(path, "rb") as f:
        first = f.readline()
    sep = "\t" if b"\t" in first else ","
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            return pd.read_csv(path, sep=sep, dtype=str, low_memory=False, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, sep=sep, dtype=str, low_memory=False)


def load_orders(path: Path | str, account: str | None = None) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = _read_csv_flexible(path)
    if account and "渠道账号" in df.columns:
        df = df[df["渠道账号"].astype(str).str.strip() == account].copy()
    if "渠道账号不含国家" not in df.columns and "渠道账号" in df.columns:
        df["渠道账号不含国家"] = df["渠道账号"].astype(str).str.strip().str[:-2]
    return df.reset_index(drop=True)


def load_rules(path: Path | str) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = _read_csv_flexible(path)
    if "发货数量1订单尾程运费" not in df.columns and "订单尾程运费" in df.columns:
        df = df.rename(columns={"订单尾程运费": "发货数量1订单尾程运费"})
    for col in COEFF_COLS + REF_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = float("nan")
    if "收款币种" in df.columns:
        df["收款币种"] = df["收款币种"].astype(str).str.strip()
        df.loc[df["收款币种"].isin(("", "nan", "None", "NaT")), "收款币种"] = ""
    else:
        df["收款币种"] = ""
    # 保留原始 Excel 行号（表头=1 → 数据行从 2 起）
    df = df.copy()
    df["excel_row"] = df.index + 2
    return df


def load_fx_table(
    fx_file: Path | str | None = None,
    fx_usd: float | None = None,
    orders: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, str]:
    """返回 (收款币种,汇率) 表 + 来源说明。"""
    if fx_file is not None:
        path = Path(fx_file)
        if path.suffix.lower() in (".xlsx", ".xls"):
            fx = pd.read_excel(path)
        else:
            fx = _read_csv_flexible(path)
        cols = list(fx.columns)
        cur_col = "收款币种" if "收款币种" in cols else cols[0]
        rate_col = "汇率" if "汇率" in cols else cols[1]
        out = fx[[cur_col, rate_col]].rename(
            columns={cur_col: "收款币种", rate_col: "汇率"}
        )
        out["收款币种"] = out["收款币种"].astype(str).str.strip()
        out["汇率"] = pd.to_numeric(out["汇率"], errors="coerce")
        out = out.dropna(subset=["汇率"])
        if "RMB" not in set(out["收款币种"]):
            out = pd.concat(
                [out, pd.DataFrame([{"收款币种": "RMB", "汇率": 1.0}])],
                ignore_index=True,
            )
        return out, f"fx-file:{path.name}"

    if fx_usd is not None:
        return (
            pd.DataFrame(
                [
                    {"收款币种": "USD", "汇率": float(fx_usd)},
                    {"收款币种": "RMB", "汇率": 1.0},
                ]
            ),
            f"fx-usd:{fx_usd}",
        )

    if orders is not None and "汇率" in orders.columns:
        rates = pd.to_numeric(orders["汇率"], errors="coerce").dropna()
        if len(rates):
            mode = float(rates.mode().iloc[0])
            return (
                pd.DataFrame(
                    [
                        {"收款币种": "USD", "汇率": mode},
                        {"收款币种": "RMB", "汇率": 1.0},
                    ]
                ),
                f"orders-汇率众数:{mode}",
            )

    return pd.DataFrame(columns=["收款币种", "汇率"]), "none"
