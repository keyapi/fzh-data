---
okf: v0.1
type: Reference
title: 钉钉群文件与聊天归档 — 用 DWS 个人身份，不用群机器人
date: 2026-11-03
category: tooling-decisions
module: dingtalk_group_harvest
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - "要定期读取钉钉群历史消息、群文件或钉钉文档"
  - "有人提议用群机器人 / 企业内部应用 / 会话存档做群内容采集"
  - "需要判断个人 OAuth CLI 与企业应用权限的边界"
tags: [dingtalk, dws, group-files, chat-archive, oauth, robot, watermark]
---

# 钉钉群文件与聊天归档 — 用 DWS 个人身份

## Context

运营2/3/4部 AI 项目群（2026-10-27~29 新建）里，同事持续提交 `.md` 产品分析、市场竞品、提示词等文件。需求是：每天自动采集群消息与文件，每周生成可检索的记录文档，数据只留在公司内部。

先排除了三条常见路径：

| 方案 | 为什么不行 |
|---|---|
| 自定义群机器人 | 只能发送 text/markdown/link/actionCard，不能读消息、不能发文件 |
| 企业内部应用 + Stream | 只能收「@机器人」的实时消息；读不到机器人接入前的历史，事件中断也无法补历史 |
| 会话存档 | 企业付费/管理员开通，且钉钉给的是密文，企业要自己解密、落库、管私钥 |

## Guidance（本学习沉淀的做法）

用 **DWS（DingTalk Workspace CLI）** 以**个人 OAuth 身份**采集。它是钉钉官方开源项目（Apache-2.0），能复用你在钉钉客户端里的权限：拉群历史消息、下载消息附件、导出钉钉文档、读钉盘和知识库。

落地的四条硬规则：

1. **先解析群并固定 `openConversationId`**：`dws chat +chat-search --query "<群名>" --page-all -f json`；首次成功后写进本机 `groups.local.json`，避免群改名导致解析失败。
2. **完整性账本是硬门槛**：`+chat-messages` 必须检查 `complete=true`、`hasMore=false`、`failures=[]`。任一不满足就不推进水位、退出码非零；否则会把“半页数据”当成完整历史。
3. **按文件引用单独下载，不批量拽全部媒体**：`+messages-resource-download --type fileId --resource-id <id>`；用 `resourceId` 去重并记录本地路径。图片/视频默认不下，避免每天重复拉取。
4. **原始数据必须在公开仓库之外**：归档根 `%USERPROFILE%\dingtalk_harvest`（`DINGTALK_HARVEST_ROOT` 可覆盖），`groups.local.json`、原始消息、附件全部 gitignore；仓库只放代码、模板和脱敏文档。

水位设计：每群保存 `last_message_time` + `last_message_id`，下次从上次时间前 1 秒开始重叠拉取，按 `messageId`/`resourceId` 去重。文件下载失败时**不推进水位**，下次重试；钉钉文档导出失败只记报告、不阻塞水位（消息原文已归档）。

## Why This Matters

- 不依赖机器人，不需要等管理员给群加机器人，也不打扰群成员。
- 不需要企业内部应用的 scope 申请，也不需要会话存档的解密链路。
- 完整性账本让“漏采”可被发现：DWS 分页失败时会明确返回 `chat_list_incomplete` / `failures`，不会静默返回半截数据。
- 2026-11-03 实测：三个群解析成功；首次采集 103 条消息、24 个文件引用、22 个唯一文件归档、0 失败；第二遍 0 新增、0 重复下载。

## When to Apply

- 要定期归档钉钉群历史消息/文件/文档，且你有权访问这些群。
- 群机器人只能做“推送摘要”，不能承担采集。
- 不想走付费会话存档，但需要比“@机器人实时消息”更完整的历史。

不适用：需要审计全员单聊、需要防撤回/防截图的合规存档（那属于会话存档的职责）；或组织未开通 DWS CLI 访问权限。

## Examples

```bash
# 解析群
dws chat +chat-search --query "运营2部AI项目沟通群" --page-all -f json

# 拉增量消息（输出路径必须是当前工作目录内的相对路径）
dws chat +chat-messages --group "cid..." \
  --start "2026-10-27T00:00:00+08:00" --end "2026-11-03T00:00:00+08:00" \
  --order asc --page-all --page-limit 100 --output messages.json

# 下载单个文件
dws chat +messages-resource-download --type fileId \
  --resource-id "LeBq..." --output ./res/sample.md

# 导出钉钉文档
dws doc export --node "https://alidocs.dingtalk.com/i/nodes/..." \
  --export-format markdown --output ./docs/sample.md
```

## Related

- 模块：`dingtalk/dingtalk_group_harvest/`（README / AGENT_HANDOFF）
- 同批经验：
  - `developer-experience/claude-headless-long-prompt-stdin.md`
  - `developer-experience/windows-schtasks-worktree-path-trap.md`
- DWS 官方仓库：https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli
- 开放平台群历史消息建议（说明官方尚未开放任意群历史）：https://developer.aliyun.com/ask/707883
