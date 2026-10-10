#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成「待追尾程清单」——按承运商/货代拆分给运营（WXP）与物流商对账。

输入：EN「上传通途订单Excel」产出的成品
      「EN上传Cost Review预估尾程 只用尾程 通途非FBA订单YYYYMM <ts>.xlsx」

口径（与 docs/reference/monthly-tail-cost-pipeline.md 一致）：
  分母只看「是否需要尾程=1」；缺口 = needs=1 且「物流商运费=0」（即还没拿到真实账单）。

本脚本额外按「谁出账单」把缺口拆两类，分别落一个 xlsx：
  1) 官方 FedEx（自有账号：US-FedEx / FEDEX Economy TX）→ 黄总/WXP 去 FedEx 官网下载账单
  2) 蜴国际 FedEx（M6180蜴国际-Fedex）→ 找货代（YIGlobal）要账单

只读输入、不改源文件；输出到 --out 目录。用法见 --help。
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

import pandas as pd

# 「邮寄方式」列存的是完整承运链（如 "US-FedEx>>OSTK-FedEx"）→ 用子串判定。
# 蜴国际 FedEx（货代 YIGlobal）：链含此关键字
FORWARDER_FEDEX_KEYWORD = "蜴国际"
# 官方 FedEx 自有账号：链含 FedEx 且不是货代
OFFICIAL_FEDEX_KEYWORD = "fedex"

LIST_COLS = [
    "序号", "包裹号", "跟踪号", "发货日期", "发货时间",
    "发货方式", "邮寄方式", "渠道", "渠道账号",
    "通途SKU", "订单号", "历史预估尾程费用",
]


def _tracking(row: pd.Series) -> str:
    for col in ("跟踪号", "虚拟跟踪号", "物流商单号"):
        v = row.get(col)
        if v is not None and str(v).strip() and str(v).strip().lower() != "nan":
            return str(v).strip()
    return ""


def build_package_rows(miss: pd.DataFrame) -> pd.DataFrame:
    """按包裹号聚合（一包裹可能多行 → 预估求和；其余取首值）。"""
    if len(miss) == 0:
        return pd.DataFrame(columns=LIST_COLS)
    rows = []
    for parcel, g in miss.groupby("包裹号", sort=False):
        first = g.iloc[0]
        rows.append({
            "包裹号": parcel,
            "跟踪号": _tracking(first),
            "发货日期": first.get("发货日期", ""),
            "发货时间": first.get("发货时间", ""),
            "发货方式": first.get("发货方式", ""),
            "邮寄方式": first.get("邮寄方式", ""),
            "渠道": first.get("渠道", ""),
            "渠道账号": first.get("渠道账号", ""),
            "通途SKU": " / ".join(sorted({str(x) for x in g["通途SKU"].dropna().astype(str)})),
            "订单号": " / ".join(sorted({str(x) for x in g["订单号"].dropna().astype(str)})),
            "历史预估尾程费用": round(float(g["历史预估尾程费用"].fillna(0).sum()), 2),
        })
    out = pd.DataFrame(rows)
    # 排序：发货方式 → 邮寄方式 → 发货日期 → 发货时间 → 包裹号
    out = out.sort_values(["发货方式", "邮寄方式", "发货日期", "发货时间", "包裹号"]).reset_index(drop=True)
    out.insert(0, "序号", range(1, len(out) + 1))
    return out[LIST_COLS]


def _write(df: pd.DataFrame, path: Path, note: str) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="待追尾程")
        ws = w.sheets["待追尾程"]
        ws.freeze_panes = "A2"
        # 列宽
        widths = {"序号": 5, "包裹号": 22, "跟踪号": 22, "发货日期": 11, "发货时间": 9,
                  "发货方式": 16, "邮寄方式": 26, "渠道": 12, "渠道账号": 18,
                  "通途SKU": 24, "订单号": 20, "历史预估尾程费用": 14}
        for i, c in enumerate(df.columns, start=1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = widths.get(c, 14)
    print(f"  -> {path.name}  ({len(df)} 行)  {note}")


def main() -> int:
    ap = argparse.ArgumentParser(description="生成待追尾程清单（官方 FedEx / 蜴国际 FedEx）")
    ap.add_argument("--en-xlsx", required=True, help="EN 上传产出：EN上传Cost Review预估尾程 …YYYYMM <ts>.xlsx")
    ap.add_argument("--month", required=True, help="YYYYMM")
    ap.add_argument("--out", default=".", help="输出目录")
    ap.add_argument("--stamp", default=None, help="文件名时间戳（默认今天 YYYYMMDD）")
    args = ap.parse_args()

    stamp = args.stamp or dt.date.today().strftime("%Y%m%d")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(args.en_xlsx)
    req = ["是否需要尾程", "物流商运费", "发货方式", "邮寄方式", "包裹号", "历史预估尾程费用"]
    missing = [c for c in req if c not in df.columns]
    if missing:
        print(f"缺列：{missing}", file=sys.stderr)
        return 2

    n1 = df[df["是否需要尾程"] == 1]
    miss = n1[n1["物流商运费"].fillna(0) == 0].copy()
    print(f"needs=1: {len(n1)} 行 | 缺口(物流商运费=0): {len(miss)} 行 / {miss['包裹号'].nunique()} 包裹")

    mailing = miss["邮寄方式"].astype(str)
    is_forwarder = mailing.str.contains(FORWARDER_FEDEX_KEYWORD, na=False)
    is_official = mailing.str.contains(OFFICIAL_FEDEX_KEYWORD, case=False, na=False) & ~is_forwarder

    off = build_package_rows(miss[is_official])
    fwd = build_package_rows(miss[is_forwarder])

    if len(off):
        p = out / f"{args.month} 待追尾程-官方FedEx（自有账号） 给黄总WXP {stamp}.xlsx"
        _write(off, p, f"预估合计 {off['历史预估尾程费用'].sum():.2f}")
    else:
        print("  (官方 FedEx 无缺口)")

    if len(fwd):
        p = out / f"{args.month} 待追尾程-蜴国际FedEx（货代） 给物流商 {stamp}.xlsx"
        _write(fwd, p, f"预估合计 {fwd['历史预估尾程费用'].sum():.2f}")
    else:
        print("  (蜴国际 FedEx 无缺口)")

    # 其余缺口（GLS / CENTRADE 等）也报一下，便于运营心里有数
    rest = miss[~is_official & ~is_forwarder]
    if len(rest):
        g = rest.groupby("邮寄方式").agg(包裹=("包裹号", "nunique"), 预估=("历史预估尾程费用", "sum")).sort_values("包裹", ascending=False)
        print("其余缺口（非 FedEx 两类，仅提示）:")
        print(g.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
