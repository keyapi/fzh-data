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
| Tailscale 组网 (北京↔Vultr) | ✅ P2P 直连 ~260ms |
| CLIProxyAPI 部署 (Vultr) | ✅ v7.2.16 运行中，监听 Tailscale IP |
| ChatGPT OAuth | ✅ 免费账号 `fzhselleruse@gmail.com` 已登录 |
| 端到端 API 测试 | ✅ curl 对话成功 |
| ChatGPT 付费账号 | ⚠️ 免费账号限额严重，待获取 Plus/Pro/Team |
| CLIProxyAPI Windows Service | ⏳ 待注册（当前手动启动） |
| Claude Desktop 配置 | ⏳ 待配置 |
| USTX 实体电脑远程桌面 | ⏳ 待装 Tailscale + RDP |

## 架构

```
北京 (Tailscale) ──P2P 252ms──→ US Vultr VM (Tailscale)
  fzhpc13                          vultr-guest
                                   └─ C:\CLIProxyAPI\cli-proxy-api.exe
                                      port 8317, bind Tailscale IP only
                                      auth: codex OAuth → ChatGPT
```

- **不需要 HK 中转**：P2P 打洞成功，无需 DERP relay
- **HK 阿里云不参与**：它是 ERPNext 生产服务器，不能加重负担
- **公网无暴露**：CLIProxyAPI 只监听 Tailscale 虚拟 IP

## 关键文件路径 (Vultr VM)

| 路径 | 说明 |
|------|------|
| `C:\CLIProxyAPI\cli-proxy-api.exe` | 主程序 |
| `C:\CLIProxyAPI\config.yaml` | 配置文件 |
| `C:\CLIProxyAPI\auth\` | OAuth 凭证目录 |
| `C:\CLIProxyAPI\config.example.yaml` | 官方示例配置 |

## 敏感信息

所有机密值在 Vultr VM 本地，不写入本文档：
- `secret-key`：config.yaml 中 `remote-management.secret-key`
- `api-keys`：config.yaml 中 `api-keys[0]`
- Vultr RDP 密码
- 真实 IP 地址 → 见 `.env.example` 占位符，实际值在本地 `.env`

## 日常运维

### 启动 CLIProxyAPI
```powershell
cd C:\CLIProxyAPI
.\cli-proxy-api.exe
```

### 重新登录 ChatGPT（换账号时）
```powershell
cd C:\CLIProxyAPI
.\cli-proxy-api.exe --codex-login
```
浏览器弹出 OAuth 授权，完成后 Ctrl+C 重新正常启动。

### 查看已登录账号
```powershell
ls C:\CLIProxyAPI\auth\
```
文件名格式：`codex-<email>-<tier>.json`

### 检查 Tailscale 状态
```powershell
& "C:\Program Files\Tailscale\tailscale.exe" status
```

### 测试 API（从北京或其他客户端）
```bash
curl http://<VULTR_TAILSCALE_IP>:8317/v1/models \
  -H "Authorization: Bearer <API_KEY>"
```

## 客户端接入

### Claude Desktop
编辑 `%APPDATA%\Claude\claude_desktop_config.json`：
```json
{
  "apiProvider": "openai_compatible",
  "baseURL": "http://<VULTR_TAILSCALE_IP>:8317/v1",
  "apiKey": "<API_KEY>"
}
```

### Codex Desktop
同理，选择 OpenAI Compatible provider。

### new-api（未来多用户管理）
- 等付费账号到位、验证稳定后再部署
- 可部署在 Vultr 同一台机器或 HK 服务器

## 待办清单

1. **获取 ChatGPT Plus/Pro/Team 账号**（当前阻塞）
2. 重新 OAuth 登录付费账号
3. 下载 NSSM，注册 CLIProxyAPI 为 Windows Service
4. 配置 Claude Desktop 端到端验证
5. USTX 实体电脑装 Tailscale，Y 切换 RDP 替代向日葵
6. （可选）new-api 多用户权限管理

## 相关资源

| 资源 | 链接 |
|------|------|
| CLIProxyAPI GitHub | https://github.com/router-for-me/CLIProxyAPI |
| CLIProxyAPI 文档 | https://help.router-for.me/ |
| Tailscale 下载 | https://tailscale.com/download |
| Tailscale 文档 | https://tailscale.com/docs |
| NSSM (Windows Service) | https://nssm.cc/ |
| new-api (多用户管理) | https://github.com/QuantumNous/new-api |

## 见也

- [README.md](./README.md) — 人读概述
- [docs/architecture.md](./docs/architecture.md) — 架构详解
- [docs/log.md](./docs/log.md) — 变更日志
- [docs/lessons/lessons-learned.md](./docs/lessons/lessons-learned.md) — 经验教训
