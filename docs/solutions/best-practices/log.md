---
okf: v0.1
type: Log
title: best-practices — 变更日志
tags: [solutions, best-practices, log]
---

# best-practices 变更日志

## 2026-11-18

- **新增**: `openclash-target-via-proxy-when-direct-degrades.md` — 单个境外目标「连得上但严重丢包」时的处置：先用 ICMP 丢包 + 应用层握手（RDP X.224）确认真实质量，再用办公室/境外两处中转三方对照定界（本次直连 45% 丢包，境外两处 0%）；订阅节点可能不放行目标协议（日本/美国节点连 3389 均返回 0 字节）；自定义规则引用 overwrite 脚本动态创建的组会在合并阶段被丢弃（`Group & Proxy Not Found`），须在脚本里幂等 unshift 注入；保留 DIRECT 兜底，目标规则别挂 url-test。
