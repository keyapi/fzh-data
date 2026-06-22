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
| Tailscale 组网 | ✅ P2P 直连可行，DERP relay 兜底 (~260ms) |
| CLIProxyAPI 部署位置 | ⚠️ 已放弃 Windows Server，待迁移至 Ubuntu 24.04 |
| ChatGPT OAuth | ✅ `fzhselleruse@gmail.com` 免费账号已验证，待换付费 |
| 端到端 API | ✅ 北京→Vultr→ChatGPT 对话成功 |
| ChatGPT 付费账号 | ⚠️ 免费账号限额严重，待获取 Plus/Pro/Team |
| LAN 网关（同事接入） | ✅ 网关 PC 跑 `lite_lan_proxy.py` :3000 → 同事无需装 Tailscale |
| 开机自启 | ⚠️ 待在新 Ubuntu 上用 systemd 实现 |

## 为什么放弃 Windows Server

1. **多用户 RDP 冲突**：Tailscale GUI socket 被第一个登录的用户独占，其他人无法使用 `tailscale` CLI
2. **重启后 CLIProxyAPI 丢失**：NSSM 注册 Windows Service 失败，每次重启需手动启动
3. **4GB 内存 95% 占用**：共享机器，同事 RDP 操作 Amazon 消耗大部分资源

## 新部署目标

| 项目 | 值 |
|------|-----|
| 系统 | Ubuntu 24.04 |
| 配置 | 1C2G |
| 位置 | 美国 |
| 方案 | Tailscale + CLIProxyAPI (Linux binary) + systemd 自动重启 |

## 架构

```
北京 (Tailscale) ──P2P/DERP──→ US Ubuntu Server (Tailscale)
  fzhpc13                         └─ CLIProxyAPI :8317 (systemd)
  └─ LAN 网关 :3000 ──→ 同事 PC   └─ ChatGPT OAuth
```

## 新部署步骤（待执行）

### 1. Ubuntu 基础环境
```bash
# 安装 Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# 验证
tailscale status
```

### 2. CLIProxyAPI 部署
```bash
# 下载 Linux 版
wget https://github.com/router-for-me/CLIProxyAPI/releases/download/v7.2.16/CLIProxyAPI_7.2.16_linux_amd64.tar.gz
tar -xzf CLIProxyAPI_7.2.16_linux_amd64.tar.gz
chmod +x CLIProxyAPI

# 创建配置（API key 等从 .env 取）
mkdir -p ~/.cli-proxy-api
cat > config.yaml << 'EOF'
host: "<TAILSCALE_IP>"
port: 8317
remote-management:
  allow-remote: true
  secret-key: "<SECRET_KEY>"
auth-dir: "/home/<USER>/.cli-proxy-api"
api-keys:
  - "<API_KEY>"
debug: false
request-retry: 3
quota-exceeded:
  switch-project: true
  switch-preview-model: true
EOF
```

### 3. OAuth 登录（Ubuntu 无桌面）
```bash
# 使用本地偷渡法：
# 1. 在本地电脑下载 CLIProxyAPI → 运行 --codex-login → 浏览器完成 OAuth
# 2. 将生成的 auth/ 文件夹 scp 到 Ubuntu 服务器
# 3. 或者使用 SSH 端口转发：
ssh -L 1455:localhost:1455 user@<UBUNTU_IP>
./CLIProxyAPI --codex-login
# 在本地浏览器打开输出的 URL 完成授权
```

### 4. systemd 开机自启
```ini
# /etc/systemd/system/cliproxyapi.service
[Unit]
Description=CLIProxyAPI Service
After=network.target tailscaled.service

[Service]
Type=simple
WorkingDirectory=/opt/cliproxyapi
ExecStart=/opt/cliproxyapi/CLIProxyAPI
Restart=always
RestartSec=10
User=<USER>

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cliproxyapi
```

### 5. 客户端接入
- Codex++：供应商配置 → Base URL `http://<TAILSCALE_IP>:8317/v1`
- LAN 网关：参考 `tools/lite_lan_proxy.py`

## 日常运维

### 检查 Tailscale
```bash
tailscale status
tailscale ping <PEER_IP>
```

### 检查 CLIProxyAPI
```bash
curl http://localhost:8317/v1/models -H "Authorization: Bearer <API_KEY>"
sudo systemctl status cliproxyapi
sudo journalctl -u cliproxyapi -f
```

### 重新登录 ChatGPT（换账号）
```bash
# 用 SSH 端口转发方式
ssh -L 1455:localhost:1455 user@<UBUNTU_IP>
# 停服务
sudo systemctl stop cliproxyapi
# OAuth 登录
cd /opt/cliproxyapi && ./CLIProxyAPI --codex-login
# 完成后 Ctrl+C，重启服务
sudo systemctl start cliproxyapi
```

## 敏感信息

所有机密值不写入本文档：
- `secret-key`：config.yaml 中管理面板密钥
- `api-keys`：客户端调用密钥
- `auth/` 目录：ChatGPT OAuth 凭证
- 实际 IP → `.env` 中记录（gitignore）

## 待办

1. **在新 Ubuntu 上部署 Tailscale + CLIProxyAPI**（当前）
2. **获取 ChatGPT 付费账号**（阻塞中）
3. 配置 systemd 开机自启
4. Claude Desktop / Codex Desktop 端到端验证
5. USTX 实体电脑 Tailscale + RDP（Y 同事远程桌面）
6. (可选) new-api 多用户权限管理

## 相关资源

| 资源 | 链接 |
|------|------|
| CLIProxyAPI GitHub | https://github.com/router-for-me/CLIProxyAPI |
| CLIProxyAPI 文档 | https://help.router-for.me/ |
| Tailscale 下载 | https://tailscale.com/download |
| Tailscale Linux 安装 | `curl -fsSL https://tailscale.com/install.sh \| sh` |

## 见也

- [README.md](./README.md) — 人读概述
- [docs/architecture.md](./docs/architecture.md) — 架构详解
- [docs/log.md](./docs/log.md) — 变更日志
- [docs/lessons/lessons-learned.md](./docs/lessons/lessons-learned.md) — 经验教训（15 条）
- [docs/lan-gateway.md](./docs/lan-gateway.md) — LAN 网关部署
