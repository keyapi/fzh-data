---
okf: v0.1
type: Reference
title: 办公室 OpenClash 单目标直连（境外 RDP/远程访问）
date: 2026-10-27
category: best-practices
module: office-network-openclash
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - "办公室 WiFi 客户端访问某境外主机/业务系统失败，但同一网络直连光猫正常"
  - "OpenClash 日志把目标匹配到默认 Match 或代理节点，而不是 DIRECT"
  - "只希望让一个目标直连，不能关闭全局翻墙"
tags: [openclash, direct-rule, rdp, nat, office-network, troubleshooting]
related_components: [us_openai_api_proxy, openwrt]
---

# 办公室 OpenClash 单目标直连（境外 RDP/远程访问）

## Context

办公室 WiFi（FZH-5G）客户端的流量路径：客户端 → 新华三 → OpenWrt/OpenClash → 代理节点 → 目标。直连光猫的客户端完全绕过 OpenClash。因此「直连光猫能通、WiFi 不通」的第一嫌疑是 OpenClash 把目标送进了代理。

2026-10-27 的一例：同事访问某境外 Windows Server 的 RDP（3389）。直连光猫正常，WiFi 失败。排查结果：

- WiFi 客户端出口是代理节点，不是办公室直连 IP；
- ICMP 通；TCP 端口在 tproxy 下显示 OPEN，但这是本地握手，不能证明上游可达；
- HTTP 80 端到端 200，说明主机在线；
- RDP X.224 协商返回 0 字节，SSH banner 超时；
- OpenClash 日志：`[TCP] ... --> <TARGET_IP>:3389 match Match using <PROXY_NODE>`。

根因不是信号/端口，而是目标落到最后的 `Match`，被送进代理节点；远端只对办公室出口 IP 放行 RDP（或该代理路径不可用）。HTTP 对公网开放，造成「主机在线但远程连不上」的错觉。

## Guidance

在 OpenClash 自定义规则文件（路由器上的 `.../custom/openclash_custom_rules.list`）中，在最终 `MATCH` 之前加入目标直连规则：

```yaml
# 单目标直连：<TARGET_HOST>（业务系统路由例外）
- IP-CIDR,<TARGET_IP>/32,DIRECT
```

- 目标是域名时用 `- DOMAIN-SUFFIX,<TARGET_DOMAIN>,DIRECT`；域名解析到多个 IP 时优先用域名规则。
- `/32` 覆盖该主机的所有端口；如只需单端口，可在内核支持时用 `DST-PORT` 组合。
- **不要切全局直连模式**；只加目标级规则，其他流量继续走代理。
- 改前备份自定义规则文件，改后重启 OpenClash 使其生效。

### 排查顺序

1. WiFi 客户端确认出口：`curl -s https://api.ipify.org`。返回代理节点 IP → 流量在代理里。
2. 路由器看日志：`grep "<TARGET_IP>" /tmp/openclash.log | tail`，确认 `match ... using <PROXY/GROUP>`。
3. 用目标协议做端到端验证；不要只信 TCP 端口 OPEN（tproxy 本地握手会假阳性）。
4. 加最小 DIRECT 规则 → 备份 → 重启 OpenClash。
5. 复查日志应出现 `match IP-CIDR(...) using DIRECT`；再验证目标协议与普通翻墙都不受影响。

## Why This Matters

- 目标级 DIRECT 恢复办公室直连出口 IP，满足远端 IP 白名单，同时不牺牲全局代理。
- 规则只影响一台目标，爆炸半径小；比关闭全局翻墙或改网络拓扑安全得多。
- 多级 NAT 下 OpenClash 只看到新华三 WAN IP，无法按单台客户端隔离；因此规则是「目标级、对全办公室生效」，变更前需确认影响范围。

## When to Apply

- 单个境外主机/业务系统在 WiFi 下不通、直连光猫正常；
- OpenClash 日志显示目标落到默认 `Match` 或错误的代理组；
- 目标是固定 IP 或固定域名，且远端可能做 IP 白名单/端口限制。

## Examples

```bash
# 1) 在 WiFi 客户端确认出口（代理节点 IP ≠ 办公室直连 IP）
curl -s https://api.ipify.org

# 2) 在路由器上确认目标实际匹配的规则/节点
ssh <OPENWRT_SSH_ALIAS>
grep "<TARGET_IP>" /tmp/openclash.log | tail

# 3) 备份自定义规则文件
cp -a <RULES_FILE> <RULES_FILE>.bak-$(date +%Y%m%d-%H%M%S)

# 4) 加入目标直连规则后重启 OpenClash
/etc/init.d/openclash restart

# 5) 复查：应出现 using DIRECT，而不是代理节点
grep "<TARGET_IP>" /tmp/openclash.log | tail
```

验收标准：

- 目标协议真实可用（RDP 应返回 X.224 协商响应；不要只看端口 OPEN）；
- HTTP/业务回归正常；
- 普通翻墙出口仍是节点 IP，未被切成直连；
- 日志显示 `using DIRECT`；
- 路由器/OpenClash 定时重启后规则仍生效。

## Constraints

- **共用路由器**：规则对所有办公室客户端生效；多级 NAT 下无法按单台设备隔离。
- **远端仍可能失败**：若加 DIRECT 后仍不通，检查远端防火墙/IP 白名单是否包含当前办公室公网 IP，或 RDP/SSH 服务本身是否正常。
- **目标 IP 会变**：Vultr 等云主机重装/换 IP 后规则失效；有域名时优先用域名规则。
- **不要用全局模式兜底**：关闭全局翻墙会影响所有人；目标级规则是更小的改动。

## Related Issues

- [adobe-genuine-prompts-office-openclash.md](adobe-genuine-prompts-office-openclash.md) — 同一自定义规则文件的 REJECT 用法；多级 NAT 无法按设备隔离的实测。
- [../architecture-patterns/office-egress-fallback-chain.md](../architecture-patterns/office-egress-fallback-chain.md) — 办公室出口链路与「现在走哪条线」的定界方法。
- `us_openai_api_proxy/docs/office-lan-access.md` — 办公室拓扑与 OpenClash 共存说明。
- `us_openai_api_proxy/docs/lessons/lessons-learned.md` Lesson 12 — 路由例外必须最小化且经授权。

## 本次记录

- 2026-10-27：为某境外 Windows Server 的 RDP 访问加入 `/32 → DIRECT` 规则；备份后重启 OpenClash。验证 RDP X.224 协商恢复、HTTP 200、普通代理出口不变。实际目标 IP 只保留在受控路由器配置，不写入公开仓库。
