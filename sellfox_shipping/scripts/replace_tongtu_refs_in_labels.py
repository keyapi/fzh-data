"""Replace 通途 P-numbers with 赛狐 package numbers in lizard label PDF.

Reads sellfox-native-fixture/00-tongtu-to-sellfox-package-map.csv
(P814xxxxx → P2xxxx), then replaces CUST REF / Ref No in the source PDF.

Usage:
  uv run python sellfox_shipping/scripts/replace_tongtu_refs_in_labels.py

Requires: pymupdf (``uv add pymupdf`` if missing).
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

import fitz  # pymupdf

MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MODULE_ROOT / "数据源" / "蜥蜴国际-p0-样例"
FIXTURE_DIR = DATA_DIR / "sellfox-native-fixture"
CSV_PATH = FIXTURE_DIR / "00-tongtu-to-sellfox-package-map.csv"
PDF_IN = DATA_DIR / "4 04-lizard-labels-2026-07-15 7.15蜴国际面单.pdf"
PDF_OUT = FIXTURE_DIR / "04-lizard-labels-2026-07-15.pdf"


def load_mapping(csv_path: Path) -> dict[str, str]:
    mapping = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            mapping[row["tongtu_ref"].strip()] = row["sellfox_package_sn"].strip()
    return mapping


def get_page_font(page: fitz.Page, prefix: str) -> tuple[str, float]:
    """Extract font name and size from a page's text span matching prefix."""
    blocks = page.get_text("dict")["blocks"]
    for block in blocks:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if prefix in span["text"]:
                    return span["font"], span["size"]
    return "Helvetica-Bold", 14.3  # fallback from verified sample


def replace_labels(pdf_in: Path, pdf_out: Path, mapping: dict[str, str]) -> int:
    doc = fitz.open(str(pdf_in))
    replaced = 0

    for page in doc:
        for pnum, sellfox_sn in mapping.items():
            # Two formats observed in lizard labels: 'CUST REF: Pxxxx' and 'Ref No:Pxxxx'
            for fmt_prefix, replacement_prefix in [
                (f"CUST REF: {pnum}", "CUST REF: "),
                (f"Ref No:{pnum}", "Ref No:"),
            ]:
                areas = page.search_for(fmt_prefix)
                if not areas:
                    continue

                rect = areas[0]
                font, size = get_page_font(page, fmt_prefix.split(":")[0])

                page.add_redact_annot(rect)
                page.apply_redactions()

                new_text = f"{replacement_prefix}{sellfox_sn}"
                page.insert_text(
                    (rect.x0, rect.y1 - 2),
                    new_text,
                    fontname=font,
                    fontsize=size,
                    color=(0, 0, 0),
                )
                replaced += 1
                break  # one P-number per page

    pdf_out.parent.mkdir(exist_ok=True)
    if pdf_out.exists():
        os.remove(pdf_out)
    doc.save(str(pdf_out), garbage=4, deflate=True)
    doc.close()
    return replaced


def verify(pdf_out: Path) -> None:
    doc = fitz.open(str(pdf_out))
    old_p = sum(1 for i in range(len(doc)) if "P814" in doc[i].get_text())
    new_sf = sum(
        1
        for i in range(len(doc))
        if "P2AJA" in doc[i].get_text() or "P2AKA" in doc[i].get_text()
    )
    doc.close()
    print(f"P814 remaining: {old_p} (should be 0)")
    print(f"P2AJA/P2AKA pages: {new_sf} (should be 38)")


if __name__ == "__main__":
    mapping = load_mapping(CSV_PATH)
    print(f"Loaded {len(mapping)} P-number mappings")
    n = replace_labels(PDF_IN, PDF_OUT, mapping)
    print(f"Replaced: {n}/38")
    verify(PDF_OUT)
    print(f"Output: {PDF_OUT}")
    print(f"Size: {PDF_OUT.stat().st_size} bytes")
