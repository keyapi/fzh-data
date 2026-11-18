# -*- coding: utf-8 -*-
"""把库存提醒渲染成 PNG 卡片（Pillow），用现有群机器人发图 + 下载按钮。

自定义机器人 ActionCard 的 Markdown 不能居中、不能配色；把设计稿直接渲染成图片，
再用 `![卡片](url)` 放进 ActionCard 正文，就能达到预览图效果，且不需要企业内部应用或
卡片模板。图片由 Pillow 在本机生成，上传 ERPNext 后发送。
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

WIDTH = 1000
MARGIN = 24
PAD = 44
GAP = 22

BG = "#F2F5F9"
CARD = "#FFFFFF"
NAVY = "#123A5A"
LIGHT = "#EAF3FA"
TEAL = "#0F8B8D"
TEXT = "#1F2933"
MUTED = "#6B7785"
SUBTLE = "#C9D6E3"
LINE = "#E3E8EF"

_FONT_REG = "C:/Windows/Fonts/msyh.ttc"
_FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
NEW_ROW_H = 38


def _font(size: int, *, bold: bool = False):
    from PIL import ImageFont

    return ImageFont.truetype(_FONT_BOLD if bold else _FONT_REG, size)


def _tw(draw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _center(draw, y: int, text: str, font, fill: str, width: int = WIDTH) -> None:
    draw.text(((width - _tw(draw, text, font)) / 2, y), text, font=font, fill=fill)


def _right(draw, x_right: int, y: int, text: str, font, fill: str) -> None:
    draw.text((x_right - _tw(draw, text, font), y), text, font=font, fill=fill)


def _fit(draw, text: str, font, max_width: int) -> str:
    text = " ".join(str(text or "").split())
    if _tw(draw, text, font) <= max_width:
        return text
    suffix = "…"
    while text and _tw(draw, text + suffix, font) > max_width:
        text = text[:-1]
    return text + suffix


def _wrap(draw, text: str, font, max_width: int, max_lines: int = 2) -> list[str]:
    """按字符折行（中文友好），最多 max_lines 行，末行加省略号。"""
    text = " ".join(str(text or "").split())
    lines: list[str] = []
    current = ""
    for char in text:
        if _tw(draw, current + char, font) <= max_width:
            current += char
            continue
        lines.append(current)
        current = char
        if len(lines) == max_lines:
            break
    if len(lines) < max_lines and current:
        lines.append(current)
    if not lines:
        return [""]
    if len(lines) == max_lines and _tw(draw, text, font) > max_width * max_lines:
        lines[-1] = _fit(draw, lines[-1] + "…", font, max_width)
    return lines


def _header(draw, height: int, title: str, subtitle: str) -> None:
    draw.rounded_rectangle([MARGIN, MARGIN, WIDTH - MARGIN, MARGIN + height],
                           radius=28, fill=NAVY)
    # 让头部下沿变直角
    draw.rectangle([MARGIN, MARGIN + height // 2, WIDTH - MARGIN, MARGIN + height], fill=NAVY)
    _center(draw, MARGIN + 30, title, _font(46, bold=True), "#FFFFFF")
    _center(draw, MARGIN + 96, subtitle, _font(22), SUBTLE)


def _stats(draw, y: int, height: int, left: tuple[str, str], right: tuple[str, str]) -> None:
    x0, x1 = MARGIN + PAD, WIDTH - MARGIN - PAD
    draw.rounded_rectangle([x0, y, x1, y + height], radius=18, fill=LIGHT)
    mid = (x0 + x1) // 2
    for base_x, (label, value) in ((x0 + 36, left), (mid + 12, right)):
        draw.text((base_x, y + 22), label, font=_font(20), fill=MUTED)
        draw.text((base_x, y + 52), value, font=_font(38, bold=True), fill=NAVY)


def _divider(draw, y: int, x0: int, x1: int) -> None:
    draw.line([x0, y, x1, y], fill=LINE, width=1)


def _footer(draw, y: int, note: str) -> None:
    _center(draw, y, note, _font(17), MUTED)


def _num(value) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _new_items(wh) -> list:
    return [item for item in wh.low if item.is_new]


def _low_height(result) -> int:
    height = MARGIN * 2 + 160 + GAP + 116 + GAP + 8 + 52
    for wh in result.warehouses:
        height += 52 + 24 + 10 + 8
        if wh.baseline_missing:
            height += NEW_ROW_H
        else:
            height += NEW_ROW_H * (len(_new_items(wh)) or 1)
    return height


def render_low_stock(result, path: str | Path, *, when: _dt.date | None = None,
                     new_count: int = 0) -> Path:
    """低库存汇总卡片：标题居中、统计框、各仓今日新增 SKU（不限条数）。"""
    from PIL import Image, ImageDraw

    day = when or _dt.date.today()
    height = _low_height(result)
    img = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([MARGIN, MARGIN, WIDTH - MARGIN, height - MARGIN], radius=28, fill=CARD)
    _header(draw, 160, "通途低库存提醒", day.isoformat())
    y = MARGIN + 160 + GAP
    _stats(draw, y, 116,
           ("低库存商品", f"{result.total_low} 个 SKU"),
           ("今日新增", f"{new_count} 个"))
    y += 116 + GAP + 8
    for wh in result.warehouses:
        draw.text((MARGIN + PAD, y + 4), _fit(draw, wh.warehouse, _font(26, bold=True),
                                              WIDTH - 2 * MARGIN - 2 * PAD - 230),
                  font=_font(26, bold=True), fill=TEXT)
        _right(draw, WIDTH - MARGIN - PAD, y + 4, f"{wh.count} 个 SKU", _font(26, bold=True), TEAL)
        if wh.baseline_missing:
            draw.text((MARGIN + PAD, y + 38), "昨日基线缺失，无法判断今日新增", font=_font(17), fill=MUTED)
            y += 62
            draw.text((MARGIN + PAD, y + 6), "该仓低库存明细请见下载 Excel", font=_font(18), fill=MUTED)
            y += NEW_ROW_H
        else:
            new_items = _new_items(wh)
            draw.text((MARGIN + PAD, y + 38), f"今日新增 {len(new_items)} 个", font=_font(17), fill=MUTED)
            y += 62
            if not new_items:
                draw.text((MARGIN + PAD, y + 6), "今日无新增", font=_font(18), fill=MUTED)
                y += NEW_ROW_H
            for item in new_items:
                label = f"• {item.sku}"
                if item.name:
                    label += f"  {item.name}"
                label = _fit(draw, label, _font(18), WIDTH - 2 * MARGIN - 2 * PAD - 130)
                draw.text((MARGIN + PAD, y + 4), label, font=_font(18), fill=TEXT)
                _right(draw, WIDTH - MARGIN - PAD, y + 4, f"库存{_num(item.available)}个",
                       _font(18, bold=True), TEAL)
                y += NEW_ROW_H
        y += 8
        _divider(draw, y, MARGIN + PAD, WIDTH - MARGIN - PAD)
        y += 6
    _footer(draw, height - MARGIN - 30, "完整明细见下载按钮 · 数据生成于 " +
            _dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out


def _inbound_height(result) -> int:
    height = MARGIN * 2 + 160 + GAP + 116 + GAP + 44 + 52
    for wh in result.warehouses:
        height += 54
        height += len(wh.items) * 66 if wh.items else 40
    return height


def render_inbound(result, path: str | Path) -> Path:
    """采购入库卡片：标题居中、统计框、分仓/产品明细。"""
    from PIL import Image, ImageDraw

    height = _inbound_height(result)
    img = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([MARGIN, MARGIN, WIDTH - MARGIN, height - MARGIN], radius=28, fill=CARD)
    _header(draw, 160, "通途采购入库提醒", f"{result.day.isoformat()} · 昨日入库")
    y = MARGIN + 160 + GAP
    _stats(draw, y, 116,
           ("入库商品", f"{result.total_skus} 个 SKU"),
           ("入库总数", f"{int(result.total_qty)} 个"))
    y += 116 + GAP + 12
    draw.text((MARGIN + PAD, y), "分仓明细", font=_font(28, bold=True), fill=NAVY)
    y += 46
    _divider(draw, y, MARGIN + PAD, WIDTH - MARGIN - PAD)
    y += 6
    for wh in result.warehouses:
        draw.text((MARGIN + PAD, y + 8), _fit(draw, wh.warehouse, _font(26, bold=True),
                                              WIDTH - 2 * MARGIN - 2 * PAD - 180),
                  font=_font(26, bold=True), fill=TEXT)
        total = f"{int(wh.total_qty)} 个" if wh.count else "无入库"
        _right(draw, WIDTH - MARGIN - PAD, y + 8, total, _font(24, bold=True),
               TEAL if wh.count else MUTED)
        y += 44
        if not wh.items:
            draw.text((MARGIN + PAD, y), "昨日无采购入库", font=_font(19), fill=MUTED)
            y += 40
        for item in wh.items:
            name = item.name or item.sku
            lines = _wrap(draw, name, _font(21), WIDTH - 2 * MARGIN - 2 * PAD - 120, max_lines=2)
            for line in lines:
                draw.text((MARGIN + PAD, y), line, font=_font(21), fill=TEXT)
            _right(draw, WIDTH - MARGIN - PAD, y, f"{int(item.qty)} 个", _font(21), TEXT)
            y += 26 * len(lines)
            draw.text((MARGIN + PAD, y), f"SKU：{item.sku}", font=_font(16), fill=MUTED)
            y += 34
        _divider(draw, y, MARGIN + PAD, WIDTH - MARGIN - PAD)
        y += 8
    _footer(draw, height - MARGIN - 30, "完整明细见下载按钮 · 数据生成于 " +
            _dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out
