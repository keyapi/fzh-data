# -*- coding: utf-8 -*-
"""库存提醒：单条分仓汇总卡片，下载按钮与正文在同一卡片中。"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path

from .inbound import InboundResult
from .scan import ScanResult

_ROBOT_DIR = Path(__file__).resolve().parents[1] / "dingtalk" / "dingtalk_robot"
_OUT_DIR = Path(__file__).resolve().parents[1] / "stock_alert_output"
WEBHOOK_ENV = "DINGTALK_WEBHOOK_STOCK"
SECRET_ENV = "DINGTALK_SECRET_STOCK"
DINGTALK_MAX_BYTES = 20000
CARD_BUDGET_BYTES = 18000


def _robot_path() -> str:
    if not _ROBOT_DIR.is_dir():
        raise FileNotFoundError(f"找不到钉钉推送脚本目录：{_ROBOT_DIR}")
    path = str(_ROBOT_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    return path


def _fmt_num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _clean(value: str) -> str:
    return " ".join(str(value or "").split())


def _check_body(body: str) -> str:
    if len(body.encode("utf-8")) > CARD_BUDGET_BYTES:
        raise ValueError("卡片汇总超过字节上限，请减少单次仓库范围")
    return body


def build_low_stock_messages(result: ScanResult, *, when: _dt.date | None = None,
                             new_count: int = 0) -> list[str]:
    day = when or _dt.date.today()
    threshold = _fmt_num(result.threshold)
    parts = [f"## 通途低库存提醒 · {day.isoformat()}",
             f"**库存概览**  ·  共 **{result.total_low}** 个 SKU 可用库存 < {threshold}",
             f"今日新增：**{new_count}** 个"]
    if not result.total_low:
        parts.append("无 SKU 可用库存低于阈值。")
    for wh in result.warehouses:
        parts.extend([f"### {_clean(wh.warehouse)}",
                      f"低库存：**{wh.count}** 个 SKU",
                      f"今日新增：**{sum(item.is_new for item in wh.low)}** 个",
                      f"在途合计：**{_fmt_num(wh.intransit_total)}** 件"])
        if wh.baseline_missing and wh.count:
            parts.append("> 昨日基线缺失，本仓按全量低库存导出，不代表已确认新增。")
    if result.total_low:
        parts.append("完整 SKU、产品名称和库存明细，请使用本卡片底部下载按钮。")
    parts.append(f"> 口径：可用库存 < {threshold}，排除可用=0且在途=0。")
    return [_check_body("\n\n".join(parts))]


def _inbound_body(result: InboundResult) -> tuple[str, bool]:
    day = result.day.isoformat()
    intro = [f"## 通途采购入库提醒 · {day}",
             f"**入库概览**  ·  共 **{result.total_skus}** 个 SKU · 入库 **{_fmt_num(result.total_qty)}** 件"]
    if not result.total_skus:
        return "\n\n".join(intro + [f"昨日（{day}）无采购入库。"]), False
    summary = list(intro)
    detailed = list(intro)
    for wh in result.warehouses:
        section = [f"### {_clean(wh.warehouse)}",
                   f"入库：**{_fmt_num(wh.total_qty)}** 件 · **{wh.count}** 个 SKU"]
        if not wh.items:
            section.append("昨日无采购入库。")
        summary.extend(section)
        detailed.extend(section)
        for item in wh.items:
            name = _clean(item.name) or _clean(item.sku)
            detailed.append(f"**{name}**\n\nSKU：{_clean(item.sku)}\n\n入库：**{_fmt_num(item.qty)} 件**")
    body = "\n\n".join(detailed)
    if len(body.encode("utf-8")) <= CARD_BUDGET_BYTES:
        return body, False
    summary.append("明细较多，完整产品、SKU和入库数量请点击本卡片底部下载按钮。")
    return _check_body("\n\n".join(summary)), True


def build_inbound_messages(result: InboundResult) -> list[str]:
    return [_inbound_body(result)[0]]


def default_new_out_path(when: _dt.date | None = None) -> Path:
    day = when or _dt.date.today()
    return _OUT_DIR / f"通途新增低库存_{day:%Y%m%d}.xlsx"


def _resolve_creds() -> tuple[str, str]:
    webhook = os.environ.get(WEBHOOK_ENV, "").strip() or os.environ.get("DINGTALK_WEBHOOK", "").strip()
    secret = os.environ.get(SECRET_ENV, "").strip() or os.environ.get("DINGTALK_SECRET", "").strip()
    if not webhook or not secret:
        raise KeyError(
            f"缺少钉钉凭证：请在仓库根 .env 设 {WEBHOOK_ENV}/{SECRET_ENV}，"
            f"或复用默认 DINGTALK_WEBHOOK/DINGTALK_SECRET"
        )
    return webhook, secret


def _notify_one(title: str, body: str, files: list[dict], errors: list[str],
                *, dry_run: bool) -> dict:
    """先上传文件，最后仅发一次；失败也只发一条带说明的汇总。"""
    if dry_run:
        return {"errcode": 1 if errors else 0, "dry_run": True,
                "messages": [body], "files": files, "file_errors": errors}
    webhook, secret = _resolve_creds()
    _robot_path()
    buttons = []
    for item in files:
        try:
            from upload_to_erpnext import upload_file_to_erpnext
            url = upload_file_to_erpnext(Path(item["path"]))
            buttons.append({"title": item["title"], "actionURL": url})
        except Exception as exc:
            errors.append(f"{item['title']}上传失败（{type(exc).__name__}）")
    if errors:
        body += "\n\n> ⚠️ " + "；".join(errors)
    _check_body(body)
    try:
        from send_dingtalk import send_action_card, send_markdown
        if buttons:
            response = send_action_card(title, body, buttons, webhook=webhook, secret=secret)
        else:
            response = send_markdown(body, title=title, webhook=webhook, secret=secret)
    except Exception as exc:
        response = {"errcode": -1, "errmsg": type(exc).__name__}
    ok = response.get("errcode") == 0
    return {"errcode": 0 if ok and not errors else 1, "sent": int(ok), "total": 1,
            "messages": [response], "buttons": buttons, "files": files, "file_errors": errors}


def notify_low_stock(result: ScanResult, *, when: _dt.date | None = None,
                     out_xlsx: str | Path | None = None, dry_run: bool = False) -> dict:
    from .excel import write_low_stock_workbook

    day = when or _dt.date.today()
    new_count = sum(item.is_new for wh in result.warehouses for item in wh.low)
    body = build_low_stock_messages(result, when=day, new_count=new_count)[0]
    new_path = Path(out_xlsx or default_new_out_path(day))
    full_path = (new_path.with_name(new_path.stem + "_全部" + new_path.suffix) if out_xlsx
                 else _OUT_DIR / f"通途低库存明细_{day:%Y%m%d}.xlsx")
    exports = []
    if new_count:
        exports.append((f"下载今日新增（{new_count}）", new_path, True))
    if result.total_low:
        exports.append((f"下载全部低库存（{result.total_low}）", full_path, False))
    files, errors = [], []
    for title, path, newly_only in exports:
        try:
            write_low_stock_workbook(result, path, newly_only=newly_only)
            files.append({"title": title, "path": str(path)})
        except Exception as exc:
            errors.append(f"{title}生成失败（{type(exc).__name__}）")
    return _notify_one(f"通途低库存提醒 · {day.isoformat()}", body, files, errors, dry_run=dry_run)


def notify_inbound(result: InboundResult, *, dry_run: bool = False) -> dict:
    body, _ = _inbound_body(result)
    files, errors = [], []
    if result.total_skus:
        try:
            from .excel import write_inbound_workbook
            path = write_inbound_workbook(result, _OUT_DIR / f"通途采购入库明细_{result.day:%Y%m%d}.xlsx")
            files.append({"title": "下载全部采购入库明细", "path": str(path)})
        except Exception as exc:
            errors.append(f"采购入库明细生成失败（{type(exc).__name__}）")
    return _notify_one(f"通途采购入库提醒 · {result.day.isoformat()}", body, files, errors, dry_run=dry_run)


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
