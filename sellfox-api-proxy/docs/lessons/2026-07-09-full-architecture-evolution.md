---
okf: v0.1
type: Lesson
title: sellfox-api-proxy 架构演进全记录 — v0.1.0 → v0.4.2
description: 从零到生产可用的 API 代理网关完整经验教训，涵盖架构选型、部署调试、OIDC 集成、多账号设计、前端交互等
tags: [sellfox, api-proxy, gateway, architecture, lessons, full-record]
timestamp: 2026-07-09
sources:
  - sellfox-api-proxy/AGENT_HANDOFF.md
  - sellfox-api-proxy/docs/research/
  - sellfox-api-proxy/docs/specs/
  - SELLFOX_API/fetch_ad_reports.py
  - SELLFOX_API/docs/lessons/2026-06-25-sellfox-integration-lessons.md
---

# sellfox-api-proxy 架构演进全记录

> 最后更新: 2026-07-09 | 覆盖版本: v0.1.0 → v0.4.3 | 共 17 条核心教训

---

## 1. 架构选型：不要为 2 个 Provider 建插件框架

**决策过程**：初始设计了借鉴 Kong 的 4 阶段管线 + Plugin ABC + Pipeline 调度器。自我批判后发现——只有赛狐一个 Provider，4 个阶段只有 4 个插件，调度逻辑比插件本身还复杂。

**最终方案**：硬编码函数调用链。`key_auth → rate_limit → token_cache → signing → httpx`，一个 30 行 async 函数搞定。等 Provider 到 5 个以上再抽象。

**代码**：`main.py` 中的 `proxy_route()` 函数——直接依次调用，清晰直观。

---

## 2. 声明式配置 ≠ 全放 YAML（避开 Kong DB-less 陷阱）

**问题**：Kong DB-less 模式把静态配置和动态数据全塞进一个 YAML，导致每次加 Key 都要改文件 + reload。

**方案**：双层存储——YAML 管静态（accounts、plugins、rate limits），SQLite 管动态（api_keys 表）。改 Key → REST API 即时生效，改 Provider 配置 → 改 YAML 重启。

**教训**：区分"一年改不了几次"的配置和"每天都要改"的数据。

---

## 3. nginx 后面的相对 URL 是噩梦

**Bug 链**（踩了 4 次）：

| # | 现象 | 根因 | 修复 |
|---|------|------|------|
| 1 | 登录后跳到 new-api | 表单 `action="/admin/login"` 绝对路径 | 改 `<base href="/sellfox/admin/">` + 相对路径 |
| 2 | Cookie 不发到 `/sellfox/admin` | Cookie path 默认 `/admin/`（proxy 视角 ≠ browser 视角） | `path="/"` |
| 3 | POST 创建 Key → 404 | app.js 里 `fetch('/admin/api/keys')` 漏改 | 逐个改成相对 `api/keys` |
| 4 | `/sellfox/admin` 无尾部斜杠 → `./login` → `/sellfox/login` | 浏览器把 `admin` 当文件，`./` 指向父目录 | `<base href="/sellfox/admin/">` 强制目录解析 |

**最终架构**：`<base href="/sellfox/admin/">` 在 HTML head，所有 URL 用相对路径。`cookie path="/"`（不用担心前缀）。

---

## 4. OIDC 回调不要用 303 重定向

**问题**：OIDC 回调设置 cookie 后 `RedirectResponse("/sellfox/admin")` → 浏览器可能不发送刚设的 cookie（某些浏览器 303 响应不处理 Set-Cookie）。

**修复**：OIDC 回调和 Admin Key 登录一样——直接返回 `HTMLResponse(admin.html)` + `set_cookie`。不重定向。

---

## 5. Cookie 值不能含中文

**问题**：钉钉用户名（如"张克勇"）直接存入 session token，Starlette 的 `set_cookie` 调用 `encode("latin-1")` 抛 `UnicodeEncodeError`。

**修复**：`urllib.parse.quote(display_name, safe='')` 编码后存入 token；`unquote()` 解码读出。

---

## 6. HMAC 签名参数 ≠ URL 参数

**问题**：`compute_sign()` 返回了全部 7 个参数（含 `method` 和 `url`），`httpx.post(params=query)` 全发出去了。赛狐只期望 `access_token + client_id + nonce + timestamp + sign` 这 5 个。

**修复**：签名计算用 7 个参数，返回只含 5 个。`method` 和 `url` 仅参与签名，不发送。

---

## 7. Docker 构建时 pip 版本号陷阱

**问题**：`cryptography>=42.0.0` 在 `python:3.12-slim` 上找不到匹配版本。

**修复**：
- 方案 A（最终）：用纯 Python XOR + SHA-256 实现加密，零额外依赖。`_derive_bytes(seed, length)` → XOR → base64。
- 方案 B（备用）：不加版本约束 `cryptography`（无版本号）

**教训**：能用 stdlib 就别加依赖。特别是 Docker 构建环境可能比本地苛刻。

---

## 8. Provider → Account 的重构

**演进**：
- v0.1: `providers.sellfox` — 一个赛狐 = 一个 Provider
- v0.4: `accounts.sellfox-main` — 一个赛狐 App ID/Secret = 一个 Account。多个 Account 可共享同一个 upstream（如 赛狐 主/备账号）

**API Key 绑定**：`api_keys.account` 字段（同时保留 `provider` 字段做迁移兼容）。proxy URL 从 `/v1/sellfox/...` 变为 `/v1/sellfox-main/...`。

**向后兼容**：SQLite migration 自动添加 `account` 列，旧数据 `provider='sellfox'` → `account='sellfox-main'`。

---

## 9. 自动配给（Auto-Provision）

**问题**：不想手动给每个同事创建 Key。

**方案**：`_ensure_user_has_key(db, dingtalk_id, display_name)` — 在 OIDC 回调时检查，如果用户没有活跃 Key 就自动创建一个。Key 名 `auto-{display_name}`，Account 由 `_resolve_account()` 决定。

**`_resolve_account()` 逻辑**：
1. 查 `config.yaml` 中的 `account_overrides`（mapping：`dingtalk_id → account_id`）
2. 无覆盖 → 用 `default_account`

**管理模式**：这是方案 A（最简 YAML mapping）。将来升级到方案 B（规则引擎）时，数据和 API 不变，只改 `_resolve_account()` 内部。

---

## 10. 全局限速按 Account 隔离

**设计**：每个 Account 有独立的 `RateLimiter` 实例（`global_rps` 从 `config.yaml` 读取）。

```python
# main.py lifespan
limiters: dict[str, RateLimiter] = {}
for aid, acc in app_config.accounts.items():
    limiters[aid] = RateLimiter(default_rps=acc.rate_limit.global_rps)
```

**Per-key + global 两级**：`limiter.check(key_id, key.rate_limit_rps)` + `limiter.check(f"global:{account}", None)`。

**超限返回**：429 + `Retry-After` header。不做排队（快速失败）。

---

## 11. Key 加密存储 —— 纯 Python，零依赖

**需求**：用户要求能随时复制已有的 Key（不愿接受"创建时复制一次"的限制）。

**方案**：XOR + SHA-256 加密存储。

```python
def _encrypt(raw: str) -> str:
    data = raw.encode()
    key = _derive_bytes(ADMIN_KEY, len(data))
    return base64.urlsafe_b64encode(
        bytes(a ^ b for a, b in zip(data, key))
    ).decode()
```

- 加密密钥 = ADMIN_API_KEY（SHA-256 派生）
- Key 同时存 `key_hash`（SHA-256，用于验证）和 `key_encrypted`（XOR，用于恢复）
- Reveal API：`POST /api/keys/{id}/reveal` → 解密返回
- 旧 Key（无 `key_encrypted`）→ 无法恢复，提示删除重建

---

## 12. 角色模型：Admin vs User

| 登录方式 | `identity` | `role` | 权限 |
|----------|-----------|--------|------|
| Admin Key | `"admin"` | `admin` | 看全部 Key、管理全部、可选 Account |
| 钉钉 OIDC | `dingtalk_union_id` | `user` | 只看自己的 Key、只用自己的 Account |

**API 级权限**：
- `list_keys` 按 `dingtalk_union_id` 过滤
- `toggle_key` / `delete_key` 检查 `get_key_owner()`
- `create_key` 用户只能给自己创建、admin 可指定归属
- `GET /api/accounts` 用户只看到自己被分配的 Account、admin 看到全部

---

## 13. 前端：Vue 3 CDN + Jinja2 单文件

**选型**：不用 npm/build。`<script src="https://unpkg.com/vue@3/dist/vue.global.prod.js">` CDN 引入，单 HTML 文件搞定所有交互。

**角色感知 UI**：
- `isAdmin → true`：显示"🔑 API Keys" + User 列 + 全部 Key
- `isAdmin → false`：显示"My API Keys" + 无 User 列 + 只看自己的

**状态**：错误框、loading、空态引导、curl 示例框（创建 Key 后显示）。

---

## 14. 部署清单

| 服务 | 位置 | 端口 |
|------|------|------|
| sellfox-api-proxy | `/opt/sellfox-api-proxy` (Docker) | 8400 (内部) |
| nginx | `/etc/nginx/conf.d/new-api.conf` | 443 (public) |
| 数据 | `/data/sellfox-proxy/sellfox-proxy.db` | SQLite |
| 凭证 | docker-compose 环境变量 | 不落地文件 |

**nginx 关键配置**：
```nginx
location /sellfox/admin { proxy_pass http://127.0.0.1:8400/admin; }
location /sellfox/ { proxy_pass http://127.0.0.1:8400/; }
```

**构建部署**：
```bash
cd /opt/sellfox-api-proxy && docker build -t sellfox-api-proxy:latest .
cd /opt/new-api && docker compose up -d sellfox-proxy
```

---

## 15. 测试策略

**Playwright MCP 真浏览器测试**：
- Admin Key 登录 → 创建 Key → 验证 User 列 → 删除
- dev-login 模拟钉钉用户 → 验证 auto-provision → 验证权限隔离
- 代理 API 调用验证（curl 从 VPS 测试）

**dev-login 端点**：仅 `ADMIN_API_KEY` 配置时启用。`GET /admin/dev-login?name=张三&id=dingtalk-xxx` → 直接签发 session cookie。

---

## 16. OIDC 回调不能直接返回 HTML——URL 残留导致刷新失败

**问题**：OIDC 回调 `/admin/oidc-callback?code=...&state=...` 成功后直接返回 `admin.html`。浏览器地址栏残留 OIDC query 参数。用户刷新时重新提交已消费的 `state` → `{"detail":"Invalid state"}`。

**修复**：回调成功后返回极简 HTML 页面，通过 `window.location.replace("/sellfox/admin")` 跳转到干净 URL。Cookie 照常设置（`path="/"`），浏览器地址栏变成 `/sellfox/admin`，刷新安全。

**代码**：`admin.py` 中 `oidc_callback()` 和 `dev_login()` 均改为返回 JS 重定向页面。

**教训**：OIDC 回调的 response 必须改变浏览器 URL（要么 302 重定向，要么 JS redirect）。不能直接返回目标页面。

---

## 17. Key 加密上线后旧 Key 的 `key_encrypted` 为空

**问题**：加密功能 (v0.4.1) 通过 migration 添加 `key_encrypted` 列（`DEFAULT ''`），旧 key 的该列保持空字符串。`_reveal_key()` 中 `not row[0]` 对空字符串返回 True → 返回 None → 前端显示"无法复制此 Key"。

**无法恢复**：旧 key 的原始值在创建时未加密存储，`key_hash`（SHA-256）不可逆，无法回填。

**修复**：删除旧 key，让用户重新 OIDC 登录触发 auto-provision 创建新 key（带加密）。

**教训**：migration 添加加密列时，要么：(1) 在 migration 中加密已有数据（需要原始值），要么 (2) 接受旧数据无法恢复，但要明确区分"未加密"和"解密失败"两种状态。当前 `key_encrypted = ''` 被当作"不可恢复"，语义不精确。

---

## 更新历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-07-07 | v0.1 | 项目启动，架构选型，5 轮方案推演 |
| 2026-07-08 上午 | v0.2 | 首次部署 VPS，浏览器登录修复 |
| 2026-07-08 下午 | v0.3 | 钉钉 OIDC 登录，Provider 重构 |
| 2026-07-09 | v0.4 | Accounts 模型，自动配给，Key 加密，中文 UI |
| 2026-07-09 下午 | v0.4.3 | 离职封号集成 + 冒烟测试 + OIDC 刷新修复 + 旧 Key 加密兼容 |
