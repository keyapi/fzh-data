---
okf: v0.1
type: Research
title: 对话演化过程 — sellfox-api-proxy 方案推演全记录
description: 从原始需求到 Micro Kong 方案的完整对话推演过程，含每次转向的原因和关键发现
tags: [sellfox, api-proxy, conversation-log, decision-evolution]
---

# 对话演化过程 — 方案推演全记录

## 第 0 轮：原始需求

用户提出赛狐 API 的三个问题：
1. IP 白名单（联通 IP 会变 / 在家 IP 不同）
2. 凭据不能暴露给同事（App ID / Secret）
3. 赛狐最多 5 个 API 账号（已用 2 个），不能每人一个

用户自己提出了初步思路：能否像 new-api 那样做个中转？

## 第 1 轮：通用方案调研

- 搜索了 One-API / New-API / VoAPI（LLM 专用，不适合赛狐自定义签名）
- 搜索了 voidllm / Tkngate / Bifrost 等通用 API 代理
- **关键发现**：行业最佳实践——四个必设项 = IP 白名单 + 有效期 + 模块限制 + 额度上限
- 初步提出：自研 FastAPI 代理（~600 行）

用户反馈：**"有没有现成的？不是 LLM 专用的？先搜再造"**

## 第 2 轮：通用 API 代理开源方案搜索

搜索方向：
- 通用 API 密钥分发代理（非 LLM）
- 发现了 **APIKeyRotator**、**NyaProxy**、**Bifrost**、**Gateon**
- 深度对比分析
- **关键发现**：NyaProxy（~960 stars）明确支持"通用 API"模式（非 LLM），Python/FastAPI + Vue Dashboard

但也有一个共同问题：**这些工具都没有自定义 HMAC-SHA256 签名能力**。它们只能注入静态 Key（Header/Query param），不能每请求动态计算签名。

提出：**Fork NyaProxy + 加 ~90 行代码**（赛狐签名 + Token 缓存）

用户反馈：**"有没有兼顾 NyaProxy 和支持 HMAC 签名 + OAuth Token 的方案？把湖煮干"**

## 第 3 轮：把湖煮干——穷举搜索

并行搜索：
- 成熟 API 网关（APISIX / Kong / Tyk / Gravitee / Higress / ShenYu / KrakenD / Gloo / Traefik）
- 专用 HMAC 签名代理（18F/hmacproxy / gogatekeeper / jwtproxy / aws-sigv4-proxy）
- OAuth2 代理（oauth2-proxy / Ory Oathkeeper / ooproxy / stoat）
- 虚拟 Key 管理（Unkey / Ory Talos）
- 中文生态（签名代理 / API 签名中转）

**终极结论**：不存在同时满足三个条件的现成方案。

但有几个"差一步"的方案：
- gogatekeeper — 最近，但 HMAC 签名字段硬编码，Go 语言
- NyaProxy — 需要 Fork 加 ~90 行
- APISIX/Kong — 太重，需要写 Lua/Go 插件

用户向 Google AI 交叉验证，Google AI 认可方向但签名代码有误。

提出两条路：Fork NyaProxy vs 自研 FastAPI

用户要求：**先 deep dive NyaProxy 代码，再评估自研引用哪些方案**

## 第 4 轮：NyaProxy 源码深度分析 + 自研参考调研

NyaProxy 关键发现：
- ~3,350 行 Python，MIT 许可
- **query 参数被丢弃**的 Bug（`parse_request()` 只取 path，不取 query）
- 无插件/中间件钩子系统
- Key 存在 YAML 配置文件中（不是数据库）
- 插入点确定：`nya/core/proxy.py` `_process_queued_request()` 第 89-100 行
- Dashboard 是 Vue SPA（8.3KB HTML + 12.3KB JS）

自研参考方案：
- LM-Proxy（137 stars）— **最好的架构参考**：RequestContext + before 管线 + resolve_instance_or_callable
- proxy.py（3,535 stars）— ABC 插件生命周期（但 TCP 级别，不适用）
- litellm（52,899 stars）— Key/Team/Org 多级权限模型 + 用量追踪

提出：自研 ~500 行，借鉴以上方案

用户反馈：**"自研能否兼容别的 API？加通途难度？"**

回答：可以，用策略模式，加新 API 0~50 行代码

用户仍有疑虑：**"自研不踏实，分析一下 Kong"**

## 第 5 轮（最终轮）：Kong 深度分析 → Micro Kong

关键发现：
- Kong 镜像 114MB，核心 ~15 万行 Lua，45 个插件
- DB-less 模式有限制：OAuth2 插件不可用、UI 只读、限流 local-only
- **Kong 也解决不了赛狐签名**——仍然要写自定义 Lua 插件（~160 行）
- 但 Kong 的插件阶段模型（rewrite → access → header_filter → body_filter → log）是 10 年验证的设计
- Python 替代品：proxy.py 有插件架构，但无阶段模型；Bottle 有 pre/post hooks

**最终方案：自研 "Micro Kong"**
- 借鉴 Kong 插件阶段模型（简化为 4 阶段）
- 借鉴 Kong 声明式 Provider 配置（但做双层存储：YAML 静态 + SQLite 动态）
- Python/FastAPI 实现 ~500 行
- 策略模式支持多 Provider（赛狐、通途、未来任意 API）

## 第 6 轮：集成已有钉钉 OIDC 身份体系

用户提出：能否利用已有的 DingTalk OIDC + 离职自动封号机制？

分析结论：可以，两个集成点——
1. 管理页面 SSO：nginx `auth_request` → OIDC 桥 `/userinfo` → 无需静态 ADMIN_API_KEY
2. API Key 离职封号：扩展 offboarding-check.py + stream_listener.py，按 dingtalk_union_id 同步禁用

API Key 创建时绑定员工钉钉身份，离职时自动吊销。从"管理员手动发 Key + 手动吊销"升级为"员工自助 + 零延迟自动封号"。

方案更新到计划文件中（v7），OKF 文档同步更新。
