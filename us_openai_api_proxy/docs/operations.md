---
okf: v0.1
type: HowTo
title: 运维手册
description: US AI Proxy 服务器日常运维操作指南
tags: [operations, monitoring, health-check, ssh]
---
# 运维手册

## 快速登录

```bash
# 管理员 (root)
ssh us-ubuntu-proxy

# 运维同事 (gq-agent, 有限权限)
ssh gq-agent@<UBUNTU_PUBLIC_IP>
```

## 服务检查

### 手动检查
```bash
# 服务状态
ssh us-ubuntu-proxy systemctl status cliproxyapi

# 查看实时日志
ssh us-ubuntu-proxy journalctl -u cliproxyapi -f

# 查看健康检查日志
ssh us-ubuntu-proxy tail -20 /var/log/cliproxy-health.log

# API 快速测试 (从北京)
curl -s --max-time 10 http://<TAILSCALE_IP>:8317/v1/models \
  -H "Authorization: Bearer <API_KEY>" | head -50
```

### 自动检查
- cron 每 5 分钟跑 `/opt/cliproxyapi/health_check.sh`
- 检查项: systemd 是否 active + API 端口是否响应
- 日志: `/var/log/cliproxy-health.log`

## 服务重启

```bash
ssh us-ubuntu-proxy systemctl restart cliproxyapi
```

systemd 配置了 `Restart=always`，崩溃自动重启，无需手动干预。

## 重新登录 ChatGPT OAuth (换账号时)

```bash
# 1. 在北京开 SSH 隧道 (新窗口, 保持不关)
ssh -L 1455:127.0.0.1:1455 -D 1080 us-ubuntu-proxy

# 2. 停服务
ssh us-ubuntu-proxy systemctl stop cliproxyapi

# 3. 启动 OAuth 登录
ssh us-ubuntu-proxy /opt/cliproxyapi/cli-proxy-api --codex-login

# 4. 在北京 Chrome (SOCKS 代理 localhost:1080) 打开输出的 URL
# 5. 完成后 Ctrl+C, 启动服务
ssh us-ubuntu-proxy systemctl start cliproxyapi
```

## 添加同事 Agent 访问 (gq-agent)

```bash
# 管理员执行:
ssh us-ubuntu-proxy "
  adduser --disabled-password gq-agent
  mkdir -p ~gq-agent/.ssh
  echo '<GQ_PUBKEY>' >> ~gq-agent/.ssh/authorized_keys
  chmod 700 ~gq-agent/.ssh
  chmod 600 ~gq-agent/.ssh/authorized_keys
  chown -R gq-agent:gq-agent ~gq-agent/.ssh
"
```

sudo 权限在 `/etc/sudoers.d/gq-agent`:
```
gq-agent ALL=(root) NOPASSWD: /bin/systemctl status cliproxyapi
gq-agent ALL=(root) NOPASSWD: /bin/systemctl restart cliproxyapi
gq-agent ALL=(root) NOPASSWD: /bin/journalctl -u cliproxyapi *
```

## 磁盘/资源检查

```bash
ssh us-ubuntu-proxy "
  echo '=== Disk ===' && df -h /
  echo '=== Memory ===' && free -h
  echo '=== CPU ===' && uptime
  echo '=== Service ===' && systemctl status cliproxyapi --no-pager | head -5
"
```

## 告警

当前无自动告警。可配置:
- **Telegram Bot**: 健康检查连续失败 3 次 → 发 Telegram 消息
- **邮件**: `mail` 命令发送到管理员邮箱

待后续实施。

## 见也

- [../AGENT_HANDOFF.md](../AGENT_HANDOFF.md) — Agent 参考
- [architecture.md](architecture.md) — 架构设计
- [lessons/lessons-learned.md](lessons/lessons-learned.md) — 经验教训
