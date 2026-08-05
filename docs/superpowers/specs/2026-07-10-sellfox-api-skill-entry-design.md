# Sellfox API Skill — 入口路由强化

## Context

`.agents/skills/sellfox-api/SKILL.md` 文档本身很完善（代理 API + 直接 API 双路径，脚本模板，错误处理），但在两个不同的 AI 编程工具（Claude Code、Codex）上测试时，Agent 都跳过了代理路径，直接问用户要 `SELLFOX_APP_ID` / `SELLFOX_APP_SECRET`。

**根因**：skill 入口的 §1 快速路由表是"建议性的"——Agent 看到熟悉的 OAuth2 + HMAC 模式就选了那条路，忽略了"默认走代理"的规则。

**目标**：把 §1 改为 Agent 无法跳过的强制决策树，Step 0 必须先查本地 `.env`。

## 设计

### 文件改动

| 文件 | 操作 | 说明 |
|------|------|------|
| `.agents/skills/sellfox-api/SKILL.md` | 重写 §1 | 强制决策树 |
| `sellfox-api-proxy/AGENT_HANDOFF.md` | 开头加路由块 | Agent 交接时知道普通用户不该来这里 |

### SKILL.md §1 新结构

```
§1 入口路由（Agent 必须按顺序执行）

  Step 0 — 检查本地凭证
    - 读取项目 .env: SELLFOX_API_KEY / SAIFU_KEY
    - 读取项目 .env: SELLFOX_APP_ID + SELLFOX_APP_SECRET
    - 都没有 → Step 1

  Step 1 — 引导用户获取凭证
    优先: https://api.vilavi.cn/sellfox/admin 钉钉登录
    侧注: 开发者如需直连赛狐官方 API，去后台获取 App ID/Secret
    拿到 key 后 → Step 2

  Step 2 — 持久化
    echo "SELLFOX_API_KEY=sk-xxx" >> .env
    后续对话 Step 0 命中，无需再问
```

### 关键设计决策

1. **Step 0 是硬门** — 用检查清单格式（不是建议性表格），Agent 必须先执行
2. **默认推荐代理** — 用户看到的第一条指引是 admin 页面链接，不是 App ID
3. **开发者路径是侧注** — 放在括号里一句话，只有用户主动提才展开
4. **Key 自动持久化** — Agent 拿到 key 后写入 `.env`，一劳永逸
5. **AGENT_HANDOFF.md 只加路由块** — 开发者内容不动

### AGENT_HANDOFF.md 追加路由块

在标题下第一段前插入：

```markdown
> **路由提示**
> - 普通用户想调赛狐 API → 不需要看这个文档，打开 admin 页面钉钉登录拿 Key
> - 接手代理项目的开发者 → 继续往下读
```

## 验证

1. 新对话中 Agent 被 "赛狐API 获取店铺列表" 触发时
2. Agent 第一步应检查 `.env` 是否有 `SELLFOX_API_KEY`
3. 没有时，Agent 应输出 admin 页面链接 + 钉钉登录指引
4. 不应出现 "请提供 SELLFOX_APP_ID" 作为首选方案
