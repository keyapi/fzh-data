---
okf: v0.1
type: Log
title: 变更日志
description: US OpenAI API Proxy 模块的时序变更记录（公开脱敏版）
tags: [openai, api-proxy, changelog]
---
# 变更日志

> 此日志只记录可公开复用的结论。服务器、账号、授权材料、私有地址、订阅与访问凭据均不入库。

## 2026-10-14

- **修复（出口接线）**：办公室 OpenClash 的**自建应急出口长期「活着但没接线」**。现象：策略组 `Emergency`（节点 `SH-Tailscale-US`，socks5 → 上海跳板 `ssh -D` SOCKS → 美国 Vultr）在运行配置里**入向引用为零** —— 无规则指向、无其它组收编；而链路本身实测是活的（出口 `149.28.67.226`、Tailscale 为 direct）。
- **根因**：自定义覆写脚本 `openclash_custom_overwrite.sh` 的 `inject_emergency()` 里**写死了上一代订阅（SSRDog）的策略组名 `Auto`**，现役订阅叫 `自动选择` ⇒ `Array#find` 返回 `nil`、整段静默跳过。**即 Lesson 9（组名不是稳定接口）在现役订阅下的一次真实翻车**；修法即 Lesson 11（走幂等覆写路径）。
- **处置**：在 `add_country_groups()` 的 `ai_members` 字面量末尾追加 `'Emergency'`（**改脚本不改 live config**），先备份 `*.bak-*`；验证顺序 = 副本干跑 → 重载后从内核 REST API 读回组员表 → 端到端切过去看出口 IP。**刻意不放进 url-test 自动组**（会把全办公室流量挤上窄带跨境隧道，并重现「被持续占用、忘了切回」的历史事故）；`故障转移`(fallback) 组当前成员开头是订阅商 info 伪节点，处于空转，未动。
- **效果**：`AI 出口` 现在多了一个**人工兜底**选项 `Emergency`；AI 线路全挂时可手动切过去（实测出口 = 美国 Vultr，OpenAI 可达）。
- **留档**：`docs/solutions/integration-issues/openclash-overwrite-stale-group-name-orphaned-egress.md`（事故正文 + 检测手段）；出口拓扑同步更新于 `docs/solutions/architecture-patterns/office-egress-fallback-chain.md`。

## 2026-09-20

- **修复（链接）**：`office-lan-access.md` 指向 `NAS_API/docs/reference/nas-multi-domain-access.md` 的链接多退一级（`../../../` → `../../`）。

## 2026-09-08 (v0.15)

- 处理 CLIProxyAPI `503 auth_unavailable`：确认 systemd active 与基础健康检查不等于目标模型有可用上游授权。
- CLIProxyAPI 升级至 v7.2.152，使用浏览器 OAuth 刷新授权，隔离确认失效的认证记录后重启服务。
- 恢复验收改为向配置的实际监听地址请求目标模型；真实 completion 正常返回才标记恢复。
- 更新 README、operations、handoff、lesson 与 skill；移除公开文档中的账号历史和具体网络、认证操作细节。

## 2026-08-25 (v0.14)

- 更新办公室代理订阅与策略组映射，保留受控应急出口作为 fallback。
- 处理 DNS 分流导致的外网解析异常，并以覆写机制保证订阅更新后可重复应用。
- 增加 AI 服务按可用出口选择的操作说明；验证应以实际服务连续可用为准。
- 记录个别业务系统的路由例外应先经验证，并在变更前取得明确授权。

## 2026-08-03 (v0.8)

- 更新上游模型可用性和内部定价说明。
- 记录专用生图模型与聊天端点的协议边界。
- 明确工作区策略会影响模型可用性，切换或刷新认证前须先确认授权范围。

## 2026-07-27 (v0.13)

- 处理服务器重启后的 DNS 故障：禁用不需要的 DNS 接管，并持久化系统上游解析器。
- 验证受控应急出口恢复可用。

## 2026-07-01 至 2026-07-03 (v0.11–v0.12)

- 代理订阅故障期间，验证经受控跳板的 SSH SOCKS 应急链路可用。
- 为办公室 OpenClash 增加可重复注入的应急 fallback；修正 fallback 优先级，确保主线路恢复后不会持续占用应急出口。

## 2026-06-18 至 2026-06-25 (v0.1–v0.10)

- 初始搭建 CLIProxyAPI、受控内网访问、systemd 管理与健康检查。
- 完成 LAN 网关、国内节点与容器网络的部署排障记录。
- 建立模块 OKF 文档、Agent handoff 和敏感信息分层规则。

## 后续规划

- 在取得授权后评估独立备份出口与健康检查告警。
- 持续收敛公开文档中的运维细节，真实配置只保留在受控环境。
