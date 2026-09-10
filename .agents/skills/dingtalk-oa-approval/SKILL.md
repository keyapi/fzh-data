---
name: dingtalk-oa-approval
description: >
  钉钉 OA 销售收款确认单附件拉取与账期桶对照、Amazon 账期按账号对 NAS/核算/赛狐结算组。
  触发词：钉钉审批附件、OA附件、账期明细 txt、销售收款确认单、DRM 账期资料、
  Amazon 账期漏交、结算组、Rucener、Rosoon、Novelledo、YTHD、userNotExist、
  迟交挪动记录、提交时间不对、跨月剔除、账期日期与提交时间不一致。
  不要用于钉钉群机器人发消息（那是 dingtalk-robot），不要改本地 NAS 同步副本。
---

# 钉钉 OA 审批附件

目录：`dingtalk/dingtalk_oa_approval/`。先读 `AGENT_HANDOFF.md`。
7 月 Amazon 对照结论：`docs/research/2026-09-10-july-amazon-period-reconcile.md`。
附件拉取与 DRM 对照数字：`docs/research/2026-09-09-attachment-fetch-and-drm-audit.md`。
迟交挪动登记 / 跨月剔除：`docs/reference/late-submission-registry.md`。
惯例：`docs/solutions/conventions/amazon-period-file-reconcile.md`。

```text
uv run python dingtalk/dingtalk_oa_approval/fetch_attachments.py
uv run python dingtalk/dingtalk_oa_approval/compare_local_nas.py
uv run python dingtalk/dingtalk_oa_approval/audit_vs_drm.py
uv run python dingtalk/dingtalk_oa_approval/july_amz_by_account.py
```

铁律：缓存用 `fileId__原名`；对照 DRM「提交窗/人名」vs 核算「账期月」；负责人看渠道账号表 `运营人员YYYYMM`，不看 NAS 人名夹；赛狐店名经别名对 `AMZ*` 文件前缀；不改 `D:\NAS与我共享\`；真搬文件只走 NAS API。不下已撤销/拒绝、不下图片。Amazon 账期只认 `.txt`。离职账号附件 API 常 `userNotExist`（单上可能仍有文件），**不能当离职人员的漏交证据**。算新月前先按迟交挪动登记的唯一键剔除，避免迟交单算两次。

浏览器下钉钉管理后台 Excel/附件：先读 `dingtalk/dingtalk_oa_approval/docs/research/browser-admin-download.md`，再 `uv run python web_automation/scripts/dispatch.py <task> --check`，按状态字面执行；当时若没有钉钉 capability 就停。写操作先确认范围。人名映射用 gitignore 的 `person_folders.local.json`，不要把真名写进公开文档或 git。
