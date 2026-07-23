---
type: log
module: dingtalk_robot
date: 2026-07-23
summary: 开发与变更记录
---

# dingtalk_robot — 变更日志

## 2026-07-23 — v0.2.0 文件附件支持

- 新增 `send_file_card.py` — 上传 ERPNext + 发钉钉 ActionCard，一步完成
- 新增 `upload_to_erpnext.py` — 上传文件到 ERPNext，返回公开下载 URL
- 重构 `send_dingtalk.py` — 拆出 `send_markdown()` / `send_action_card()`，保留旧 `send_dingtalk_message()` 兼容
- 新增 `.env.example` — 环境变量模板
- 更新 `README.md`、`AGENT_HANDOFF.md`、同事指引 — 补充文件附件工作流
- 数据流：Excel → ERPNext /api/method/upload_file → file_url → 钉钉 actionCard

## 2026-07-22 — v0.1.0 初始版本

- 从 `EN_API/out/` 迁移两份操作指引到独立子项目 `dingtalk/dingtalk_robot/`
- 新增 `send_dingtalk.py` — 零依赖 Python 脚本，HMAC-SHA256 加签发钉钉 markdown 消息
- 新增 `README.md`（人读）、`AGENT_HANDOFF.md`（Agent 读）
- 新增 `docs/index.md`、`docs/log.md`（OKF v0.1）
