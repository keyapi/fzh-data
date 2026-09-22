---
okf: v0.1
type: Reference
title: Tailscale 慢到不可用：先查直连（UDP 41641 入站），别急着换方案
date: 2026-09-22
category: tooling-decisions
module: pb_orders
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - "Tailscale 上访问自建服务『感觉有点慢』，需要判断是应用问题还是链路问题"
  - "`tailscale status` 显示 relay『xxx』而不是 direct，想知道怎么修"
  - "计划把另一台机器（如个人笔记本）加进 Tailscale 来提速"
tags: [tailscale, derp, relay, latency, nginx, https, network]
related_components: [pb_orders, nas-access]
---

# Tailscale 慢到不可用：先查直连（UDP 41641 入站），别急着换方案

## Context

`pb_orders` 部署在上海阿里云的 EN 测试服务器上，使用者在国内。
第一版为了安全（服务当时没有任何登录）只监听 Tailscale 地址 `100.119.28.72:8412`。

上线后使用者反馈「速度感觉有点慢」，并且出现具体故障：
**12MB 的标签 PDF 下载没下完**（客户端留下 `.crdownload` 残留文件）。

## Guidance

**先量，再猜。** 同一时刻三条路径的实测：

| 访问路径 | 耗时 |
|---|---|
| 服务器**本机** `curl 127.0.0.1:8412` | **1-3 ms** |
| **公网 HTTPS**（同机 `api.vilavi.cn`） | **125-152 ms** |
| **Tailscale**（`100.119.28.72`） | **20-30 秒** |

从客户端测，`connect`（TCP 握手）单独就花 **12-19 秒**，`ttfb` 20-30 秒。
服务器侧同一个请求只要 1-3 ms —— **瓶颈在网络，不在应用**。

再看链路怎么走的：

```
$ tailscale status
100.119.28.72  <server>  ...  active; relay "hkg", tx ... rx ...
$ tailscale ping 100.119.28.72
ping "100.119.28.72" timed out        # 连中继都打不通
```

`relay "hkg"` = 走**香港 DERP 中继**而不是直连。两地都在国内却绕道香港，
跨境链路再把 UDP 打洞失败（云厂商安全组和内网 NAT 都常见），
结果就是「能用，但慢到不能用于大文件」。

**先别急着换方案 —— 这是可修的。** 直连失败的典型原因是**云厂商安全组没放行入站 UDP 41641**。

> **实测（2026-09-22，用户放开安全组后）**：
> ```
> $ tailscale ping izuf6cg60rfql8k8qbw87xz      # 从国内 PC
> pong ... via 8.133.254.66:41641 in 69ms       # 直连，69ms
> $ tailscale ping fzhpc13                      # 从上海服务器
> pong ... via 123.117.232.176:41641 in 35ms    # 直连，35ms
> ```
> 同一对机器，之前是 `relay "hkg"` + `tailscale ping` 超时 + HTTP 20-30 秒；
> **只改了安全组一条入站规则**，就变成 31-69ms 直连。应用的耗时也从 20-30 秒
> 掉到百毫秒级。

**处置顺序**：
1. **先查直连能不能修**（安全组/防火墙放行入站 **UDP 41641**，两端都要）。
   这是根因，修完所有 Tailscale 流量都受益，不只是这一个服务。
2. 直连修不动（对端在 CGNAT 后之类）或等不及，**再**考虑对**单个服务**
   改走公网 HTTPS + 应用层登录 —— 这属于绕开问题，不是解决问题。

## Why This Works

**修直连（首选）**：Tailscale 的设计就是「能直连就直连，直连不了才退回中继」。
直连走 WireGuard over **UDP 41641**，只要云厂商安全组放行入站该端口、且对端不在
CGNAT 后面，就会自动切回 direct。修完之后**所有**走 Tailscale 的用途
（NAS、出口节点、内网服务）都受益，不只是当次遇到的这一个服务。

**改公网 HTTPS（次选，绕开）**：如果直连确实修不动，对**单个服务**改走公网是有效的
——因为它是直连云厂商机房，没有跨境绕行。但要补一层登录，见
[dingtalk-oidc-bridge-client-onboarding.md](../integration-issues/dingtalk-oidc-bridge-client-onboarding.md)：
容器只绑 `127.0.0.1`，公网必须经 NGINX 的路径前缀且过钉钉登录。
服务器上已是这套模式（`api.vilavi.cn` + Certbot + 反代到 127.0.0.1 的多个服务），
新增一个 location 即可，不需要新域名新证书。

**注意这是绕开而非解决**：公网方案只救了一个服务，Tailscale 上的其它用途
（NAS、出口）仍然慢。所以能修直连就不要绕。

## When to Apply

- 国内 ↔ 国内的访问被 Tailscale 绕到境外中继（看 `tailscale status` 里的 `relay "xxx"`）；
- Tailscale 上出现"能用但大文件传不完 / 页面要等十几秒"这类症状；
- 有人提议"把另一台机器也加进 Tailscale 提速"——**这条要单独说清**，见下。

## Examples

### 本仓库实例：上海服务器上已有现成的 SOCKS5 出口

同一台机器上还跑着 `socks5-tunnel.service`（`ssh -N -D 100.119.28.72:1080 ... root@<美国 Vultr>`），
把**服务器自己**的流量经美国出口转出，用于拉 Docker Hub 这类国内不稳的资源。
它只监听 Tailscale 地址，**公网不可达、只在 tailnet 内可用**。

实测对比（服务器发起）：

| 目标 | 直连 | 经该 SOCKS5 |
|---|---|---|
| `registry-1.docker.io/v2/` | **HTTP 000（失败）** | **HTTP 401（通）** |
| `pypi.org/simple` | 200 但慢到 8s 超时 | 200，4.8s |

**但包和镜像仍优先用国内源**（清华 PyPI / 清华 apt / daocloud Docker）——
更快、更稳、且不涉及出口合规问题。隧道留给"确实没有国内等价物"的场景。

### 别指望"把个人笔记本加进 Tailscale"能提速

使用者最初的判断是「Tailscale 登录才能用，那把笔记本也加进去」。
这解决不了问题：

- 瓶颈是**中继路径**，不是账号或设备数；加了设备还是走同一个中继；
- 新增的如果是另一个身份（如微软账号），那是**另一个 tailnet**，
  要共享只能靠 Tailscale 的节点分享，配置更复杂；
- 正确的第一步是**查直连**（安全组 UDP 41641、对端 NAT），不是加设备。

### 路由到中继而非直连的常见原因

- 云厂商安全组没放开 **UDP 41641**（Tailscale 直连用的端口）；
- 一侧处于运营商 CGNAT 后面，UDP 打洞失败；
- Tailscale 的协调服务器在境外，国内网络下建立直连本身就不稳定。

### 「要不要自己开 41641」分两种环境（实测）

| 环境 | 需要开吗 | 说明 |
|---|---|---|
| **云主机（阿里云等）** | **要**，在**云平台安全组**里放开入站 UDP 41641 | 云安全组在主机 iptables 之前，`tailscaled` 拦不到 |
| **自管 Linux + ufw/iptables** | **不用** | `tailscaled` 启动时自动在 `ts-input` 链插 `ACCEPT udp dpt:41641`，且该链排在 ufw 的 DROP 策略**之前**。ufw 里只放行 22/tcp 也不影响 |

实测佐证（美国 Vultr）：`ufw status` 只有 `22/tcp ALLOW`、INPUT 策略 DROP，
但 `iptables -L ts-input` 里有 `ACCEPT udp dpt:41641`，且 `tailscale status`
显示与上海服务器 `active; direct 8.133.254.66:41641` —— **直连正常，无需人工干预**。

### 一条通用教训

**「内网方案」不等于「更快」**，尤其当两端分属不同运营商/云厂商时。
判断依据只能是实测数字，不是"它是个内网"。

## Related Issues

- [../integration-issues/reverse-proxy-prefix-return-to.md](../integration-issues/reverse-proxy-prefix-return-to.md)
  —— 走公网 + 前缀化部署后踩到的登录跳转坑
- [../integration-issues/dingtalk-oidc-bridge-client-onboarding.md](../integration-issues/dingtalk-oidc-bridge-client-onboarding.md)
  —— 公网暴露后补的登录层
- [nas-access.md 所在模块](../../../NAS_API/README.md) —— 另一处 Tailscale 使用场景（exit node）
