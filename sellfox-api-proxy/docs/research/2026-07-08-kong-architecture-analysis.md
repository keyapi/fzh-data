---
okf: v0.1
type: Research
title: Kong API Gateway 架构分析 — 借鉴与放弃
description: 深度分析 Kong 的架构、DB-less 模式陷阱、插件系统，提取可借鉴的模式，说明为何不直接使用
tags: [kong, api-gateway, architecture, db-less, plugin-system, lua]
sources:
  - https://github.com/Kong/kong
  - https://docs.konghq.com/gateway/latest/
  - https://developer.konghq.com/custom-plugins/
  - https://github.com/LEGO/kong-aws-request-signing
  - https://github.com/abhinavsingh/proxy.py
  - https://github.com/Nayjest/lm-proxy
---

# Kong API Gateway 架构分析

## 一、Kong 规模数据

| 指标 | 数值 |
|------|------|
| Docker 镜像 | 114.9 MB (压缩) |
| 核心 Lua 代码 | ~15 万行 |
| 总代码（含 vendored/测试） | ~1050 万行 |
| 捆绑插件 | 45 个 |
| 推荐内存 | 2 GB |
| 最小内存 | 512 MB |
| 启动时间 | 2-15 秒 |
| 许可证 | Apache 2.0 |
| 数据库 | PostgreSQL（或 DB-less 模式） |
| Stars | ~40,000 |

## 二、Kong 的插件阶段模型（值得借鉴的核心设计）

Kong 将请求生命周期划分为明确的阶段，插件按优先级在每个阶段执行：

```
客户端 → [certificate] → [rewrite] → [access] → 上游
                                                    ↓
客户端 ← [log] ← [body_filter] ← [header_filter] ←──┘
```

| 阶段 | 执行时机 | 典型用途 |
|------|----------|----------|
| `init_worker` | 每个 worker 启动一次 | 定时器、健康检查 |
| `certificate` | SSL 握手 | 动态 TLS 证书 |
| `rewrite` | 路由前（仅全局插件） | 请求规范化 |
| `access` | 路由后，转发前 | **认证、限流、签名**（90% 逻辑） |
| `header_filter` | 收到上游响应头 | 修改响应头 |
| `body_filter` | 每个响应体块 | 修改响应体 |
| `log` | 响应发送后 | 审计、指标 |

**每个阶段所有相关插件按 priority 排序执行**，低 priority 先执行。这个设计确保了关注点分离和可组合性。

## 三、Kong DB-less 模式的陷阱

Kong 可以不装 PostgreSQL 运行（`KONG_DATABASE=off`），但代价：

### 陷阱 1: OAuth2 插件不可用

Kong 的 OAuth2 插件是一个**授权服务器**——签发 token、管理授权码、存储 refresh token——全部需要数据库。DB-less 模式直接不可用。

**但这不是我们需要的**。我们是 OAuth2 **客户端**（从赛狐获取 token），不需要授权服务器。然而，在 DB-less 模式下，Kong 无法运行任何需要持久化状态的插件。

### 陷阱 2: Kong Manager UI 只读

DB-less 模式下，Kong Manager 可以查看配置但不能增删改。添加一个同事的 Key → 改 `kong.yml` → `kong reload`。

### 陷阱 3: 限流仅 local 策略

`rate-limiting` 插件的 `cluster` 和 `redis` 策略需要数据库。DB-less 只能用 `local`（单进程计数器，不做跨节点共享）。

### 陷阱 4: 每次配置变更需要 reload

声明式配置是全部的（原子操作），没有增量更新。`POST /config` 替换整个配置，运行时变更只能通过 `kong reload`。

### 根本原因

Kong DB-less 把所有数据（静态配置 + 动态数据）强行塞进一个 YAML 文件。我们的设计中，这两层是分开的：

| | 存储 | 变更频率 | 变更方式 |
|---|------|----------|----------|
| 静态配置（providers/plugins） | YAML | 极少 | 改文件 + 重启 |
| 动态数据（API Keys） | SQLite | 日常 | REST API 即时生效 |

## 四、Kong 自定义插件开发

### 最小自定义插件骨架

**handler.lua**:
```lua
local MyPlugin = { PRIORITY = 750, VERSION = "1.0.0" }

function MyPlugin:access(conf)
    -- 在这里修改即将发往上游的请求
    kong.service.request.set_query({ sign = "...", timestamp = "..." })
end

return MyPlugin
```

**schema.lua**:
```lua
return {
    name = "my-plugin",
    fields = {
        { config = { type = "record", fields = {
            { secret = { type = "string", required = true } },
        } } },
    },
}
```

### PDK 关键能力

- `kong.service.request.set_query(args)` — 替换上游 query 参数
- `kong.service.request.set_header(name, value)` — 设置上游请求头
- `kong.request.get_path()` — 获取请求路径
- `kong.ctx.shared` — 跨插件阶段共享数据
- 外部 HTTP 调用：`lua-resty-http` 在 `access` 阶段可用

### 赛狐场景需要写的 Lua 代码

约 160 行 Lua（OAuth2 token 获取 + 缓存 + HMAC-SHA256 签名 + query 参数注入）。

## 五、Kong vs 自研 Micro Kong 对比

| 维度 | Kong | 自研 Micro Kong |
|------|------|----------------|
| 部署 | 114MB 镜像 + PostgreSQL 或 DB-less | ~100MB 镜像（Python） + SQLite |
| 自定义代码 | ~160 行 Lua 插件 | ~500 行 Python（全部） |
| 语言匹配 | Lua（团队不会） | Python（团队主力） |
| 插件系统 | 完整（45 个内置） | 精简（3-5 个插件） |
| 阶段模型 | 8 阶段 | 4 阶段（够用） |
| 配置方式 | DB-less 声明式 YAML | YAML（静态）+ SQLite（动态） |
| 后端数据库 | 不需要（我们也不需要） | SQLite（内嵌） |
| 管理 UI | Kong Manager OSS（DB-less 只读） | Jinja2 简易页 |
| 多 Provider | 多 Service/Route 配置 | 多 Provider YAML + 策略插件 |
| 运维 | 需要 Lua 调试技能 | 标准 Python 调试 |
| 适合度 | 过度设计 | 刚好 |

## 六、从 Kong 借鉴什么

### 借鉴的设计

1. **插件阶段模型**：简化为 pre_request → post_auth → pre_upstream → post_response 四阶段
2. **声明式 Provider 配置**：YAML 定义每个上游 API 的认证和签名策略
3. **按优先级排序的插件执行**：`priority` 字段决定同阶段插件执行顺序
4. **全局 + 按 Provider 双层插件**：`default_plugins` + `provider.plugins`
5. **PDK 风格 API**：`ctx.request`, `ctx.response`, `ctx.upstream` 命名空间

### 不借鉴的

1. Lua 技术栈（团队用 Python）
2. 8 个插件阶段（4 个够用）
3. PostgreSQL 依赖
4. 45 个内置插件（不需要）
5. DB-less 模式的数据模型（区分不开静态/动态数据）

## 七、Python 生态中的 Kong 灵感项目

| 项目 | 星数 | Kong 对应 | 借鉴点 |
|------|------|-----------|--------|
| **proxy.py** | 3,535 | 反向代理 + 插件 | ABC 插件基类 + MRO 发现 |
| **LM-Proxy** | 137 | 请求管线 | RequestContext + before 处理器 |
| **Bottle** | ~8,500 | before/after hooks | 最接近 Kong 阶段模型的 Python 框架 |
| **litellm** | 52,899 | Key 管理 | Key 数据模型 + 用量追踪 |
