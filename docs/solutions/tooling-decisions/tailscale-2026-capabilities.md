---
okf: v0.1
type: Reference
title: Tailscale 2026 新能力盘点与对本仓库的适用性（Tailcat / Peer Relays / Services）
date: 2026-09-22
category: tooling-decisions
module: us_openai_api_proxy
problem_type: tooling_decision
component: tooling
severity: low
applies_when:
  - "评估是否升级/扩展当前 Tailscale 用法（NAS、出口、子网路由、内网服务）"
  - "有人问『Tailscale 最近有什么新东西』『Tailcat 是什么』"
  - "想改善跨境中继速度或减少手工维护的 NGINX location / 白名单"
tags: [tailscale, tailcat, peer-relays, services, mesh-vpn, infrastructure]
related_components: [us_openai_api_proxy, NAS_API, openwrt, pb_orders]
---

# Tailscale 2026 新能力盘点与对本仓库的适用性（Tailcat / Peer Relays / Services）

## Context

Tailscale 是本仓库的网络基础设施：办公室 OpenWrt 做子网路由、
多台服务器用 Tailscale IP 互访、NAS/出口都挂在上面。
2026 年 8–9 月 Tailscale 有一轮产品更新（Tailscale Up 大会 + Winter Update），
本篇记录**与本仓库相关的**部分及适用性判断，不追求穷尽发布说明。

## Guidance

### Peer Relays（GA）—— 最对症的一项

**自己部署中继**，替代 Tailscale 的公共 DERP 节点。支持部署在防火墙/负载均衡之后，
官方定位里明确写了「可替代传统子网路由器」。

**为什么对本仓库最有用**：本仓库遇到过「跨境走公共 DERP 中继导致 20-30 秒」
（见 [tailscale-relay-vs-public-https-china.md](tailscale-relay-vs-public-https-china.md)）。
根治办法是修直连（UDP 41641），但**当直连确实打不通时**（例如对端在 CGNAT 后），
自建中继能把「绕到香港公共中继」换成「走自己美国/上海的中继」——
吞吐与可控性都更好。

### Tailscale Services（GA）—— 减少手工维护面

把内部资源（数据库、API、Web 服务）发布为带**稳定 MagicDNS 名字**的一等对象，
配套细粒度访问控制与每服务审计日志，原生集成 `tsnet`（Go 库）。

**对本仓库的适用性**：现在每加一个内部服务，都要在 NGINX 上加 `location`、
在应用里加登录闸门、维护白名单（例如本次 `pb_orders` 的 `/pb/`）。
用 Services 可以把「谁可以访问哪个服务」收敛到 Tailscale 的策略层。
不过要注意：**它管的是网络层可达性，不替代应用层登录**——
页面里含客户数据的服务（如 `pb_orders`）仍然需要自己的认证。

### Tailcat —— 你问的那个

**Tailcat**（2026-08-31 开源，BSD-3）一句话：**"Tailscale without Tailscale"**。
把 Tailscale 的**数据面**（WireGuard 加密 + NAT 穿透 + DERP）拿出来做成独立
CLI 与 Go 库，**去掉控制面**：没有账号、没有 IP 地址、没有用户/管理员、
不需要 root、不改路由表和 DNS（纯用户态，自带用户态 TCP 栈）。

用法：服务端生成密钥对并选一个 DERP → 产出一个 `tc…` 地址
（像密码一样线下分享，可选白名单限定客户端公钥）→ 客户端连接后先经 DERP 会合，
再尝试 P2P 直连，打不通就退回 DERP 中继。

它的定位不是「Tailscale 替代品」——**没有身份、权限、设备管理**，
官方原文也把它描述为 netcat 的加密+穿透版。

**适用场景**：临时把一次性环境接进来（AI Agent 沙箱、临时 VM、树莓派、测试机），
不需要先配账号和网络。**对本仓库**：现在的 Tailnet 已经覆盖了长期设备，
Tailcat 更适合「临时/一次性」的连接，属于锦上添花，不是当前痛点。

### 其它（了解即可）

- **Aperture**：AI 网关，把 AI 智能体访问统一到 Tailscale 身份下、避免分发 API key。
  与 [`us_openai_api_proxy`](../../../us_openai_api_proxy/AGENT_HANDOFF.md) 的定位有重叠，值得后续评估。
- **Aperture Plus**：基于浏览器的访问入口，**不需要装系统级 VPN** ——
  与现在用 Funnel 给深圳兜底的做法可比。
- **Workload identity federation**：用代码管理联邦身份，消除静态 API key。
- **PAM**（源自收购 Border0）、Control D DNS 过滤。

## Why This Matters

- **Peer Relays** 是唯一直接改善「中继慢」这个已发生痛点的能力，优先级最高；
- **Services** 能收敛现在散在 NGINX location + 应用白名单里的访问控制，
  但**不能替代**应用层登录 —— 混淆这两层会出安全问题；
- **Tailcat** 是补位工具（临时连接），不是架构升级，别高估。

## When to Apply

- 要再优化跨境 Tailscale 速度，且直连已确认修过仍不理想时 → 评估 Peer Relays；
- 内部服务数量继续增长、NGINX location 与白名单开始难维护时 → 评估 Services；
- 需要临时接入一次性环境、又不想先配账号时 → 考虑 Tailcat。

## Examples

判断优先级的一个简单问法：

| 问题 | 该看哪个能力 |
|---|---|
| 「走公共中继太慢」 | Peer Relays（先确认直连是否已修） |
| 「每加一个服务都要改 NGINX + 白名单」 | Services（应用层登录仍要保留） |
| 「临时接一个沙箱进来，不想配账号」 | Tailcat |
| 「不想给每个人装 VPN 客户端」 | Aperture Plus / 现有 Funnel 兜底 |

## Related Issues

- [tailscale-relay-vs-public-https-china.md](tailscale-relay-vs-public-https-china.md)
  —— 中继/直连问题的实测与根因（UDP 41641）
- [../architecture-patterns/office-egress-fallback-chain.md](../architecture-patterns/office-egress-fallback-chain.md)
  —— 现有出口拓扑，评估任何改动前先看这张图
- `docs/superpowers/specs/2026-06-23-tailscale-upgrade-design.md` —— OpenWrt 上 Tailscale 的升级记录

## 来源

- <https://tailscale.com/blog/tailcat>
- <https://tailscale.com/blog/services-ga>
- <https://tailscale.com/winter-update-week-26>
- <https://www.networkworld.com/article/4215616/tailscale-expands-from-vpn-into-a-full-connectivity-platform.html>
- <https://gigazine.net/news/20260920-tailcat/>
