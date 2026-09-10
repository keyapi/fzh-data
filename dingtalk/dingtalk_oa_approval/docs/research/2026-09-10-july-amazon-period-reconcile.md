---
okf: v0.1
type: Research
title: 2026-09-10 7 月 Amazon 账期 NAS/钉钉/赛狐对照
description: 上次合入之后的归档口径、别名匹配、95 个结算组结论、剩余缺口与浏览器补下载方向。人名用拼音首字母。
tags: [amazon, dingtalk, nas, sellfox, reconcile]
timestamp: 2026-09-10
resource: dingtalk/dingtalk_oa_approval/july_amz_by_account.py
---

# 2026-09-10 7 月 Amazon 账期对照

公开仓库用人名**拼音大写首字母**。NAS 文件夹真名只在 gitignore 的 `person_folders.local.json`（从 `person_folders.example.json` 复制后填真实文件夹名）。不要把核算缓存盘路径、NAS 密码、token 写进 git。`NAS_FINANCE_PERIOD_ROOT` / `LOCAL_NAS_PERIOD_ROOT` / `DINGTALK_OA_DATA` / `DINGTALK_OA_WORK` 见 `.env.example`。

| 首字母 | 角色（7 月相关） |
|--------|------------------|
| LYX | 如森各站 202607 表负责人；7 月多数 `AMZRosoon*` 钉钉发起人；已离职 |
| SYX | 如森各站 202608 表负责人；补交现任 |
| LTT | `AMZYTHDUS` 202607 表负责人；NAS 7 月该 txt 在其夹 |
| LTZ | Johnear-US / Strusery 7 月迟交提交人；`AMZYTHDUS` 202608 负责人 |
| JCY | Daneey-ES 提交人 |
| JHP | 部分 BAINA/CTRD/Ver 202607 负责人；LN 夹里有其店第一期 |
| LN | 已离职提交人；夹里有 JHP 名下店 7 月第一期 txt |
| CLB | Johnear-FR 等；核算补行（含 9/9 六张） |
| HWH | Johnear-US 202607 表负责人；实际 7 月 txt 由 LTZ 交 |
| LXJ | 结算周期 csv 不算 Amazon txt；人名夹别名曾与其重复，已去重 |
| WLR | `AMZYTHDUS` 更早历史夹 |
| YTQ | 大量 invoice PDF，核算 Amazon txt 用不上 |
| ZKY | 审批中 csv 综合集可跳过 |
| YB / SWY | 独立站 csv / PKO；按账期月归桶时用过 |

## 背景（上次 PR 之后）

目标：7/8 月销售收款确认单附件进财务 NAS 账期桶，并回答「哪些 Amazon 账期还没交」。

已固化口径（`AGENT_HANDOFF.md` / `nas_upload_api21.py` 的 `dest_bucket`）：

- 归档看钉钉「账期日期」自然月；跨月一张单才拆文件名。
- **木已成舟**：发起日 ≤ 2026-07-03 已进 6 月的，不再改归 7 月。
- 不写本地 `D:\NAS与我共享\`；搬文件只走 NAS FileStation（`fzh.nas`）。
- Amazon 账期只认 `.txt`。
- 21 位审批编号必须当文本。
- 9 月账期文件暂留 8 月桶。

过程中做过：迟交 txt 补进对应月桶；Johnear 属 7 月账期的从 8 月挪到 7 月；JCY 的 `AMZDANEEYES-2026-07-01.txt` 误传 7 月的副本已删、6 月原件保留；用 OA `get_instance` 按导出列补 9/9 之后的核算行，不必再等手工导出。

## 过程（按账号，不按人名夹）

1. 渠道账号表 `运营人员202607` / `202608` + `渠道账号别名` + `赛狐店铺`（`channel_account_sync/fetch_sources.py`）。
2. NAS 三桶全员扫文件名账期月 = 2026-07 的 Amazon txt。
3. 7 月核算表亚马逊行（账期日期在 7 月）。
4. 赛狐 OpenAPI `settlementSummary/groupPage.json`，结算结束日 2026-07-01～07-31，`isSite=true` → **95** 组。这不是后台逐店下载的 Amazon txt。
5. 匹配脚本 `july_amz_by_account.py`：先 brand+site，再用别名把 Rucener→ROSOON、Novelledo/YTHD→YTHD。

曾错把「赛狐有打款、脚本对不上」写成「表上没 AMZ 行」。表上一直有 `AMZRosoon*`、`AMZYTHDUS`。

## 结果（7 月、打款非 0 优先）

松口径（NAS **或** 核算，日期窗宽）：95 组 → 有一侧 **73**；打款 0 且两侧都无 **21**；有打款且两侧都无 **1**。

打款非 0 共 58 组。按文件日期/账期日期与 `groupEnd` 相差 ≤2 天：两侧都有约 52；其余要人工看，不能说「只缺 1 笔钉钉+附件」。

| 项 | 结论 |
|----|------|
| 如森-IT 7/8 打款 69.85，`AMZRosoonIT` | **缺钉钉**（故无附件）。NAS 该站最后一份在 2026-04 桶。202607 LYX，现任 SYX |
| 如森-SE 7/18 | **不是忘传**。审批 `202607231544000528489`（LYX，7/23，账期日期 7/18），附件 `AMZRosoonSE-2026-07-18.txt`；标准下载 `userNotExist`；单曾为 RUNNING；7 月桶只有 7/4 那份 |
| 君缘-Johnear-US 7/10 | 核算 `202608061717000057610`（LTZ）已进 7 月表；NAS 7 月桶有 `AMZJohnaUS-7.13.txt`（人工名，差几天） |
| Strusery-ES 7/15 | 同一张 `202608061654000326702`（LTZ）附 `AMZStruseryES-2026-7-16.txt`，已在 7 月桶；表单账期日期 7/16 |
| VERCART-SE 7/1、Daneey-ES 7/1 | 文件在 **6 月桶**，木已成舟，本轮不管 |
| 打款 0 的组 | 先不当漏交；若「出账期 7 天内必须交」连 0 打款也算，缺的远不止 IT |

如森 7 月 txt 多在 LYX 夹，8 月起多见 SYX 夹。云途 US：表负责人和 NAS 夹是 LTT，该笔核算发起人却是 LYX。

## 7 月定稿怎么来的（方法 1 vs 方法 2）

起因：7 月定稿一开始用的是「按提交窗导出」的那份（文件 1），后来发现迟交的单不在里面。

| | 定义 | 行数 |
|---|---|---|
| 文件 1 | 7 月提交窗导出（按发起时间；用于核对是否有未提交） | 129 = 6 月 3 + 7 月 124 + 8 月 2 |
| 文件 2 | 跨月导出（含 8、9 月账期，截至 9/8） | 396 |
| 方法 1 | 文件 1 + 迟交行 | 172 = 6 月 3 + 7 月 167 + 8 月 2 |
| **方法 2（采用）** | 文件 2 剔除账期日期在 8/9 月的行 | **170 = 6 月 3 + 7 月 167** |

- 文件 1 的全部行都在文件 2 里。
- 方法 1 会把 **2 条早交**（账期日期 8/3、8/4，发起落在 7 月窗口）留在 7 月文件里；方法 2 把它们拿掉。那 2 条要在 8 月核算里保留。
- 6 月遗留的 3 行按「木已成舟」**保留在 7 月文件**里，两种方法一致。
- 迟交行的登记与跨月剔除见 [late-submission-registry.md](../reference/late-submission-registry.md)。

**陷阱（关键）**：方法 2 里 21 位审批编号已被 Excel 收成数字，会对不上原文（例：`202608071142000210210` 变成 `202608071142000197632`），用编号会以为某行没进 7 月。**不要用方法 2 按审批编号对账**；改用编号为文本的 `核算_账期日期2026-07_销售收款确认单_20260910.xlsx`（170 行，含 Johnear）。8 月同理用 `核算_账期日期2026-08_销售收款确认单_20260910.xlsx`（**不含** Johnear）。

## 脚本（仓库内）

| 脚本 | 用途 |
|------|------|
| `sellfox_amz_settlements.py` | 拉结算组；`BRAND_ALIASES`（ROSOON/RUCENER、YTHD/NOVELLEDO） |
| `july_amz_txt_vs_sellfox.py` | `shop_key` 中文店名兜底 |
| `july_amz_by_account.py` | 按 brand+site 综合 NAS + 核算 + 赛狐 + 表负责人 |
| `export_period_excels.py` / `fill_aug_from_oa.py` | 核算表；审批编号文本；API 补行 |
| `nas_upload_api21.py` | `dest_bucket`；木已成舟返回空 |
| `fetch_attachments.py` | 标准下载；离职常失败 |

对照 xlsx 在仓库外核算缓存，**不要 commit**。

`DINGTALK_OA_TOOLS` 里的 `patch_july_2026.py` **没入库**，`export_period_excels.py` / `fill_aug_from_oa.py` / `july_amz_by_account.py` 都 import 它，新克隆直接跑会 `ModuleNotFoundError`。

## 下一步（给后续 Agent）

用户打算让 Claude **浏览器自动化**：进钉钉管理后台直接下销售收款确认单 Excel 和附件（尤其离职发起人、标准 API `userNotExist` 的单，如 SE 7/18）。

操作手册：[browser-admin-download.md](browser-admin-download.md)。必须先 `dispatch.py <task> --check`。仓库里当时还没有钉钉管理后台 capability，缺能力就停，不要绕过。
