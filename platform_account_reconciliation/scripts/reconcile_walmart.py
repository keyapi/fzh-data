#!/usr/bin/env python3
"""Walmart 账期 vs EN/Tongtool Order 订单级 + 费用级勾稽。

数据源：
  赛狐 `queryStatementDetail` 导出的账期行（probe_walmart_settlement.py --pull-period 落盘）
  EN 生产 ERPNext `Tongtool Order` 只读 REST

用法:
  uv run python platform_account_reconciliation/scripts/reconcile_walmart.py \
      --sellfox-json "out/sellfox_walmart_probe/period_598030_*.json" \
      --out "out/sellfox_walmart_probe/Walmart账期勾稽.xlsx"

为什么要跨账期合并看：Walmart 是双周账期，赛狐按 periodStart/End 分账期，
而 EN 的订单只是一条。同一 PO 的销售行与后续退货/费用行可能落在相邻账期，
按单账期聚合去比 EN 必然错位。
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform_account_reconciliation" / "scripts"))
from reconcile_ostkus import EN_BASE, en_headers, load_en_credentials, num  # noqa: E402

TO_PATH = "/api/resource/Tongtool Order"
TOL = 0.01


def load_sellfox_rows(patterns: list[str]) -> pd.DataFrame:
    records: list[dict] = []
    for pattern in patterns:
        for path_str in sorted(glob.glob(pattern)):
            path = Path(path_str)
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("rows") if isinstance(payload, dict) else payload
            for r in rows or []:
                records.append({
                    "账期期初": r.get("periodStartDate"),
                    "账期期末": r.get("periodEndDate"),
                    "结算时间": r.get("transactionPostedDate"),
                    "订单号": str(r.get("purchaseOrder") or ""),
                    "MSKU": r.get("partnerItemId"),
                    "GTIN": r.get("partnerGtin"),
                    "数量": num(r.get("shipQty")),
                    "交易类型": r.get("transactionType"),
                    "费用类型": r.get("amountType"),
                    "费用描述": r.get("transactionDescription"),
                    "金额": num(r.get("amount")),
                    "币种": r.get("currency"),
                    "配送类型": r.get("fulfillmentType"),
                    "_source": path.name,
                })
            print(f"  {path.name}: {len(rows or [])} 行")
    df = pd.DataFrame(records)
    if df.empty:
        raise SystemExit("没有读到任何赛狐结算行，检查 --sellfox-json 路径")
    return df


def fetch_en(pos: list[str], headers: dict[str, str]) -> pd.DataFrame:
    fields = [
        "name", "platform_code", "platform_order_id", "sale_account", "order_status",
        "sale_time", "order_amount", "products_total_price", "actual_total_price",
        "platform_fee", "shipping_fee", "gross_profit", "total_item_cost", "match_status",
    ]
    out: list[dict] = []
    for i in range(0, len(pos), 100):
        batch = pos[i:i + 100]
        resp = requests.get(
            f"{EN_BASE}{TO_PATH}",
            headers=headers,
            params={
                "filters": json.dumps([["Tongtool Order", "platform_order_id", "in", batch]]),
                "fields": json.dumps(fields),
                "limit_page_length": "200",
            },
            timeout=60,
        )
        if resp.status_code != 200:
            raise SystemExit(f"EN 查询失败 http={resp.status_code} {resp.text[:200]}")
        out += resp.json().get("data") or []
    return pd.DataFrame(out)


def classify(sf_amount: float, en_amount: float, has_sale_row: bool, sf_negative: bool) -> str:
    if abs(sf_amount - en_amount) <= TOL:
        return "一致"
    if not has_sale_row:
        return "本期无销售行(跨期)"
    if sf_negative:
        return "本期为退货"
    return "金额不一致"


def build(df: pd.DataFrame, en: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (订单级勾稽表, 账期总览表)。

    平台费口径（2026-09-21 实测确认，64/64 命中）：
        赛狐 Commission on Product = (商品价 + Total Walmart Funded Savings) × 15%
        EN   platform_fee          =  商品价 × 15%
    差额 = 沃尔玛补贴 × 15% —— 即 **EN 的 platform_fee 少算了补贴基数**，赛狐是对的。
    """
    # 销售行：Sale 交易 + Product Price
    sale = df[(df["费用类型"] == "Product Price") & (df["交易类型"] == "Sale")]
    sale_by_po = sale.groupby("订单号")["金额"].sum()
    sale_period = (
        sale.groupby("订单号")
        .agg(销售账期期初=("账期期初", "first"), 销售账期期末=("账期期末", "first"))
    )
    comm_by_po = (
        df[df["费用类型"] == "Commission on Product"]
        .groupby("订单号")["金额"].sum()
        .abs()
    )
    subs_by_po = df[df["费用类型"] == "Total Walmart Funded Savings"].groupby("订单号")["金额"].sum()

    en_amt = {}
    en_fee = {}
    en_meta = {}
    for _, row in en.iterrows():
        po = row["platform_order_id"]
        en_amt[po] = num(row.get("products_total_price") or row.get("order_amount"))
        en_fee[po] = num(row.get("platform_fee"))
        en_meta[po] = row

    records = []
    for po in sorted(set(df["订单号"]) - {""}):
        sf_amt = float(sale_by_po.get(po, 0.0))
        sf_fee = float(comm_by_po.get(po, 0.0))
        sf_sub = float(subs_by_po.get(po, 0.0))
        e_amt = en_amt.get(po)
        e_fee = en_fee.get(po)
        meta = en_meta.get(po)
        has_sale = po in sale_by_po.index

        # 口径差：扣除「补贴×15%」后，赛狐佣金应与 EN 平台费一致
        fee_residual = None
        fee_verdict = ""
        if e_fee is not None and has_sale and sf_amt > 0:
            fee_residual = round(sf_fee - e_fee - sf_sub * 0.15, 2)
            if sf_fee == 0:
                fee_verdict = "佣金已退货冲平(EN未冲)"
            elif abs(fee_residual) <= TOL:
                fee_verdict = "口径一致(差=补贴×15%)"
            else:
                fee_verdict = "口径异常"

        records.append({
            "订单号": po,
            "销售账期": (f"{sale_period.loc[po, '销售账期期初']}~{sale_period.loc[po, '销售账期期末']}"
                     if po in sale_period.index else ""),
            "EN单据": meta.get("name") if meta is not None else "",
            "EN状态": meta.get("order_status") if meta is not None else "",
            "EN销售时间": meta.get("sale_time") if meta is not None else "",
            "赛狐销售额": round(sf_amt, 2),
            "EN商品额": None if e_amt is None else round(e_amt, 2),
            "销售额差异": None if e_amt is None else round(sf_amt - e_amt, 2),
            "沃尔玛补贴": round(sf_sub, 2),
            "赛狐佣金": round(sf_fee, 2),
            "EN平台费": None if e_fee is None else round(e_fee, 2),
            "平台费差异": None if e_fee is None else round(sf_fee - e_fee, 2),
            "口径残差": fee_residual,
            "平台费判定": fee_verdict,
            "判定": "EN未匹配" if e_amt is None
                    else classify(sf_amt, e_amt, has_sale, sf_amt < 0),
        })
    order_df = pd.DataFrame(records)

    # 账期总览：按“销售账期”归口，避免跨期错位
    periods = sorted(df["账期期初"].dropna().unique())
    overview = []
    for ps in periods:
        pe = df.loc[df["账期期初"] == ps, "账期期末"].iloc[0]
        sub = df[df["账期期初"] == ps]
        pos_in = set(order_df.loc[order_df["销售账期"].str.startswith(str(ps)), "订单号"])
        en_sub = en[en["platform_order_id"].isin(pos_in)] if pos_in else en.iloc[0:0]
        overview.append({
            "账期期初": ps,
            "账期期末": pe,
            "结算行数": len(sub),
            "涉及订单": sub["订单号"].nunique(),
            "本期销售单": len(pos_in),
            "赛狐销售额": round(sub.loc[(sub["费用类型"] == "Product Price") &
                                    (sub["交易类型"] == "Sale"), "金额"].sum(), 2),
            "EN商品额": round(sum(num(v.get("products_total_price") or v.get("order_amount"))
                              for _, v in en_sub.iterrows()), 2),
            "赛狐佣金": round(abs(sub.loc[sub["费用类型"] == "Commission on Product", "金额"].sum()), 2),
            "EN平台费": round(sum(num(v.get("platform_fee")) for _, v in en_sub.iterrows()), 2),
        })
    return order_df, pd.DataFrame(overview)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sellfox-json", action="append", required=True,
                    help="赛狐账期行 JSON（可多次传，支持 glob）")
    ap.add_argument("--out", help="输出 xlsx 路径")
    ap.add_argument("--no-en", action="store_true", help="只出赛狐侧，不调 EN")
    args = ap.parse_args()

    print("[1] 读赛狐账期行")
    df = load_sellfox_rows(args.sellfox_json)
    print(f"  合计 {len(df)} 行 / {df['订单号'].nunique()} 单 / {df['账期期初'].nunique()} 个账期")

    if args.no_en:
        print("\n[2] --no-en，跳过 EN")
        return

    key, secret = load_en_credentials()
    if not key:
        raise SystemExit("EN 凭证缺失（EN_API/.env）")
    print("\n[2] 拉 EN Tongtool Order")
    en = fetch_en(sorted(df["订单号"].unique().tolist()), en_headers(key, secret))
    print(f"  EN 命中 {en['platform_order_id'].nunique() if not en.empty else 0} 单")

    order_df, overview = build(df, en)

    print("\n[3] 账期总览")
    print(overview.to_string(index=False))

    print("\n[4] 订单级判定分布")
    print(order_df["判定"].value_counts().to_string())

    matched = order_df[order_df["判定"] != "EN未匹配"]
    ok_amt = matched[matched["销售额差异"].abs() <= TOL]
    print(f"\n  销售额精确一致: {len(ok_amt)}/{len(matched)}")
    if not ok_amt.empty:
        print("\n  平台费口径判定（销售额已一致的单）：")
        print(ok_amt["平台费判定"].value_counts().to_string())
        bad = ok_amt[ok_amt["平台费判定"] == "口径异常"]
        if not bad.empty:
            print(f"\n  ★ 口径异常（{len(bad)} 单）：")
            print(bad[["订单号", "赛狐销售额", "沃尔玛补贴", "赛狐佣金", "EN平台费",
                       "平台费差异", "口径残差"]].to_string(index=False))
        else:
            print("\n  ✓ 无口径异常 —— 所有销售额一致的单，平台费差都被"
                  "「沃尔玛补贴 × 15%」完全解释")

    bad_amt = matched[matched["销售额差异"].abs() > TOL]
    if not bad_amt.empty:
        print(f"\n  ★ 销售额不一致（{len(bad_amt)} 单）：")
        print(bad_amt[["订单号", "销售账期", "赛狐销售额", "EN商品额", "销售额差异", "判定"]]
              .to_string(index=False))

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(out, engine="openpyxl") as w:
            overview.to_excel(w, sheet_name="账期总览", index=False)
            order_df.to_excel(w, sheet_name="订单级勾稽", index=False)
            (df.groupby(["账期期初", "费用类型"])["金额"].sum().unstack(fill_value=0)
               .round(2).to_excel(w, sheet_name="账期费用分类"))
            df.to_excel(w, sheet_name="账期明细", index=False)
        print(f"\n[5] 已写出 {out}")


if __name__ == "__main__":
    main()
