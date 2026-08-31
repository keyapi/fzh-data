# -*- coding: utf-8 -*-
"""Build the Tongtu -> EN -> Sellfox mapping workbook from read-only inputs.

Reads the latest mainline audit workbook, the latest EN BOM Cost List and the
latest Tongtu simple-template export zip, then writes a colleague-friendly
Excel workbook under missing_products/out/.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from tongtu_data import (
    latest_bom_path,
    latest_mainline_audit_path,
    latest_tongtu_zip_path,
    load_mainline_mapping,
    load_tongtu_aliases,
    norm,
)

OUT = HERE / "out"


def parse_products(value) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [x.strip() for x in str(value).split("|") if x.strip()]


def parse_int(value) -> int:
    text = norm(value)
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def load_bom_map(bom_path: Path) -> dict[str, list[dict]]:
    df = pd.read_excel(bom_path, sheet_name=0, dtype=str)
    result: dict[str, list[dict]] = {}
    for _, row in df.iterrows():
        code = norm(row.get("产品编号"))
        if not code:
            continue
        result.setdefault(code, []).append(row.to_dict())
    return result


def product_summary(bom_map: dict[str, list[dict]], codes: list[str]) -> tuple[str, str, str]:
    names: list[str] = []
    costs: list[str] = []
    refs: list[str] = []
    for code in codes:
        rows = bom_map.get(code, [])
        if rows:
            names.append(norm(rows[0].get("产品名称")))
            costs.append(norm(rows[0].get("绍兴总成本")))
            refs.append(norm(rows[0].get("成品参考采购价")))
        else:
            names.append("")
            costs.append("")
            refs.append("")
    return "; ".join(names), "; ".join(costs), "; ".join(refs)


def spu_from_code(code: str) -> str:
    return str(code).split("-", 1)[0] if code else ""


def build_mapping_rows(
    audit: pd.DataFrame,
    aliases: pd.DataFrame,
    bom_map: dict[str, list[dict]],
) -> pd.DataFrame:
    alias_by_sku: dict[str, set[str]] = {}
    if not aliases.empty:
        for _, row in aliases.iterrows():
            alias_by_sku.setdefault(norm(row.get("通途SKU")), set()).add(norm(row.get("SKU别名")))

    rows: list[dict] = []
    sku_to_products: dict[str, set[str]] = {}
    for _, r in audit.iterrows():
        sku = norm(r.get("通途SKU"))
        products = parse_products(r.get("EN精确登记产品"))
        sku_to_products[sku] = set(products)
    product_to_skus: dict[str, set[str]] = {}
    for sku, products in sku_to_products.items():
        for p in products:
            product_to_skus.setdefault(p, set()).add(sku)

    for _, r in audit.iterrows():
        sku = norm(r.get("通途SKU"))
        base = norm(r.get("清理后SKU"))
        products = parse_products(r.get("EN精确登记产品"))
        names, costs, refs = product_summary(bom_map, products)
        aliases_out = sorted(alias_by_sku.get(sku, set()) | alias_by_sku.get(base, set()))
        sellfox_sku = norm(r.get("赛狐已存在SKU")) or norm(r.get("赛狐缺失SKU"))
        first_code = products[0] if products else ""
        n_products = parse_int(r.get("EN精确登记次数"))
        if n_products <= 1 and len(products) > 1:
            n_products = len(products)
        if n_products > 1:
            relation = "一对多"
        elif len(product_to_skus.get(first_code, set())) > 1:
            relation = "多对一"
        else:
            relation = "唯一"
        rows.append(
            {
                "通途SKU": sku,
                "SKU别名": "; ".join(aliases_out),
                "基码": base,
                "可用库存": norm(r.get("可用库存")),
                "仓库": norm(r.get("仓库")),
                "货品名称": norm(r.get("货品名称")),
                "分类": norm(r.get("分类")),
                "EN登记状态": norm(r.get("EN登记状态")),
                "EN精确登记次数": str(n_products) if n_products else "",
                "EN产品编号": " | ".join(products),
                "EN物料名称": names,
                "EN客户物料号": sku,
                "EN绍兴总成本": costs,
                "EN成品参考采购价": refs,
                "赛狐SPU": spu_from_code(first_code),
                "赛狐SKU": sellfox_sku,
                "关系类型": relation,
                "匹配依据": norm(r.get("匹配依据")),
                "赛狐产品SKU状态": norm(r.get("赛狐产品SKU状态")),
                "建议动作": norm(r.get("建议动作")),
            }
        )
    return pd.DataFrame(rows)


def build_many_to_one(rows: pd.DataFrame, bom_map: dict[str, list[dict]]) -> pd.DataFrame:
    out: list[dict] = []
    grouped: dict[str, set[str]] = {}
    for _, r in rows.iterrows():
        for code in parse_products(r.get("EN产品编号")):
            grouped.setdefault(code, set()).add(norm(r.get("通途SKU")))
    for code, skus in sorted(grouped.items()):
        if len(skus) <= 1:
            continue
        names, _, _ = product_summary(bom_map, [code])
        sellfox = next(
            (
                norm(r.get("赛狐SKU"))
                for _, r in rows.iterrows()
                if code in parse_products(r.get("EN产品编号")) and norm(r.get("赛狐SKU"))
            ),
            "",
        )
        out.append(
            {
                "EN产品编号": code,
                "EN物料名称": names,
                "通途SKU数": len(skus),
                "通途SKU列表": "; ".join(sorted(skus)),
                "赛狐SKU": sellfox,
                "关系类型": "多对一",
                "建议动作": "保留并核对库存归属，不做自动去重",
            }
        )
    return pd.DataFrame(out)


def build_deferred(audit_path: Path) -> pd.DataFrame:
    xl = pd.ExcelFile(audit_path)
    frames: list[pd.DataFrame] = []
    for sheet, label in (("套件暂缓", "套件暂缓"), ("其他非产品项暂缓", "其他非产品项暂缓")):
        if sheet not in xl.sheet_names:
            continue
        df = xl.parse(sheet, dtype=str)
        df = df[df["通途SKU"].notna() & (df["通途SKU"].astype(str).str.strip() != "")].copy()
        df["暂缓类型"] = label
        frames.append(df)
    if not frames:
        return pd.DataFrame({"说明": ["无"]})
    return pd.concat(frames, ignore_index=True)


FIELD_DESCRIPTIONS = [
    ("通途SKU", "完整通途 SKU，含 -Cover/-Foam 等后缀；EN 客户物料号以完整码为准"),
    ("SKU别名", "通途简易模板导出中该 SKU 的别名，分号分隔"),
    ("基码", "去掉 -Cover/-Foam 等后缀后的候选码，只用于定位，不算已登记"),
    ("可用库存", "通途合并库存结存清单中的可用库存"),
    ("仓库", "有库存的仓库列表"),
    ("货品名称", "通途货品名称/规格"),
    ("分类", "主线审计分类"),
    ("EN登记状态", "已精确登记/仅基码匹配/真正未登记等"),
    ("EN精确登记次数", "完整通途 SKU 在 EN 产品 customer_items 中的精确登记次数"),
    ("EN产品编号", "对应 EN 产品成品变体 item_code，多个用 | 分隔"),
    ("EN物料名称", "EN 产品名称，来自最新 BOM Cost List"),
    ("EN客户物料号", "当前通途完整 SKU 作为 EN 客户物料号"),
    ("EN绍兴总成本", "来自 BOM Cost List 的绍兴总成本"),
    ("EN成品参考采购价", "来自 BOM Cost List 的成品参考采购价"),
    ("赛狐SPU", "EN 产品编号首段，通常为赛狐 SPU"),
    ("赛狐SKU", "赛狐中对应的 EN 产品 SKU（已存在或缺失）"),
    ("关系类型", "唯一/一对多/多对一，均保留不自动去重"),
    ("匹配依据", "审计中该行匹配/候选的依据"),
    ("赛狐产品SKU状态", "赛狐回读状态"),
    ("建议动作", "本轮建议，写入前需用户确认"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audit-xlsx", type=Path, default=None)
    ap.add_argument("--bom-xlsx", type=Path, default=None)
    ap.add_argument("--tongtu-zip", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    audit_path = args.audit_xlsx or latest_mainline_audit_path()
    bom_path = args.bom_xlsx or latest_bom_path()
    zip_path = args.tongtu_zip or latest_tongtu_zip_path()
    if not audit_path:
        print("未找到最新主线审计工作簿")
        return 1
    if not bom_path:
        print("未找到最新 EN BOM Cost List")
        return 1

    print(f"审计底表: {audit_path.name}")
    print(f"BOM: {bom_path.name if bom_path else '未找到'}")
    print(f"通途导出: {zip_path.name if zip_path else '未找到'}")

    audit = load_mainline_mapping(audit_path)
    bom_map = load_bom_map(bom_path)
    aliases = load_tongtu_aliases(zip_path) if zip_path else pd.DataFrame()
    print(f"映射全量输入: {len(audit)} 行；通途别名: {len(aliases)} 行")

    rows = build_mapping_rows(audit, aliases, bom_map)
    many_one = build_many_to_one(rows, bom_map)
    one_many = rows[rows["关系类型"] == "一对多"].copy()
    deferred = build_deferred(audit_path)

    summary = pd.DataFrame(
        [
            ("通途有库存 SKU", len(rows)),
            ("EN 产品精确登记", int((rows["EN登记状态"] == "已精确登记").sum())),
            ("一对多关系", len(one_many)),
            ("多对一 EN 产品", len(many_one)),
            ("套件暂缓", int((deferred["暂缓类型"] == "套件暂缓").sum()) if len(deferred) else 0),
            ("其他非产品项暂缓", int((deferred["暂缓类型"] == "其他非产品项暂缓").sum()) if len(deferred) else 0),
            ("审计底表时间", audit_path.stem),
            ("BOM 时间", bom_path.stem if bom_path else ""),
            ("通途导出时间", zip_path.stem if zip_path else ""),
            ("生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ],
        columns=["指标", "值"],
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or (OUT / f"通途EN赛狐映射表_{stamp}.xlsx")
    OUT.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="汇总", index=False)
        rows.to_excel(writer, sheet_name="映射全量", index=False)
        one_many.to_excel(writer, sheet_name="一对多", index=False)
        many_one.to_excel(writer, sheet_name="多对一", index=False)
        deferred.to_excel(writer, sheet_name="暂缓_待确认", index=False)
        pd.DataFrame(FIELD_DESCRIPTIONS, columns=["字段", "说明"]).to_excel(
            writer, sheet_name="字段说明", index=False
        )

    print(f"已生成: {out_path}")
    print(f"映射全量={len(rows)} 一对多={len(one_many)} 多对一={len(many_one)} 暂缓={len(deferred)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
