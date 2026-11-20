#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 Camping World 入驻表格的预填草稿（全部落在仓库外）。

只写**有把握**的字段；无法确认的一律留空并写入缺项清单。
原始模板不被修改：先复制到输出目录，再在副本上写值。

用法:
  uv run python camping_world/build_vendor_forms.py
  uv run python camping_world/build_vendor_forms.py --src "D:/.../入驻包" --out "D:/.../填表草稿"
"""
from __future__ import annotations

import argparse
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import openpyxl

DEFAULT_SRC = Path(r"D:\Work\美国\Tracy Miller\Camping World\2026-11-19 入驻包")
DEFAULT_OUT = Path(r"D:\Work\美国\Tracy Miller\Camping World\填表草稿")

VENDOR_FORM = "2 -Vendor Information Form.xlsx"
ITEM_SETUP = "8 - 2026 Item Set UP FINAL 3.5.26.xlsx"
QUOTATION = "Camping World Product Quotation_English.xlsx"

BRAND = "SKYROOM by Tracy Miller"
EDI_EMAIL = "us@mxdeals.com"
EDI_CONTACT = "Key / FZH Data Team"


@dataclass
class QuoteRow:
    product: str
    fabric: str
    color: str
    size: str
    retail: float
    supply: float
    weight: float
    dims: tuple[float, float, float]


def parse_dims(text: str) -> tuple[float, float, float]:
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
    if len(nums) < 3:
        return (0.0, 0.0, 0.0)
    return (nums[0], nums[1], nums[2])


def load_quotes(path: Path) -> list[QuoteRow]:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Sheet1"]
    rows: list[QuoteRow] = []
    product = fabric = color = ""
    for r in range(2, ws.max_row + 1):
        vals = [ws.cell(r, c).value for c in range(1, 11)]
        if vals[2]:
            product = str(vals[2]).strip()
        if vals[3]:
            fabric = str(vals[3]).strip()
        if vals[4]:
            color = str(vals[4]).strip()
        size = str(vals[5]).strip() if vals[5] else ""
        if not size:
            continue
        rows.append(
            QuoteRow(
                product=product,
                fabric=fabric,
                color=color,
                size=size,
                retail=float(vals[6] or 0),
                supply=float(vals[7] or 0),
                weight=float(vals[8] or 0),
                dims=parse_dims(str(vals[9] or "")),
            )
        )
    wb.close()
    return rows


def register_desc(q: QuoteRow) -> str:
    short = {
        "Triangle Pillow": "Tri",
        "Couch Cushion": "Couch",
        "Corner Pillow": "Corner",
        "Bone Pillow": "Bone",
        "Arm Support Pillow": "Arm",
        "Dual-Use Side-Sleeping Wedge": "Side Wedge",
    }.get(q.product, q.product[:8])
    text = f"SKYROOM {short} {q.size}"
    return text[:20]


def long_desc(q: QuoteRow) -> str:
    return (
        f"{BRAND} - {q.product}, {q.fabric}, {q.size}. "
        "Designed for RVs, campers, cabins and favorite getaways."
    )


def fill_vendor_form(src: Path, out_dir: Path, missing: list[str]) -> Path:
    target = out_dir / "Vendor Information Form_草稿.xlsx"
    shutil.copy2(src / VENDOR_FORM, target)
    wb = openpyxl.load_workbook(target)
    ws = wb["Sheet1"]

    ws["B31"] = "Yes"
    ws["C35"] = EDI_CONTACT
    ws["F36"] = EDI_EMAIL
    ws["F40"] = 0.03
    ws["F45"] = 0.01
    ws["Q40"] = 30
    ws["P46"] = "FOB Destination"
    ws["P50"] = "Daneey LLC - USTX (pending confirmation)"

    for field in [
        "Corporate Information 公司名/地址/电话/网站",
        "Remit Payment To Address",
        "Purchase Order Information",
        "Ship From Information 完整地址与联系人",
        "Sales Representative（Tracy 公司地址）",
        "Store to Vendor Questions / 退货地址",
        "EDI Contact 电话",
        "Separate Dropship Fee?",
        "Total Order Minimum",
        "Lead Time / 到 CW 两仓的运输时间",
    ]:
        missing.append(f"Vendor Information Form: {field}")

    wb.save(target)
    return target


def fill_item_setup(src: Path, out_dir: Path, quotes: list[QuoteRow], missing: list[str]) -> Path:
    target = out_dir / "2026 Item Set UP_草稿.xlsx"
    shutil.copy2(src / ITEM_SETUP, target)
    wb = openpyxl.load_workbook(target)
    ws = wb["Item Set Up Info"]

    start_row = 10
    for idx, q in enumerate(quotes):
        r = start_row + idx
        ws.cell(r, 6, "")  # F Vendor/Supplier Name - 主体未定
        ws.cell(r, 7, BRAND)
        ws.cell(r, 8, f"{q.product} - {q.size}")
        ws.cell(r, 9, register_desc(q))
        ws.cell(r, 10, long_desc(q))
        ws.cell(r, 11, "Textile pillow / support cushion")
        ws.cell(r, 14, q.supply)
        ws.cell(r, 15, q.retail)
        ws.cell(r, 18, 1)  # Inner case pack qty
        ws.cell(r, 22, q.weight)
        ws.cell(r, 23, f"=X{r}*Y{r}*Z{r}")
        ws.cell(r, 24, q.dims[0])
        ws.cell(r, 25, q.dims[1])
        ws.cell(r, 26, q.dims[2])
        ws.cell(r, 29, q.fabric)
        ws.cell(r, 30, "No")
        ws.cell(r, 31, "No")
        ws.cell(r, 35, "N/A")
        ws.cell(r, 41, "FOB")
        ws.cell(r, 42, "Daneey LLC - USTX (pending)")
        ws.cell(r, 45, "CN")

    missing.extend(
        [
            "Item Set Up: Vendor/Supplier Name（等签约主体）",
            f"Item Set Up: UPC/EAN × {len(quotes)} 行（12-13 位，需 GS1）",
            f"Item Set Up: HTS 8 位编码 × {len(quotes)} 行",
            "Item Set Up: Country of Origin 已暂填 CN，需确认",
            "Item Set Up: Prop 65 Warning# / Chemical",
            "Item Set Up: MAP Price",
            "Item Set Up: Case Pack Qty / MOQ / Full Container Qty",
            "Item Set Up: Freight Class / Freight Policy",
            "Item Set Up: Warranty Product/Labor Terms",
            "Item Set Up: Return / Warranty Claim Instructions",
            "Item Set Up: Production Lead Time",
            "Item Set Up: In-Transit Lead Time to Arvin, CA & Lebanon, IN",
            "Item Set Up: MPN / VPN",
        ]
    )

    wb.save(target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not (args.src / VENDOR_FORM).is_file():
        raise SystemExit(f"缺少模板：{args.src / VENDOR_FORM}")
    args.out.mkdir(parents=True, exist_ok=True)

    quotes = load_quotes(args.src / QUOTATION)
    missing: list[str] = []

    vendor = fill_vendor_form(args.src, args.out, missing)
    items = fill_item_setup(args.src, args.out, quotes, missing)

    report = args.out / "缺项清单.md"
    lines = [
        "# Camping World 填表缺项清单",
        "",
        f"生成时间：2026-11-20；产品行数：{len(quotes)}",
        "",
        "## 已生成",
        "",
        f"- `{vendor.name}`",
        f"- `{items.name}`",
        "",
        "## 已预填",
        "",
        "- EDI capabilities = Yes；EDI 联系人 / 邮箱",
        "- Co-op 3%、Defective 1%、Net 30",
        "- Incoterm FOB Destination；Ship-from 暂填 Daneey LLC - USTX",
        "- Item Set Up：品牌、描述、供货价、MSRP、包装重量尺寸、材质、原产地暂填 CN",
        "",
        "## 缺项",
        "",
    ]
    lines += [f"- {m}" for m in missing]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"已生成 {vendor.name}")
    print(f"已生成 {items.name}（{len(quotes)} 行产品）")
    print(f"缺项清单：{report}")
    print(f"缺项 {len(missing)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
