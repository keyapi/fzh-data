---
okf: v0.1
type: Reference
title: 共享出口 VPS 上新服务用 venv+systemd，不装 Docker（iptables 风险）
date: 2026-10-28
category: architecture-patterns
module: wayfair-api-proxy
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "要在承载 Tailscale/CLIProxyAPI 应急出口的 VPS 上新增服务"
  - "考虑用 Docker 部署，但该机的网络规则不能被扰动"
tags: [vps, systemd, docker, iptables, tailscale, deployment]
---

# 共享出口 VPS 上新服务用 venv+systemd，不装 Docker

## Context

美国 Vultr 同时承载 CLIProxyAPI（监听 Tailscale IP:8317）和北京办公室 OpenClash
的应急 AI 出口。新服务需要长期运行、只能本机访问，并要能随时回滚。Docker 是最常见
的部署方式，但这台机器不能承受网络规则变化。

## Guidance

- 选择 **Python venv + systemd**：服务绑定 `127.0.0.1`，只新增一个本地监听；
- **不要在这台机器上安装 Docker**：安装/启动 Docker daemon 会写 iptables/NAT，
  可能影响既有 Tailscale 转发、出口节点和 CLIProxyAPI 的可达性；
- 部署前后都验证：
  - `systemctl is-active cliproxyapi tailscaled`
  - `ss -lnt` 确认 8317 仍在、只新增目标端口
  - 服务监听地址是 `127.0.0.1`，不是 `0.0.0.0`
- systemd 单元做最小权限：专用系统用户、`NoNewPrivileges`、`ProtectSystem=strict`、
  `ReadWritePaths` 只给数据目录、`CapabilityBoundingSet=` 清空；
- uvicorn 用 `--no-access-log`，请求日志由应用中间件统一记录（避免 query 泄漏）；
- 公网/同事访问不要直接暴露应用端口：走 Nginx HTTPS 或 Tailscale，应用端口保持本地。

## Why This Matters

Docker 的网络副作用是**全局**的，不是“只影响新容器”。在一台同时提供应急出口的机器上，
一次 Docker 安装就可能改变 NAT/转发行为，故障面远大于一个业务服务本身。
venv+systemd 的改动面是可枚举的：一个目录、一个用户、一个 unit、一个 localhost 监听。

## When to Apply

- 共享 VPS 上有 Tailscale exit node、代理、跳板或其它网络关键服务；
- 新服务只需要被本机或少数客户端访问；
- 需要可预测的回滚路径（停 unit、换目录）。

## Examples

```ini
[Service]
User=wayfair
WorkingDirectory=/opt/wayfair-api-proxy
EnvironmentFile=/etc/wayfair-api-proxy/env
ExecStart=/opt/wayfair-api-proxy/.venv/bin/uvicorn \
  main:create_runtime_app --factory --host 127.0.0.1 --port 8410 \
  --log-level info --no-access-log
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/srv/wayfair-api-proxy/data
```

验收：

```bash
curl -fsS http://127.0.0.1:8410/health
systemctl is-active cliproxyapi tailscaled
ss -lnt | grep -E ':(8317|8410)\b'
```

## Related

- `wayfair-api-proxy/docs/operations.md` — 部署、回滚、secret 轮换
- `docs/solutions/architecture-patterns/office-egress-fallback-chain.md` — 出口链路背景
