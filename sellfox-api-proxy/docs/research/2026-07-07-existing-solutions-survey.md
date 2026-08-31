---
okf: v0.1
type: Research
title: 现成方案调研 — 通用 API 代理/网关开源项目
description: 对 NyaProxy、APIKeyRotator、Bifrost、Gateon 等通用 API 代理方案 + 专用 HMAC 签名代理 + OAuth2 代理 + 虚拟 Key 管理的全面调研
tags: [sellfox, api-proxy, survey, open-source, comparison]
---

# 现成方案调研

## 一、通用 API 代理（非 LLM 专用）

### NyaProxy — 最成熟的通用 API 代理

- **GitHub**: https://github.com/Nya-Foundation/NyaProxy
- **Stars**: ~960
- **语言**: Python/FastAPI + Vue.js 3
- **许可证**: MIT
- **版本**: v0.5.0
- **代码量**: ~3,350 行 Python
- **关键能力**: API Key 池轮询、负载均衡（5 种策略）、多级限流、请求体 JMESPath 转换、流式代理、实时 Dashboard、Prometheus 指标
- **通用 API 模式**: 支持，Key 通过 Header `${{variable}}` 模板注入
- **局限性**:
  - 无查询参数注入（forward 时丢失 `?query=string`）
  - 无插件/中间件钩子系统
  - 无自定义签名能力
  - Key 存储在 YAML 配置文件中（非数据库）
  - OAuth2 令牌管理需从零实现
- **Fork 可行性**: 高。代码结构清晰，插入点明确（`nya/core/proxy.py` 第 89-100 行），MIT 许可

### APIKeyRotator — Go 语言轻量代理

- **GitHub**: https://github.com/lrbmike/APIKeyRotator
- **语言**: Go + Vue.js
- **特点**: 明确支持"通用 API"（非 AI）模式，Key 注入方式可选 Query param / Header
- **局限性**: 新项目，社区小；Go 语言对团队不友好；无 Dashboard 截图可参考

### Bifrost (FokusInternal) — 虚拟 Key 代理

- **GitHub**: https://github.com/FokusInternal/bifrost
- **Stars**: 1（新项目）
- **语言**: Go
- **特点**: 通用 API 访问网关，虚拟 Key 委托 + Vault 集成，Kubernetes Operator
- **局限性**: 太新（1 star），无 Dashboard，无 HMAC 签名

### Gateon — 通用反向代理

- **GitHub**: https://github.com/gsoultan/gateon
- **Stars**: 较新
- **语言**: Go
- **特点**: API Key + JWT 认证，负载均衡，限流，WAF，React Dashboard
- **局限性**: Go 语言，对赛狐签名无原生支持

## 二、成熟 API 网关（有插件系统）

### Apache APISIX

- **GitHub**: https://github.com/apache/apisix
- **Stars**: ~14,000
- **语言**: Lua + Go/Wasm 多语言插件
- **HMAC 出站签名**: 可通过自定义 Lua/Wasm 插件实现
- **Dashboard**: 2025 年重写的 React Dashboard
- **评估**: 优秀但偏重，需要 Lua 开发

### Kong Gateway

- **GitHub**: https://github.com/Kong/kong
- **Stars**: ~40,000
- **语言**: Lua（核心~15 万行）
- **Docker 镜像**: 114.9 MB
- **HMAC 出站签名**: 需自定义 Lua 插件（~160 行）
- **DB-less 模式**: 可用但受限（OAuth2 插件不可用、UI 只读、限流 local-only）
- **评估**: 太重，Lua 技能不匹配。详见 [Kong 架构分析](2026-07-08-kong-architecture-analysis.md)

### Tyk Gateway

- **GitHub**: https://github.com/TykTechnologies/tyk
- **Stars**: ~10,000
- **特点**: 唯一内置出站 HMAC 签名的网关（`request_signing` API 定义属性）
- **OAuth2**: 支持 client_credentials
- **Dashboard**: 商业版
- **评估**: 最接近"现成方案"，但 Dashboard 需商业许可

### Gravitee APIM

- **GitHub**: https://github.com/gravitee-io/gravitee-api-management
- **Stars**: ~300
- **语言**: Java
- **特点**: 有 `generate-http-signature` 策略（出站 HTTP 签名）
- **评估**: Java 技术栈不匹配

### Higress (Alibaba)

- **GitHub**: https://github.com/alibaba/higress
- **Stars**: ~6,500
- **语言**: Go + Wasm 插件
- **特点**: Go Wasm 插件可处理任意请求签名
- **评估**: 中文生态友好，但偏重

### Apache ShenYu

- **GitHub**: https://github.com/apache/shenyu
- **Stars**: ~8,600
- **语言**: Java
- **特点**: 内置 Sign 插件（AK/SK 认证 + 参数签名），Admin UI 含密钥管理
- **评估**: Java 技术栈不匹配

## 三、专用 HMAC 签名代理

### 18F/hmacproxy

- **GitHub**: https://github.com/18F/hmacproxy
- **Stars**: 3（已归档）
- **语言**: Go
- **特点**: 配置 `-secret` + `-sign-header` + `-upstream` 即可 HMAC 签发出站请求
- **局限**: 单密钥，无 YAML 路由，无 OAuth2，无 Dashboard

### jlewi/hmacproxy（推荐的分支）

- **GitHub**: https://github.com/jlewi/hmacproxy
- **Stars**: ~20
- **特点**: 增强分支，支持 YAML 路由配置 + GCP Secret Manager
- **评估**: 最轻量的 HMAC 签名代理参考

### gogatekeeper/gatekeeper

- **GitHub**: https://github.com/gogatekeeper/gatekeeper
- **Stars**: ~700
- **特点**: `--enable-forwarding --enable-hmac` 前向代理 + HMAC 签名 + OAuth2 令牌管理
- **局限**: 签名字段硬编码，不可自定义；Go 语言
- **评估**: 最接近"一体方案"，但不适合扩展

### aws-sigv4-proxy

- **GitHub**: https://github.com/awslabs/aws-sigv4-proxy
- **Stars**: ~360
- **语言**: Go
- **特点**: AWS SigV4 签名代理——证明"签名代理"模式可行
- **参考价值**: 架构模式，但签名为 AWS 固定格式

### quay/jwtproxy

- **GitHub**: https://github.com/quay/jwtproxy
- **语言**: Go
- **特点**: JWT 签名代理，Red Hat 生产使用
- **参考价值**: signer_proxy / verifier_proxy 双模式架构

## 四、OAuth2 令牌管理工具

### oauth2-proxy

- **GitHub**: https://github.com/oauth2-proxy/oauth2-proxy
- **Stars**: ~14,600
- **局限**: 仅支持浏览器 authorization_code 流程，不支持 client_credentials
- **来源**: [Issue #2509](https://github.com/oauth2-proxy/oauth2-proxy/issues/2509)

### Ory Oathkeeper

- **GitHub**: https://github.com/ory/oathkeeper
- **Stars**: ~3,500
- **特点**: v0.38.20-beta.1 引入 OAuth2 client_credentials 令牌缓存
- **参考价值**: 客户端凭据令牌缓存的成熟实现参考

### ooproxy

- **Docker Hub**: https://hub.docker.com/r/hal24000/ooproxy
- **特点**: 极轻量（6.8 MB），纯 client_credentials 反向代理，支持令牌缓存
- **参考价值**: 最简 OAuth2 代理参考

## 五、虚拟 Key 管理

### Unkey

- **GitHub**: https://github.com/unkeyed/unkey
- **Stars**: ~5,400
- **特点**: API 密钥发放/验证/撤销/限流/RBAC/审计，Dashboard UI
- **参考价值**: Key 管理数据模型和 Dashboard 设计

### Ory Talos

- **GitHub**: https://github.com/ory/talos
- **特点**: 2026 年 6 月新发布，专用 API 密钥管理服务器
- **参考价值**: 长期 Key → 短期 JWT 的派生模式

## 六、最终对比矩阵

| 方案 | 通用 API | 密钥分发 | HMAC 签名 | OAuth2 Token | Dashboard | Python | 轻量 |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| NyaProxy | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ |
| APIKeyRotator | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ✅ |
| Kong | ✅ | ✅ | 需插件 | 需插件 | ✅ | ❌ | ❌ |
| APISIX | ✅ | ✅ | 需插件 | 需插件 | ✅ | 部分 | ❌ |
| Tyk | ✅ | ✅ | ✅内置 | ✅ | 商业版 | ❌ | ❌ |
| gogatekeeper | ❌ | ❌ | ✅硬编码 | ✅ | ❌ | ❌ | ✅ |
| 18F/hmacproxy | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ |
| **Micro Kong (选定)** | ✅ | ✅ | ✅插件 | ✅插件 | 简易 | ✅ | ✅ |
