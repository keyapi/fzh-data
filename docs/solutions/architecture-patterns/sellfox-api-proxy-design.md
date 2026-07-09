---
module: sellfox-api-proxy
date: 2026-07-09
problem_type: architecture_pattern
component: tooling
severity: medium
tags: [api-gateway, proxy, multi-tenant, oidc, dingtalk, sellfox, key-management]
---

# API 代理网关自建方案与架构演进

## Context

赛狐 OpenAPI 要求 IP 白名单 + 最多 5 个 API 账号。团队需要多同事共用一套凭证，同时解决凭证安全分发和权限控制。

## Guidance

**不要为 2-3 个 Provider 建插件框架。** 硬编码调用链，等 Provider 到 5+ 再抽象。

**借鉴 Kong 的插件阶段模型，不照搬 Kong。** 取其设计思想（按阶段分组、声明式配置），用 Python 实现轻量版。

**双层存储**：静态配置 (accounts, rate limits) 放 YAML，动态数据 (API keys) 放 SQLite。避免 "改 Key 要重启"。

**自包含 OIDC 验证**：不依赖 nginx auth_request。proxy 自己完成 OIDC code 交换和 session 签发。

## Why This Matters

见 sellfox-api-proxy 完整经验教训文档（15 条）：
- `sellfox-api-proxy/docs/lessons/2026-07-09-full-architecture-evolution.md`
- 部署地址：`https://api.vilavi.cn/sellfox/admin`
- 代码：`sellfox-api-proxy/` (1,234 行)

## When to Apply

- 需要给多个同事安全分发第三方 API 凭证
- 上游 API 有 IP 白名单限制
- 上游 API 有自定义签名算法（HMAC-SHA256 等）
- 团队需要 OIDC/SSO 登录 + 自动配给
