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
| OA API | 在职发起人表单（账期日期、销售账户、附件文件名）、实例详情、附件字节 | `get_instance` / `fetch_attachments.py`（`--end` 默认今天） |
| aflow 浏览器 | 同一发起窗的管理后台 Excel，用来和 API 对审批编号；离职发起人附件（API `userNotExist`） | `dingtalk.aflow.receipt.export` / `.attachments` |
| 账期月切开 | 导出按**发起时间**，定稿按**账期日期**自然月 | `filter_export_by_period.py` |
| NAS 归档 | 只走 FileStation；账号/URL/密码只在 `NAS_API/.env` | `nas_upload_api21.py`（API 缓存）、`archive_aflow_to_nas.py`（浏览器缓存） |

浏览器脚本在 `web_automation/`（PR 227）。本模块不复制那份代码，只约定目录与后续步骤。

选择器、登录（`.env` 账号密码 → 陌生设备短信一次 → `--channel chrome`）、SPA hash 必须 `reload`：见 `web_automation/docs/reference/aflow-receipt-export.md`。

## 每月：API、Excel、赛狐三条线

钉钉运营提交和赛狐结算组在一段时间内都要留着。赛狐出问题、同步不全、或以后不用赛狐时，仍然要能只靠钉钉判断「交了没有、填错没有」。

1. **钉钉 API**（不下附件也能做）：发起时间从该月 1 日到今天。保留完成和审批中，去掉拒绝和已撤销。读每行账期日期、销售账户、附件文件名。
2. **aflow Excel**：同一发起窗自己导出（用户刚下的同一窗口 xlsx 可以先用）。按 21 位审批编号（文本）对 API：行数、状态、账期日期、销售账户。差集写出来，不要只报「差不多」。导出格里的「账期明细」常常只是「1个附件」，文件名以 API 表单为准。
3. **赛狐**（有则对，没有也不要停）：`groupPage`，`timeType=settlementEndTime`，`isSite=true`，结算结束日在该自然月。这是赛狐已经同步的组，不是亚马逊全部账期。有打款却对不上钉钉行的，才是催交；打款 0 先不催。别名先对上再判漏（熙锦 `AMZBJXJ*` = Jalnodd，`AMZTOODDLY*` = TOODDLY-Daneey）。
4. **填错**：同一张单上，账期日期或销售账户和 txt 文件名不一致。这是改单，不是漏交。
5. **手填金额先不要和赛狐打款比。** 表上「销售额」、txt 的 `total-amount`、赛狐 `transferAmount` 各是各的。金额是否填对，等附件 txt 的打款额。2026-10-09 这一轮没有下 txt，所以没有核销售额。

催办对话用渠道账号表真人名（没有 `运营人员YYYYMM` 当月列就用最新列，并写明列名）。进 git 不写真名。真人名只放 `DINGTALK_OA_DATA`。

2026-10-09：发起 9/1–10/9，API 与 15:13 Excel 的 9 月 Amazon 都是 74 行（完成 62、审批中 12）、61 个审批编号，集合相同。9/1–9/3 没有账期落在 9 月的 Amazon 行。

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
