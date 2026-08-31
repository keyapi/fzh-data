# sellfox-api-proxy

赛狐（及其他非 LLM）API 代理网关。解决赛狐 API 的 IP 白名单限制 + 凭证安全分发问题。

## 为什么需要

- 赛狐 OpenAPI 必须 IP 白名单，团队 IP 不固定（家里/办公室/联通动态 IP）
- App ID/Secret 不能直接分发给同事（安全 + 赛狐最多 5 个 API 账号）
- 需要权限控制（不同同事访问不同模块）
- 将来可能接入通途等其他国产 ERP API

## 方案

借鉴 Kong 的插件阶段模型和声明式配置，用 Python/FastAPI 实现轻量 API 网关（~500 行），部署在 VPS（固定 IP）上。

```
同事 AI Agent (任意 IP)
       │ Bearer sk-xxx
       ▼
┌──────────────────────────┐
│  sellfox-api-proxy       │  ← VPS (固定 IP)
│  FastAPI :8400           │
│                          │
│  Key验证→限流→Token→签名→│→ 赛狐/通途/...
└──────────────────────────┘
```

## 文档

完整设计文档见 [docs/](docs/)（OKF v0.1 标准），入口 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)。
