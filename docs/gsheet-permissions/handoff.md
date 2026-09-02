---
okf: v0.1
type: Handoff
title: Google Sheet 权限运维 — Agent 参考
description: 凭证路径、Google Sheet 台账 sheet_id、脚本函数表、Drive/Sheets API 机制、边界条件
---

# Agent Handoff — Google Sheet 权限运维

> 给 Agent（Claude Code / Codex）快速上手用。**不含任何员工邮箱/账号明文的硬编码**（一律从 Google Sheet 台账读）。

## 1. 凭证（在父仓库，不在 git）

| 凭证 | 路径 | 用场 |
|------|------|------|
| 服务账号私钥 | `D:\Work\赛狐\Cursor\secrets\gsheets-service-account.json` | 只读/改显式共享给它的文件 |
| 用户 OAuth | `D:\Work\赛狐\Cursor\secrets\gsheets-user-oauth.json` | 全局审计（属主 kyzh2022） |
| Desktop client_secret | `D:\Work\google\client_secret_234331188447-…apps.googleusercontent.com.json` | 重新授权用户 OAuth |

> worktree 里没有这些文件。运行脚本必须带环境变量：
> `GSPREAD_SERVICE_ACCOUNT_FILE="D:/Work/赛狐/Cursor/secrets/gsheets-service-account.json"`
> 加载用户 OAuth 用 `google.oauth2.credentials.Credentials.from_authorized_user_file(...)` + `refresh(Request())`。

## 2. Google Sheet 台账（权威源）

- **sheet_id**: `1TTVVHQOe5VCmdLZynGFAKXSPUVIvtlB6kOOqgszIqD0`
- 链接: https://docs.google.com/spreadsheets/d/1TTVVHQOe5VCmdLZynGFAKXSPUVIvtlB6kOOqgszIqD0
- **账号主清单** worksheet 列：`状态 | 账号 | 识别/备注 | 处理方式 | 当前文件数`（状态=自己/SA/在职/离职/待确认；处理方式=不取消/保留/已清理/已清(遗留)）
- **现状明细** worksheet 列：`类别 | 文件名称 | 文件ID | 属主 | 链接 | 账户 | 角色`（类别=电子表格/Colab）
- 打开/读取用 gspread：`gc.open_by_key(SHEET_ID)`（SA 或用户凭证均可，账号主清单已含 SA editor）

> **数据源约定**：所有账号邮箱（离职名单、现任/前任财务、在职保留等）**一律从本台账读**（见 `scripts/sheet_ledger.py`），脚本内**不硬编码任何邮箱**（PII 治理）。用「识别/备注」列找现任财务负责人等语义账号。

## 3. 脚本（docs/gsheet-permissions/scripts/）

全部从**脚本所在目录运行**：`cd docs/gsheet-permissions/scripts/ && uv run python <script>.py`。
运行需 `GSPREAD_SERVICE_ACCOUNT_FILE` 环境变量（SA 类）或用用户 OAuth token 文件。

| 脚本 | 用途 | 凭证 | 幂等 | CSV 产物 |
|------|------|------|------|---------|
| `audit_gsheet_permissions.py` | 只读盘点 spreadsheet 权限（Drive files.list 一次拉全，快） | SA | 只读 | gsheet_permission_audit.csv |
| `audit_drive_permissions.py` | 用户级全量盘点 spreadsheet+Colab 权限 | 用户OAuth | 只读 | drive_permission_ledger.csv + colab_permission_ledger.csv |
| `cleanup_gsheet_permissions.py` | 补 zj 到含 zhongyu 的表 + 移除离职账号 | SA | dry-run 默认 | — |
| `add_sa_to_business_colab.py` | 给业务 Colab 补 SA writer（幂等） | 用户OAuth | 是 | — |
| `check_oauth_token.py` | 验证用户 OAuth token 可 refresh + Drive about | 用户OAuth | 只读 | — |
| `check_colab_capabilities.py` | 检查 Colab canShare/canEdit | 用户OAuth | 只读 | — |
| `share_tongtu_order_editor.py` | 给 12 张通途订单表加编辑权限（无参则从台账取现任财务） | SA | 是 | — |
| `list_colab_and_public.py` | 收集全部 Colab 状态 + 公开链接表 | 用户OAuth | 只读 | — |
| `auth_gsheets_user.py` | 一次性授权：浏览器登录后把 refresh token 存到 secrets | 用户 | — | — |
| `sheet_ledger.py` | **共享模块**：从台账读账号列表（removed/kept/all） | SA | 只读 | — |

> **归档/初期脚本（含 PII，不入仓，仅供本地参考）**：`build_accounts_master.py`（建台账，内含离职/在职+姓名备注）、`create_permissions_ledger_sheet.py`（建台账）。已移至 `docs/gsheet-permissions/_init_local/`（gitignore）。

## 4. API 机制

- **加/删共享**（与 mimeType 无关）：`POST /drive/v3/files/{id}/permissions`、`DELETE /drive/v3/files/{id}/permissions/{permId}`。
  加用 `sendNotificationEmail=false` 可静默；权限 body `{role, type:"user", emailAddress}`。
- **批量审计快径**：`files.list` 带 `permissions(id,emailAddress,role,type)` 字段，一次拿全（避免逐表 list_permissions 的几百次调用）。
- **改内容**才分：spreadsheet→Sheets API(gspread)；.ipynb→Drive files.get/update。
- **限流**：429/500/503 需退避重试（本项目脚本 `api()` 已实现 4 次指数退避）。

## 5. 边界与坑

- **查 SA 能否操作**：必须用 **SA 凭证** 调 `files.get` 看 `capabilities.canShare`；用属主凭证查永远 true，会误判。
- **「仅属主可改共享」开关** = `writersCanShare`（`files.update` 顶层布尔）。`capabilities.canShare` 只是调用者能否共享，别混淆。
- **Testing 状态 refresh token 7 天过期**（external app 请求 drive scope）；服务账号私钥永不过期；access token 约 1 小时。改消息别一概而论。
- **invalid_scope**：refresh token 只授权过 `drive` 时，再请求 `drive+spreadsheets` 会报错。gspread 用 `drive` scope 即可，或重新授权两个 scope。
- **PII**：所有含员工邮箱的明细都只放 Google Sheet 台账，**绝不入仓**。脚本 CSV 产物已被 .gitignore 排除。
- **凭证不入仓**：`secrets/*.json`、client_secret、refresh token 均由 .gitignore 保护。

## 6. 离职账号名单 & 在职保留

不在文档里硬编码（PII）。以 **Google Sheet 台账「账号主清单」** 为准：`处理方式` 列标了 保留 / 不取消 / 已清理 / 已清(遗留)。执行前先读该 worksheet。
