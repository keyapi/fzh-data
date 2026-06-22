---
okf: v0.1
type: Explanation
title: 经验教训
description: 部署过程中的经验教训和避坑指南
tags: [lessons, pitfalls, tips]
---
# 经验教训

## Lesson 1: Tailscale 国内下载需要 winget

国内 Windows 优先用 `winget install Tailscale.Tailscale` 而非直接 curl 官方链接。

## Lesson 2: Tailscale P2P 打洞中美可行

北京↔US P2P 直连 215ms，先试直连再决定是否部署中继，不要提前过度设计。

## Lesson 3: Vultr Web 控制台是万能兜底

云端虚拟机永远有厂商控制台（浏览器 VNC），不需要第三方远程软件做初始化。

## Lesson 4: 免费 ChatGPT 账号几乎不可用

免费账号只有 `gpt-5.4-mini`，很快限额。Plus/Pro/Team 才可用。

## Lesson 5: CLIProxyAPI 绑定内网 IP 而非 0.0.0.0

`host: "<Tailscale IP>"` 防止端口暴露公网被扫描。

## Lesson 6: 共享 Windows 机器需评估资源

Tailscale + CLIProxyAPI 极轻量，但共享机器的其他因素（多用户 RDP）可能导致问题。

## Lesson 7: 文档即基础设施

OKF v0.1 规范、AGENT_HANDOFF.md 确保 Agent 接手丝滑，敏感信息用 .env 隔离。

## Lesson 8: Ping 通 != TCP 端口通 (Windows 防火墙)

从底层往上排查：ICMP ping → TCP 端口 → HTTP 应用层。Windows 防火墙可能阻断 Tailscale 虚拟网卡。

## Lesson 9: 代理进程须常驻

面向用户的代理/转发服务必须在首次验证后立即注册为持久化服务（systemd / NSSM）。

## Lesson 10: Windows Server 多用户 RDP 冲突 Tailscale

Windows 多用户 RDP 时，第一个登入用户独占 Tailscale GUI socket。`tailscale up --unattended` 绑定系统级，或直接用 Linux。

## Lesson 11: 服务器重启后所有手动进程都会丢失

所有服务必须注册为系统级自启。P2P 打洞重启后可能退化到 DERP relay。

## Lesson 12: Linux 比 Windows Server 更适合做转发服务

无 GUI 开销、systemd 原生、SSH 运维简单、Tailscale 无 session 冲突。1C2G 足够。

## Lesson 13: LAN 网关降低同事接入成本

Tailscale → 网关代理 → 纯 HTTP，接入门槛每降一步，推广阻力小一个量级。

## Lesson 14: Tailscale P2P 打洞重启后可能退化为 DERP

P2P 直连是 bonus，架构设计始终以 DERP relay 兜底为前提。

## Lesson 15: 善用 `tailscale up --unattended`

服务器环境始终用 unattended 模式，避免用户 session 绑定。

## Lesson 16: SSH SOCKS 代理解决无 GUI 服务器 OAuth

**问题**：Ubuntu 无桌面，无法浏览器 OAuth。且北京 IP 登录 ChatGPT 可能触发风控。

**解决**：一条 SSH 命令同时解决:
```bash
ssh -L 1455:127.0.0.1:1455 -D 1080 us-ubuntu-proxy
```
- `-L 1455`: OAuth 回调隧道回服务器
- `-D 1080`: SOCKS 代理，浏览器流量走服务器美国 IP

启动走 SOCKS 的 Chrome: `chrome.exe --proxy-server="socks5://localhost:1080"`

**教训**：SSH 是瑞士军刀，`-D` 动态端口转发经常被忽略但极其强大。

## Lesson 17: systemd 让运维降维

**优势**：
- `Restart=always` 崩溃自愈，不用写监控脚本保活
- `journalctl -u cliproxyapi -f` 实时看日志
- `systemctl enable` 开机自启零配置
- 内存仅 10.8MB，远超 Windows Service (NSSM) 的复杂度和失败率

**教训**：能用 systemd 就用 systemd，不要手动后台进程。

## Lesson 18: Tailscale 新机器入网只需 2 条命令

```bash
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up
```

浏览器打开链接授权即可。全流程 2 分钟。比配置任何 VPN 都快。

## Lesson 19: 敏感信息分层管理

不要在文档里写真实 IP / Key / 密码。分层:
| 层级 | 位置 | 内容 |
|------|------|------|
| L1 | Git 文档 | 占位符 `<VAR>` |
| L2 | `.env` (gitignore) | 真实值 |
| L3 | `~/.ssh/config` | SSH 密钥路径 |
| L4 | Tailscale 控制台 | 机器列表 |

**教训**：文档里出现真实 IP 或 Key = 安全漏洞。新 Agent 接手不需要知道公网 IP，只需要 Tailscale IP 和 API Key。
