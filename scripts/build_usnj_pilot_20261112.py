# -*- coding: utf-8 -*-
"""USNJ 补货试点包（P2c）：B 归属清单 + USNJ 补货建议 + 特殊产品 + CNY。

只读消费 D6 v6.24 / D3b v3.11 / 订单序列；不重算供给，不写 EN/通途。
输出给运营负责人 Jing 直接用的 xlsx/csv + 说明。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

B = "D:/Work/fzh-order-store"
BA = f"{B}/analysis"
KEYS = ["product_id", "pool", "physical_form", "canonical_uom"]
AS_OF = date(2026, 11, 11)
CNY_STOP = date(2027, 1, 24)
CNY_RESUME = date(2027, 2, 22)
CNY_FIRST_RECEIPT = date(2027, 5, 4)   # 中国线：复工 + 71.5 天
WALL = ("KS0211-KJB-60-BEIGE", "KS0211-KJB-90-BEIGE",
        "KS0211-KJB-90-DEEPGREY", "KS0211-DM-60-DEEPGREY")

METHOD_NOTE = {
    "naive": "最近一期销量直接外推",
    "ma3": "近 3 月均值",
    "snaive": "去年同月外推（季节基线）",
    "ets_ann": "水平平滑（ETS）",
    "ets_aadn": "水平+阻尼趋势平滑（ETS）",
    "ets_aaa": "趋势+季节平滑（ETS/STL）",
    "theta": "趋势+平滑（Theta）",
    "croston": "间歇需求（Croston）",
    "sba": "间歇需求（SBA，偏差校正）",
    "tsb": "间歇/淘汰（TSB）",
    "ensemble": "多模型平均",
    "none": "无可靠模型",
}


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _read_d3b(path):
    audit = pd.read_excel(path, sheet_name="10_责任重述审计")
    cls = pd.read_excel(path, sheet_name="3_分类")
    res = pd.read_excel(path, sheet_name="4_回测_asof")
    return audit, cls, res


def build_b_list(audit: pd.DataFrame, trend: pd.DataFrame,
                 meta: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    a = audit.copy()
    a["current_owner"] = a["current_owner"].fillna("US_unassigned").astype(str)
    a["current_pool"] = a["current_pool"].fillna("US_unassigned").astype(str)
    tr = trend.copy()
    for c in ("2025", "2026"):
        tr[c] = pd.to_numeric(tr[c], errors="coerce").fillna(0.0)
    tot = tr.groupby("product_id")[["2025", "2026"]].sum().rename(
        columns={"2025": "2025总销量", "2026": "2026总销量"})
    usnj = (tr[tr["pool"].astype(str) == "美东USNJ"].groupby("product_id")[["2025", "2026"]]
            .sum().rename(columns={"2025": "2025USNJ销量", "2026": "2026USNJ销量"}))
    a = a.merge(tot, left_on="product_id", right_index=True, how="left")
    a = a.merge(usnj, left_on="product_id", right_index=True, how="left")
    m = meta.drop_duplicates("product_id")[["product_id", "name", "item_group"]]
    a = a.merge(m, on="product_id", how="left")
    a["name"] = a["name"].fillna(a["product_id"])
    a["item_group"] = a["item_group"].fillna("")
    parts = a["product_id"].astype(str).str.split("-")
    a["family"] = parts.str[0]
    a["fabric"] = parts.str[1].fillna("")
    a["面料"] = a["name"].astype(str).str.split("-").str[1].fillna(a["fabric"])
    a["家族"] = a["family"]
    for c in ("2025总销量", "2026总销量", "2025USNJ销量", "2026USNJ销量"):
        a[c] = a[c].fillna(0.0)

    def _flag(r):
        tags = []
        if bool(r.exception_current_USNJ_hist_USTX):
            tags.append("错")
        if bool(r.both_pools):
            tags.append("多")
        if float(r.moved_qty or 0) > 0 or int(r.current_key_count or 0) == 0:
            tags.append("待确认")
        return "；".join(dict.fromkeys(tags)) or "正常"

    a["标记"] = [_flag(r) for r in a.itertuples(index=False)]
    a["证据"] = [
        f"hist={r.hist_pools}; USNJ={r.hist_qty_USNJ:.0f}; USTX={r.hist_qty_USTX:.0f}; "
        f"moved={r.moved_qty:.0f} {r.direction}"
        for r in a.itertuples(index=False)]
    a["Jing勾选"] = ""
    a["Jing备注"] = ""
    b = a[a["current_pool"] == "美东USNJ"].copy()
    pending = a[(a["current_pool"] == "US_unassigned")
                | (a["exception_current_USNJ_hist_USTX"])].copy()
    pending["标记"] = np.where(pending["current_pool"] == "US_unassigned", "漏", pending["标记"])
    b = b.sort_values(["标记", "2026总销量"], ascending=[True, False])
    pending = pending.sort_values("unassigned_qty", ascending=False)
    return b, pending


def load_sales(series_path: str) -> pd.DataFrame:
    s = pd.read_parquet(series_path)
    s["month"] = s["month"].astype(str)
    s = s[(s["pool"].astype(str) == "美东USNJ") & (s["month"] <= "202610")]
    for c in KEYS:
        s[c] = s[c].astype(str)
    s30 = (s[s["month"] == "202610"].groupby(KEYS)["qty"].sum()
           .rename("近30天销量_202610"))
    s90 = (s[s["month"].isin(["202608", "202609", "202610"])].groupby(KEYS)["qty"].sum()
           .rename("近90天销量_202608_10"))
    return pd.concat([s30, s90], axis=1).reset_index()


def build_wape_index(res: pd.DataFrame) -> dict:
    """只取 4_回测_asof 的 model 层（汇总），origin 明细绝不覆盖。

    键 = 源键 + model + split；同键重复直接报错，不静默覆盖。
    """
    keys = ["product_id", "pool", "physical_form", "canonical_uom", "model", "split"]
    r = res[res["层级"].astype(str) == "model"].copy()
    if r.duplicated(keys).any():
        raise ValueError("4_回测_asof model 层同键重复，拒绝回填")
    return {(str(x.product_id), str(x.pool), str(x.physical_form),
             str(x.canonical_uom), str(x.model), str(x.split)): x.wape
            for x in r.itertuples(index=False)}


def build_pilot(d6: pd.DataFrame, b: pd.DataFrame, sales: pd.DataFrame,
                cls: pd.DataFrame, res: pd.DataFrame,
                meta: pd.DataFrame) -> pd.DataFrame:
    us = d6[d6["池"].astype(str) == "美东USNJ"].copy()
    us = us.rename(columns={"池": "pool", "形态": "physical_form", "UOM": "canonical_uom"})
    for c in KEYS:
        us[c] = us[c].astype(str)
    ev = b[["product_id", "current_owner", "hist_pools", "moved_qty", "direction",
            "both_pools", "exception_current_USNJ_hist_USTX", "标记", "name",
            "item_group", "family", "fabric", "2025总销量", "2026总销量",
            "2025USNJ销量", "2026USNJ销量"]].copy()
    us = us.merge(ev, on="product_id", how="left")
    us = us.merge(sales, on=KEYS, how="left")
    for c in ("近30天销量_202610", "近90天销量_202608_10"):
        us[c] = us[c].fillna(0.0)
    cl = cls[KEYS + ["n_obs_train", "demand_pattern_train",
                     "adopted_model", "adopted_sources"]].copy()
    for c in KEYS:
        cl[c] = cl[c].astype(str)
    us = us.merge(cl, on=KEYS, how="left")
    # 每个模型的 validation/holdout WAPE：只取 model 层汇总，origin 明细不覆盖
    wape_idx = build_wape_index(res)
    us["name"] = us["name"].fillna(us["product_id"])
    us["item_group"] = us["item_group"].fillna("")
    us["model"] = us["采用模型"].fillna(us["D5模型"]).fillna(us["adopted_model"])
    us["模型一句话"] = us["model"].map(METHOD_NOTE).fillna(METHOD_NOTE["none"])
    us["算法说明"] = us["模型一句话"]
    us["short_hist"] = ((pd.to_numeric(us["n_obs_train"], errors="coerce") < 12)
                        | us["需求形态"].astype(str).isin(["new", "short"]))
    us["is_triangle"] = us["item_group"].astype(str).str.contains("三角", na=False)
    us["is_low_conf"] = (
        us["short_hist"]
        | us["item_group"].astype(str).isin(["麻将沙发衍生款", "麻将沙发优化款", "主体骨架"])
        | us["product_id"].astype(str).str.startswith(("ZTGJ5525", "KS0319", "KS0385",
                                                       "KS0443", "KS0454"))
        | us["name"].astype(str).str.contains("印花", na=False))
    us.loc[us["is_low_conf"], "算法说明"] = (
        "沿用原模型（" + us["模型一句话"] + "），未做相似品/池化预测；低置信")
    us["is_special"] = us["is_triangle"] | us["is_low_conf"]
    us["特殊产品"] = np.where(us["is_special"], "是", "")
    us["特殊说明"] = np.where(
        us["is_triangle"],
        "长历史三角靠枕；部分面料已从 USNJ 迁 USTX，按当前 owner，不把迁走面料算回 USNJ",
        np.where(us["is_low_conf"],
                 "2026 才卖/短历史/骨架/印花；沿用原模型，未做相似品/池化预测；低置信（需人工用相似品复核）",
                 ""))
    us["置信度"] = np.where(us["is_low_conf"], "低", us["置信度"].astype(str))
    us["CNY优先"] = np.where(us["is_triangle"], "是", "")
    us["CNY说明"] = (
        f"停工 {CNY_STOP}→复工 {CNY_RESUME}→首批到货 {CNY_FIRST_RECEIPT}；"
        "97/157 窗不足；bridge 备货待核（需 D5 183 天窗）；157 净需求仅参考，不作 bridge"
        + np.where(us["is_triangle"], "；三角靠枕优先", ""))
    us["可覆盖天数"] = [
        (pd.Timestamp(r.需要日).date() - AS_OF).days
        if pd.notna(r.需要日) else np.nan for r in us.itertuples(index=False)]
    us["供给状态"] = [
        "OK" if str(r.C完整键状态) in ("exact_full", "adapted_full_form")
        and pd.notna(r.C可发供给) else "待核"
        for r in us.itertuples(index=False)]
    def _backtest(r):
        model = str(r.model)
        if model in ("nan", "none", ""):
            return "—"
        sources = []
        if isinstance(r.adopted_sources, str) and r.adopted_sources.strip():
            try:
                sources = json.loads(r.adopted_sources)
            except json.JSONDecodeError:
                sources = []
        cands = [x for x in sources if str(x.get("model")) == model]
        if cands:
            src = max(cands, key=lambda x: float(x.get("qty", 0.0)))
            src_key = tuple(str(src.get("source_key", "")).split("|"))
        else:
            src_key = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        val = wape_idx.get(src_key + (model, "validation"), np.nan)
        hold = wape_idx.get(src_key + (model, "holdout"), np.nan)
        if pd.notna(val) and pd.notna(hold):
            return f"val {val:.3f} / holdout {hold:.3f}"
        if pd.notna(val):
            return f"val {val:.3f}"
        if pd.notna(hold):
            return f"holdout {hold:.3f}"
        return "—"

    us["回测"] = [_backtest(r) for r in us.itertuples(index=False)]
    us["理由"] = [
        f"{r.动作原因}；{r.服务档}/{r.分位标签}；{r.算法说明}"
        + ("；特殊/短历史，低置信" if r.is_special else "")
        for r in us.itertuples(index=False)]
    us["池"] = "美东USNJ"
    us["形态"] = us["physical_form"]
    us["UOM"] = us["canonical_uom"]
    if "q95需求" not in us.columns and "q95" in us.columns:
        us["q95需求"] = us["q95"]
    us["建议量_可编辑"] = us["建议数量"]
    us["需要日_可编辑"] = us["需要日"]
    us["理由_可编辑"] = us["理由"]
    return us.sort_values(["CNY优先", "服务档", "建议数量"],
                          ascending=[False, True, False])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="USNJ 补货试点包（只读）")
    ap.add_argument("--d6", default=f"{BA}/D6v6_24-1112/"
                    "D_Top50沙盒_D6_v6_24_2026-11-12.xlsx")
    ap.add_argument("--d3b", default=f"{BA}/D3b-v3_11-20261112/"
                    "D_历史归一与回测_D3b_v3_11_2026-11-12.xlsx")
    ap.add_argument("--series", default=f"{BA}/D3b-v3_11-20261112/"
                    "D3b_v3_11_series_current_2026-11-12.parquet")
    ap.add_argument("--demand-trend", default=f"{BA}/DEMAND_TREND_20261112.csv")
    ap.add_argument("--eligibility", default=f"{BA}/boss-delivery-20261106-1725/"
                    "eligibility-all1749.csv")
    ap.add_argument("--out-xlsx", default=f"{BA}/usnj_replenishment_pilot_20261112.xlsx")
    ap.add_argument("--out-dir", default=f"{BA}/usnj_replenishment_pilot_20261112")
    args = ap.parse_args(argv)
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    d6 = pd.read_excel(args.d6, sheet_name="1_全量动作")
    audit, cls, res = _read_d3b(args.d3b)
    trend = pd.read_csv(args.demand_trend, dtype={"product_id": str})
    meta = pd.read_csv(args.eligibility, dtype={"product_id": str},
                       usecols=["product_id", "name", "item_group"])
    sales = load_sales(args.series)
    b, pending = build_b_list(audit, trend, meta)
    us = build_pilot(d6, b, sales, cls, res, meta)

    b_cols = ["product_id", "current_owner", "current_pool", "hist_pools",
              "hist_qty_USNJ", "hist_qty_USTX", "moved_qty", "direction",
              "both_pools", "exception_current_USNJ_hist_USTX", "标记", "证据",
              "name", "item_group", "家族", "面料", "family", "fabric", "2025总销量", "2026总销量",
              "2025USNJ销量", "2026USNJ销量", "Jing勾选", "Jing备注"]
    p_cols = ["product_id", "current_owner", "hist_pools", "unassigned_qty",
              "标记", "证据", "name", "item_group", "2025总销量", "2026总销量",
              "Jing勾选", "Jing备注"]
    pilot_cols = ["product_id", "形态", "UOM", "name", "item_group", "服务档", "预设",
                  "分位", "建议动作", "新补数量", "催已有量", "建议量_可编辑",
                  "需要日_可编辑", "理由_可编辑", "可覆盖天数", "需要日",
                  "近30天销量_202610", "近90天销量_202608_10", "C可发供给",
                  "EN已发运量", "EN待发量", "PO追加(去重)", "SO已下",
                  "CG可调拨抵扣", "CG缓冲抵扣", "到时供给", "ETA_p50", "ETA_p90",
                  "在途ETA_p50", "在途ETA_p90", "EN快照状态", "净需求(所选分位)",
                  "净需求157", "p50", "q90需求", "q95需求", "采用模型", "模型一句话",
                  "算法说明", "回测", "置信度", "供给状态", "hist_pools", "current_owner",
                  "moved_qty", "标记", "CNY优先", "CNY说明", "特殊产品", "特殊说明"]
    spec = us[us["特殊产品"] == "是"].copy()
    cny = us[["product_id", "name", "item_group", "服务档", "建议动作",
              "净需求157", "CNY优先", "CNY说明"]].rename(
        columns={"净需求157": "157天净需求_参考(非bridge)"}).copy()
    cny["bridge备货"] = "待核（需 D5 183 天窗）"
    cny["bridge窗"] = f"{CNY_STOP}→{CNY_FIRST_RECEIPT}"
    cny["停工"] = str(CNY_STOP)
    cny["复工"] = str(CNY_RESUME)
    cny["首批到货"] = str(CNY_FIRST_RECEIPT)
    cny["到首批天数"] = (CNY_FIRST_RECEIPT - AS_OF).days
    cny = cny.sort_values(["CNY优先", "157天净需求_参考(非bridge)"], ascending=[False, False])

    Path(args.out_dir, "B_USNJ归属清单.csv").write_text(
        b[b_cols].to_csv(index=False), encoding="utf-8-sig")
    Path(args.out_dir, "B_待确认.csv").write_text(
        pending[p_cols].to_csv(index=False), encoding="utf-8-sig")
    Path(args.out_dir, "USNJ补货建议.csv").write_text(
        us[pilot_cols].to_csv(index=False), encoding="utf-8-sig")
    Path(args.out_dir, "USNJ_特殊产品.csv").write_text(
        spec[pilot_cols].to_csv(index=False), encoding="utf-8-sig")
    pd.DataFrame(columns=["sku", "pool", "preset_or_quantile", "reason",
                          "owner", "as_of"]).to_csv(
        Path(args.out_dir, "service_policy_overrides_TEMPLATE.csv"),
        index=False, encoding="utf-8-sig")
    Path(args.out_dir, "USNJ_CNY_prebuild.csv").write_text(
        cny.to_csv(index=False), encoding="utf-8-sig")

    with pd.ExcelWriter(args.out_xlsx, engine="openpyxl") as xw:
        pd.DataFrame([
            ("用途", "USNJ 补货试点；给运营负责人 Jing 直接勾选/编辑"),
            ("as-of", str(AS_OF)),
            ("D6", args.d6),
            ("D3b", args.d3b),
            ("4 周", "上线后的监控期，不是等待期；本包现在出"),
            ("CNY", f"停工 {CNY_STOP} → 复工 {CNY_RESUME} → 首批到货 {CNY_FIRST_RECEIPT}；"
                     "bridge 备货待核（需 D5 183 天窗）；157 净需求仅参考"),
            ("未知供给", "C 完整键/供给未知标“待核”，不当 0"),
            ("30/90 天销量", "月度口径：2026-10 / 2026-08..10（D3b current 序列）"),
            ("列口径", "C可发供给=C14/通途可发；EN已发运/待发；PO追加(去重)/SO；"
                       "CG可调拨/缓冲；ETA_p50/p90；未知=待核"),
            ("可编辑", "建议量_可编辑 / 需要日_可编辑 / 理由_可编辑；Jing 直接改这三列"),
        ], columns=["项", "说明"]).to_excel(xw, sheet_name="0_说明", index=False)
        b[b_cols].to_excel(xw, sheet_name="1_B归属清单", index=False)
        pending[p_cols].to_excel(xw, sheet_name="1b_待确认", index=False)
        us[pilot_cols].to_excel(xw, sheet_name="2_补货建议", index=False)
        spec[pilot_cols].to_excel(xw, sheet_name="3_特殊产品", index=False)
        cny.to_excel(xw, sheet_name="4_CNY_prebuild", index=False)
        pd.DataFrame([
            ("naive", METHOD_NOTE["naive"]), ("ma3", METHOD_NOTE["ma3"]),
            ("snaive", METHOD_NOTE["snaive"]), ("ets_ann", METHOD_NOTE["ets_ann"]),
            ("ets_aadn", METHOD_NOTE["ets_aadn"]), ("ets_aaa", METHOD_NOTE["ets_aaa"]),
            ("theta", METHOD_NOTE["theta"]), ("croston", METHOD_NOTE["croston"]),
            ("sba", METHOD_NOTE["sba"]), ("tsb", METHOD_NOTE["tsb"]),
            ("ensemble", METHOD_NOTE["ensemble"]), ("none", METHOD_NOTE["none"]),
        ], columns=["方法", "一句话"]).to_excel(xw, sheet_name="5_方法说明", index=False)

    readme = f"""# USNJ 补货试点包（{AS_OF}）

- 给运营负责人 Jing 直接使用；**4 周是上线后的监控期，不是等待期，本包现在出**。
- D6 v6.24 preset=balance；q95 保留在表内作敏感性。
- 未知 C 供给标“待核”，不当 0；30/90 天销量为月度口径（2026-10 / 2026-08..10）。
- 供给侧列：`C可发供给`=C14/通途可发；`EN已发运量/EN待发量`；`PO追加(去重)`/`SO已下`；
  `CG可调拨抵扣/CG缓冲抵扣`；`ETA_p50/p90`。
- **CNY**：停工 {CNY_STOP} → 复工 {CNY_RESUME} → 首批到货 {CNY_FIRST_RECEIPT}；97/157 窗不足；
  **bridge 备货待核（需 D5 183 天窗）**；157 净需求仅参考、不作 bridge；三角靠枕优先。
- **特殊产品**：三角靠枕按当前 owner（不把已迁走面料算回 USNJ）；麻将沙发/铁架/印花/短历史**沿用原模型，未做相似品/池化预测**，标低置信，需人工复核。
- 可直接改 `2_补货建议` 的 **建议量_可编辑 / 需要日_可编辑 / 理由_可编辑**。
- `回测` 只取该行 `采用模型` 在 D3b as-of 源键的 validation/holdout WAPE；无同模型回测显示 `—`，不展示别的模型成绩。

## 文件

| 文件 | 内容 |
|---|---|
| `1_B归属清单` | {len(b)} 个 current USNJ 归属产品；含历史仓/current owner/2025-26 销量/面料/家族/标记/Jing勾选 |
| `1b_待确认` | {len(pending)} 个 unassigned/exception 产品；Jing 勾选确认 |
| `2_补货建议` | {len(us)} 行 SKU×形态×UOM；动作/量/覆盖/原因/可编辑 |
| `3_特殊产品` | {len(spec)} 行三角/麻将/铁架/印花/短历史 |
| `4_CNY_prebuild` | CNY 日历 + 157 天净需求 + 三角优先 |
| `5_方法说明` | 每个模型一句话 |
"""
    Path(args.out_dir, "USNJ_试点包_说明_20261112.md").write_text(readme, encoding="utf-8")

    summary = dict(
        as_of=str(AS_OF), d6=args.d6, d3b=args.d3b,
        outputs=dict(xlsx=args.out_xlsx, dir=args.out_dir),
        counts=dict(b_usnj=len(b), b_pending=len(pending), pilot_rows=len(us),
                    special=len(spec), triangle=int(us["is_triangle"].sum()),
                    unknown_supply=int((us["供给状态"] == "待核").sum()),
                    cny_priority=int((us["CNY优先"] == "是").sum())),
        files={p.name: dict(sha256=sha256(p), bytes=p.stat().st_size)
               for p in ([Path(args.out_xlsx)]
                         + sorted(Path(args.out_dir).glob("*")))
               if p.is_file()},
    )
    Path(args.out_dir, "USNJ_试点包.manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summary["counts"], ensure_ascii=False))
    print("xlsx：", args.out_xlsx)
    print("目录：", args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
