# -*- coding: utf-8 -*-
"""
ERPNext 物料导出（含通途客户物料号子表）与「通途SKU别名炸开」结果配对。

- 对 物料编码 / 物料组 等主表列做前向填充（纵向一对多时空行补齐）。
- 客户物料号 (客户物料) 对应通途里的主 SKU 或炸开后的 SKU别名，用于关联。
- 输出列：物料组、物料编码、客户物料号 (客户物料)、通途主SKU、SKU别名、商品名称。

- 按「物料属性」Sheet1 的 款式ID / 在售 / 还有库存（与 erpnext_to_saihu 一致）拆分：在售=1 →
  赛狐配对导入_在售.xlsx；不在售再分为 赛狐配对导入_不在售有库存.xlsx 与 赛狐配对导入_不在售无库存.xlsx。

- 合并前：同一 物料编码 下重复的 客户物料号 (客户物料) 去重（忽略 客户组 等差异）。
- 合并后不改结果，另写检验报告：同一 客户物料号 若挂在多个不同 物料编码 上则列出（误操作排查）。
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from typing import Any

import pandas as pd

from erpnext_to_saihu import _default_spu_from_sku, load_spu_status_maps

# ERP 导出列名（与 Excel 表头一致）
COL_ERP_SKU = "物料编码"
COL_ERP_GROUP = "物料组"
COL_CUSTOMER = "客户物料号 (客户物料)"

# 通途炸开表（tongtu_sku_explode 输出）
COL_TT_MAIN = "SKU"
COL_TT_ALIAS = "SKU别名"
COL_TT_NAME = "商品名称"
# 输出里主 SKU 使用更明确的列名（与通途炸开表中的「SKU」同义）
COL_OUT_TT_MAIN = "通途主SKU"

DEFAULT_TONGTU = "通途SKU别名炸开.xlsx"
DEFAULT_OUT_COMBINED = "ERP通途SKU配对.xlsx"
DEFAULT_ONSALE = "赛狐配对导入_在售.xlsx"
DEFAULT_OFF_STOCK = "赛狐配对导入_不在售有库存.xlsx"
DEFAULT_OFF_NOSTOCK = "赛狐配对导入_不在售无库存.xlsx"
DEFAULT_CONFLICT_REPORT = "ERP通途客户物料号_跨物料编码冲突检验.xlsx"


def _norm(x: Any) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def prepare_erp_customer_rows(erp: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    ffill 主表列 → 去掉空客户物料号 → 按 (物料编码, 客户物料号) 去重。
    返回 (清洗后的 ERP 行, 因重复去掉的行数)。
    """
    out = ffill_erp_master_columns(erp)
    out["_k_erp_sku"] = out[COL_ERP_SKU].map(_norm)
    out["_k_cust"] = out[COL_CUSTOMER].map(_norm)
    out = out[out["_k_cust"] != ""].copy()
    before = len(out)
    out = out.drop_duplicates(subset=["_k_erp_sku", "_k_cust"], keep="first")
    dropped = before - len(out)
    out = out.drop(columns=["_k_erp_sku", "_k_cust"], errors="ignore")
    return out, dropped


def build_cross_item_conflict_report(erp_deduped: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    去重后的 ERP：若同一 客户物料号 对应多个不同 物料编码，则视为潜在冲突。
    返回 (汇总表, 明细表)。
    """
    tmp = erp_deduped.copy()
    tmp["_k_cust"] = tmp[COL_CUSTOMER].map(_norm)
    tmp["_k_erp_sku"] = tmp[COL_ERP_SKU].map(_norm)
    n_distinct_item = tmp.groupby("_k_cust")["_k_erp_sku"].nunique()
    bad_customers = n_distinct_item[n_distinct_item > 1].index.tolist()
    if not bad_customers:
        empty_summary = pd.DataFrame(
            columns=["客户物料号 (客户物料)", "涉及物料编码数量", "物料编码列表"]
        )
        empty_detail = pd.DataFrame(
            columns=["客户物料号 (客户物料)", "物料编码", "物料组"]
        )
        return empty_summary, empty_detail

    sub = tmp[tmp["_k_cust"].isin(bad_customers)].copy()
    detail = sub[
        [COL_CUSTOMER, COL_ERP_SKU, COL_ERP_GROUP]
    ].rename(
        columns={
            COL_CUSTOMER: "客户物料号 (客户物料)",
            COL_ERP_SKU: "物料编码",
            COL_ERP_GROUP: "物料组",
        }
    )
    detail = detail.sort_values(
        by=["客户物料号 (客户物料)", "物料编码"], kind="mergesort"
    ).reset_index(drop=True)

    rows_sum: list[dict[str, Any]] = []
    for ck in sorted(bad_customers):
        codes = sorted(sub.loc[sub["_k_cust"] == ck, "_k_erp_sku"].unique())
        rows_sum.append(
            {
                "客户物料号 (客户物料)": ck,
                "涉及物料编码数量": len(codes),
                "物料编码列表": ";".join(codes),
            }
        )
    summary = pd.DataFrame(rows_sum)
    return summary, detail


def ffill_erp_master_columns(df: pd.DataFrame) -> pd.DataFrame:
    """主表字段在子表多行时仅首行有值：向下填充。"""
    out = df.copy()
    for c in (COL_ERP_SKU, COL_ERP_GROUP, "物料名称", "禁用", "有多种规格"):
        if c in out.columns:
            # 保留原类型尽量用 ffill；字符串与数字混合时统一为前向填充
            out[c] = out[c].ffill()
    return out


def tongtu_to_long_match_rows(tt: pd.DataFrame) -> pd.DataFrame:
    """
    将通途表扩成「匹配键」行：同一行可用 主SKU 或 SKU别名 与 ERP 客户物料号对齐。
    当主 SKU 与 SKU别名 相同时只保留一条，避免 merge 翻倍。
    """
    rows: list[dict[str, Any]] = []
    for _, r in tt.iterrows():
        base = {
            COL_TT_MAIN: r[COL_TT_MAIN],
            COL_TT_ALIAS: r[COL_TT_ALIAS],
            COL_TT_NAME: r[COL_TT_NAME] if COL_TT_NAME in tt.columns else pd.NA,
        }
        m_main = _norm(r[COL_TT_MAIN])
        m_alias = _norm(r[COL_TT_ALIAS])
        rows.append({**base, "_match_key": m_main})
        if m_alias and m_alias != m_main:
            rows.append({**base, "_match_key": m_alias})
    return pd.DataFrame(rows)


def bridge_erp_tongtu(
    erp: pd.DataFrame,
    tt: pd.DataFrame,
    *,
    erp_already_prepared: bool = False,
) -> pd.DataFrame:
    """若 erp_already_prepared=True，则 erp 须已是 prepare_erp_customer_rows 的结果。"""
    for c in (COL_ERP_SKU, COL_ERP_GROUP, COL_CUSTOMER):
        if c not in erp.columns:
            raise ValueError(f"ERP 表缺少列 {c!r}，当前: {list(erp.columns)}")
    for c in (COL_TT_MAIN, COL_TT_ALIAS):
        if c not in tt.columns:
            raise ValueError(f"通途表缺少列 {c!r}，当前: {list(tt.columns)}")

    if not erp_already_prepared:
        erp, _ = prepare_erp_customer_rows(erp)
    else:
        erp = erp.copy()
    erp["_客户物料_key"] = erp[COL_CUSTOMER].map(_norm)

    tt_long = tongtu_to_long_match_rows(tt)
    tt_long["_match_key"] = tt_long["_match_key"].map(_norm)

    merged = pd.merge(
        erp,
        tt_long,
        left_on="_客户物料_key",
        right_on="_match_key",
        how="left",
        suffixes=("", "_tt"),
    )
    merged = merged.drop(columns=["_客户物料_key", "_match_key"], errors="ignore")

    if COL_TT_MAIN in merged.columns:
        merged = merged.rename(columns={COL_TT_MAIN: COL_OUT_TT_MAIN})

    # 输出列顺序与命名
    out_cols = [
        COL_ERP_GROUP,
        COL_ERP_SKU,
        COL_CUSTOMER,
        COL_OUT_TT_MAIN,
        COL_TT_ALIAS,
        COL_TT_NAME,
    ]
    for c in out_cols:
        if c not in merged.columns:
            merged[c] = pd.NA
    return merged[out_cols]


def split_paired_by_onsale_and_stock(
    paired: pd.DataFrame,
    spu_map: dict[str, int],
    spu_stock: dict[str, bool],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, int]:
    """
    在售=1 → 在售；在售=0 且 还有库存=「有」→ 不在售有库存；其余不在售及未映射款式 → 无库存。
    款式ID = 物料编码首段（与 erpnext_to_saihu 一致）。
    返回 (on_df, off_has_stock_df, off_no_stock_df, n_spu_not_in_map)。
    """
    spu = paired[COL_ERP_SKU].map(lambda x: _default_spu_from_sku(x) if pd.notna(x) else "")
    status = spu.map(spu_map)
    stock_yes = spu.map(lambda s: spu_stock.get(s, False))

    on_sale = paired[status == 1].copy()
    in_map = status.notna()
    n_missing = int((~in_map).sum())
    off_has = paired[(status == 0) & stock_yes].copy()
    off_no = paired[((status == 0) & (~stock_yes)) | status.isna()].copy()
    return on_sale, off_has, off_no, n_missing


def main() -> None:
    ap = argparse.ArgumentParser(description="ERP 客户物料号 ↔ 通途 SKU / 别名 配对")
    ap.add_argument(
        "erp_path",
        nargs="?",
        default=None,
        help="ERPNext 导出 xlsx（默认：含「物料导出」+「通途SKU」，排除别名/炸开/配对）",
    )
    ap.add_argument(
        "-t",
        "--tongtu",
        default=None,
        help=f"通途炸开结果（默认: {DEFAULT_TONGTU}）",
    )
    ap.add_argument(
        "--spu-status",
        default=None,
        metavar="PATH",
        help="物料属性 xlsx（Sheet1 款式ID/在售/还有库存；默认：最新 *物料属性*.xlsx）",
    )
    ap.add_argument(
        "--out-onsale",
        default=None,
        help=f"在售输出（默认: {DEFAULT_ONSALE}）",
    )
    ap.add_argument(
        "--out-offsale-stock",
        default=None,
        help=f"不在售有库存（默认: {DEFAULT_OFF_STOCK}）",
    )
    ap.add_argument(
        "--out-offsale-nostock",
        default=None,
        help=f"不在售无库存 / 未映射（默认: {DEFAULT_OFF_NOSTOCK}）",
    )
    ap.add_argument(
        "--write-combined",
        action="store_true",
        help=f"额外写出未拆分的全量表（{DEFAULT_OUT_COMBINED} 或见 --output-combined）",
    )
    ap.add_argument(
        "--output-combined",
        default=None,
        metavar="PATH",
        help=f"与 --write-combined 配合，指定全量表路径（默认: {DEFAULT_OUT_COMBINED}）",
    )
    ap.add_argument(
        "--conflict-report",
        default=None,
        metavar="PATH",
        help=f"跨物料编码冲突检验 xlsx（默认: {DEFAULT_CONFLICT_REPORT}）；无冲突时仍生成空表",
    )
    ap.add_argument(
        "--no-conflict-report",
        action="store_true",
        help="不写冲突检验报告",
    )
    ap.add_argument("--sheet-erp", default=0, help="ERP 工作表名或索引（默认 0）")
    ap.add_argument("--sheet-tongtu", default=0, help="通途表工作表（默认 0）")
    args = ap.parse_args()

    base = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base)

    erp_path = args.erp_path
    if not erp_path:
        # 必须与通途输出「通途SKU别名炸开.xlsx」区分：要求物料导出且含通途SKU
        cands = [
            f
            for f in glob.glob("*.xlsx")
            if not f.startswith("~$")
            and "物料导出" in f
            and "通途SKU" in f
            and "别名" not in f
            and "炸开" not in f
            and "配对" not in f
        ]
        if not cands:
            print(
                '未找到 ERP 导出（文件名需含「物料导出」与「通途SKU」，且非别名/炸开/配对）。请指定 erp_path',
                file=sys.stderr,
            )
            sys.exit(1)
        erp_path = sorted(cands, key=os.path.getmtime)[-1]

    tongtu_path = args.tongtu or os.path.join(base, DEFAULT_TONGTU)
    if not os.path.isfile(tongtu_path):
        print(f"找不到通途文件: {tongtu_path}", file=sys.stderr)
        sys.exit(1)

    spu_path = args.spu_status
    if not spu_path:
        cands = [f for f in glob.glob("*物料属性*.xlsx") if not f.startswith("~$")]
        if not cands:
            print("未找到 *物料属性*.xlsx，请用 --spu-status 指定（款式ID/在售）。", file=sys.stderr)
            sys.exit(1)
        spu_path = sorted(cands, key=os.path.getmtime)[-1]

    out_on = args.out_onsale or os.path.join(base, DEFAULT_ONSALE)
    out_off_stock = args.out_offsale_stock or os.path.join(base, DEFAULT_OFF_STOCK)
    out_off_nostock = args.out_offsale_nostock or os.path.join(base, DEFAULT_OFF_NOSTOCK)
    out_combined = args.output_combined or os.path.join(base, DEFAULT_OUT_COMBINED)

    sheet_erp: str | int = args.sheet_erp
    if isinstance(sheet_erp, str) and str(sheet_erp).isdigit():
        sheet_erp = int(sheet_erp)

    df_erp = pd.read_excel(erp_path, sheet_name=sheet_erp, header=0)
    df_tt = pd.read_excel(tongtu_path, sheet_name=args.sheet_tongtu, header=0)

    erp_dedup, n_dup = prepare_erp_customer_rows(df_erp)
    if n_dup:
        print(f"  ERP 内 (物料编码+客户物料号) 去重去掉行数: {n_dup}")

    if not args.no_conflict_report:
        rep_path = args.conflict_report or os.path.join(base, DEFAULT_CONFLICT_REPORT)
        sum_df, det_df = build_cross_item_conflict_report(erp_dedup)
        with pd.ExcelWriter(rep_path, engine="openpyxl") as w:
            sum_df.to_excel(w, sheet_name="冲突汇总", index=False)
            det_df.to_excel(w, sheet_name="冲突明细", index=False)
        n_conf = len(sum_df)
        print(f"  冲突检验: {rep_path}（跨物料编码的客户物料号: {n_conf} 个）")

    result = bridge_erp_tongtu(erp_dedup, df_tt, erp_already_prepared=True)
    n_miss = result[COL_OUT_TT_MAIN].isna().sum()

    spu_map, spu_stock = load_spu_status_maps(spu_path, sheet_name="Sheet1")
    on_df, off_has, off_no, n_missing = split_paired_by_onsale_and_stock(
        result, spu_map, spu_stock
    )

    on_df.to_excel(out_on, index=False, engine="openpyxl")
    off_has.to_excel(out_off_stock, index=False, engine="openpyxl")
    off_no.to_excel(out_off_nostock, index=False, engine="openpyxl")

    print(
        f"在售: {len(on_df)} -> {out_on}\n"
        f"不在售有库存: {len(off_has)} -> {out_off_stock}\n"
        f"不在售无库存(含未映射): {len(off_no)} -> {out_off_nostock}\n"
        f"物料属性: {spu_path} ({len(spu_map)} unique 款式ID)\n"
        f"  *SPU 未在表中: {n_missing} 行（进无库存文件）"
    )
    if args.write_combined:
        result.to_excel(out_combined, index=False, engine="openpyxl")
        print(f"全量: {len(result)} -> {out_combined}")
    if n_miss:
        print(f"  未匹配到通途的行数（「{COL_OUT_TT_MAIN}」为空）: {n_miss}")


if __name__ == "__main__":
    main()
