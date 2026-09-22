---
okf: v0.1
type: Reference
title: 境内访问境内服务器：Tailscale 走中继时慢到不可用，改用公网 HTTPS
date: 2026-09-22
category: tooling-decisions
module: pb_orders
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - "服务部署在国内云主机上，使用者也在国内，正在纠结走 Tailscale 还是公网"
  - "Tailscale 上访问自建服务『感觉有点慢』，需要判断是应用问题还是链路问题"
  - "计划把另一台机器（如个人笔记本）加进 Tailscale 来提速"
tags: [tailscale, derp, relay, latency, nginx, https, network]
related_components: [pb_orders, nas-access]
---

# 境内访问境内服务器：Tailscale 走中继时慢到不可用，改用公网 HTTPS

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

**处置：这条路直接弃用，改走同机已有的公网 HTTPS + 应用层登录。**

## Why This Works

- 同一台服务器上公网 HTTPS 只要 **125ms**，比 Tailscale 快约 **200 倍** ——
  因为它是客户端直连阿里云上海，没有跨境绕行。
- 公网暴露带来的风险用**应用层登录**补上（见
  [dingtalk-oidc-bridge-client-onboarding.md](../integration-issues/dingtalk-oidc-bridge-client-onboarding.md)）：
  容器只绑 `127.0.0.1`，公网必须经 NGINX 的 `/pb/` 且要过钉钉登录；
  直接访问 `:8412` 仍然拒绝连接。
- 服务器上本来就是这套模式（`api.vilavi.cn` + Certbot + 反代到 127.0.0.1 的多个服务），
  新增一个 location 而已，不需要新域名新证书。

## When to Apply

- 国内 ↔ 国内的访问被 Tailscale 绕到境外中继（看 `tailscale status` 里的 `relay "xxx"`）；
- Tailscale 上出现"能用但大文件传不完 / 页面要等十几秒"这类症状；
- 有人提议"把另一台机器也加进 Tailscale 提速"——**这条要单独说清**，见下。

## Examples

### 别指望"把个人笔记本加进 Tailscale"能提速

使用者最初的判断是「Tailscale 登录才能用，那把笔记本也加进去」。
这解决不了问题：

- 瓶颈是**中继路径**，不是账号或设备数；加了设备还是走同一个中继；
- 新增的如果是另一个身份（如微软账号），那是**另一个 tailnet**，
  要共享只能靠 Tailscale 的节点分享，配置更复杂；
- 如果首选方案是公网 HTTPS，**根本不需要 Tailscale**。

### 路由到中继而非直连的常见原因

- 云厂商安全组没放开 **UDP 41641**（Tailscale 直连用的端口）；
- 一侧处于运营商 CGNAT 后面，UDP 打洞失败；
- Tailscale 的协调服务器在境外，国内网络下建立直连本身就不稳定。

### 一条通用教训

**「内网方案」不等于「更快」**，尤其当两端分属不同运营商/云厂商时。
判断依据只能是实测数字，不是"它是个内网"。

## Related Issues

- [../integration-issues/reverse-proxy-prefix-return-to.md](../integration-issues/reverse-proxy-prefix-return-to.md)
  —— 走公网 + 前缀化部署后踩到的登录跳转坑
- [../integration-issues/dingtalk-oidc-bridge-client-onboarding.md](../integration-issues/dingtalk-oidc-bridge-client-onboarding.md)
  —— 公网暴露后补的登录层
- [nas-access.md 所在模块](../../../NAS_API/README.md) —— 另一处 Tailscale 使用场景（exit node）
