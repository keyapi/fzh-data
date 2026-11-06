# -*- coding: utf-8 -*-
"""把低库存汇总推到钉钉（复用原群机器人）。

两种投递（按「低库存 SKU 总数」自动分档，见 `small_threshold`）：
* 数量少 → markdown 正文里**直接列明细**，不发文件；
* 数量多 → 生成**按仓库分 sheet 的 Excel**，上传 ERPNext 后用 ActionCard 发下载卡片。

正文两种都会给每仓「N 个 SKU 可用<5，在途合计 M 件」。
复用 `dingtalk/dingtalk_robot` 的 `send_markdown` / `send_file_card`（不是包，需临时挂 sys.path）。

凭证默认复用原群机器人（DINGTALK_WEBHOOK / DINGTALK_SECRET）；
设了 DINGTALK_WEBHOOK_STOCK / DINGTALK_SECRET_STOCK 则改推专用群。
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path

from .scan import ScanResult

_ROBOT_DIR = Path(__file__).resolve().parents[1] / "dingtalk" / "dingtalk_robot"
_OUT_DIR = Path(__file__).resolve().parents[1] / "stock_alert_output"

WEBHOOK_ENV = "DINGTALK_WEBHOOK_STOCK"
SECRET_ENV = "DINGTALK_SECRET_STOCK"

_EMPTY_TIP = "无 SKU 可用库存低于阈值"
DEFAULT_SMALL_THRESHOLD = 10


def _robot_path() -> str:
    """把 dingtalk_robot 挂上 sys.path（其内部用绝对 import 互相引用）。"""
    if not _ROBOT_DIR.is_dir():
        raise FileNotFoundError(f"找不到钉钉推送脚本目录：{_ROBOT_DIR}")
    path = str(_ROBOT_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    return path


def _fmt_num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def summarize(result: ScanResult, *, when: _dt.date | None = None) -> str:
    """ScanResult → 钉钉 markdown 正文（每仓：低库存 SKU 数 + 在途合计）。

    钉钉自定义机器人的 markdown 不渲染表格，所以用列表。
    """
    day = when or _dt.date.today()
    threshold = _fmt_num(result.threshold)
    lines = [
        f"## 通途低库存提醒 · {day.isoformat()}",
        "",
    ]
    if result.total_low == 0:
        lines.append(f"{_EMPTY_TIP}（< {threshold}）")
    else:
        lines.append(f"共 **{result.total_low}** 个 SKU 可用库存 < {threshold}：")
        lines.append("")
        for w in result.warehouses:
            lines.append(
                f"- {w.warehouse}：**{w.count}** 个（在途合计 {_fmt_num(w.intransit_total)} 件）"
            )
    lines += ["", f"> 口径：可用库存 < {threshold}（已排除「可用=0 且 在途=0」）；括号内为该仓低库存 SKU 的在途数量合计"]
    return "\n".join(lines)


def detail_lines(result: ScanResult) -> str:
    """数量少时直接列明细：每仓一行一条 SKU（可用 / 在途）。"""
    chunks: list[str] = []
    for w in result.warehouses:
        if not w.low:
            continue
        chunks.append(f"\n**{w.warehouse}**")
        for item in w.low:
            chunks.append(f"- {item.sku}：可用 {_fmt_num(item.available)}　在途 {_fmt_num(item.intransit)}")
    return "\n".join(chunks)


def build_body(result: ScanResult, *, when: _dt.date | None = None, small_threshold: int = DEFAULT_SMALL_THRESHOLD) -> tuple[str, bool]:
    """返回 (正文, 是否需要 Excel 附件)。

    低库存总数 > small_threshold 时改用 Excel 附件（正文只留汇总）。
    """
    text = summarize(result, when=when)
    need_file = result.total_low > small_threshold
    if result.total_low and not need_file:
        text += "\n" + detail_lines(result)
    return text, need_file


def default_out_path(when: _dt.date | None = None) -> Path:
    day = when or _dt.date.today()
    return _OUT_DIR / f"通途低库存_{day:%Y%m%d}.xlsx"


def _resolve_creds() -> tuple[str, str]:
    webhook = os.environ.get(WEBHOOK_ENV, "").strip() or os.environ.get("DINGTALK_WEBHOOK", "").strip()
    secret = os.environ.get(SECRET_ENV, "").strip() or os.environ.get("DINGTALK_SECRET", "").strip()
    if not webhook or not secret:
        raise KeyError(
            f"缺少钉钉凭证：请在仓库根 .env 设 {WEBHOOK_ENV}/{SECRET_ENV}，"
            f"或复用默认 DINGTALK_WEBHOOK/DINGTALK_SECRET"
        )
    return webhook, secret


def notify(
    result: ScanResult,
    *,
    out_xlsx: str | Path | None = None,
    small_threshold: int = DEFAULT_SMALL_THRESHOLD,
    title: str | None = None,
    when: _dt.date | None = None,
    dry_run: bool = False,
) -> dict:
    """按数量分档推钉钉；dry_run 只回正文/落盘 Excel、不碰网络。"""
    from .excel import write_low_stock_workbook

    day = when or _dt.date.today()
    title = title or f"通途低库存提醒 · {day.isoformat()}"
    text, need_file = build_body(result, when=when, small_threshold=small_threshold)

    if not need_file:
        if dry_run:
            return {"errcode": 0, "dry_run": True, "mode": "text", "title": title, "text": text}
        webhook, secret = _resolve_creds()
        _robot_path()
        from send_dingtalk import send_markdown

        return send_markdown(text, title=title, webhook=webhook, secret=secret)

    xlsx = write_low_stock_workbook(result, out_xlsx or default_out_path(day))
    if dry_run:
        return {"errcode": 0, "dry_run": True, "mode": "file", "title": title, "text": text, "xlsx": str(xlsx)}
    webhook, secret = _resolve_creds()
    _robot_path()
    from send_file_card import send_file_to_dingtalk

    resp = send_file_to_dingtalk(xlsx, title=title, text=text, webhook=webhook, secret=secret)
    resp["xlsx"] = str(xlsx)
    return resp


def notify_failure(message: str, *, title: str = "通途低库存任务失败") -> dict:
    """无人值守跑挂时的告警；凭证缺失会同样抛出，由调用方兜底打印。"""
    _robot_path()
    from send_dingtalk import send_markdown

    webhook = os.environ.get(WEBHOOK_ENV, "").strip() or os.environ.get("DINGTALK_WEBHOOK", "").strip()
    secret = os.environ.get(SECRET_ENV, "").strip() or os.environ.get("DINGTALK_SECRET", "").strip()
    return send_markdown(f"## {title}\n\n> {message}", title=title, webhook=webhook or None, secret=secret or None)
