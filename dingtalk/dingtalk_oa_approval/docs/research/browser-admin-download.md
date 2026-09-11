---
okf: v0.1
type: Research
title: 钉钉管理后台浏览器补下载与 7 月账期收口
description: API + aflow 浏览器 + 账期月过滤 + NAS 归档是同一条流水线。必须先 dispatch --check。公开叙述用人名首字母。
tags: [dingtalk, browser, web-automation, oa, attachment, aflow, nas]
timestamp: 2026-09-11
resource: web_automation/scripts/dispatch.py
---

# 钉钉账期补下载（API + aflow + NAS）

本文件是 **226（OA/NAS/对账）和 227（aflow 浏览器）拼在一起的操作手册**。不要把两边当成两套互斥方案。本文件不是许可扩大到全历史。

## 两段能力怎么拼

| 段 | 做什么 | 入口 |
|----|--------|------|
| OA API | 在职发起人附件、实例详情、核算补行 | `fetch_attachments.py`（`--end` 默认今天） |
| aflow 浏览器 | 管理后台 Excel；离职发起人附件（API `userNotExist`） | `dingtalk.aflow.receipt.export` / `.attachments` |
| 账期月切开 | 导出按**发起时间**，定稿按**账期日期**自然月 | `filter_export_by_period.py` |
| NAS 归档 | 只走 FileStation；账号/URL/密码只在 `NAS_API/.env` | `nas_upload_api21.py`（API 缓存）、`archive_aflow_to_nas.py`（浏览器缓存） |

浏览器脚本在 `web_automation/`（PR 227）。本模块不复制那份代码，只约定目录与后续步骤。

选择器、登录（`.env` 账号密码 → 陌生设备短信一次 → `--channel chrome`）、SPA hash 必须 `reload`：见 `web_automation/docs/reference/aflow-receipt-export.md`。

## 为什么还要走浏览器

- 标准 OA 下载按发起人钉盘授权。离职发起人常 `userNotExist`。实例详情仍可读，附件可能已经在表单上。
- 专享 `.../premium/.../urls/download` 文档支持离职，但本企业实测 `benefit.status.invalid` / `403 AccessTokenPermissionDenied`。
- 管理员在钉钉客户端能打开，是因为**查看者是在职用户**。浏览器用的是这条在职会话。
- **在职补交**（例如 SYX）优先 API，不要用 `--only-departed`（默认只筛姓名含「离职」的发起人）。

详见 [departed-originator-download.md](departed-originator-download.md)。

## 7 月还没收口的两笔（2026-09-11）

| 优先级 | 对象 | 现状 | 下一任怎么拿 |
|--------|------|------|----------------|
| 1 | `AMZRosoonIT` 7/8 | **2026-09-10 SYX 已补交钉钉**。此前缺单；浏览器解决不了「没交」。现在单已在，发起人在职。 | `fetch_attachments.py --start 2026-07-04`（`--end` 默认今天，必须盖过 9/10）。再 `nas_upload_api21.py --dry-run`。 |
| 2 | 审批 `202607231544000528489` / `AMZRosoonSE-2026-07-18.txt` | LYX 离职发起，API `userNotExist`，7 月桶只有 7/4。 | aflow `--mode attachments`（默认 `--only-departed`）。下到 `DINGTALK_OA_WORK` 后 `archive_aflow_to_nas.py --dry-run`。 |
| 3 | 7 月核算 Excel | 钉钉只能按发起时间导出。要「只保留 7 月账期」必须宽窗再过滤。SYX 9/10 补交会落在 9 月发起窗。 | export `--from 2026-07-04 --to <今天>` → `filter_export_by_period.py --period 2026-07`。迟交行用 `late_submission_keys.py --period 2026-07` 生成剔除集后 `--exclude-keys`（见[登记表](../reference/late-submission-registry.md)）。 |

不要把「有核算行」当成「NAS 已有 txt」。SE 7/18 就是反例。IT 7/8 补交之后仍要核对 **NAS 7 月桶**里是否出现对应 txt。

木已成舟的 7/1（Daneey-ES、VERCART-SE）不要再改归 7 月。

## 必须先做的路由

```text
uv run python web_automation/scripts/dispatch.py dingtalk.aflow.receipt.export --check
uv run python web_automation/scripts/dispatch.py dingtalk.aflow.receipt.attachments --check
```

按输出状态字面执行：`READY` / `NEED_BROWSER` / `NEED_LOGIN` / `NEED_OCR` / `NEED_USER_CONFIRMATION` / `BLOCKED`。

**不要**自己拼 Playwright 脚本路径或本机人名目录。`--out` 读 `DINGTALK_OA_WORK`（未设即报错）。组织名读 `DINGTALK_ORG`。NAS 账号读 `NAS_ADMIN_USER` / `NAS_SSH_USER` / `NAS_USERNAME`（只用最后一个会警告：可能看不见「财务部」），不要写进 git。

写 NAS 无范围确认时必须停。本任务默认范围：

- 只补 **7 月 Amazon 已确认缺口**（IT 7/8 的 SYX 补交；SE 7/18；以及用户当场点名的其它单）
- 不要扩大到全店铺、全历史桶、9 月未开桶
- 下载落后盘到 `DINGTALK_OA_DATA` / `DINGTALK_OA_WORK`；**不要写** `D:\NAS与我共享\`
- 真要进财务桶：NAS FileStation，按**账期日期自然月**进已有桶

## 建议命令（7 月收口；先 --check / dry-run）

```text
uv run python dingtalk/dingtalk_oa_approval/fetch_attachments.py --start 2026-07-04

uv run python web_automation/scripts/dispatch.py dingtalk.aflow.receipt.export --check
uv run python web_automation/scripts/dispatch.py dingtalk.aflow.receipt.export -- --from 2026-07-04 --to 2026-09-11

uv run python dingtalk/dingtalk_oa_approval/late_submission_keys.py --period 2026-07 --out "<DINGTALK_OA_DATA>/reports/exclude_2026-07.txt"
uv run python dingtalk/dingtalk_oa_approval/filter_export_by_period.py --in "<DINGTALK_OA_WORK 下刚下的 xlsx>" --period 2026-07 --exclude-keys "<上一步的 exclude 文件>" --out "<DINGTALK_OA_DATA>/reports/核算_账期日期2026-07_销售收款确认单_今日.xlsx"

uv run python web_automation/scripts/dispatch.py dingtalk.aflow.receipt.attachments --check
uv run python web_automation/scripts/dispatch.py dingtalk.aflow.receipt.attachments -- --from-xlsx "<上面那份导出>"

uv run python dingtalk/dingtalk_oa_approval/nas_upload_api21.py --dry-run
uv run python dingtalk/dingtalk_oa_approval/archive_aflow_to_nas.py --dry-run
```

真上传 NAS 才加 `--apply --confirm-scope july-2026-it-se-gaps`（`archive_aflow_to_nas.py`）或按 `nas_upload_api21.py` 既有确认。

下载成功 ≠ 已进 7 月桶。39/39 离职附件也不能代替「SE 7/18 那张 txt 已在 NAS」。对照文件名 `AMZRosoonSE-2026-07-18.txt` 和 `AMZRosoonIT` 7/8 那份。

## 归档口径（下载后仍要遵守）

- 木已成舟：发起日 ≤ 2026-07-03 已进 6 月的，不要再改归 7 月
- Amazon 账期只认 `.txt`
- 21 位审批编号当文本
- NAS 人名夹 = 提交人，不是渠道负责人
- 真名文件夹只在本地 `person_folders.local.json`；公开叙述用拼音首字母
- 算新月前按迟交唯一键 `审批编号|账期日期|销售账户|销售额` 剔除

## 7 月对照结论（避免浏览器白跑）

赛狐 7 月 `groupPage` **95** 组。松口径有 NAS 或核算 **73**；打款 0 且两侧无 **21**；当时有打款且两侧无 **1**（`AMZRosoonIT` 7/8）。2026-09-10 起 IT 7/8 不再是「钉钉上没有单」。

完整过程：[2026-09-10-july-amazon-period-reconcile.md](2026-09-10-july-amazon-period-reconcile.md)。
