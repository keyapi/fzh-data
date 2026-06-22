---
okf: v0.1
type: Handoff
title: US OpenAI API Proxy — Agent 接手参考
description: 新 Agent 或新对话接手时的高频信息 + 导航
tags: [openai, api-proxy, tailscale, handoff]
---
# US OpenAI API Proxy — Agent 接手参考

> 本文档让新 Agent 或新对话在最少 token 内了解模块状态并继续工作。

## 当前状态

| 项目 | 状态 |
|------|------|
| 部署位置 | ✅ Ubuntu 24.04 (1C2G, Vultr US) |
| Tailscale 组网 | ✅ P2P 直连 ~215ms, DERP 兜底 |
| CLIProxyAPI | ✅ v7.2.16, systemd 开机自启 |
| ChatGPT OAuth | ✅ `fzhvickyjing@gmail.com` (免费) |
| 健康检查 | ✅ cron 每 5 分钟 |
| ChatGPT 付费账号 | ⚠️ 待获取 Plus/Pro/Team |
| LAN 网关 | ✅ 同事通过网关 PC :3000 接入 |
| 告警通知 | ⏳ 待配置 Telegram Bot |
| gq-agent 用户 | ⏳ 待 GQ 提供公钥 |
| Y 远程桌面 | ⏳ USTX 实体电脑 Tailscale + RDP |

## 架构

```
北京办公室 (Tailscale)                      美国
  ├─ fzhpc13                                 Ubuntu 24.04 (vultr)
  │   └─ Codex++ ────P2P/DERP─→              ├─ Tailscale (系统级)
  │                                         └─ CLIProxyAPI (systemd :8317)
  │                                             └─ ChatGPT OAuth
  └─ LAN 网关 :3000 → 同事 PC
```

## 服务器信息

> ⚠️ 所有 IP/密钥的真实值在 `.env`（gitignored），此处仅用占位符。

| 项目 | 占位符 | 来源 |
|------|--------|------|
| SSH 登录 | `ssh us-ubuntu-proxy` | `~/.ssh/config` |
| 公网 IP | `<UBUNTU_PUBLIC_IP>` | `.env` |
| Tailscale IP | `<UBUNTU_TAILSCALE_IP>` | `.env` |
| API Key | `<API_KEY>` | `.env` |
| OAuth 账号 | `<CHATGPT_OAUTH_EMAIL>` | `.env` |

## 日常运维

### 快速登录
```bash
ssh us-ubuntu-proxy
```

### 检查服务
```bash
# 一键
ssh us-ubuntu-proxy systemctl status cliproxyapi

# 看日志
ssh us-ubuntu-proxy journalctl -u cliproxyapi -f

# 健康检查日志
ssh us-ubuntu-proxy tail -20 /var/log/cliproxy-health.log
```

### 重启服务
```bash
ssh us-ubuntu-proxy systemctl restart cliproxyapi
```

> systemd 配置了 `Restart=always`，崩溃自愈。

### 测试 API
```bash
# 从北京
curl -s http://<TAILSCALE_IP>:8317/v1/models \
  -H "Authorization: Bearer <API_KEY>"
```

### 换 ChatGPT 账号 (OAuth)
```bash
# 1. 在北京开 SOCKS 隧道 (新 Terminal 窗口):
ssh -L 1455:127.0.0.1:1455 -D 1080 us-ubuntu-proxy

# 2. 停服务:
ssh us-ubuntu-proxy systemctl stop cliproxyapi

# 3. 启动 OAuth:
ssh us-ubuntu-proxy /opt/cliproxyapi/cli-proxy-api --codex-login

# 4. 在北京 Chrome (SOCKS proxy localhost:1080) 打开输出的 URL
# 5. 完成后 Ctrl+C, 重启:
ssh us-ubuntu-proxy systemctl start cliproxyapi
```

### 查看 Tailscale 网络
```bash
ssh us-ubuntu-proxy tailscale status
```

## 服务器文件路径

| 路径 | 说明 |
|------|------|
| `/opt/cliproxyapi/cli-proxy-api` | 主程序 |
| `/opt/cliproxyapi/config.yaml` | 配置 (监听 Tailscale IP) |
| `/opt/cliproxyapi/auth/` | OAuth 凭证 |
| `/opt/cliproxyapi/health_check.sh` | 健康检查脚本 |
| `/etc/systemd/system/cliproxyapi.service` | systemd unit |
| `/var/log/cliproxy-health.log` | 健康检查日志 |

## 客户端接入

### Codex++ (北京)
- Base URL: `http://<TAILSCALE_IP>:8317/v1`
- API Key: `<API_KEY>`
- 上游协议: Chat Completions

### 同事通过 LAN 网关
- Base URL: `http://<GATEWAY_IP>:3000/v1`
- API Key: 同上

## 同事 Agent 接入

1. GQ 生成 `ssh-keygen -t ed25519 -f id_ed25519_us_proxy`
2. 管理员添加: 见 [docs/operations.md](docs/operations.md)
3. GQ 的 `~/.ssh/config`:
```
Host us-ubuntu-proxy
    HostName <UBUNTU_PUBLIC_IP>
    User gq-agent
    IdentityFile ~/.ssh/id_ed25519_us_proxy
```

## 待办

1. **获取 ChatGPT 付费账号**（当前阻塞）
2. 告警通知 (Telegram Bot)
3. GQ Agent 接入 (等他提供公钥)
4. Y 远程桌面 (USTX 实体电脑)
5. (可选) new-api 多用户权限管理

## 见也

- [README.md](./README.md) — 人读概述
- [docs/architecture.md](./docs/architecture.md) — 架构设计 + 决策理由
- [docs/operations.md](./docs/operations.md) — 运维手册
- [docs/log.md](./docs/log.md) — 变更日志
- [docs/lessons/lessons-learned.md](./docs/lessons/lessons-learned.md) — 19 条经验教训
- [docs/lan-gateway.md](./docs/lan-gateway.md) — LAN 网关部署
