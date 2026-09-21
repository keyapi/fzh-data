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

不做的：赛狐导入（原步骤 3.x）、按仓库分拆（原 4.3，已停用）、邮件对账（归 pb_reconciliation）。
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

import pb_back_label_pdf  # noqa: E402
import pb_label_pdf  # noqa: E402
import pb_tongtu_excel  # noqa: E402
import sps_pb_pdf  # noqa: E402

PDF_PATTERN = "Packslip*.pdf"
CSV_PATTERN = "checked0stock*.csv"
SHIPMENT_PATTERN = "shipment*.csv"


def pick_newest(dir_path, pattern):
    """取最新修改的匹配文件（跳过 ~$ 锁文件）；无则返回 None。"""
    if not dir_path.is_dir():
        return None
    files = [p for p in dir_path.glob(pattern) if not p.name.startswith("~$")]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def resolve_input(dir_path, explicit, pattern, label):
    path = Path(explicit).resolve() if explicit else pick_newest(dir_path, pattern)
    if path is None or not path.is_file():
        sys.exit(f"找不到{label}：目录 {dir_path} 下没有匹配 {pattern} 的文件，请用参数显式指定")
    return path.resolve()


def check_shipment(dir_path, df_rows):
    """只读交叉核对：用 ASN(shipment) CSV 的实发数量比对订单数量，报缺货 SKU。不删行。"""
    sp = pick_newest(dir_path, SHIPMENT_PATTERN)
    if sp is None:
        print(f"[发货核对] 跳过：目录下没有 {SHIPMENT_PATTERN}")
        return
    ship = pd.read_csv(sp, dtype=str)
    ship["_qty"] = pd.to_numeric(ship["Qty Ship"], errors="coerce").fillna(0).astype(int)
    ordered = df_rows.groupby("Vendor Style")["Qty Ordered"].sum().astype(int)
    shipped = ship.groupby("Vdr Item #")["_qty"].sum()
    cmp = pd.DataFrame({"ordered": ordered, "shipped": shipped}).fillna(0).astype(int)
    short = cmp[cmp["shipped"] < cmp["ordered"]]
    print(f"[发货核对] {sp.name}: 订单 {int(cmp['ordered'].sum())} 件 vs 实发 {int(cmp['shipped'].sum())} 件")
    if short.empty:
        print("[发货核对] 逐 SKU 均已发齐，无缺货")
    else:
        print(f"[发货核对] 缺货 {len(short)} 个 SKU（需人工判断是否用 --no-stock 剔除）:")
        for sku, r in short.iterrows():
            print(f"    {sku}: 订 {r['ordered']} 发 {r['shipped']} 差 {r['shipped'] - r['ordered']}")


def run(args):
    in_dir = Path(args.dir).resolve()
    if not in_dir.is_dir():
        sys.exit(f"目录不存在: {in_dir}")
    out_dir = Path(args.out).resolve() if args.out else in_dir
    pdf_path = resolve_input(in_dir, args.pdf, PDF_PATTERN, "Packslip PDF")
    csv_path = resolve_input(in_dir, args.csv, CSV_PATTERN, "订单 CSV")

    print("=" * 62)
    print("PB 订单履约（步骤 1-2 / 3 / 4 / 4.2）")
    print("=" * 62)
    print(f"输入目录 : {in_dir}")
    print(f"Packslip : {pdf_path.name}")
    print(f"订单 CSV : {csv_path.name}")
    print(f"输出目录 : {out_dir}{'  [dry-run 不写文件]' if args.dry_run else ''}")

    # ---------- 步骤 1-2：PDF 抽取 ----------
    df_pdf = sps_pb_pdf.build_page_df(pdf_path)
    po_fail = int(df_pdf[sps_pb_pdf.COL_PO].isna().sum())
    item_fail = int(df_pdf[sps_pb_pdf.COL_ITEM].isna().sum())
    print(
        f"\n[步骤 1-2] PDF {len(df_pdf)} 页 | 唯一 PO {df_pdf[sps_pb_pdf.COL_PO].nunique()}"
        f" | PO 抽取失败 {po_fail} | Item 抽取失败 {item_fail}"
    )

    # ---------- 步骤 3：订单 CSV -> 通途 xlsx ----------
    df_order = pb_tongtu_excel.build_order_df(csv_path)
    no_stock_skus = [s for s in (args.no_stock or "").split(",") if s.strip()]
    importable, no_stock = pb_tongtu_excel.split_no_stock(df_order, no_stock_skus)
    print(
        f"[步骤 3]   拆行后 {len(df_order)} 行 | 通途列数 {df_order.shape[1]}"
        f" | 可导入 {len(importable)} | 无库存 {len(no_stock)}"
    )

    if args.check_shipment:
        check_shipment(in_dir, importable)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    written = {}
    if not args.dry_run:
        written = pb_tongtu_excel.export(
            df_order, importable, no_stock, out_dir, csv_path.stem, ts
        )
        for key, path in written.items():
            print(f"           -> {path.name}")

    # ---------- 1:1 硬校验（对全量订单行；无货拆分是之后的事）----------
    if len(df_pdf) != len(df_order):
        print(
            f"\n[1:1 校验] 失败：PDF {len(df_pdf)} 页 != 订单 {len(df_order)} 行，"
            "拒绝生成 PDF 标签。"
        )
        print("  提示：请检查 SPS PDF 导出设置，可能 Qty per Carton 有不是 1 的。")
        sys.exit(1)
    print(f"\n[1:1 校验] PDF {len(df_pdf)} 页 == 订单 {len(df_order)} 行  ✓")

    # ---------- join：页 -> SKUxQTY（先用全量行 join，再按无货拆页）----------
    df_join, unmatched = sps_pb_pdf.join_pages_with_orders(df_pdf, df_order)
    print(f"[join]     未匹配 {len(unmatched)}")
    if unmatched:
        print(f"  未匹配的 PO Number-Line: {unmatched[:10]}")
        if not args.allow_unmatched:
            sys.exit(
                "  未匹配会往标签上写空 SKU，已中止。确认无害可加 --allow-unmatched 继续。"
            )

    # 按无货 SKU 把「页」分成两组（df_join 行序 == PDF 页序）
    if no_stock_skus:
        wanted = {s.strip().lower() for s in no_stock_skus if s.strip()}
        is_no_stock = df_join["Vendor Style"].astype(str).str.strip().str.lower().isin(wanted)
    else:
        is_no_stock = pd.Series(False, index=df_join.index)
    ns_idx = [i for i, flag in enumerate(is_no_stock) if flag]
    ok_idx = [i for i, flag in enumerate(is_no_stock) if not flag]
    if no_stock_skus and not ns_idx:
        print(f"警告：--no-stock 指定的 SKU 本批都没有，按全量出件: {no_stock_skus}")

    split = bool(ns_idx)
    df_ok = df_join.iloc[ok_idx].reset_index(drop=True) if split else df_join
    df_ns = df_join.iloc[ns_idx].reset_index(drop=True) if split else df_join.iloc[0:0]
    note = args.no_stock_note or f"{df_ns['PO Number'].nunique()}单{len(df_ns)}件"

    ts_mmdd = datetime.now().strftime("%m.%d")

    # ---------- 步骤 4 / 4.2：标签 PDF + 背贴 PDF ----------
    ns_label_name = pb_label_pdf.NO_STOCK_LABEL_PDF_NAME.format(note=note, mmdd=ts_mmdd)
    ns_back_name = pb_back_label_pdf.NO_STOCK_BACK_LABEL_PDF_NAME.format(note=note, mmdd=ts_mmdd)
    main_label_name = pb_label_pdf.LABEL_PDF_NAME.format(mmdd=ts_mmdd)
    main_back_name = pb_back_label_pdf.BACK_LABEL_PDF_NAME.format(mmdd=ts_mmdd)

    if args.dry_run:
        print(f"[步骤 4]   将输出 {len(ok_idx) * 2} 页 -> {main_label_name}")
        print(f"[步骤 4.2] 将输出 {len(df_ok)} 页 -> {main_back_name}")
        if split:
            print(f"[无货子集] 将输出 {len(ns_idx) * 2} 页 -> {ns_label_name}")
            print(f"[无货子集] 将输出 {len(df_ns)} 页 -> {ns_back_name}")
    else:
        label_path, label_pages = pb_label_pdf.build_label_pdf(
            pdf_path, df_ok["SKUxQTY"].astype(str).tolist(), out_dir, ts_mmdd=ts_mmdd,
            page_indices=ok_idx if split else None,
        )
        print(f"[步骤 4]   {len(ok_idx)} 页 -> {label_pages} 页  {label_path.name}")

        back_path, back_pages, missing_names = pb_back_label_pdf.build_back_label_pdf(
            df_ok, out_dir, ts_mmdd=ts_mmdd, use_cache_only=args.cache_only
        )
        print(f"[步骤 4.2] {back_pages} 页  {back_path.name}（缺名称 SKU {len(missing_names)}）")

        if split:
            ns_label, ns_label_pages = pb_label_pdf.build_label_pdf(
                pdf_path, df_ns["SKUxQTY"].astype(str).tolist(), out_dir, ts_mmdd=ts_mmdd,
                filename=ns_label_name, page_indices=ns_idx,
            )
            print(f"[无货子集] {len(ns_idx)} 页 -> {ns_label_pages} 页  {ns_label.name}")
            ns_back, ns_back_pages, _ = pb_back_label_pdf.build_back_label_pdf(
                df_ns, out_dir, ts_mmdd=ts_mmdd, filename=ns_back_name, use_cache_only=True
            )
            print(f"[无货子集] {ns_back_pages} 页  {ns_back.name}")

    # ---------- 数量对账 ----------
    print(
        f"\n[数量对账] 订单总行 {len(df_order)} = 可导入 {len(importable)} + 无库存 {len(no_stock)}"
        f" | 差 {len(df_order) - len(importable) - len(no_stock)}"
    )
    print(
        f"[数量对账] 页 {len(df_pdf)} = 有货 {len(ok_idx)} + 无货 {len(ns_idx)}"
        f" | 差 {len(df_pdf) - len(ok_idx) - len(ns_idx)}"
    )
    print(
        f"[数量对账] 标签 {len(ok_idx)}×2={len(ok_idx) * 2} 页"
        + (f" + 无货 {len(ns_idx)}×2={len(ns_idx) * 2} 页" if split else "")
        + f"；背贴 {len(df_ok)} 页" + (f" + 无货 {len(df_ns)} 页" if split else "")
    )
    print("=" * 62)


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
