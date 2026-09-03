#!/usr/bin/env python3
"""
合并多个仓库的库存结存清单到一个 Excel 文件。

每个原始文件结构:
  第1行: "库存结存清单"
  第2行: "仓库 XXX  库存清单导出时间 YYYY"
  第3行: 空
  第4行: 列标题 (SKU, 货品名称/规格, ...)
  第5行+: 数据

用法:
  uv run python merge_inventory.py                          # 合并 downloads/ 下所有仓库
  uv run python merge_inventory.py --output 合并库存.xlsx   # 指定输出文件名
"""

import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
DOWNLOADS_DIR = WEB_ROOT / "downloads"
OUTPUT_DIR = WEB_ROOT / "output"

WAREHOUSES = [
    "CENTRADE",
    "FZHPoland-covers",
    "FZH-DANEEY-皮壳仓库",
    "FZH-DANEEY-退货产品仓",
    "FZH-DANEEY-成品仓",
    "FZH-DANEEY-半成品仓",
]


def safe_prefix(name):
    return name.replace("/", "-").replace("\\", "-").replace(":", "-")


def read_inventory_df(path):
    """读取一个库存结存清单文件，返回干净 DataFrame（含所有列）"""
    df = pd.read_excel(path, header=None)

    # 找到表头行（第1列为'SKU'的行）
    header_mask = df.iloc[:, 0].astype(str).str.strip() == "SKU"
    if header_mask.sum() == 0:
        raise ValueError(f"未找到 SKU 表头行: {path}")
    header_idx = header_mask[header_mask].index[0]

    # 设置列名
    df.columns = df.iloc[header_idx].astype(str).str.replace("\n", "").str.strip()
    df = df.iloc[header_idx + 1:]  # 数据从表头下一行开始

    # 跳过汇总行和空行
    sku_col = df.columns[0]
    df = df[~df[sku_col].astype(str).str.strip().isin(["数量总计", "金额总计", "", "nan"])]
    df = df[df[sku_col].notna()]

    return df


def merge_downloads(downloads_dir, warehouses, output_path):
    """合并多个仓库的下载文件"""
    all_dfs = []
    found = 0

    for wh in warehouses:
        prefix = safe_prefix(wh)
        # Windows 文件名编码坑:
        # Playwright download.suggested_filename 在 GBK 环境下可能返回乱码，
        # 导致磁盘上的中文文件名变为 mojibake（如 ¿â´æ½á´æÇåµ¥）。
        # 因此不能用中文关键词匹配，改为前缀 + .xlsx 后缀匹配。
        all_files = list(downloads_dir.iterdir())
        files = sorted(
            [f for f in all_files
             if f.name.startswith(prefix) and f.suffix == ".xlsx"],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not files:
            print(f"  [跳过] {wh}: 未找到下载文件")
            continue

        path = files[0]  # 取最新
        print(f"  [读取] {wh}  →  {path.name}")
        df = read_inventory_df(path)
        all_dfs.append(df)
        found += 1

    if not all_dfs:
        print("[错误] 没有找到任何可合并的文件")
        return None

    merged = pd.concat(all_dfs, ignore_index=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    merged.to_excel(output_path, index=False, sheet_name="合并库存")

    # 统计
    total_skus = len(merged)
    warehouses_included = merged.get("仓库", merged.iloc[:, 4] if merged.shape[1] > 4 else None)

    print(f"\n[完成] 合并 {found} 个仓库，共 {total_skus} 行")
    print(f"  输出: {output_path}")

    return merged


def main():
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    output_name = f"通途合并库存结存清单 {ts}.xlsx"
    for arg in sys.argv[1:]:
        if arg.startswith("--output="):
            output_name = arg.split("=", 1)[1]

    output_path = OUTPUT_DIR / output_name
    merge_downloads(DOWNLOADS_DIR, WAREHOUSES, output_path)


if __name__ == "__main__":
    main()
