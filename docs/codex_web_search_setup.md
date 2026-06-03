# Codex Desktop 网页搜索/网络访问配置踩坑记录

> 适用于：Codex Desktop + 自定义模型（DeepSeek 等非 OpenAI 模型）
> 日期：2026-06-03
> 最终方案：审批模式切到"默认权限（手动审批）"

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

Codex Desktop 的 `guardian_approval`（安全审批系统）在"自动审批"模式下调用 `codex-auto-review` 这个专用安全审查模型。**该模型名在 Codex 内部硬编码，无法通过配置更改。**

自定义模型代理只暴露自己的模型名（如 `deepseek-v4-flash`、`deepseek-v4-pro`），不认识 `codex-auto-review` → 全部拒绝。

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

### 方案一：本地代理做模型名映射 ⚠️ 可行但过度复杂

思路：写一个 Python 代理在 57322 端口，拦截 `codex-auto-review` 请求并映射为 `deepseek-v4-flash`，再修改 `config.toml` 的 `base_url`。

结果：可以工作，但需要额外维护代理进程 + 修改 config.toml。

### 方案二：`codex features disable guardian_approval` ⚠️ 可行但过头

```bash
codex features disable guardian_approval
```

可以禁用整个审批系统，但完全跳过了安全层，且需要重启生效。

### 方案三：`model_migrations` 映射 ❌ 无效（已验证）

```toml
[model_migrations]
codex-auto-review = "deepseek-v4-flash"
```

经查阅 Codex 官方 [config-reference](https://developers.openai.com/codex/config-reference) 文档确认：
- `model_migrations` 是**用户确认的模型迁移记录**（当 OpenAI 发布新模型替代旧模型时，通知用户迁移），**不参与模型路由**
- `review_model` 是 `/review` 命令用的，不是审批系统用的
- `auto_review.model` 配置项**不存在**（官方文档没有这个键）
- `codex-auto-review` 模型名在 Codex 内部是**硬编码**的，目前无法通过 config 更改

### 方案四：切换审批模式 ✅ 最终方案

**在 Codex Desktop 左下角，将"自动审批"改为"默认权限（手动审批）"。**

原理：`approvals_reviewer` 从 `auto_review` 切到 `user`，审批弹窗由用户手动确认，不调用 `codex-auto-review` 模型。

- 比禁用 guardian_approval 安全（你仍能看到每次确认）
- 即时生效，无需重启
- 是官方支持的配置方式

## 最终配置

```toml
# config.toml — 无需任何修改，保持原样
model = "deepseek-v4-flash"
model_provider = "custom"

[model_providers.custom]
base_url = "http://127.0.0.1:57321/v1"

[projects.'d:\work\赛狐\cursor']
trust_level = "trusted"

# guardian_approval: 保持启用
# approvals_reviewer = "user" (等同于 UI 左下角选"默认权限")
```

## 对比：Codex vs Claude 的审批逻辑

| 维度 | Claude Desktop | Codex Desktop |
|------|---------------|---------------|
| 搜索审核机制 | WebFetch 预检查 (`claude.ai/api/web/domain_info`) | Guardian Approval (`codex-auto-review` 模型调用) |
| 绕过方式 | `settings.json` 加 `"skipWebFetchPreflight": true` | 审批模式切"手动"（UI）或 `codex features disable guardian_approval`（CLI） |
| 官方支持 | 有隐藏配置项 | `approvals_reviewer` 有 `user` 选项 |
| 手动审批 | 不支持（要么自动要么跳过） | 支持手动审批模式（弹窗确认） |

## 给 Codex 上游的建议

如果想让自定义模型 + 自动审批也能用，可以给 `openai/codex` 提 feature request：

> 支持 `auto_review_model` 配置项，允许用户指定自动审批使用的模型名，或让 `codex-auto-review` fallback 到主模型。

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

## Lessons Learned

1. **`codex-auto-review` 模型名硬编码**：自定义模型提供商无法使用自动审批。
2. **`model_migrations` 不等于模型路由**：它是用户通知系统，不参与实际调用。
3. **手动审批模式是唯一被官方支持的方案**：对于自定义模型用户。
4. **`trust_level = "trusted"` 不影响审批**：它只影响 sandbox 文件权限。
5. **Codex 和 Claude 一样有隐藏配置**：`codex features list` 是发现它们的入口。
6. **官方 config-reference 没有 `auto_review.model`**：确认此功能暂未实现。
# Codex + Codex++ 新手避坑：网页搜索不工作

> **TL;DR**：装完别碰左下角审批模式，默认就能搜索。如果不小心切了"自动审批"→ 切回"默认权限"即可。

---

## 默认状态

Codex Desktop 安装后，审批模式默认为 **"默认权限（手动审批）"**。

此时你可以：
- 让 Agent 上网搜索
- 控制浏览器
- 安装 MCP 插件
- 读写项目文件

每个风险操作会弹窗让你点"允许"——这是预期行为。

## 如果突然不能搜索了

错误信息：
```
This action was rejected due to unacceptable risk.
Reason: Automatic approval review failed: codex-auto-review model not supported
```

99% 是因为**左下角审批模式被切到了"自动审批"**。

### 修复（1 秒）

```
左下角 → 点审批模式 → 选"默认权限"
```

不需要改任何配置文件，不需要重启。

## 原理

| 审批模式 | 左下角显示 | 工作原理 | 自定义模型能用吗 |
|----------|-----------|---------|:---:|
| **默认权限** | 默认权限 | 弹窗让你确认 → 不调模型 | ✅ |
| 自动审批 | 自动审批 | Codex 调 `codex-auto-review` 模型自动审核 | ❌ DeepSeek 没这个模型 |

自动审批是给 OpenAI 官方模型用的，Codex++ 接的 DeepSeek 不支持。

## 提醒方式

建议在公司内部文档 / 新手指南里加一句：

> ⚠️ 使用 Codex++ 时，**不要将左下角审批模式改为"自动审批"**，否则网页搜索、浏览器控制等功能会全部失效。如果不小心切了，切回"默认权限"即可恢复。
