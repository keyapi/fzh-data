# dingtalk_robot — 钉钉自定义机器人通知

> 给同事的 WorkBuddy（腾讯桌面 AI 助手）配置钉钉定时通知推送。

## 背景

同事在自己电脑上使用 WorkBuddy agent，希望它定时通过钉钉发送通知消息。本模块提供：

1. **操作指引**：如何在钉钉创建自定义机器人（不需要管理员权限）
2. **Python 脚本**：HMAC-SHA256 加签方式调用钉钉 webhook 发送 markdown 消息

## 文件说明

| 文件 | 用途 |
|------|------|
| `钉钉自定义机器人配置指引_给管理员.md` | 给钉钉管理员的操作步骤（备用） |
| `钉钉自定义机器人配置指引_给同事.md` | 给同事的完整操作手册（钉钉建机器人 + WorkBuddy 配置） |
| `send_dingtalk.py` | Python 发送脚本，从 `.env` 读取凭证，加签发消息 |

## 快速开始（同事用）

1. 在钉钉建一个只有自己的群，添加自定义机器人（选「加签」）
2. 把 webhook 地址和 secret 告诉你的 WorkBuddy
3. WorkBuddy 用 `send_dingtalk.py` 脚本定时发消息

详细步骤见 `钉钉自定义机器人配置指引_给同事.md`。

## 技术栈

- Python 3（标准库，零依赖）：`hmac`, `hashlib`, `base64`, `urllib.request`
- 钉钉自定义机器人 webhook API（加签模式）
