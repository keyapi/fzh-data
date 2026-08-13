# -*- coding: utf-8 -*-
"""美中 DANEEY 通途订单 PP 棉用量估算。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

PP_FILL_NAME = "PP棉-7D51-加硅-新料"
KNOWN_SKU_SUFFIXES = ["-淘汰", "-out", "-Cover", "-Foam", "-PPCotton", "-1"]

DANEEY_WH_KEYWORDS = ("DANEEY", "USTX", "美中")
WAREHOUSE_LABELS = {
    "FZH-DANEEY-皮壳仓库": "皮壳仓",
    "FZH-DANEEY-半成品仓": "半成品仓",
    "FZH-DANEEY-成品仓": "成品仓",
    "FZH-DANEEY-退货产品仓": "退货仓",
}


def clean_sku(sku: str) -> str:
    s = str(sku).strip()
    for suffix in KNOWN_SKU_SUFFIXES:
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s


def is_daneey_warehouse(name: str) -> bool:
    text = str(name).strip().upper()
    return any(k.upper() in text for k in DANEEY_WH_KEYWORDS)


def infer_ship_type(warehouse: str, order_ship_type: Any) -> str:
    if pd.notna(order_ship_type) and str(order_ship_type).strip():
        return str(order_ship_type).strip()
    return WAREHOUSE_LABELS.get(str(warehouse).strip(), str(warehouse).strip())


def build_bom_lookup(bom: pd.DataFrame) -> tuple[dict[str, pd.Series], list[dict[str, str]]]:
    """通途 SKU / 去后缀 SKU → BOM 行；重复客户物料号保留首条并记录。"""
    lookup: dict[str, pd.Series] = {}
    duplicates: list[dict[str, str]] = []
    for _, row in bom.iterrows():
        cust = str(row.get("客户物料号", "")).strip()
        if not cust or cust.lower() == "nan":
            continue
        for key in (cust, clean_sku(cust)):
            if not key:
                continue
            if key in lookup:
                duplicates.append(
                    {
                        "客户物料号": cust,
                        "已有产品编号": str(lookup[key].get("产品编号", "")),
                        "重复产品编号": str(row.get("产品编号", "")),
                    }
                )
                continue
            lookup[key] = row
    return lookup, duplicates


def resolve_pp_kg(row: pd.Series | None) -> tuple[float | None, str | None, str | None]:
    """返回 (单件 kg, 来源说明, 填充物1名称)。"""
    if row is None:
        return None, None, None

    fill_name = str(row.get("填充物1名称", "")).strip()
    qty = pd.to_numeric(row.get("填充物1数量"), errors="coerce")
    ustx_pkg = str(row.get("美中包装成品, USTX 编号", "")).strip()
    sx_pkg = str(row.get("绍兴包装成品, 编号", "")).strip()

    if fill_name != PP_FILL_NAME or pd.isna(qty):
        return None, None, fill_name or None

    if ustx_pkg and ustx_pkg.lower() != "nan":
        source = "美中包装成品BOM(填充物1)"
    elif sx_pkg and sx_pkg.lower() != "nan":
        source = "绍兴包装成品BOM(填充物1)"
    else:
        source = "产品BOM(填充物1)"

    return float(qty), source, fill_name


@dataclass
class PpCottonReport:
    detail: pd.DataFrame
    summary_rows: list[dict[str, Any]]
    by_warehouse: pd.DataFrame
    by_ship_type: pd.DataFrame
    unmatched: pd.DataFrame
    matched_no_pp: pd.DataFrame
    duplicate_customers: pd.DataFrame


def estimate_pp_cotton(
    orders: pd.DataFrame,
    bom: pd.DataFrame,
    *,
    warehouse_filter: str = "daneey",
    month: str | None = None,
) -> PpCottonReport:
    required = {"通途SKU", "发货仓库", "发货数量"}
    missing = required - set(orders.columns)
    if missing:
        raise ValueError(f"订单表缺少列: {', '.join(sorted(missing))}")

    df = orders.copy()
    if warehouse_filter == "daneey":
        df = df[df["发货仓库"].map(is_daneey_warehouse)].copy()

    if month:
        ship_dates = pd.to_datetime(df["发货日期"], errors="coerce")
        target = pd.Period(month, freq="M")
        df = df[ship_dates.dt.to_period("M") == target].copy()

    bom_lookup, dup_records = build_bom_lookup(bom)
    rows: list[dict[str, Any]] = []

    for _, order in df.iterrows():
        sku = str(order["通途SKU"]).strip()
        qty = float(pd.to_numeric(order["发货数量"], errors="coerce") or 0)
        bom_row = bom_lookup.get(sku)
        if bom_row is None:
            bom_row = bom_lookup.get(clean_sku(sku))

        pp_each, pp_source, fill_name = resolve_pp_kg(bom_row)
        has_pp = pp_each is not None
        warehouse = str(order["发货仓库"]).strip()
        ship_type = infer_ship_type(warehouse, order.get("当月给分公司发货类型"))

        rows.append(
            {
                "发货日期": order.get("发货日期"),
                "订单号": order.get("订单号"),
                "通途SKU": sku,
                "通途SKU_去后缀": clean_sku(sku),
                "发货仓库": warehouse,
                "推断发货类型": ship_type,
                "当月给分公司发货类型": order.get("当月给分公司发货类型"),
                "发货数量": qty,
                "匹配BOM": bom_row is not None,
                "产品编号": None if bom_row is None else bom_row.get("产品编号"),
                "产品名称": None if bom_row is None else bom_row.get("产品名称"),
                "绍兴发货方式": None if bom_row is None else bom_row.get("绍兴发货方式"),
                "美中包装成品编号": None if bom_row is None else bom_row.get("美中包装成品, USTX 编号"),
                "绍兴包装成品编号": None if bom_row is None else bom_row.get("绍兴包装成品, 编号"),
                "填充物1名称": fill_name,
                "单件PP棉_kg": pp_each,
                "PP棉来源": pp_source,
                "PP棉合计_kg": (pp_each or 0) * qty if has_pp else None,
            }
        )

    detail = pd.DataFrame(rows)
    total_lines = len(detail)
    total_qty = float(detail["发货数量"].sum()) if total_lines else 0.0
    matched_lines = int(detail["匹配BOM"].sum())
    pp_lines = int(detail["单件PP棉_kg"].notna().sum())
    pp_total = float(detail["PP棉合计_kg"].fillna(0).sum())

    wh_stats = (
        detail.groupby("发货仓库", dropna=False)
        .agg(
            订单行数=("通途SKU", "count"),
            发货数量=("发货数量", "sum"),
            PP棉合计_kg=("PP棉合计_kg", lambda s: float(s.fillna(0).sum())),
            有PP棉行数=("单件PP棉_kg", lambda s: int(s.notna().sum())),
        )
        .reset_index()
    )

    ship_stats = (
        detail.groupby("推断发货类型", dropna=False)
        .agg(
            订单行数=("通途SKU", "count"),
            发货数量=("发货数量", "sum"),
            PP棉合计_kg=("PP棉合计_kg", lambda s: float(s.fillna(0).sum())),
            有PP棉行数=("单件PP棉_kg", lambda s: int(s.notna().sum())),
        )
        .reset_index()
        .sort_values("PP棉合计_kg", ascending=False)
    )

    unmatched = (
        detail[~detail["匹配BOM"]]
        .groupby("通途SKU", as_index=False)
        .agg(订单行数=("通途SKU", "count"), 发货数量=("发货数量", "sum"))
        .sort_values("发货数量", ascending=False)
    )

    matched_no_pp = (
        detail[detail["匹配BOM"] & detail["单件PP棉_kg"].isna()]
        .groupby("通途SKU", as_index=False)
        .agg(
            订单行数=("通途SKU", "count"),
            发货数量=("发货数量", "sum"),
            填充物1名称=("填充物1名称", "first"),
            产品名称=("产品名称", "first"),
        )
        .sort_values("发货数量", ascending=False)
    )

    shell_wh_pp = float(
        detail[detail["发货仓库"].isin(["FZH-DANEEY-皮壳仓库", "FZH-DANEEY-半成品仓"])]["PP棉合计_kg"]
        .fillna(0)
        .sum()
    )

    summary_rows = [
        {"指标": "订单行数", "值": total_lines},
        {"指标": "发货数量合计", "值": total_qty},
        {"指标": "匹配BOM行数", "值": matched_lines},
        {"指标": "未匹配BOM行数", "值": total_lines - matched_lines},
        {"指标": "有PP棉行数", "值": pp_lines},
        {"指标": "匹配但无PP棉行数", "值": matched_lines - pp_lines},
        {"指标": "PP棉合计(kg)", "值": round(pp_total, 2)},
        {"指标": "PP棉合计(吨)", "值": round(pp_total / 1000, 3)},
        {
            "指标": "皮壳仓+半成品仓PP棉(kg)",
            "值": round(shell_wh_pp, 2),
            "说明": "现场填充更可能发生在皮壳/半成品仓",
        },
        {"指标": "BOM重复客户物料号", "值": len(dup_records)},
    ]

    return PpCottonReport(
        detail=detail,
        summary_rows=summary_rows,
        by_warehouse=wh_stats,
        by_ship_type=ship_stats,
        unmatched=unmatched,
        matched_no_pp=matched_no_pp,
        duplicate_customers=pd.DataFrame(dup_records),
    )


def load_bom(path: Path | str) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    return pd.read_csv(path, dtype=str, low_memory=False)


def write_pp_cotton_workbook(report: PpCottonReport, out_path: Path | str) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        pd.DataFrame(report.summary_rows).to_excel(writer, sheet_name="00_汇总", index=False)
        report.by_warehouse.to_excel(writer, sheet_name="01_按发货仓库", index=False)
        report.by_ship_type.to_excel(writer, sheet_name="02_按发货类型", index=False)
        report.detail.to_excel(writer, sheet_name="03_订单明细", index=False)
        if len(report.unmatched):
            report.unmatched.to_excel(writer, sheet_name="04_未匹配SKU", index=False)
        if len(report.matched_no_pp):
            report.matched_no_pp.to_excel(writer, sheet_name="05_匹配无PP棉", index=False)
        if len(report.duplicate_customers):
            report.duplicate_customers.to_excel(writer, sheet_name="06_BOM重复客户码", index=False)
    return out_path
