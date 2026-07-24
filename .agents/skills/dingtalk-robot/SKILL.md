---
name: dingtalk-robot
description: >
  钉钉自定义机器人通知与文件附件发送。通过 ERPNext 做文件中转，ActionCard 推送下载链接。
  当用户提到"钉钉"、"dingtalk"、"机器人"、"robot"、"通知"、"notify"、
  "发消息到钉钉"、"钉钉群推送"、"发送文件到钉钉"、"ActionCard"、"webhook"等时触发。
  不要用于钉钉 OAuth/OIDC 登录(new-api-dingtalk-oidc)、钉钉 Stream API 企业应用、
  或接收钉钉消息(本模块只负责发送)。
compatibility: >
  需要 requests。从 dingtalk/dingtalk_robot/ 目录运行。
  Python 标准库即可发 markdown 消息，文件附件需 requests + ERPNext API。
metadata:
  module: dingtalk_robot
  scripts: send_dingtalk.py, upload_to_erpnext.py, send_file_card.py
  updated: 2026-07-23
---

# 钉钉自定义机器人 — 通知与文件附件发送

通过钉钉群自定义机器人 webhook 发送文本通知和文件附件（ERPNext 中转）。

## 快速启动

```bash
# 发文本通知
cd dingtalk/dingtalk_robot && python send_dingtalk.py

# 发文件附件 (上传 ERPNext → ActionCard 卡片)
cd dingtalk/dingtalk_robot && python send_file_card.py report.xlsx "标题" "正文"
```

## 两种场景

| 场景 | 脚本 | 消息类型 |
|------|------|---------|
| 纯文本通知 | `send_dingtalk.py` | markdown |
| 文件附件 | `send_file_card.py` | ActionCard (上传 ERPNext → 卡片下载链接) |

## 管道概要

```
Excel → upload_to_erpnext.py → ERPNext file_url
       → send_action_card() → 钉钉群 ActionCard
```

## 环境变量

```
DINGTALK_WEBHOOK  — 钉钉机器人 webhook 地址
DINGTALK_SECRET    — 加签 secret
ERP_API_KEY        — ERPNext API Key (仅文件附件需要)
ERP_API_SECRET     — ERPNext API Secret (仅文件附件需要)
```

## 硬约束

- 自定义机器人只支持 text / markdown / link / actionCard / feedCard，不支持直接发文件
- 文件附件通过 ERPNext 公开上传中转，ActionCard 带下载链接
- 每分钟最多 20 条消息
- Webhook 和 Secret 必须走 `.env`，不能硬编码或提交 git
- ERPNext API Key 是用户级别的，不是企业应用凭证，泄露影响面小
- ActionCard 按钮链接必须可公网访问（ERPNext 生产环境满足）

## 安全

- 两个凭证独立：DINGTALK_* 只管发消息，ERP_* 只管上传文件
- 即使 webhook 泄露，攻击者只能发消息到那个群，不影响企业系统
- 如果某天同事不再用，在钉钉群设置里删掉机器人即刻失

## 参考

- [给人看的 README](../../dingtalk/dingtalk_robot/README.md)
- [Agent 详细参考](../../dingtalk/dingtalk_robot/AGENT_HANDOFF.md)
- [同事操作手册](../../dingtalk/dingtalk_robot/钉钉自定义机器人配置指引_给同事.md)
