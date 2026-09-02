---
okf: v0.1
type: Lesson
title: Google Drive 权限管理 — 经验教训
description: 踩坑记录：writersCanShare vs capabilities.canShare、权限接口 vs 内容接口、SA vs 用户 OAuth、Testing 7天、invalid_scope、PII 治理
---

# 经验教训

> 这些是实际操作中踩出来的。写成通用规律，避免下一个 Agent 重蹈。

## Lesson 1：「仅属主可改共享」的真正开关是 `writersCanShare`

- **表象**：服务账号是 writer，但调 Drive API 删人/加人时被 403。
- **根因**：文件的共享设置里开启了「仅属主可改共享」。它对应的字段是 **`files.update` 的 `writersCanShare`（顶层布尔）**，而不是 `capabilities.canShare`。
- **`capabilities.canShare` 的意义**：反映**当前调用者**能否共享。用属主凭证查永远 `True`（属主当然能共享），所以用它判断「SA 能不能改共享」会**误判**。
- **正确姿势**：判断 SA 能否操作，必须用 **SA 凭证**调 `files.get` 看返回的 `capabilities.canShare`。
- **修复**：属主（用户 OAuth）`PATCH /drive/v3/files/{id}` body `{"writersCanShare": true}` → SA 之后就能改共享。

## Lesson 2：权限接口 ≠ 内容接口（spreadsheet 与 Colab 权限无需分开）

- **加/删共享**：一律走 **Drive API `files/{id}/permissions`**。无论 spreadsheet 还是 Colab，在 Drive 里都是"一个文件"，权限管理完全一致。gspread 的 `sh.share()` 底层也是这个。
- **改内容**才分家：spreadsheet 内容 → **Sheets API**（gspread）；`.ipynb` → **Drive files.get/update**（JSON 文件，无专门 API）。
- **结论**：权限台账里 spreadsheet 和 Colab **不需要拆成两个表**；加一列「类别」区分即可，筛选/批量按类别过滤。

## Lesson 3：服务账号 vs 用户 OAuth 的可见范围天差地别

- **服务账号**：独立身份（`colab-gsheets@gsheets-351101.iam.gserviceaccount.com`），只能看到**显式共享给它**的文件（本项目约 130）。
- **用户 OAuth**（kyzh2022）：看到该用户可访问的**全部**（989 表 + 134 Colab ≈ 1123 文件）。
- **要全局审计/清理**必须用**用户 OAuth**；服务账号只适合固定共享给它的业务表。
- 这条解释了「为什么之前 Sheets 一直能用（服务账号私钥）但看不到全盘」。

## Lesson 4：Testing 状态 refresh token 7 天过期 —— 别一概而论

- 外部 OAuth 应用处于 **Testing**、且请求 **drive 等非基础 scope** 时，签发的 **refresh token 7 天过期**。
- **不适用**：
  - 服务账号私钥（无 7 天限制，直到撤销）；
  - access token（本来约 1 小时，每次用 refresh token 换新）。
- 用户拿「Google API credentials expire after one week」质询时，要分清是哪一种。**服务账号的 Sheets 一直能用，就是因为它是私钥。**
- 长期方案：把 OAuth 应用发布为 Production（个人自用 <100 用户可不做正式验证，仅有未验证提醒）→ refresh token 不再是 7 天。

## Lesson 5：invalid_scope 的坑

- 凭证只被授权过 `drive` scope 时，脚本再请求 `drive + spreadsheets` 两个 scope，`refresh()` 报 **`invalid_scope`**。
- **解法**：要么只请求一个 scope（`drive` 就够 gspread 建表/写数）；要么重新做 OAuth 授权把两个 scope 都纳入 refresh token。
- 别误以为凭证坏了，先看 scope 是否和授权时一致。

## Lesson 6：PII 治理 —— 员工邮箱绝不入仓

- 权限台账/审计 CSV 含**真实员工邮箱**（PII）。这些**只能**放 Google Sheet 台账（受控可访问），**绝不提交 git**。
- 脚本的 CSV 产物（`*_ledger.csv`、`*_audit.csv`、`accounts_master.csv`）统一加进 `.gitignore`。
- 经验：**权威数据放 Google Sheet，脚本从 Sheet 读**，本地 CSV 只是逐次运行的临时产物。

## Lesson 7：batch 审计用 files.list 而非逐表 list_permissions

- 用 gspread 逐表 `list_permissions()` 需要几百次串行调用（本项目 260 次花了 12 分钟+）。
- **快得多**：`Drive files.list` 带 `permissions(...)` 字段，一次分页拉全部；加权限 `POST permissions.create`、删 `DELETE permissions/{id}`。
- 400+ 文件时差距是数量级的，优先 Drive API 批量。
