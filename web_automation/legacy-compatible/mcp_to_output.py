#!/usr/bin/env python3
"""
MCP 下载文件 → 整理到 output/ 目录

当通过 Playwright MCP（而非 tongtu_auto_export.py）导出仓库时，
下载的文件保存在 .playwright-mcp/ 目录，文件名是时间戳格式。
此脚本将这些文件整理、按仓库重命名、并生成导入文件。

用法:
  # 交互模式：列出下载文件，逐一确认归属仓库
  uv run python mcp_to_output.py

  # 指定下载目录（MCP 下载可能不在项目目录下）
  uv run python mcp_to_output.py --from "C:/Users/zhang/通途库存Excel/.playwright-mcp"

  # 扫描后自动匹配（按时间戳顺序匹配 WAREHOUSES 列表）
  uv run python mcp_to_output.py --auto
"""

import subprocess, sys, shutil
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
DOWNLOADS_DIR = WEB_ROOT / "downloads"
OUTPUT_DIR = WEB_ROOT / "output"

# 检测 Git 仓库根目录（MCP 下载统一保存到仓库根 .playwright-mcp/）
def _find_repo_root():
    p = SCRIPT_DIR
    for _ in range(10):
        if (p / ".git").exists():
            return p
        p = p.parent
    return SCRIPT_DIR.parent  # fallback

REPO_ROOT = _find_repo_root()
DEFAULT_MCP_DIR = REPO_ROOT / ".playwright-mcp"

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


def find_downloads(mcp_dir):
    """扫描目录中的库存结存清单 xlsx 文件，按时间排序

    支持两种命名格式:
      - 库存结存清单2026-04-29...xlsx  (MCP 原始文件名)
      - CENTRADE_库存结存清单.xlsx      (已重命名的文件)
    会排除临时文件 (~$ 开头)
    """
    xlsx_files = [
        p for p in mcp_dir.glob("*库存结存清单*.xlsx")
        if not p.name.startswith("~$")
    ]
    if not xlsx_files:
        return []
    xlsx_files.sort(key=lambda p: p.stat().st_mtime)
    return xlsx_files


def copy_to_downloads(src, warehouse_name):
    """复制到 downloads/ 并重命名；如已有仓库前缀则不再重复添加"""
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    prefix = safe_prefix(warehouse_name)
    src_name = src.name
    if src_name.startswith(prefix + "_"):
        dst = DOWNLOADS_DIR / src_name
    else:
        dst = DOWNLOADS_DIR / f"{prefix}_{src_name}"
    shutil.copy2(str(src), str(dst))
    print(f"  [复制] {src.name} → {dst.name}")
    return dst


def generate_import(inventory_path, warehouse_name):
    """调用 generate_tongtu_import.py 生成导入文件"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    script = SCRIPT_DIR / "generate_tongtu_import.py"
    prefix = safe_prefix(warehouse_name)
    out_path = OUTPUT_DIR / f"{prefix}_通途导入_头程运费_其他费用.xlsx"

    print(f"  [生成] 导入文件 → {out_path.name}")
    result = subprocess.run(
        [sys.executable, str(script), str(inventory_path), str(out_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                print(f"    {line.strip()}")
    if result.returncode != 0:
        print(f"  [错误] 生成失败 (exit={result.returncode})")
        if result.stderr:
            print(f"    {result.stderr[:500]}")
        return False
    return True


def interactive(mcp_dir):
    """交互模式：逐文件确认仓库"""
    files = find_downloads(mcp_dir)
    if not files:
        print(f"[信息] 在 {mcp_dir} 中未找到库存结存清单文件")
        return

    print(f"[信息] 找到 {len(files)} 个下载文件:")
    for i, f in enumerate(files):
        size_kb = f.stat().st_size / 1024
        print(f"  [{i+1}] {f.name}  ({size_kb:.0f} KB)")

    print(f"\n仓库列表:")
    for i, wh in enumerate(WAREHOUSES):
        print(f"  [{i+1}] {wh}")

    print(f"\n请按顺序确认每个文件对应的仓库 (输入仓库编号，回车=按顺序自动匹配):")
    for i, f in enumerate(files):
        if i < len(WAREHOUSES):
            wh = WAREHOUSES[i]
            choice = input(f"\n文件 [{i+1}/{len(files)}] {f.name[:40]}... → [{wh}] (回车确认): ").strip()
            if choice and choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(WAREHOUSES):
                    wh = WAREHOUSES[idx]
        else:
            print(f"  仓库不够，跳过: {f.name}")
            continue

        inv_path = copy_to_downloads(f, wh)
        generate_import(inv_path, wh)

    print(f"\n[完成] 文件已整理:")
    print(f"  下载: {DOWNLOADS_DIR}")
    print(f"  输出: {OUTPUT_DIR}")


def auto(mcp_dir):
    """自动模式：按时间戳顺序匹配仓库列表"""
    files = find_downloads(mcp_dir)
    if not files:
        print(f"[信息] 在 {mcp_dir} 中未找到库存结存清单文件")
        return

    if len(files) != len(WAREHOUSES):
        print(f"[警告] 文件数({len(files)})与仓库数({len(WAREHOUSES)})不一致，建议用交互模式")
        return

    print(f"[信息] 自动匹配 {len(files)} 个文件 → {len(WAREHOUSES)} 个仓库")

    for i, (f, wh) in enumerate(zip(files, WAREHOUSES)):
        print(f"\n[{i+1}/{len(files)}] {wh}")
        inv_path = copy_to_downloads(f, wh)
        generate_import(inv_path, wh)

    print(f"\n[完成] 文件已整理:")
    print(f"  下载: {DOWNLOADS_DIR}")
    print(f"  输出: {OUTPUT_DIR}")


def main():
    mcp_dir = DEFAULT_MCP_DIR

    args = sys.argv[1:]
    for arg in args:
        if arg.startswith("--from="):
            mcp_dir = Path(arg.split("=", 1)[1])
        elif arg == "--auto":
            auto(mcp_dir)
            return

    interactive(mcp_dir)


if __name__ == "__main__":
    main()
