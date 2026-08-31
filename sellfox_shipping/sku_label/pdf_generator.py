"""SKU 背贴 PDF 生成 — 4×2 英寸标签，含包裹号 + 条形码 + 品名表。

从 Colab notebook (148 cells) 提取的核心逻辑，已跑 2 年稳定。
"""

from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.graphics.barcode import code128


# ── 常量（4×2 英寸标签）──────────────────────────────────────
PAGE_W, PAGE_H = 288, 144
MARGIN_L, MARGIN_R, MARGIN_TOP = 5, 5, 10
FONT_START, FONT_MIN, FONT_SHRINK, LEADING_SHRINK = 10, 5, 0.9, 0.9
COL_WIDTHS = [0.4 * cm, 2.55 * cm, 0.5 * cm, 3.25 * cm, 3.35 * cm]
HEADERS = ["#", "SKU", "QTY", "Name Chinese", "Nombres en español"]


# ── 语言检测 ──────────────────────────────────────────────────

def is_chinese(char: str) -> bool:
    return '一' <= char <= '鿿'


def split_text_by_language(text: str) -> list[tuple[str, bool]]:
    """按语言拆分文本为 [(片段, is_chinese), ...]。"""
    parts: list[tuple[str, bool]] = []
    current = ""
    current_is_cn = None
    for char in text:
        char_is_cn = is_chinese(char)
        if current_is_cn is None:
            current_is_cn = char_is_cn
        if char_is_cn == current_is_cn or not char_is_cn:
            current += char
        else:
            parts.append((current, current_is_cn))
            current = char
            current_is_cn = char_is_cn
    if current:
        parts.append((current, current_is_cn))
    return parts


def build_mixed_xml(text: str, cn_font: str = "STSong-Light", latin_font: str = "Helvetica") -> str:
    """将文本转为 reportlab Paragraph XML。"""
    result: list[str] = []
    for part, is_cn in split_text_by_language(text):
        if is_cn:
            result.append(f"<font name='{cn_font}'>{part}</font>")
        else:
            result.append(part)
    return "".join(result)


# ── 表格构建 ──────────────────────────────────────────────────

def _build_table(items: list[dict], font_size: float = 10, leading: float = 8) -> list:
    """构建 reportlab Table 数据。items: [{sku, qty, cn_name, es_name}, ...]"""
    styles = getSampleStyleSheet()
    ps = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=font_size, leading=leading)
    data = [HEADERS]
    for i, it in enumerate(items, 1):
        data.append([
            str(i),
            Paragraph(it["sku"], ps),
            str(it.get("qty", 1)),
            Paragraph(build_mixed_xml(it.get("cn_name", "")), ps),
            Paragraph(build_mixed_xml(it.get("es_name", "")), ps),
        ])
    return data


def _table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 1),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
        ("TOPPADDING", (0, 1), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ])


# ── 主函数 ────────────────────────────────────────────────────

def generate_sku_label_pdf(
    packages: list[dict],
    output_path: str,
    *,
    timestamp: str = "",
    warehouse_class: str = "",
) -> str:
    """生成背贴 PDF。

    packages: [{
        "package_sn": str,
        "items": [{"sku": str, "qty": int, "cn_name": str, "es_name": str}, ...]
    }, ...]

    返回 output_path。
    """
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c = canvas.Canvas(output_path, pagesize=(PAGE_W, PAGE_H))
    total = len(packages)

    for page, pkg in enumerate(packages, 1):
        sn = pkg["package_sn"]
        items = pkg.get("items", [])
        y = PAGE_H - MARGIN_TOP

        c.setFont("Helvetica", 8)
        c.drawString(MARGIN_L, y, f"Package Number: {sn}")
        y -= 9
        code128.Code128(sn, barHeight=10, fontSize=8, barWidth=1.2).drawOn(
            c, MARGIN_L + 100, y + 5
        )

        c.setFont("STSong-Light", 5)
        label = f"{timestamp}{warehouse_class}仓" if warehouse_class else timestamp
        c.drawRightString(PAGE_W - MARGIN_R - 10, PAGE_H - MARGIN_TOP + 3, label)
        c.drawRightString(PAGE_W - MARGIN_R - 10, PAGE_H - MARGIN_TOP - 3, f"{page} / {total}")

        font_size, leading = FONT_START, 9.5
        while True:
            t = Table(_build_table(items, font_size, leading), colWidths=COL_WIDTHS)
            t.setStyle(_table_style())
            t.wrapOn(c, PAGE_W - MARGIN_L - MARGIN_R, y)
            if y - t._height >= 0 or font_size <= FONT_MIN:
                break
            font_size *= FONT_SHRINK
            leading *= LEADING_SHRINK
        t.drawOn(c, MARGIN_L - 3, y - t._height)
        c.showPage()
    c.save()
    return output_path
