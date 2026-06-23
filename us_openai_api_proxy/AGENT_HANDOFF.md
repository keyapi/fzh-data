---
okf: v0.1
type: Handoff
title: US OpenAI API Proxy — Agent 接手参考
description: 新 Agent 或新对话接手时的高频信息 + 导航, 含 US + 上海双节点架构
tags: [openai, api-proxy, tailscale, handoff, new-api]
---
# US OpenAI API Proxy — Agent 接手参考

> 本文档让新 Agent 或新对话在最少 token 内了解模块状态并继续工作。

## 架构总览 (v0.5)

```
                          Tailscale 虚拟网络
    ┌──────────────────────────────────────────────────┐
    │                                                  │
    │  北京                    上海                      美国
    │  ┌──────────┐    ┌──────────────────┐    ┌──────────────┐
    │  │ fzhpc13   │    │ sh-erpnext-test  │    │ us-ubuntu    │
    │  │ LAN网关   │    │ new-api :3000    │    │ CLIProxyAPI  │
    │  │  :3000   │    │ ┌──────────────┐ │    │ :8317        │
    │  │          │    │ │ DeepSeek 直连 │ │    │ ChatGPT OAuth│
    │  └──────────┘    │ │ OpenAI → US  │─┼────→              │
    │                  │ └──────────────┘ │    └──────────────┘
    │  同事 PC         └──────────────────┘
    │   ↓ HTTP
    │  LAN网关 :3000 或 new-api :3000
    └──────────────────────────────────────────────────┘
```

## 服务器清单

> ⚠️ 真实 IP/密钥在 `.env`（gitignored），文档仅用占位符。

| 机器 | SSH | Tailscale IP | 角色 |
|------|-----|-------------|------|
| US Ubuntu | `ssh us-ubuntu-proxy` | `<US_TS_IP>` | CLIProxyAPI (ChatGPT → API) |
| 上海测试 | `ssh sh-erpnext-test` | `<SH_TS_IP>` | new-api (API 分发中心) |
| 北京办公 | — | `<BJ_TS_IP>` | LAN 网关 + 开发 |

## 上海 new-api 运维

### 服务检查
```bash
ssh sh-erpnext-test "
  cd /opt/new-api && docker compose ps
  docker stats --no-stream
"
```

### 重启
```bash
ssh sh-erpnext-test "cd /opt/new-api && docker compose restart new-api"
```

### new-api Web UI
- 地址: `http://<SH_TAILSCALE_IP>:3000` (Tailscale 内网)
- 待初始化: 管理员账号 + 渠道配置 + API Key 分发

## US Ubuntu CLIProxyAPI 运维

### 快速登录
```bash
ssh us-ubuntu-proxy
```

### 检查服务
```bash
ssh us-ubuntu-proxy systemctl status cliproxyapi
ssh us-ubuntu-proxy tail -20 /var/log/cliproxy-health.log
```

### 重启
```bash
ssh us-ubuntu-proxy systemctl restart cliproxyapi
```

### 换 ChatGPT 账号 (SSH SOCKS OAuth)
```bash
# 北京新 Terminal: SSH 隧道
ssh -L 1455:127.0.0.1:1455 -D 1080 us-ubuntu-proxy

# 停服务 → OAuth 登录 → 重启
ssh us-ubuntu-proxy systemctl stop cliproxyapi
ssh us-ubuntu-proxy /opt/cliproxyapi/cli-proxy-api --codex-login
# Chrome SOCKS localhost:1080 打开输出的 URL
ssh us-ubuntu-proxy systemctl start cliproxyapi
```

## 用户权限

| 服务器 | 管理员 (你) | 运维 (GQ) | Agent |
|--------|-----------|----------|-------|
| US Ubuntu | root | gq-agent | — |
| 上海测试 | root / frappe | dev01 (已有) | sh-agent |

## 关键文件路径

### US Ubuntu
| 路径 | 说明 |
|------|------|
| `/opt/cliproxyapi/` | CLIProxyAPI 目录 |
| `/opt/cliproxyapi/config.yaml` | 配置 (监听 Tailscale IP) |
| `/opt/cliproxyapi/health_check.sh` | 健康检查脚本 |
| `/etc/systemd/system/cliproxyapi.service` | systemd unit |

### 上海测试
| 路径 | 说明 |
|------|------|
| `/opt/new-api/docker-compose.yml` | new-api Docker 编排 |
| `/opt/new-api/data/` | new-api 数据 |
| `/opt/new-api/mysql/` | MySQL 数据卷 |
| `/opt/new-api/redis/` | Redis 数据卷 |
| `/etc/iptables/rules.v4` | iptables 持久化 (含 Tailscale NAT) |

## 国内部署注意 (Lesson 20-26)

1. Tailscale 务必 `--accept-dns=false`（否则 DNS 挂）
2. Docker 用 DaoCloud 代理拉取（`docker.m.daocloud.io`）
3. apt 备非阿里云镜像源（清华 `mirrors.tuna.tsinghua.edu.cn`）
4. shim-signed GRUB 交互提示需 `debconf-set-selections` 修复
5. 国内 Tailscale P2P 可能失败，DERP relay 兜底
6. Docker bridge 容器无法直接访问 Tailscale IP — 需 iptables MASQUERADE
   ```bash
   iptables -t nat -I POSTROUTING -s <DOCKER_SUBNET> -o tailscale0 -j MASQUERADE
   netfilter-persistent save   # 持久化
   ```

## 待办

1. **ChatGPT 付费账号**（当前阻塞）
2. new-api 初始化 + 渠道配置 (可交 GQ)
3. new-api 安全加固 (绑 Tailscale IP)
4. **办公室全员 Tailscale 访问** → [docs/office-lan-access.md](./docs/office-lan-access.md) (方案 A 优先)
5. Tailscale 延迟优化 (Peer Relays / 自建 DERP)
6. Telegram/邮件告警

## 见也

- [README.md](./README.md) — 人读概述
- [docs/architecture.md](./docs/architecture.md) — 架构详解
- [docs/operations.md](./docs/operations.md) — 运维手册
- [docs/log.md](./docs/log.md) — 变更日志
- [docs/lessons/lessons-learned.md](./docs/lessons/lessons-learned.md) — 26 条经验教训
- [docs/office-lan-access.md](./docs/office-lan-access.md) — 办公室全员访问 Tailscale (5 方案)
- [docs/lan-gateway.md](./docs/lan-gateway.md) — LAN 网关 (lite_lan_proxy.py)
