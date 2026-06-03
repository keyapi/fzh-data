# Codex vs Claude：网络搜索架构对比与改进方案

> 写给 Claude 看，帮我分析有无办法让 Codex（Codex++ + DeepSeek）实现开箱即用的网络搜索。

---

## 当前环境

- **Codex Desktop** 通过 **Codex++** 启动，底层模型：DeepSeek V4 Pro
- **Claude Desktop** 同样用 DeepSeek V4 Pro（通过本地代理）
- 两个 Agent 共享同一个项目 `D:\Work\赛狐\Cursor`

---

## 问题

Claude Desktop 的网络搜索（WebFetch）开箱即用，Codex 的一直没法用。

## 架构差异

### Claude Desktop：平台级搜索

```
用户 → Claude Desktop → DeepSeek 模型
                ↓
         "帮我搜一下 XXX"
                ↓
    Claude 平台自己去抓网页
    （内置 HTTP 客户端，不走模型）
                ↓
         返回网页内容给模型 → 模型总结回答
```

- **搜索能力是平台的**，模型只消费结果，不执行网络请求
- 不管底层接什么模型，搜索都能用
- 唯一的问题是中国网络下 `claude.ai` 被墙 → `skipWebFetchPreflight: true` 解决

### Codex Desktop：工具箱模式

```
用户 → Codex Desktop → DeepSeek 模型
                ↓
         "调用 web_search 工具"
                ↓
    Guardian Approval 审核
    （调 codex-auto-review 模型）
                ↓         ↓
          官方模型用户    第三方模型用户
          → 通过审核      → ❌ DeepSeek 代理不认识 codex-auto-review
          → Brave Search  → 拒绝执行
          → 返回结果
```

Codex 把搜索拆成了三层，每层都可能断：

| 层 | 作用 | 第三方模型状态 |
|---|---|---|
| **搜索后端** | 实际执行搜索（Brave Search） | ❌ 需注册 API key |
| **安全审批** | Guardian Approval（codex-auto-review） | ❌ 代理不认识该模型名 |
| **浏览器兜底** | Playwright 操控 Chrome | ❌ Node REPL 没装 playwright |

**绕过方式**：左下角切"默认权限（手动审批）"→ 跳过 codex-auto-review → 但 `web_search` 工具仍因无搜索后端而返回 `unsupported`。

---

## 已尝试方案

| 方案 | 结果 |
|------|------|
| 手动审批模式（跳过审批层） | ✅ 审批通过了，但搜索仍失败 |
| `web_search` 工具直接调用 | `unsupported custom tool call` |
| Playwright 浏览器搜索 | `Module not found: playwright` |
| `gh search issues` | 需 `gh auth login` |

---

## 核心矛盾

**Codex 的 web_search 工具需要一个"搜索提供商"API key（如 Brave Search）。** 对于 OpenAI 官方模型用户，这由 ChatGPT 后端透明提供。对于第三方模型用户，这是一个需要自己填的坑。

Claude 没有这个问题，因为搜索是平台能力，不是工具链。

---

## 请 Claude 帮忙分析

1. **有没有不依赖外部 API key 的方式让 Codex 搜索？** 比如：
   - 写一个 DuckDuckGo 免费搜索 MCP server？
   - 用 Python 的 `requests` + 免费搜索引擎绕过？
   - Codex 的 browser tool 能否配置为无头抓取模式？

2. **Codex++ 社区有没有人解决了这个问题？** 之前搜到 [codex-session-recovery](https://github.com/huajiexiewenfeng/codex-session-recovery)，同作者可能有其他工具或方案。

3. **长远看，是给 Codex 官方提 feature request？** 还是写一个"零配置搜索" MCP plugin 更实际？

4. **目前最务实的 workaround 是什么？**——让 Codex 在需要搜索时用 Python `urllib` 直接发 HTTP 请求抓取？还是放弃 Codex 的搜索，所有搜索需求切到 Claude 做？

---

## 附录：当前 Codex 环境的技术细节

- Codex Desktop 版本：26.601.2237.0
- 通过 Codex++ 启动，模型走本地代理 `localhost:57321`
- 审批模式：默认权限（手动审批）
- `config.toml` 中有 `trust_level = "trusted"`
- `web_search` 工具在 tool list 中存在但返回 `unsupported custom tool call`
