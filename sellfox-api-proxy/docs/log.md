---
okf: v0.1
type: Log
title: 变更日志
description: sellfox-api-proxy 项目全生命周期记录
tags: [sellfox, api-proxy, gateway, log]
---

# 变更日志

## 2026-07-09

- **v0.4.2 中文 UI + 复制修复**: 全中文界面、复制按钮移到 Key 列、`data.key → undefined` 修复
- **v0.4.1 Key 加密存储**: XOR + SHA-256 纯 Python（零依赖），`POST /api/keys/{id}/reveal` 随时复制
- **v0.4.0 Accounts + Auto-Provision**: Provider→Account 重构，`_ensure_user_has_key()` 首次登录自动配给，per-account 全局限速
- **v0.3.0 角色隔离**: Admin Key=管理员看全部，钉钉登录=用户只看自己
- **v0.2.1 浏览器可用**: `<base href>` + 相对 URL + cookie path 修复
- **完整经验教训**: [2026-07-09-full-architecture-evolution.md](lessons/2026-07-09-full-architecture-evolution.md) — 15 条核心教训

## 2026-07-08

- **钉钉 OIDC 身份集成设计**: 复用已有 new-api-dingtalk-oidc 桥实现管理页面 SSO（nginx auth_request），API Key 绑定 dingtalk_union_id，扩展 offboarding-check.py + stream_listener.py 实现离职自动封号
- **Micro Kong 架构定案**: 深入分析 Kong API Gateway 后，决定自研"Micro Kong"——借鉴 Kong 插件阶段模型和声明式配置思想，Python/FastAPI 实现 ~500 行，避免 Kong 的臃肿（15 万行 Lua / 114MB 镜像 / PostgreSQL 依赖）
- **声明式配置与 DB 解耦设计**: 分析 Kong DB-less 模式陷阱（OAuth2 不可用、UI 只读、限流 local-only、改 Key 需 reload），决定采用"YAML 管静态配置 + SQLite 管动态数据"双层架构
- **NyaProxy 源码深度分析完成**: 确认关键插入点位于 `nya/core/proxy.py` `_process_queued_request()` 方法（第 89-100 行），发现 query 参数丢失 Bug
- **通用 API 网关全面调研完成**: 覆盖 9 个网关（APISIX/Kong/Tyk/Gravitee/Higress/ShenYu/KrakenD/Gloo/Traefik）+ 专用 HMAC 签名代理（18F/hmacproxy/gogatekeeper/aws-sigv4-proxy）+ OAuth2 代理 + 虚拟 Key 管理
- **自研参考架构分析完成**: 选定 LM-Proxy 的 RequestContext + before 管线、proxy.py 的 ABC 插件生命周期、litellm 的 Key 管理数据模型为参考

## 2026-07-07

- **赛狐 HMAC 签名算法确认**: 确认格式为 `k1=v1&k2=v2`（字典排序），不是 Google AI 建议的 `k1v1k2v2`。已从 `fetch_ad_reports.py:55-69` 验证
- **通用 API 分发开源方案首轮调研**: 发现 NyaProxy（~960 stars）、APIKeyRotator、Bifrost 三个通用 API 代理
- **NyaProxy 初步分析**: 确认其通用 API 模式、密钥分发、Dashboard 功能，同时确认不支持自定义 HMAC 签名
- **gogatekeeper 排除**: 签名字段硬编码，不可扩展；Go 语言对团队不友好
- **Google AI 交叉验证**: 其分析逻辑完全成立，但签名代码格式有误（`k1v1k2v2` 应为 `k1=v1&k2=v2`），且建议 Fork NyaProxy 路径正确
- **项目启动**: 创建 sellfox-api-proxy 子项目文件夹，按 OKF v0.1 标准建立文档体系
