---
type: skill
name: us-openai-api-proxy
description: CLIProxyAPI 的可用性、认证恢复和受控运维入口
version: 0.1.0
triggers:
  - "CLIProxyAPI"
  - "auth_unavailable"
  - "Codex OAuth"
  - "OpenAI API Proxy"
  - "US AI Proxy"
  - "模型授权失败"
---

# US OpenAI API Proxy Skill

## 新对话必读

1. `us_openai_api_proxy/AGENT_HANDOFF.md`：模块状态、升级与升级后的验收入口。
2. `us_openai_api_proxy/docs/operations.md`：脱敏运维 runbook。
3. `docs/solutions/integration-issues/cliproxyapi-auth-unavailable-oauth-recovery.md`：
   `503 auth_unavailable` 的诊断和恢复边界。

## 处理规则

- 服务 `active` 或基础 health check 成功，不等于目标模型有可用上游授权；恢复验收必须是
  对目标模型的最小真实请求。
- 升级、OAuth、认证记录隔离、重启或服务器配置修改均会影响共享服务，执行前必须取得用户授权。
- 浏览器 OAuth URL、callback 参数、授权码、认证文件名/内容、账号、token、API key、私有地址和
  网络拓扑均不得输出到仓库、日志或对话摘要。
- 认证记录仅可在服务器上受控检查；先备份、再隔离已确认失效的条目，并保留恢复路径。
- 设备代码登录若被策略禁用，不绕过策略；改用经授权的浏览器 OAuth。
