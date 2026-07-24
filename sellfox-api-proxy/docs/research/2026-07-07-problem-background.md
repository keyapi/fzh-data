---
okf: v0.1
type: Research
title: 问题背景 — 赛狐 API 代理需求
description: 为什么需要 API 代理网关：赛狐 IP 白名单限制 + 凭证安全分发 + 多同事 AI Agent 调用
tags: [sellfox, api-proxy, problem-statement, ip-whitelist, credential-security]
sources:
  - SELLFOX_API/docs/lessons/2026-06-25-sellfox-integration-lessons.md
  - SELLFOX_API/docs/api-reference/开发指南/获取 Access Token.md
  - SELLFOX_API/docs/api-reference/开发指南/生成sign（签名）.md
  - SELLFOX_API/config.json
---

# 赛狐 API 代理需求 — 问题背景

## 赛狐 OpenAPI 概述

赛狐（Sellfox / 赛狐ERP）提供 OpenAPI 供开发者对接。已成功接入广告报告获取等功能。

- **API 域名**: `https://openapi.sellfox.com`
- **认证方式**: OAuth2 client_credentials
  - `GET /api/oauth/v2/token.json?client_id=...&client_secret=...&grant_type=client_credentials`
  - 返回 `access_token`，有效期 24 小时（86400000ms）
  - 有效期内重复获取返回相同结果
- **业务请求签名**: HMAC-SHA256
  - 签名字段（字典排序）: `access_token`, `client_id`, `method`, `nonce`, `timestamp`, `url`
  - 格式: `k1=v1&k2=v2&...`
  - 签名后拼接到 URL query string: `?access_token=...&client_id=...&nonce=...&timestamp=...&sign=...`
- **请求方式**: POST + JSON body（token 端点除外）

## 三个核心痛点

### 痛点 1: IP 白名单限制

赛狐 API 的 IP 白名单是服务端强制校验。**Token 端点 (`/api/oauth/v2/token.json`) 是唯一不受 IP 白名单限制的端点**（Lesson 1）。

当前白名单 IP：
- 123.117.236.65（北京办公室）
- 82.156.238.248（VPS）

问题：
- 联通宽带 IP 动态变化
- 在家办公 IP 不同
- 同事出差/IP 随时变
- AI Agent 可能在任意网络环境运行

**根因**：赛狐的 IP 白名单是静态的，无法适应分布式团队。

### 痛点 2: 凭证安全分发

赛狐 API 账号信息：
- 最多支持 5 个 API 账号
- 已用 2 个（开发）
- 剩余 3 个配额

App ID 和 App Secret 不能直接分发给所有同事：
- 安全风险：泄露后攻击者可直接调用赛狐 API
- 赛狐条款明确要求"不将自身的 App key 和 App secret 透露给任何第三方"（免责声明第 7.10 节）
- 无权限控制：赛狐不提供子账号或 RBAC 机制
- 无法追踪：不知道谁调用了什么

### 痛点 3: AI Agent 时代的调用模式变化

以前：
- 同事用软件 → 软件内置 API 调用 → IP 在白名单中

现在：
- 每个同事可能用 AI Agent（Claude Code、Cursor 等）
- Agent 直接调用 API → IP 可能不在白名单中
- Agent 需要 API 凭证 → 但不能给真实凭证

## 约束条件

1. **部署环境**：已有 VPS（82.156.238.248），运行 Docker（new-api + new-api-dingtalk-oidc）
2. **技术栈**：Python 为主（团队技能匹配），已有 FastAPI 项目
3. **赛狐限流**：全局约 1 rps（Lesson 16: 2 秒间隔才稳定）
4. **未来扩展**：可能需要接入通途等其他 ERP API

## 已有基础设施

| 资源 | 状态 | 位置 |
|------|------|------|
| VPS | 运行中 (82.156.238.248) | Docker, new-api 已部署 |
| new-api | 运行中 | LLM API 网关 + DingTalk OIDC 登录 |
| 赛狐 API 凭证 | 已获取 | `SELLFOX_API/.env` (gitignored) |
| 赛狐集成代码 | 生产验证 | `SELLFOX_API/fetch_ad_reports.py` |
| 赛狐踩坑文档 | 16 条教训 | `SELLFOX_API/docs/lessons/` |
| 赛狐 API 文档 | Apifox 导出 | `SELLFOX_API/docs/api-reference/` |

## 已有赛狐相关代码

- `SELLFOX_API/fetch_ad_reports.py` — SP 广告报告获取（urllib 实现，生产验证）
- `SELLFOX_API/fetch_sb_sd_reports.py` — SB/SD 广告报告
- `SELLFOX_API/fetch_extra_reports.py` — 额外报告
- `SELLFOX_API/test_api.py` — API 测试
- `SELLFOX_API/config.json` — 配置文件
- `advertise/` — 广告分析模块（依赖赛狐 API）
