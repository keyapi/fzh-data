#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PB 订单履约文件本地生成（Colab notebook 步骤 1-2 / 3 / 4 / 4.2 的本地化）。

原来要跑 Google Colab，得把 11MB 的 Packslip PDF 上传上去；数据本来就在本地
`D:\\Work\\美国\\Tracy Miller\\PB orders\\<YYYYMMDD>\\`，所以改成一条命令本地出件。

从当天文件夹产出（默认与输入同目录，沿用历史惯例）：
    1. PB_0_导入_原始_{csv_stem}_on_{ts}.xlsx        通途导入
    2. {MM.DD} PotteryBarn label-FZH-DANEEY-Not Prime-第一天.pdf   步骤 4
    3. {MM.DD} PotteryBarn 背贴-中文西班牙语.pdf                    步骤 4.2

用 `--no-stock "SKU-A,SKU-B"` 指出无货 SKU 时（只在有货才发的场景）：
    - 通途额外产出 PB_1_不可导入_无库存_ / PB_2_导入_库存有货_
    - 主标签/背贴 PDF **只含有货订单的页**
    - 另出一份「无货{N单M件}-{MM.DD} …」子集标签/背贴 PDF，给无货那几单单独留着

用法：
    uv run python run_pb_orders.py --dir "D:\\Work\\美国\\Tracy Miller\\PB orders\\20260921"
    uv run python run_pb_orders.py --dir "...\\20260921" --dry-run
    uv run python run_pb_orders.py --dir "...\\20260921" --no-stock "SKU-A" --check-shipment

本文件只是 `service.py` 的薄适配器：编排、校验和报告都在 service 层，
Web/队列复用同一套逻辑（见 `web/tasks.py`）。

不做的：赛狐导入（原步骤 3.x）、按仓库分拆（原 4.3，已停用）、邮件对账（归 pb_reconciliation）。
"""

import argparse
import sys
from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

import service  # noqa: E402

PDF_PATTERN = service.PDF_PATTERN
CSV_PATTERN = service.CSV_PATTERN
SHIPMENT_PATTERN = service.SHIPMENT_PATTERN


def _print_report(report, dry_run):
    print("=" * 62)
    print("PB 订单履约（步骤 1-2 / 3 / 4 / 4.2）")
    print("=" * 62)
    print(f"Packslip : {report['inputs']['packslip']}")
    print(f"订单 CSV : {report['inputs']['order_csv']}")
    if dry_run:
        print("输出目录 : [dry-run 不写文件]")

    pdf = report["pdf"]
    print(
        f"\n[步骤 1-2] PDF {pdf['pages']} 页 | 唯一 PO {pdf['unique_po']}"
        f" | PO 抽取失败 {pdf['po_fail']} | Item 抽取失败 {pdf['item_fail']}"
    )
    orders = report["orders"]
    print(
        f"[步骤 3]   拆行后 {orders['rows']} 行 | 通途列数 {orders['columns']}"
        f" | 可导入 {orders['importable']} | 无库存 {orders['no_stock_rows']}"
    )

    ship = report.get("shipment")
    if ship:
        print(f"[发货核对] {ship['file']}: 订单 {ship['ordered']} 件 vs 实发 {ship['shipped']} 件")
        if not ship["short"]:
            print("[发货核对] 逐 SKU 均已发齐，无缺货")
        else:
            print(f"[发货核对] 缺货 {len(ship['short'])} 个 SKU（需人工判断是否用 --no-stock 剔除）:")
            for row in ship["short"]:
                print(f"    {row['sku']}: 订 {row['ordered']} 发 {row['shipped']} 差 {row['diff']}")

    print(f"\n[1:1 校验] PDF {pdf['pages']} 页 == 订单 {orders['rows']} 行  ✓")
    print(f"[join]     未匹配 {report['join']['unmatched']}")
    if report["join"]["unmatched"]:
        print(f"  未匹配的 PO Number-Line: {report['join']['unmatched_sample']}")

    for out in report["outputs"]:
        pages = f" {out['pages']} 页" if "pages" in out else ""
        print(f"[产物]     {out['kind']}:{pages} {out['name']}")

    if report.get("missing_names"):
        print(f"[背贴]     缺名称 SKU {len(report['missing_names'])}")

    print()
    for rec in report["reconciliation"]:
        print(
            f"[数量对账] {rec['label']} {rec['total']} = {rec['parts']} | 差 {rec['diff']}"
        )
    for warn in report["warnings"]:
        print(f"[警告] {warn}")
    print("=" * 62)


def run(args):
    in_dir = Path(args.dir).resolve()
    if not in_dir.is_dir():
        sys.exit(f"目录不存在: {in_dir}")

    options = service.JobOptions(
        no_stock=[s for s in (args.no_stock or "").split(",") if s.strip()],
        no_stock_note=args.no_stock_note,
        allow_unmatched=args.allow_unmatched,
        cache_only=args.cache_only,
        check_shipment=args.check_shipment,
        validate_only=args.dry_run,
    )
    out_dir = Path(args.out).resolve() if args.out else in_dir
    pdf_path = service.resolve_input(in_dir, args.pdf, PDF_PATTERN, "Packslip PDF")
    csv_path = service.resolve_input(in_dir, args.csv, CSV_PATTERN, "订单 CSV")

    print(f"输入目录 : {in_dir}")
    print(f"输出目录 : {out_dir}{'  [dry-run 不写文件]' if args.dry_run else ''}")

    try:
        result = service.run_job(
            pdf_path,
            csv_path,
            options,
            output_dir=None if args.dry_run else out_dir,
            progress=lambda _step, msg: print(f"  … {msg}"),
            shipment_csv=service.pick_newest(in_dir, SHIPMENT_PATTERN),
        )
    except service.PBJobError as exc:
        print(f"\n[失败] {exc.message}")
        if exc.hint:
            print(f"  {exc.hint}")
        sys.exit(1)

    _print_report(result.report, args.dry_run)


def build_parser():
    ap = argparse.ArgumentParser(
        description="PB 订单履约：Packslip PDF + 订单 CSV -> 通途 xlsx + 标签 PDF + 背贴 PDF"
    )
    ap.add_argument("--dir", required=True, help="当天文件夹（含 Packslip PDF 与订单 CSV）")
    ap.add_argument("--pdf", default=None, help=f"Packslip PDF 文件名，默认自动取最新 {PDF_PATTERN}")
    ap.add_argument("--csv", default=None, help=f"订单 CSV 文件名，默认自动取最新 {CSV_PATTERN}")
    ap.add_argument("--no-stock", default="", help="无货 SKU，逗号分隔；默认空 = 不过滤")
    ap.add_argument(
        "--no-stock-note", default=None,
        help='无货子集文件名前缀里的描述，默认自动 "N单M件"，例："4单6个三角灰97"',
    )
    ap.add_argument("--out", default=None, help="输出目录，默认与 --dir 相同")
    ap.add_argument("--check-shipment", action="store_true", help="只读核对 ASN 实发数量并报缺货")
    ap.add_argument("--allow-unmatched", action="store_true", help="join 未匹配时不中止")
    ap.add_argument("--cache-only", action="store_true", help="背贴名称表只用本地缓存，不联网")
    ap.add_argument("--dry-run", action="store_true", help="只算不写")
    return ap


if __name__ == "__main__":
    run(build_parser().parse_args())
