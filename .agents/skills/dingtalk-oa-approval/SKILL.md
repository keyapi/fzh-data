---
name: dingtalk-oa-approval
description: >
  钉钉 OA 销售收款确认单附件拉取与账期桶对照、Amazon 账期按账号对 NAS/核算/赛狐结算组。
  触发词：钉钉审批附件、OA附件、账期明细 txt、销售收款确认单、DRM 账期资料、
  Amazon 账期漏交、结算组、Rucener、Rosoon、Novelledo、YTHD、userNotExist、
  迟交挪动记录、提交时间不对、跨月剔除、账期日期与提交时间不一致、
  手填销售额、钉钉API与Excel交叉比对、催运营补交、
  aflow、dingtalk.aflow.receipt.export、dingtalk.aflow.receipt.attachments。
  不要用于钉钉群机器人发消息（那是 dingtalk-robot），不要改本地 NAS 同步副本。
---

# 钉钉 OA 审批附件

目录：`dingtalk/dingtalk_oa_approval/`。先读 `AGENT_HANDOFF.md`。
7 月 Amazon 对照结论：`docs/research/2026-09-10-july-amazon-period-reconcile.md`。
附件拉取与 DRM 对照数字：`docs/research/2026-09-09-attachment-fetch-and-drm-audit.md`。
迟交挪动登记 / 跨月剔除：`docs/reference/late-submission-registry.md`。
惯例：`docs/solutions/conventions/amazon-period-file-reconcile.md`。
API + aflow + 账期月过滤 + NAS：**同一条流水线**，手册 `docs/research/browser-admin-download.md`。

```text
uv run python dingtalk/dingtalk_oa_approval/fetch_attachments.py --start 2026-07-04
uv run python web_automation/scripts/dispatch.py dingtalk.aflow.receipt.export --check
uv run python dingtalk/dingtalk_oa_approval/filter_export_by_period.py --in <xlsx> --period 2026-07 --out <xlsx>
uv run python dingtalk/dingtalk_oa_approval/july_amz_by_account.py
```

铁律：缓存用 `fileId__原名`；对照 DRM「提交窗/人名」vs 核算「账期月」；负责人看渠道账号表 `运营人员YYYYMM`（没有当月列就用最新一列，并写明是哪一列），不看 NAS 人名夹；赛狐店名经别名对 `AMZ*` 文件前缀；不改 `D:\NAS与我共享\`；真搬文件只走 NAS API。保留口径：完成或审批中，且结果不是拒绝；已撤销不算。不下已撤销/拒绝、不下图片。Amazon 账期只认 `.txt`。离职账号附件 API 常 `userNotExist`（单上可能仍有文件），**不能当离职人员的漏交证据**。在职补交走 API，不要用 aflow `--only-departed`。算新月前先按迟交挪动登记的唯一键剔除，避免迟交单算两次。NAS 账号只从 `NAS_API/.env` 读。下载目录用 `DINGTALK_OA_WORK`，不要写本机人名路径。下载成功 ≠ 已入账期桶。

钉钉提交和赛狐结算组要并存。赛狐 API 会故障、会同步慢，以后也可能不用赛狐。每月先用钉钉 API 读表单，再用 aflow 导出的 Excel 按审批编号交叉；两边一致之后才和赛狐结算结束日对。只信一边不算对完。2026-10-09 实测：发起 9/1–10/9，API 与当日 15:13 Excel 的 9 月 Amazon 都是 74 行、61 个审批编号，集合相同。发起窗从该月 1 日看到今天，不只从 4 日；1–3 日提前交单独标出。

手填「销售额」这次没有核。它、附件 txt 的 `total-amount`、赛狐 `transferAmount` 是三个数，不能互相代替。没下附件之前只核有没有交、账期日期和销售账户是否与文件名一致。金额要等 txt：欧式逗号的 `total-amount` 才是打款；表上销售额可以更大（7 月 IT：表 131.15，txt `69,85` EUR）。

给人看的催办用渠道账号表真人名。进 git 的文档不写真名。拼音首字母会撞车，公开称呼用渠道账号 + 审批编号；必须点人时写「首字母 + 发起人 UserID」。真人名稿只放 `DINGTALK_OA_DATA`（仓库外或模块 `data/`，已 gitignore）。

浏览器：先读手册，再 `uv run python web_automation/scripts/dispatch.py dingtalk.aflow.receipt.export --check`（附件任务 `dingtalk.aflow.receipt.attachments`），按状态字面执行。写 NAS 先确认范围。人名映射用 gitignore 的 `person_folders.local.json`，不要把真名或 NAS 账号写进公开文档或 git。
