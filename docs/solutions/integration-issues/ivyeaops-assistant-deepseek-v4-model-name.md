---
okf: v0.1
type: Solution
title: IvyeaOps AI 问答 503 — deepseek-chat 无渠道，改用 deepseek-v4-flash
description: 浏览器 E2E 发现 IvyeaOps /assistant 调用 api.vilavi.cn 返回 503；根因是 seed 默认模型名与公司 new-api 渠道不一致。
problem_type: integration-issues
module: ai_access_poc
tags: [ivyeaops, api.vilavi.cn, new-api, deepseek, e2e, assistant]
created: 2026-07-27
updated: 2026-07-27
sources:
  - ai_access_poc/board/scripts/seed_ivyeaops_hub_from_owui.ps1
  - ai_access_poc/board/docs/specs/hands-on-ivyeaops-sellfox.md
  - new-api-deployment/Quick_Start.md
  - ai_access_poc/open_webui/.env.example
---

# IvyeaOps AI 问答 503 — deepseek-chat 无渠道，改用 deepseek-v4-flash

## Context

2026-07-27 在 IvyeaOps-sellfox 完整 SPA（`:8001`）做浏览器端到端实测时，`/assistant` 能发出消息，但上游返回：

```text
openai: Server error '503 Service Unavailable'
for url 'https://api.vilavi.cn/v1/chat/completions'
```

当时 hub 已 seed：

- `assistant_base_url=https://api.vilavi.cn/v1`
- `assistant_api_key` 来自 `ai_access_poc/open_webui/.env` 的 `OPENAI_API_KEY`
- `assistant_model=deepseek-chat`

同日稍早相关 PR 已合入 main（含 #120 赛狐 UX / seed）。本问题是合入后的 E2E 闭环发现。

## Guidance

### 不要把「网关在线」当成「模型可用」

无 Key 探测：

| 请求 | 结果 |
|------|------|
| `GET https://api.vilavi.cn/` | 200 |
| `GET /v1/models`（无 Key） | 401 |

带公司 Key 对比：

| model | HTTP | 含义 |
|-------|------|------|
| `deepseek-v4-flash` | **200** | 生产渠道可用 |
| `deepseek-chat` | **503** | `No available channel for model deepseek-chat under group default` |

### 修复

`seed_ivyeaops_hub_from_owui.ps1` 默认模型改为 `deepseek-v4-flash`，仍可用环境变量覆盖：

```powershell
$env:IVYEA_ASSISTANT_MODEL = "deepseek-v4-pro"  # 可选
powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\seed_ivyeaops_hub_from_owui.ps1
```

重 seed 后浏览器复测：`/assistant` 约 15s 内收到真实回复；服务端日志可见 `POST .../chat/completions HTTP/1.1 200 OK`。

### 阶段性 E2E 结论（同日）

| 模块 | 结果 |
|------|------|
| 赛狐 ERP `/lingxing` | PASS — Proxy Chip、优化引擎 29 候选 |
| AI 问答 `/assistant` | PASS — 改模型后打通 |
| 资讯 `/news` | PASS — 立即刷新约 60 条 |
| 市场 `/market` | PARTIAL — Sorftime Key 未配（销售链接暂不用） |
| 知识库 `/brain` | PARTIAL — IvyeaAgent `:8765` 未起 |

## Why This Matters

- seed 默认模型若与 `new-api` 渠道名漂移，UI「Key 已配置」仍会出现 503，排查成本高。
- 公司网关文档（`new-api-deployment/Quick_Start.md`）以 `deepseek-v4-flash` 为准，历史名 `deepseek-chat` 不可再用。

## When to Apply

- IvyeaOps / Open WebUI / 任意客户端接 `api.vilavi.cn/v1` 报 503
- 新增 seed / 默认模型配置时
- 浏览器 E2E 验收 AI 问答链路时

## Examples

### 冒烟（勿把完整 Key 写入聊天/文档）

```powershell
curl.exe -s -w "`nHTTP:%{http_code}" -X POST https://api.vilavi.cn/v1/chat/completions `
  -H "Authorization: Bearer $env:OPENAI_API_KEY" `
  -H "Content-Type: application/json" `
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"ping"}],"max_tokens":8}'
```

### IvyeaAgent 边界（勿与 IvyeaOps 混淆）

- **IvyeaOps**：运营工作台 SPA（本 PoC 主体验）→ https://github.com/Hector-xue/IvyeaOps  
- **IvyeaAgent**：本地 Agent 服务（知识库/部分 text chain），常见监听 `:8765` → https://github.com/Hector-xue/ivyea-agent  
- 未启动 IvyeaAgent 时，知识库可 fallback；**AI 问答直连 assistant / new-api 不依赖它**。

## Related

- [board AGENT_HANDOFF](../../../ai_access_poc/board/AGENT_HANDOFF.md)
- [hands-on 体验清单](../../../ai_access_poc/board/docs/specs/hands-on-ivyeaops-sellfox.md)
- [钉钉 SSO / new-api](dingtalk-sso-new-api-oidc-bridge.md)
- [统一 AI 接入调研结论](fzh-unified-ai-access-conclusion.md)
