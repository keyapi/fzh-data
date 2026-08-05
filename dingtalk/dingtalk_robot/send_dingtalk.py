"""
钉钉自定义机器人 — 消息发送工具。

支持消息类型:
  - markdown    (send_markdown)
  - actionCard  (send_action_card) — 适合带文件下载链接

用法:
    cd dingtalk/dingtalk_robot && python send_dingtalk.py

环境变量:
    DINGTALK_WEBHOOK — 钉钉机器人 webhook 地址
    DINGTALK_SECRET   — 加签 secret
"""

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.request


def _sign_request(secret: str) -> tuple[str, str]:
    """生成时间戳和签名。"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    sign = base64.b64encode(
        hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    return timestamp, sign


def _post(url: str, data: dict) -> dict:
    """发送 POST 请求到钉钉 webhook。"""
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def _signed_url() -> str:
    """构造带签名的完整 webhook URL。"""
    secret = os.environ["DINGTALK_SECRET"]
    webhook = os.environ["DINGTALK_WEBHOOK"]
    timestamp, sign = _sign_request(secret)
    return f"{webhook}&timestamp={timestamp}&sign={sign}"


def send_markdown(text: str, title: str = "通知") -> dict:
    """发送 markdown 消息。"""
    return _post(_signed_url(), {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text},
    })


def send_action_card(title: str, text: str, buttons: list[dict]) -> dict:
    """发送 ActionCard 卡片消息（支持下载按钮）。

    Args:
        title:  卡片标题
        text:   markdown 格式的卡片正文
        buttons: 按钮列表，每个按钮 {"title": "下载", "actionURL": "https://..."}

    若只有一个按钮，使用 singleTitle/singleURL 模式（更简洁）。
    """
    card = {
        "title": title,
        "text": text,
        "btnOrientation": "1",  # 横向排列
    }
    if len(buttons) == 1:
        card["singleTitle"] = buttons[0]["title"]
        card["singleURL"] = buttons[0]["actionURL"]
    else:
        card["btns"] = buttons

    return _post(_signed_url(), {"msgtype": "actionCard", "actionCard": card})


def send_dingtalk_message(text: str, title: str = "通知") -> dict:
    """兼容旧接口：发送 markdown 消息。"""
    return send_markdown(text, title)


# ── 测试入口 ────────────────────────────────────────────
if __name__ == "__main__":
    result = send_markdown(
        text="## dingtalk_robot 测试\n\n> 如果你收到这条消息，说明脚本工作正常。",
        title="连通性测试",
    )
    print(result)
    assert result["errcode"] == 0, f"发送失败: {result}"
