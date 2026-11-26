# -*- coding: utf-8 -*-
"""钉钉互动卡片（createAndDeliver）发送层。

自定义机器人 Webhook 的 ActionCard 只能发 Markdown，无法做居中标题、蓝底头部、
统计框和通栏按钮。要做到 Codex 预览图的效果，需要：

1. 企业内部应用（Client ID / Secret）
2. 应用机器人安装到目标群，拿到 robotCode 与 openConversationId
3. 在钉钉卡片平台创建并**发布**两个模板（低库存 / 采购入库）
4. 把下面的配置写入根 `.env`（已 gitignore）：

    DINGTALK_CLIENT_ID / DINGTALK_CLIENT_SECRET
    DINGTALK_ROBOT_CODE                  # 默认 = Client ID
    DINGTALK_OPEN_CONVERSATION_ID        # 目标群的 openConversationId
    DINGTALK_OPERATOR_ID                 # 可选，卡片创建人 userId
    DINGTALK_LOW_STOCK_TEMPLATE_ID
    DINGTALK_INBOUND_TEMPLATE_ID

模板变量见 `docs/reference/interactive-card.md`。配置不全时调用方回退到现有
ActionCard，不会阻断每日提醒。
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import urllib.error
import urllib.request
import uuid

API = "https://api.dingtalk.com"
TOKEN_PATH = "/v1.0/oauth2/accessToken"
CARD_PATH = "/v1.0/card/instances/createAndDeliver"

_KIND_ENV = {
    "low": "DINGTALK_LOW_STOCK_TEMPLATE_ID",
    "inbound": "DINGTALK_INBOUND_TEMPLATE_ID",
}


class InteractiveCardError(RuntimeError):
    """互动卡片配置/发送失败。调用方应回退到 ActionCard。"""


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def config(kind: str) -> dict | None:
    """读取指定卡片类型的配置；缺任何必填项返回 None（触发回退）。"""
    template_env = _KIND_ENV.get(kind)
    if not template_env:
        raise ValueError(f"未知卡片类型：{kind}")
    client_id = _env("DINGTALK_CLIENT_ID", "DINGTALK_APP_KEY")
    client_secret = _env("DINGTALK_CLIENT_SECRET", "DINGTALK_APP_SECRET")
    robot_code = _env("DINGTALK_ROBOT_CODE", default=client_id)
    conversation_id = _env("DINGTALK_OPEN_CONVERSATION_ID")
    template_id = _env(template_env)
    if not (client_id and client_secret and robot_code and conversation_id and template_id):
        return None
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "robot_code": robot_code,
        "conversation_id": conversation_id,
        "template_id": template_id,
        "operator_id": _env("DINGTALK_OPERATOR_ID"),
    }


def interactive_available(kind: str) -> bool:
    try:
        return config(kind) is not None
    except ValueError:
        return False


def _http_json(method: str, url: str, *, body: dict | None = None, token: str | None = None,
               timeout: int = 30) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["x-acs-dingtalk-access-token"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload


def get_access_token(cfg: dict) -> str:
    code, payload = _http_json(
        "POST",
        API + TOKEN_PATH,
        body={"appKey": cfg["client_id"], "appSecret": cfg["client_secret"]},
    )
    token = payload.get("accessToken") if isinstance(payload, dict) else None
    if code != 200 or not token:
        raise InteractiveCardError(f"accessToken 失败 http={code} body={payload}")
    return token


def send_card(cfg: dict, card_param_map: dict, *, out_track_id: str | None = None,
              token: str | None = None) -> dict:
    token = token or get_access_token(cfg)
    body = {
        "cardTemplateId": cfg["template_id"],
        "outTrackId": out_track_id or f"stock_alert_{uuid.uuid4().hex}",
        "openSpaceId": cfg["conversation_id"],
        "cardData": {"cardParamMap": {str(k): str(v) for k, v in card_param_map.items()}},
        "imGroupOpenSpaceModel": {"supportForward": True},
        "imGroupOpenDeliverModel": {"robotCode": cfg["robot_code"]},
    }
    if cfg.get("operator_id"):
        body["userId"] = cfg["operator_id"]
    code, payload = _http_json("POST", API + CARD_PATH, body=body, token=token)
    if code != 200 or not isinstance(payload, dict) or payload.get("success") is False:
        raise InteractiveCardError(f"createAndDeliver 失败 http={code} body={payload}")
    return {"errcode": 0, "mode": "interactive", "http": code, "response": payload}


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _buttons(params: dict, buttons, prefix: str) -> dict:
    for index, (title, url) in enumerate(list(buttons)[:2], 1):
        params[f"{prefix}{index}Title"] = str(title or "")
        params[f"{prefix}{index}Url"] = str(url or "")
    return params


def low_stock_params(result, *, when: _dt.date | None = None, new_count: int = 0,
                     buttons=(), footnote: str = "") -> dict:
    """低库存卡片模板变量（全部字符串）。"""
    day = when or _dt.date.today()
    lines = []
    for wh in result.warehouses:
        section = [f"### {wh.warehouse}"]
        new_for_wh = sum(item.is_new for item in wh.low)
        if not new_for_wh:
            continue
        section.append(
            f"今日新增 **{new_for_wh}** 个 · 在途 **{_fmt(wh.intransit_total)}** 件"
        )
        if wh.baseline_missing and wh.count:
            section.append("> 昨日基线缺失，本仓按全量低库存导出。")
        lines.append("\n\n".join(section))
    params = {
        "title": "低库存预警",
        "subtitle": day.isoformat(),
        "overview": f"今日新增 **{new_count}** 个",
        "body": "\n\n".join(lines),
        "footnote": footnote or f"口径：可用库存 < {_fmt(result.threshold)}，排除可用=0且在途=0。",
    }
    return _buttons(params, buttons, "btn")


def inbound_params(result, *, buttons=(), footnote: str = "") -> dict:
    """采购入库卡片模板变量（全部字符串）。"""
    lines = []
    for wh in result.warehouses:
        section = [f"### {wh.warehouse}", f"入库：**{_fmt(wh.total_qty)}** 个 · **{wh.count}** 个 SKU"]
        if not wh.items:
            section.append("昨日无采购入库。")
        for item in wh.items:
            name = item.name or item.sku
            section.append(f"**{name}**  ·  **{_fmt(item.qty)}** 个\n\nSKU：{item.sku}")
        lines.append("\n\n".join(section))
    params = {
        "title": "通途采购入库提醒",
        "subtitle": f"{result.day.isoformat()} · 昨日入库",
        "overview": f"共 **{result.total_skus}** 个 SKU · 入库 **{_fmt(result.total_qty)}** 个",
        "body": "\n\n".join(lines),
        "footnote": footnote or "统计口径：采购单（02）正向入库事件，不代表采购单全部到货。",
    }
    return _buttons(params, buttons, "btn")


def send_low_stock(result, *, when: _dt.date | None = None, new_count: int = 0,
                   buttons=(), footnote: str = "") -> dict:
    cfg = config("low")
    if not cfg:
        raise InteractiveCardError("低库存互动卡片未配置")
    return send_card(cfg, low_stock_params(result, when=when, new_count=new_count,
                                           buttons=buttons, footnote=footnote))


def send_inbound(result, *, buttons=(), footnote: str = "") -> dict:
    cfg = config("inbound")
    if not cfg:
        raise InteractiveCardError("采购入库互动卡片未配置")
    return send_card(cfg, inbound_params(result, buttons=buttons, footnote=footnote))
