# -*- coding: utf-8 -*-
"""独立校验：不经项目聚合，直接从 V1 结算 txt 重算 Tax / FBA。

与 ``read_amz_txt._normalize_v1_schema`` + ``tax_aggregate.tax_summary_df6`` /
``fba_adjust.FBA_DESCRIPTIONS`` 的口径对齐，但只依赖标准库（csv/decimal）：

- Tax = ``price-type`` 含 ``Tax`` 且非 ``MarketplaceFacilitator*`` 的 ``price-amount``
  （V2 里对应 amount-type∈{ItemPrice,Promotion} 且 description 含 Tax；
  MarketplaceFacilitator 是代扣税 → 归一化成 ItemWithheldTax，不计入 Tax）。
- FBA = 各 ItemFees 金额族里标签为 ``FBAPerUnitFulfillmentFee`` 的金额。

用法::

    uv run python amazon_period_tax/tests/verify_v1_independent.py
    uv run python amazon_period_tax/tests/verify_v1_independent.py --bucket-dir <dir> --folder 刘小菁

默认桶：``$LOCAL_NAS_PERIOD_ROOT/账期20261004-20261103``。
退出码 0 = 全部在容差内；1 = 有偏差或文件缺失。
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from decimal import Decimal
from pathlib import Path

BUCKET = "账期20261004-20261103"
FOLDER = "刘小菁"
STEM_GLOB = "AMZBJRYECLTDUS-2026-10-*.txt"
RATE_USD = Decimal("6.7367")  # Tax 汇总用的 USD 汇率（2026-10 汇率表）

# 上游（任务单）给出的基准：USD 金额 + 折算人民币
EXPECTED_TAX_USD = {
    "AMZBJRYECLTDUS-2026-10-08.txt": Decimal("630.51"),
    "AMZBJRYECLTDUS-2026-10-12.txt": Decimal("322.95"),
    "AMZBJRYECLTDUS-2026-10-26.txt": Decimal("1177.85"),
}
EXPECTED_TAX_TOTAL_USD = Decimal("2131.31")
EXPECTED_TAX_TOTAL_RMB = Decimal("14357.996077")
EXPECTED_FBA_USD = Decimal("-901.86")  # 来自 2026-10-26 的 FBAPerUnitFulfillmentFee
EXPECTED_FBA_RMB = Decimal("-6075.560262")
TOLERANCE = Decimal("0.01")

# V1 各金额族列：(type 列, amount 列, 归一化后的 V2 amount-type)
_FAMILIES = (
    ("price-type", "price-amount", "ItemPrice"),
    ("promotion-type", "promotion-amount", "Promotion"),
    ("item-related-fee-type", "item-related-fee-amount", "ItemFees"),
    ("shipment-fee-type", "shipment-fee-amount", "ItemFees"),
    ("order-fee-type", "order-fee-amount", "ItemFees"),
    ("direct-payment-type", "direct-payment-amount", "ItemFees"),
)


def _dec(raw: str | None) -> Decimal | None:
    s = (raw or "").strip()
    if not s:
        return None
    # 与 read_amz_txt 一致：逗号当小数点（部分国家站导出用 `,`）
    return Decimal(s.replace(",", "."))


def compute_file(path: Path) -> tuple[Decimal, Decimal]:
    """返回 (Tax USD, FBA USD)。仅按 V1 语义读取；遇到 V2 表头直接报错。"""
    tax = Decimal("0")
    fba = Decimal("0")
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        header = reader.fieldnames or []
        if "amount-type" in header or "price-type" not in header:
            raise ValueError(f"{path.name} 不是 V1 表头（amount-type/price-type 判定失败）")
        for row in reader:
            for type_col, amt_col, amount_type in _FAMILIES:
                label = (row.get(type_col) or "").strip()
                amount = _dec(row.get(amt_col))
                if not label or amount is None:
                    continue
                if amount_type == "ItemPrice" and label.startswith("MarketplaceFacilitator"):
                    continue  # 代扣税 → ItemWithheldTax，不算 Tax
                if amount_type == "ItemPrice" and "Tax" in label:
                    tax += amount
                if amount_type == "ItemFees" and label == "FBAPerUnitFulfillmentFee":
                    fba += amount
    return tax, fba


def _fail(msg: str) -> None:
    print(f"FAIL {msg}")
    global _failed
    _failed = True


_failed = False


def main() -> int:
    ap = argparse.ArgumentParser(description="V1 结算 txt Tax/FBA 独立校验")
    ap.add_argument("--bucket-dir", default="", help="账期桶目录；默认 $LOCAL_NAS_PERIOD_ROOT/<bucket>")
    ap.add_argument("--folder", default=FOLDER, help="人名文件夹")
    args = ap.parse_args()

    if args.bucket_dir:
        bucket_dir = Path(args.bucket_dir)
    else:
        root = os.environ.get("LOCAL_NAS_PERIOD_ROOT", "").strip()
        if not root:
            print("FAIL 未设置 LOCAL_NAS_PERIOD_ROOT，且未传 --bucket-dir")
            return 1
        bucket_dir = Path(root) / BUCKET

    folder = bucket_dir / args.folder
    files = sorted(folder.glob(STEM_GLOB))
    if not files:
        print(f"FAIL 未找到 V1 文件：{folder / STEM_GLOB}")
        return 1
    print(f"bucket={bucket_dir}  folder={args.folder}  files={len(files)}")

    total_tax = Decimal("0")
    total_fba = Decimal("0")
    print(f"{'file':<28}{'Tax USD':>12}{'FBA USD':>12}")
    for f in files:
        tax, fba = compute_file(f)
        total_tax += tax
        total_fba += fba
        print(f"{f.name:<28}{tax:>12}{fba:>12}")
        expected = EXPECTED_TAX_USD.get(f.name)
        if expected is None:
            _fail(f"{f.name} 不在基准清单里")
        elif abs(tax - expected) > TOLERANCE:
            _fail(f"{f.name} Tax={tax} 期望 {expected}")
    print(f"{'TOTAL':<28}{total_tax:>12}{total_fba:>12}")

    tax_rmb = (total_tax * RATE_USD).quantize(Decimal("0.000001"))
    fba_rmb = (total_fba * RATE_USD).quantize(Decimal("0.000001"))

    if abs(total_tax - EXPECTED_TAX_TOTAL_USD) > TOLERANCE:
        _fail(f"Tax 合计 {total_tax} 期望 {EXPECTED_TAX_TOTAL_USD}")
    if abs(tax_rmb - EXPECTED_TAX_TOTAL_RMB) > TOLERANCE:
        _fail(f"Tax 合计人民币 {tax_rmb} 期望 {EXPECTED_TAX_TOTAL_RMB}")
    if abs(total_fba - EXPECTED_FBA_USD) > TOLERANCE:
        _fail(f"FBA 合计 {total_fba} 期望 {EXPECTED_FBA_USD}")
    if abs(fba_rmb - EXPECTED_FBA_RMB) > TOLERANCE:
        _fail(f"FBA 合计人民币 {fba_rmb} 期望 {EXPECTED_FBA_RMB}")

    print(f"Tax RMB @{RATE_USD} = {tax_rmb}（期望 {EXPECTED_TAX_TOTAL_RMB}）")
    print(f"FBA RMB @{RATE_USD} = {fba_rmb}（期望 {EXPECTED_FBA_RMB}）")
    if _failed:
        print("结果：FAIL")
        return 1
    print("结果：OK（容差 0.01）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
