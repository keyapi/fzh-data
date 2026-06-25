---
okf: v0.1
type: Log
title: 变更日志
description: US OpenAI API Proxy 模块的时序变更记录
tags: [openai, api-proxy, changelog]
---
# 变更日志

## 2026-06-25 (v0.11)

- **v0.11**: 方案 A (Tailscale Funnel): `tailscale funnel --bg 3000` → 公网 HTTPS URL, 零配置, ~300ms 延迟
- **v0.11**: 方案 B (nginx HTTPS 反代): `api.vilavi.cn` → nginx 443 反代 127.0.0.1:3000, Let's Encrypt 证书, ~30ms 延迟
- **v0.11**: ERPNext 零影响 (nginx SNI 多域名共存, 未改 frappe-bench.conf)
- **v0.11**: 安全加固: `RegisterEnabled=false` (关闭公开注册), 管理员后台手动创建用户
- **v0.11**: 推荐 API 用户用方案 B (`https://api.vilavi.cn`), 方案 A 作为兜底
- **v0.11**: DNS 小插曲: OpenClash 缓存了新域名的 NXDOMAIN, 重启 OpenClash 后自动恢复, 无需额外配置

## 2026-06-25 (v0.12)

- **v0.12**: Lesson 29 — new-api 钉钉 OAuth 登录可行性调研 (new-api 原生不支持, 需 OIDC 桥接代理)
- **v0.12**: 调研记录: 钉钉 OAuth 端点/参数/限制方案/离职撤销, 参考链接见 Lesson 29

## 2026-06-24 (v0.9)

- **v0.9**: 钉钉视频会议卡顿修复 — 开启 OpenClash "绕过中国大陆IP" + 添加钉钉域名 DIRECT 规则
- **v0.9**: 根因: `china_ip_route=0` (关闭) 导致国内 IP 的 UDP 流量被 TPROXY 劫持进 Clash 内核, 代理节点 UDP 转发性能差
- **v0.9**: 修复: `china_ip_route=1` (开启) → iptables 层面 RETURN 国内 IP 流量, 不进 Clash 内核
- **v0.9**: 双重保险: 覆写规则添加 5 条钉钉域名 DIRECT 规则 (dingtalk.com/dingtalk.cn/dingtalkapps.com/alicdn.com/KEYWORD:dingtalk)
- **v0.9**: 效果: NAT TCP 254 pkts RETURN vs 188 REDIRECT, MANGLE UDP 471 pkts RETURN vs 73 TPROXY
- **v0.9**: 不影响翻墙: 非国内 IP 流量仍正常进 Clash 代理

## 2026-06-23 (v0.8)

- **v0.8**: Tailscale 安全升级 v1.32.3 → v1.98.4 (手动静态二进制替换, arm64)
- **v0.8**: 验证新版 iptables 规则 — ts-forward MARK 方向未变化, 手工 MASQUERADE 仍需保留
- **v0.8**: 升级后重新认证, 所有节点正常, 手机 new-api + 翻墙正常

## 2026-06-23 (v0.7)

- **v0.7**: 方案 A 实施完成 — 办公室全员可通过路由器访问 Tailscale 网络
- **v0.7**: OpenWrt R68S 安装 Tailscale v1.32.3 + 防火墙 zone 配置 + LAN↔tailscale 转发
- **v0.7**: 关键修复: MASQUERADE on tailscale0 (ts-forward MARK 只匹配入站，出站无 SNAT)
- **v0.7**: 回程路由: 192.168.10.0/24 via 192.168.100.181 (新华三 LAN 子网)
- **v0.7**: 新华三 ER3208G3-P-E 静态路由: 100.64.0.0/10 → 192.168.100.1 (WAN1)
- **v0.7**: 验证通过: 手机 (无 Tailscale) 访问 new-api + 翻墙均正常
- **v0.7**: 踩坑 5 条: 防火墙冲掉 iptables / MARK 方向 / 三层 NAT 回程 / 新华三 LuCI 混淆 / Hash 路由

## 2026-06-23 (v0.6)

- **v0.6**: 新增 `docs/office-lan-access.md` — 办公室全员访问 Tailscale 5 种方案全景 (OpenWrt/PC网关/公网/全员Tailscale/Subnet Router)
- **v0.6**: 方案 A (OpenWrt 路由器) 详细部署步骤 — 当前优先级最高

## 2026-06-22 (v0.5)

- **v0.5**: Lesson 25 — docker-compose 必须自包含 (漏 SQL_DSN → 降级 SQLite), 必须从官方 compose 出发
- **v0.5**: Lesson 26 — Docker bridge 无法访问宿主机 Tailscale (经典冲突, iptables MASQUERADE 修复, 附 5 个社区链接)

- **v0.5**: 上海 ERPNext 测试服务器加入 Tailscale (100.119.28.72)
- **v0.5**: Docker v29.1.3 安装 (DaoCloud 镜像, 清华 apt 源)
- **v0.5**: new-api Docker 部署 (MySQL 8.0 + Redis 7 + calciumion/new-api, 端口 3000)
- **v0.5**: 上海 Tailscale 延迟优化 — 启用 Peer Relays (`--relay-server-port 3478`)
- **v0.5**: Lesson 20-24 — Tailscale MagicDNS / shim-signed / 阿里云镜像 / Docker 代理 / 国内 Tailscale 延迟
- **v0.5**: sh-agent 用户创建 + 用户权限体系确立
- **v0.5**: 上海 SSH config: `ssh sh-erpnext-test`

## 2026-06-22 (v0.4)

- **v0.4**: 迁移至 Ubuntu 24.04 (1C2G) — 放弃 Windows Server，新开 Vultr Ubuntu
- **v0.4**: systemd 部署 + 健康检查 cron + SSH SOCKS OAuth
- **v0.4**: Lesson 16-19

## 2026-06-18 (v0.3)

- **v0.3**: 放弃 Windows Server（多用户 RDP 冲突 + NSSM 失败）
- **v0.3**: Lesson 10-15

## 2026-06-18 (v0.2)

- **v0.2**: LAN 网关部署 + ping != TCP 端口通
- **v0.2**: Lesson 8-9

## 2026-06-18 (v0.1)

- **v0.1**: 初始搭建 — Tailscale P2P 直连、CLIProxyAPI v7.2.16、OKF 文档骨架
- **v0.1**: Lesson 1-7
