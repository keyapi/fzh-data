---
okf: v0.1
type: Reference
title: 办公室 OpenClash 单目标改走代理（直连丢包 / 规则注入顺序）
date: 2026-11-18
category: best-practices
module: us_openai_api_proxy
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - "某境外主机/远程桌面在办公室『能用但很卡』、丢包严重（而不是连不上）"
  - "想把这个目标改走代理，但规则写进自定义规则文件后被跳过"
  - "需要先区分是服务器问题、还是本地出境链路问题"
tags: [openclash, rdp, packet-loss, rule-injection, office-network, troubleshooting]
related_components: [us_openai_api_proxy, openwrt]
---

# 办公室 OpenClash 单目标改走代理

## Context

同事反馈远程桌面（RDP 3389）连某境外 Windows Server 不顺畅：**直连光猫和办公室 WiFi 都一样差**，服务器也已重启过。路由器上早有一条强制直连规则：

```yaml
- IP-CIDR,<TARGET_IP>/32,DIRECT
```

（那条规则的由来见 [openclash-per-target-direct-rule.md](openclash-per-target-direct-rule.md)。）

**关键前提**：直连光猫和 WiFi 其实走**同一条出口**——因为 OpenClash 已把该目标强制 DIRECT。所以「两边都差」并不能证明无解，只证明这条出境路径差；真正没被测过的是「换一条出境路径」。

## Guidance（本学习沉淀的做法）

### 1. 先分清「连不上」和「连得上但质量差」

- **tproxy 下的 TCP connect 是本地假握手**：实测连目标 3389 只要 8ms、12/12 成功，但这只是 Clash 本地接受了连接，不能证明上游可达。
- 用两个东西测真实往返：**ICMP 丢包**（不经 tproxy）+ **应用层握手**（RDP 的 X.224 协商：发 19 字节 Connection Request，期待返回 `03 00 00 13 … d0`）。

### 2. 三方对照定界

在办公室、境外中转 A、境外中转 B 分别 ping / 握手目标，一次就能定界：

| 起点 | 实测 | 结论 |
|---|---|---|
| 办公室 | 40 包 **丢包 45%**，RDP 10 次 7 成功、单次 0.6–6 秒 | 本地出境链路差 |
| 境外中转 A | 60 包 **0% 丢包**，224ms，抖动 0.035ms | 服务器健康 |
| 境外中转 B | 10 包 **0% 丢包**，58ms | 服务器健康 |

服务器两端都干净 ⇒ 重启服务器永远不会解决问题。本次丢包落在「本地 ISP → Cogent」这一段。

### 3. 「走订阅节点」≠「走得通」

必须用**目标协议**做端到端验证，不能只看日志命中了哪个节点：

- 订阅的日本节点、美国节点连目标 3389：**TCP 通，但返回 0 字节**（节点不放行 3389，这类封锁很常见）。
- 自建跳板（境外云主机）正常。

教训：代理组配置正确、日志显示 `using <节点>`，**不代表该节点能承载目标协议**。

### 4. 规则注入顺序（本次最大的坑）

- OpenClash 合并 `openclash_custom_rules.list` 时，会**校验规则目标组/节点是否存在**。
- 由 `openclash_custom_overwrite.sh` 动态创建的组（国家组、`AI 出口`、`Emergency`）在合并阶段**还不存在** → 规则被静默丢弃，日志只有一行：
  `Skiped The Custom Rule Because Group & Proxy Not Found`
- 正确做法：在 overwrite 脚本里用 ruby 把规则 `unshift` 进 `rules` 数组（和现有 AI 规则同一写法，**幂等**，重启/订阅重生成都会重新注入）。
- 若规则引用的是**订阅原始配置里就存在的节点名**（如某国编号节点），则可以直接写在自定义规则文件里。

### 5. 兜底规则要保留

自定义规则里保留 `DIRECT` 作为 fallback：万一脚本注入失败，流量退回直连（慢但能连），而不是落到默认代理——默认代理的节点可能不放行目标协议，会变成**完全连不上**。

### 6. 目标规则别挂 url-test

`自动选择` / `故障转移`（`type: url-test` / `fallback`）会在会话中途换节点，RDP 必断线。用 `select` 组或具体节点，并**钉死**选择。

### 7. 用云主机做中转，先确认计费方式

本次有一条实测最快的线路（每 RTT ~267ms、0 丢包），但该机器**按流量计费**，不适合做长期中转，只能排除。做长期中转优先用固定成本的机器。

## Why This Matters

- 「连得上但卡」和「连不上」是两条完全不同的排查路径；用错判据（TCP 端口 OPEN）会把方向带偏到服务器/防火墙。
- 订阅节点可以「看起来在用」却完全不承载目标协议；只有端到端握手能证伪。
- 注入顺序是**结构性**问题，换组名、换订阅都会再犯；写进 overwrite 脚本才是持久解。

## When to Apply

- 单个境外主机/远程桌面在办公室「能用但体验差」，且换光猫/WiFi 无改善；
- 想为单个目标换出口，但写在自定义规则里的规则不生效；
- 评估「哪条代理线路能承载某个非 HTTP 协议」。

## Examples

幂等注入规则（加在 overwrite 脚本末尾、`exit 0` 之前）：

```ruby
rules = cfg['rules'] || [];
line = 'IP-CIDR,<TARGET_IP>/32,Emergency';
unless rules.any? { |r| r.to_s == line }
  rules.unshift(line);
  File.open('$TARGET', 'w') { |f| YAML.dump(cfg, f) };
end;
```

三层对照验证（UI 看到的 ≠ 运行时生效的）：

```sh
# 1) 自定义规则文件（UI「规则设置」页显示的就是它，可能是兜底 DIRECT）
grep "<TARGET_IP>" /etc/openclash/custom/openclash_custom_rules.list

# 2) 运行配置：注入的规则应在最前面（Clash 从上往下匹配，命中第一条即停）
grep -n "<TARGET_IP>" /etc/openclash/<订阅名>.yaml

# 3) 实际命中
grep "<TARGET_IP>" /tmp/openclash.log | tail
```

验收标准：

- 目标协议端到端可用（RDP 应返回 X.224 协商响应，而不是 0 字节）；
- 通用出口 IP 不变（`curl -s https://api.ipify.org`）；
- 其他业务正常（如一个常用站点返回 200）。

## Constraints

- **共用路由器**：规则对所有办公室客户端生效；多级 NAT 下无法按单台设备隔离。
- 改规则需重启 OpenClash → 全办公室代理中断 10–30 秒，需先取得授权。
- 目标 IP 会变（云主机重装/换 IP 后规则失效）；有域名时优先用域名规则。
- **实际目标 IP、服务器地址、出口 IP 只保留在受控路由器配置，不写入公开仓库。**

## Related Issues

- [openclash-per-target-direct-rule.md](openclash-per-target-direct-rule.md) — 反向场景：需要强制目标直连（远端做 IP 白名单时）
- [../architecture-patterns/office-egress-fallback-chain.md](../architecture-patterns/office-egress-fallback-chain.md) — 三条出口链路与「现在走哪条线」的定界方法
- `us_openai_api_proxy/docs/office-lan-access.md` — 办公室网络拓扑与 OpenClash 共存
- `us_openai_api_proxy/docs/log.md` — 本次变更记录
