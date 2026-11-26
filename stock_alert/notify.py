# -*- coding: utf-8 -*-
"""库存提醒：单条分仓汇总卡片，下载按钮与正文在同一卡片中。"""
from __future__ import annotations

import datetime as _dt
import os
import re
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


def _safe_name(value: str) -> str:
    cleaned = "".join(c for c in str(value or "") if c not in '\\/:*?"<>|').strip()
    return cleaned or "warehouse"


def _check_body(body: str) -> str:
    if len(body.encode("utf-8")) > CARD_BUDGET_BYTES:
        raise ValueError("卡片汇总超过字节上限，请减少单次仓库范围")
    return body


def _card_mode() -> str:
    """STOCK_ALERT_CARD_MODE：image（默认，渲染图片卡片）/ text / interactive / auto。"""
    return os.environ.get("STOCK_ALERT_CARD_MODE", "image").strip().lower()


def build_low_stock_messages(result: ScanResult, *, when: _dt.date | None = None,
                             new_count: int = 0) -> list[str]:
    day = when or _dt.date.today()
    title = f"低库存预警 · {day.isoformat()}"
    if new_count == 0:
        return [f"## {title}\n\n今日无新增低库存。"]
    threshold = _fmt_num(result.threshold)
    parts = [f"## {title}", f"今日新增：**{new_count}** 个"]
    for wh in result.warehouses:
        new_for_wh = sum(item.is_new for item in wh.low)
        if not new_for_wh:
            continue
        parts.extend([f"### {_clean(wh.warehouse)}",
                      f"今日新增：**{new_for_wh}** 个",
                      f"在途合计：**{_fmt_num(wh.intransit_total)}** 件"])
        if wh.baseline_missing and wh.count:
            parts.append("> 昨日基线缺失，无法判断今日新增。")
    parts.append(f"> 口径：可用库存 < {threshold}，排除可用=0且在途=0。")
    return [_check_body("\n\n".join(parts))]


def _inbound_body(result: InboundResult) -> tuple[str, bool]:
    day = result.day.isoformat()
    single = result.warehouses[0] if len(result.warehouses) == 1 else None
    title = "## 通途采购入库提醒"
    if single is not None:
        title += f" · {_clean(single.warehouse)}"
    title += f" · {day}" + (f" · {result.label}" if result.label else "")
    if not result.total_skus:
        empty = (f"本次无采购入库（{result.label}）。" if result.label
                 else f"昨日（{day}）无采购入库。")
        return "\n\n".join([title, empty]), False
    summary = [title]
    detailed = [title]
    for wh in result.warehouses:
        section = [f"入库：**{_fmt_num(wh.total_qty)}** 个 · **{wh.count}** 个 SKU"]
        if single is None:
            section.insert(0, f"### {_clean(wh.warehouse)}")
        if not wh.items:
            section.append("本次无采购入库。" if result.label else "昨日无采购入库。")
        summary.extend(section)
        detailed.extend(section)
        for item in wh.items:
            name = _clean(item.name) or _clean(item.sku)
            detailed.append(f"**{name}**\n\nSKU：{_clean(item.sku)}\n\n入库：**{_fmt_num(item.qty)} 个**")
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
                *, dry_run: bool, interactive=None, preview=None, image_path=None) -> dict:
    """先上传文件，最后仅发一次；失败也只发一条带说明的汇总。

    `interactive` 为可选的互动卡片发送器；`image_path` 为可选 PNG 卡片。
    优先级：互动卡片 → 图片卡片 → 文本 ActionCard，逐级回退。
    """
    if dry_run:
        resp = {"errcode": 1 if errors else 0, "dry_run": True,
                "messages": [body], "files": files, "file_errors": errors}
        if image_path:
            resp["card_image"] = str(image_path)
        if preview:
            try:
                resp["card_preview"] = preview()
            except Exception as exc:  # noqa: BLE001 - 预览失败不影响结果
                resp["card_preview_error"] = type(exc).__name__
        return resp
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
    if interactive and buttons and not errors:
        try:
            card_response = interactive(buttons)
            if card_response.get("errcode") == 0:
                return {"errcode": 0, "sent": 1, "total": 1, "mode": "interactive",
                        "messages": [card_response], "buttons": buttons, "files": files,
                        "file_errors": errors}
            print(f"[warn] 互动卡片发送失败，回退下一档：{card_response}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - 回退
            print(f"[warn] 互动卡片发送失败，回退下一档：{type(exc).__name__}: {exc}",
                  file=sys.stderr)
    image_url = None
    if image_path and not errors:
        try:
            from upload_to_erpnext import upload_file_to_erpnext
            image_url = upload_file_to_erpnext(Path(image_path))
        except Exception as exc:  # noqa: BLE001 - 回退文本
            print(f"[warn] 卡片图片上传失败，回退文本：{type(exc).__name__}: {exc}", file=sys.stderr)
    if image_url:
        try:
            from send_dingtalk import send_action_card, send_markdown
            image_body = f"![卡片]({image_url})"
            if buttons:
                response = send_action_card(title, image_body, buttons, webhook=webhook,
                                            secret=secret, single_jump=False)
            else:
                response = send_markdown(image_body, title=title, webhook=webhook, secret=secret)
            if response.get("errcode") == 0:
                return {"errcode": 0, "sent": 1, "total": 1, "mode": "image",
                        "messages": [response], "buttons": buttons, "files": files,
                        "file_errors": errors, "image": str(image_path)}
            print(f"[warn] 图片卡片发送失败，回退文本：{response}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - 回退文本
            print(f"[warn] 图片卡片发送失败，回退文本：{type(exc).__name__}: {exc}", file=sys.stderr)
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


def _interactive_sender(kind: str, result, *, when: _dt.date | None = None, new_count: int = 0):
    """返回 (发送器, 预览器)；未配置或初始化失败返回 (None, None)。"""
    try:
        from . import card as card_mod
        if not card_mod.interactive_available(kind):
            return None, None
        if kind == "low":
            preview_buttons = []
            if new_count:
                preview_buttons.append((f"下载今日新增（{new_count}）", "https://example.invalid/new.xlsx"))
            if result.total_low:
                preview_buttons.append((f"下载全部低库存（{result.total_low}）", "https://example.invalid/all.xlsx"))

            def preview():
                return card_mod.low_stock_params(result, when=when, new_count=new_count,
                                                 buttons=preview_buttons)

            def send(btns):
                return card_mod.send_low_stock(
                    result, when=when, new_count=new_count,
                    buttons=[(b["title"], b["actionURL"]) for b in btns])
        else:
            preview_buttons = []
            if result.total_skus:
                preview_buttons.append(("下载全部采购入库明细", "https://example.invalid/inbound.xlsx"))

            def preview():
                return card_mod.inbound_params(result, buttons=preview_buttons)

            def send(btns):
                return card_mod.send_inbound(
                    result, buttons=[(b["title"], b["actionURL"]) for b in btns])
        return send, preview
    except Exception as exc:  # noqa: BLE001 - 互动卡片只是增强，失败不阻断
        print(f"[warn] 互动卡片初始化失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return None, None


def notify_low_stock(result: ScanResult, *, when: _dt.date | None = None,
                     out_xlsx: str | Path | None = None, dry_run: bool = False) -> dict:
    from .excel import write_low_stock_workbook

    day = when or _dt.date.today()
    new_count = sum(item.is_new for wh in result.warehouses for item in wh.low)
    if new_count == 0:
        # 今日无新增低库存：不推送（也不生成图片/Excel）
        return {"errcode": 0, "skipped": "no_new_low_stock", "sent": 0, "total": 0,
                "messages": [], "files": [], "file_errors": []}
    body = build_low_stock_messages(result, when=day, new_count=new_count)[0]
    new_path = Path(out_xlsx or default_new_out_path(day))
    full_path = (new_path.with_name(new_path.stem + "_全部" + new_path.suffix) if out_xlsx
                 else _OUT_DIR / f"通途低库存明细_{day:%Y%m%d}.xlsx")
    exports = [(f"下载今日新增（{new_count}）", new_path, True)]
    if result.total_low:
        exports.append(("下载全部低库存", full_path, False))
    files, errors = [], []
    for title, path, newly_only in exports:
        try:
            write_low_stock_workbook(result, path, newly_only=newly_only)
            files.append({"title": title, "path": str(path)})
        except Exception as exc:
            errors.append(f"{title}生成失败（{type(exc).__name__}）")
    mode = _card_mode()
    send = preview = None
    if mode in ("interactive", "auto"):
        send, preview = _interactive_sender("low", result, when=day, new_count=new_count)
    image_path = None
    if mode != "text":
        try:
            from .card_image import render_low_stock
            image_path = render_low_stock(result, _OUT_DIR / f"通途低库存卡片_{day:%Y%m%d}.png",
                                          when=day, new_count=new_count)
        except Exception as exc:  # noqa: BLE001 - 图片失败回退文本
            print(f"[warn] 低库存卡片图片生成失败，回退文本：{type(exc).__name__}: {exc}",
                  file=sys.stderr)
    return _notify_one(f"低库存预警 · {day.isoformat()}", body, files, errors,
                       dry_run=dry_run, interactive=send, preview=preview, image_path=image_path)


def notify_inbound(result: InboundResult, *, dry_run: bool = False) -> dict:
    if result.total_skus == 0:
        # 无入库不推送（也不生成图片/Excel）
        return {"errcode": 0, "skipped": "no_inbound", "sent": 0, "total": 0,
                "messages": [], "files": [], "file_errors": []}
    body, _ = _inbound_body(result)
    single = result.warehouses[0] if len(result.warehouses) == 1 else None
    suffix = f"_{_safe_name(single.warehouse)}" if single else ""
    if result.as_of:
        suffix += f"_{result.as_of.replace(':', '')}"
    files, errors = [], []
    if result.total_skus:
        try:
            from .excel import write_inbound_workbook
            path = write_inbound_workbook(
                result, _OUT_DIR / f"通途采购入库明细_{result.day:%Y%m%d}{suffix}.xlsx")
            files.append({"title": "下载全部采购入库明细", "path": str(path)})
        except Exception as exc:
            errors.append(f"采购入库明细生成失败（{type(exc).__name__}）")
    mode = _card_mode()
    send = preview = None
    if mode in ("interactive", "auto"):
        send, preview = _interactive_sender("inbound", result)
    image_path = None
    if mode != "text":
        try:
            from .card_image import render_inbound
            image_path = render_inbound(
                result, _OUT_DIR / f"通途采购入库卡片_{result.day:%Y%m%d}{suffix}.png")
        except Exception as exc:  # noqa: BLE001 - 图片失败回退文本
            print(f"[warn] 采购入库卡片图片生成失败，回退文本：{type(exc).__name__}: {exc}",
                  file=sys.stderr)
    title = "通途采购入库提醒"
    if single is not None:
        title += f" · {single.warehouse}"
    title += f" · {result.day.isoformat()}" + (f" · {result.label}" if result.label else "")
    return _notify_one(title, body, files, errors,
                       dry_run=dry_run, interactive=send, preview=preview, image_path=image_path)


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


def _redact_secrets(text: str) -> str:
    """失败告警里去掉 app_token/sign/timestamp/secret 等敏感查询参数。"""
    for key in ("app_token", "sign", "timestamp", "secret", "access_token"):
        text = re.sub(rf"({key}=)[^&\s]+", r"\1***", text)
    return text


def notify_failure(message: str, *, title: str = "低库存预警任务失败") -> dict:
    """无人值守跑挂时的告警；凭证缺失会同样抛出，由调用方兜底打印。"""
    _robot_path()
    from send_dingtalk import send_markdown

    body = _redact_secrets(failure_body(message, egress_ip=_egress_ip()))
    webhook = os.environ.get(WEBHOOK_ENV, "").strip() or os.environ.get("DINGTALK_WEBHOOK", "").strip()
    secret = os.environ.get(SECRET_ENV, "").strip() or os.environ.get("DINGTALK_SECRET", "").strip()
    return send_markdown(f"## {title}\n\n{body}", title=title, webhook=webhook or None, secret=secret or None)


def sync_incomplete_body(detail: str, *, when: _dt.date | None = None) -> str:
    day = when or _dt.date.today()
    return (
        f"## 低库存预警 · {day.isoformat()}\n\n"
        "⚠️ **库存同步未完成**，本次不生成低库存明细（避免把同步失败误报为断货）。\n\n"
        f"> {detail}"
    )


def notify_sync_incomplete(detail: str, *, when: _dt.date | None = None, dry_run: bool = False) -> dict:
    """EN 快照不新鲜时只发「同步未完成」，不发低库存明细。"""
    day = when or _dt.date.today()
    title = f"低库存预警 · {day.isoformat()}"
    text = sync_incomplete_body(detail, when=day)
    if dry_run:
        return {"errcode": 0, "dry_run": True, "mode": "sync_incomplete", "title": title, "text": text}
    webhook, secret = _resolve_creds()
    _robot_path()
    from send_dingtalk import send_markdown

    return send_markdown(text, title=title, webhook=webhook, secret=secret)
