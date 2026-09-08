---
okf: v0.1
type: HowTo
title: 运维手册
description: US AI Proxy 的日常检查、授权恢复与安全边界
tags: [operations, monitoring, health-check, ssh, authentication]
---
# 运维手册

## 操作边界

- 本模块服务共享 API 使用者。升级、认证恢复、认证记录隔离、重启或配置修改前，必须取得用户授权。
- 文档、终端回显和 issue 中只用占位符；不得记录账号、OAuth URL 或回调参数、授权码、认证文件名和内容、token、API key、私有地址或完整请求体。
- 真实配置和认证材料仅留在受控服务器与 gitignored 配置中，不上传、不复制到仓库。

## 快速登录与服务检查

```bash
ssh <PROXY_SSH_ALIAS> systemctl status cliproxyapi --no-pager
ssh <PROXY_SSH_ALIAS> journalctl -u cliproxyapi -n 100 --no-pager
ssh <PROXY_SSH_ALIAS> tail -20 <HEALTH_LOG_PATH>
```

自动健康检查可确认进程、监听端口或基础 HTTP 路径是否响应，但**不能证明某个模型可获得上游授权**。

## 诊断 `auth_unavailable`

当调用返回 `503 auth_unavailable` 时：

1. 查看 systemd 状态和服务日志，排除进程退出、网络错误和客户端 API key 错误。
2. 从受控配置确认服务的实际监听地址；不要假设是 `127.0.0.1`。
3. 用最小、脱敏的真实请求调用**发生故障的目标模型**；避免 shell history、日志或截图保留认证头和请求体。
4. 若服务 active 而目标模型仍返回 `auth_unavailable`，按“授权恢复”处理，而非仅反复重启。

验证请求形状仅供说明，地址和认证值必须来自受控配置：

```bash
curl --fail-with-body --max-time 30 \
  "http://<CONFIGURED_LISTENER>/v1/chat/completions" \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  --data '{"model":"<TARGET_MODEL>","messages":[{"role":"user","content":"Reply OK"}],"max_tokens":8}'
```

成功的验收标准是目标模型返回正常 completion，而不是仅返回模型列表或 HTTP 200。

## 授权恢复：升级、浏览器 OAuth 与验证

### 1. 升级前检查与可回滚备份

先检查当前二进制、服务单元和配置位置；将现有可执行文件或发布工件备份到受控路径，并确认可恢复。不要备份或打印认证文件内容。

```bash
ssh <PROXY_SSH_ALIAS> "<PROXY_BINARY> --help | head"
ssh <PROXY_SSH_ALIAS> "systemctl cat cliproxyapi"
ssh <PROXY_SSH_ALIAS> "test -d <AUTH_DIR> && printf 'auth directory exists\n'"
```

按上游发布说明升级后，保留上一版本工件直至真实模型请求通过；升级失败时使用已确认的备份恢复，再重启服务。

### 2. 浏览器 OAuth

若服务器无 GUI，在本地建立 callback 转发，并按需要让浏览器经受控代理访问授权页：

```bash
ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
  -L <LOCAL_CALLBACK_PORT>:127.0.0.1:<SERVER_CALLBACK_PORT> \
  -D <LOCAL_SOCKS_PORT> <PROXY_SSH_ALIAS>
```

在另一受控会话中启动 CLIProxyAPI 的浏览器 OAuth 命令。仅在浏览器中打开该次命令即时输出的授权页，不要把 URL、state、code 或 callback 复制到文档、聊天记录或日志。

- OAuth 会话是短时效的；认证耗时过长或链接失效时，重新生成新会话，不能复用旧链接。
- 设备代码登录可能被工作区管理员策略禁用；出现该限制时不要尝试绕过，改用受支持的浏览器流程。

### 3. 认证记录整理与重启

先仅列出认证目录的元数据，确认哪些条目明确过期或无效；不要输出文件内容。将确认无效的条目移动到受控、可恢复的隔离位置，而不是直接删除。

```bash
ssh <PROXY_SSH_ALIAS> "find <AUTH_DIR> -maxdepth 1 -type f -printf '%f %TY-%Tm-%Td %TH:%TM\n'"
ssh <PROXY_SSH_ALIAS> systemctl restart cliproxyapi
```

重启后立即按上节对目标模型做最小真实请求。成功后再清理到期的隔离备份；失败时恢复隔离条目或升级前工件，并根据日志继续排查。

## 日常重启与资源检查

```bash
ssh <PROXY_SSH_ALIAS> systemctl restart cliproxyapi
ssh <PROXY_SSH_ALIAS> "df -h / && free -h && uptime"
```

`Restart=always` 能恢复进程崩溃，但不能恢复失效、过期或不被目标模型接受的上游授权。

## 相关记录

- [CLIProxyAPI `auth_unavailable`：升级、浏览器 OAuth 与真实模型验收](../../docs/solutions/integration-issues/cliproxyapi-auth-unavailable-oauth-recovery.md)
- [经验教训](lessons/lessons-learned.md)
- [Agent 接手入口](../AGENT_HANDOFF.md)
