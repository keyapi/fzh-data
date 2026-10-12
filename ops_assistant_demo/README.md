---
type: Reference
title: 科技运营受控办理助手
---

# 科技运营受控办理助手

最新新增终端注册、注册参数、固定IP三功能页，包含模拟数据增删改查、真实模型准备、统一确认、高亮鼠标填写及后台独立读回。当前76项自动化通过、0跳过；实际验收见[渠道接入](docs/bank-operations.md)，下文早期计数为历史记录。

> 本轮已修复身份、工作区、旧接口旁路和HTTP验收差距，并部署经验证的版本。47项自动化全部通过、0项跳过；真实模型和线上联调办理已验证。核验范围及剩余限制见[交接](docs/handoff-2026-10-12.md)与[审计](docs/cursor-audit-2026-10-12.md)。

银行科技子公司内部创新竞赛 POC：有据可查、有权可办、执行可验。业务资料、参数、检测结果和工单全部模拟；自然语言助手调用真实模型。主场景是合作方联调异常处理，柜面测试限额作为答疑场景保留。

演示流程：查询规范和历史经验、读取当前状态、提出具体变更、等待确认、执行受控动作、重新读取核验、形成生产申请。生产参数没有写入口。演示身份不是银行 SSO，检测不是实际外部接口压测。

## 运行

Python 3.10+，运行时使用标准库。在仓库目录执行：

```powershell
Copy-Item .env.example .env
uv run python server.py
```

编辑配置中的 `OPENAI_API_BASE_URL`、`OPENAI_API_KEY` 和 `OPENAI_MODEL`，浏览器打开 `http://127.0.0.1:8765/`。配置也可来自进程环境变量。Key 留在服务端，不进入页面或版本控制。

演示账号：`operator`（经办）、`reader`（只读）、`reviewer`（复核）。共享演示口令为 `demo2026`，它是公开模拟资料，不应作为公网访问门槛。对外部署可设置私有 `DEMO_ACCESS_CODE`，配合 HTTPS 与来源限制；本次演示部署尚未设置私有访问码。这些账号不是银行员工的真实身份认证。

业务数据保存到 SQLite，`DEMO_DB_PATH` 可指定路径。后台按浏览器工作区隔离模拟状态，同一浏览器切换岗位保留工作区；这不是正式多租户隔离证明。数据库、模型配置和运行报告不提交到 Git。

## 演示与验证

- [5 分钟主剧本与答疑场景](docs/demo-script.md)
- [实施规格与验收目标](docs/competition-plan.md)
- [安全边界与质疑解答](docs/security-boundaries.md)
- [公开案例与设计依据](docs/research.md)

```powershell
uv run python -m unittest discover -s tests -v
```

测试结果以本次命令输出为准。安全测试是明确标注的确定性测试，不把它冒充真实模型遭受攻击。真实模型对话单独演练；备用录像与回放也须标注。

## Linux 部署

把代码部署到 `/opt/web-ai-assistant`，运行账户为 `desk`，创建该账户可写的 `data/` 目录；运行配置放在该目录 `.env`，权限 `0600`、属主 `desk`。安装 [systemd unit](deploy/web-ai-assistant.service) 后执行 `systemctl daemon-reload` 和 `systemctl restart web-ai-assistant`，检查状态、日志和 HTTP 响应。

既有部署可能使用不同目录和 unit，先读取私有运维记录，不能盲目套用以上示例。HTTP 白名单仅提供界面资源，配置、源码、数据库和部署文件不可读取。公开 `/v1` 模型转发入口已取消；业务助手要求后台会话，并受进程内预算与并发控制；预算不是供应商硬账单上限。

当前腾讯云地址使用 HTTP，不能防止网络窃听口令和会话。正式演示应在受信网络或 HTTPS 下开展。此前 `.env` 曾可被外部读取，封堵路径不能撤销可能发生的泄露；用户本次明确决定暂不轮换 Key。没有 Git 泄露不能证明没有 HTTP 泄露。
