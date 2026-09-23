#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPS New 订单库存预检（履约前的那一步，本地化）。

出件之前有一道人工动作：在 SPS 里把 New 订单全选导出原始 CSV，
按 `Vendor Style` 对照当前断货清单，剔掉缺货条明细，得到 `checked0stock …`，
再拿它在 SPS 里勾 ASN 明细、发新日期通知。

本脚本把「导出 CSV → checked CSV + 操作表」这一步自动化，产出：

    1. `checked0stock {stem}.csv`            —— 给下一步出件用
    2. `SPS库存检查操作表-{stem}.xlsx`        —— 人在 SPS 里照着勾

**分类口径按明细行，不按整单**（见模块 docstring `stock_precheck.py`）：
每个 PO 的 Header 一律保留；只有「全部明细都缺货」的 PO 才整组剔除。

用法：
    uv run python run_stock_check.py --dir "D:\\Work\\美国\\Tracy Miller\\PB orders\\20260917"
    uv run python run_stock_check.py --dir "..." --no-stock "SKU-A,SKU-B"
    uv run python run_stock_check.py --dir "..." --dry-run

本文件只是 `stock_precheck.py` 的薄适配器：分类、对账与产物都在服务层，
网页复用同一套逻辑（见 `web/tasks.py` 的 `_run_stock_check`）。
"""

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

import stock_precheck  # noqa: E402

# 待检查的原始导出：check0stock order x{N} YYYYMMDD_HHMM_SSSSSS.csv
RAW_CSV_PATTERN = re.compile(r"(?i)^check0stock.*\.csv$")


def pick_raw_csv(in_dir: Path, explicit: str | None) -> Path:
    if explicit:
        path = (in_dir / explicit).resolve()
        if not path.is_file():
            sys.exit(f"指定的 CSV 不存在: {path}")
        return path
    candidates = [
        p for p in in_dir.glob("*.csv")
        if RAW_CSV_PATTERN.match(p.name) and not p.name.startswith("~$")
    ]
    if not candidates:
        sys.exit(
            f"目录里没找到 check0stock*.csv：{in_dir}\n"
            "请从 SPS 的 New 订单列表导出原始 CSV 后再跑。"
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _print_report(report, checked_path, workbook_path):
    po, details, quantity = report["po"], report["details"], report["quantity"]
    print("=" * 62)
    print("SPS New 订单库存预检")
    print("=" * 62)
    print(f"输入 CSV : {report['input']['name']}")
    print(f"           {report['input']['rows']} 行 / {report['input']['columns']} 列")

    print("\n[断货 SKU（本次冻结）]")
    print("  " + ("、".join(report["no_stock_snapshot"]) or "（无，全量有货）"))

    print(
        f"\n[PO]     共 {po['total']} | 全有货 {po['fully_in_stock']}"
        f" | 部分缺货 {po['partially_out_of_stock']} | 全部缺货 {po['fully_out_of_stock']}"
        f" | 保留 {po['retained']}"
    )
    print(
        f"[明细]   共 {details['total']} | 有货 {details['in_stock']}"
        f" | 缺货 {details['out_of_stock']} | 保留 {details['retained']}"
    )
    print(
        f"[数量]   共 {quantity['total']} | 有货 {quantity['in_stock']}"
        f" | 缺货 {quantity['out_of_stock']}"
    )

    if report["mixed_po"]:
        print(
            f"\n[注意] {len(report['mixed_po'])} 个 PO 是「部分缺货」——"
            "**不要整单取消**：保留 Header，生成 ASN 时只勾有货明细行。"
        )
        for po_number in report["mixed_po"]:
            print(f"    {po_number}")

    print("\n[对账] PO/明细/数量 均无差数 ✓")
    print(f"\n[产物] {checked_path.name}")
    print(f"[产物] {workbook_path.name}")
    print("=" * 62)


def run(args):
    in_dir = Path(args.dir).resolve()
    if not in_dir.is_dir():
        sys.exit(f"目录不存在: {in_dir}")

    csv_path = pick_raw_csv(in_dir, args.csv)
    out_dir = Path(args.out).resolve() if args.out else in_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    skus = [s.strip() for s in (args.no_stock or "").split(",") if s.strip()]

    print(f"输入文件 : {csv_path}")
    print(f"输出目录 : {out_dir}{'  [dry-run 不落盘]' if args.dry_run else ''}")
    print(f"断货 SKU : {'、'.join(skus) if skus else '（无，不过滤）'}")

    # dry-run 走一遍完整流程（含产物自校验），但落在临时目录里，跑完删掉
    scratch = Path(tempfile.mkdtemp(prefix="pb-stock-check-dry-")) if args.dry_run else out_dir
    try:
        result = stock_precheck.run_stock_check(
            csv_path, skus, scratch, progress=lambda _step, msg: print(f"  … {msg}")
        )
    except stock_precheck.StockCheckError as exc:
        print(f"\n[失败] {exc.message}")
        if exc.hint:
            print(f"  {exc.hint}")
        sys.exit(1)
    finally:
        if args.dry_run:
            shutil.rmtree(scratch, ignore_errors=True)

    _print_report(result.report, result.checked_csv, result.operations_xlsx)


def build_parser():
    ap = argparse.ArgumentParser(
        description="SPS New 订单库存预检：原始订单 CSV -> checked CSV + SPS 操作表"
    )
    ap.add_argument("--dir", required=True, help="当天文件夹（含 SPS 导出的 check0stock*.csv）")
    ap.add_argument(
        "--csv", default=None,
        help="显式指定原始 CSV 文件名，默认自动取目录里最新的 check0stock*.csv",
    )
    ap.add_argument("--no-stock", default="", help="断货 SKU，逗号分隔；默认空 = 不过滤")
    ap.add_argument("--out", default=None, help="输出目录，默认与 --dir 相同")
    ap.add_argument("--dry-run", action="store_true", help="只校验与对账，不写产物")
    return ap


if __name__ == "__main__":
    run(build_parser().parse_args())
