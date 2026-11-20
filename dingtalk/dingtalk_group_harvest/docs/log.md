---
okf: v0.1
type: Log
title: dingtalk_group_harvest 变更日志
---

# 变更日志

## 2026-11-03（ce-okf 收尾）

- **验证**：首次真实采集 103 条消息、22 个唯一文件归档、0 失败；第二遍 0 新增。W44 周报已生成，Claude Code 润色路径验证通过。
- **修复**：`claude -p` 长提示词改走 stdin（Windows argv 32K 限制）。
- **新增**：`docs/solutions/` 三篇经验（DWS 选型、claude stdin、worktree 计划任务）。
- **提醒**：worktree 里注册的计划任务需在合并后从主仓库重跑安装脚本。

## 2026-11-03（首版）

- **新增** `dingtalk/dingtalk_group_harvest/`：DWS 个人身份采集三个 AI 项目群的增量消息、附件、钉钉文档。
- **验证**：三个群均可按名称唯一解析；文件消息 23 条（含 .md/.docx/.xls/.zip）；样例 `.md` 下载成功（UTF-8，11.5KB）；整群拉取自动下载图片与 md。
- **决策**：不使用群机器人采集；原始数据全部落仓库外；水位只在完整时推进；首期不做实时 Stream。
- **新增** 每日采集/每周汇总的 schtasks 安装脚本。
- **测试**：`tests/test_normalize.py`、`test_state.py`、`test_ledger.py`。
