# -*- coding: utf-8 -*-
"""钉钉投递：低库存逐条明细（按仓分片）+ 今日新增 Excel + 采购入库。

* 低库存：按仓逐条 `• SKU 产品名称：库存N个`；超过单条字节上限时按仓/分片拆成多条。
* Excel：只含「今日新增可用<5」，每仓一 sheet，带产品名称列。
* 采购入库：昨日 `voucher_type=02` 汇总，按仓逐条 `• SKU 产品名称：入库N个`。

复用 `dingtalk/dingtalk_robot` 的 `send_markdown` / `send_file_card`（不是包，需临时挂 sys.path）。
凭证默认复用原群机器人（DINGTALK_WEBHOOK / DINGTALK_SECRET）；
设了 DINGTALK_WEBHOOK_STOCK / DINGTALK_SECRET_STOCK 则改推专用群。
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
import time
from pathlib import Path

from .inbound import InboundResult
from .scan import ScanResult

_ROBOT_DIR = Path(__file__).resolve().parents[1] / "dingtalk" / "dingtalk_robot"
_OUT_DIR = Path(__file__).resolve().parents[1] / "stock_alert_output"

WEBHOOK_ENV = "DINGTALK_WEBHOOK_STOCK"
SECRET_ENV = "DINGTALK_SECRET_STOCK"

# 钉钉自定义机器人 markdown 正文上限 20000 字节；留出标题/汇总/脚注余量。
DINGTALK_MAX_BYTES = 20000
BODY_BUDGET_BYTES = 18000
_EMPTY_TIP = "无 SKU 可用库存低于阈值"
_MAX_NAME_CHARS = 60


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


def _sanitize_name(name: str, sku: str) -> str:
    text = " ".join(str(name or "").split())
    if not text or text == str(sku or ""):
        return ""
    return text[:_MAX_NAME_CHARS]


def low_stock_line(item) -> str:
    name = _sanitize_name(item.name, item.sku)
    head = f"• {item.sku} {name}" if name else f"• {item.sku}"
    return f"{head}：库存{_fmt_num(item.available)}个"


def inbound_line(item) -> str:
    name = _sanitize_name(item.name, item.sku)
    head = f"• {item.sku} {name}" if name else f"• {item.sku}"
    return f"{head}：入库{_fmt_num(item.qty)}个"


def chunk_sections(
    sections: list[tuple[str, list[str]]],
    *,
    budget: int = BODY_BUDGET_BYTES,
) -> list[str]:
    """按 UTF-8 字节贪心装箱；不拆行，同仓跨条时补「（续）」段头。"""
    chunks: list[str] = []
    current: list[str] = []
    used = 0

    def flush() -> None:
        nonlocal current, used
        if current:
            chunks.append("\n".join(current))
            current = []
            used = 0

    for title, lines in sections:
        if not lines:
            continue
        header = f"**{title}**"
        first = True
        for line in lines:
            block = ([header] if first else []) + [line]
            cost = sum(len(x.encode("utf-8")) + 1 for x in block)
            if current and used + cost > budget:
                flush()
                header = f"**{title}**（续）" if not first else f"**{title}**"
                block = [header, line]
                cost = sum(len(x.encode("utf-8")) + 1 for x in block)
            current.extend(block)
            used += cost
            first = False
    flush()
    return chunks


def _assemble(
    sections: list[tuple[str, list[str]]],
    *,
    intro: list[str],
    footer: list[str],
    title: str,
    budget: int = BODY_BUDGET_BYTES,
) -> list[str]:
    # Reserve the full intro/footer and a numbered title even for the smallest chunk.
    overhead = len(("\n".join(intro + footer) + title).encode("utf-8")) + 100
    bodies = chunk_sections(sections, budget=min(budget, DINGTALK_MAX_BYTES - overhead))
    if not bodies:
        bodies = [""]
    if intro:
        bodies[0] = "\n".join(intro + [bodies[0]]) if bodies[0] else "\n".join(intro)
    if footer:
        bodies[-1] = (bodies[-1] + "\n" + "\n".join(footer)) if bodies[-1] else "\n".join(footer)
    total = len(bodies)
    out: list[str] = []
    for index, body in enumerate(bodies, 1):
        head = f"## {title}（第{index}/{total}条）" if total > 1 else f"## {title}"
        message = head + ("\n\n" + body if body else "")
        if len(message.encode("utf-8")) > DINGTALK_MAX_BYTES:
            raise ValueError("单条明细/标题超过钉钉字节上限，无法不拆行发送")
        out.append(message)
    return out


def _short_warehouse(name: str) -> str:
    return name.split("-", 1)[0]


def build_low_stock_messages(
    result: ScanResult,
    *,
    when: _dt.date | None = None,
    new_count: int = 0,
) -> list[str]:
    day = when or _dt.date.today()
    threshold = _fmt_num(result.threshold)
    title = f"通途低库存提醒 · {day.isoformat()}"
    if result.total_low == 0:
        return [f"## {title}\n\n{_EMPTY_TIP}（< {threshold}）。"]

    parts = " / ".join(
        f"{_short_warehouse(w.warehouse)} {w.count}" for w in result.warehouses if w.count
    )
    intro = [f"共 **{result.total_low}** 个 SKU 可用库存 < {threshold}（{parts}）"]
    if new_count:
        intro.append(f"今日新增 **{new_count}** 个，明细见随后 Excel 卡片。")
    for w in result.warehouses:
        if w.baseline_missing and w.count:
            intro.append(f"> {w.warehouse} 昨日基线缺失，本仓按全量低库存计。")

    sections = [
        (f"{w.warehouse}（{w.count} 个）", [low_stock_line(item) for item in w.low])
        for w in result.warehouses
        if w.low
    ]
    footer = [f"> 口径：可用库存 < {threshold}（已排除「可用=0 且 在途=0」）"]
    return _assemble(sections, intro=intro, footer=footer, title=title)


def build_inbound_messages(result: InboundResult) -> list[str]:
    day = result.day.isoformat()
    title = f"通途采购入库提醒 · {day}"
    if result.total_skus == 0:
        return [f"## {title}\n\n昨日（{day}）无采购入库。"]
    intro = [
        f"共 **{result.total_skus}** 个 SKU 入库 **{_fmt_num(result.total_qty)}** 件",
    ]
    sections = [
        (f"{w.warehouse}（{_fmt_num(w.total_qty)} 件）", [inbound_line(item) for item in w.items])
        for w in result.warehouses
        if w.items
    ]
    return _assemble(sections, intro=intro, footer=[], title=title)


def default_new_out_path(when: _dt.date | None = None) -> Path:
    day = when or _dt.date.today()
    return _OUT_DIR / f"通途新增低库存_{day:%Y%m%d}.xlsx"


def _new_count(result: ScanResult) -> int:
    return sum(1 for w in result.warehouses for item in w.low if item.is_new)


def _resolve_creds() -> tuple[str, str]:
    webhook = os.environ.get(WEBHOOK_ENV, "").strip() or os.environ.get("DINGTALK_WEBHOOK", "").strip()
    secret = os.environ.get(SECRET_ENV, "").strip() or os.environ.get("DINGTALK_SECRET", "").strip()
    if not webhook or not secret:
        raise KeyError(
            f"缺少钉钉凭证：请在仓库根 .env 设 {WEBHOOK_ENV}/{SECRET_ENV}，"
            f"或复用默认 DINGTALK_WEBHOOK/DINGTALK_SECRET"
        )
    return webhook, secret


def _send_markdowns(messages: list[str], title: str, webhook: str, secret: str) -> list[dict]:
    from send_dingtalk import send_markdown

    responses: list[dict] = []
    for index, text in enumerate(messages):
        try:
            responses.append(send_markdown(text, title=title, webhook=webhook, secret=secret))
        except Exception as exc:  # noqa: BLE001 - 单条失败不阻断后续
            responses.append({"errcode": -1, "errmsg": f"{type(exc).__name__}: {exc}"})
        if index < len(messages) - 1 and len(messages) > 3:
            time.sleep(1)
    return responses


def notify_low_stock(
    result: ScanResult,
    *,
    when: _dt.date | None = None,
    out_xlsx: str | Path | None = None,
    dry_run: bool = False,
) -> dict:
    """低库存分片消息 + 今日新增 Excel 卡片；dry_run 只回正文/落盘。"""
    from .excel import write_low_stock_workbook

    day = when or _dt.date.today()
    new_count = _new_count(result)
    messages = build_low_stock_messages(result, when=day, new_count=new_count)

    xlsx: Path | None = None
    if dry_run:
        if new_count:
            xlsx = write_low_stock_workbook(result, out_xlsx or default_new_out_path(day), newly_only=True)
        return {
            "errcode": 0,
            "dry_run": True,
            "messages": messages,
            "xlsx": str(xlsx) if xlsx else None,
        }

    webhook, secret = _resolve_creds()
    _robot_path()
    title = f"通途低库存提醒 · {day.isoformat()}"
    responses = _send_markdowns(messages, title, webhook, secret)
    sent = sum(1 for r in responses if r.get("errcode") == 0)

    resp: dict = {
        "errcode": 0 if sent == len(messages) else 1,
        "sent": sent,
        "total": len(messages),
        "messages": responses,
    }
    if new_count:
        try:
            xlsx = write_low_stock_workbook(result, out_xlsx or default_new_out_path(day), newly_only=True)
            from send_file_card import send_file_to_dingtalk

            card = send_file_to_dingtalk(
                xlsx,
                title=f"通途新增低库存 · {day.isoformat()}",
                text=f"今日新增可用<{_fmt_num(result.threshold)} 的产品 **{new_count}** 个，按仓分 sheet。",
                webhook=webhook,
                secret=secret,
            )
        except Exception as exc:  # noqa: BLE001 - 卡片失败不影响已发文本
            card = {"errcode": -1, "errmsg": f"{type(exc).__name__}: {exc}"}
        resp["card"] = card
        resp["xlsx"] = str(xlsx) if xlsx else None
        if card.get("errcode") != 0:
            resp["errcode"] = 1
    return resp


def notify_inbound(result: InboundResult, *, dry_run: bool = False) -> dict:
    messages = build_inbound_messages(result)
    if dry_run:
        return {"errcode": 0, "dry_run": True, "messages": messages}

    webhook, secret = _resolve_creds()
    _robot_path()
    title = f"通途采购入库提醒 · {result.day.isoformat()}"
    responses = _send_markdowns(messages, title, webhook, secret)
    sent = sum(1 for r in responses if r.get("errcode") == 0)
    return {
        "errcode": 0 if sent == len(messages) else 1,
        "sent": sent,
        "total": len(messages),
        "messages": responses,
    }


def _egress_ip(timeout: float = 5.0) -> str | None:
    """尽力取当前公网出口 IP（仅失败告警诊断用；失败返回 None）。"""
    import urllib.request

    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            return urllib.request.urlopen(url, timeout=timeout).read().decode().strip()
        except Exception:  # noqa: BLE001 - 诊断用，失败不影响告警
            continue
    return None


def failure_body(message: str, *, egress_ip: str | None = None) -> str:
    """失败告警正文；524 类错误附带排查提示（524 是未授权，不是限流）。"""
    if "524" not in message and "白名单" not in message:
        return message
    return (
        f"{message}\n\n"
        "524 不是限流（限流是 526），通常是**应用/调用方未授权**"
        "（如「unknown不在白名单列表里」）。请核对通途开放平台：应用是否正常/已发布、"
        "AppSecret 是否被重置、ERP2 库存/基础资料接口权限、以及 MCP 接入白名单。"
        f"\n当前出口 IP：{egress_ip or '未知'}"
    )


def notify_failure(message: str, *, title: str = "通途低库存任务失败") -> dict:
    """无人值守跑挂时的告警；凭证缺失会同样抛出，由调用方兜底打印。"""
    _robot_path()
    from send_dingtalk import send_markdown

    body = failure_body(message, egress_ip=_egress_ip())
    webhook = os.environ.get(WEBHOOK_ENV, "").strip() or os.environ.get("DINGTALK_WEBHOOK", "").strip()
    secret = os.environ.get(SECRET_ENV, "").strip() or os.environ.get("DINGTALK_SECRET", "").strip()
    return send_markdown(f"## {title}\n\n{body}", title=title, webhook=webhook or None, secret=secret or None)


def sync_incomplete_body(detail: str, *, when: _dt.date | None = None) -> str:
    day = when or _dt.date.today()
    return (
        f"## 通途低库存提醒 · {day.isoformat()}\n\n"
        "⚠️ **库存同步未完成**，本次不生成低库存明细（避免把同步失败误报为断货）。\n\n"
        f"> {detail}"
    )


def notify_sync_incomplete(detail: str, *, when: _dt.date | None = None, dry_run: bool = False) -> dict:
    """EN 快照不新鲜时只发「同步未完成」，不发低库存明细。"""
    day = when or _dt.date.today()
    title = f"通途低库存提醒 · {day.isoformat()}"
    text = sync_incomplete_body(detail, when=day)
    if dry_run:
        return {"errcode": 0, "dry_run": True, "mode": "sync_incomplete", "title": title, "text": text}
    webhook, secret = _resolve_creds()
    _robot_path()
    from send_dingtalk import send_markdown

    return send_markdown(text, title=title, webhook=webhook, secret=secret)
