---
okf: v0.1
type: Handoff
title: US OpenAI API Proxy — Agent 接手参考
description: CLIProxyAPI 服务的安全入口、状态判断与文档导航
tags: [openai, api-proxy, handoff, authentication]
---
# US OpenAI API Proxy — Agent 接手参考

> 本文档是本模块的新对话入口。只保存可公开的导航和操作边界；真实配置、身份和认证材料仅存在于受控环境。

## 当前状态

| 项目 | 状态 |
|------|------|
| 服务形态 | US Ubuntu 上的 CLIProxyAPI，由 systemd 管理 |
| 网络暴露 | 仅使用受控内网监听；实际地址见受控配置 |
| 上游认证 | 已通过浏览器 OAuth 刷新；真实身份和认证材料不入库 |
| 最近验收 | 目标模型的真实最小 completion 已返回正常结果 |
| 软件版本 | CLIProxyAPI v7.2.152 |

## 首先判断哪一层失败

| 现象 | 首先读 / 做 |
|------|-------------|
| 服务启动、日志、重启或资源问题 | [docs/operations.md](docs/operations.md) 的“快速登录与服务检查” |
| `503 auth_unavailable` | [docs/operations.md](docs/operations.md) 的“诊断”和“授权恢复” |
| ChatGPT/Codex OAuth 需要刷新 | [docs/operations.md](docs/operations.md) 的“浏览器 OAuth” |
| 服务 active 但模型仍失败 | 对**目标模型**运行最小真实请求，不以 health check 为结论 |
| 上游返回 `429` | [429 限流调研](../docs/solutions/integration-issues/chatgpt-edu-cliproxyapi-429-rate-limit.md) |

## `auth_unavailable` 处置顺序

1. 查看 service 状态和脱敏日志，并确认实际监听地址。
2. 用目标模型的最小请求确认是授权可用性问题，而非仅进程或端口问题。
3. 获用户授权后，备份可回滚工件并升级 CLIProxyAPI。
4. 通过受控的浏览器 OAuth 刷新授权；过期 URL 必须重新生成。
5. 只检查认证目录的元数据，隔离已确认失效的条目，不打印或提交其内容。
6. 重启服务，向实际监听地址再次请求目标模型；正常 completion 才是恢复完成。

设备代码授权可能受工作区管理员策略禁用；不得尝试绕过策略。

## 隐私与变更边界

- 不输出或提交账号、OAuth URL/callback/state/code、认证文件名或内容、token、API key、私有地址和完整请求体。
- 升级、OAuth、认证记录隔离、重启与配置修改都影响共享服务，执行前须取得用户授权。
- 不将临时 OAuth 辅助脚本提交到仓库；只有已确认通用、长期需要且完全脱敏的工具才可单独评审后纳入。

## 文档导航

- [README.md](README.md) — 人读概览
- [docs/operations.md](docs/operations.md) — 日常运维和授权恢复 runbook
- [docs/architecture.md](docs/architecture.md) — 架构说明
- [docs/log.md](docs/log.md) — 模块变更记录
- [docs/lessons/lessons-learned.md](docs/lessons/lessons-learned.md) — 经验教训
- [docs/index.md](docs/index.md) — 模块文档索引
- [解决方案：`auth_unavailable` 恢复](../docs/solutions/integration-issues/cliproxyapi-auth-unavailable-oauth-recovery.md)
