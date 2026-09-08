# US OpenAI API Proxy

> 在 US Ubuntu 服务器上部署 CLIProxyAPI，通过受控内网向团队提供 OpenAI 兼容 API。

## 做了什么

部署开源项目 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)，将经授权的
ChatGPT/Codex OAuth 会话代理为标准 OpenAI 兼容接口。服务由 systemd 管理，监听和认证
配置仅保存在受控、gitignored 环境中。

## 为什么这样做

- 将受控的上游授权能力提供为统一 API 接口。
- 内网访问减少服务暴露面。
- systemd 便于运行、观察日志和受控重启。

## 当前状态

| 项目 | 状态 |
|------|------|
| 部署位置 | US Ubuntu（systemd） |
| 网络 | 受控内网访问；实际地址不入库 |
| 软件 | CLIProxyAPI v7.2.152 |
| 上游认证 | 工作区 OAuth；真实身份和认证材料不入库 |
| 验收 | 目标模型真实 completion 已验证 |

## 认证与可用性

服务 active 或基础 health check 成功，只能证明进程和基础路径可用；它**不等于**目标模型
已有可用上游授权。出现 `503 auth_unavailable` 时，按
[运维手册](docs/operations.md) 中的升级、浏览器 OAuth、认证记录隔离和目标模型验收流程处理。

## 快速开始

- Agent 接手：[AGENT_HANDOFF.md](AGENT_HANDOFF.md)
- 日常运维：[docs/operations.md](docs/operations.md)
- 已解决故障：[CLIProxyAPI `auth_unavailable` 恢复](../docs/solutions/integration-issues/cliproxyapi-auth-unavailable-oauth-recovery.md)

## 目录

```
us_openai_api_proxy/
├── README.md
├── AGENT_HANDOFF.md
├── .env.example
├── .env                     ← 实际配置（gitignored）
├── .gitignore
├── tools/
└── docs/                    ← OKF v0.1 bundle
    ├── index.md
    ├── log.md
    ├── operations.md
    ├── architecture.md
    ├── lessons/
    └── reference/
```
