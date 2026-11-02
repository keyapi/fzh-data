"""48 个「可补单—待定量」键的 97/157 天数量原型（只读）。

口径（用户 2026-10-28）
- 视界：L+R = 90+7 = 97 天（正常）/ 150+7 = 157 天（春节）；**不把旧 35/60 天参考量按比例放大**
- 需求：真实预测曲线积分（forecast-20261027-r4 → run-2026-10-26-r6 的 27 个周桶）
  - 周桶无法精确切到第 97/157 天 → 按项目既定做法取「桶结束 ≥ 目标」的第一个桶，
    实际覆盖 **98 / 161 天**，逐行标明；**不插值**
- 已承诺未履约 SO：本批 48 个键的 so_pipeline_qty 全为 0，无可加/需去重的 SO
- IP = 10-28 同仓已证可发 + 已证未到货（proven_receipts=0）；未证在途/PO/SO 不抵扣
- S = 需求 + SS；SS = 档位系数 × z(服务水平) × σ_daily × √H，
  仅在存在误差链（σ_daily>0）时应用；否则 SS=0 并标「未应用政策」
  - 档位策略（用户口径）：A 1.5×/95%、B 1.0×/90%、C 1.0×/85%
- Q = max(0, S - IP)，分别给 97（98 天桶界）与 157（161 天桶界）
- 最晚下单日 = 首次缺口起始 − 提前期（P50 / 规划上值），到仓日按 10/29 下单口径

只读：只读本地文件与 DuckDB（read_only），不写 EN/通途，不 push。
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

# 用户口径的 A/B/C 档：系数 / 服务水平
TIER_POLICY = {"A": (1.5, 0.95), "B": (1.0, 0.90), "C": (1.0, 0.85)}

# 路由提前期（leadtime_config v2026-10-28.2）：P50=生产20+发运11.5+海运35/40（ceil）；规划=50+20+35/40
ROUTE_LEAD = {
    "美东-CENTRADE": {"p50": 67, "plan": 105, "ocean": 35},
    "美中-FZH-DANEEY": {"p50": 67, "plan": 105, "ocean": 35},
    "波兰-FZHPoland-covers": {"p50": 72, "plan": 110, "ocean": 40},
}


def norm_inv(sl: float) -> float:
    """标准正态分位（Acklam 近似，与 pack._z 同量级）。"""
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
    """从 as_of 起累计桶需求，取「桶结束 ≥ anchor + target」的第一个桶（不插值）。

    anchor = 下单日（2026-10-29）：保证覆盖 ≥ L+R 天；起点含 as_of..下单日的 3 天
    （桶无法拆分，宁可多算不少算）。
    """
    import json as _json

    manifest = _json.loads((run_dir / "supply_netting_manifest.json").read_text(encoding="utf-8"))
    as_of = datetime.fromisoformat(manifest["as_of"]).date()
    target_date = anchor + timedelta(days=target_days)
    buckets = sorted(manifest["buckets"], key=lambda b: b["end"])
    chosen_end = None
    ids = []
    for b in buckets:
        ids.append(b["bucket_id"])
        end = datetime.fromisoformat(b["end"])
        if end.date() >= target_date:
            chosen_end = end
            break
    return {
        "bucket_ids": ids,
        "end": chosen_end.strftime("%Y-%m-%d") if chosen_end else "",
        "target_date": (anchor + timedelta(days=target_days)).isoformat(),
        "actual_days_from_order": (chosen_end.date() - anchor).days if chosen_end else None,
        "covered_from": as_of.isoformat(),
        "as_of": as_of.isoformat(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classify", default="D:/Work/fzh-order-store/analysis/53补单逐键分类_2026-10-28_v3.csv")
    ap.add_argument("--run", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/run-2026-10-26-r6")
    ap.add_argument("--pack", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/pack-2026-10-29-h180/conditional_decision_pack.csv")
    ap.add_argument("--stock", default="D:/Work/fzh-order-store/en_stock.parquet")
    ap.add_argument("--db", default="D:/Work/fzh-order-store/order_store.duckdb")
    ap.add_argument("--sku-class", default="D:/Work/fzh-order-store/analysis/sku_classification_20261027.csv")
    ap.add_argument("--out", default="D:/Work/fzh-order-store/analysis/48待定量_97_157_原型_2026-10-28.csv")
    args = ap.parse_args()

    run_dir = Path(args.run)
    classify = pd.read_csv(args.classify, encoding="utf-8-sig")
    keys = classify[classify["分类"].astype(str).str.startswith("可补单—待定量")].copy()
    keys["首次缺口起始"] = keys["首次缺口周"].astype(str).str[:10]

    pack = pd.read_csv(args.pack, encoding="utf-8-sig")
    pack = pack.rename(columns={"canonical_sku": "SKU", "canonical_warehouse": "仓库", "canonical_uom": "单位"})
    keys = keys.merge(
        pack[["SKU", "仓库", "单位", "tier", "sigma_daily", "proven_receipts", "so_pipeline_qty", "opening"]],
        on=["SKU", "仓库"], how="left", suffixes=("", "_pack"),
    )

    netting = pd.read_parquet(run_dir / "supply_netting.parquet")
    netting = netting[netting["scenario"] == "expected"].copy()

    win97 = bucket_window(run_dir, TARGETS["97"], ORDER_DAY)
    win157 = bucket_window(run_dir, TARGETS["157"], ORDER_DAY)

    def cumulative(sku: str, warehouse: str, ids: list[str]) -> float | None:
        rows = netting[(netting["canonical_sku"] == sku)
                       & (netting["canonical_warehouse"] == warehouse)
                       & (netting["bucket_id"].isin(ids))]
        if not len(rows):
            return None
        return float(rows["period_demand"].sum())

    # 分型标注（多别名时保守标注）
    con = duckdb.connect(args.db, read_only=True)
    pairs = con.execute("select upper(sku) sku, upper(item_code) item from sku_item").df()
    reverse: dict[str, set[str]] = {}
    for _, row in pairs.iterrows():
        reverse.setdefault(row["item"], set()).add(row["sku"])
    sku_class = pd.read_csv(args.sku_class, encoding="utf-8-sig")
    sku_class["sku"] = sku_class["sku"].astype(str).str.upper()
    class_map = sku_class.set_index("sku")

    out_rows = []
    for _, row in keys.iterrows():
        sku, wh = row["SKU"], row["仓库"]
        uom = row.get("单位") or row.get("单位_pack")
        d97 = cumulative(sku, wh, win97["bucket_ids"])
        d157 = cumulative(sku, wh, win157["bucket_ids"])

        ip = float(row["当前可发(10-28同仓)"] or 0) + float(row.get("proven_receipts") or 0)
        intransit_unverified = float(row.get("同仓在途(10-28)") or 0)

        tier = row.get("tier")
        sigma = row.get("sigma_daily")
        sigma = float(sigma) if pd.notna(sigma) else 0.0
        policy_applied = sigma > 0 and tier in TIER_POLICY
        if policy_applied:
            factor, sl = TIER_POLICY[tier]
            z = norm_inv(sl)
            ss97 = factor * z * sigma * math.sqrt(TARGETS["97"])
            ss157 = factor * z * sigma * math.sqrt(TARGETS["157"])
            policy_note = f"{tier} {factor}×/SL{sl:.0%}，σ={sigma:.3f}"
        else:
            ss97 = ss157 = 0.0
            policy_note = "未应用政策（无误差链 σ=0 或缺档）"

        s97 = (d97 or 0) + ss97
        s157 = (d157 or 0) + ss157
        q97 = max(0.0, s97 - ip)
        q157 = max(0.0, s157 - ip)

        lead = ROUTE_LEAD.get(wh, None)
        gap_start = row["首次缺口起始"]
        latest_p50 = latest_plan = ""
        if lead and gap_start:
            g = datetime.strptime(gap_start, "%Y-%m-%d").date()
            latest_p50 = (g - timedelta(days=lead["p50"])).isoformat()
            latest_plan = (g - timedelta(days=lead["plan"])).isoformat()

        # 分型标注
        mapped = sorted(reverse.get(str(sku).upper(), set()))
        types = {class_map.loc[m, "历史分型"] for m in mapped if m in class_map.index}
        recent = {class_map.loc[m, "近6月分型"] for m in mapped if m in class_map.index}
        type_note = "；".join(sorted(t for t in types if isinstance(t, str))) or "无分型数据"
        if len({t for t in types if isinstance(t, str)}) > 1:
            type_note = "多别名不一致(" + type_note + ")"
        recent_note = "；".join(sorted(r for r in recent if isinstance(r, str))) or "无"

        # 充分度
        missing = [name for name, val in (("需求曲线", d97 if d97 is not None else None),
                                          ("157 曲线", d157 if d157 is not None else None),
                                          ("IP", None if pd.isna(ip) else ip)) if val is None]
        if missing:
            sufficiency, reason = "不足", "缺：" + "、".join(missing)
        elif (d97 or 0) < 1 or (d157 or 0) < 1:
            sufficiency = "部分"
            reason = "预测曲线近零（98/161 天需求 <1），Q≈0 需人工复核是否真要补"
        else:
            sufficiency, reason = "可算", ""

        passed_p50 = bool(latest_p50) and datetime.strptime(latest_p50, "%Y-%m-%d").date() < AS_OF
        passed_plan = bool(latest_plan) and datetime.strptime(latest_plan, "%Y-%m-%d").date() < AS_OF

        out_rows.append({
            "SKU": sku, "仓库": wh, "单位": uom,
            "分类": row["分类"], "首次缺口周": row["首次缺口周"], "首次缺口起始": gap_start,
            "旧35天参考量": row["旧35天参考量"], "当前可发_10-28同仓": row["当前可发(10-28同仓)"],
            "同仓在途_未证": intransit_unverified, "已证未到货": float(row.get("proven_receipts") or 0),
            "IP_已证": round(ip, 3),
            "需求曲线": "forecast-20261027-r4 / run-2026-10-26-r6（27 周桶）",
            "需求_97天目标_实际98天": None if d97 is None else round(d97, 3),
            "需求_157天目标_实际161天": None if d157 is None else round(d157, 3),
            "覆盖目标日_97": win97["target_date"], "覆盖目标日_157": win157["target_date"],
            "实际覆盖天数_97_从下单日": win97["actual_days_from_order"],
            "实际覆盖天数_157_从下单日": win157["actual_days_from_order"],
            "桶界_97": win97["end"], "桶界_157": win157["end"],
            "覆盖口径": "周桶界：97 目标→实际覆盖 102 天、157 目标→158 天（不插值）",
            "档位": tier, "sigma_daily": round(sigma, 4),
            "安全库存政策": policy_note,
            "SS_97目标": round(ss97, 3), "SS_157目标": round(ss157, 3),
            "S_97目标": round(s97, 3), "S_157目标": round(s157, 3),
            "Q_97目标": round(q97, 3), "Q_157目标": round(q157, 3),
            "提前期P50_天": lead["p50"] if lead else "", "提前期规划_天": lead["plan"] if lead else "",
            "最晚下单日_P50": latest_p50, "最晚下单日_规划": latest_plan,
            "10-29下单到仓_P50": row.get("10/29下单P50到仓"),
            "10-29下单到仓_规划": row.get("10/29下单规划(P90)到仓"),
            "新单是否晚于首次缺口": row.get("新单是否晚于首次缺口"),
            "最晚下单日_P50已过": "是" if passed_p50 else "否",
            "最晚下单日_规划已过": "是" if passed_plan else "否",
            "断货_清仓标注": type_note + " / 近6月:" + recent_note,
            "数据充分度": sufficiency, "原因": reason,
            "备注": "需求为周桶积分（98/161 天桶界），非精确第 97/157 天；SO 管线为 0，未加 SO",
        })

    out = pd.DataFrame(out_rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False, encoding="utf-8-sig")

    summary = {
        "rows": len(out),
        "window_97": win97, "window_157": win157,
        "sufficiency": out["数据充分度"].value_counts().to_dict(),
        "policy_applied": int((out["安全库存政策"].astype(str).str.startswith(("A", "B", "C"))).sum()),
        "policy_not_applied": int(out["安全库存政策"].astype(str).str.startswith("未应用").sum()),
        "latest_order_p50_passed": int((out["最晚下单日_P50已过"] == "是").sum()),
        "latest_order_plan_passed": int((out["最晚下单日_规划已过"] == "是").sum()),
        "q97_positive": int((out["Q_97目标"] > 0).sum()),
        "q157_positive": int((out["Q_157目标"] > 0).sum()),
        "q97_sum": float(out["Q_97目标"].fillna(0).sum()),
        "q157_sum": float(out["Q_157目标"].fillna(0).sum()),
        "old35_sum": float(out["旧35天参考量"].fillna(0).sum()),
        "demand_sum_target97_bucket": float(out["需求_97天目标_实际98天"].fillna(0).sum()),
        "demand_sum_target157_bucket": float(out["需求_157天目标_实际161天"].fillna(0).sum()),
        "output": args.out,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
