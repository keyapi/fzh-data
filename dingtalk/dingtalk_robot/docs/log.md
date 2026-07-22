---
type: log
module: dingtalk_robot
date: 2026-07-22
summary: 开发与变更记录
---

# dingtalk_robot — 变更日志

## 2026-07-22

- 初始版本 v0.1.0
- 从 `EN_API/out/` 迁移两份操作指引到独立子项目
- 新增 `send_dingtalk.py` — 零依赖 Python 脚本，HMAC-SHA256 加签发钉钉 markdown 消息
- 新增 `README.md`（人读）、`AGENT_HANDOFF.md`（Agent 读）
- 新增 `docs/index.md`、`docs/log.md`（OKF v0.1）

### 文件清单

- `send_dingtalk.py` — 发送脚本
- `README.md` — 模块说明
- `AGENT_HANDOFF.md` — Agent 交接文档
- `钉钉自定义机器人配置指引_给管理员.md` — 管理员操作步骤
- `钉钉自定义机器人配置指引_给同事.md` — 同事操作手册（含 WorkBuddy 提示词）
