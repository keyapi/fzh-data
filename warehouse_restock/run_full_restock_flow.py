#!/usr/bin/env python3
"""
run_full_restock_flow.py
赛狐海外仓备货单 完整流程调度器

流程:
  1. 导出库存明细 (sellfox_auto_export.py --headless)
  2. (可选) 其他出库清零: 生成Excel + 导入赛狐
  3. 海外仓备货单: 生成Excel(双格式) + 导入赛狐

用法:
  python run_full_restock_flow.py                    # 全部步骤（含确认）
  python run_full_restock_flow.py --skip-zero-out     # 跳过清零步骤
  python run_full_restock_flow.py --export-only       # 仅导出库存明细
  python run_full_restock_flow.py --generate-only     # 仅生成Excel(不导入赛狐)
  python run_full_restock_flow.py --yes               # 跳过所有确认（危险！）
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ── 路径配置 ──────────────────────────────────────────────

CURSOR_ROOT = Path(__file__).resolve().parent.parent
WEB_AUTO = Path(r"D:\Work\赛狐\网页自动化")
CURSOR_VENV = CURSOR_ROOT / ".venv" / "Scripts" / "python.exe"
WEB_VENV = WEB_AUTO / ".venv" / "Scripts" / "python.exe"

# 关键脚本
EXPORT_SCRIPT = WEB_AUTO / "sellfox_auto_export.py"
IMPORT_OUTBOUND_SCRIPT = WEB_AUTO / "sellfox_import_other_outbound.py"
IMPORT_RESTOCK_SCRIPT = WEB_AUTO / "sellfox_import_warehouse_restock.py"
GEN_OUTBOUND_SCRIPT = CURSOR_ROOT / "other_outbound" / "build_saihu_other_outbound.py"
GEN_RESTOCK_SCRIPT = Path(__file__).resolve().parent / "build_saihu_warehouse_restock.py"

# 关键目录
OUTBOUND_DATA_DIR = CURSOR_ROOT / "other_outbound" / "数据源"
OUTBOUND_OUT_DIR = WEB_AUTO / "outbound"
RESTOCK_OUT_DIR = WEB_AUTO / "restock"
DOWNLOADS_DIR = WEB_AUTO / "downloads"


def run_py(script: Path, cwd: Path, venv: Path, *extra_args) -> int:
    """运行 Python 脚本，返回 exit code。"""
    args = [str(venv), str(script)] + list(extra_args)
    print(f"\n  > 执行: {' '.join(str(a) for a in args[-3:]) if len(args) > 4 else script.name}")
    print(f"  > 工作目录: {cwd}")
    result = subprocess.run(args, cwd=str(cwd), encoding="utf-8",
                            errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return result.returncode


def confirm(prompt: str) -> bool:
    """用户确认。非交互模式下默认跳过危险操作。"""
    if "--yes" in sys.argv:
        return True
    try:
        ans = input(f"\n{prompt} [y/N] ").strip().lower()
        return ans in ("y", "yes")
    except EOFError:
        print("  (非交互模式，默认跳过)")
        return False


def find_latest_export() -> Path | None:
    """找到最新的 WarehouseItem*.xlsx 导出文件。"""
    candidates = sorted(
        [f for f in DOWNLOADS_DIR.glob("WarehouseItem*.xlsx") if not f.name.startswith("~$")],
        key=lambda f: f.stat().st_mtime, reverse=True
    )
    return candidates[0] if candidates else None


# ── 各步骤 ────────────────────────────────────────────────

def step_export_stock() -> Path | None:
    """Step 1: 导出赛狐库存明细（headless 浏览器模式）。"""
    print("\n" + "=" * 60)
    print("Step 1: 导出赛狐库存明细")
    print("=" * 60)

    ret = run_py(EXPORT_SCRIPT, WEB_AUTO, WEB_VENV, "--headless")
    if ret != 0:
        print("[失败] 导出脚本返回非 0")
        return None

    latest = find_latest_export()
    if not latest:
        print("[失败] 未找到导出文件")
        return None

    # 复制到 other_outbound 数据源
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    dst = OUTBOUND_DATA_DIR / f"赛狐库存明细_{stamp}.xlsx"
    dst.parent.mkdir(exist_ok=True)
    shutil.copy(latest, dst)
    print(f"\n  导出文件: {latest.name} ({latest.stat().st_size / 1024:.0f} KB)")
    print(f"  已复制到: {dst}")
    return dst


def step_gen_other_outbound(inv_file: Path) -> list[Path] | None:
    """Step 2a: 生成其他出库 Excel 文件。"""
    print("\n" + "=" * 60)
    print("Step 2a: 生成其他出库导入文件")
    print("=" * 60)

    ret = run_py(GEN_OUTBOUND_SCRIPT, GEN_OUTBOUND_SCRIPT.parent, CURSOR_VENV)
    if ret != 0:
        print("[失败] 其他出库生成脚本返回非 0")
        return None

    # 找到最新输出
    out_dirs = sorted((GEN_OUTBOUND_SCRIPT.parent / "out").iterdir(), reverse=True)
    if not out_dirs:
        print("[失败] 未找到输出目录")
        return None

    latest = out_dirs[0]
    files = sorted(f for f in latest.glob("赛狐_其他出库_导入_*.xlsx"))
    print(f"\n  生成 {len(files)} 个文件:")
    for f in files:
        print(f"    {f.name} ({f.stat().st_size / 1024:.0f} KB)")
    return files


def step_import_outbound(files: list[Path]) -> bool:
    """Step 2b: 导入其他出库文件到赛狐。"""
    print("\n" + "=" * 60)
    print("Step 2b: 导入其他出库到赛狐")
    print("=" * 60)

    # 复制到 网页自动化/outbound/
    OUTBOUND_OUT_DIR.mkdir(exist_ok=True)
    # 清空旧文件
    for old in OUTBOUND_OUT_DIR.glob("赛狐_其他出库_导入_*.xlsx"):
        old.unlink()

    copied = []
    for f in files:
        dst = OUTBOUND_OUT_DIR / f.name
        shutil.copy(f, dst)
        copied.append(dst)
        print(f"  已复制: {dst.name}")

    print("\n⚠ 导入需要打开浏览器。赛狐导入后需手动'确认出库'。")
    if not confirm("确认导入其他出库文件到赛狐？"):
        print("  已跳过导入")
        return False

    ret = run_py(IMPORT_OUTBOUND_SCRIPT, WEB_AUTO, WEB_VENV)
    if ret != 0:
        print("[警告] 导入脚本返回非 0，请检查浏览器")
        return False
    return True


def step_gen_warehouse_restock() -> list[Path] | None:
    """Step 3a: 生成海外仓备货单 Excel 文件（双格式）。"""
    print("\n" + "=" * 60)
    print("Step 3a: 生成海外仓备货单导入文件（格式1 + 格式2）")
    print("=" * 60)

    ret = run_py(GEN_RESTOCK_SCRIPT, GEN_RESTOCK_SCRIPT.parent, CURSOR_VENV)
    if ret != 0:
        print("[失败] 备货单生成脚本返回非 0")
        return None

    out_dirs = sorted((GEN_RESTOCK_SCRIPT.parent / "out").iterdir(), reverse=True)
    if not out_dirs:
        print("[失败] 未找到输出目录")
        return None

    latest = out_dirs[0]
    # 只收集格式2文件（不含"旧格式"和"问题报告"）
    files = sorted(
        f for f in latest.glob("赛狐_海外仓备货单_导入_*.xlsx")
        if "旧格式" not in f.name and "问题报告" not in f.name
    )
    print(f"\n  格式2文件 ({len(files)} 个):")
    for f in files:
        print(f"    {f.name} ({f.stat().st_size / 1024:.0f} KB)")

    old_files = sorted(f for f in latest.glob("*旧格式*.xlsx"))
    print(f"  格式1备份 ({len(old_files)} 个，不导入)")
    return files


def step_import_restock(files: list[Path]) -> bool:
    """Step 3b: 导入海外仓备货单文件到赛狐。"""
    print("\n" + "=" * 60)
    print("Step 3b: 导入海外仓备货单到赛狐")
    print("=" * 60)

    # 复制到 网页自动化/restock/
    RESTOCK_OUT_DIR.mkdir(exist_ok=True)
    for old in RESTOCK_OUT_DIR.glob("赛狐_海外仓备货单_导入_*.xlsx"):
        old.unlink()

    copied = []
    for f in files:
        dst = RESTOCK_OUT_DIR / f.name
        shutil.copy(f, dst)
        copied.append(dst)
        print(f"  已复制: {dst.name}")

    print(f"\n⚠ 即将导入 {len(copied)} 个备货单文件（格式2：绍兴+加工→采购单价，头程→头程费用）。")
    if not confirm("确认导入海外仓备货单到赛狐？"):
        print("  已跳过导入")
        return False

    ret = run_py(IMPORT_RESTOCK_SCRIPT, WEB_AUTO, WEB_VENV)
    if ret != 0:
        print("[警告] 导入脚本返回非 0，请检查浏览器")
        return False
    return True


# ── 主流程 ────────────────────────────────────────────────

def main():
    export_only = "--export-only" in sys.argv
    generate_only = "--generate-only" in sys.argv
    skip_zero = "--skip-zero-out" in sys.argv

    print("=" * 60)
    print("赛狐海外仓备货单 — 完整流程")
    print("=" * 60)

    flags = []
    if export_only:
        flags.append("仅导出")
    if generate_only:
        flags.append("仅生成Excel")
    if skip_zero:
        flags.append("跳过清零")
    if flags:
        print(f"选项: {', '.join(flags)}")
    print()

    # Step 1: 导出库存明细
    inv_file = step_export_stock()
    if not inv_file:
        print("\n[中止] 库存导出失败")
        return
    if export_only:
        print("\n完成！(仅导出)")
        return

    # Step 2: 其他出库清零（可选）
    if skip_zero:
        print("\n跳过 Step 2 (其他出库清零)")
    else:
        if confirm("是否执行 其他出库清零？(需要导入赛狐 + 手动确认出库)"):
            outbound_files = step_gen_other_outbound(inv_file)
            if outbound_files and not generate_only:
                step_import_outbound(outbound_files)
        else:
            print("  跳过其他出库清零")

    # Step 3: 海外仓备货单
    if confirm("是否生成海外仓备货单导入文件？"):
        restock_files = step_gen_warehouse_restock()
        if restock_files and not generate_only:
            step_import_restock(restock_files)

    print("\n" + "=" * 60)
    print("流程结束")
    print("=" * 60)
    print("后续手动操作:")
    print("  1. 赛狐 其他出库页面 → 逐条确认出库")
    print("  2. 赛狐 海外仓备货单页面 → 检查收货入库状态")


if __name__ == "__main__":
    main()
