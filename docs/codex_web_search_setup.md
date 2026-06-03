# Codex Desktop 网页搜索/网络访问配置踩坑记录

> 适用于：Codex Desktop + 自定义模型（DeepSeek 等非 OpenAI 模型）
> 日期：2026-06-03
> 结论：审批模式切到"默认权限（手动审批）"即可，无需改代码或 config。

---

## 问题

Codex Desktop 配置了自定义模型（DeepSeek-v4 经本地代理 `localhost:57321`），但所有需要网络访问的操作（网页搜索、浏览器控制、安装 MCP 服务器等）全部失败。

错误信息：
```
This action was rejected due to unacceptable risk.
Reason: Automatic approval review failed:
The supported API model names are deepseek-v4-pro or deepseek-v4-flash,
but you passed codex-auto-review.
```

## 根因

Codex Desktop 有两套审批机制：

| 机制 | 适用场景 | 触发条件 |
|------|---------|---------|
| **Sandbox** | 文件读写、命令执行 | 操作超出 writable_roots |
| **Guardian Approval (**`guardian_approval`**)** | 网络访问、浏览器、MCP risky 调用 | 自动审批模式 + 风险操作 |

`guardian_approval` 在"自动审批"模式下，会调用 `codex-auto-review` 模型做安全审查。但这个模型名只存在于 OpenAI 官方 API，自定义代理（DeepSeek）不认识 → 全部拒绝。

### 额外根因：三层叠加

这只是第一层。实际有三层问题叠加导致 Web Search 彻底不可用：

```
│ 第 3 层  协议不匹配
│          Codex 用 Responses API (/v1/responses)
│          DeepSeek 只有 Chat Completions API → 需要代理翻译
│          Codex++/bridge 已解决这一层，但不完美
│
├── 第 2 层  tool_choice 参数不支持
│          DeepSeek V4 (deepseek-reasoner) 不支持 tool_choice
│          Web Search 依赖此参数 → API 层面直接报错
│          deepseek-chat (V3) 反而支持
│          Ref: github.com/deepseek-ai/DeepSeek-R1/issues/836
│
└── 第 1 层  codex-auto-review 模型不存在 ← 本文档主要讨论的
           Codex 自动审批调用 codex-auto-review
           第三方 provider 无此模型 → 拒绝全部高风险操作
```

**第 2 层补充说明**：即使审批通过，DeepSeek V4 Pro 收到 `tool_choice` 参数会返回：

```json
{"error": {"message": "deepseek-reasoner does not support this tool_choice"}}
```

这意味着 `deepseek-v4-pro` 下 Web Search **必然失败**，与审批无关。`deepseek-v4-flash` 基于 V3 架构，理论上可用。

### 第 4 个问题：权限标志 bug

Codex++ 内部可能复用了社区已知的 bug：使用 `--approval-mode full-auto`（不存在的 CLI 标志）。正确标志应为 `--dangerously-bypass-approvals-and-sandbox`。

Ref: [ComposioHQ/agent-orchestrator Issue #147](https://github.com/ComposioHQ/agent-orchestrator/issues/147)

### 架构示意

```
Codex Desktop
  ├── 本地模型代理 (localhost:57321)
  │     └── 只支持: deepseek-v4-flash, deepseek-v4-pro
  │
  └── Guardian Approval (自动审批模式)
        └── 调用 codex-auto-review → ❌ 代理不认识 → 拒绝所有操作
```

## 尝试过的方案

### 方案一：本地代理做模型名映射 ❌ 过度复杂

思路：写一个 Python 代理在 57322 端口，拦截 `codex-auto-review` 请求并映射为 `deepseek-v4-flash`，再修改 `config.toml` 的 `base_url`。

结果：代理可以工作，但需要修改 config.toml（有 sandbox 权限问题），且本质上是绕过安全机制。

### 方案二：`codex features disable guardian_approval` ⚠️ 有用但过头

```bash
codex features disable guardian_approval
```

可以禁用整个审批系统，项目设置为 `trusted` 时副作用可接受。但需要重启才能生效，且完全跳过了安全层。

### 方案三：切换审批模式 ✅ 最终方案

**在 Codex Desktop 左下角，将"自动审批"改为"默认权限（手动审批）"。**

- 操作变成弹窗让你手动确认 → 不调用 `codex-auto-review` 模型
- 比完全禁用更安全（你仍能看到每次确认）
- 即时生效，无需重启

## 最终配置

```toml
# config.toml — 无需修改，保持原样
model = "deepseek-v4-flash"
model_provider = "custom"

[model_providers.custom]
base_url = "http://127.0.0.1:57321/v1"
...

[projects.'d:\work\赛狐\cursor']
trust_level = "trusted"  # 已有

# guardian_approval: 保持启用 (true)
# 审批模式: 手动 (UI 左下角切换)
```

## 对比：Codex vs Claude 的审批逻辑

| 维度 | Claude Desktop | Codex Desktop |
|------|---------------|---------------|
| 搜索审核机制 | WebFetch 预检查 (`claude.ai/api/web/domain_info`) | Guardian Approval (`codex-auto-review` 模型调用) |
| 绕过方式 | `settings.json` 加 `"skipWebFetchPreflight": true` | 审批模式切"手动"（UI）或 `codex features disable guardian_approval`（CLI） |
| 共同点 | 都有隐藏配置项需用户发现 | 都有隐藏配置项需用户发现 |
| 手动审批 | 不支持（要么自动要么跳过） | 支持手动审批模式（弹窗确认） |

## 相关命令速查

```bash
# 查看所有功能开关
codex features list

# 搜索相关功能
codex features list | grep -E "guardian|search|web|browser"

# 禁用审批（需要重启生效）
codex features disable guardian_approval

# 恢复
codex features enable guardian_approval
```

## 相关 Issue 追踪

| Issue | 仓库 | 关联 |
|-------|------|------|
| `deepseek-reasoner does not support tool_choice` | [deepseek-ai/DeepSeek-R1 #836](https://github.com/deepseek-ai/DeepSeek-R1/issues/836) | 第 2 层：V4 不支持 tool_choice |
| Wrong permission flag for unattended mode | [ComposioHQ/agent-orchestrator #147](https://github.com/ComposioHQ/agent-orchestrator/issues/147) | 第 4 个问题：权限标志 bug |
| Feature request: third-party model auto-approval | [BigPizzaV3/CodexPlusPlus #564](https://github.com/BigPizzaV3/CodexPlusPlus/issues/564) | Codex++ 改进建议（已提交） |

## Lessons Learned

1. **自定义模型 + 自动审批 = 必死**：`codex-auto-review` 模型名只在 OpenAI 官方 API 存在。
2. **手动审批模式是最佳实践**：既保留了安全层，又绕过了模型依赖。
3. **`trust_level = "trusted"` 不等于跳过审批**：它只影响 sandbox 文件权限，不影响网络审批。
4. **Codex 的配置项和 Claude 一样有隐藏项**，`codex features list` 是发现它们的入口。
5. **DeepSeek V4 Pro ≠ V4 Flash**：Pro 版基于 `deepseek-reasoner`（不支持 tool_choice），Flash 版基于 `deepseek-chat`（V3，支持 tool_choice）。Web Search 需要 tool_choice → Pro 版不可用。
6. **三层问题叠加**：协议（Responses vs Chat Completions）+ 参数（tool_choice）+ 审批（codex-auto-review）。任何一层都可能导致失败，排查时要逐层排除。
