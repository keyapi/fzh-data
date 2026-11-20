---
name: dingtalk-group-harvest
description: >
  钉钉 AI 项目群（运营2/3/4部）群消息、群文件、钉钉文档的增量采集与周报。
  用 DWS 个人 OAuth 身份读取历史消息和消息附件，数据落仓库外。
  当用户提到"钉钉群文件"、"群消息采集"、"AI项目沟通群"、"DWS"、"钉钉归档"、
  "群周报"、"聊天记录汇总"、"harvest"、"watermark"等时触发。
  不要用于钉钉机器人发送（dingtalk-robot）、OA 审批附件（dingtalk-oa-approval）、
  或钉钉表格读取（dingtalk_sheet）。
compatibility: >
  需要钉钉官方 DWS CLI（dws）与有效登录态；Windows 计划任务以当前登录用户运行。
  所有原始聊天/文件写仓库外，绝不入库。
metadata:
  module: dingtalk_group_harvest
  scripts: cli.py, harvest.py, digest.py
  updated: 2026-11-03
---

# 钉钉 AI 项目群采集与周报

## 何时使用

- 要把钉钉群里的 `.md` 文件、消息、钉钉文档定期归档。
- 要判断该用群机器人、企业内部应用还是会话存档（答案：都读不了完整历史，用 DWS 个人身份）。
- 周报生成失败、DWS 结果不完整、计划任务没跑。

## 快速启动

```bash
uv run python -m dingtalk.dingtalk_group_harvest.cli resolve --write
uv run python -m dingtalk.dingtalk_group_harvest.cli harvest
uv run python -m dingtalk.dingtalk_group_harvest.cli digest
uv run python -m dingtalk.dingtalk_group_harvest.cli status
uv run pytest dingtalk/dingtalk_group_harvest/tests -q
```

## 硬规则

- 数据落 `%USERPROFILE%\dingtalk_harvest`（`DINGTALK_HARVEST_ROOT` 可覆盖），原始消息/附件/`groups.local.json` 全部 gitignore。
- 只有 DWS 返回 `complete=true`、`hasMore=false`、`failures=[]` 才推进水位；文件下载失败也不推进。
- 群名解析成功后固定 `openConversationId`，不要每次靠群名。
- 不用群机器人采集（只能发不能读）；首期不回推群。
- 在 worktree 注册的计划任务指向 worktree，合并后必须在主仓库重跑安装脚本。

## 新对话必读

- `../../../docs/solutions/tooling-decisions/dingtalk-group-harvest-dws-user-identity.md` — DWS 选型、完整性账本、水位、文件去重
- `../../../docs/solutions/developer-experience/claude-headless-long-prompt-stdin.md` — 周报润色为什么走 stdin
- `../../../docs/solutions/developer-experience/windows-schtasks-worktree-path-trap.md` — 计划任务路径陷阱

模块入口：`dingtalk/dingtalk_group_harvest/README.md`、`AGENT_HANDOFF.md`。
