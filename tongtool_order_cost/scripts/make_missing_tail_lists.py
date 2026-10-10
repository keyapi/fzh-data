#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成「待追尾程清单」——把某月所有「还没拿到真实账单」的包裹整理成**一个** Excel 给运营（WXP）。

输入：EN「上传通途订单Excel」产出的成品
      「EN上传Cost Review预估尾程 只用尾程 通途非FBA订单YYYYMM <ts>.xlsx」

口径（与 docs/reference/monthly-tail-cost-pipeline.md 一致）：
  分母只看「是否需要尾程=1」；缺口 = needs=1 且「物流商运费=0」（即还没拿到真实账单）。

输出一个工作簿（多 sheet）：
  - 汇总        按「账单来源/供应商」统计：包裹数 / 行数 / 预估合计 / 说明
  - 明细        逐包裹，含 包裹号/订单号/跟踪号/渠道/通途SKU/日期/预估 + 备注（可直接给 WXP）
  - 无需追      平台付尾程（OSTK/Wayfair）等——默认不追，但保留不丢

按「邮寄方式」链（如 `M6180蜴国际>>M6180蜴国际-Fedex`）判定账单来源：
  蜴国际（货代）· GLS 波兰 · 「7条」尾程供应商 · CENTRADE · 疑似官方 FedEx · 平台付尾程（OSTK/Wayfair）

只读输入、不改源文件。用法见 --help。
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import pandas as pd

_REISSUE_RE = re.compile(r"-M\d+$", re.IGNORECASE)

# —— 账单来源判定（按序，子串匹配「邮寄方式」链；OSTK 必须排在通用 FedEx 之前）——
SUPPLIER_RULES = [
    ("蜴国际", "蜴国际 FedEx（货代）", "高", "货代账单，找蜴国际/YIGlobal 要"),
    ("GLS", "GLS 波兰", "高", "GLS 账单/后台下载"),
    ("7条", "「7条」尾程供应商", "中", "美国尾程供应商「7条」结算"),
    ("CENTRADE", "CENTRADE", "中", "Centrade 结算"),
    ("OSTK", "平台付尾程（OSTK/Wayfair）", "不追", "疑似平台付尾程；确认后可不追"),
]

DETAIL_COLS = [
    "序号", "账单来源", "优先级", "包裹号", "跟踪号", "发货日期", "发货时间",
    "发货方式", "邮寄方式", "渠道", "渠道账号", "通途SKU", "平台SKU",
    "订单号", "发货数量", "历史预估尾程费用", "是否补发", "备注",
]


def is_reissue(row: pd.Series) -> bool:
    """补发单：是否补发货=是 或 订单号以 -M<数字> 结尾。"""
    flag = str(row.get("是否补发货", "")).strip()
    if flag in ("是", "1", "True", "true"):
        return True
    return bool(_REISSUE_RE.search(str(row.get("订单号", ""))))


def classify(chain: str, reissue: bool = False) -> tuple[str, str, str]:
    """返回 (账单来源, 优先级, 说明)。"""
    s = str(chain)
    for kw, name, prio, note in SUPPLIER_RULES:
        if kw in s:
            # OSTK/Wayfair 常态是平台付→不追；但**补发单**可能用自有尾程 → 需追（待确认）
            if kw == "OSTK" and reissue:
                return "平台渠道补发（需确认尾程）", "待确认", "补发货→可能用自有尾程，需确认是否追"
            return name, prio, note
    low = s.lower()
    if "fedex" in low:
        return "疑似官方 FedEx（待确认）", "待确认", "可能是公司自有 FedEx 账号 → FedEx Billing Online"
    return "其他（待确认）", "待确认", "未知来源，需人工确认"


def _tracking(row: pd.Series) -> str:
    for col in ("跟踪号", "虚拟跟踪号", "物流商单号"):
        v = row.get(col)
        if v is not None and str(v).strip() and str(v).strip().lower() != "nan":
            return str(v).strip()
    return ""


def _note(row: pd.Series, estimate, supplier: str, reissue: bool) -> str:
    notes = []
    if reissue:
        notes.append("补发单→若用自有尾程需追")
    if supplier.startswith("平台付"):
        notes.append("疑似平台付尾程，确认后可不追")
    if not _tracking(row):
        notes.append("无跟踪号→按 账号+日期+目的地 反查")
    if estimate is None or float(estimate or 0) == 0:
        notes.append("无预估（重量/成本缺失）")
    return "；".join(notes)


def build_rows(miss: pd.DataFrame) -> pd.DataFrame:
    if len(miss) == 0:
        return pd.DataFrame(columns=DETAIL_COLS)
    rows = []
    for parcel, g in miss.groupby("包裹号", sort=False):
        first = g.iloc[0]
        re_ = bool(g.apply(is_reissue, axis=1).any())
        supplier, prio, _ = classify(first.get("邮寄方式", ""), re_)
        est = round(float(g["历史预估尾程费用"].fillna(0).sum()), 2) if g["历史预估尾程费用"].notna().any() else None
        rows.append({
            "账单来源": supplier,
            "优先级": prio,
            "包裹号": parcel,
            "跟踪号": _tracking(first),
            "发货日期": first.get("发货日期", ""),
            "发货时间": first.get("发货时间", ""),
            "发货方式": first.get("发货方式", ""),
            "邮寄方式": first.get("邮寄方式", ""),
            "渠道": first.get("渠道", ""),
            "渠道账号": first.get("渠道账号", ""),
            "通途SKU": " / ".join(sorted({str(x) for x in g["通途SKU"].dropna().astype(str)})),
            "平台SKU": " / ".join(sorted({str(x) for x in g["平台SKU"].dropna().astype(str)})),
            "订单号": " / ".join(sorted({str(x) for x in g["订单号"].dropna().astype(str)})),
            "发货数量": int(g["发货数量"].fillna(0).sum()) if "发货数量" in g else "",
            "历史预估尾程费用": est,
            "是否补发": "是" if re_ else "",
            "备注": _note(first, est, supplier, re_),
        })
    out = pd.DataFrame(rows)
    # 排序：优先级(自定义) → 账单来源 → 发货日期 → 发货时间 → 包裹号
    prio_order = {"高": 0, "中": 1, "待确认": 2, "不追": 3}
    out["_p"] = out["优先级"].map(prio_order).fillna(9)
    out = out.sort_values(["_p", "账单来源", "发货日期", "发货时间", "包裹号"]).drop(columns="_p").reset_index(drop=True)
    out.insert(0, "序号", range(1, len(out) + 1))
    return out[DETAIL_COLS]


def _write_sheet(w, df: pd.DataFrame, name: str, freeze="A2"):
    df.to_excel(w, index=False, sheet_name=name)
    ws = w.sheets[name]
    ws.freeze_panes = freeze
    widths = {"序号": 5, "账单来源": 26, "优先级": 8, "包裹号": 20, "跟踪号": 20,
              "发货日期": 11, "发货时间": 9, "发货方式": 16, "邮寄方式": 30,
              "渠道": 12, "渠道账号": 16, "通途SKU": 22, "平台SKU": 22,
              "订单号": 30, "发货数量": 9, "历史预估尾程费用": 15, "是否补发": 8, "备注": 40}
    for i, c in enumerate(df.columns, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = widths.get(c, 14)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成「待追尾程清单」单一工作簿（给 WXP）")
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

    allrows = build_rows(miss)
    # 拆：待追（非「不追」） / 无需追（平台付·非补发）
    no_chase = allrows[allrows["优先级"] == "不追"].copy()
    to_chase = allrows[allrows["优先级"] != "不追"].reset_index(drop=True)
    to_chase["序号"] = range(1, len(to_chase) + 1)
    to_chase = to_chase[DETAIL_COLS]
    no_chase = no_chase.reset_index(drop=True)
    no_chase["序号"] = range(1, len(no_chase) + 1)
    no_chase = no_chase[DETAIL_COLS]

    # 汇总
    summ = []
    for supplier, g in to_chase.groupby("账单来源", sort=False):
        prio = g["优先级"].iloc[0]
        est = g["历史预估尾程费用"].dropna()
        summ.append({"账单来源": supplier, "优先级": prio, "包裹数": len(g),
                     "预估合计": round(float(est.sum()), 2) if len(est) else None})
    summ_df = pd.DataFrame(summ)
    prio_order = {"高": 0, "中": 1, "待确认": 2}
    summ_df["_p"] = summ_df["优先级"].map(prio_order).fillna(9)
    summ_df = summ_df.sort_values(["_p", "包裹数"]).drop(columns="_p")
    # 追加总计
    tot_est = to_chase["历史预估尾程费用"].dropna()
    summ_df.loc[len(summ_df)] = {"账单来源": "合计（待追）", "优先级": "",
                                 "包裹数": len(to_chase),
                                 "预估合计": round(float(tot_est.sum()), 2) if len(tot_est) else None}

    path = out / f"{args.month} 待追尾程清单 给WXP {stamp}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        _write_sheet(w, summ_df, "汇总")
        _write_sheet(w, to_chase, "明细")
        if len(no_chase):
            _write_sheet(w, no_chase, "无需追-平台付(待确认)")

    print(f"  -> {path.name}")
    print(summ_df.to_string(index=False))
    # 缺口对账：待追 + 无需追 = 全部
    print(f"  对账：待追 {len(to_chase)} + 无需追 {len(no_chase)} = {len(allrows)} 包裹")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
