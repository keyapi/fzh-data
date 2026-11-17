---
okf: v0.1
type: Reference
title: 办公室双 WAN 出口与「直连 SSID」设计（H3C ER3208G3-P-E）
date: 2026-11-17
category: architecture-patterns
module: us_openai_api_proxy
problem_type: architecture_pattern
component: api-gateway
severity: medium
applies_when:
  - "要给一部分人开一条不走代理（不翻墙）的 WiFi"
  - "排查 FZH-5G / 直连网段到底走 WAN1（OpenWrt）还是 WAN2（光猫）"
  - "规划 OpenWrt 故障时的自动切换与回切"
  - "直连设备解析不到 NAS 域名（fzh.myds.me 等）"
tags: [network-topology, h3c, dual-wan, policy-routing, openclash, tailscale, dns, failover]
related_components: [us_openai_api_proxy, NAS_API, openwrt, h3c]
---

# 办公室双 WAN 出口与「直连 SSID」设计（H3C ER3208G3-P-E）

## Context

办公室需要**同时**满足两件互相冲突的事：

1. 大多数人走 `FZH-5G` → H3C → **OpenWrt/OpenClash** → 代理出海；
2. 一部分人需要一条**不走代理、直连普通联通**的线路（性能/合规/故障兜底）。

物理上已经铺了两条腿：

```
联通光猫 192.168.1.1
├── 线路 A：OpenWrt(WAN 192.168.1.2) ── LAN 192.168.100.1 ── H3C WAN1 192.168.100.181（默认）
└── 线路 B：H3C WAN2 192.168.1.13（直连光猫，备用）
H3C LAN 192.168.10.0/24 ── AP AX71 ── FZH-5G
```

**关键事实**：H3C 在 OpenWrt 的**上游**（默认路由指向 OpenWrt LAN），客户端先被 H3C NAT 成
`192.168.100.181` 再进 OpenWrt。所以 OpenClash **只看得到这一个源 IP**，无法按 SSID/设备区分
（见 [openclash-per-target-direct-rule.md](../best-practices/openclash-per-target-direct-rule.md)）。

→ 想给某一部分人去掉代理，**只能让他们不经过 OpenWrt**，即走 WAN2。

## Guidance

### 2026-11-17 实机盘点（只读）

| 项 | 现状 |
|---|---|
| 型号/版本 | ER3208G3-P-E / Release 0136P01 |
| WAN1 | 静态 `192.168.100.181`，NAT 启用，**链路探测未启用** |
| WAN2 | 静态 `192.168.1.13`，NAT 启用，**链路探测未启用**（链路通） |
| 静态路由 | `0.0.0.0/0 → 192.168.100.1`(WAN1)；`100.64.0.0/10 → 192.168.100.1`(WAN1, Tailscale) |
| 多WAN策略 | **平均分配负载分担**（不是主备） |
| 策略路由 | 1 条：`VLAN1 → 全流量 → WAN2`，**禁用** |
| VLAN | 只有 VLAN1 `192.168.10.0/24` |
| AP | 在线 1 台 AX71（模板 `default`，38 客户端）；离线 3 台（2 台坏机、1 台待布线） |
| 多 SSID | 「配置模板管理 → default」，每模板最多 8 个（实际数量看 AP 型号） |
| 客户端 DNS | `192.168.10.1`（H3C 自己），H3C 再转发给 OpenWrt |

实测：向 5 个不同公网目标 traceroute，全部 `→ 192.168.100.1 → 光猫`，即都走 WAN1。

### 新增 `FZH-Direct-5G` 的正确顺序

1. **多WAN策略改「主备模式」**：主 = WAN1，备 = WAN2。当前"平均分配"在原理上可能把部分源 IP
   分到 WAN2（等于绕过代理）；改主备能消除不确定性。
2. **新建 VLAN20**（如 `192.168.20.1/24`）并开 DHCP。
3. 端口管理/VLAN划分：确认 AP 上联口为 trunk，放行 VLAN1 + VLAN20。
4. 配置模板管理 → `default`：新增 SSID `FZH-Direct-5G`，绑定 VLAN20，只开 5G。
5. 策略路由：新增 **源 `192.168.20.0/24` → 出接口 WAN2**，启用。
6. H3C 静态DNS：NAS 域名指向 `192.168.1.5`（理由见下）。

> ⚠️ **那条现成的 `VLAN1 → WAN2` 规则绝对不能启用**——一启用就是全办公室绕过 OpenClash。

### Tailscale 必须做例外（最容易漏）

`100.64.0.0/10` 是 Tailscale 网段，靠 H3C 静态路由送到 OpenWrt。**策略路由优先级高于静态路由**，
所以一旦给 Direct 网段配"全流量 → WAN2"，Tailscale 也会被送去 WAN2 直接失效。

必须在策略路由里加一条**更高优先级**（数值更小）规则：
`源 192.168.20.0/24 + 目的 100.64.0.0/10 → 出接口 WAN1`。

### 静态DNS 指向 `192.168.1.5` 还是 `192.168.100.242`

| 指向 | OpenWrt 正常 | OpenWrt 挂了 |
|---|---|---|
| `192.168.100.242`（NAS eth0，OpenWrt LAN） | 短路径 | **不可达** |
| `192.168.1.5`（NAS eth1，光猫 LAN） | 经光猫多一跳 | **可达**（光猫活着就行） |

直连场景的主要价值就是"OpenWrt 挂了还能用"，所以 **H3C 静态DNS 用 `192.168.1.5`**。
OpenWrt 自己的 dnsmasq 仍保持 4 个域名 → `.242` 不用动（H3C 客户端优先走 H3C 的静态DNS）。

覆盖的域名：`fzh.myds.me`、`nas.daneey.com`、`nas.vilavi.cn`、`nas.mxdeals.com`。

### OpenWrt 故障兜底：链路探测 + 主备

- 只靠**物理链路状态**不够：OpenWrt 挂了但 H3C WAN1 网线仍是 up。
- 必须给 WAN1 开**链路探测**（ICMP/DNS/NTP，可设探测地址、间隔、超时、上线/下线次数），
  探测目标选一个**只有经 OpenWrt 才能通**的公网地址。
- 手册只写了"主链路故障自动切备份"，**没有写回切**。回切行为必须实测（断 OpenWrt → 观察切换 →
  恢复 → 观察是否自动切回）。若不回切，只能手工切回。
- 注意语义：切到 WAN2 后**全办公室变直连**，这是预期的兜底状态。

### 地址占位（容易忘）

- H3C WAN1 `192.168.100.181` 落在 OpenWrt DHCP 池 `.100–.249` 内，且 **OpenWrt 没有它的静态绑定**
  → 有被别的设备抢走的风险。应在 OpenWrt 加静态 host：MAC `80:61:6C:01:7A:1E → .181`。
- H3C WAN2 `192.168.1.13` 落在光猫 DHCP 池 `.2–.254` 内 → 在光猫加静态绑定
  （MAC `80:61:6C:01:7A:1F → .13`）纯做占位。

## Why This Matters

- 出口走错一条线，症状都一样（"某网站打不开/变慢"），但原因可能是代理没生效或代理被绕过；
- 直连 SSID 若做成"走 WAN1 但在 OpenClash 里加 DIRECT"，在多级 NAT 下**根本做不到按人隔离**；
- Tailscale 例外与 DNS 指向是两个"看起来无关、实际会互相打断"的耦合点，配置前不写清就会二次返工。

## When to Apply

- 要新增"不翻墙"的 WiFi / 给某类设备分流；
- 回答"这条流量走哪条线"、"为什么这个人没翻墙"；
- 规划或演练 OpenWrt 故障兜底；
- 直连设备打不开 NAS 域名。

## Examples

定界"走哪条 WAN"最快的方法（在 H3C 后面的机器上）：

```bash
tracert -h 3 -d 223.5.5.5     # 第 2 跳 192.168.100.1 → 走 WAN1(OpenWrt)
tracert -h 3 -d 192.168.1.1   # 第 2 跳就是 192.168.1.1 → 直连光猫网段(connected，走 WAN2)
```

判断出口是否被代理（不要在办公室看，要看真实出口）：

```bash
curl -s https://api.ipify.org     # 订阅节点 IP = 主线路；运营商 IP = 直连
```

## Related

- [office-egress-fallback-chain.md](office-egress-fallback-chain.md) —— 出口三条路径（主/应急/直连）与定界
- [us_openai_api_proxy/docs/office-lan-access.md](../../../us_openai_api_proxy/docs/office-lan-access.md) —— 办公室逐级拓扑与 Tailscale 子网路由
- [../best-practices/openclash-per-target-direct-rule.md](../best-practices/openclash-per-target-direct-rule.md) —— 多级 NAT 下无法按设备隔离
- [NAS_API/docs/reference/router-port-forward-inventory.md](../../../NAS_API/docs/reference/router-port-forward-inventory.md) —— 光猫侧端口转发与 NAS 双网口
- [../developer-experience/h3c-er-g3-readonly-automation.md](../developer-experience/h3c-er-g3-readonly-automation.md) —— 如何只读登录 H3C 核对配置
