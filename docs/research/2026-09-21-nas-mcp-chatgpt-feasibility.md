---
type: Research
title: 群晖 NAS 接入 ChatGPT 的可行性与部署位置 — 部署在 VPS 而非 NAS（NAS 公网只开非标端口 11024）
description: 实测确认 NAS 公网 443 不通、11024 通（上海+美国两处外部主机一致），故 ChatGPT 接不了 NAS 本机；推荐部署在 api.vilavi.cn（VPS，nginx+Docker 已有模式），由它回调 NAS 的 DSM API。含复用件清单、工具设计与安全约束
tags: [nas, synology, mcp, chatgpt, deployment, research]
timestamp: 2026-09-21
---

# 群晖 NAS 接入 ChatGPT：可行性与部署位置（2026-09-21）

## 一句话结论

**能接，但不要部署在 NAS 上 —— 部署在 VPS（`api.vilavi.cn`）。**

理由不是「NAS 性能不够」，而是一条硬约束：**ChatGPT 是 OpenAI 的服务端来连你的端点，必须公网可达**。
而 NAS 对外**只开了非标准端口 11024**，标准 443 不通 —— 这既接不了 ChatGPT，也**不该**为了接它而把 DSM 直接怼到公网。

---

## 一、定论：NAS 的公网可达性（实测，两处外部主机）

我在**北京办公室内网**做初步探测时，`https://nas.vilavi.cn/` 返回 **HTTP 200** —— 但那是个**假阳性**：
办公室 OpenWrt 的 dnsmasq 把该域名**劫持到内网 `192.168.100.242`**（见 `NAS_API/docs/reference/nas-multi-domain-access.md`），
我测到的其实是内网路径。

改用**两处独立的外部主机**复测（`ssh sh-erpnext-test` = 上海 VPS / `us-ubuntu-proxy-pub` = 美国 VPS）：

| 目标 | 上海 VPS | 美国 VPS | 说明 |
|---|---|---|---|
| `nas.vilavi.cn:443` | **失败** | **失败** | 公网不通 |
| `nas.vilavi.cn:11024` | ✅ HTTP 200 | ✅ HTTP 200 | 公网唯一入口 |
| `api.vilavi.cn:443`（对照） | ✅ HTTP 200 | ✅ HTTP 200 | VPS 正常 |

公网 DNS：`nas.vilavi.cn` → `123.117.232.176`（办公网出口 IP，DDNS）。

**两处外部主机结论一致，且与仓库既有记载吻合** → 之前的记载是对的，我的本地探测被 DNS 劫持骗了。
（教训记一笔：**在办公网内测自家公网可达性 = 无效**，必须换外部视角。）

---

## 二、为什么这决定了部署位置

| 方案 | MCP 跑在哪 | ChatGPT 能否连 | 公网暴露 | 结论 |
|---|---|---|---|---|
| **A** | 上海 VPS 容器，回调 NAS | ✅ 走 `api.vilavi.cn:443` | NAS 完全不动 | ✅ **推荐** |
| B | NAS Container Manager | ❌ 只有 11024 非标端口 | 需新增 Cloudflare Tunnel / Tailscale Funnel 才能拿到 443 | 备选，要新建基础设施 |
| C | 本机 stdio（不联网） | ➖ 不适用 | 无 | 若只需局域网 Agent，最安全 |

**关键顺带验证**：上面那次外部测试同时证明了 —— **上海 VPS 能访问 NAS 的 `11024`**（HTTP 200）。
即方案 A 的链路 **VPS → NAS 是通的**，不需要额外打通。

---

## 三、方案 A 的落地设计

### 3.1 链路

```
ChatGPT（OpenAI 服务端）
   │  HTTPS 443 —— MCP streamable-http
   ▼
api.vilavi.cn（上海 VPS 8.133.254.66 · nginx）
   │  nginx 路径块  /nas/*  →  127.0.0.1:8402
   ▼
nas-mcp 容器（FastMCP）
   │  HTTPS nas.vilavi.cn:11024  ← 已验证此 VPS 可达
   ▼
FZH-NAS（DSM FileStation API）
```

### 3.2 直接复用现有件（不引第三方）

| 复用 | 位置 | 说明 |
|---|---|---|
| **NAS 客户端** | `NAS_API/synology.py`（`SynologyNAS` + `get_nas()`） | 认证、`NAS_ROOT_FOLDER` 范围限制现成 |
| **MCP 骨架** | `sellfox_shipping/mcp_tools.py` | `FastMCP(name=…)` + `@mcp.tool` + `init_mcp()` 共享状态；`main.py` 里 `mount_mcp(mcp.asgi_app())` |
| **部署模式** | `sellfox-api-proxy`（8400）/ `new-api`（3000） | Docker 服务 + VPS nginx 路径块，`docker compose up -d --no-deps <svc>` |

> **不要引第三方群晖 MCP**（网上有 87 工具/15 模块那种）。它们默认权限面覆盖 Docker、备份、Photos、VMM —— 而我们只需要**一个共享文件夹的读写**。复用 `NAS_API` 能带上已测过的范围限制。

### 3.3 工具设计（默认只读）

`NAS_API/synology.py` 的方法天然可分成两侧：

**只读（先只暴露这些）**

| 现有方法 | 建议的 MCP 工具 |
|---|---|
| `available()` | `nas_health` —— 连通性自检 |
| `get_file_list(...)` | `nas_list_folder` —— 列目录 |
| `get_thumbnail(...)` | `nas_thumbnail` |
| `download_file(path)` | `nas_read_file`（注意：需截断/限额，避免把大文件灌进上下文） |
| `folder_exists(...)` | `nas_folder_exists` |

**写（默认不暴露）**

| 现有方法 | 风险 |
|---|---|
| `create_folder` / `create_subfolders` | 中（可恢复） |
| **`delete_folder`** | **高 —— 破坏性，建议永不暴露** |

### 3.4 鉴权（一个尚未解决的共同问题）

**ChatGPT → 我们的 MCP 用什么鉴权，目前还没验证过**：

- ChatGPT 的自定义连接器 UI 提供「访问令牌/API 密钥 → 标头方案」，**但只能填一个自定义头**
- 赛狐官方 MCP 正好用一个头（`X-MCP-Key`），可以一试
- FAC 走的是 OAuth 2.1 + PKCE + DCR（已在 `ensh` 上实测通）

→ **建议**：`nas-mcp` 采用与赛狐一致的**单头静态密钥**（我们自己的 `X-NAS-MCP-Key`），
**先验证「ChatGPT 自定义标头」这条路是否可行** —— 这个结论对赛狐和 NAS **是同一个**，验一次两处都受益。

### 3.5 安全约束（必须做）

1. **专用 DSM 账号 + 只读权限**，只授权目标共享文件夹
   - ⚠️ **DSM API 不支持 2FA** → 必须用**应用专用密码**（`NAS_API` 现有实现也依赖这点）
2. **DSM Auto Block 白名单**加入 VPS 出口 IP，否则几次失败就封
3. **证书校验要打开**：`NAS_API` 现用 `cert_verify=False`，那是为**局域网**设计的；
   经公网调 `nas.vilavi.cn:11024` 应**校验 LE 证书**（该域名有 LE 证书）
4. **范围锁死**在 `NAS_ROOT_FOLDER`，工具不接受超出范围的路径
5. 容器侧设**超时 / 单文件大小上限**，防大文件灌爆上下文

---

## 四、未决

| # | 问题 | 怎么解 |
|---|---|---|
| 1 | **ChatGPT 能否用「自定义标头」鉴权** | 建一个最小 MCP 端点试一次。**这个结论赛狐也用得上** |
| 2 | VPS 出口 IP 到底是什么 | 仓库里出现过 `82.156.238.248`（赛狐白名单）与 `8.133.254.66`（api.vilavi.cn）。要加 DSM 白名单前须确认 |
| 3 | 要不要做、先给谁用 | 若只给局域网 Agent，方案 C 最省事，不必上线任何公网服务 |
| 4 | 是否需要「搜索文件」能力 | `NAS_API` 目前没有，要新写（Synology FileStation 有 Search API） |

---

## 五、建议的推进顺序

1. **先验第 1 项**（ChatGPT 自定义标头）—— 成本最低，且结论对赛狐复用
2. 确认 VPS 出口 IP
3. 建 DSM 专用只读账号 + 应用专用密码
4. 写 `nas_mcp/`（复用 `NAS_API` + FastMCP 骨架），**先只上只读工具**
5. 部署到 VPS，加 nginx 路径块，接入 ChatGPT
6. **`delete_folder` 永不暴露**；写工具若要开，单独评估

---

## 参考 URL / 仓库内

**实测**（2026-09-21）

- 外部视角：`ssh sh-erpnext-test`（上海 VPS）、`ssh us-ubuntu-proxy-pub`（美国 VPS）各 curl 一次
- 公网 DNS：Cloudflare DoH 查 `nas.vilavi.cn` / `api.vilavi.cn`

**仓库内**

- `NAS_API/synology.py` —— DSM FileStation 客户端（`SynologyNAS`，读/写方法边界见 §3.3）
- `NAS_API/docs/reference/nas-multi-domain-access.md` —— 四个公网域名、QuickConnect、`11024` 端口的由来
- `NAS_API/AGENT_HANDOFF.md` —— NAS 主机名/双网卡/env 变量
- `sellfox_shipping/mcp_tools.py` + `main.py` —— FastMCP 骨架与挂载
- `sellfox-api-proxy/` + `new-api-deployment/AGENT_HANDOFF.md` —— VPS 上「Docker 服务 + nginx 路径块」的既有模式
- `docs/research/2026-09-20-sellfox-official-mcp-feasibility.md` —— 赛狐 MCP（含 ChatGPT 鉴权那条共同未决）

**外部（第三方群晖 MCP，**不推荐**，仅备查）**

- [DRVBSS/dk-synology-mcp — 87 工具/15 模块](https://github.com/DRVBSS/dk-synology-mcp)
- [vocweb/synology-mcp-server — 32 工具，含 ChatGPT 接入说明](https://github.com/vocweb/synology-mcp-server/blob/HEAD/integration-guide.md)
- [rafalmanka-synology-mcp — Rust 单二进制，可跑在 NAS 上](https://lobehub.com/mcp/rafalmanka-synology-mcp)
