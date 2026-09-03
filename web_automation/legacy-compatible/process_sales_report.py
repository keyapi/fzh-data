#!/usr/bin/env python3
"""
销售及库存报表处理：解压 → 按仓库分表 → 输出多 sheet Excel

3 主仓 + 3 退货仓（6 个主线仓）各一个工作表；其余仓库（成品/半成品/Wayfair/
星链/大件/多渠道等非主线）合并进"其他"工作表，不丢数据。

用法:
  uv run python process_sales_report.py <zip_path>                    # 指定 zip 路径
  uv run python process_sales_report.py                               # 自动找 downloads/ 下最新 zip
"""
import sys, io
from pathlib import Path
from datetime import datetime
import zipfile
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
DOWNLOADS_DIR = WEB_ROOT / "downloads"
OUTPUT_DIR = WEB_ROOT / "output"

# 6 个主线仓（与 tongtu_auto_export.WAREHOUSES 对齐，2026-09 通途改名后）。
# 其余仓库（成品/半成品/Wayfair/星链/大件/多渠道等）归入"其他"表。
MAIN_SHEETS = {
    "美东-CENTRADE",
    "波兰-FZHPoland-covers",
    "美中-FZH-DANEEY",
    "美东-CENTRADE-退货产品仓",
    "波兰-FZHPoland-退货产品仓",
    "美中-FZH-DANEEY-退货产品仓",
}
OTHER_SHEET_NAME = "其他"

# 需要跳过的汇总行关键词（精确匹配仓库列的值）
SKIP_WAREHOUSE_VALUES = {"数量总计", "金额总计"}


def find_latest_zip():
    """在 downloads/ 下找最新的 销售及库存报表*.zip"""
    zips = sorted(
        DOWNLOADS_DIR.glob("销售及库存报表*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not zips:
        raise FileNotFoundError("未找到 销售及库存报表*.zip 文件")
    return zips[0]


def extract_zip(zip_path):
    """解压 zip，返回 xlsx 路径"""
    extract_dir = DOWNLOADS_DIR / "sales_report_extracted"
    extract_dir.mkdir(exist_ok=True)
    for f in extract_dir.iterdir():
        f.unlink()
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_dir)
    xlsx_files = list(extract_dir.glob("*.xlsx"))
    if not xlsx_files:
        raise FileNotFoundError("zip 中没有找到 xlsx 文件")
    return xlsx_files[0]


def read_data(xlsx_path):
    """读取 xlsx，跳过元数据行，返回 DataFrame"""
    df = pd.read_excel(xlsx_path, header=12)
    # 排除空行 和 汇总行
    df = df[df["仓库"].notna()]
    df = df[~df["仓库"].astype(str).isin(SKIP_WAREHOUSE_VALUES)]
    return df


def split_by_warehouse(df):
    """按仓库分组：6 个主线仓各一表，其余归入"其他"（不丢数据）。"""
    sheets = {}
    other_dfs = []
    for wh, group in df.groupby("仓库", sort=False):
        if wh in MAIN_SHEETS:
            sheets[wh] = group.reset_index(drop=True)
        else:
            other_dfs.append(group)
    if other_dfs:
        merged = pd.concat(other_dfs, ignore_index=True)
        sheets[OTHER_SHEET_NAME] = merged
        wh_names = sorted({str(g.iloc[0]["仓库"]) for g in other_dfs})
        print(f"  [归入其他] {', '.join(wh_names)} → {len(merged)} 行")
    return sheets


def write_output(sheets):
    """写入多 sheet 的 xlsx"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"销售及库存报表_按仓分表_{ts}.xlsx"

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        for sheet_name, sheet_df in sheets.items():
            safe_name = sheet_name[:31]
            sheet_df.to_excel(writer, sheet_name=safe_name, index=False)
            print(f"  [写入] {safe_name}: {len(sheet_df)} 行")

    return output_path


def process(zip_path=None):
    """主入口"""
    print("=" * 50)
    print("[处理] 销售及库存报表 → 按仓分表")
    print("=" * 50)

    if zip_path:
        zip_path = Path(zip_path)
    else:
        zip_path = find_latest_zip()
    print(f"\n[步骤 1] 解压: {zip_path.name}")
    xlsx_path = extract_zip(zip_path)

    print(f"\n[步骤 2] 读取: {xlsx_path.name}")
    df = read_data(xlsx_path)
    print(f"  总行数: {len(df)}, 仓库数: {df['仓库'].nunique()}")

    print(f"\n[步骤 3] 按仓库分组...")
    sheets = split_by_warehouse(df)

    print(f"\n[步骤 4] 写入多 sheet Excel...")
    output_path = write_output(sheets)

    print(f"\n{'=' * 50}")
    print(f"[完成] 输出文件: {output_path}")
    print(f"  工作表: {list(sheets.keys())}")
    print(f"{'=' * 50}")
    return output_path


if __name__ == "__main__":
    zip_arg = sys.argv[1] if len(sys.argv) > 1 else None
    process(zip_arg)
