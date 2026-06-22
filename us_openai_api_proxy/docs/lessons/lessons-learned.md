---
okf: v0.1
type: Explanation
title: 经验教训
description: 部署过程中的经验教训和避坑指南
tags: [lessons, pitfalls, tips]
---
# 经验教训

## Lesson 1: Tailscale 国内下载需要 winget

**问题**：`pkgs.tailscale.com` 从国内直接下载超时，curl 和 Invoke-WebRequest 均失败。

**解决**：用 `winget install Tailscale.Tailscale`，Windows 包管理器走国内 CDN 下载正常。

**教训**：国内 Windows 机器优先用 winget 安装国外软件，避免直接 curl 官方下载链接。

## Lesson 2: Tailscale P2P 打洞中美可行

**问题**：担心中美之间 NAT 复杂，P2P 打洞成功率低，需要部署 DERP 中继。

**结果**：北京↔US Vultr P2P 直连成功，延迟 ~260ms，无需中继。

**教训**：先试 Tailscale 直连再决定是否部署中继，不要提前过度设计。

## Lesson 3: Vultr Web 控制台是万能兜底

**问题**：先有鸡还是先有蛋——要装 Tailscale 就得远程连 US 机器，要远程连就得先装 Tailscale。

**解决**：Vultr 网页控制台（浏览器 VNC）可以在不装任何软件的情况下操作 Windows 桌面。

**教训**：云端虚拟机永远有厂商控制台这个后门，不需要第三方远程软件做初始化。

## Lesson 4: 免费 ChatGPT 账号几乎不可用

**问题**：免费账号 OAuth 登录后模型只有 `gpt-5.4-mini`，很快触发限额。

**解决**：必须用 Plus ($20/月)、Pro ($200/月) 或 Team 账号。

**教训**：部署前先确认订阅等级，免费账号只能验证通道通不通，不能实际使用。

## Lesson 5: CLIProxyAPI 绑定内网 IP 而非 0.0.0.0

**问题**：如果绑定 `0.0.0.0`，端口暴露在公网上可能被扫描攻击。

**解决**：`config.yaml` 中 `host: "<Tailscale IP>"`，仅监听虚拟网卡。

**教训**：任何内部服务都应绑定内网 IP，即使有防火墙也要做纵深防御。

## Lesson 6: 共享 Windows 机器需评估资源

**问题**：Vultr VM 4GB 内存，同事日常 RDP 操作 Amazon，担心影响。

**结果**：Tailscale 虚拟网卡零干扰；CLIProxyAPI Go 二进制 ~50MB 内存。

**教训**：在共享机器上部署服务前，先评估资源占用和可能的干扰点。

## Lesson 7: 文档即基础设施

**问题**：多步骤手动操作，中途换对话或换 Agent 会丢失上下文。

**解决**：按 OKF v0.1 规范建立模块文档，AGENT_HANDOFF.md 确保 Agent 接手丝滑，敏感信息用 .env 隔离。

**教训**：做完每一步立即文档化，不要等全部完成再补。

## Lesson 8: Ping 通 != TCP 端口通 (Windows 防火墙)

**问题**：Tailscale ping 通但 curl 被拒。Windows 防火墙默认阻止入站连接，Tailscale 虚拟网卡被归类为"公用网络"。

**解决**：在 Windows 防火墙中为 Tailscale 网卡放行 8317 端口，或将 Tailscale 网络设为"专用网络"。

**教训**：网络调试时从底层往上排查：ICMP ping → TCP 端口 → HTTP 应用层。每层都可能被 Windows 防火墙阻断。

## Lesson 9: 代理进程须常驻，不能测试完就停

**问题**：LAN 网关代理用 `python lite_lan_proxy.py` 测试成功后关掉窗口，同事那边立即断连。

**解决**：同类问题要用 NSSM / systemd 注册为常驻服务。

**教训**：任何面向用户的代理/转发服务必须在首次验证后立即注册为持久化服务。

## Lesson 10: Windows Server 多用户 RDP 冲突 Tailscale

**问题**：Windows Server 多用户同时 RDP 登录时，第一个登入的用户独占 Tailscale GUI socket。其他用户运行 `tailscale status/up` 时报 `401 Unauthorized: Tailscale already in use by XXX`。

**原因**：Tailscale Windows 客户端使用每用户 session 的 IPC socket，不是真正的系统级服务。

**解决**：
- 临时：杀掉占有进程 (`Stop-Process -Id <pid>`) + 当前用户重跑 `tailscale up`
- 长期：`tailscale up --unattended` 绑定系统级，或改用 Linux 服务器

**教训**：Windows Server 多用户环境下不适合部署依赖用户 session 的服务。Linux + systemd 才是正确的服务器部署方式。

## Lesson 11: 服务器重启后所有手动启动的进程都会丢失

**问题**：Vultr VM 重启后 Tailscale 虽然作为 Service 自启，但 P2P 打洞状态丢失，降级到 DERP relay。CLIProxyAPI 没注册为 Service，直接消失。

**解决**：所有服务必须注册为系统级自启 (systemd / Windows Service)。Tailscale P2P 打洞在重启后可能退化，需要接受 DERP relay 作为兜底。

**教训**：验证部署时不要只看"现在能通"，要模拟重启后验证。

## Lesson 12: Linux 比 Windows Server 更适合做转发服务

**问题**：Windows Server 的 GUI 开销、多用户 session 管理、NSSM 注册失败等问题增加了运维复杂度。

**决策**：新开 Ubuntu 24.04 (1C2G) 替代 Windows Server。

**优势**：
- 无 GUI 开销，1C2G 足够
- systemd 原生支持，注册服务零依赖
- SSH + tmux 运维简单
- Tailscale Linux 版没有多用户 session 冲突
- Docker 可选，但二进制部署也简单

**教训**：转发/代理类服务优先选 Linux 服务器。Windows Server 适合需要 GUI 的场景（如 Amazon 后台操作），不适合做后端服务。

## Lesson 13: LAN 网关降低同事接入成本

**问题**：每位同事装 Tailscale 不现实（安装、登录、配置）。

**解决**：一台网关电脑装 Tailscale + `lite_lan_proxy.py` :3000 反代到远程 CLIProxyAPI，同事只需改 Codex++ Base URL 为 `http://<网关IP>:3000/v1`。

**教训**：接入成本每降低一步，推广阻力小一个量级。Tailscale → 网关代理 → 纯 HTTP 是递减的接入门槛。

## Lesson 14: Tailscale P2P 打洞重启后可能退化为 DERP

**问题**：首次 P2P 打洞成功 (`via 45.63.1.166:41641`)，机器重启后降级到 `via DERP(nyc)`。

**原因**：P2P 打洞状态（NAT mapping）在重启后过期，需要双方重新通信才能重建。Tailscale 会自动尝试重新打洞，但 DERP relay 作为即时兜底。

**影响**：延迟差不多（P2P ~252ms vs DERP ~260ms），功能不受影响。但多了一跳 DERP 中继。

**教训**：P2P 直连是 bonus 不是 guarantee。架构设计始终以 DERP relay 兜底为前提。

## Lesson 15: 善用 `tailscale up --unattended` 避免用户绑定

**问题**：Windows 上 `tailscale up` 将认证绑定到当前用户 session，其他用户无法控制。

**解决**：`tailscale up --unattended` 绑定到系统级，所有用户共享。

**教训**：服务器环境（尤其是多用户 Windows Server）始终用 unattended 模式。
