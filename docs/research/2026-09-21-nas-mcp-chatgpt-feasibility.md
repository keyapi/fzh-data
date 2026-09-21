---
type: Research
title: 群晖 NAS 接入 ChatGPT — 部署在 VPS；✅ 实测 ChatGPT 静态令牌可用；第三方方案对比与三次自我更正
description: NAS 公网 443 被联通封（非配置问题，NAS 永远给不了公网 443）故部署在 VPS。✅ 已实测 ChatGPT「访问令牌(Bearer)」路线可用 —— 日志见 openai-mcp/1.0.0 带 Authorization 头完成全流程。含第三方群晖 MCP 对比（mrquj 支持 Streamable HTTP+Bearer，最贴合）、Tailscale Funnel 公网可扫描的发现，以及三处对本文自身错误结论的更正
tags: [nas, synology, mcp, chatgpt, deployment, tailscale, research]
timestamp: 2026-09-21
---

# 群晖 NAS 接入 ChatGPT：可行性、部署位置与方案对比（2026-09-21）

## 一句话结论

**能接，部署在 VPS（`api.vilavi.cn`）而不是 NAS。**
但**暴露路径有一个比公网端口更好的选择**（见 §4），且**实现路线不止「自建」一条**（见 §3）。

---

## 一、定论：NAS 的公网可达性（实测）

在**北京办公室内网**初测 `https://nas.vilavi.cn/` 得 **HTTP 200** —— **假阳性**：
办公室 OpenWrt dnsmasq 把该域名**劫持到内网 `192.168.100.242`**。

改用**两处独立外部主机**复测：

| 目标 | 上海 VPS | 美国 VPS |
|---|---|---|
| `nas.vilavi.cn:443` | **失败** | **失败** |
| `nas.vilavi.cn:11024` | ✅ HTTP 200 | ✅ HTTP 200 |
| `api.vilavi.cn:443`（对照） | ✅ HTTP 200 | ✅ HTTP 200 |

→ 与仓库既有记载吻合。**教训：在办公网内测自家公网可达性 = 无效。**

### 1.1 ⭐ 为什么 443 不通 —— **是联通封的，不是配置问题**

这一点**仓库里早有完整记载**（`NAS_API/docs/reference/nas-multi-domain-access.md` §网络拓扑）：

```
联通光猫 192.168.1.1（公网 123.117.236.65）
├── 端口转发 11024 → 192.168.1.5:11024   （通）
├── 端口转发 443   → 192.168.1.5:443     （LAN 通，公网不通 —— 联通限制）★
└── LAN → OpenWrt WAN eth1 192.168.1.3

OpenWrt 192.168.100.1 ── dnsmasq 劫持 4 个域名 → 192.168.100.242
新华三 192.168.10.1（FZH-5G WiFi）── 客户端 DNS 也劫持 myds → .242
群晖 NAS 双网口: eth0 192.168.100.242（OpenWrt LAN）/ eth1 192.168.1.5（光猫 LAN）
```

**→ 公网 443 是 ISP 层封的（联通限制）**，任何 NAS/OpenWrt 配置都改不了。
**推论**：NAS **永远不可能**提供公网标准 443 —— 除非走**隧道**（Cloudflare Tunnel / Tailscale Funnel 之类，不依赖入向端口）。
这条**强化了「部署在 VPS」的结论**：VPS 有真实可用的公网 443。

> 也解释了本次「假阳性」的机制：本开发机在 `192.168.10.9`（新华三网段），DNS 指向 `192.168.10.1`，
> 该 DNS 把 `nas.vilavi.cn` 解析成 `192.168.100.242` → curl 实连 `192.168.100.242:443` 得 200。
> **是内网 DNS 覆盖，不是公网可达。**

### 1.2 NAS 双网卡与「默认路由会翻」的副作用

NAS 双网口（`eth0` 在 OpenWrt LAN / `eth1` 在光猫 LAN），**默认线路是 `eth1`（光猫侧，`192.168.1.5`）**，
选择理由是**可访问率**（OpenWrt/翻墙路由器挂了也不影响）。
但**断电重启有一定概率默认口翻到 LAN1**（近期办公楼断电 2 次后仍保持 LAN2）。

**这对方案的直接后果**：

| 路径 | 依赖 NAS 的**出向**默认路由吗 | 断电翻转后 |
|---|---|---|
| 公网 `:11024`（现状） | ❌ **不依赖** —— 端口转发是**入向**，与出向路由无关 | ✅ 不受影响 |
| **NAS 上装 Tailscale** | ✅ **依赖**（出向要找到控制面） | ⚠️ **可能断** |
| **OpenWrt 侧定向转发**（不动 NAS） | ❌ 不依赖 | ✅ 不受影响 |

> **→ 「NAS 装 Tailscale」在本场景被高估**：它引入的正是当初选 LAN2 想规避的那类风险。
> 另有已知副作用：LAN2 与 LAN1 的**翻墙能力不一致**，群晖自动备份 Google Sheet 到 NAS 的功能受默认口影响。

---

## 二、IP 关系（已查实一部分）

| IP | 是什么 | 依据 |
|---|---|---|
| **`8.133.254.66`** | 上海 VPS（EN 测试 `ensh` / `api.vilavi.cn` 同一台）的**真实出口 IP** | 在该机 `curl ifconfig.me` 实得；网卡只有 `192.168.0.12` + Tailscale `100.119.28.72`，公网 IP 是 EIP |
| **`82.156.238.248`** | 赛狐 OpenAPI **IP 白名单**里的「VPS」条目，2026-06-25 入仓 | `SELLFOX_API/docs/research/2026-06-25-sellfox-api-exploration.md:26` |

**⚠️ 两者关系仍未确认** —— `82.156.238.248` **不是**上述那台的出口。它可能是另一台 VPS（也可能已下线）。
**对 NAS 的影响**：若要给 DSM 加白名单，**应加 `8.133.254.66`**（那是 api.vilavi.cn 的真实出口）。
`82.156.238.248` 是否仍在服役，需单独确认。

---

## 三、实现路线对比（**更正早先的「不推荐第三方」**）

早先本文写「不推荐第三方群晖 MCP」。**那个结论下得太粗** —— 实际有若干可用方案，其中**有一个明显更贴合**。逐一对比：

| 方案 | 传输 | ChatGPT 能否直连 | 范围控制 | 评价 |
|---|---|---|---|---|
| **① `mrquj/mcp-server-synology`**（Node） | **`POST /mcp` Streamable HTTP** + `Authorization: Bearer <token>`；**默认只绑 `127.0.0.1:3020`**（要求前面挂反代） | ✅ **能** | **路径白名单**（含 symlink 逃逸防护）+ 只读启发式 + **策略下不可能成功的工具直接从清单隐藏**；泛用 `call_dsm_api` 另开关、默认关 | ⭐ **最贴合**。默认绑回环 + 反代 的架构与本文设计一致；`/healthz` 可审计当前策略 |
| ② `cmeans/mcp-synology`（Python, Apache-2.0） | 疑似 **stdio** + OS keyring 存凭据 | ❌ 需再加桥接 | **权限分层（READ/WRITE 在工具注册时强制）** + 2FA + 回收站 | 面向本地桌面；权限分层设计好，但传输不适配 ChatGPT |
| ③ `lordraw77/synology-mcp`（Python, MIT） | stdio；另有 HTTP streamable | 可能 | 71 工具，覆盖 Docker/VMM/用户组/计划任务 —— **面过宽** | 权限面远超「只读一个共享文件夹」的需求 |
| ④ **AnythingMCP**（通用 MCP 网关，AGPL-3.0） | HTTP，**自带 OAuth2 / RBAC / 审计日志** | ✅ | 需自己把 DSM REST 映射成工具（175+ 预置适配器里没有群晖） | 引一个**新的常驻系统**；好处是鉴权层现成。**除非以后要接很多异构源，否则对「一个共享文件夹」过重** |
| ⑤ **自建薄 MCP**（复用 `NAS_API/synology.py`） | 自己实现 Streamable HTTP | ✅ | **最可控** | 开发量最小（客户端与范围限制都有），但要自己维护传输/鉴权 |

### 3.1 ⚠️ 更正：`sellfox_shipping/mcp_tools.py` **不是**「现成的骨架」

早先本文把它列为可直接复用的 FastMCP 骨架。**实际不是**：

- 文件确实存在（201 行，2026-07-16 由 keyapi 提交），**但从未真正启用**
- **`fastmcp` 不在根 `pyproject.toml` 依赖里** —— 只有 `sellfox_shipping/Dockerfile:22` 单独装
- `sellfox_shipping/main.py:7-17` 用 `try/except ImportError: pass` **静默吞掉**导入失败
- `sellfox_shipping/AGENT_HANDOFF.md:253` 自述：**「FastMCP（legacy；根 uv 环境无 fastmcp，Docker 另装）」**
- 相关测试（`docs/log.md:768-773`）验证的是**「不装 fastmcp 也能起服务」的 no-op 路径**
- 设计文档也说 MCP 映射是**延后**项（`recovery-cli-error-taxonomy-outbox-plan-2026-08-05.md:14`）

→ **它是一个「可参考形状」的脚手架，不是可复用的已验证组件。** 复用它等于从头验证一遍。

### 3.2 ⚠️ 更正：FAC 里加工具**没有**仓库内配方

「把 NAS 读取做成 FAC 的一个工具、复用已通的 ChatGPT 连接」这条路：
- **FAC 源码不在本仓库**（`frappe_assistant_core/*` 在服务器/上游，`git ls-files` 为空）
- 仓库里**没有** FAC 自定义工具/插件的编写文档（只有 `docs/fac-dev-notes.md` 的工具用法与 `docs/fac-mcp-setup.md` 的连接指南）
- 所以这条路**可行但要研究上游插件机制 + 在服务器上部署**，不是现成动作

---

## 四、暴露路径：**Tailscale 私网优于公网端口**（本次新发现）

### 4.1 现状（实测）

上海 VPS 上 tailnet 已存在，成员包括**办公室 OpenWrt 路由器**：

```
100.119.28.72    izuf6cg60rfql8k8qbw87xz   上海 VPS          linux
100.124.94.69    openwrt                   办公室路由器        linux
100.126.133.106  vultr                     linux   active
# Funnel on:  https://izuf6cg60rfql8k8qbw87xz.alpines-grouper.ts.net
#   └── /  →  http://127.0.0.1:3000          ← 这是 new-api，已被公网暴露
```

- **VPS 能 ping 通办公室路由器**（`100.124.94.69` → OK）
- **但 ping 不通 NAS**（`192.168.100.242` → FAIL）→ **路由器没有 advertise 办公网段**，Tailscale 这条路**暂时到不了 NAS**
- **Funnel 已经在用**，当前把 `new-api`（:3000）以 443 公网暴露

### 4.2 更好的架构：把 NAS 拉上 tailnet

`mrquj` 项目在「Reaching a NAS that sits behind your home router」一节给出的建议，**正是我们的场景**：

> A hosted MCP server cannot dial into a home LAN directly. Rather than port-forwarding DSM
> to the public internet, put both machines on a private overlay network and point `SYNOLOGY_URL`
> at the overlay address. **Only the MCP server needs to reach DSM. DSM itself stays unexposed.**

有几种实现路径，但**结合 §1.2 的默认路由问题后，结论与 `mrquj` 的泛化建议不同**：

| 路径 | 做法 | 优点 | 代价 / 风险 |
|---|---|---|---|
| ~~**T1. NAS 装 Tailscale**~~ | NAS 加入 tailnet | 不用动路由器 | ⚠️ **依赖 NAS 出向默认路由** → 断电翻转可能断（§1.2）。**本场景不推荐** |
| **T2. 让 OpenWrt advertise 网段** | 路由器 `--advertise-routes=192.168.100.0/24` + 控制台批准 | 不用动 NAS | **把整个办公网 LAN 暴露给 tailnet** —— 面太大 |
| **⭐ T3. OpenWrt 定向转发** | 在 OpenWrt 上把 **tailnet 侧的一个端口 DNAT 到 `192.168.100.242:5001`** | 只暴露 NAS 的 DSM 端口，**不暴露整个网段**；**不依赖 NAS 出向路由** | 需在 OpenWrt 加一条 NAT 规则 |
| **T4. 维持公网 `:11024`**（现状） | 不动 | 已通、不依赖 NAS 路由 | **DSM 暴露在公网非标端口** |

### 4.3 ⚠️ 再更正：**T3 也会破坏你的可靠性设计** —— 维持现状（T4）才对

上一轮我把「OpenWrt 定向转发（T3）」列为首选。**再想一层发现它同样有问题**：
转发规则**就在 OpenWrt 上** —— OpenWrt 一断电，这条路**直接没了**。

把三种路径在**两种已知故障**下摊开看：

| 路径 | **OpenWrt 断电**时 | **NAS 默认口翻到 LAN1**时 |
|---|---|---|
| **公网 `:11024`（现状 T4）** | ✅ **不受影响**（入向端口转发） | ✅ **不受影响** |
| NAS 装 Tailscale（T1） | 默认口在 LAN2 → ✅ 可用；**已翻到 LAN1 → ❌ 断** | ⚠️ **可能断** |
| OpenWrt 定向转发（T3） | ❌ **直接断** | ✅ 不受影响 |

> **⭐ 结论（第三次修正）**：**只有公网 `:11024` 在两种故障下都不受影响。**
> 用户当初把 NAS 默认口放 LAN2，**买到的就是这个性质** —— 而 T3 会把它卖掉。
>
> **所以不要为了「更安全」把主路径从 `:11024` 挪走。**
> 想更安全，应该在**这条路上加约束**：只读 DSM 账号 + 只放行 VPS 出口 IP `8.133.254.66`
> + 开证书校验 + 必要时在 DSM 侧限速/自动封锁白名单。
>
> Tailscale 可以作为**备用或运维通道**（例如 SSH），但**不要当主通路**。

---

## 五、鉴权：ChatGPT 两条路线都能走，但**我们已有一条被验证的**

这是本次要回答的核心疑问（「ChatGPT 能否用自定义标头鉴权」）。

### 5.1 两条路线

| 路线 | ChatGPT 侧怎么配 | 服务端要求 |
|---|---|---|
| **A. 静态令牌** | 建连接器时选「**访问令牌 / API 密钥**」→ ChatGPT 发 `Authorization: Bearer <token>` | 服务端接受静态 Bearer 即可（`mrquj` 正好支持） |
| **B. OAuth 2.1** | 选 OAuth → 走授权码流程 | 需 PKCE(S256) + `/.well-known/oauth-protected-resource` + DCR 或 CIMD + 回显 `resource` 参数 |

**两条都可用**，但要注意趋势：MCP 授权规范已把 **OAuth 2.1 定为强制**（有资料称 **2026-03-15 起强制**），
静态令牌被描述为**过渡性**方案；且**已发布的/可发布的应用**走 OAuth 是硬要求（个人开发者模式的连接器才能用静态令牌）。

### 5.2 ✅ **已验证：ChatGPT 的静态令牌路线可用**（2026-09-21 实测）

**不再需要「先验一次」了 —— 已经验完，结论是「能用」。**

做法（**零生产影响**）：在开发笔记本上起一个最小 MCP 服务（~140 行 stdlib，只做 `initialize` /
`tools/list` / 一个 `probe_echo`），用**该机自己的 Tailscale Funnel**（原本无任何 serve 配置）
暴露成公网 443，在 ChatGPT 网页版建「访问令牌 / API 密钥 → 持有者(Bearer)」连接器。

**服务端日志实测收到的请求**（关键证据）：

```
User-Agent = openai-mcp/1.0.0 (Agent Builder)
Authorization = Bearer probe-f…
请求序列：server/discover → initialize → notifications/initialized → tools/list → tools/call
```

→ **ChatGPT 确实按「Bearer」方案发送了 `Authorization` 头，且整条 MCP 握手与工具调用都成功**
（`probe_echo` 返回 `echo: 测试`）。

**这对两个项目的意义**：

| | 结论 |
|---|---|
| **NAS MCP** | 可以走**静态令牌**，不必实现 OAuth。`mrquj` 那类「Streamable HTTP + Bearer」的服务**直接可用** |
| **赛狐官方 MCP** | 同样受益 —— 它的 `X-MCP-Key` / 双头方案属于同类静态令牌思路（注意：ChatGPT 的「自定义标头」下拉**只给一个头**，赛狐若需两个头要另行验证） |

> **仍建议保留 OAuth 作为备选**：MCP 授权规范已把 OAuth 定为强制方向（§5.1），
> 静态令牌属过渡方案。**但至少现在不必为它先做 OAuth**。

### 5.3 顺带发现：**Tailscale Funnel 是公开可扫描的**

funnel 一开，**数分钟内**就被互联网扫描器命中（`leakix.net` 的 l9scan、`ForestEngine`、
以及 `ClaudeBot`）。说明：

> **Funnel ≠ 私密通道**，它是**公网可发现**的。用 Funnel 给 NAS 一个公网地址，
> 在安全上**不比端口转发更好**（只是不用改光猫）。这条**削弱了「用 Funnel 替代 nginx」的动机**。

---

## 六、建议的推进顺序（已按本次发现调整）

1. ~~鉴权最小验证~~ → ✅ **已完成：静态令牌可用**（§5.2）
2. **VPS → NAS 维持现状 T4（公网 `:11024`）**（§4.3）—— 只有它在两种已知故障下都不受影响
3. **实现路线二选一**（§3）：
   - **① `mrquj/mcp-server-synology`** —— 省开发；默认绑回环 + 路径白名单 + 只读启发式；**且原生支持 Bearer 静态令牌，与 §5.2 验证过的路线一致**
   - **⑤ 自建薄 MCP**（复用 `NAS_API/synology.py`）—— 范围最可控；但传输/鉴权要自己实现
   > 两者的**部署形态相同**（VPS 上容器 + 前置反代），所以**先在本地把 ① 跑起来验证连通**，再决定是否值得自建。
4. 前置反代：用**已有 nginx**（`api.vilavi.cn/nas/*`）
5. 安全：专用只读 DSM 账号 + **应用专用密码**（DSM API 不支持 2FA）；**开证书校验**；
   **只放行 VPS 出口 IP `8.133.254.66`**；范围锁死在 `NAS_ROOT_FOLDER`；`delete` 类工具不暴露
3. **实现路线二选一**：
   - **① `mrquj/mcp-server-synology`** —— 省开发；默认绑回环 + 路径白名单 + 只读启发式，安全姿态最好；若走静态令牌它现成支持
   - **⑤ 自建薄 MCP**（复用 `NAS_API/synology.py`）—— 范围最可控；但传输/鉴权要自己实现
   > 两者的**部署形态相同**（VPS 上容器 + 前置反代），所以**先在本地把 ① 跑起来验证鉴权与连通**，再决定是否值得自建。
4. 前置反代：优先用**已有 nginx**（`api.vilavi.cn/nas/*`）；备选 **Tailscale Funnel**（已在用，当前指向 new-api）
5. 安全：专用只读 DSM 账号 + **应用专用密码**（DSM API 不支持 2FA）；**开证书校验**；范围锁死；`delete` 类工具不暴露

---

## 七、未决

| # | 问题 | 怎么解 |
|---|---|---|
| 1 | ~~ChatGPT 静态令牌 vs OAuth~~ | ✅ **已验：静态令牌可用**（§5.2） |
| 2 | `82.156.238.248` 是否仍在服役、是什么 | 单独确认 |
| 3 | 赛狐官方 MCP 的**双请求头**在 ChatGPT 里怎么填（下拉只给一个自定义头） | 单独验证 —— 这是**赛狐特有**的问题，NAS 用单头不受影响 |
| 4 | 自建还是用 `mrquj` | 先在本地把 `mrquj` 跑起来验证连通 |

---

## 参考 URL / 仓库内

**实测**（2026-09-21）

- 外部视角：`ssh sh-erpnext-test`（上海 VPS）、`ssh us-ubuntu-proxy-pub`（美国 VPS）
- 出口 IP：在两台机上 `curl ifconfig.me`
- Tailscale：在上海 VPS 上 `tailscale status` / `tailscale serve status`
- 公网 DNS：Cloudflare DoH

**仓库内**

- `NAS_API/synology.py` —— DSM FileStation 客户端（读/写方法边界见设计稿）
- `NAS_API/docs/reference/nas-multi-domain-access.md` —— 公网域名、QuickConnect、`11024` 端口的由来
- `sellfox_shipping/mcp_tools.py` + `main.py` —— **脚手架（未启用）**，见 §3.1 更正
- `docs/fac-dev-notes.md` / `docs/fac-mcp-setup.md` —— FAC 用法与连接（**无**自定义工具编写文档，见 §3.2）

**第三方（候选方案）**

- [mrquj/mcp-server-synology](https://github.com/mrquj/mcp-server-synology) —— ⭐ Streamable HTTP + Bearer + 路径白名单 + 默认绑回环
- [cmeans/mcp-synology](https://github.com/cmeans/mcp-synology) —— 权限分层 + 2FA（偏本地 stdio）
- [lordraw77/synology-mcp](https://github.com/lordraw77/synology-mcp) —— 面很宽（71 工具）
- [HelpCode-ai/anythingmcp](https://github.com/HelpCode-ai/anythingmcp) —— 通用 MCP 网关（OAuth2/RBAC/审计），非群晖专用
- [OpenAI — Authentication (Plugins build)](https://developers.openai.com/plugins/build/auth) —— 连接器认证要求
- [Connect ChatGPT (Customerscore 文档)](https://docs.customerscore.io/mcp/chatgpt/) —— 「选 access token 而非 OAuth」的实操示例
