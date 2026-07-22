"""
钉钉自定义机器人 — HMAC-SHA256 加签发送 markdown 消息。

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


def send_dingtalk_message(text: str, title: str = "通知") -> dict:
    """通过钉钉自定义机器人 webhook 发送 markdown 消息。

    Args:
        text:  markdown 格式的消息正文
        title: 通知栏显示的标题

    Returns:
        dict: {"errcode": 0, "errmsg": "ok"} 表示成功
    """
    secret = os.environ["DINGTALK_SECRET"]
    webhook = os.environ["DINGTALK_WEBHOOK"]

    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    sign = base64.b64encode(
        hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    ).decode()

    url = f"{webhook}&timestamp={timestamp}&sign={sign}"
    data = json.dumps({
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text},
    }).encode()

    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


if __name__ == "__main__":
    result = send_dingtalk_message(
        text="## dingtalk_robot 测试\n\n> 如果你收到这条消息，说明脚本工作正常。",
        title="连通性测试",
    )
    print(result)
    assert result["errcode"] == 0, f"发送失败: {result}"
