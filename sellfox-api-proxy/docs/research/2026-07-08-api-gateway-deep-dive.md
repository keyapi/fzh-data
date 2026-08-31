---
okf: v0.1
type: Research
title: API 网关深度调研 — 架构模式与参考项目
description: 深入分析 NyaProxy 源码、LM-Proxy、proxy.py、litellm 等项目的架构，提取可借鉴的模式
tags: [api-proxy, architecture, plugin-pattern, reference-projects]
sources:
  - https://github.com/Nya-Foundation/NyaProxy
  - https://deepwiki.com/Nya-Foundation/NyaProxy
  - https://github.com/Nayjest/lm-proxy
  - https://github.com/abhinavsingh/proxy.py
  - https://github.com/BerriAI/litellm
  - https://github.com/janbjorge/pipegate
---

# API 网关深度调研

## 一、NyaProxy 源码深度分析

### 代码规模

~3,350 行 Python（`nya/` 包），~10,800 行含测试。关键目录：

```
nya/
├── core/
│   ├── proxy.py      # NyaProxyCore 主编排器 (~110 行)
│   ├── handler.py    # RequestHandler 解析/验证/头注入 (~200 行)
│   ├── request.py    # RequestExecutor httpx 调用 (~170 行)
│   ├── control.py    # TrafficManager 限流+负载均衡 (~280 行)
│   ├── queue.py      # RequestQueue 优先级队列 (~340 行)
│   └── streaming.py  # SSE/流式响应 (~105 行)
├── server/
│   ├── app.py        # FastAPI 应用 (~370 行)
│   └── auth.py       # AuthMiddleware (~200 行)
├── dashboard/
│   ├── api.py        # DashboardAPI FastAPI 子应用 (~110 行)
│   └── routes/       # 仪表板 API 路由
├── services/
│   ├── lb.py         # 负载均衡器 5 种策略 (~140 行)
│   ├── limit.py      # 内存限流器 (~155 行)
│   └── metrics.py    # Prometheus 指标 (~260 行)
├── utils/
│   ├── header.py     # 模板变量替换 (~190 行)
│   └── substitution.py # JMESPath 请求体转换 (~430 行)
└── config/
    └── manager.py    # 配置读取 (~350 行)
```

### 请求转发管线

```
客户端请求
  → generic_proxy_request() (server/app.py)
  → ProxyRequest.from_request() (models.py)
  → NyaProxyCore.handle_request() (core/proxy.py)
    → handler.prepare_request()       # 路由 + URL 构建
    → handler.is_request_allowed()    # 路径/方法 ACL
    → [限流] queue.enqueue_request() + asyncio.wait_for()
    → [不限流] control.select_any_key() + _process_queued_request()
        → handler.process_request_headers()  # 注入 ${{variables}}
        → handler.process_request_body()     # JMESPath 转换
        → [随机延迟]
        → request_executor.execute()         # httpx 调用
```

### 关键发现：Query 参数丢失 Bug

`parse_request()` 用 `urlparse` 取 path，丢弃 query string：

```python
target_url = f"{target_endpoint}{trail_path}"
# trail_path 来自 urlparse path，不含 ?query=string
```

客户端请求 `/api/myapi/users?page=1` → 转发时变成 `/v2/users`（丢失 `?page=1`）。这对赛狐（签名必须包含完整 URL）是致命问题。

### 自定义代码最佳插入点

`nya/core/proxy.py` 的 `_process_queued_request()` 方法：

```python
async def _process_queued_request(self, request):
    # ← [插 OAuth2 Token 缓存] 第 89 行前，检查/刷新 token
    await self.handler.process_request_headers(request)   # 第 91 行
    self.handler.process_request_body(request)              # 第 93 行
    # ← [插 HMAC 签名] 第 100 行前，计算签名 + 注入 query params
    return await self.request_executor.execute(request)     # 第 100 行
```

## 二、LM-Proxy — 最佳架构参考

- **GitHub**: https://github.com/Nayjest/lm-proxy
- **Stars**: 137
- **语言**: Python/FastAPI
- **License**: MIT

### 核心设计模式

**1. RequestContext 可变数据类**（`base_types.py`）:
```python
@dataclass
class RequestContext:
    request: Any
    http_request: Request
    response: Any = None
    group: str = ""
    api_key_id: str = ""
    remote_addr: str = ""
    extra: dict = field(default_factory=dict)
```

**2. before 管线处理器**（`core.py`）:
```python
for handler in env.before:
    result = handler(ctx)
    if inspect.isawaitable(result):
        await result
```

**3. 配置驱动的插件实例化**（`utils.py`）:
```python
def resolve_instance_or_callable(config: dict):
    """{'class': 'module.ClassName', 'param': value} → 实例化的对象"""
    cls = import_class(config["class"])
    kwargs = {k: v for k, v in config.items() if k != "class"}
    return cls(**kwargs)
```

**4. API Key 检查抽象**（`api_key_check/`）:
- `AllowAll` — 接受所有 key
- `check_api_key_in_config` — 配置中查找
- `CheckAPIKeyWithRequest` — 外部 HTTP 验证

### 借鉴要点

- **RequestContext 贯穿管线**：每个处理器接收并修改同一个可变上下文
- **配置驱动的加载机制**：TOML/JSON/YAML 都支持
- **关注点分离**：auth / rate_limit / routing / logging 各自独立文件

## 三、proxy.py — 插件生命周期参考

- **GitHub**: https://github.com/abhinavsingh/proxy.py
- **Stars**: 3,535
- **License**: BSD-3-Clause

### ABC 插件基类

```python
class HttpProxyBasePlugin(ABC):
    def before_upstream_connection(self, request): ...
    def handle_client_request(self, request): ...
    def handle_upstream_chunk(self, chunk): ...
    def on_upstream_connection_close(self): ...
    def on_access_log(self, context): ...
```

### 借鉴要点

- **ABC + MRO 自动发现**：`inspect.getmro()` 分类插件
- **CLI 参数自声明**：`flags.add_argument()` 让插件声明自己的配置
- **生命周期清晰**：before → handle → on_close → log

### 不适合借鉴

- Raw socket 级别（不适合 HTTP 代理）
- 自己实现事件循环（不和 FastAPI 兼容）

## 四、litellm — Key 管理数据模型参考

- **GitHub**: https://github.com/BerriAI/litellm
- **Stars**: 52,899

### Key 管理数据模型（简化后适用）

```python
class APIKey:
    token_hash: str       # SHA-256(key)
    key_name: str         # 可读名称
    user_id: str          # 所属用户
    permissions: list     # 权限列表
    models: list          # 可访问的 provider
    max_budget: float     # 预算上限
    rate_limit: int       # 速率限制
    is_active: bool       # 是否启用
```

### 借鉴要点

- 多级粒度：Key → User → Team → Org
- 用量追踪作为 post-request hook（不侵入请求路径）
- 预算预留机制

### 不适合借鉴

- 16,000 行单片文件（反模式）
- Prisma ORM（过度）
- 全局变量（`global general_settings`）

## 五、自主构建的推荐架构

整合以上分析，推荐文件结构：

```
sellfox-api-proxy/
  main.py              # FastAPI 入口 + lifespan（~50 行）
  config.py            # YAML 配置加载 + Pydantic 校验（~40 行）
  pipeline.py          # 插件阶段调度器 — 借鉴 Kong（~30 行）
  proxy.py             # httpx 上游转发（~50 行）

  plugins/
    base.py            # Plugin 基类 — 借鉴 proxy.py ABC（~30 行）
    key_auth.py        # API Key 验证 — 借鉴 litellm 模型（~50 行）
    rate_limit.py      # 滑动窗口限流 — 借鉴 LM-Proxy（~50 行）
    oauth2_cc.py       # OAuth2 Token 缓存 — 借鉴 Anthropic SDK（~60 行）
    sellfox_sign.py    # 赛狐 HMAC 签名 — 移植已有代码（~40 行）

  db.py                # SQLite 操作 — 借鉴 pipegate（~80 行）
  admin.py             # Key 管理页 — Jinja2 模板（~80 行）
```

**总计**: ~500 行 Python

### 核心设计决策

| 决策 | 理由 |
|------|------|
| 4 阶段模型（非 Kong 8 阶段） | 够用且简单 |
| 声明式 YAML + SQLite 双层 | 避免 Kong DB-less 陷阱 |
| 插件按阶段注册 | Kong 的核心价值，保留 |
| 策略模式（AuthStrategy + SigningStrategy） | 支持多 Provider |
| httpx.AsyncClient 复用 | 连接池，性能 |
