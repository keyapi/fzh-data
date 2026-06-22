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

**教训**：先试 Tailscale 直连再决定是否部署中继，不要提前过度设计。Tailscale 的 NAT 穿透能力比预期强。

## Lesson 3: Vultr Web 控制台是万能兜底

**问题**：先有鸡还是先有蛋——要装 Tailscale 就得远程连 US 机器，要远程连就得先装 Tailscale。

**解决**：Vultr 网页控制台（浏览器 VNC）可以在不装任何软件的情况下操作 Windows 桌面。这是初始安装入口，也是 Tailscale/RDP 全挂时的最后兜底。

**教训**：云端虚拟机永远有厂商控制台这个后门，不需要第三方远程软件做初始化。

## Lesson 4: CLIProxyAPI 免费账号几乎不可用

**问题**：用免费 ChatGPT 账号 OAuth 登录后，API 返回模型只有 `gpt-5.4-mini`，且很快触发限额。

**解决**：必须用 Plus ($20/月)、Pro ($200/月) 或 Team 账号才能稳定使用。

**教训**：部署前先确认订阅等级，免费账号只能验证通道通不通，不能实际使用。

## Lesson 5: CLIProxyAPI 绑定 Tailscale IP 而非 0.0.0.0

**问题**：如果 CLIProxyAPI 绑定 `0.0.0.0`，8317 端口会暴露在 Vultr 公网上，可能被扫描攻击。

**解决**：`config.yaml` 中 `host: "<Tailscale IP>"`，仅监听虚拟网卡。

**教训**：任何内部服务都应绑定内网 IP，即使有防火墙也要做纵深防御。

## Lesson 6: 同事共用 Vultr 机器需最小化干扰

**问题**：Vultr VM 4GB 内存，同事日常 RDP 操作 Amazon，担心装 Tailscale + CLIProxyAPI 影响。

**结果**：Tailscale 虚拟网卡零干扰；CLIProxyAPI Go 二进制 ~50MB 内存，CPU 可忽略。

**教训**：在共享机器上部署服务前，先评估资源占用和可能的干扰点，选择轻量方案。

## Lesson 7: 文档即基础设施

**问题**：多步骤手动操作，中途换对话或换 Agent 会丢失上下文。

**解决**：按 OKF v0.1 规范建立模块文档，AGENT_HANDOFF.md 确保 Agent 接手丝滑，敏感信息用 .env 隔离。

**教训**：做完每一步立即文档化，不要等全部完成再补。
