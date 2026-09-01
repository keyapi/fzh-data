---
okf: v0.1
type: Reference
title: 渠道账号表列与 EN 字段
timestamp: 2026-08-25
---
# 表列与 EN 字段

Workbook：`和运营部共享`（id `1nbMO-wf-Oj7HIuYlPOtrC7F8QtsEPDE80BmXo8G6O3Y`）。
Tab：`渠道账号（20260521起在此维护）`（gid `763421711`）。

| 表列 | EN |
|------|-----|
| 渠道 | `Channel Account.channel` → Sales Channel |
| 渠道账号 | `name` / `account_id`（Illiosenergy → ILLIOSPL） |
| 渠道账号别名 | 子表 `Channel Account Alias.account_alias`（逗号分隔；canonical name 也要有一行） |
| 运营分组 | 本次未写入 EN 字段；只出现在计划 JSON |
| 运营人员YYYYMM | 折叠后写入 `Channel Account Owner.user` + `from_date` |

## Owner 子表

- `user`：中文名 Data，不是 User 邮箱。存量已是中文；`validate_user_exists` 按 User.name 查会失败，但历史数据就是这样写的。
- `from_date`：该负责人段的第一个月 1 号。
- `to_date`：本次追加时不填。
- `role_in_account`：新建账号第一条 Operator，之后 Primary Owner；已有账号追加用 Primary Owner。
- `is_active`：1。

## 拉数注意

- GET list `Channel Account Alias` / `Channel Account Owner`：本会话 403。
- GET `/api/resource/Channel Account/{name}`：父文档带 `channel_account_alias`、`owners`。
- PUT 父文档时提交**完整**子表数组。
