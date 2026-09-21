---
okf: v0.1
type: Log
title: chatgpt 变更日志
description: chatgpt 子项目变更历史
tags: [chatgpt, mcp, log]
---

# 变更日志

## 2026-09-20

- **初始化 OKF bundle**：新建 `chatgpt/` 子项目（README + AGENT_HANDOFF + `docs/`）。
  **起因**：在 ChatGPT 网页版智能体的「新应用」弹窗里加 EN 测试站的 FAC MCP，卡在不知道身份验证怎么选，
  且误入「访问令牌/API 密钥 → 标头方案（持有者/基本/自定义标头）」这条死路。
- **新增**: [reference/connector-requirements.md](reference/connector-requirements.md) — ChatGPT 自定义连接器对 MCP 服务器的**通用**硬性要求：OAuth 2.1+PKCE(S256)、DCR(RFC 7591) 或 CIMD、两处 `.well-known`、不支持 API Key，以及「无本地进程」这条与 Claude Desktop 的根本差异。
- **新增**: [reference/fac-mcp-oauth-connect.md](reference/fac-mcp-oauth-connect.md) — FAC（ensh 测试站）接入实录：表单填写值、服务端实测证据表、报错阶梯。
- **实测（关键证据）**：拿 ChatGPT 真实回调 `https://chatgpt.com/connector_platform_oauth_redirect` 打 FAC 的 DCR 端点，
  得 **`HTTP 201 Created` + `client_id: co3m2l4e7h`** → OAuth 路径在服务端成立。探针记录测完即删（走已连的 `fac` MCP 删 `OAuth Client`）。
- **纠正**: 「Allowed Public Client Origins」**预期无需为 ChatGPT 修改**。读源码 `api/oauth_cors.py` 确认该字段只写
  `frappe.conf.allow_cors` —— **纯 CORS**，只约束浏览器侧 XHR；ChatGPT 是 OpenAI 服务端注册（无 `Origin` 头）+
  浏览器顶层跳转授权（不受 CORS 约束）。FAC 官方 quick start 里「给 MCP Inspector 加 `http://localhost:6274`」
  的语境是浏览器 XHR 客户端，**不要照搬**。
- **纠正**: DCR 对 redirect_uri **只校验 scheme**（非 https 且非 localhost 才拒），**不限域名** ——
  依据 `utils/oauth_compat.py::validate_dynamic_client_metadata`。这解释了为什么 ChatGPT 的回调能直接注册成功。
- **观察**: 测试站 `OAuth Client` 累积 7 条同名 `MCP CLI Proxy`（`localhost:5535`，2026-06-08 → 08-27）→
  **Claude Desktop 每次重新授权都会新建一条记录，旧的不回收**。不紧急，清理时按 `creation` 删旧。
- **未验证**: ChatGPT 侧完整端到端（授权跳转 / token 交换 / `tools/list` / 工具执行）需人工点授权，本地无法代劳。
  各专文已显式标注「尚未验证」，未当作成功。
- **收敛**: 本文档最初写在 `docs/lessons/` 下（旧路径 `docs/lessons/chatgpt-mcp-connector.md`，**该文件已删除、不再是有效引用**），
  随子项目建立**迁移**至此，避免两处说同一件事。`docs/lessons/index.md` 只保留一行指向本子项目。
