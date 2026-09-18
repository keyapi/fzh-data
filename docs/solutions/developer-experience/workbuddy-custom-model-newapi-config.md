---
okf: v0.1
type: Solution
title: "WorkBuddy 接公司 new-api 自定义模型：useCustomProtocol 必须 false 且 url 带 /v1"
date: 2026-09-03
category: developer-experience
module: docs
problem_type: developer_experience
component: tooling
severity: medium
applies_when:
  - "在 WorkBuddy 里添加公司 new-api 自定义模型（deepseek-v4-flash 等），发消息只回「任务完成」无正文"
  - "同事说 WorkBuddy 接了 api.vilavi.cn 但聊天没下文"
  - "想给非开发同事配置 WorkBuddy 用公司 AI 网关"
tags:
  - workbuddy
  - new-api
  - custom-model
  - deepseek-v4-flash
  - api.vilavi.cn
---

# WorkBuddy 接公司 new-api 自定义模型：useCustomProtocol 必须 false 且 url 带 /v1

## Context

WorkBuddy（腾讯桌面 Agent，底层是 CodeBuddy Code）支持接入第三方模型，配置写在 `%USERPROFILE%\.workbuddy\models.json`——这跟 Codex++ / Codex Desktop 那套（管理工具 → 供应商配置）是**两套独立体系**。

同事用 WorkBuddy 接公司网关 `https://api.vilavi.cn`，发「你好」只显示「任务完成」、之后没下文。日志（`~/.workbuddy/logs/`）里是 `Aborting session ... reason: empty response output from model`，即模型返回了空。根因不在「不支持」，而在 `models.json` 里 `useCustomProtocol` 字段的语义：

- `useCustomProtocol: true` → WorkBuddy 把 `url` **原样透传**，不追加路径 → 打到 `https://api.vilavi.cn/v1`（缺 `/chat/completions`）→ 空响应。
- `useCustomProtocol: false` → 调 `normalizeChatCompletionsUrl(url)` 自动补 `/chat/completions`。

公司 new-api 的正确 OpenAI 兼容端点是 `https://api.vilavi.cn/v1/chat/completions`（`docs/solutions/integration-issues/ivyeaops-assistant-deepseek-v4-model-name.md` 已确认）。所以正确配置是：`url` 带 `/v1`、`useCustomProtocol` 设 `false`。模型名 WorkBuddy 会自动剥掉内部 `custom-local:` 前缀，正确发出 `deepseek-v4-flash`，无需处理。

## Guidance

1. 打开 `%USERPROFILE%\.workbuddy\models.json`（不存在就新建），填入：

```json
[
  {
    "id": "deepseek-v4-flash",
    "name": "deepseek-v4-flash",
    "vendor": "Custom",
    "url": "https://api.vilavi.cn/v1",
    "apiKey": "sk-你的令牌",
    "supportsToolCall": true,
    "supportsImages": false,
    "supportsReasoning": true,
    "useCustomProtocol": false,
    "reasoning": { "supportedEfforts": ["low", "medium", "high"] }
  }
]
```

2. 两个**必对**字段：
   - `url` 必须带 `/v1`（`https://api.vilavi.cn/v1`），不要写成 `https://api.vilavi.cn`（少 `/v1`）。
   - `useCustomProtocol` 必须 `false`。`true` = URL 透传，会打裸根 → 空响应。

3. `apiKey` 用 `sk-` 开头的令牌，在 https://api.vilavi.cn 后台「令牌管理」领取（钉钉扫码登录）。令牌不要贴群、不要进 git。

4. 改完**重启 WorkBuddy**（右下角托盘图标也右键退出再开），发「你好」验证。

5. 模型名用 `deepseek-v4-flash` / `deepseek-v4-pro`（生产渠道可用）；历史名 `deepseek-chat` 在默认组无渠道，会 503。

## Why This Matters

- 现象极具迷惑性：网关在线、Key 有效、模型名也对，但只要 `useCustomProtocol` 错，WorkBuddy 就是「任务完成 + 无正文」，不报任何错误。
- 这是非开发同事最容易踩的坑，且和 Codex++ 的配置方法完全不一样，照搬 Codex++ 教程必然失败。
- 密钥必须留在用户主目录配置里，不能写进仓库文档。

## When to Apply

- 新同事装 WorkBuddy 要接公司 AI 网关
- WorkBuddy 里添加自定义模型后发消息无回复、只显示「任务完成」
- 排查 WorkBuddy 日志出现 `empty response output from model`

## Examples

### 失败现象对照（2026-08-26 本机实测）

| 配置状态 | 实际请求 URL | 结果 |
|---------|-------------|------|
| `useCustomProtocol=true`, `url=.../v1` | `https://api.vilavi.cn/v1`（透传，缺 `/chat/completions`） | 空响应 → 「任务完成」 |
| `useCustomProtocol=false`, `url=...`（少 `/v1`） | `https://api.vilavi.cn/chat/completions` | 收到 ~1507 字节错误页 → 仍空 |
| `useCustomProtocol=false`, `url=.../v1` | `https://api.vilavi.cn/v1/chat/completions` | ✅ 正常回复 |

日志关键行（`~/.workbuddy/logs/2026-08-26/*.log`）：

```text
[ModelProvider] Using custom URL ... https://api.vilavi.cn/ (useCustomProtocol=true, URL passthrough)
[ModelProvider] Aborting session in session-manager, reason: empty response output from model
```

正确时日志应为：

```text
[ModelProvider] Using custom URL ... https://api.vilavi.cn/v1/chat/completions(raw:https://api.vilavi.cn/v1) (custom model, ensured /chat/completions)
[ModelProvider] First raw chunk received ... bytes>0
```

### 兜底

若改完仍空，把 `supportsReasoning` 先设 `false` 复测——排查 `reasoning` 块（`supportedEfforts`）是否让网关对 deepseek-v4 报错。确认不是这个原因后再改回 `true`。

## Related

- [Codex Desktop + Codex++ 安装配置指南](../../codex-desktop-setup-guide.md) — 另一套（Codex 系）的配置方法，勿混淆
- [IvyeaOps AI 问答 503 — deepseek-v4-flash](../integration-issues/ivyeaops-assistant-deepseek-v4-model-name.md) — 公司 new-api 模型名与端点确认
- [Cursor 通途 MCP 注册](cursor-tongtool-mcp-registration.md) — 同类桌面工具配置踩坑
