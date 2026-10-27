# -*- coding: utf-8 -*-
"""P1 条件决策包：未映射匹配建议、服务水平情景、SKU×仓工作表。

只读一次已完成的净额 run（默认 ``run-2026-10-23-r2``），产本地 CSV/xlsx；
不预测、不下单、不改净额结果。所有「建议」都是条件情景，不是采购指令。

匹配分三级，越靠前证据越硬：
- R1 同族后缀：去掉已知后缀（``-Cover`` / ``-Foam`` / ``-淘汰`` / ``-out`` / ``-PPCotton`` /
  ``-1`` / 末尾 ``-0``）后命中 ``sku_map`` → 直接继承同一物料（high）。
- R2 型号唯一：通途型号前缀（``TT0031245``）在 ``sku_map`` 里只对应一个物料族且族内唯一
  物料 → 候选（medium）；族内多物料则列候选、置信 low。
- 其余标 ``unknown``，不硬绑。
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import pandas as pd

from self_fulfilled_demand.canonical import load_sku_map

KNOWN_SUFFIXES = ("-Cover", "-Foam", "-淘汰", "-out", "-PPCotton", "-1")
TT_MODEL = re.compile(r"^(TT\d{7})")
ITEM_MODEL = re.compile(r"^([A-Z]{2,3}\d{3,4})")

# 服务水平档：销量 ABC，用户已确认口径，只作情景
SERVICE_LEVEL_TIERS = (("A", 0.80, 0.98), ("B", 0.95, 0.95), ("C", 1.00, 0.90))
FLAT_SL = 0.95
SCENARIO_WINDOW_DAYS = 14          # 无 lead time 时的情景窗口，不是承诺
HISTORY_DAYS = 90


def _z(sl: float) -> float:
    """标准正态分位（有理近似，误差 < 1e-4）。"""
    p = min(max(float(sl), 1e-6), 1 - 1e-6)
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def assumed_uom(sku: str) -> str:
    """用户口径：未映射默认「个」；TJ# 套件按「套」；``#qc`` 视为清仓。"""
    text = str(sku)
    if text.startswith("TJ#") or text.startswith("TJ"):
        return "套"
    return "个"


def _strip_suffix(sku: str) -> list[str]:
    """返回去掉已知后缀的全部候选基码（含 `-N` 数字后缀）。"""
    out = []
    text = str(sku)
    for suffix in KNOWN_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            out.append(text[: -len(suffix)])
    match = re.search(r"-\d+$", text)
    if match:
        out.append(text[: match.start()])
    return out


def build_model_index(sku_map: pd.DataFrame) -> dict[str, list[str]]:
    """通途型号前缀 → 该型号已登记的物料清单。"""
    index: dict[str, set[str]] = {}
    for row in sku_map.itertuples(index=False):
        match = TT_MODEL.match(str(row.tongtool_sku))
        if not match or row.mapping_status != "mapped" or len(row.item_codes) != 1:
            continue
        index.setdefault(match.group(1), set()).add(row.item_codes[0])
    return {k: sorted(v) for k, v in index.items()}


def match_unmapped(unmapped: pd.DataFrame, sku_map: pd.DataFrame) -> pd.DataFrame:
    """未映射 SKU 的候选与建议。``unmapped`` 需含 ``raw_sku`` / ``quantity`` / ``rows``。"""
    lookup = {str(r.tongtool_sku): tuple(r.item_codes)
              for r in sku_map.itertuples(index=False)
              if r.mapping_status == "mapped" and len(r.item_codes) == 1}
    models = build_model_index(sku_map)
    rows = []
    for record in unmapped.itertuples(index=False):
        raw = str(record.raw_sku)
        candidates: list[str] = []
        method, confidence, evidence = "none", "none", ""
        for base in _strip_suffix(raw):
            if base in lookup:
                candidates = [lookup[base][0]]
                method, confidence = "R1_sibling_suffix", "high"
                evidence = f"去后缀命中 sku_map：{base} → {candidates[0]}"
                break
        if not candidates:
            # 反向同族：本 SKU 无后缀，但它的带后缀兄弟已登记（如 X-Foam / X-Cover / X-0）
            stems = [raw] + _strip_suffix(raw)
            found: dict[str, list[str]] = {}
            for stem in stems:
                for suffix in KNOWN_SUFFIXES + ("-0",):
                    sibling = f"{stem}{suffix}"
                    if sibling in lookup:
                        found.setdefault(lookup[sibling][0], []).append(sibling)
            if len(found) == 1:
                item, siblings = next(iter(found.items()))
                candidates = [item]
                method, confidence = "R1b_sibling_of_registered_variant", "high"
                evidence = f"同族已登记变体 {', '.join(siblings[:2])} → {item}"
            elif len(found) > 1:
                candidates = sorted(found)[:5]
                method, confidence = "R1c_sibling_conflict", "low"
                evidence = f"带后缀兄弟指向 {len(found)} 个物料，需确认"
        if not candidates:
            match = TT_MODEL.match(raw)
            if match:
                family = models.get(match.group(1), [])
                if len(family) == 1:
                    candidates = family
                    method, confidence = "R2_model_unique", "medium"
                    evidence = f"型号 {match.group(1)} 在 sku_map 只对应一个物料"
                elif len(family) > 1:
                    candidates = family[:5]
                    method, confidence = "R3_model_family", "low"
                    evidence = (f"型号 {match.group(1)} 对应 {len(family)} 个物料，"
                                "需按颜色/尺寸确认")
        suggestion = {"high": "map", "medium": "map_after_confirm",
                      "low": "manual", "none": "manual_or_skip"}[confidence]
        rows.append(dict(
            raw_sku=raw, quantity=float(getattr(record, "quantity", 0) or 0),
            rows=int(getattr(record, "rows", 0) or 0),
            uom_assumed=assumed_uom(raw),
            candidates=" | ".join(candidates),
            n_candidates=len(candidates),
            match_method=method, confidence=confidence,
            evidence=evidence or "无后缀/型号证据；不硬猜",
            suggestion=suggestion,
        ))
    frame = pd.DataFrame(rows)
    return frame.sort_values(["quantity"], ascending=False) if len(frame) else frame


def abc_tiers(demand_by_key: pd.DataFrame) -> pd.DataFrame:
    """按销量降序累计占比分 A/B/C（80% / 95% / 余）。"""
    frame = demand_by_key.sort_values("quantity", ascending=False).copy()
    total = float(frame["quantity"].sum())
    if total <= 0:
        frame["cum_share"] = 0.0
        frame["tier"] = "C"
        return frame
    frame["cum_share"] = frame["quantity"].cumsum() / total
    tier = []
    for share in frame["cum_share"]:
        if share <= 0.80:
            tier.append("A")
        elif share <= 0.95:
            tier.append("B")
        else:
            tier.append("C")
    frame["tier"] = tier
    for name, _bound, sl in SERVICE_LEVEL_TIERS:
        frame.loc[frame["tier"] == name, "service_level"] = sl
    frame["z"] = frame["service_level"].map(_z)
    return frame


def service_level_scenarios(history: pd.DataFrame, demand_by_key: pd.DataFrame) -> pd.DataFrame:
    """逐 key 的服务水平情景：A98/B95/C90 + flat95。

    ``history`` 是逐日需求（key + demand_date + quantity），取最近 ``HISTORY_DAYS`` 天算
    σ。**未含提前期**：buffer = z × σ_daily × √14，14 天只是情景窗口，不是承诺。
    """
    if not len(demand_by_key):
        return pd.DataFrame()
    frame = abc_tiers(demand_by_key)
    if len(history):
        hist = history.copy()
        hist["demand_date"] = pd.to_datetime(hist["demand_date"])
        cutoff = hist["demand_date"].max() - pd.Timedelta(days=HISTORY_DAYS)
        hist = hist[hist["demand_date"] >= cutoff]
        stats = (hist.groupby(["canonical_sku", "canonical_warehouse", "canonical_uom"])["quantity"]
                 .agg(sigma_daily="std", mean_daily="mean", days="size").reset_index())
        frame = frame.merge(stats, on=["canonical_sku", "canonical_warehouse", "canonical_uom"],
                            how="left")
    else:
        frame["sigma_daily"] = None
        frame["mean_daily"] = None
        frame["days"] = 0
    frame["sigma_daily"] = frame["sigma_daily"].fillna(0.0)
    frame["window_days"] = SCENARIO_WINDOW_DAYS
    frame["buffer_abc"] = frame["z"] * frame["sigma_daily"] * math.sqrt(SCENARIO_WINDOW_DAYS)
    frame["buffer_flat95"] = _z(FLAT_SL) * frame["sigma_daily"] * math.sqrt(SCENARIO_WINDOW_DAYS)
    frame["flat95_service_level"] = FLAT_SL
    frame["note"] = "未含提前期；σ 取最近 90 天日需求波动；只作情景，不是承诺"
    return frame.sort_values(["tier", "quantity"], ascending=[True, False])


def decision_pack(netting: pd.DataFrame, scenarios: pd.DataFrame,
                  facts: pd.DataFrame) -> pd.DataFrame:
    """SKU×仓工作表：需求、供给、缺口、标记、服务档与建议。"""
    key = ["canonical_sku", "canonical_warehouse", "canonical_uom"]
    expected = netting[netting["scenario"] == "expected"]
    protect = expected[expected["bucket_id"] == "protect"]
    horizon = expected.groupby(key, as_index=False).agg(
        period_demand=("period_demand", "sum"),
        conditional_receipts=("conditional_receipts", "max"),
        end_unserved=("unserved", "last"),
    )
    base = protect[key + ["opening", "receipts", "gap", "status"]].rename(
        columns={"receipts": "proven_receipts", "gap": "protect_gap"})
    out = base.merge(horizon, on=key, how="left")
    if len(scenarios):
        out = out.merge(scenarios[key + ["tier", "service_level", "z", "sigma_daily",
                                         "buffer_abc", "buffer_flat95"]], on=key, how="left",
                        suffixes=("", "_sl"))

    # 供给来源标记：该 key 是否拿到在途 / 通途 PO 量
    if len(facts):
        supply = facts[facts["qty"].notna()].copy()
        supply["source_layer"] = supply["source_layer"].fillna("")
        intransit = (supply[supply["source_layer"] == "in_transit"].groupby(key)["qty"].sum()
                     .rename("intransit_qty"))
        po = (supply[supply["source_layer"] == "tongtool_po"].groupby(key)["qty"].sum()
              .rename("po_qty"))
        for series in (intransit, po):
            out = out.merge(series, on=key, how="left")
    for column in ("intransit_qty", "po_qty"):
        if column not in out.columns:
            out[column] = None

    def recommend(row) -> str:
        if row.get("status") == "unknown" or pd.isna(row.get("opening")):
            return "数据不足"
        gap = float(row.get("protect_gap") or 0)
        conditional = float(row.get("conditional_receipts") or 0)
        if gap > 0:
            return "补（缺口已证）" if conditional < gap else "观察（有条件供给，需核实 ETA）"
        if float(row.get("end_unserved") or 0) > 0:
            return "补（视界内未满足）"
        buffer = float(row.get("buffer_abc") or 0)
        opening = float(row.get("opening") or 0)
        if buffer and opening < buffer:
            return "观察（低于服务档缓冲）"
        return "不需补（当前窗口）"

    out["recommendation"] = out.apply(recommend, axis=1)
    out["demand_basis"] = "demand_netting 前瞻行；未接入未履约 SO backlog"
    out["supply_basis"] = "期初库存 + 已证到货；在途/通途 PO 无 ETA 仅作条件量"
    out["note"] = "条件决策包，不是采购单；partial=true"
    return out.sort_values(["protect_gap", "period_demand"], ascending=False)


def _history_frame(demand_netting: pd.DataFrame) -> pd.DataFrame:
    keep = demand_netting[demand_netting["in_default_series"].fillna(False).astype(bool)]
    return keep[["canonical_sku", "canonical_warehouse", "canonical_uom",
                 "demand_date", "quantity_default"]].rename(columns={"quantity_default": "quantity"})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="P1 条件决策包（未映射建议 / 服务水平 / SKU×仓工作表）")
    parser.add_argument("--run", required=True, help="supply_netting run 目录（含 parquet 与 manifest）")
    parser.add_argument("--sku-map", default="D:/Work/fzh-order-store/sku_map.tsv")
    parser.add_argument("--demand", required=True, help="demand_netting.parquet（算历史波动与需求侧未映射）")
    parser.add_argument("--stock", required=True, help="库存快照 parquet（算库存侧未映射）")
    parser.add_argument("--blocked", default=None, help="demand_blocked.parquet（需求侧未映射清单）")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    run_dir = Path(args.run)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    sku_map = load_sku_map(args.sku_map)
    known = set(sku_map.tongtool_sku)
    manifest = json.loads((run_dir / "supply_netting_manifest.json").read_text(encoding="utf-8"))

    # 库存侧未映射
    stock = pd.read_parquet(args.stock)
    stock_unmapped = stock[~stock.sku.isin(known)]
    inv_rows = (stock_unmapped.groupby("sku", as_index=False)
                .agg(quantity=("available", "sum"), rows=("warehouse_name", "size"))
                .rename(columns={"sku": "raw_sku"}))
    inventory_top = match_unmapped(inv_rows, sku_map).head(20)

    # 需求侧未映射
    if args.blocked:
        blocked = pd.read_parquet(args.blocked)
        un = blocked[blocked["canonical_sku"].astype(str).str.startswith("unmapped:")].copy()
        un["raw_sku"] = un["canonical_sku"].str.replace("^unmapped:", "", regex=True)
        demand_rows = (un.groupby("raw_sku", as_index=False)
                       .agg(quantity=("quantity", "sum"), rows=("line_count", "sum")))
    else:
        demand_rows = pd.DataFrame(columns=["raw_sku", "quantity", "rows"])
    demand_top = match_unmapped(demand_rows, sku_map).head(20) if len(demand_rows) else pd.DataFrame()

    # 净额与情景
    netting = pd.read_parquet(run_dir / "supply_netting.parquet")
    facts = pd.read_parquet(run_dir / "supply_facts.parquet")
    for column in ("opening", "receipts", "gap", "unserved", "period_demand",
                   "conditional_receipts", "qty"):
        if column in netting.columns:
            netting[column] = pd.to_numeric(netting[column], errors="coerce")
    facts["qty"] = pd.to_numeric(facts["qty"], errors="coerce")

    key = ["canonical_sku", "canonical_warehouse", "canonical_uom"]
    demand_by_key = (netting[netting["scenario"] == "expected"]
                     .groupby(key, as_index=False)
                     .agg(quantity=("period_demand", "sum")))
    history = _history_frame(pd.read_parquet(args.demand))
    scenarios = service_level_scenarios(history, demand_by_key)
    pack = decision_pack(netting, scenarios, facts)

    inventory_top.to_csv(out_dir / "unmapped_top20_inventory.csv", index=False, encoding="utf-8-sig")
    demand_top.to_csv(out_dir / "unmapped_top20_demand.csv", index=False, encoding="utf-8-sig")
    scenarios.to_csv(out_dir / "service_level_scenarios.csv", index=False, encoding="utf-8-sig")
    pack.to_csv(out_dir / "conditional_decision_pack.csv", index=False, encoding="utf-8-sig")

    inventory_all = match_unmapped(inv_rows, sku_map)
    demand_all = match_unmapped(demand_rows, sku_map) if len(demand_rows) else pd.DataFrame()
    summary = dict(
        inventory_unmapped_skus=int(len(inv_rows)),
        inventory_auto_map_high=int((inventory_all["confidence"] == "high").sum()),
        inventory_auto_map_medium=int((inventory_all["confidence"] == "medium").sum()),
        inventory_manual=int(inventory_all["confidence"].isin(["low", "none"]).sum()),
        inventory_auto_map_qty=float(inventory_all.loc[inventory_all["confidence"] == "high", "quantity"].sum()),
        demand_unmapped_skus=int(len(demand_rows)),
        demand_auto_map_high=int((demand_all["confidence"] == "high").sum()) if len(demand_all) else 0,
        demand_auto_map_medium=int((demand_all["confidence"] == "medium").sum()) if len(demand_all) else 0,
        demand_manual=int(demand_all["confidence"].isin(["low", "none"]).sum()) if len(demand_all) else 0,
        demand_auto_map_qty=float(demand_all.loc[demand_all["confidence"] == "high", "quantity"].sum()) if len(demand_all) else 0.0,
        demand_unmapped_qty=float(demand_rows["quantity"].sum()) if len(demand_rows) else 0.0,
        scenario_rows=int(len(scenarios)),
        scenario_window_days=SCENARIO_WINDOW_DAYS,
        decision_pack_rows=int(len(pack)),
        decision_pack_gap_keys=int((pack["protect_gap"].fillna(0) > 0).sum()),
        decision_pack_recommendations=pack["recommendation"].value_counts().to_dict(),
        run_manifest=dict(run_id=manifest.get("run_id"), as_of=manifest.get("as_of"),
                          partial=manifest.get("partial")),
        note="条件情景，不是采购单；未含提前期与未履约 SO backlog",
    )
    (out_dir / "pack_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    with pd.ExcelWriter(out_dir / "conditional_decision_pack.xlsx", engine="openpyxl") as writer:
        pack.to_excel(writer, sheet_name="SKU×仓", index=False)
        scenarios.to_excel(writer, sheet_name="服务水平情景", index=False)
        inventory_top.to_excel(writer, sheet_name="未映射-库存top20", index=False)
        (demand_top if len(demand_top) else pd.DataFrame({"说明": ["无需求侧未映射"]})).to_excel(
            writer, sheet_name="未映射-需求top20", index=False)
        pd.DataFrame([{"key": k, "value": json.dumps(v, ensure_ascii=False)} for k, v in summary.items()]
                     ).to_excel(writer, sheet_name="Manifest", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("输出：", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
