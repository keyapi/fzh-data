---
okf: v0.1
type: Handoff
title: 钉钉 OA 销售收款确认单附件
description: 用企业内部应用读审批实例、下载账期明细/图片；与 DRM 按人归档的 NAS 桶对照。不改本地同步副本，搬文件只走 NAS API。
tags: [dingtalk, oa, approval, attachment, nas, 账期]
timestamp: 2026-09-10
---

# dingtalk_oa_approval

> 与 `dingtalk/dingtalk_robot` 并列。本模块**读 OA 审批附件**；机器人模块只负责群通知。

## 凭证

- 使用 new-api 那套**企业内部应用**（Client ID = 原 AppKey）。`.env` gitignore。
- ⚠️ 这套应用是**临时**借用的（原为钉钉登录 / 离职打通），权限面偏大。读**后台原生模板**（销售收款确认单）建议另开一个**企业内部应用**，只开下面 3 个 workflow 权限；`qyapi_aflow`（审批流数据管理）对读原生 OA 单没有用，可以从 new-api 应用拿掉。详见 [docs/reference/oa-attachment-api.md](docs/reference/oa-attachment-api.md)。
- 公开仓库用人名拼音首字母。真名文件夹映射：复制 `person_folders.example.json` 为 `person_folders.local.json`（gitignore）后填 NAS 真实文件夹名。
- 可设 `DINGTALK_OA_ENV` 指向仓库外 env（gitignore）。缓存目录 `DINGTALK_OA_DATA`（默认模块 `data/`）。核算导出 Excel / aflow 下载目录 `DINGTALK_OA_WORK`（**未设路径时脚本不得默认同事人名目录**）。NAS FileStation 账期根 `NAS_FINANCE_PERIOD_ROOT`（可分号分隔候选）。本地同步盘账期根 `LOCAL_NAS_PERIOD_ROOT`（**未设即报错**）。财务 NAS 账号读 `NAS_API/.env` 的 `NAS_ADMIN_USER`（或 `NAS_SSH_USER`），密码 `NAS_SSH_PASSWORD`，**不要把账号写进 git**。**不要**让它回退到 `NAS_USERNAME`——那是只做 API 的 DSM 账号，看不见「财务部」共享，静默用它会以为权限没问题。都不要把含人名的路径写进 git。
- 权限：`Workflow.Instance.Read`、`Workflow.Instance.Write`（下载接口要写权限）、`Workflow.Form.Read`。
- 模板：销售收款确认单 `PROC-FB234439-0642-451E-A514-20FBEF4A4241`。Excel「数据id」= `processInstanceId`，「审批编号」= `businessId`。

## 落盘（防重名覆盖）

缓存写到仓库外目录（`--out` 可改）。模块内 `data/` 仍 gitignore，避免附件进 git。

DRM 在 NAS 上按 **发起人姓名** 分子文件夹。这只表示谁提交，不是渠道账号负责人。负责人看 Google 表「和运营部共享」→「渠道账号」的 `运营人员YYYYMM`。同一账号可能出现在多个人名夹（助手、离职交接、换人）。钉钉标题名可能和财务文件夹不一致，映射在 `person_folders.local.json`（公开文档用拼音首字母 LXJ/LTZ/LYX/…）。

归档口径：**钉钉「账期日期」自然月** 与附件所在桶、核算表该月一致。跨月一张单才看文件名拆附件。**木已成舟**：已经在上一月提交窗里核算过的（例如发起日≤某月 3 日已进上月桶），不要再改归本月。Amazon 账期只认 `.txt`。同茎 csv 已在桶里则不再加 zip。无横杠日期（如 `20260708`）也按该月。迟交附件补进账期月对应桶。新月桶未开时，该月账期文件暂留上一桶。21 位「审批编号」写出 Excel 必须当文本。导出截止之后的单用 OA `get_instance` 按导出列补行。

## 两套「应该放哪」

| 口径 | 规则 | 谁在用 |
|---|---|---|
| 提交桶（现在） | 发起时间落入 4号~下月3号 → `账期YYYYMMDD-YYYYMMDD/{发起人}/` | DRM 从钉钉按发起时间下载 |
| 账期月（核算/Tax） | `账期日期` 自然月对应的那个桶 | 7 月账期 8/4 后才交的 Amazon txt，Colab1 应算进 7 月 |

## 铁律

- **不要改** `D:\NAS与我共享\...` 本地同步文件（单向同步，改了 NAS 不会跟着变）。
- 真要挪：NAS FileStation / NAS 网页。先对照表，经 DRM 审核。
- 9 月桶 `账期20260904-20261003` DRM 要 10/4 后才下。
- **不下** 已撤销 / 拒绝（`keep_approval`：完成或审批中，且结果≠拒绝）。
- **不下图片**。部分 PDF / 审批中 csv 可不纳入综合集。
- 离职附件标准 API 常 `userNotExist`：先综合 DRM 已归档与核算 Excel；专享接口见 docs/research。实例详情仍可读，附件可能已在单上只是下不下来。
- 财务 NAS FileStation 用 `NAS_API/.env` 里的管理员账号（要能看见财务部共享），不要用看不到财务部的测试账号。
- 未开的新月桶等 DRM 日切后再下；迟交件按账期月进已有桶，不预建空人名夹。
- 算某个账期月之前，先跑 `late_submission_keys.py --period <YYYY-MM>` 从[迟交挪动登记](docs/reference/late-submission-registry.md)导出**唯一键** `审批编号|账期日期|销售账户|销售额` 剔除集，再交给 `filter_export_by_period.py --exclude-keys`，否则迟交单会被算两次。两个脚本都调 `ding_xlsx.build_key()`，**不要**直接用表里那列「唯一键」（金额 `0` vs `0.0` 会对不上）。

## 7 月 Amazon 对账结论（2026-09-10）

完整过程与剩余缺口：[docs/research/2026-09-10-july-amazon-period-reconcile.md](docs/research/2026-09-10-july-amazon-period-reconcile.md)。惯例：[docs/solutions/conventions/amazon-period-file-reconcile.md](../../docs/solutions/conventions/amazon-period-file-reconcile.md)。附件拉取与 DRM 对照数字：[docs/research/2026-09-09-attachment-fetch-and-drm-audit.md](docs/research/2026-09-09-attachment-fetch-and-drm-audit.md)。

- 按**账号**对，不按人名夹。赛狐店名经 `赛狐店铺` / 别名对到 `AMZRosoon*`、`AMZYTHDUS`。
- 赛狐 `groupPage` 95 个 7 月结算组 ≠ Amazon txt 原件。「有 NAS 或核算」≠「这一期钉钉且附件都齐」。
- `AMZRosoonIT` 结算结束 2026-07-08：2026-09-10 起 SYX **已补交钉钉**。下一步是 API 拉取附件 + 按账期月进 7 月 NAS 桶，不是再催交。
- 钉钉有附件、标准 API 下不来、NAS 缺对应 txt：`AMZRosoonSE-2026-07-18.txt`，审批 `202607231544000528489`（LYX 离职发起）→ aflow `--mode attachments` 后再 `archive_aflow_to_nas.py`。
- 6 月已核算的 7/1 文件（Daneey-ES、VERCART-SE 等）本轮不管。

浏览器 + API + 账期月过滤 + NAS 是同一条流水线：[docs/research/browser-admin-download.md](docs/research/browser-admin-download.md)。先 `uv run python web_automation/scripts/dispatch.py dingtalk.aflow.receipt.export --check`（附件任务同理）。确认范围，不改本地 NAS 同步盘。

## 命令

```text
uv run python dingtalk/dingtalk_oa_approval/fetch_attachments.py --start 2026-07-04
uv run python dingtalk/dingtalk_oa_approval/filter_export_by_period.py --in <导出xlsx> --period 2026-07 --out <7月定稿xlsx>
uv run python dingtalk/dingtalk_oa_approval/compare_local_nas.py
uv run python dingtalk/dingtalk_oa_approval/audit_vs_drm.py
uv run python dingtalk/dingtalk_oa_approval/combine_jul_aug.py
uv run python dingtalk/dingtalk_oa_approval/nas_upload_api21.py --dry-run
uv run python dingtalk/dingtalk_oa_approval/archive_aflow_to_nas.py --dry-run
uv run python dingtalk/dingtalk_oa_approval/july_amz_by_account.py
```

读导出 / 展开销售账户 / 21 位审批编号文本在 `ding_xlsx.py`（已入库）。仓库外 `patch_july_2026.py` 只剩一次性 Google 表写入等，不再被上面这些脚本 import。
