"""
build_saihu_stock_init.py
通途库存 + EN BOM 成本 → 赛狐库存初始值导入文件

数据流:
  通途库存(df2) ──left merge── EN BOM成本(df3) ──filter── 赛狐SKU(df4) ──agg── 模板输出
    SKU→客户物料号             产品编号→赛狐SKU           按(仓库+SKU)聚合

使用:
  python build_saihu_stock_init.py
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

os.chdir(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = Path("数据源")
OUT_BASE = Path("out")
ANCHOR_FILE = OUT_BASE / "上次导入_基准.xlsx"

# ── 通途仓库 → 赛狐仓库 ──────────────────────────────
WAREHOUSE_MAP = {
    "CENTRADE": "CENTRADE",
    "FZHPoland-covers": "POLAND",
    "FZH-DANEEY-皮壳仓库": "DANEEY",
    "FZH-DANEEY-退货产品仓": "DANEEY",
    "FZH-DANEEY-成品仓": "DANEEY",
    "FZH-DANEEY-半成品仓": "DANEEY",
}

# ── (绍兴发货方式, 赛狐仓库) → EN BOM 成本列名 ─────────
COST_COLUMN_MAP = {
    ("皮壳", "CENTRADE"): "发皮壳尾程前成本, 美东USNJ",
    ("半成品", "CENTRADE"): "发皮壳尾程前成本, 美东USNJ",
    ("成品", "CENTRADE"): "发成品尾程前成本, 美东USNJ",
    ("皮壳", "DANEEY"): "发皮壳尾程前成本, 美中USTX",
    ("半成品", "DANEEY"): "发皮壳尾程前成本, 美中USTX",
    ("成品", "DANEEY"): "发成品尾程前成本, 美中USTX",
    ("皮壳", "POLAND"): "发皮壳尾程前成本, 波兰PL",
    ("半成品", "POLAND"): "发皮壳尾程前成本, 波兰PL",
    ("成品", "POLAND"): "发成品尾程前成本, 波兰PL",
}

# ── 赛狐模板输出列（工作表名必须为 商品）─────────────────
SHEET_MAIN = "商品"
TEMPLATE_COLS = [
    "*所属仓库", "*SKU", "店铺", "FNSKU", "品名",
    "可用库存", "次品库存", "*采购成本", "单位费用", "上架时间"
]

# ── 问题报告 sheet 名 ─────────────────────────────────
SHEET_SUMMARY = "汇总"
SHEET_TT_UNMATCHED = "通途SKU_未匹配EN客户物料号"
SHEET_SX_NOTFOUND = "不在赛狐商品列表的SKU"
SHEET_ZERO_COST = "采购成本为0"
SHEET_ZERO_QTY = "可用库存为0"
SHEET_EN_EXCLUDED = "EN数据清洗排除"
SHEET_WH_STATS = "每仓统计"
SHEET_COST_BORROW = "成本借用记录"

SHEETS_ORDER = [
    SHEET_TT_UNMATCHED,
    SHEET_SX_NOTFOUND,
    SHEET_ZERO_COST,
    SHEET_ZERO_QTY,
    SHEET_EN_EXCLUDED,
    SHEET_COST_BORROW,
    SHEET_WH_STATS,
]


def auto_select(pattern, directory=None):
    """Auto-select latest file matching pattern (exclude ~$ lock files)."""
    d = Path(directory) if directory else DATA_DIR
    candidates = [f for f in d.glob(pattern) if not f.name.startswith("~$")]
    if not candidates:
        raise FileNotFoundError(f"未找到匹配 '{pattern}' 的文件于 {d}")
    return max(candidates, key=lambda f: f.stat().st_mtime)


def _borrow_costs(df: pd.DataFrame, cost_columns: list[str]) -> tuple[pd.DataFrame, list[dict]]:
    """按重量模板键，每列内独立借用：同键同列中 0 值借用 >0 值。"""
    borrow_records: list[dict] = []

    if "重量模板, 编号" not in df.columns:
        return df, borrow_records

    df = df.copy()
    df["_wt_key"] = df["重量模板, 编号"].apply(
        lambda x: str(x).replace("ZLMB#", "").strip() if pd.notna(x) else None
    )

    for col in cost_columns:
        if col not in df.columns:
            continue
        for wt_key, grp in df.groupby("_wt_key"):
            if wt_key is None or len(grp) < 2:
                continue
            non_zero_mask = grp[col] > 0
            if not non_zero_mask.any():
                continue
            donor_idx = non_zero_mask.idxmax()
            donor_val = grp.loc[donor_idx, col]
            donor_product = grp.loc[donor_idx, "产品编号"]
            need_borrow = grp[grp[col] == 0]
            for idx in need_borrow.index:
                if donor_val is None or pd.isna(donor_val):
                    continue
                df.at[idx, col] = donor_val
                borrow_records.append({
                    "产品编号": df.at[idx, "产品编号"],
                    "客户物料号": df.at[idx, "客户物料号"] if pd.notna(df.at[idx, "客户物料号"]) else "",
                    "产品名称": df.at[idx, "产品名称"],
                    "绍兴发货方式": df.at[idx, "绍兴发货方式"],
                    "重量模板键": wt_key,
                    "借用成本列": col,
                    "借用来源产品编号": donor_product,
                    "借用值": donor_val,
                })

    df.drop(columns=["_wt_key"], inplace=True)
    n_products = len(set(r["产品编号"] for r in borrow_records))
    print(f"成本借用: {len(borrow_records)} 个单元格, 涉及 {n_products} 个产品编号")
    return df, borrow_records


def _write_issues(out_path: Path, issues_summary: list[dict], reports: dict[str, list[dict]]) -> None:
    """多 sheet 问题报告，参照 item_weight_size 模式。"""
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        if issues_summary:
            pd.DataFrame(issues_summary).to_excel(w, sheet_name=SHEET_SUMMARY, index=False)

        for s in SHEETS_ORDER:
            data = reports.get(s, [])
            if data:
                pd.DataFrame(data).to_excel(w, sheet_name=s, index=False)
            else:
                pd.DataFrame({"说明": ["（无数据）"]}).to_excel(w, sheet_name=s, index=False)


def _diff_against_previous(
    today_import: pd.DataFrame,
    out_dir: Path,
    stamp: str,
    all_ref: pd.DataFrame,
    all_agg: pd.DataFrame,
    template_cols: list[str],
    compare_to: str | None = None,
) -> tuple[pd.DataFrame | None, Path | None]:
    """对比上次导入文件，生成差异报告和新增条目文件。"""
    if compare_to:
        prev_file = Path(compare_to)
        if not prev_file.exists():
            print(f"差异对比: 指定文件不存在 — {compare_to}")
            return None, None
        prev_label = prev_file.stem.replace("赛狐库存初始值_导入_", "")
    else:
        # 找最近的导入文件（子目录 + 旧平级目录都找）
        candidates = list(OUT_BASE.glob("*/赛狐库存初始值_导入_*.xlsx")) + list(OUT_BASE.glob("赛狐库存初始值_导入_*.xlsx"))
        candidates = [f for f in candidates if stamp not in str(f)]
        all_imports = sorted(candidates, key=lambda f: f.stat().st_mtime)
        if len(all_imports) < 1:
            print("差异对比: 未找到历史导入文件，跳过")
            return None, None
        prev_file = all_imports[-1]
        prev_label = prev_file.stem.replace("赛狐库存初始值_导入_", "")

    print(f"差异对比: 基准 = {prev_file.name} (from {prev_label})")

    prev = pd.read_excel(prev_file)
    key_cols = ["*所属仓库", "*SKU"]

    # 收集产品名称
    sku_name = {}
    for _, row in all_ref.iterrows():
        sku_name[(row["*所属仓库"], row["*SKU"])] = row.get("产品名称", "")
    # also from agg
    for _, row in all_agg.iterrows():
        sku_name[(row["赛狐仓库"], row["产品编号"])] = row.get("产品名称", "")

    def _name(warehouse, sku):
        return sku_name.get((warehouse, sku), "")

    m = prev[key_cols + ["*采购成本", "可用库存"]].merge(
        today_import[key_cols + ["*采购成本", "可用库存"]],
        on=key_cols, suffixes=("_prev", "_today"), how="outer", indicator=True
    )

    new_entries = m[m["_merge"] == "right_only"].copy()
    removed_entries = m[m["_merge"] == "left_only"].copy()
    both = m[m["_merge"] == "both"].copy()

    # Classify changes
    cost_changed = both[both["*采购成本_prev"] != both["*采购成本_today"]].copy()
    qty_changed = both[both["可用库存_prev"] != both["可用库存_today"]].copy()

    n_new = len(new_entries)
    n_removed = len(removed_entries)
    n_cost = len(cost_changed)
    n_qty = len(qty_changed)
    n_unchanged = len(both) - n_cost - n_qty + (
        (cost_changed.index.isin(qty_changed.index)).sum() if n_cost and n_qty else 0
    )

    # ── Diff report sheets ──
    diff_reports: dict[str, list[dict]] = {}
    diff_summary = [{
        "类型": "汇总",
        "昨日导入条目数": len(prev),
        "今日导入条目数": len(today_import),
        "新增条目": n_new,
        "条目消失": n_removed,
        "成本变更": n_cost,
        "数量变更": n_qty,
        "完全不变": max(0, n_unchanged),
        "对比基准文件": prev_file.name,
    }]

    # 新增条目
    if n_new > 0:
        diff_reports["新增条目"] = [
            {
                "仓库": row["*所属仓库"],
                "SKU": row["*SKU"],
                "产品名称": _name(row["*所属仓库"], row["*SKU"]),
                "今日_采购成本": row["*采购成本_today"],
                "今日_可用库存": int(row["可用库存_today"]),
                "说明": "昨日导入中不存在，今日新增",
            }
            for _, row in new_entries.iterrows()
        ]

    # 成本变更
    if n_cost > 0:
        cost_changed["_cost_diff"] = cost_changed["*采购成本_today"] - cost_changed["*采购成本_prev"]
        diff_reports["成本变更"] = [
            {
                "仓库": row["*所属仓库"],
                "SKU": row["*SKU"],
                "产品名称": _name(row["*所属仓库"], row["*SKU"]),
                "昨日成本": row["*采购成本_prev"],
                "今日成本": row["*采购成本_today"],
                "差值": row["_cost_diff"],
                "说明": "成本已变更，若昨日已导入赛狐，需用成本补录单修正",
            }
            for _, row in cost_changed.iterrows()
        ]

    # 数量变更
    if n_qty > 0:
        qty_changed["_qty_diff"] = qty_changed["可用库存_today"] - qty_changed["可用库存_prev"]
        diff_reports["数量变更"] = [
            {
                "仓库": row["*所属仓库"],
                "SKU": row["*SKU"],
                "产品名称": _name(row["*所属仓库"], row["*SKU"]),
                "昨日库存": int(row["可用库存_prev"]),
                "今日库存": int(row["可用库存_today"]),
                "差值": int(row["_qty_diff"]),
                "说明": "库存数量已变更，需用调整单修正",
            }
            for _, row in qty_changed.iterrows()
        ]

    # 条目消失
    if n_removed > 0:
        diff_reports["条目消失"] = [
            {
                "仓库": row["*所属仓库"],
                "SKU": row["*SKU"],
                "产品名称": _name(row["*所属仓库"], row["*SKU"]),
                "昨日成本": row["*采购成本_prev"],
                "昨日库存": int(row["可用库存_prev"]),
                "说明": "今日输出中不再包含此条目",
            }
            for _, row in removed_entries.iterrows()
        ]

    # Write diff report
    diff_file = out_dir / f"差异报告_{stamp}_vs_{prev_label}.xlsx"
    diff_sheets_order = ["新增条目", "成本变更", "数量变更", "条目消失"]
    with pd.ExcelWriter(diff_file, engine="openpyxl") as w:
        pd.DataFrame(diff_summary).to_excel(w, sheet_name="汇总", index=False)
        for sn in diff_sheets_order:
            data = diff_reports.get(sn, [])
            if data:
                pd.DataFrame(data).to_excel(w, sheet_name=sn, index=False)
            else:
                pd.DataFrame({"说明": ["（无数据）"]}).to_excel(w, sheet_name=sn, index=False)
    print(f"  差异报告: {diff_file.name}")

    # New entries import file
    new_import_file = None
    if n_new > 0:
        new_out = today_import[
            today_import.set_index(key_cols).index.isin(
                new_entries.set_index(key_cols).index
            )
        ].copy()
        new_import_file = out_dir / f"新增条目_导入_{stamp}.xlsx"
        new_out[template_cols].to_excel(new_import_file, sheet_name="商品", index=False, na_rep="")
        print(f"  新增条目导入: {new_import_file.name} ({len(new_out)} 条)")

    return new_out if n_new > 0 else None, new_import_file


def _print_summary(
    n_tongtu_sku: int,
    n_matched_sku: int,
    n_unmatched_sku: int,
    n_matched_rows: int,
    n_output: int,
    n_cost_zero: int,
    n_qty_zero: int,
    n_en_excluded_ship: int,
    n_en_excluded_cust: int,
    n_sx_filtered: int,
    n_cost_borrowed_cells: int,
    n_cost_borrowed_products: int,
    wh_stats: list[dict],
    f_import: Path,
    f_ref: Path,
    f_issues: Path,
    f_diff: Path | None,
    n_import: int,
) -> None:
    print("=" * 60)
    print("赛狐 库存初始值导入 — 处理完成")
    print("=" * 60)
    print(f"导入用 (成本>0): {f_import}  ({n_import} 条)")
    print(f"参考用 (全量):   {f_ref}  ({n_output} 条)")
    print(f"问题报告:       {f_issues}")
    if f_diff:
        print(f"差异报告:       {f_diff}")
    print(f"---")
    print(f"操作提示:")
    print(f"  导入赛狐后，请复制导入文件到固定锚点:")
    print(f"  cp {f_import.name} {ANCHOR_FILE.name}")
    print(f"  下次运行即可自动对比")
    print(f"---")
    print(f"通途 SKU 总数:          {n_tongtu_sku}")
    print(f"  → EN 匹配成功:        {n_matched_sku} 个 SKU ({n_matched_rows} 条)")
    print(f"  → EN 匹配失败(排除):  {n_unmatched_sku} 个 SKU")
    print(f"EN 清洗排除:            发货方式空 {n_en_excluded_ship} / 客户物料号空 {n_en_excluded_cust}")
    print(f"成本借用(重量模板补齐):  {n_cost_borrowed_cells} 个单元格, 涉及 {n_cost_borrowed_products} 个产品")
    print(f"赛狐白名单过滤(排除):   {n_sx_filtered} 条")
    print(f"---")
    print(f"最终输出 SKU-仓库组合:  {n_output}")
    print(f"  ⚠ 采购成本=0:          {n_cost_zero}")
    print(f"  ℹ 可用库存=0:          {n_qty_zero}")
    for wh in wh_stats:
        print(f"  {wh['仓库']}: {wh['SKU数']} SKUs, 库存={wh['可用库存合计']}, 成本合计={wh['成本合计']:.2f}, 库存>0且成本>0={wh['正常记录数']}")
    print(f"---")
    print(f"问题报告 sheet: {', '.join([SHEET_SUMMARY] + SHEETS_ORDER)}")
    print("=" * 60)


def main():
    import sys
    compare_to = None
    if "--compare-to" in sys.argv:
        idx = sys.argv.index("--compare-to")
        if idx + 1 < len(sys.argv):
            compare_to = sys.argv[idx + 1]
    elif ANCHOR_FILE.exists():
        # 检查是否为有效 xlsx（不是空占位）
        try:
            pd.read_excel(ANCHOR_FILE)
            compare_to = str(ANCHOR_FILE)
        except Exception:
            pass

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUT_DIR = OUT_BASE / stamp
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 收集问题数据
    issues_summary: list[dict] = []
    reports: dict[str, list[dict]] = {s: [] for s in SHEETS_ORDER}

    # ─── 1. 读取数据源 ───
    f_tongtu = auto_select("通途合并库存结存清单*.xlsx")
    f_enbom = auto_select("EN产品BOM成本列表*.xlsx")
    f_saihu = auto_select("商品导出*.xlsx")

    print(f"通途库存: {f_tongtu.name}")
    print(f"EN BOM:   {f_enbom.name}")
    print(f"赛狐商品: {f_saihu.name}")

    df2 = pd.read_excel(f_tongtu)
    df3 = pd.read_excel(f_enbom)
    df4 = pd.read_excel(f_saihu)

    n_tongtu_sku = df2["SKU"].nunique()
    n_tongtu_rows = len(df2)
    n_en_init = len(df3)

    # ─── 2. 赛狐 SKU 白名单 ───
    saihu_sku_set = set(df4["SKU"].dropna().unique())
    print(f"赛狐SKU白名单: {len(saihu_sku_set)} 个")

    # ─── 3. 通途仓库映射 ───
    unknown_wh = set(df2["仓库"].dropna().unique()) - set(WAREHOUSE_MAP.keys())
    if unknown_wh:
        for wh in unknown_wh:
            cnt = (df2["仓库"] == wh).sum()
            issues_summary.append({"类型": "未知仓库", "仓库": wh, "记录数": cnt})

    df2["赛狐仓库"] = df2["仓库"].map(WAREHOUSE_MAP)
    n_wh_unmapped = df2["赛狐仓库"].isna().sum()
    if n_wh_unmapped > 0:
        issues_summary.append({"类型": "仓库映射失败", "记录数": n_wh_unmapped})

    # ─── 4. EN 数据清洗 ───
    # 绍兴发货方式为空
    df3_null_ship = df3[df3["绍兴发货方式"].isna()]
    n_en_excluded_ship = len(df3_null_ship)
    if n_en_excluded_ship > 0:
        df3_null_ship[["产品编号", "客户物料号", "产品名称"]].assign(排除原因="绍兴发货方式为空").to_dict("records")
        for _, row in df3_null_ship.iterrows():
            reports[SHEET_EN_EXCLUDED].append({
                "产品编号": row["产品编号"],
                "客户物料号": row.get("客户物料号", ""),
                "产品名称": row["产品名称"],
                "排除原因": "绍兴发货方式为空",
            })

    df3 = df3.dropna(subset=["绍兴发货方式"])

    # 客户物料号为空
    df3_null_cust = df3[df3["客户物料号"].isna()]
    n_en_excluded_cust = len(df3_null_cust)
    if n_en_excluded_cust > 0:
        for _, row in df3_null_cust.iterrows():
            reports[SHEET_EN_EXCLUDED].append({
                "产品编号": row["产品编号"],
                "客户物料号": "",
                "产品名称": row["产品名称"],
                "排除原因": "客户物料号为空",
            })

    df3 = df3.dropna(subset=["客户物料号"])
    print(f"EN 清洗: 发货方式空 {n_en_excluded_ship} + 客户物料号空 {n_en_excluded_cust} = 排除 {n_en_init - len(df3)} 行 (剩余 {len(df3)})")

    # ─── 4.5 成本借用（按重量模板键补齐零值）───
    all_cost_cols = list(set(COST_COLUMN_MAP.values()))
    df3, borrow_records = _borrow_costs(df3, all_cost_cols)
    reports[SHEET_COST_BORROW] = borrow_records

    # ─── 5. Left merge: 通途SKU → EN客户物料号 ───
    df_m = df2.merge(df3, left_on="SKU", right_on="客户物料号", how="left", suffixes=("_tt", "_en"))

    matched = df_m[df_m["产品编号"].notna()]
    unmatched = df_m[df_m["产品编号"].isna()]

    n_matched_sku = matched["SKU"].nunique()
    n_matched_rows = len(matched)
    n_unmatched_sku = unmatched["SKU"].nunique()
    n_unmatched_rows = len(unmatched)

    print(f"通途SKU→EN: 匹配 {n_matched_sku} SKU ({n_matched_rows}条) / 未匹配 {n_unmatched_sku} SKU ({n_unmatched_rows}条)")

    # 收集未匹配明细
    if n_unmatched_rows > 0:
        unmatched_unique = unmatched[["SKU", "货品名称/规格", "仓库", "可用库存", "在途库存", "待发库存"]].drop_duplicates(subset=["SKU", "仓库"])
        for _, row in unmatched_unique.iterrows():
            reports[SHEET_TT_UNMATCHED].append({
                "SKU": row["SKU"],
                "货品名称/规格": row.get("货品名称/规格", ""),
                "仓库": row["仓库"],
                "可用库存": row["可用库存"],
                "在途库存": row["在途库存"],
                "待发库存": row["待发库存"],
                "说明": "该通途SKU在EN产品BOM成本列表中找不到匹配的客户物料号",
            })

    # 继续只用匹配到的
    df = matched.copy()

    # ─── 6. 为每行选取成本列 ───
    df["_cost_col"] = df.apply(lambda r: COST_COLUMN_MAP.get((r["绍兴发货方式"], r["赛狐仓库"]), None), axis=1)

    def _get_cost(row):
        ccol = row["_cost_col"]
        if ccol is None or ccol not in row.index:
            return None
        return row[ccol]

    df["采购成本"] = df.apply(_get_cost, axis=1)

    cost_missing = df[df["采购成本"].isna()]
    n_cost_missing = len(cost_missing)
    if n_cost_missing > 0:
        issues_summary.append({"类型": "成本匹配失败", "记录数": n_cost_missing})

    df = df.dropna(subset=["采购成本"])

    # ─── 7. 赛狐 SKU 白名单过滤 ───
    before_filter = len(df)
    sx_filtered_df = df[~df["产品编号"].isin(saihu_sku_set)]
    df = df[df["产品编号"].isin(saihu_sku_set)]
    n_sx_filtered = len(sx_filtered_df)

    if n_sx_filtered > 0:
        sx_filtered_grp = sx_filtered_df.groupby(["产品编号", "绍兴发货方式", "赛狐仓库"], as_index=False).agg(
            可用库存=("可用库存", "sum"),
            产品名称=("产品名称", "first"),
        )
        for _, row in sx_filtered_grp.iterrows():
            reports[SHEET_SX_NOTFOUND].append({
                "产品编号": row["产品编号"],
                "产品名称": row.get("产品名称", ""),
                "绍兴发货方式": row["绍兴发货方式"],
                "赛狐仓库": row["赛狐仓库"],
                "可用库存": row["可用库存"],
                "说明": "该EN产品编号不在赛狐商品导出中（赛狐尚未建档）",
            })

    print(f"赛狐白名单过滤: 排除 {n_sx_filtered} 条 (剩余 {len(df)} 条)")

    # ─── 8. 按(赛狐仓库, 产品编号)聚合 ───
    agg = df.groupby(["赛狐仓库", "产品编号"], as_index=False).agg(
        可用库存=("可用库存", "sum"),
        在途库存=("在途库存", "sum"),
        待发库存=("待发库存", "sum"),
        采购成本=("采购成本", "first"),
        产品名称=("产品名称", "first"),
        绍兴发货方式=("绍兴发货方式", "first"),
        _cost_col=("_cost_col", "first"),
        _cust_count=("客户物料号", "nunique"),
    )

    # ─── 9. 构建输出 ───
    out = pd.DataFrame()
    out["*所属仓库"] = agg["赛狐仓库"]
    out["*SKU"] = agg["产品编号"]
    out["店铺"] = None
    out["FNSKU"] = None
    out["品名"] = None
    out["可用库存"] = agg["可用库存"]
    out["次品库存"] = None
    out["*采购成本"] = agg["采购成本"]
    out["单位费用"] = None
    out["上架时间"] = None

    n_output = len(out)

    # ─── 10. 收集聚合后的问题 ───
    # 成本=0
    zero_cost = out[out["*采购成本"] == 0]
    n_cost_zero = len(zero_cost)
    for _, row in zero_cost.iterrows():
        agg_row = agg[(agg["产品编号"] == row["*SKU"]) & (agg["赛狐仓库"] == row["*所属仓库"])]
        ship_method = agg_row["绍兴发货方式"].values[0] if len(agg_row) > 0 else ""
        cost_col = agg_row["_cost_col"].values[0] if len(agg_row) > 0 else ""
        product_name = agg_row["产品名称"].values[0] if len(agg_row) > 0 else ""
        reports[SHEET_ZERO_COST].append({
            "仓库": row["*所属仓库"],
            "SKU": row["*SKU"],
            "产品名称": product_name,
            "可用库存": int(row["可用库存"]),
            "绍兴发货方式": ship_method,
            "成本来源列": cost_col,
            "说明": "EN成本列表中该列值为0，赛狐可能将成本=0视为不导入（需手动确认）",
        })

    # 可用库存=0
    zero_qty = out[out["可用库存"] == 0]
    n_qty_zero = len(zero_qty)
    for _, row in zero_qty.iterrows():
        agg_row = agg[(agg["产品编号"] == row["*SKU"]) & (agg["赛狐仓库"] == row["*所属仓库"])]
        transit = int(agg_row["在途库存"].values[0]) if len(agg_row) > 0 else 0
        pending = int(agg_row["待发库存"].values[0]) if len(agg_row) > 0 else 0
        product_name = agg_row["产品名称"].values[0] if len(agg_row) > 0 else ""
        reports[SHEET_ZERO_QTY].append({
            "仓库": row["*所属仓库"],
            "SKU": row["*SKU"],
            "产品名称": product_name,
            "在途库存": transit,
            "待发库存": pending,
            "采购成本": row["*采购成本"],
            "说明": "在途=" + str(transit) if transit > 0 else "库存全为0，可观察是否需要保留在导入文件中",
        })

    # ─── 11. 每仓统计 ───
    wh_stats = []
    for wh in ["CENTRADE", "DANEEY", "POLAND"]:
        sub = out[out["*所属仓库"] == wh]
        if len(sub) == 0:
            continue
        good = sub[(sub["可用库存"] > 0) & (sub["*采购成本"] > 0)]
        wh_stats.append({
            "仓库": wh,
            "SKU数": len(sub),
            "可用库存合计": int(sub["可用库存"].sum()),
            "在途库存合计": int(agg[agg["赛狐仓库"] == wh]["在途库存"].sum()),
            "待发库存合计": int(agg[agg["赛狐仓库"] == wh]["待发库存"].sum()),
            "成本合计": round(sub["*采购成本"].sum(), 2),
            "成本>0的SKU数": int((sub["*采购成本"] > 0).sum()),
            "成本=0的SKU数": int((sub["*采购成本"] == 0).sum()),
            "库存>0的SKU数": int((sub["可用库存"] > 0).sum()),
            "库存=0的SKU数": int((sub["可用库存"] == 0).sum()),
            "正常记录数": len(good),
        })
    reports[SHEET_WH_STATS] = wh_stats

    # ─── 12. 汇总整理 ───
    issues_summary.insert(0, {
        "类型": "汇总",
        "通途SKU总数": n_tongtu_sku,
        "通途记录总数": n_tongtu_rows,
        "EN产品总数": n_en_init,
        "赛狐白名单SKU数": len(saihu_sku_set),
        "匹配成功SKU数": n_matched_sku,
        "匹配成功记录数": n_matched_rows,
        "匹配失败SKU数": n_unmatched_sku,
        "匹配失败记录数": n_unmatched_rows,
        "EN清洗_发货方式空": n_en_excluded_ship,
        "EN清洗_客户物料号空": n_en_excluded_cust,
        "赛狐白名单过滤掉": n_sx_filtered,
        "成本缺失排除": n_cost_missing,
        "成本借用单元格数": len(borrow_records),
        "成本借用涉及产品数": len(set(r["产品编号"] for r in borrow_records)),
        "最终输出记录数": n_output,
        "采购成本=0数": n_cost_zero,
        "可用库存=0数": n_qty_zero,
        "库存>0且成本>0数": sum(s["正常记录数"] for s in wh_stats),
    })

    # ─── 13. 写文件 ───
    # 导入文件：仅含 *采购成本>0 的行，用于上传赛狐
    out_import = out[out["*采购成本"] > 0]
    import_file = OUT_DIR / f"赛狐库存初始值_导入_{stamp}.xlsx"
    out_import[TEMPLATE_COLS].to_excel(import_file, sheet_name=SHEET_MAIN, index=False, na_rep="")
    n_import = len(out_import)

    # 全量参考文件：包含所有行（含成本=0、库存=0），仅用于查看，不可导入
    ref_file = OUT_DIR / f"参考_库存初始值全量_{stamp}.xlsx"
    out[TEMPLATE_COLS].to_excel(ref_file, sheet_name=SHEET_MAIN, index=False, na_rep="")

    print(f"\n导入用 (成本>0): {import_file.name}  ({n_import} 条, 不含成本=0)")
    print(f"参考用 (全量):   {ref_file.name}  ({n_output} 条, 含成本=0和库存=0)")

    issues_file = OUT_DIR / f"stock_init_问题报告_{stamp}.xlsx"
    _write_issues(issues_file, issues_summary, reports)
    print(f"问题报告:       {issues_file.name}")

    # ─── 13.5 差异对比 ───
    _new_entries, diff_file = _diff_against_previous(
        out_import, OUT_DIR, stamp, out, agg, TEMPLATE_COLS, compare_to=compare_to
    )

    # ─── 14. 控制台摘要 ───
    n_cost_borrowed_cells = len(borrow_records)
    n_cost_borrowed_products = len(set(r["产品编号"] for r in borrow_records))
    _print_summary(
        n_tongtu_sku=n_tongtu_sku,
        n_matched_sku=n_matched_sku,
        n_unmatched_sku=n_unmatched_sku,
        n_matched_rows=n_matched_rows,
        n_output=n_output,
        n_cost_zero=n_cost_zero,
        n_qty_zero=n_qty_zero,
        n_en_excluded_ship=n_en_excluded_ship,
        n_en_excluded_cust=n_en_excluded_cust,
        n_sx_filtered=n_sx_filtered,
        n_cost_borrowed_cells=n_cost_borrowed_cells,
        n_cost_borrowed_products=n_cost_borrowed_products,
        wh_stats=wh_stats,
        f_import=import_file,
        f_ref=ref_file,
        f_issues=issues_file,
        f_diff=diff_file,
        n_import=n_import,
    )


if __name__ == "__main__":
    main()
