"""48 个「可补单—待定量」键的 97/157 天数量原型 v2（只读，纯口径修正）。

v2 修正（对应 48key-97-157-review-2026-10-28 的 F1–F5，**不改任何数量**）：
- F1 需求盲区：run manifest `forecast.gap_from_as_of_days=2.779`；
  桶时间轴从 10-26 起、预测从 10-29 起，**10-26→10-29 有 2.779 天无需求数据、未估算**，
  不再说「已含 3 天/宁可多算」。
- F2 σ 口径：σ 是**近 90 天历史销量 std（历史销量波动代理）**，不是预测误差链；
  SS 标「政策情景，服务水平未校准」；40 行 SS=0 写「未应用销量波动代理/缺σ」。
- F3 近零分窗口：97 目标 8 行 Q<1；157 目标只有 3 行 Q<1，另 5 行为 1.28–1.52。
- F4 表头/备注 98/161 → **102/158**（从 10-29 起算；桶起点另有盲区）。
- F5 汇总按**全精度**求和后再舍入（Q157=662.26、波兰 Q157=249.23），
  并注明 CSV 三位小数逐行相加会有 0.00x 差异。

输入/公式与 v1 相同；只读，不写 EN/通途，不 push。
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

AS_OF = date(2026, 10, 28)
ORDER_DAY = date(2026, 10, 29)
TARGETS = {"97": 97, "157": 157}
TIER_POLICY = {"A": (1.5, 0.95), "B": (1.0, 0.90), "C": (1.0, 0.85)}
ROUTE_LEAD = {
    "美东-CENTRADE": {"p50": 67, "plan": 105},
    "美中-FZH-DANEEY": {"p50": 67, "plan": 105},
    "波兰-FZHPoland-covers": {"p50": 72, "plan": 110},
}
SS_LABEL = "政策情景（历史销量波动代理 σ=近90天 std；服务水平未校准）"


def norm_inv(sl: float) -> float:
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    plow, phigh = 0.02425, 1 - 0.02425
    if sl < plow:
        q = math.sqrt(-2 * math.log(sl))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if sl > phigh:
        q = math.sqrt(-2 * math.log(1 - sl))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = sl - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def bucket_window(run_dir: Path, target_days: int, anchor: date) -> dict:
    manifest = json.loads((run_dir / "supply_netting_manifest.json").read_text(encoding="utf-8"))
    as_of = datetime.fromisoformat(manifest["as_of"]).date()
    target_date = anchor + timedelta(days=target_days)
    buckets = sorted(manifest["buckets"], key=lambda b: b["end"])
    ids = []
    chosen_end = None
    for b in buckets:
        ids.append(b["bucket_id"])
        end = datetime.fromisoformat(b["end"])
        if end.date() >= target_date:
            chosen_end = end
            break
    gap = manifest.get("forecast", {}).get("gap_from_as_of_days")
    return {
        "bucket_ids": ids,
        "end": chosen_end.strftime("%Y-%m-%d") if chosen_end else "",
        "target_date": target_date.isoformat(),
        "actual_days_from_order": (chosen_end.date() - anchor).days if chosen_end else None,
        "covered_from": as_of.isoformat(),
        "forecast_window_start": manifest.get("forecast", {}).get("window_start"),
        "gap_from_as_of_days": gap,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classify", default="D:/Work/fzh-order-store/analysis/53补单逐键分类_2026-10-28_v3.csv")
    ap.add_argument("--run", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/run-2026-10-26-r6")
    ap.add_argument("--pack", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/pack-2026-10-29-h180/conditional_decision_pack.csv")
    ap.add_argument("--db", default="D:/Work/fzh-order-store/order_store.duckdb")
    ap.add_argument("--sku-class", default="D:/Work/fzh-order-store/analysis/sku_classification_20261027.csv")
    ap.add_argument("--out", default="D:/Work/fzh-order-store/analysis/48待定量_97_157_原型_2026-10-28_v2.csv")
    args = ap.parse_args()

    run_dir = Path(args.run)
    classify = pd.read_csv(args.classify, encoding="utf-8-sig")
    keys = classify[classify["分类"].astype(str).str.startswith("可补单—待定量")].copy()
    keys["首次缺口起始"] = keys["首次缺口周"].astype(str).str[:10]

    pack = pd.read_csv(args.pack, encoding="utf-8-sig").rename(
        columns={"canonical_sku": "SKU", "canonical_warehouse": "仓库", "canonical_uom": "单位"})
    keys = keys.merge(
        pack[["SKU", "仓库", "单位", "tier", "sigma_daily", "proven_receipts", "so_pipeline_qty"]],
        on=["SKU", "仓库"], how="left", suffixes=("", "_pack"))

    netting = pd.read_parquet(run_dir / "supply_netting.parquet")
    netting = netting[netting["scenario"] == "expected"].copy()

    win97 = bucket_window(run_dir, TARGETS["97"], ORDER_DAY)
    win157 = bucket_window(run_dir, TARGETS["157"], ORDER_DAY)
    gap_days = win97["gap_from_as_of_days"]

    def cumulative(sku: str, wh: str, ids: list[str]) -> float | None:
        rows = netting[(netting["canonical_sku"] == sku) & (netting["canonical_warehouse"] == wh)
                       & (netting["bucket_id"].isin(ids))]
        return float(rows["period_demand"].sum()) if len(rows) else None

    con = duckdb.connect(args.db, read_only=True)
    pairs = con.execute("select upper(sku) sku, upper(item_code) item from sku_item").df()
    reverse: dict[str, set[str]] = {}
    for _, row in pairs.iterrows():
        reverse.setdefault(row["item"], set()).add(row["sku"])
    sku_class = pd.read_csv(args.sku_class, encoding="utf-8-sig")
    sku_class["sku"] = sku_class["sku"].astype(str).str.upper()
    class_map = sku_class.set_index("sku")

    coverage_text = (
        f"预测窗口 {win97['forecast_window_start']} 起；桶时间轴从 {win97['covered_from']} 起，"
        f"{win97['covered_from']}→{win97['forecast_window_start']} 有 {gap_days} 天需求盲区（未估算、未填 0）；"
        f"97 目标实际覆盖 {win97['actual_days_from_order']} 天、157 目标 {win157['actual_days_from_order']} 天（从 10-29 起算）"
    )

    rows, raw = [], []
    for _, row in keys.iterrows():
        sku, wh = row["SKU"], row["仓库"]
        uom = row.get("单位") or row.get("单位_pack")
        d97 = cumulative(sku, wh, win97["bucket_ids"])
        d157 = cumulative(sku, wh, win157["bucket_ids"])
        ip = float(row["当前可发(10-28同仓)"] or 0) + float(row.get("proven_receipts") or 0)

        tier = row.get("tier")
        sigma = float(row["sigma_daily"]) if pd.notna(row.get("sigma_daily")) else 0.0
        applied = sigma > 0 and tier in TIER_POLICY
        if applied:
            factor, sl = TIER_POLICY[tier]
            z = norm_inv(sl)
            ss97 = factor * z * sigma * math.sqrt(TARGETS["97"])
            ss157 = factor * z * sigma * math.sqrt(TARGETS["157"])
            policy = f"应用：{tier} {factor}×/{sl:.0%}；{SS_LABEL}"
        else:
            ss97 = ss157 = 0.0
            policy = "未应用销量波动代理/缺σ（SS=0）"

        s97 = (d97 or 0) + ss97
        s157 = (d157 or 0) + ss157
        q97 = max(0.0, s97 - ip)
        q157 = max(0.0, s157 - ip)

        lead = ROUTE_LEAD.get(wh)
        gap_start = row["首次缺口起始"]
        latest_p50 = latest_plan = ""
        if lead and gap_start:
            g = datetime.strptime(gap_start, "%Y-%m-%d").date()
            latest_p50 = (g - timedelta(days=lead["p50"])).isoformat()
            latest_plan = (g - timedelta(days=lead["plan"])).isoformat()

        mapped = sorted(reverse.get(str(sku).upper(), set()))
        types = {class_map.loc[m, "历史分型"] for m in mapped if m in class_map.index}
        recent = {class_map.loc[m, "近6月分型"] for m in mapped if m in class_map.index}
        type_note = "；".join(sorted(t for t in types if isinstance(t, str))) or "无分型数据"
        if len({t for t in types if isinstance(t, str)}) > 1:
            type_note = "多别名不一致(" + type_note + ")"
        recent_note = "；".join(sorted(r for r in recent if isinstance(r, str))) or "无"

        low97 = q97 < 1
        low157 = q157 < 1
        if low97 and low157:
            sufficiency = "部分"
            reason = "97/157 两目标 Q<1（预测近零），应观察/复核，不按小数件下单"
        elif low97 and not low157:
            sufficiency = "部分"
            reason = f"97 目标 Q<1（{q97:.2f}），但 157 目标 Q={q157:.2f}（>1），需人工复核口径"
        elif (d97 or 0) is None or (d157 or 0) is None:
            sufficiency, reason = "不足", "缺需求曲线"
        else:
            sufficiency, reason = "可算", ""

        passed_p50 = bool(latest_p50) and datetime.strptime(latest_p50, "%Y-%m-%d").date() < AS_OF

        rows.append({
            "SKU": sku, "仓库": wh, "单位": uom,
            "分类": row["分类"], "首次缺口周": row["首次缺口周"], "首次缺口起始": gap_start,
            "旧35天参考量": row["旧35天参考量"], "当前可发_10-28同仓": row["当前可发(10-28同仓)"],
            "同仓在途_未证": row.get("同仓在途(10-28)"), "已证未到货": float(row.get("proven_receipts") or 0),
            "IP_已证": round(ip, 3),
            "需求曲线": "forecast-20261027-r4 / run-2026-10-26-r6（27 周桶）",
            "需求_97目标_102天": None if d97 is None else round(d97, 3),
            "需求_157目标_158天": None if d157 is None else round(d157, 3),
            "覆盖目标日_97": win97["target_date"], "覆盖目标日_157": win157["target_date"],
            "实际覆盖天数_97_从下单日": win97["actual_days_from_order"],
            "实际覆盖天数_157_从下单日": win157["actual_days_from_order"],
            "桶界_97": win97["end"], "桶界_157": win157["end"],
            "覆盖口径": coverage_text,
            "档位": tier, "sigma_daily": round(sigma, 4), "安全库存政策": policy,
            "SS_97目标": round(ss97, 3), "SS_157目标": round(ss157, 3),
            "S_97目标": round(s97, 3), "S_157目标": round(s157, 3),
            "Q_97目标": round(q97, 3), "Q_157目标": round(q157, 3),
            "Q<1_97": "是" if low97 else "否", "Q<1_157": "是" if low157 else "否",
            "提前期P50_天": lead["p50"] if lead else "", "提前期规划_天": lead["plan"] if lead else "",
            "最晚下单日_P50": latest_p50, "最晚下单日_规划": latest_plan,
            "10-29下单到仓_P50": row.get("10/29下单P50到仓"),
            "10-29下单到仓_规划": row.get("10/29下单规划(P90)到仓"),
            "新单是否晚于首次缺口": row.get("新单是否晚于首次缺口"),
            "最晚下单日_P50已过": "是" if passed_p50 else "否",
            "最晚下单日_规划已过": "是" if (latest_plan and datetime.strptime(latest_plan, "%Y-%m-%d").date() < AS_OF) else "否",
            "断货_清仓标注": type_note + " / 近6月:" + recent_note,
            "数据充分度": sufficiency, "原因": reason,
            "备注": "需求=周桶积分（覆盖 102/158 天，从 10-29 起算）；10-26→10-29 为 2.779 天需求盲区未估算；"
                    "SO 管线 0；IP 只认已证",
        })
        raw.append({"仓库": wh, "d97": d97 or 0.0, "d157": d157 or 0.0, "ss97": ss97, "ss157": ss157,
                    "s97": s97, "s157": s157, "q97": q97, "q157": q157, "ip": ip,
                    "old": float(row["旧35天参考量"] or 0)})

    out = pd.DataFrame(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False, encoding="utf-8-sig")

    # F5：全精度求和后再舍入
    raws = pd.DataFrame(raw)

    def tot(col):
        return round(float(raws[col].sum()), 2)

    by_wh = {
        wh: {k: round(float(g[k].sum()), 2) for k in ("d97", "d157", "ss97", "ss157", "q97", "q157", "old")}
        for wh, g in raws.groupby("仓库")
    }
    summary = {
        "rows": len(out),
        "window_97": {k: v for k, v in win97.items() if k != "bucket_ids"},
        "window_157": {k: v for k, v in win157.items() if k != "bucket_ids"},
        "coverage_text": coverage_text,
        "sufficiency": out["数据充分度"].value_counts().to_dict(),
        "policy_applied": int(out["安全库存政策"].astype(str).str.startswith("应用").sum()),
        "policy_not_applied": int(out["安全库存政策"].astype(str).str.startswith("未应用").sum()),
        "latest_order_p50_passed": int((out["最晚下单日_P50已过"] == "是").sum()),
        "latest_order_plan_passed": int((out["最晚下单日_规划已过"] == "是").sum()),
        "q97_lt1_rows": int((out["Q<1_97"] == "是").sum()),
        "q157_lt1_rows": int((out["Q<1_157"] == "是").sum()),
        "q97_lt1_skus": out.loc[out["Q<1_97"] == "是", "SKU"].tolist(),
        "q157_lt1_skus": out.loc[out["Q<1_157"] == "是", "SKU"].tolist(),
        "totals_full_precision": {"d97": tot("d97"), "d157": tot("d157"), "ss97": tot("ss97"),
                                  "ss157": tot("ss157"), "q97": tot("q97"), "q157": tot("q157"),
                                  "old35": tot("old")},
        "totals_by_warehouse": by_wh,
        "rounding_note": "总数按全精度求和后保留 2 位；CSV 逐行是 3 位小数，逐行相加与总数会差 0.00x"
                         "（如 Q97 441.815 vs 441.82；Q157 662.252 vs 662.26）",
        "output": args.out,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
