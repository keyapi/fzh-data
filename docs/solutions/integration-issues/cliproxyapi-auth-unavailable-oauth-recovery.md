---
okf: v0.1
type: Solution
title: CLIProxyAPI `auth_unavailable`：升级、浏览器 OAuth 与真实模型验收
date: 2026-09-08
category: integration-issues
module: us-openai-api-proxy
problem_type: integration_issue
component: authentication
symptoms:
  - "请求目标模型返回 `503 auth_unavailable`"
  - "systemd 服务为 active 且健康检查正常，但真实模型请求失败"
root_cause: incomplete_setup
resolution_type: workflow_improvement
severity: high
tags: [cliproxyapi, oauth, authentication, auth-unavailable, model-verification]
related_components: [new-api-deployment]
---

# CLIProxyAPI `auth_unavailable`：升级、浏览器 OAuth 与真实模型验收

## Problem

CLIProxyAPI 的 systemd 服务和基础健康检查均正常，但调用目标模型返回
`503 auth_unavailable`。这类故障不能仅凭进程状态判断为服务可用：代理进程可
正常监听，却没有任何可向该模型提供授权的上游 OAuth 凭据。

## Symptoms

- 请求返回 `503 auth_unavailable`，并指出无可用授权提供者。
- `systemctl` 显示服务运行中，基础端口或模型列表检查仍可成功。
- 更换或刷新授权后，必须对目标模型发起实际 completion 才能确认恢复。

## What Didn't Work

- **只看 health check**：它只证明进程、监听端口或基础 HTTP 路径可响应，不证明
  某个模型可被上游授权。
- **复用旧浏览器授权链接**：OAuth 授权链接和回调状态为短时效、一次性会话，过期后
  不能继续使用。
- **假设设备代码登录一定可用**：部分工作区会由管理员策略禁用该方式。
- **假设服务在 localhost 监听**：验证请求必须使用配置中的实际监听地址。

## Solution

按以下顺序恢复，并在每个会改变服务器状态的步骤前取得运维授权：

1. 检查服务状态和日志，确认错误是 `auth_unavailable` 而不是网络、监听或 API key
   问题。
2. 备份当前可回滚的部署工件后升级 CLIProxyAPI。
3. 使用浏览器 OAuth 刷新授权。无 GUI 的服务器需建立本地 callback 转发；浏览器可按
   需要使用受控代理访问授权页。生成授权会话后应立即完成流程。
4. 先列出认证目录，再隔离已确认失效或陈旧的认证记录；不要打印、复制或提交认证内容。
5. 重启服务，并使用最小请求向配置的实际监听地址调用**目标模型**。
6. 只有获得正常模型响应后，才将故障标记为恢复。

完整的安全操作边界和占位符命令见
[`us_openai_api_proxy/docs/operations.md`](../../../us_openai_api_proxy/docs/operations.md)。

## Why This Works

代理服务健康与上游授权可用性属于不同层次：前者只验证本地服务，后者要求存在对当前
模型有效、可被代理选用的 OAuth 凭据。升级确保使用受支持的认证行为；刷新授权恢复
凭据；隔离失效条目避免错误选择；最后以目标模型的真实调用验证完整链路。

## Prevention

- 将“目标模型最小 completion 成功”纳入每次认证变更和版本升级的验收条件。
- 诊断时先记录脱敏错误类别，不记录完整认证头、请求体、OAuth URL、回调参数或文件名。
- 将 OAuth URL 视为短时效敏感信息；过期后重新生成，不在聊天记录或仓库中留存。
- 设备代码登录失败时记录为工作区策略限制，切换至受支持的浏览器授权流程。
- 认证目录只可在服务器上受控检查；仓库只保存路径占位符与操作原则。

## Related Issues

- [ChatGPT Edu 账号 CLIProxyAPI 429 限流机制调研](chatgpt-edu-cliproxyapi-429-rate-limit.md)：
  `429` 表示上游额度或速率窗口问题；`auth_unavailable` 表示没有可用授权，两者应分开诊断。
- [US OpenAI API Proxy 运维手册](../../../us_openai_api_proxy/docs/operations.md)
