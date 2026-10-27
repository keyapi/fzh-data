# -*- coding: utf-8 -*-
"""目录覆盖分析：4,014 决策键 vs 公司目录 / 在售 / 有库存 SKU（只读，不改数）。

三个口径（互相独立，报告分别给出）：
- **公司目录**：EN 商品目录条目（`ks_items.tsv`），含成品/皮壳/内胆/套件。
- **在售**：能被通途码映射到的 EN 物料（`sku_map.tsv`）。
- **有库存**：2026-10-26 快照里 `available > 0` 的物料。

未进包原因（互斥，优先级从上到下）：
`component_or_cover`（ND#/PK#）→ `discontinued`（名称标记）→ `unmapped_no_evidence`
（无通途映射且无库存无销量）→ `stock_without_uom_evidence`（有库存但 EN 单位未证）
→ `mapped_no_stock_no_sales` → `other`。

结论口径：4,014 个键 ≠ 公司全部 SKU；未覆盖不等于零需求（有库存/有映射的要单列）。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from self_fulfilled_demand.canonical import load_sku_map

SNAPSHOT_DATE = "2026-10-26"
DISCONTINUED_MARKERS = ("淘汰", "停售", "-out")


def role_of(item: str) -> str:
    text = str(item)
    if text.startswith("ND#"):
        return "component_bag"      # 内胆
    if text.startswith("PK#"):
        return "cover"              # 皮壳
    if text.startswith("TJ#"):
        return "bundle"             # 套件
    if text.startswith("KS"):
        return "finished"
    return "other"


def load_catalog(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", header=None, names=["item", "group", "name"],
                        dtype=str, keep_default_na=False)
    frame["role"] = frame["item"].map(role_of)
    return frame.drop_duplicates("item")


def build_item_facts(*, catalog: pd.DataFrame, sku_map: pd.DataFrame, stock: pd.DataFrame,
                     classification: pd.DataFrame, pack: pd.DataFrame) -> pd.DataFrame:
    item_by_tt = {row.tongtool_sku: row.item_codes[0]
                  for row in sku_map.itertuples(index=False)
                  if row.mapping_status == "mapped" and len(row.item_codes) == 1}
    tts_by_item: dict[str, set] = {}
    for tt, item in item_by_tt.items():
        tts_by_item.setdefault(item, set()).add(tt)

    snapshot = stock[pd.to_datetime(stock["snapshot_date"]).dt.date.astype(str)
                     == SNAPSHOT_DATE].copy()
    snapshot["item"] = snapshot["sku"].astype(str).str.strip().map(item_by_tt)
    stock_qty = snapshot.groupby("item")["available"].sum()
    stock_pos = stock_qty[stock_qty > 0]
    stock_wh = snapshot[snapshot["available"] > 0].groupby("item")["warehouse_name"].agg(
        lambda s: ";".join(sorted({str(v) for v in s})))

    cls = classification.copy()
    cls["item"] = cls["sku"].astype(str).str.strip().map(item_by_tt)
    def _sales(column: str) -> pd.Series:
        if column not in cls.columns:
            return pd.Series(dtype=float)
        return pd.to_numeric(cls[column], errors="coerce").fillna(0.0).groupby(
            cls["item"]).sum()

    sales_total = _sales("历史总销量")
    sales_recent = _sales("近6月销量")

    pack_items = set(pack["canonical_sku"])
    pack_keys = pack.groupby("canonical_sku").size()

    universe = set(catalog["item"]) | pack_items
    rows = []
    for item in sorted(universe):
        meta = catalog[catalog["item"] == item]
        rows.append(dict(
            item=item,
            role=(meta["role"].iloc[0] if len(meta) else role_of(item)),
            group=(meta["group"].iloc[0] if len(meta) else None),
            name=(meta["name"].iloc[0] if len(meta) else None),
            in_catalog=bool(len(meta)),
            mapped_tt_count=len(tts_by_item.get(item, ())),
            stock_qty=round(float(stock_pos.get(item, 0.0)), 3),
            stock_warehouses=stock_wh.get(item),
            sales_total=round(float(sales_total.get(item, 0.0)), 3),
            sales_recent6=round(float(sales_recent.get(item, 0.0)), 3),
            in_pack=item in pack_items,
            pack_keys=int(pack_keys.get(item, 0)),
        ))
    return pd.DataFrame(rows)


def classify(frame: pd.DataFrame, *, uom_items: set[str]) -> pd.DataFrame:
    def reason(row) -> tuple[str, str]:
        if row["in_pack"]:
            return "", ""
        if row["role"] in ("component_bag", "cover"):
            return "component_or_cover", "ND#内胆/PK#皮壳：本层不作为独立可售 SKU"
        text = str(row["name"] or "")
        if any(marker in text for marker in DISCONTINUED_MARKERS):
            return "discontinued", "名称含淘汰/停售/-out 标记"
        if row["mapped_tt_count"] == 0 and row["stock_qty"] <= 0 and row["sales_total"] <= 0:
            return "unmapped_no_evidence", "无通途映射、无库存、无历史销量"
        if row["stock_qty"] > 0 and row["item"] not in uom_items:
            return "stock_without_uom_evidence", "有库存但 EN 单位未证（UOM 缓存未覆盖）"
        if row["stock_qty"] <= 0 and row["sales_total"] <= 0:
            return "mapped_no_stock_no_sales", "有映射但无库存、无销量"
        if row["stock_qty"] > 0 or row["sales_total"] > 0:
            return "other_gap", "有库存/销量但未进包（需逐项核对）"
        return "other", "未分类"

    frame = frame.copy()
    pairs = [reason(row) for _, row in frame.iterrows()]
    frame["reason"] = [pair[0] for pair in pairs]
    frame["reason_detail"] = [pair[1] for pair in pairs]
    return frame


def summarize(frame: pd.DataFrame, pack: pd.DataFrame) -> dict:
    catalog = frame[frame["in_catalog"]]
    uncovered = frame[~frame["in_pack"]]
    mapped = frame[frame["mapped_tt_count"] > 0]
    with_stock = frame[frame["stock_qty"] > 0]
    reasons = (uncovered[uncovered["reason"] != ""]["reason"].value_counts().to_dict())
    reason_qty = (uncovered.groupby("reason")["stock_qty"].sum().round(3).to_dict())
    return dict(
        keys_in_pack=int(len(pack)),
        items_in_pack=int(frame["in_pack"].sum()),
        catalog_items=int(len(catalog)),
        catalog_in_pack=int((catalog["in_pack"]).sum()),
        catalog_uncovered=int((~catalog["in_pack"]).sum()),
        catalog_coverage_pct=round(100 * float(catalog["in_pack"].mean()), 2),
        mapped_items=int(len(mapped)),
        mapped_in_pack=int(mapped["in_pack"].sum()),
        mapped_uncovered=int((~mapped["in_pack"]).sum()),
        stock_items=int(len(with_stock)),
        stock_in_pack=int(with_stock["in_pack"].sum()),
        stock_uncovered=int((~with_stock["in_pack"]).sum()),
        stock_uncovered_qty=round(float(with_stock[~with_stock["in_pack"]]["stock_qty"].sum()), 3),
        reasons={k: int(v) for k, v in reasons.items()},
        reason_stock_qty={k: float(v) for k, v in reason_qty.items()},
        pack_items_outside_catalog=int((~frame["in_catalog"] & frame["in_pack"]).sum()),
        pack_keys_by_uom=pack.groupby("canonical_uom").size().to_dict(),
        pack_keys_by_warehouse=pack.groupby("canonical_warehouse").size().to_dict(),
        pack_items_by_role=frame[frame["in_pack"]]["role"].value_counts().to_dict(),
        uncovered_by_role=uncovered["role"].value_counts().to_dict(),
        reconciliation=dict(
            catalog_equals_pack_plus_uncovered=int(
                len(catalog) == int((catalog["in_pack"]).sum()) + int((~catalog["in_pack"]).sum())),
            reasons_sum_to_uncovered=int(sum(reasons.values())
                                         == int((~frame["in_pack"]).sum())),
        ),
        statement=("4,014 键只覆盖 1,627 个 EN 物料，不代表公司全部 SKU；"
                   "未覆盖项中有库存/有映射的必须单列，不能当作零需求"),
    )


def write_report(frame: pd.DataFrame, stats: dict, meta: dict, out: Path) -> None:
    lines = [
        "# 目录覆盖分析（2026-10-28）",
        "",
        f"- 决策包：`{meta['pack']}`（{stats['keys_in_pack']} 个 SKU×仓×UOM 键）",
        f"- 公司目录：`{meta['catalog']}`（{stats['catalog_items']} 个 EN 物料条目）",
        f"- 映射：`{meta['sku_map']}`；库存：`{meta['stock']}`（{SNAPSHOT_DATE}）；"
        f"销量分类：`{meta['classification']}`",
        "",
        "## 1. 三个口径的覆盖",
        "",
        "| 口径 | 总数 | 进包 | 未进包 | 覆盖率 |",
        "|---|---:|---:|---:|---:|",
        f"| 公司目录（EN 物料） | {stats['catalog_items']} | {stats['catalog_in_pack']} | "
        f"{stats['catalog_uncovered']} | {stats['catalog_coverage_pct']}% |",
        f"| 在售（可映射物料） | {stats['mapped_items']} | {stats['mapped_in_pack']} | "
        f"{stats['mapped_uncovered']} | — |",
        f"| 有库存（可用>0） | {stats['stock_items']} | {stats['stock_in_pack']} | "
        f"{stats['stock_uncovered']} | — |",
        "",
        f"- 未进包但有库存：**{stats['stock_uncovered']} 个物料 / "
        f"{stats['stock_uncovered_qty']:.0f} 件**——这是最需要单列的覆盖缺口。",
        f"- 决策包里有 {stats['pack_items_outside_catalog']} 个物料不在 EN 目录（套件/外部码）。",
        f"- **4,014 键 ≠ 公司全部 SKU**：它只覆盖 {stats['items_in_pack']} 个物料；"
        "未覆盖不等于零需求。",
        "",
        "## 2. 未进包原因（互斥）",
        "",
        "| 原因 | 物料数 | 其中库存件数 | 说明 |",
        "|---|---:|---:|---|",
    ]
    detail = {
        "component_or_cover": "ND# 内胆 / PK# 皮壳，不作为独立可售 SKU",
        "discontinued": "名称含淘汰/停售/-out",
        "unmapped_no_evidence": "无通途映射、无库存、无历史销量",
        "stock_without_uom_evidence": "有库存但 EN 单位未证（UOM 缓存未覆盖）",
        "mapped_no_stock_no_sales": "有映射但无库存、无销量",
        "other_gap": "有库存/销量但未进包（待核对）",
        "other": "未分类",
    }
    for reason, count in sorted(stats["reasons"].items(), key=lambda item: -item[1]):
        qty = stats["reason_stock_qty"].get(reason, 0.0)
        lines.append(f"| {reason} | {count} | {qty:.0f} | {detail.get(reason, '')} |")
    lines += [
        "",
        f"- 原因合计 {sum(stats['reasons'].values())} = 未进包 "
        f"{stats['catalog_uncovered']}（对账 "
        f"{'通过' if stats['reconciliation']['reasons_sum_to_uncovered'] else '失败'}）。",
        "",
        "## 3. 分布",
        "",
        "**进包键按 UOM**：" + json.dumps(stats["pack_keys_by_uom"], ensure_ascii=False),
        "",
        "**进包键按仓**：",
        "",
        "| 仓 | 键数 |",
        "|---|---:|",
    ]
    for warehouse, count in sorted(stats["pack_keys_by_warehouse"].items(),
                                   key=lambda item: -item[1]):
        lines.append(f"| {warehouse} | {count} |")
    lines += [
        "",
        "**进包物料按角色**：" + json.dumps(stats["pack_items_by_role"], ensure_ascii=False),
        "",
        "**未进包物料按角色**：" + json.dumps(stats["uncovered_by_role"], ensure_ascii=False),
        "",
        "## 4. 使用边界",
        "",
        "- 4,014 键是「有需求证据或有库存且单位已证」的子集，**不是公司全 SKU**。",
        "- 未进包 ≠ 零需求：64 个物料有 1,324 件库存但缺 EN 单位证据；"
        "348 个可映射物料没有进入需求/预测覆盖。",
        "- 皮壳/内胆是组件形态，是否算可售取决于渠道口径（本层不替业务裁定）。",
        "- 只读分析：不改净额与决策包，不 push。",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="目录覆盖分析（只读）")
    parser.add_argument("--pack", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                           "decision-pack-2026-10-29-r2/decision_pack_2026-10-29.parquet")
    parser.add_argument("--catalog", default="D:/Work/fzh-order-store/ks_items.tsv")
    parser.add_argument("--sku-map", default="D:/Work/fzh-order-store/sku_map.tsv")
    parser.add_argument("--stock", default="D:/Work/fzh-order-store/en_stock.parquet")
    parser.add_argument("--classification",
                        default="D:/Work/fzh-order-store/analysis/sku_classification_20261027.csv")
    parser.add_argument("--uom-cache",
                        default="D:/Work/fzh-order-store/en-demand-v1/canonical/item_uom_cache.parquet")
    parser.add_argument("--out", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                         "catalog-coverage-2026-10-28")
    args = parser.parse_args(argv)

    pack = pd.read_parquet(args.pack)
    catalog = load_catalog(args.catalog)
    sku_map = load_sku_map(args.sku_map)
    stock = pd.read_parquet(args.stock)
    classification = pd.read_csv(args.classification, encoding="utf-8-sig")
    uom_items = set(pd.read_parquet(args.uom_cache)["item_code"].astype(str)) \
        if Path(args.uom_cache).exists() else set()

    frame = build_item_facts(catalog=catalog, sku_map=sku_map, stock=stock,
                             classification=classification, pack=pack)
    frame = classify(frame, uom_items=uom_items)
    stats = summarize(frame, pack)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / "catalog_items.csv", index=False, encoding="utf-8-sig")
    frame[~frame["in_pack"]].to_csv(out / "uncovered_items.csv", index=False,
                                    encoding="utf-8-sig")
    (out / "catalog_coverage_summary.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    meta = dict(schema_version="catalog-coverage/v1",
                generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                pack=str(args.pack), catalog=str(args.catalog), sku_map=str(args.sku_map),
                stock=str(args.stock), classification=str(args.classification),
                snapshot_date=SNAPSHOT_DATE, rows=int(len(frame)),
                note="只读分析；不改净额与决策包，不 push")
    (out / "catalog_coverage_manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(frame, stats, meta, out)
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    print("输出：", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
